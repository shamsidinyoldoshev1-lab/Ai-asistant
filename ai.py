import os
import re
import json
import html
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path
from collections import defaultdict
from anthropic import AsyncAnthropic, APIError

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from config import Config, logger
import db

_claude_client: Optional[AsyncAnthropic] = None
SAMPLES_FILE = Config.BASE_DIR / "style_samples.json"


def get_claude_client() -> Optional[AsyncAnthropic]:
    """Claude API mijozi (AsyncAnthropic) instansiyasini olish."""
    global _claude_client
    if _claude_client is None:
        if not Config.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY sozlanmagan (.env faylida ko'rsating).")
            return None
        _claude_client = AsyncAnthropic(api_key=Config.ANTHROPIC_API_KEY)
    return _claude_client


def get_active_provider() -> str:
    """Qaysi AI provayderi faolligini aniqlash: 'ollama', 'gemini' yoki 'claude'."""
    if Config.AI_PROVIDER != "auto":
        return Config.AI_PROVIDER
    if Config.GEMINI_API_KEY:
        return "gemini"
    if Config.ANTHROPIC_API_KEY:
        return "claude"
    return "ollama"


async def call_llm(
    prompt: Optional[str] = None,
    system_prompt: str = "",
    messages: Optional[List[Dict[str, str]]] = None,
    max_tokens: int = 500,
) -> Optional[str]:
    """
    Ko'p provayderli universal LLM chaqiruvchisi:
    - ollama: 100% lokal model (llama3.2, qwen2.5 va b.)
    - gemini: Google Gemini (mutlaqo bepul)
    - claude: Anthropic Claude
    """
    provider = get_active_provider()

    # 1. OLLAMA (Lokal model, 100% oflayn / tekin)
    if provider == "ollama":
        if AsyncOpenAI is None:
            logger.error("openai kutubxonasi o'rnatilmagan.")
            return None
        try:
            client = AsyncOpenAI(base_url=f"{Config.OLLAMA_BASE_URL}/v1", api_key="ollama")
            chat_msgs = []
            if system_prompt:
                chat_msgs.append({"role": "system", "content": system_prompt})
            if messages:
                chat_msgs.extend(messages)
            elif prompt:
                chat_msgs.append({"role": "user", "content": prompt})

            logger.info(f"Ollama Lokal AI ga so'rov yuborilmoqda (Model: {Config.OLLAMA_MODEL})...")
            res = await client.chat.completions.create(
                model=Config.OLLAMA_MODEL,
                messages=chat_msgs,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return res.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Ollama lokal AI xatoligi: {e}")
            return None

    # 2. GOOGLE GEMINI (Mutlaqo bepul bulut)
    elif provider == "gemini":
        if genai is None or not Config.GEMINI_API_KEY:
            logger.error("Gemini kutubxonasi yoki GEMINI_API_KEY sozlanmagan.")
            return None
        try:
            client = genai.Client(api_key=Config.GEMINI_API_KEY)
            full_prompt = prompt or ""
            if messages and not prompt:
                full_prompt = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages])

            models_to_try = [
                Config.GEMINI_MODEL,
                "gemini-3.1-flash-lite",
                "gemini-flash-lite-latest",
                "gemini-3.8-flash",
                "gemini-flash-latest",
            ]
            seen_models = set()
            unique_models = []
            for m in models_to_try:
                if m and m not in seen_models:
                    seen_models.add(m)
                    unique_models.append(m)

            for m_name in unique_models:
                try:
                    logger.info(f"Google Gemini AI ga so'rov yuborilmoqda (Model: {m_name})...")
                    config = {"system_instruction": system_prompt} if system_prompt else None
                    response = await client.aio.models.generate_content(
                        model=m_name,
                        contents=full_prompt,
                        config=config,
                    )
                    if response and response.text:
                        return response.text.strip()
                except Exception as me:
                    logger.warning(f"Model {m_name} xatoligi ({me}), keyingisi sinab ko'riladi...")

            return None
        except Exception as e:
            logger.error(f"Google Gemini AI xatoligi: {e}")
            return None

    # 3. CLAUDE ANTHROPIC
    else:
        client = get_claude_client()
        if not client:
            return None
        try:
            chat_msgs = messages if messages else [{"role": "user", "content": prompt or ""}]
            logger.info(f"Claude API ga so'rov yuborilmoqda (Model: {Config.CLAUDE_MODEL})...")
            response = await client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt if system_prompt else None,
                messages=chat_msgs,
            )
            reply = ""
            for block in response.content:
                if getattr(block, "type", "") == "text":
                    reply += block.text
            return reply.strip()
        except Exception as e:
            logger.error(f"Claude API xatoligi: {e}")
            return None


