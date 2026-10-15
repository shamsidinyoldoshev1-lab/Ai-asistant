import os
import html
import random
import asyncio
from typing import Optional, Tuple
from telethon import TelegramClient, events
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    DocumentAttributeFilename,
    DocumentAttributeAudio,
    DocumentAttributeVideo,
)

from config import Config, logger
import db
import control_bot
import safety
import ai

_client: Optional[TelegramClient] = None


def extract_media_info(event: events.NewMessage.Event) -> Tuple[Optional[str], Optional[str]]:
    """Xabardagi media turini va taxminiy fayl nomini aniqlash."""
    if not event.message.media:
        return None, None

    media = event.message.media
    media_type = "unknown"
    ext = ""

    if isinstance(media, MessageMediaPhoto):
        media_type = "photo"
        ext = ".jpg"
    elif isinstance(media, MessageMediaDocument):
        doc = media.document
        media_type = "document"
        ext = ".bin"

        # Atributlardan media turini aniqroq aniqlash
        if doc and hasattr(doc, "attributes"):
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeAudio):
                    if getattr(attr, "voice", False):
                        media_type = "voice"
                        ext = ".ogg"
                    else:
                        media_type = "audio"
                        ext = ".mp3"
                elif isinstance(attr, DocumentAttributeVideo):
                    media_type = "video"
                    ext = ".mp4"
                elif isinstance(attr, DocumentAttributeFilename):
                    orig_name = attr.file_name
                    ext = os.path.splitext(orig_name)[1]

    filename = f"{event.chat_id}_{event.message.id}{ext}"
    return media_type, filename


async def handle_new_message(event: events.NewMessage.Event):
    """Barcha kiruvchi va chiquvchi xabarlarni tutib olish va bazaga saqlash."""
    try:
        msg = event.message
        if not msg:
            return

        chat_id = event.chat_id
        telegram_message_id = msg.id
        is_outgoing = msg.out

        # Boshqaruv boti, xizmat kanallari va botlar bilan o'zaro loopga tushishni oldini olish
        bot_id_str = Config.BOT_TOKEN.split(":")[0] if ":" in Config.BOT_TOKEN else ""
        control_bot_id = int(bot_id_str) if bot_id_str.isdigit() else 0

        # Agar xabar boshqaruv boti bilan bo'lsa yoki Telegram rasmiy xizmatidan bo'lsa, e'tiborsiz qoldiramiz
        if chat_id in (control_bot_id, 777000, 42777) or (msg.sender_id and msg.sender_id in (control_bot_id, 777000, 42777)):
            return

        # Yuboruvchi ma'lumotlarini olish
        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            return

        sender_id = msg.sender_id or chat_id
        sender_name = None
        sender_username = None

        if sender:
            first_name = getattr(sender, "first_name", "") or ""
            last_name = getattr(sender, "last_name", "") or ""
            sender_name = f"{first_name} {last_name}".strip() or getattr(sender, "title", None)
            sender_username = getattr(sender, "username", None)

        # Media mavjud bo'lsa yuklab olish
        media_path = None
        media_type, media_filename = extract_media_info(event)
        if media_filename:
            target_path = Config.MEDIA_DIR / media_filename
            try:
                downloaded = await event.message.download_media(file=str(target_path))
                if downloaded:
                    media_path = str(target_path)
            except Exception as e:
                logger.warning(f"Media yuklab olishda xatolik: {e}")

        # Bazaga saqlash
        msg_text = msg.text or ""
        await db.save_message(
            telegram_message_id=telegram_message_id,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_username=sender_username,
            text=msg_text,
            media_path=media_path,
            media_type=media_type,
            is_outgoing=is_outgoing,
        )

        direction = "Chiquvchi" if is_outgoing else "Kiruvchi"
        logger.info(
            f"[{direction} xabar] Chat: {chat_id} | Sender: {sender_name or sender_id} | "
            f"ID: {telegram_message_id} | Matn: {msg_text[:40] if msg_text else f'<{media_type}>'}"
        )

        # Ovozli xabar (voice/audio) transkripsiyasi (Whisper STT)
        if not is_outgoing and media_type in ("voice", "audio") and media_path:
            logger.info(f"Ovozli xabar aniqlandi, transkripsiya qilinmoqda ({media_path})...")
            transcription = await ai.transcribe_voice(media_path)
            if transcription:
                await db.update_message_transcription(telegram_message_id, chat_id, transcription)
                msg_text = f"[🎙 Ovozli xabar]: {transcription}"
                logger.info(f"Ovozli xabar transkripsiyasi: «{transcription[:50]}...»")
            else:
                if not (Config.OPENAI_API_KEY or Config.GROQ_API_KEY or Config.GEMINI_API_KEY):
                    safe_sender = html.escape(str(sender_name or chat_id))
                    await control_bot.notify_admin(
                        f"🎙 <b>{safe_sender}</b> dan yangi ovozli xabar keldi.\n"
                        "<i>(Eslatma: Ovozni avtomatik matnga o'girish uchun GEMINI_API_KEY, GROQ_API_KEY yoki OPENAI_API_KEY ni to'ldiring)</i>"
                    )

        # Rasm yoki hujjat (chek, PDF) tahlili
        if not is_outgoing and event.is_private and media_type in ("photo", "document") and media_path:
            try:
                import document_analyzer
                logger.info(f"Yuborilgan {media_type} tahlil qilinmoqda...")
                doc_summary = await document_analyzer.analyze_document_or_image(
                    file_path=media_path,
                    user_instruction="Ushbu yuborilgan fayl yoki chekni qisqa lo'nda 1-2 gapda tahlil qil."
                )
                if doc_summary and not doc_summary.startswith("❌"):
                    clean_summary = doc_summary.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
                    msg_text = f"[{media_type.upper()}: {clean_summary[:150]}] {msg_text}".strip()
            except Exception as de:
                logger.warning(f"Media tahlilida xatolik: {de}")

        # AI javob tayyorlash (faqat kiruvchi xabarlar uchun)
        if not is_outgoing and msg_text.strip():
            await process_incoming_message_for_ai(
                event=event,
                chat_id=chat_id,
                telegram_message_id=telegram_message_id,
                sender_id=sender_id,
                sender_name=sender_name,
                msg_text=msg_text,
            )

    except Exception as e:
        logger.error(f"Xabarni saqlashda xatolik yuz berdi: {e}", exc_info=True)


