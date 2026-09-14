import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read CRAG_<name>, falling back to legacy INSTARAG_<name>."""
    key = f"CRAG_{name}"
    if key in os.environ:
        return os.environ[key]
    legacy = f"INSTARAG_{name}"
    if legacy in os.environ:
        return os.environ[legacy]
    return default


def load_runtime_env() -> None:
    """Load .env files for source and frozen executable modes.

    Precedence (highest first):
    1) Existing process environment variables.
    2) .env next to the executable (when running frozen).
    3) .env in the current working directory.
    4) ~/.crag/.env (per-user persistent config).
    5) ~/.instarag/.env (legacy path).
    """
    candidates = []

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / ".env")

    home = Path.home()
    candidates.extend(
        [
            Path.cwd() / ".env",
            home / ".crag" / ".env",
            home / ".instarag" / ".env",
        ]
    )

    for env_path in candidates:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
