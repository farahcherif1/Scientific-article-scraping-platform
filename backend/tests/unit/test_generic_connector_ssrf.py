"""
SSRF guard tests (security review finding, EP-custom-connectors): a custom
connector's `base_url` is entirely researcher-supplied, so without a host
check it could be pointed at the cloud metadata address, loopback, or any
other internal service reachable from this backend - and the unauthenticated
"test connection" endpoint would reflect that response straight back to
whoever called it.

Split from test_generic_connector.py (which uses real-looking hostnames as
mocked-HTTP fixtures and injects a no-op host guard) since this file's whole
point is exercising the guard itself.
"""
import ipaddress

import pytest

from app.connectors.generic import GenericConnector, SSRFBlockedError, default_host_guard
from app.connectors.generic_config import (
    CustomConnectorConfig,
    FieldMapping,
    FieldMappingConfig,
    PaginationConfig,
    PaginationStyle,
    QueryMapping,
    is_unsafe_ip,
)
from app.domain.entities import ConnectorError


class _NoopRateLimiter:
    async def acquire(self) -> None:
        return None


def _minimal_config(**overrides) -> CustomConnectorConfig:
    defaults = {
        "base_url": "https://example.org/search",
        "query_mapping": QueryMapping(keyword_param="q"),
        "pagination": PaginationConfig(style=PaginationStyle.NONE, results_path="results"),
        "field_mapping": FieldMappingConfig(title=FieldMapping(path="title")),
    }
    defaults.update(overrides)
    return CustomConnectorConfig(**defaults)


class TestIsUnsafeIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",  # loopback
            "10.0.0.5",  # private
            "172.16.0.1",  # private
            "192.168.1.1",  # private
            "169.254.169.254",  # link-local - cloud metadata address
            "0.0.0.0",  # unspecified
            "224.0.0.1",  # multicast
            "::1",  # IPv6 loopback
            "fc00::1",  # IPv6 unique local (private)
        ],
    )
    def test_unsafe_addresses_are_flagged(self, ip):
        assert is_unsafe_ip(ipaddress.ip_address(ip)) is True

    @pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "93.184.216.34"])
    def test_public_addresses_are_not_flagged(self, ip):
        assert is_unsafe_ip(ipaddress.ip_address(ip)) is False


class TestConfigValidatorRejectsLiteralPrivateIps:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/search",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5:8080/api",
            "http://[::1]/search",
        ],
    )
    def test_literal_private_ip_rejected_at_save_time(self, url):
        with pytest.raises(ValueError, match="private/internal address"):
            _minimal_config(base_url=url)

    def test_public_hostname_is_accepted(self):
        # No DNS resolution happens here - a hostname (not a literal IP)
        # always passes this validator; it's re-checked post-resolution at
        # request time by default_host_guard instead.
        config = _minimal_config(base_url="https://api.example.org/search")
        assert config.base_url == "https://api.example.org/search"

    def test_public_literal_ip_is_accepted(self):
        config = _minimal_config(base_url="http://8.8.8.8/search")
        assert config.base_url == "http://8.8.8.8/search"


class TestDefaultHostGuard:
    def test_blocks_private_hostname(self, monkeypatch):
        monkeypatch.setattr(
            "socket.getaddrinfo",
            lambda host, port: [(2, 1, 6, "", ("10.0.0.5", 0))],
        )
        with pytest.raises(SSRFBlockedError, match="private/internal address"):
            default_host_guard("http://internal.example.org/search")

    def test_allows_public_hostname(self, monkeypatch):
        monkeypatch.setattr(
            "socket.getaddrinfo",
            lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))],
        )
        default_host_guard("http://public.example.org/search")  # does not raise

    def test_raises_on_dns_failure(self, monkeypatch):
        import socket

        def _raise(host, port):
            raise socket.gaierror("nope")

        monkeypatch.setattr("socket.getaddrinfo", _raise)
        with pytest.raises(SSRFBlockedError, match="Could not resolve"):
            default_host_guard("http://does-not-exist.invalid/search")

    def test_rejects_url_with_no_hostname(self):
        with pytest.raises(SSRFBlockedError, match="no hostname"):
            default_host_guard("not-a-url")


class TestGenericConnectorHonorsHostGuard:
    def _connector_with_blocking_guard(self) -> GenericConnector:
        def _blocking_guard(url: str) -> None:
            raise SSRFBlockedError("blocked for test")

        return GenericConnector(
            slug="blocked_source",
            config=_minimal_config(),
            rate_limiter=_NoopRateLimiter(),
            host_guard=_blocking_guard,
        )

    async def test_search_raises_connector_error_when_host_is_blocked(self):
        connector = self._connector_with_blocking_guard()
        with pytest.raises(ConnectorError, match="blocked for test"):
            await connector.search("ai", max_results=5)

    async def test_test_connection_raises_connector_error_when_host_is_blocked(self):
        connector = self._connector_with_blocking_guard()
        with pytest.raises(ConnectorError, match="blocked for test"):
            await connector.test_connection("ai", max_results=5)

    async def test_health_check_returns_false_when_host_is_blocked(self):
        connector = self._connector_with_blocking_guard()
        assert await connector.health_check() is False

    async def test_search_makes_no_http_call_when_host_is_blocked(self, httpx_mock):
        # No httpx_mock.add_response() registered - if search() reaches the
        # HTTP layer at all despite the guard, pytest-httpx fails the test.
        connector = self._connector_with_blocking_guard()
        with pytest.raises(ConnectorError):
            await connector.search("ai", max_results=5)
        assert len(httpx_mock.get_requests()) == 0
