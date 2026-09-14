from pathlib import Path

from config.env import getenv, load_runtime_env

load_runtime_env()

CONFIG_DIR = Path(getenv("CONFIG_DIR", str(Path.home() / ".crag")))
DATA_DIR = Path(getenv("DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SAVED_DIR = DATA_DIR / "saved"
