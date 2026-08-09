"""
Shared-rate-limiter regression tests for `app.connectors.registry` (security
review finding, see the module docstring): concurrent collections against the
same custom connector must share one `AsyncRateLimiter` instance, the same
way the built-in connectors share their module-level singletons
(app/orchestrator/rate_limiter.py) - otherwise each concurrently-running
collection gets its own limiter and the source sees up to N x the configured
`rate_limit_rps`.
"""
from app.connectors.generic_config import (
    CustomConnectorConfig,
    FieldMapping,
    FieldMappingConfig,
    PaginationConfig,
    PaginationStyle,
    QueryMapping,
)
from app.connectors.registry import _make_factory


def _minimal_config(**overrides) -> CustomConnectorConfig:
    defaults = {
        "base_url": "https://example.org/search",
        "query_mapping": QueryMapping(keyword_param="q"),
        "pagination": PaginationConfig(style=PaginationStyle.NONE, results_path="results"),
        "field_mapping": FieldMappingConfig(title=FieldMapping(path="title")),
        "rate_limit_rps": 2.0,
    }
    defaults.update(overrides)
    return CustomConnectorConfig(**defaults)


def test_two_factory_calls_for_the_same_slug_share_one_rate_limiter():
    factory = _make_factory("my_source", _minimal_config().model_dump())

    first = factory()
    second = factory()

    assert first._rate_limiter is second._rate_limiter


def test_two_different_slugs_get_independent_rate_limiters():
    factory_a = _make_factory("source_a", _minimal_config().model_dump())
    factory_b = _make_factory("source_b", _minimal_config().model_dump())

    connector_a = factory_a()
    connector_b = factory_b()

    assert connector_a._rate_limiter is not connector_b._rate_limiter


def test_a_changed_rate_limit_gets_a_new_limiter_instead_of_reusing_a_stale_one():
    factory_slow = _make_factory("editable_source", _minimal_config(rate_limit_rps=1.0).model_dump())
    factory_fast = _make_factory("editable_source", _minimal_config(rate_limit_rps=5.0).model_dump())

    slow_connector = factory_slow()
    fast_connector = factory_fast()

    assert slow_connector._rate_limiter is not fast_connector._rate_limiter
