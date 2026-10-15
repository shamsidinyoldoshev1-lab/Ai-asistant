"""
document_analyzer.py - Hujjatlar, cheklar va PDF fayllarni tahlil qilish moduli.
Google Gemini multimodal (Vision + Doc) imkoniyatlaridan foydalanadi:
1. To'lov cheklari (Click, Payme, Uzum, kvitansiyalar) tahlili
2. PDF hujjatlar va shartnomalar xulosasi
3. Skrinshot va fotosuratlardagi ma'lumotlarni o'qish
"""
import os
import html
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any
from config import Config, logger

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


async def analyze_document_or_image(
    file_path: str,
    user_instruction: Optional[str] = None,
) -> str:
    """
    Faylni (rasm, chek, PDF, hujjat) Gemini orqali chuqur tahlil qilish.
    """
    path = Path(file_path)
    if not path.exists():
        return "❌ <b>Xatolik:</b> Tahlil qilinadigan fayl diskda topilmadi."

    if not Config.GEMINI_API_KEY or genai is None:
        return "❌ <b>Xatolik:</b> Gemini API kaliti ulanmagan yoki kutubxona mavjud emas."

    # Fayl kengaytmasi bo'yicha MIME turini aniqlash
    ext = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
    }
    mime_type = mime_map.get(ext)
    if not mime_type:
        mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "application/octet-stream"

    try:
        with open(path, "rb") as f:
            file_bytes = f.read()

        client = genai.Client(api_key=Config.GEMINI_API_KEY)
        part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

        prompt = user_instruction or """Ushbu rasm yoki hujjatni o'zbek tilida professional tarzda tahlil qil.

QUYIDAGI ANIQ FORMATDA JAVOB QAYTAR (Telegram HTML formatida, <b>, <i>, <code> teglaridan foydalanib):

1. Agar bu TO'LOV CHEKI (kvitansiya, Click, Payme, Uzum va h.k.) bo'lsa:
🧾 <b>TO'LOV CHEKI TAHLILI</b>
━━━━━━━━━━━━━━━━━━━━
💰 <b>Summa:</b> [Summa va valyuta, masalan: 150 000 so'm]
🕒 <b>Sana va vaqt:</b> [Chekdagi sana va vaqt]
👤 <b>Yuboruvchi:</b> [Ismi yoki karta raqami]
📥 <b>Qabul qiluvchi:</b> [Kompaniya yoki qabul qiluvchi shaxs]
💳 <b>To'lov tizimi:</b> [Click / Payme / Uzum / Bank]
📊 <b>Holati:</b> [✅ Muvaffaqiyatli o'tgan / ⏳ Kutilmoqda / ❌ Xatolik]
🔢 <b>Tranzaksiya / Chek ID:</b> <code>[Raqami]</code>
━━━━━━━━━━━━━━━━━━━━
💡 <i>Xulosa: [To'lov haqiqiy va to'liq o'tganmi, 1 gap]</i>

2. Agar bu PDF HUJJAT yoki SHARTNOMA bo'lsa:
📑 <b>HUJJAT / SHARTNOMA TAHLILI</b>
━━━━━━━━━━━━━━━━━━━━
📌 <b>Hujjat turi va mavzusi:</b> [Nomlanishi]
👥 <b>Tomonlar:</b> [Tomonlar nomlari]
📅 <b>Muhim sanalar va muddatlar:</b> [Sanalar]
📝 <b>Asosiy bandlar va xulosa:</b>
• [Muhim band 1]
• [Muhim band 2]
• [Muhim band 3]
⚠️ <b>E'tibor qaratish kerak bo'lgan joylar:</b> [Xavf yoki majburiyatlar]

3. Agar boshqa RASM yoki SKRINSHOT bo'lsa:
🖼 <b>RASM / SKRINSHOT TAHLILI</b>
━━━━━━━━━━━━━━━━━━━━
📝 <b>Undagi asosiy ma'lumot:</b> [Nimalar aks etganligi va matnlar mazmuni]
💡 <b>Xulosa:</b> [Amaliy ahamiyati]

Faqat tayyor tahlil matnini qaytar."""

        logger.info(f"Gemini Vision tahlili boshlandi: {path.name} ({mime_type})...")
        models_to_try = [Config.GEMINI_MODEL, "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"]
        response = None
        for m_name in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=m_name,
                    contents=[part, prompt],
                )
                if response and response.text:
                    break
            except Exception as me:
                logger.warning(f"Hujjat tahlilida {m_name} xatoligi ({me}), keyingisi sinab ko'riladi...")

        if response and response.text:
            return response.text.strip()
        return "⚠️ Hujjatni tahlil qilib bo'lmadi (bo'sh javob)."

    except Exception as e:
        logger.error(f"Hujjat tahlilida xatolik: {e}", exc_info=True)
        return f"❌ <b>Hujjatni tahlil qilishda xatolik:</b> <code>{html.escape(str(e))}</code>"