async def process_incoming_message_for_ai(
    event: events.NewMessage.Event,
    chat_id: int,
    telegram_message_id: int,
    sender_id: int,
    sender_name: Optional[str],
    msg_text: str,
):
    """
    Kiruvchi xabarni rejimlar va xavfsizlik filtri bo'yicha tahlil qilish:
    - Global pauza tekshiruvi
    - Guruhlarni filtrlash (faqat reply yoki ism aytilganda)
    - Xavfsizlik filtri: karta, parol, pul, tibbiyot, shartnoma, huquq (hech qachon avto javob berilmaydi!)
    - Rejimlar:
      * "ochiq"   : hech narsa qilmaydi
      * "tasdiq"  : javob qoralamasini adminga tugmalar bilan yuboradi
      * "aralash" : oddiy savollarga o'zi, muhimlariga tasdiq so'raydi
      * "avto"    : o'zi mustaqil javob beradi (kechikish va typing bilan)
    """
    try:
        # 1. Global pauzada bo'lsa hech narsa qilmaymiz
        if await db.is_global_paused():
            return

        # 2. Guruhlar va kanallarga UMUMAN javob bermaslik (faqat shaxsiy / lichka xabarlariga javob beradi)
        if not event.is_private or event.is_group or event.is_channel or chat_id < 0:
            return

        # 3. Kontakt rejimini tekshirish
        contact_settings = await db.get_contact_settings(chat_id)
        mode = contact_settings.get("mode", getattr(Config, "DEFAULT_MODE", "avto"))
        contact_type = contact_settings.get("contact_type", "notanish")

        if mode == "ochiq":
            return

        # 4. XAVFSIZLIK FILTRI TEKSHIRUVI (Prompt 69-qoida)
        # Pul, karta, parol, kod, shartnoma, tibbiyot, huquq bo'yicha HECH QACHON avto javob berilmaydi!
        safety_check = safety.check_safety(msg_text)
        if safety_check["is_sensitive"]:
            category = safety_check["category"]
            reason = safety_check["reason"]
            logger.warning(f"Nozik mavzu aniqlandi ({category}): '{msg_text[:50]}' | Chat: {chat_id}")

            # Ehtiyotkor qoralama tayyorlash
            draft_text = await ai.generate_reply(
                chat_id=chat_id,
                incoming_message_text=msg_text,
                contact_name=sender_name,
                contact_type=contact_type,
            )

            draft_id = None
            if draft_text:
                draft_id = await db.create_draft(
                    chat_id=chat_id,
                    draft_text=draft_text,
                    contact_name=sender_name,
                    reply_to_msg_id=telegram_message_id,
                )

            # Adminga qizil xavfsizlik ogohlantirishini yuborish
            await control_bot.send_safety_alert(
                chat_id=chat_id,
                contact_name=sender_name,
                incoming_text=msg_text,
                category=category,
                reason=reason,
                draft_id=draft_id,
                draft_text=draft_text,
            )
            return

        # 5. REJIMLAR BO'YICHA ISHLOV BERISH
        # A) "tasdiq" rejimi (standart)
        if mode == "tasdiq":
            draft_text = await ai.generate_reply(
                chat_id=chat_id,
                incoming_message_text=msg_text,
                contact_name=sender_name,
                contact_type=contact_type,
            )
            if draft_text:
                await control_bot.send_draft_to_admin(
                    chat_id=chat_id,
                    draft_text=draft_text,
                    contact_name=sender_name,
                    reply_to_msg_id=telegram_message_id,
                    note="Standart tasdiq rejimi",
                    incoming_text=msg_text,
                )
                logger.info(f"Yangi xabar uchun javob qoralamasi adminga yuborildi. Chat: {chat_id}")

        # B) "aralash" rejimi
        elif mode == "aralash":
            if safety.is_simple_question(msg_text):
                # Oddiy savol (salomlashish, ish vaqti, manzil) -> Avtomatik javob beriladi
                logger.info(f"'aralash' rejimi: oddiy savol aniqlandi. Avto-javob tayyorlanmoqda... Chat: {chat_id}")
                reply_text = await ai.generate_reply(
                    chat_id=chat_id,
                    incoming_message_text=msg_text,
                    contact_name=sender_name,
                    contact_type=contact_type,
                )
                if reply_text:
                    success = await send_userbot_message(
                        chat_id=chat_id,
                        text=reply_text,
                        reply_to=telegram_message_id,
                        simulate_typing=True,
                        delay_range=(3.0, 8.0),
                    )
                    if success:
                        await control_bot.notify_auto_reply(
                            chat_id=chat_id,
                            contact_name=sender_name or str(chat_id),
                            incoming_text=msg_text,
                            reply_text=reply_text,
                            mode="aralash (oddiy savol)",
                        )
            else:
                # Murakkab savol, uchrashuv yoki va'da -> Tasdiq so'raladi
                logger.info(f"'aralash' rejimi: uchrashuv/muhim masala. Tasdiq so'ralmoqda... Chat: {chat_id}")
                draft_text = await ai.generate_reply(
                    chat_id=chat_id,
                    incoming_message_text=msg_text,
                    contact_name=sender_name,
                    contact_type=contact_type,
                )
                if draft_text:
                    await control_bot.send_draft_to_admin(
                        chat_id=chat_id,
                        draft_text=draft_text,
                        contact_name=sender_name,
                        reply_to_msg_id=telegram_message_id,
                        note="Rejim: aralash (Uchrashuv/muhim masala tasdiqlanishi kerak)",
                        incoming_text=msg_text,
                    )

        # C) "avto" rejimi
        elif mode == "avto":
            logger.info(f"'avto' rejimi: xabarga to'g'ridan-to'g'ri avto-javob berilmoqda... Chat: {chat_id}")
            reply_text = await ai.generate_reply(
                chat_id=chat_id,
                incoming_message_text=msg_text,
                contact_name=sender_name,
                contact_type=contact_type,
            )
            if reply_text:
                success = await send_userbot_message(
                    chat_id=chat_id,
                    text=reply_text,
                    reply_to=telegram_message_id,
                    simulate_typing=True,
                    delay_range=(2.0, 5.0),
                )
                if success:
                    await control_bot.notify_auto_reply(
                        chat_id=chat_id,
                        contact_name=sender_name or str(chat_id),
                        incoming_text=msg_text,
                        reply_text=reply_text,
                        mode="avto",
                    )

    except Exception as e:
        logger.error(f"AI javob jarayonida xatolik: {e}", exc_info=True)


