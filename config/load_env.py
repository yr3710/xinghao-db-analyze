import os
from pathlib import Path

from dotenv import load_dotenv


def load_env() -> None:
    project_root = Path(__file__).resolve().parent.parent
    app_env = os.getenv("APP_ENV", "dev")
    env_file = project_root / f".env.{app_env}"

    if not env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    load_dotenv(env_file, override=True)