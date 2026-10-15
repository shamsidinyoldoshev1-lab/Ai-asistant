import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# .env faylini yuklash
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Loyiha sozlamalarini boshqarish klassi."""

    BASE_DIR: Path = BASE_DIR

    # Userbot sozlamalari
    API_ID_RAW = os.getenv("TELEGRAM_API_ID", "")
    API_ID: int = int(API_ID_RAW) if API_ID_RAW.isdigit() else 0
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
    SESSION_NAME: str = os.getenv("TELEGRAM_SESSION_NAME", "userbot_session")

    # Boshqaruv boti sozlamalari
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ADMIN_ID_RAW = os.getenv("ADMIN_USER_ID", "")
    ADMIN_USER_ID: int = int(ADMIN_ID_RAW) if ADMIN_ID_RAW.isdigit() else 0

    # AI Provider: 'auto', 'ollama', 'gemini', 'claude'
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "auto")

    # Claude AI sozlamalari
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

    # Standart rejim: 'tasdiq' yoki 'avto'
    DEFAULT_MODE: str = os.getenv("DEFAULT_MODE", "avto")

    # Google Gemini AI sozlamalari (mutlaqo bepul)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

    # Ollama Lokal AI sozlamalari (100% lokal, API kalitsiz)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    # Whisper API sozlamalari (ovozli xabarlar uchun, OpenAI yoki Groq)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # Javobsiz qolgan xabarlar eslatmasi (kun hisobida)
    UNANSWERED_REMINDER_DAYS: int = int(os.getenv("UNANSWERED_REMINDER_DAYS", "3"))

    # Baza va media saqlash papkalari
    DATABASE_PATH: Path = BASE_DIR / os.getenv("DATABASE_PATH", "messages.db")
    MEDIA_DIR: Path = BASE_DIR / os.getenv("MEDIA_DIR", "saved_media")
    LOG_FILE: Path = BASE_DIR / os.getenv("LOG_FILE", "logs/agent.log")
    MESSAGE_RETENTION_DAYS: int = int(os.getenv("MESSAGE_RETENTION_DAYS", "30"))

    @classmethod
    def validate_for_userbot(cls) -> None:
        """Userbot ishlashi uchun zarur o'zgaruvchilarni tekshirish."""
        errors = []
        if not cls.API_ID:
            errors.append("TELEGRAM_API_ID ko'rsatilmagan yoki noto'g'ri (.env da to'ldiring)")
        if not cls.API_HASH:
            errors.append("TELEGRAM_API_HASH ko'rsatilmagan (.env da to'ldiring)")
        if errors:
            raise ValueError("\n".join(errors))


# Papkalarni yaratish
Config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
Config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Logging tizimini sozlash
log_format = "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("TelegramAgent")