async def handle_deleted_message(event: events.MessageDeleted.Event):
    """
    O'chirilgan xabarlarni tutib olish, bazada belgilash va boshqaruv boti orqali
    adminga o'chirilgan xabar ma'lumotlarini (va mediasini) yuborish.
    """
    try:
        deleted_ids = event.deleted_ids or []
        chat_id = event.chat_id

        bot_id_str = Config.BOT_TOKEN.split(":")[0] if ":" in Config.BOT_TOKEN else ""
        control_bot_id = int(bot_id_str) if bot_id_str.isdigit() else 0
        if chat_id in (control_bot_id, 777000, 42777):
            return

        for msg_id in deleted_ids:
            deleted_info = await db.mark_message_deleted(telegram_message_id=msg_id, chat_id=chat_id)
            if not deleted_info:
                # Xabar bazada mavjud bo'lmasa (masalan, bot ishga tushgunga qadar yuborilgan)
                continue

            logger.info(
                f"[O'chirilgan xabar] Chat: {deleted_info.get('chat_id')} | ID: {msg_id} | "
                f"Kimdan: {deleted_info.get('sender_name') or deleted_info.get('sender_id')}"
            )

            # Faqat kiruvchi xabarlar o'chirilganda xabarnoma beriladi
            if not deleted_info.get("is_outgoing"):
                # 1. Boshqaruv boti orqali yuborishga urinish
                sent = await control_bot.send_deleted_message_alert(deleted_info)

                # 2. Agar boshqaruv boti sozlanmagan bo'lsa, Saqlangan xabarlar (Saved Messages) ga yuborish
                if not sent and _client:
                    try:
                        alert_text = control_bot.format_deleted_message_text(deleted_info)
                        media_path = deleted_info.get("media_path")
                        if media_path and os.path.exists(media_path):
                            await _client.send_file(
                                "me",
                                file=media_path,
                                caption=alert_text,
                                parse_mode="html",
                            )
                        else:
                            await _client.send_message("me", alert_text, parse_mode="html")
                        logger.info("O'chirilgan xabar Saqlangan xabarlar (Saved Messages) ga yuborildi.")
                    except Exception as fe:
                        logger.error(f"Saved Messages ga xabarnoma yuborishda xatolik: {fe}")

    except Exception as e:
        logger.error(f"O'chirilgan xabarni qayta ishlashda xatolik yuz berdi: {e}", exc_info=True)


