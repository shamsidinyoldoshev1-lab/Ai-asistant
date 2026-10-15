"""
calendar_service.py - Google Calendar va Taqvim integratsiyasi.
1. Matndan uchrashuv va sanalarni tahlil qilish (Gemini orqali).
2. Google Calendar havolasini (Direct URL) generatsiya qilish.
3. Universal .ics kalendar faylini yaratish.
"""
import os
import json
import html
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from config import Config, logger

try:
    from google import genai
except ImportError:
    genai = None


def generate_google_calendar_url(
    title: str,
    start_time: datetime,
    end_time: Optional[datetime] = None,
    details: str = "",
    location: str = "",
) -> str:
    """
    Google Calendar-ga bir bosishda tadbir qo'shish uchun havola yaratish.
    Havola ochilganda Google Calendar barcha ma'lumotlar bilan ochiladi.
    """
    if not end_time:
        end_time = start_time + timedelta(hours=1)

    start_str = start_time.strftime("%Y%m%dT%H%M%SZ")
    end_str = end_time.strftime("%Y%m%dT%H%M%SZ")

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start_str}/{end_str}",
        "details": details,
        "location": location,
    }
    return f"https://calendar.google.com/calendar/render?{urllib.parse.urlencode(params)}"


def create_ics_file(
    title: str,
    start_time: datetime,
    end_time: Optional[datetime] = None,
    details: str = "",
    location: str = "",
    output_path: Optional[str] = None,
) -> str:
    """
    Universal .ics (iCalendar) fayl yaratish.
    Ushbu fayl Telegram orqali yuborilganda telefon taqvimida ochiladi.
    """
    if not end_time:
        end_time = start_time + timedelta(hours=1)

    start_str = start_time.strftime("%Y%m%dT%H%M%SZ")
    end_str = end_time.strftime("%Y%m%dT%H%M%SZ")
    now_str = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    uid = f"event_{int(datetime.utcnow().timestamp())}@personal_ai_agent"

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Personal Telegram AI Agent//UZ
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{now_str}
DTSTART:{start_str}
DTEND:{end_str}
SUMMARY:{title}
DESCRIPTION:{details}
LOCATION:{location}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""

    if not output_path:
        out_dir = Config.BASE_DIR / "saved_media"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"event_{int(datetime.utcnow().timestamp())}.ics")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    return output_path


async def parse_meeting_event(text: str) -> Optional[Dict[str, Any]]:
    """
    Matn ichidan uchrashuv, reja, dars yoki sana/vaqtni aniqlab,
    Google Calendar havolasi va .ics faylini tayyorlash.
    """
    if not text or not Config.GEMINI_API_KEY or genai is None:
        return None

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S (hafta kuni: %A)")

    prompt = f"""Bugungi sana va vaqt: {now_str}.
Foydalanuvchi quyidagi matnni yozdi:
«{text}»

Sening vazifang:
1. Ushbu matn uchrashuv, tadbir, dars, reja, shifokor qabuli yoki eslatma haqidami? (is_event: true/false)
2. Agar ha bo'lsa:
   - title: Tadbir sarlavhasi (masalan: "Karim bilan uchrashuv", "Ingliz tili darsi")
   - start_iso: Tadbir boshlanish sanasi va vaqti ISO formatida: "YYYY-MM-DDTHH:MM:SS" (bugungi sana asosida to'g'ri hisobla, masalan 'ertaga soat 15:00' bo'lsa ertangi kun sanasini qo'y).
   - duration_minutes: Taxminiy davomiyligi daqiqalarda (standart: 60)
   - details: Qisqa izoh yoki tavsif
   - location: Joylashuv (agar matnda aytilgan bo'lsa, bo'lmasa "")

Faqat to'g'ri JSON qaytar (markdown blocsiz yoki ```json ichida):
{{
  "is_event": true,
  "title": "Karim bilan uchrashuv",
  "start_iso": "{now.strftime('%Y-%m-%d')}T15:00:00",
  "duration_minutes": 60,
  "details": "Matndagi reja",
  "location": "Toshkent"
}}
Agar uchrashuv yoki sana aytilmagan bo'lsa:
{{
  "is_event": false
}}"""

    try:
        client = genai.Client(api_key=Config.GEMINI_API_KEY)
        response = None
        models_to_try = [Config.GEMINI_MODEL, "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"]
        for m_name in models_to_try:
            try:
                response = await client.aio.models.generate_content(
                    model=m_name,
                    contents=prompt,
                )
                if response and response.text:
                    break
            except Exception as me:
                logger.warning(f"Taqvim tahlilida {m_name} xatoligi ({me}), keyingisi sinab ko'riladi...")

        if not response or not response.text:
            return None

        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)
        if not data.get("is_event") or not data.get("start_iso"):
            return None

        # Sanani o'qish
        start_dt = datetime.fromisoformat(data["start_iso"])
        duration = int(data.get("duration_minutes", 60))
        end_dt = start_dt + timedelta(minutes=duration)
        title = data.get("title", "Uchrashuv")
        details = data.get("details", text)
        location = data.get("location", "")

        cal_url = generate_google_calendar_url(
            title=title,
            start_time=start_dt,
            end_time=end_dt,
            details=details,
            location=location,
        )

        ics_file = create_ics_file(
            title=title,
            start_time=start_dt,
            end_time=end_dt,
            details=details,
            location=location,
        )

        return {
            "title": title,
            "start_time": start_dt.strftime("%Y-%m-%d %H:%M"),
            "end_time": end_dt.strftime("%Y-%m-%d %H:%M"),
            "details": details,
            "location": location,
            "google_calendar_url": cal_url,
            "ics_file_path": ics_file,
        }
    except Exception as e:
        logger.warning(f"Taqvim tahlilida xatolik: {e}")
        return None
