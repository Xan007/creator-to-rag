import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read CRAG_<name>, falling back to legacy INSTARAG_<name>."""
    load_runtime_env()
    key = f"CRAG_{name}"
    if key in os.environ:
        return _strip_env_quotes(os.environ[key])
    legacy = f"INSTARAG_{name}"
    if legacy in os.environ:
        return _strip_env_quotes(os.environ[legacy])
    return default


def _strip_env_quotes(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text



def load_runtime_env() -> None:
    """Load .env files for source and frozen executable modes.

    Precedence (highest first):
    1) Existing process environment variables.
    2) .env next to the executable (when running frozen).
    3) .env in the current working directory.
    4) ~/.crag/.env (per-user persistent config).
    5) ~/.instarag/.env (legacy path).
    """
    if getattr(load_runtime_env, "_loaded", False):
        return

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

    load_runtime_env._loaded = True
