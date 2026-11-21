import os


API_BASE_URL = "http://finefolionet:8080"
API_TOKEN_ENV_VAR = "FINEFOLIO_API_TOKEN"


def get_authorization_headers() -> dict[str, str]:
    token = os.environ.get(API_TOKEN_ENV_VAR, "").strip()
    if not token:
        raise RuntimeError(f"{API_TOKEN_ENV_VAR} environment variable must be set")

    return {"Authorization": f"Bearer {token}"}
