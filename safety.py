import re
import time
from typing import Dict, Any, List, Tuple
from collections import defaultdict
from config import logger

# -------------------------------------------------------------------------
# XAVFLI MAVZULAR LUG'ATI VA REGEXLAR
# -------------------------------------------------------------------------

# Karta raqamlari (16 xonali, masalan 8600 xxxx xxxx xxxx yoki 9860..., ajratgich bilan yoki ajratgichsiz)
CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -.]?){3}\d{4}\b")

# Xavfsizlik kodlari va parollar (kod, parol, password, sms-kod, tasdiqlash kodi, pin-kod, cvv, otp)
CODE_PATTERN = re.compile(
    r"\b(kod[a-z]*|parol[a-z]*|password|sms[- ]?kod[a-z]*|tasdiqlash kodi|pin[- ]?kod[a-z]*|cvv|cvc|otp)\b",
    re.IGNORECASE,
)

SENSITIVE_CATEGORIES: Dict[str, List[str]] = {
    "moliya": [
        "pul", "so'm", "som", "dollar", "usd", "rubl", "to'lov", "tolov",
        "qarz", "narx", "narxi", "qancha bo'ladi", "qancha boladi",
        "hisob raqam", "summa", "o'tkazma", "otkazma", "transfer", "perevod",
        "payme", "click", "uzum bank", "kredit", "omonat", "avans", "oplata",
    ],
    "xavfsizlik": [
        "parol", "password", "kod", "sms", "tasdiq", "login", "pin",
        "pin kod", "cvc", "cvv", "otp", "secret", "maxfiy",
    ],
    "shartnoma": [
        "shartnoma", "dogovor", "kontrakt", "imzo", "imzolash", "kafolat",
        "kafillik", "va'da beraman", "vada beraman", "kelishuv", "akt", "notarius",
    ],
    "tibbiyot": [
        "dori", "retsept", "tashxis", "diagnoz", "kasallik", "davolash",
        "shifokor", "vrach", "doktor", "tabletka", "ukol", "operatsiya",
        "analiz", "analiz natijasi", "lecheniye", "bolnitsa",
    ],
    "huquqiy": [
        "sud", "sudya", "advokat", "prokuror", "militsiya", "ichki ishlar",
        "ariza", "qonun", "modda", "jinoiy", "tergov", "jarima", "shtraf",
    ],
}

# Oddiy savollar kalit so'zlari ("aralash" rejimida avtomatik javob berish uchun)
SIMPLE_GREETINGS = [
    "salom", "assalomu alaykum", "assalom", "vaalaykum", "privet", "zdravstvuyte",
    "hello", "hi", "hey", "qalaysan", "qalaysiz", "yaxshimisiz", "tinchmisiz",
    "qalesiz", "ishlar qalay", "nima gap", "rahmat", "raxmat", "tashakkur",
]

SIMPLE_INQUIRIES = [
    "ish vaqti", "qachongacha ishleysiz", "grafik", "ish kunlari", "qayerda joylashgan",
    "manzil", "adres", "lokatsiya", "qayerdasiz", "qaysi filial", "location",
]

COMPLEX_OR_COMMITMENT = [
    "uchrashuv", "uchrashaylik", "ko'rishamiz", "korishamiz", "soat nechada",
    "qachon ko'rishamiz", "vstrecha", "gaplashib olaylik", "qachon kelasiz",
    "va'da", "vada", "kelishamiz", "kelishaylik",
]


def check_safety(text: str) -> Dict[str, Any]:
    """
    Xabarda xavfli yoki nozik mavzular (pul, karta, parol, tibbiyot, shartnoma, huquq)
    mavjudligini tekshirish.

    Agar aniqlansa, agent hech qachon o'zi javob bermasligi kerak!
    """
    if not text:
        return {"is_sensitive": False, "category": None, "reason": None}

    lower_text = text.lower()

    # 1. Karta raqami tekshiruvi (eng xavfli)
    if CARD_PATTERN.search(text):
        return {
            "is_sensitive": True,
            "category": "karta_raqami",
            "reason": "Xabarda bank karta raqami aniqlandi.",
        }

    # 2. Xavfsizlik kodlari va parollar
    if CODE_PATTERN.search(text):
        for word in ["kod", "parol", "sms", "tasdiq", "pin", "cvv", "otp"]:
            if word in lower_text:
                return {
                    "is_sensitive": True,
                    "category": "xavfsizlik_kodi",
                    "reason": f"Xabarda maxfiy kod yoki parol bilan bog'liq so'z ({word}) aniqlandi.",
                }

    # 3. Nozik kategoriyalar bo'yicha qidiruv
    for category, keywords in SENSITIVE_CATEGORIES.items():
        for kw in keywords:
            # Qisqa so'zlar uchun (3 belgigacha) qat'iy chegarali qidiruv
            if len(kw) <= 3:
                pattern = rf"\b{re.escape(kw)}\b"
            else:
                # O'zbek va rus tillaridagi qo'shimchalarni hisobga oluvchi qidiruv
                pattern = rf"\b{re.escape(kw)}[a-z'’\-]*"

            if re.search(pattern, lower_text):
                return {
                    "is_sensitive": True,
                    "category": category,
                    "reason": f"Xabarda '{category}' toifasidagi nozik so'z ('{kw}') aniqlandi.",
                }

    return {"is_sensitive": False, "category": None, "reason": None}


