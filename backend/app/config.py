from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_url: str = "sqlite:///./team08.db"
    polite_pool_email: str = "your-email@example.com"

    http_timeout_connect_s: int = 10
    http_timeout_read_s: int = 30
    http_timeout_source_total_s: int = 60
    http_timeout_collection_soft_limit_s: int = 600

    max_articles_per_keyword: int = 100

    rate_limit_arxiv_interval_s: int = 3
    rate_limit_openalex_rps: int = 10
    rate_limit_crossref_rps: int = 50
    rate_limit_pubmed_rps: int = 3
    rate_limit_semantic_scholar_rps: int = 1

    # Optional - neither source requires a key. When set, PubMed's E-utilities
    # allow 10 req/s instead of 3, and Semantic Scholar's Graph API gets a
    # faster tier instead of sharing the public unauthenticated pool.
    pubmed_api_key: str | None = None
    semantic_scholar_api_key: str | None = None

    cache_ttl_hours: int = 24
    log_level: str = "INFO"


settings = Settings()