async def handle_edited_message(event: events.MessageEdited.Event):
    """Tahrirlangan xabarlarni tutib olish va bazada asl hamda yangi matnlarni yangilash."""
    try:
        msg = event.message
        if not msg:
            return

        chat_id = event.chat_id
        bot_id_str = Config.BOT_TOKEN.split(":")[0] if ":" in Config.BOT_TOKEN else ""
        control_bot_id = int(bot_id_str) if bot_id_str.isdigit() else 0
        if chat_id in (control_bot_id, 777000, 42777):
            return
        msg_id = msg.id
        new_text = msg.text or ""

        old_data = await db.update_message_text(
            telegram_message_id=msg_id,
            new_text=new_text,
            chat_id=chat_id,
        )

        if old_data:
            orig_text = old_data.get("original_text") or old_data.get("text") or ""
            logger.info(
                f"[Tahrirlangan xabar] Chat: {chat_id} | ID: {msg_id} | "
                f"Eski: '{orig_text[:30]}' -> Yangi: '{new_text[:30]}'"
            )
        else:
            # Agar xabar bazada topilmasa, yangi xabar sifatida qo'shamiz
            await handle_new_message(event)

    except Exception as e:
        logger.error(f"Tahrirlangan xabarni qayta ishlashda xatolik yuz berdi: {e}", exc_info=True)


