from dataclasses import dataclass
import os
from pathlib import Path

# Local secrets (e.g. EARTHDATA_TOKEN) may live in the git-ignored backend/.env. They are read into the
# process environment only; they are never returned by the API or written to logs.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:  # python-dotenv ships with uvicorn[standard]; absence just means no .env support
    pass


@dataclass(frozen=True)
class Settings:
    application_id: str = os.getenv("APPLICATION_ID", "alterecho-terrain-explorer")
    product_name: str = os.getenv("PRODUCT_NAME", "AlterEcho AI")
    subtitle: str = os.getenv("PRODUCT_SUBTITLE", "Interplanetary Terrain Explorer")
    team_name: str = os.getenv("TEAM_NAME", "Team AlterEcho")
    description: str = os.getenv("PRODUCT_DESCRIPTION", "Transparent Earth terrain analog comparisons using processed elevation data.")
    app_version: str = os.getenv("APP_VERSION", "0.5.0")
    build_identifier: str = os.getenv("BUILD_IDENTIFIER", "phase5-workspace")
    app_env: str = os.getenv("APP_ENV", "development")
    methodology_version: str = os.getenv("METHODOLOGY_VERSION", "terrain-v3.0")
    methodology_display_name: str = os.getenv("METHODOLOGY_DISPLAY_NAME", "Terrain Analogy Index · terrain-v3.0")
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3100,http://127.0.0.1:3100"
        ).split(",")
        if origin.strip()
    )


settings = Settings()


def api_title() -> str:
    return f"{settings.product_name} API"

