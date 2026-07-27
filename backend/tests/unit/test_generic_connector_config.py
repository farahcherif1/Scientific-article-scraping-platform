import pytest
from pydantic import ValidationError

from app.connectors.generic_config import (
    AuthConfig,
    AuthType,
    CustomConnectorConfig,
    FieldMapping,
    FieldMappingConfig,
    PaginationConfig,
    PaginationStyle,
    QueryMapping,
    resolve_path,
)


def _minimal_config(**overrides) -> CustomConnectorConfig:
    defaults = {
        "base_url": "https://example.org/search",
        "query_mapping": QueryMapping(keyword_param="q"),
        "pagination": PaginationConfig(style=PaginationStyle.NONE, results_path="results"),
        "field_mapping": FieldMappingConfig(title=FieldMapping(path="title")),
    }
    defaults.update(overrides)
    return CustomConnectorConfig(**defaults)


class TestResolvePath:
    def test_flat_key(self):
        assert resolve_path({"title": "A Great Paper"}, "title") == "A Great Paper"

    def test_nested_dot_path(self):
        assert resolve_path({"bibjson": {"title": "X"}}, "bibjson.title") == "X"

    def test_array_of_objects_maps_a_field(self):
        payload = {"authors": [{"name": "A"}, {"name": "B"}]}
        assert resolve_path(payload, "authors[].name") == ["A", "B"]

    def test_already_flat_array_returned_as_is(self):
        # HAL-style: authFullName_s is stored as a flat array of strings.
        payload = {"authFullName_s": ["Ada Lovelace", "Alan Turing"]}
        assert resolve_path(payload, "authFullName_s") == ["Ada Lovelace", "Alan Turing"]

    def test_deeply_nested_array(self):
        # IEEE Xplore-style: authors.authors[].full_name
        payload = {"authors": {"authors": [{"full_name": "A"}, {"full_name": "B"}]}}
        assert resolve_path(payload, "authors.authors[].full_name") == ["A", "B"]

    def test_array_index(self):
        payload = {"concepts": [{"display_name": "ML"}, {"display_name": "AI"}]}
        assert resolve_path(payload, "concepts[0].display_name") == "ML"

    def test_missing_key_returns_none(self):
        assert resolve_path({"title": "X"}, "abstract") is None

    def test_missing_nested_key_returns_none(self):
        assert resolve_path({"a": {}}, "a.b.c") is None

    def test_missing_array_key_returns_none(self):
        assert resolve_path({}, "authors[].name") is None

    def test_non_list_value_at_array_segment_is_skipped(self):
        assert resolve_path({"authors": "not-a-list"}, "authors[].name") is None

    def test_empty_path_returns_none(self):
        assert resolve_path({"title": "X"}, None) is None
        assert resolve_path({"title": "X"}, "") is None

    def test_root_level_array_wildcard(self):
        payload = [{"title": "A"}, {"title": "B"}]
        assert resolve_path(payload, "[].title") == ["A", "B"]


class TestCustomConnectorConfig:
    def test_valid_minimal_config_parses(self):
        config = _minimal_config()
        assert config.base_url == "https://example.org/search"
        assert config.http_method == "GET"
        assert config.auth.type == AuthType.NONE

    def test_base_url_must_be_http_or_https(self):
        with pytest.raises(ValidationError):
            _minimal_config(base_url="ftp://example.org")

    def test_base_url_without_scheme_rejected(self):
        with pytest.raises(ValidationError):
            _minimal_config(base_url="example.org/search")

    def test_invalid_http_method_rejected(self):
        with pytest.raises(ValidationError):
            _minimal_config(http_method="DELETE")

    def test_rate_limit_must_be_positive(self):
        with pytest.raises(ValidationError):
            _minimal_config(rate_limit_rps=0)

    def test_api_key_header_auth_round_trips(self):
        config = _minimal_config(
            auth=AuthConfig(type=AuthType.API_KEY_HEADER, key_name="Authorization", key_value="Bearer abc")
        )
        assert config.auth.type == AuthType.API_KEY_HEADER
        assert config.auth.key_name == "Authorization"

    def test_pagination_requires_results_path(self):
        with pytest.raises(ValidationError):
            PaginationConfig(style=PaginationStyle.PAGE, results_path="")

    def test_title_field_mapping_is_required(self):
        with pytest.raises(ValidationError):
            CustomConnectorConfig(
                base_url="https://example.org",
                query_mapping=QueryMapping(keyword_param="q"),
                pagination=PaginationConfig(results_path="results"),
                field_mapping=FieldMappingConfig(),
            )

    def test_serialization_round_trip(self):
        config = _minimal_config()
        dumped = config.model_dump(mode="json")
        restored = CustomConnectorConfig.model_validate(dumped)
        assert restored == config