def get_userbot_client() -> TelegramClient:
    """Userbot clientini yaratish yoki mavjudini qaytarish."""
    global _client
    if _client is None:
        Config.validate_for_userbot()
        _client = TelegramClient(
            str(Config.BASE_DIR / Config.SESSION_NAME),
            Config.API_ID,
            Config.API_HASH,
        )
        # Hodisalarni ro'yxatdan o'tkazish
        _client.add_event_handler(handle_new_message, events.NewMessage)
        _client.add_event_handler(handle_deleted_message, events.MessageDeleted)
        _client.add_event_handler(handle_edited_message, events.MessageEdited)
    return _client


async def start_userbot() -> TelegramClient:
    """Userbotni ishga tushirish."""
    client = get_userbot_client()
    logger.info("Userbot sessiyasi ulanmoqda...")
    await client.start()
    me = await client.get_me()
    logger.info(f"Userbot muvaffaqiyatli ishga tushdi! Akkaunt: {me.first_name} (@{me.username}) ID: {me.id}")
    return client


async def send_userbot_message(
    chat_id: int,
    text: str,
    reply_to: Optional[int] = None,
    simulate_typing: bool = True,
    delay_range: Tuple[float, float] = (3.0, 7.0),
) -> bool:
    """
    Userbot akkaunti orqali suhbatdoshga xabar yuborish.
    Xabarni yuborishdan oldin:
    - Spam va flood limitlarini (RateLimiter) tekshiradi
    - 3-10 soniya tasodifiy kechikish va 'yozmoqda...' (typing) statusini imitatsiya qiladi
    - Yuborilgach, bazaga ham saqlaydi.
    """
    client = get_userbot_client()

    # 1. Spamdan himoya - Rate limiter tekshiruvi
    allowed, reason = safety.rate_limiter.is_allowed(chat_id)
    if not allowed:
        logger.warning(f"Xabar yuborish rad etildi: {reason} | Chat: {chat_id}")
        await control_bot.notify_admin(
            f"⚠️ <b>Spam himoyasi (Rate Limit):</b>\n"
            f"Chat <code>{chat_id}</code> ga xabar yuborilmadi: <i>{reason}</i>"
        )
        return False

    try:
        # 2. Insoniy harakat imitatsiyasi: tasodifiy kechikish va 'yozmoqda...' holati
        if simulate_typing:
            delay = round(random.uniform(delay_range[0], delay_range[1]), 1)
            logger.info(f"Chat {chat_id} ga yozish imitatsiyasi ({delay}s kutilmoqda)...")
            try:
                async with client.action(chat_id, "typing"):
                    await asyncio.sleep(delay)
            except Exception as te:
                logger.warning(f"Typing action xatoligi (e'tiborsiz qoldirildi): {te}")
                await asyncio.sleep(delay)

        # 3. Xabarni yuborish
        sent_msg = await client.send_message(
            entity=chat_id,
            message=text,
            reply_to=reply_to,
        )
        safety.rate_limiter.record_sent(chat_id)

        # 4. Bazaga saqlash
        me = await client.get_me()
        await db.save_message(
            telegram_message_id=sent_msg.id,
            chat_id=chat_id,
            sender_id=me.id,
            sender_name=f"{getattr(me, 'first_name', '') or ''} {getattr(me, 'last_name', '') or ''}".strip(),
            sender_username=getattr(me, 'username', None),
            text=text,
            is_outgoing=True,
        )
        logger.info(f"[Chiquvchi xabar yuborildi] Chat: {chat_id} | Matn: {text[:40]}")
        return True
    except Exception as e:
        logger.error(f"Userbot orqali xabar yuborishda xatolik: {e}", exc_info=True)
        return False

