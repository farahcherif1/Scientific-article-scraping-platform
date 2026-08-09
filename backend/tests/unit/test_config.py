from app.config import Settings


def test_cors_origins_defaults_to_the_vite_dev_server():
    settings = Settings(_env_file=None)
    assert settings.cors_origins_list == ["http://localhost:5173"]


def test_cors_origins_parses_a_comma_separated_list():
    # Security review finding: CORS_ORIGINS was previously hardcoded in
    # app/main.py, so a prod deployment with a different frontend origin
    # needed a code change rather than an env var.
    settings = Settings(_env_file=None, cors_origins="https://app.example.org, https://staging.example.org")
    assert settings.cors_origins_list == [
        "https://app.example.org",
        "https://staging.example.org",
    ]


def test_cors_origins_ignores_blank_entries():
    settings = Settings(_env_file=None, cors_origins="https://app.example.org,,")
    assert settings.cors_origins_list == ["https://app.example.org"]