def is_simple_question(text: str) -> bool:
    """
    'aralash' rejimi uchun: xabar oddiy (salomlashish, ish vaqti, manzil) savolmi
    yoki uchrashuv/va'da/shaxsiy masala talab qiladimi?
    """
    if not text:
        return False

    lower_text = text.lower().strip()

    # Agar xavfli mavzu bo'lsa hech qachon oddiy hisoblanmaydi
    safety = check_safety(text)
    if safety["is_sensitive"]:
        return False

    # Agar uchrashuv, kelishuv yoki va'da so'ralgan bo'lsa - bu oddiy emas (tasdiq so'ralishi shart)
    for trigger in COMPLEX_OR_COMMITMENT:
        if trigger in lower_text:
            return False

    # Salomlashish yoki oddiy hol-ahvol
    for greeting in SIMPLE_GREETINGS:
        if greeting in lower_text:
            return True

    # Ish vaqti, manzil yoki joylashuv haqidagi oddiy savollar
    for inquiry in SIMPLE_INQUIRIES:
        if inquiry in lower_text:
            return True

    return False


# -------------------------------------------------------------------------
# RATE LIMITER (Spam va flooddan himoya qilish)
# -------------------------------------------------------------------------

class RateLimiter:
    """
    Telegram akkauntni spam blokirovkasidan asrash uchun daqiqasiga
    xabarlar sonini nazorat qiluvchi cheklovchi.
    """

    def __init__(self, max_per_chat_per_minute: int = 5, max_global_per_minute: int = 15):
        self.max_per_chat = max_per_chat_per_minute
        self.max_global = max_global_per_minute
        self.chat_timestamps = defaultdict(list)
        self.global_timestamps = []

    def _clean_old(self, timestamps: List[float], window_seconds: float = 60.0) -> List[float]:
        now = time.time()
        return [ts for ts in timestamps if now - ts < window_seconds]

    def is_allowed(self, chat_id: int) -> Tuple[bool, str]:
        """Xabar yuborishga ruxsat bormi yoki limit oshganmi?"""
        now = time.time()
        self.global_timestamps = self._clean_old(self.global_timestamps)
        self.chat_timestamps[chat_id] = self._clean_old(self.chat_timestamps[chat_id])

        if len(self.global_timestamps) >= self.max_global:
            logger.warning(f"Global xabar yuborish limiti oshdi ({self.max_global} ta/daqiqasiga)!")
            return False, f"Global daqiqalik xabar yuborish limiti oshdi ({self.max_global} ta/daqiqasiga)."

        if len(self.chat_timestamps[chat_id]) >= self.max_per_chat:
            logger.warning(f"Chat {chat_id} bo'yicha xabar limiti oshdi ({self.max_per_chat} ta/daqiqasiga)!")
            return False, f"Ushbu chat uchun daqiqalik limit oshdi ({self.max_per_chat} ta/daqiqasiga)."

        return True, "OK"

    def record_sent(self, chat_id: int):
        """Xabar yuborilgan vaqtni qayd etish."""
        now = time.time()
        self.global_timestamps.append(now)
        self.chat_timestamps[chat_id].append(now)

    def get_stats(self) -> Dict[str, Any]:
        """Joriy limit statistikasi."""
        self.global_timestamps = self._clean_old(self.global_timestamps)
        active_chats = sum(1 for cid, tss in self.chat_timestamps.items() if self._clean_old(tss))
        return {
            "global_sent_last_min": len(self.global_timestamps),
            "max_global": self.max_global,
            "max_per_chat": self.max_per_chat,
            "active_chats_last_min": active_chats,
        }


# Global instansiya
rate_limiter = RateLimiter(max_per_chat_per_minute=5, max_global_per_minute=15)
