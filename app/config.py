from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data")))
AUDIO_DIR = DATA_DIR / "audio"
MODEL_DIR = DATA_DIR / "models"
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "intake.sqlite3")))
STATIC_DIR = ROOT / "static"
ICON_DIR = STATIC_DIR / "icons"

MAX_RECORD_SECONDS = 60
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_DURATION_SLACK = 75.0

APP_PASSWORD = os.getenv("APP_PASSWORD", "skift-mig")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "da")
WHISPER_WARMUP = os.getenv("WHISPER_WARMUP", "1").lower() not in {"0", "false", "no"}

MAIL_TO = os.getenv("MAIL_TO", "wrike@wrike.com").strip()
MAIL_CC = os.getenv("MAIL_CC", "ep@a4.dk").strip()
MAIL_MARKER = os.getenv("MAIL_MARKER", "*PODIOWRIKETASKDELETE*").strip()

LLM_ENABLED = os.getenv("LLM_ENABLED", "1").lower() not in {"0", "false", "no"}
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:14b").strip()
LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "90"))


def ensure_dirs() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)


def mail_settings() -> dict[str, str]:
    return {"to": MAIL_TO, "cc": MAIL_CC, "marker": MAIL_MARKER}