def load_style_samples(category: Optional[str] = None, max_samples: int = 30) -> str:
    """
    style_samples.json faylidan namunalarni yuklab, system prompt uchun
    few-shot matnini shakllantirish.
    """
    if not SAMPLES_FILE.exists():
        return ""

    try:
        with open(SAMPLES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        filtered = []
        if category:
            matched = [s for s in data if s.get("category") == category]
            others = [s for s in data if s.get("category") != category]
            filtered = (matched + others)[:max_samples]
        else:
            filtered = data[:max_samples]

        if not filtered:
            return ""

        lines = ["\nYOZISH USLUBIDAN NAMUNALAR (SHU USLUBDA JAVOB BERING):"]
        for idx, item in enumerate(filtered, 1):
            dialog = item.get("dialog", [])
            if len(dialog) >= 2:
                user_msg = dialog[0].get("content", "")
                bot_msg = dialog[1].get("content", "")
                lines.append(f"Namuna {idx}:")
                lines.append(f"  Suhbatdosh: «{user_msg}»")
                lines.append(f"  Sizning javobingiz: «{bot_msg}»")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Namunalar faylini o'qishda ogohlantirish: {e}")
        return ""


def build_system_prompt(contact_type: str = "notanish") -> str:
    """
    Kontakt turiga (oila, ish, notanish) qarab moslashtirilgan System Prompt.
    """
    tone_descriptions = {
        "oila": (
            "Suhbatdosh - yaqin do'st yoki oila a'zosi.\n"
            "Ohang: Juda samimiy, erkin, do'stona va iliq.\n"
            "Masalan: 'Salom, yaxshi rahmat, o'zingdachi?', 'Yo'ldaman, tezda boraman', 'Ko'rishamiz'."
        ),
        "ish": (
            "Suhbatdosh - hamkasb, mijoz yoki ish bo'yicha hamkor.\n"
            "Ohang: Rasmiy, professional, ishchan, aniq va lo'nda.\n"
            "Masalan: 'Assalomu alaykum. Xo'p, ma'lumotni o'rganib chiqib javob beraman', 'Bugun soat 15:00 da qulay'."
        ),
        "notanish": (
            "Suhbatdosh - notanish yoki yangi kontakt.\n"
            "Ohang: Qisqa, ehtiyotkor, begonalarga ortiqcha shaxsiy ma'lumot bermaydigan.\n"
            "Masalan: 'Assalomu alaykum. Qanday masala yuzasidan murojaat qilayotgan edingiz?'"
        ),
    }

    current_tone = tone_descriptions.get(contact_type, tone_descriptions["notanish"])
    few_shot_block = load_style_samples(category=contact_type, max_samples=30)

    prompt = f"""Sen Telegram shaxsiy akkaunt egasi nomidan kelgan xabarlarga avtomatik javob beruvchi aqlli shaxsiy AI agentsan.

ENG ASOSIY TALAB VA MAJBURIY QOIDA:
Har bir javobingda sen akkaunt egasining AI agenti (sun'iy intellekt yordamchisi) ekanligingni ochiq va tabiiy tarzda aytib o'tishing SHART!
Hech qachon o'zingni akkaunt egasining o'zi deb ko'rsatma. Suhbatdosh sen aynan AI agent ekanligingni bilishi lozim.

Masalan:
- «Salom! Men profil egasining AI agentiman. U hozir band bo'lgani sababli men javob qaytaryapman. Qanday xabaringiz bo'lsa qoldiring, o'ziga yetkazaman.»
- «Assalomu alaykum! Men profil egasining AI yordamchisiman. Xabaringizni qabul qildim, egasiga yetkazib qo'yaman.»
- «Men AI agentman. [Savolga lo'nda javob]. Akkaunt egasi ham bo'shagach xabaringizni ko'radi.»

BOSHQA QOIDALAR:
1. QISQALIK VA TABIIYLIK:
   - Telegram chat formatiga mos: 1-2 gapdan oshmagan, ortiqcha so'zlarsiz, lo'nda va tabiiy javob ber.
   - Ortiqcha gaplar va cho'zilgan rasmiyatchiliklardan qoch.

2. TILNI MOSLASHTIRISH:
   - Suhbatdosh qaysi tilda yozsa, aynan o'sha tilda javob qaytar (O'zbek, Rus yoki Ingliz).
   - O'zbek tilida yozilayotganda kirill yoki lotin yozuviga hamda so'zlashuv uslubiga moslash.

3. OHANG VA MUNOSABAT:
{current_tone}

4. XAVFSIZLIK:
   - Pul o'tkazish, karta raqami, parol, kod yoki muhim bitimlar bo'yicha mustaqil va'da berma («Buni profil egasining o'zi bilan maslahatlashib hal qilasiz» deb javob ber).

Faqat va faqat Telegramga yuboriladigan tayyor javob matnini qaytar. Hech qanday qo'shimcha izoh, sarlavha yoki tirnoq belgilarisiz!
"""
    return prompt.strip()


async def format_conversation_history(chat_id: int, incoming_text: str, limit: int = 20) -> List[Dict[str, str]]:
    """
    Bazada saqlangan oxirgi N ta xabarni formatlash.
    """
    raw_messages = await db.get_last_messages(chat_id=chat_id, limit=limit)
    formatted: List[Dict[str, str]] = []

    for msg in raw_messages:
        text = (msg.get("text") or "").strip()
        if not text:
            continue

        role = "assistant" if msg.get("is_outgoing") else "user"

        if formatted and formatted[-1]["role"] == role:
            formatted[-1]["content"] += "\n" + text
        else:
            formatted.append({"role": role, "content": text})

    if not formatted or formatted[-1]["content"] != incoming_text:
        if formatted and formatted[-1]["role"] == "user":
            formatted[-1]["content"] += "\n" + incoming_text
        else:
            formatted.append({"role": "user", "content": incoming_text})

    if formatted and formatted[0]["role"] == "assistant":
        formatted.pop(0)

    if not formatted:
        formatted.append({"role": "user", "content": incoming_text})

    return formatted


async def generate_reply(
    chat_id: int,
    incoming_message_text: str,
    contact_name: Optional[str] = None,
    contact_type: Optional[str] = None,
) -> Optional[str]:
    """
    AI (Ollama / Gemini / Claude) orqali kiruvchi xabarga javob qoralamasini tayyorlash.
    """
    if not incoming_message_text or not incoming_message_text.strip():
        return None

    if not contact_type:
        settings = await db.get_contact_settings(chat_id)
        contact_type = settings.get("contact_type", "notanish")

    system_prompt = build_system_prompt(contact_type=contact_type)
    messages = await format_conversation_history(chat_id=chat_id, incoming_text=incoming_message_text)

    raw_reply = await call_llm(system_prompt=system_prompt, messages=messages, max_tokens=250)
    if raw_reply:
        reply_clean = raw_reply.strip().strip('"').strip("'")
        logger.info(f"AI javob tayyorladi: «{reply_clean[:40]}...»")
        return reply_clean

    # Agar AI API kaliti hali kiritilmagan bo'lsa, zaxira javoblar (test uchun):
    text_lower = incoming_message_text.lower().strip()
    if any(s in text_lower for s in ["assalomu", "asalomu", "салом", "salom"]):
        return "Vaalaykum assalom! Yaxshimisiz?"
    elif any(s in text_lower for s in ["bo'shisan", "boshisan", "bo'shmisan", "boshmisan", "бошисан"]):
        return "Salom! Birozdan keyin bo'shayman, xudo xohlasa gaplashamiz."
    elif any(s in text_lower for s in ["qalesan", "qandaysan", "qalaysiz", "ishlar", "калесан"]):
        return "Rahmat, yaxshi. O'zingizda nima gaplar?"

    return None


def import_telegram_export(json_path: str, my_name: str, max_samples: int = 50) -> int:
    """
    Telegram Desktop dan eksport qilingan JSON faylidan namunalarni olish.
    """
    path = Path(json_path)
    if not path.exists():
        logger.error(f"Eksport fayli topilmadi: {json_path}")
        return 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            export_data = json.load(f)

        messages = export_data.get("messages", [])
        new_samples = []

        for i in range(len(messages) - 1):
            prev_msg = messages[i]
            cur_msg = messages[i + 1]

            prev_sender = prev_msg.get("from")
            cur_sender = cur_msg.get("from")

            if prev_sender and cur_sender and cur_sender == my_name and prev_sender != my_name:
                prev_text = prev_msg.get("text")
                cur_text = cur_msg.get("text")

                if isinstance(prev_text, str) and isinstance(cur_text, str):
                    prev_text = prev_text.strip()
                    cur_text = cur_text.strip()
                    if 3 < len(prev_text) < 150 and 2 < len(cur_text) < 150:
                        new_samples.append({
                            "category": "ish" if "rahmat" in cur_text.lower() else "oila",
                            "language": "uz",
                            "dialog": [
                                {"role": "user", "content": prev_text},
                                {"role": "assistant", "content": cur_text},
                            ],
                        })
                        if len(new_samples) >= max_samples:
                            break

        if new_samples:
            existing = []
            if SAMPLES_FILE.exists():
                with open(SAMPLES_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            combined = existing + new_samples
            with open(SAMPLES_FILE, "w", encoding="utf-8") as f:
                json.dump(combined, f, ensure_ascii=False, indent=2)

            logger.info(f"{len(new_samples)} ta yangi namuna style_samples.json ga qo'shildi.")
            return len(new_samples)
        return 0
    except Exception as e:
        logger.error(f"Telegram eksportini tahlil qilishda xatolik: {e}")
        return 0


# -------------------------------------------------------------------------
# STAGE 6: Ovozli xabarlar (Whisper STT), xulosa va erkin buyruqlar
# -------------------------------------------------------------------------

async def transcribe_voice(file_path: str) -> Optional[str]:
    """
    Ovozli xabarni (voice/audio) matnga o'girish.
    1. Agar GROQ_API_KEY yoki OPENAI_API_KEY bo'lsa - Whisper orqali;
    2. Aks holda Google Gemini Multimodal Audio orqali bepul va to'g'ridan-to'g'ri o'giradi.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"Ovozli fayl topilmadi: {file_path}")
        return None

    # 1. GROQ yoki OPENAI WHISPER ORQALI SINAB KO'RISH
    api_key = Config.GROQ_API_KEY or Config.OPENAI_API_KEY
    if api_key and AsyncOpenAI is not None:
        try:
            if Config.OPENAI_API_KEY:
                client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
                model_name = "whisper-1"
            else:
                client = AsyncOpenAI(base_url="https://api.groq.com/openai/v1", api_key=Config.GROQ_API_KEY)
                model_name = "whisper-large-v3"

            logger.info(f"Ovozli fayl Whisper API ga uzatilmoqda ({path.name}, model: {model_name})...")
            with open(path, "rb") as audio_file:
                transcription = await client.audio.transcriptions.create(
                    model=model_name,
                    file=audio_file,
                )
                result_text = getattr(transcription, "text", "")
                if result_text:
                    logger.info(f"Whisper transkripsiyasi muvaffaqiyatli: «{result_text[:50]}...»")
                    return result_text.strip()
        except Exception as we:
            logger.warning(f"Whisper STT xatoligi: {we}, Gemini orqali sinab ko'riladi...")

    # 2. GOOGLE GEMINI AUDIO ORQALI O'GIRISH (Qo'shimcha kalitsiz, to'g'ridan-to'g'ri bepul)
    if Config.GEMINI_API_KEY and genai is not None and types is not None:
        try:
            logger.info(f"Ovozli fayl Gemini Audio orqali transkripsiya qilinmoqda ({path.name})...")
            ext = path.suffix.lower()
            mime_type = "audio/ogg" if ext == ".ogg" else "audio/mp3" if ext == ".mp3" else "audio/wav"

            with open(path, "rb") as f:
                audio_bytes = f.read()

            client = genai.Client(api_key=Config.GEMINI_API_KEY)
            part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

            prompt = (
                "Ushbu audio/ovozli xabarni so'zma-so'z to'liq matnga o'gir (transkripsiya qil). "
                "Suhbatdosh qaysi tilda (o'zbek, rus yoki ingliz) gapirgan bo'lsa, aynan o'sha tilda yoz. "
                "Faqat eshitilgan matnning o'zini qaytar, hech qanday ortiqcha so'z yoki tushuntirish qo'shma."
            )

            models_to_try = [Config.GEMINI_MODEL, "gemini-3.7-flash", "gemini-3.5-flash", "gemini-flash-latest"]
            for m_name in models_to_try:
                try:
                    response = await client.aio.models.generate_content(
                        model=m_name,
                        contents=[part, prompt],
                    )
                    if response and response.text:
                        text_clean = response.text.strip()
                        logger.info(f"Gemini ovoz transkripsiyasi muvaffaqiyatli: «{text_clean[:50]}...»")
                        return text_clean
                except Exception as me:
                    logger.warning(f"Gemini Audio ({m_name}) xatoligi: {me}")

        except Exception as ge:
            logger.error(f"Gemini audio transkripsiyasida xatolik: {ge}", exc_info=True)

    return None


async def summarize_messages(messages: List[Dict[str, Any]]) -> str:
    """
    Bugungi yozishmalar asosida AI orqali qisqa, aniq va
    tizimli Executive Summary (kunlik xulosa) tayyorlash.
    """
    if not messages:
        return "📭 Bugun hali hech qanday yozishmalar mavjud emas."

    dialogues_text = []
    chats = defaultdict(list)
    for m in messages:
        chat_id = m.get("chat_id")
        chats[chat_id].append(m)

    for chat_id, chat_msgs in chats.items():
        sample_name = chat_msgs[0].get("sender_name") or chat_msgs[0].get("sender_username") or f"Chat {chat_id}"
        lines = [f"--- Suhbat: {sample_name} (ID: {chat_id}) ---"]
        for msg in chat_msgs:
            direction = "Akkaunt egasi (Men)" if msg.get("is_outgoing") else (msg.get("sender_name") or "Suhbatdosh")
            text = (msg.get("text") or "").strip()
            time_str = msg.get("created_at") or ""
            if text:
                lines.append(f"[{time_str}] {direction}: {text}")
        dialogues_text.append("\n".join(lines))

    all_chats_content = "\n\n".join(dialogues_text)

    prompt = f"""Sen shaxsiy Telegram AI yordamchisisan. Akkaunt egasiga uning bugungi yozishmalari asosida
qisqa, lo'nda, qulay o'qiladigan va professional kunlik hisobot (Executive Summary) tayyorlab ber.

BUGUNGI YOZISHMALAR:
{all_chats_content}

QUYIDAGI ANIQ FORMATDA JAVOB BER (Telegram HTML formatida, <b>, <i>, <code> teglaridan foydalanib):
📊 <b>BUGUNGI YOZISHMALAR XULOSASI</b>
━━━━━━━━━━━━━━━━━━━━
👥 <b>Gaplashilgan asosiy shaxslar va mavzular:</b>
• <b>[Kontakt ismi]</b>: [Nima haqida gaplashildi, qisqa lo'nda 1 gap]

📌 <b>Muhim kelishuvlar va natijalar:</b>
• [Agar biror kelishuv, reja yoki sana belgilangan bo'lsa ko'rsat, bo'lmasa 'Mavjud emas']

⏳ <b>Javob kutilayotgan yoki ochiq masalalar:</b>
• [Kimdandir javob kutilayotgan yoki egasi e'tibor qaratishi kerak bo'lgan bandlar]

💡 <b>Tavsiya va eslatma:</b>
• [Akkaunt egasi uchun amaliy 1-2 ta eslatma]

Faqat tayyor hisobot matnini qaytar. Hech qanday sarlavha yoki tirnoqsiz."""

    result = await call_llm(prompt=prompt, max_tokens=1000)
    if result:
        return result.strip()
    return "❌ Xulosa tayyorlab bo'lmadi. AI sozlamalarini tekshiring."


async def parse_and_compose_freeform(user_instruction: str) -> Optional[Dict[str, Any]]:
    """
    Erkin matn buyrug'ini (masalan: "Karimga ayt, ertaga borolmayman") tahlil qilish:
    1. Kontakt nomini aniqlash ("Karim")
    2. Akkaunt egasining uslubida tayyor xabar matnini tuzish
    """
    samples_block = load_style_samples(category="oila", max_samples=15)

    prompt = f"""Foydalanuvchi o'zining shaxsiy Telegram AI agentiga boshqaruv botida erkin matnli buyruq berdi.
Buyruq: «{user_instruction}»

Sening vazifang:
1. Bu buyruq biror kontaktga xabar yozish yoki gap yetkazish haqidami? (is_command: true/false)
   (Masalan: "Karimga ayt ertaga borolmayman", "Sherzodga yoz hisobot tayyor", "Tell John I will be late")
2. Agar ha bo'lsa:
   - contact_target: Qaysi kontaktga yuborilishi kerak? (Faqat ism yoki username ni ajrat, masalan 'Karim' yoki 'Sherzod' yoki '@nodir').
   - composed_text: Akkaunt egasi nomidan o'sha odamga yuboriladigan tayyor Telegram xabari.
     Xabar egasining uslubida: qisqa, tabiiy, salom bilan, ortiqcha rasmiyatchiliksiz bo'lsin.

{samples_block}

Faqat va faqat to'g'ri JSON formatida javob qaytar (markdown blocsiz yoki ```json teglari ichida):
{{
  "is_command": true,
  "contact_target": "Karim",
  "composed_text": "Salom Karim, uzr ertaga borolmayman, boshqa kunga sursak bo'ladimi?"
}}
Agar bu xabar yuborish buyrug'i bo'lmasa, quyidagicha qaytar:
{{
  "is_command": false,
  "contact_target": null,
  "composed_text": null
}}
"""
    raw_res = await call_llm(prompt=prompt, max_tokens=350)
    if raw_res:
        try:
            clean_json = raw_res.strip()
            if clean_json.startswith("```"):
                clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(clean_json)
            if data and data.get("is_command") and data.get("contact_target"):
                return data
        except Exception as e:
            logger.error(f"Erkin buyruqni tahlil qilishda JSON xatoligi: {e}")

    # LLM mavjud bo'lmaganda zaxira tahlilchi (Regex fallback)
    pattern = r"^([\w@]+?)(?:ga|ka|qa|ge|ke|qe|га|ка|қа)?\s+(?:ayt(?:gin)?|yoz(?:gin)?|yetkaz(?:gin)?|айт|ёз|етказиб qo\'y)[,:\s]+(.+)$"
    m = re.match(pattern, user_instruction.strip(), re.IGNORECASE)
    if m:
        target = m.group(1).strip()
        body = m.group(2).strip()
        return {
            "is_command": True,
            "contact_target": target,
            "composed_text": f"Salom, {body}",
        }

    return None
