from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
load_dotenv(ROOT / ".env")

def _path_env(name: str, default: Path) -> Path:
    """Tom værdi i .env skal give standarden, ikke Path('') som peger på projektmappen."""
    value = (os.getenv(name) or "").strip().strip('"')
    return Path(value) if value else default


DATA_DIR = _path_env("DATA_DIR", ROOT / "data")
AUDIO_DIR = DATA_DIR / "audio"
# Peg den på ~/.cache/huggingface/hub for at genbruge modeller, du allerede har hentet.
MODEL_DIR = _path_env("MODEL_DIR", DATA_DIR / "models")
DB_PATH = _path_env("DB_PATH", DATA_DIR / "intake.sqlite3")
STATIC_DIR = ROOT / "static"
ICON_DIR = STATIC_DIR / "icons"

PORT = int(os.getenv("APP_PORT", "8000"))
APP_URL = os.getenv("APP_URL", f"http://127.0.0.1:{PORT}/")
DEV_RELOAD = os.getenv("DEV_RELOAD", "0").lower() not in {"0", "false", "no"}

MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", "600"))
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(64 * 1024 * 1024)))
# 0 betyder ingen varighedsgrænse. En lang indtaling til dig selv er et gyldigt ønske.
MAX_DURATION_SEC = float(os.getenv("MAX_DURATION_SEC", "0"))

# Mappen telefonen synker til. Peg den på OneDrive-mappen.
INBOX_DIR = _path_env("INBOX_DIR", DATA_DIR / "indbakke")
INBOX_ARCHIVE_NAME = "behandlet"
# Behandlede filer flyttes ud af den synkroniserede mappe, så Dropbox ikke vokser i det uendelige.
INBOX_ARCHIVE_DIR = _path_env("INBOX_ARCHIVE_DIR", DATA_DIR / INBOX_ARCHIVE_NAME)
INBOX_POLL_SECONDS = float(os.getenv("INBOX_POLL_SECONDS", "5"))
INBOX_ARCHIVE = os.getenv("INBOX_ARCHIVE", "1").lower() not in {"0", "false", "no"}
INBOX_MAX_BYTES = int(os.getenv("INBOX_MAX_BYTES", str(512 * 1024 * 1024)))
WATCH_ENABLED = os.getenv("WATCH_ENABLED", "1").lower() not in {"0", "false", "no"}

NOTIFY = os.getenv("NOTIFY", "1").lower() not in {"0", "false", "no"}
# Navnet Windows kender programmet under. Uden et registreret navn accepterer Windows
# notifikationen og smider den væk uden at sige noget.
APP_NAME = os.getenv("APP_NAME", "Indtagelse").strip()
TOAST_AUMID = os.getenv("TOAST_AUMID", "Indtagelse.Idebakke").strip()
# Åbn indbakken af sig selv, men kun hvis ingen browserfane allerede kigger på den.
AUTO_OPEN = os.getenv("AUTO_OPEN", "1").lower() not in {"0", "false", "no"}
AUTO_OPEN_IDLE_SEC = float(os.getenv("AUTO_OPEN_IDLE_SEC", "90"))

APP_PASSWORD = (os.getenv("APP_PASSWORD") or "skift-mig").strip()
SECRET_KEY = (os.getenv("SECRET_KEY") or "dev-secret-change-me").strip()

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "da")
WHISPER_WARMUP = os.getenv("WHISPER_WARMUP", "1").lower() not in {"0", "false", "no"}
# Modellen frigives efter tomgang, så programmet ikke sidder på GPU-hukommelse hele dagen.
# Den koster få sekunder at hente frem igen, og her betyder ventetid ingenting. 0 slår det fra.
WHISPER_IDLE_UNLOAD_SEC = float(os.getenv("WHISPER_IDLE_UNLOAD_SEC", "300"))

MAIL_TO = os.getenv("MAIL_TO", "wrike@wrike.com").strip()
MAIL_CC = os.getenv("MAIL_CC", "ep@a4.dk").strip()
MAIL_MARKER = os.getenv("MAIL_MARKER", "*PODIOWRIKETASKDELETE*").strip()

# En notifikation er et øjeblik, man kan overse. Den daglige oversigt gentages,
# så længe der ligger noget usorteret — også hvis du har været bortrejst i tre uger.
REMIND_ENABLED = os.getenv("REMIND_ENABLED", "1").lower() not in {"0", "false", "no"}
REMIND_TO = (os.getenv("REMIND_TO") or MAIL_CC).strip()
REMIND_AT = os.getenv("REMIND_AT", "08:30").strip()
# Var maskinen slukket klokken 08:30, skal oversigten sendes når den tændes, ikke springes over.
REMIND_CHECK_SECONDS = float(os.getenv("REMIND_CHECK_SECONDS", "300"))

LLM_ENABLED = os.getenv("LLM_ENABLED", "1").lower() not in {"0", "false", "no"}
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:14b").strip()
# En lang indtaling giver et langt referat, og det tager tid på en delt GPU.
LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "240"))
# Sprogmodellen er den store hukommelsessluger. Den slipper kortet igen kort efter brug,
# så den ikke står i vejen, når du selv skal bruge GPU'en. "0" frigiver med det samme.
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "5m").strip()


def ensure_dirs() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)


def mail_settings() -> dict[str, str]:
    return {"to": MAIL_TO, "cc": MAIL_CC, "marker": MAIL_MARKER}
