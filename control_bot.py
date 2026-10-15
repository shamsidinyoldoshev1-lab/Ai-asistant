import os
import sys
import re
import html
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command, StateFilter, BaseFilter
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError

from config import Config, logger
import db

_bot: Optional[Bot] = None
_dp: Optional[Dispatcher] = None
router = Router()
public_router = Router()


class EditDraftState(StatesGroup):
    """Qoralamani tahrirlash holati (FSM)."""
    waiting_for_new_text = State()


class AdminFilter(BaseFilter):
    """Faqat ADMIN_USER_ID dan kelgan xabarlarni o'tkazuvchi filtr."""
    async def __call__(self, event: types.TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if not Config.ADMIN_USER_ID:
            return True
        return user is not None and user.id == Config.ADMIN_USER_ID


# Routerga admin filtrini o'rnatish (begonalarga umuman javob bermaydi)
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


# -------------------------------------------------------------------------
# INLINE TUGMALAR VA FORMATLASH
# -------------------------------------------------------------------------

def get_draft_keyboard(draft_id: int, calendar_url: Optional[str] = None) -> InlineKeyboardMarkup:
    """Javob qoralamasi uchun asosiy boshqaruv tugmalari."""
    rows = [
        [
            InlineKeyboardButton(text="✅ Yuborish", callback_data=f"draft:send:{draft_id}"),
            InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"draft:edit:{draft_id}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"draft:cancel:{draft_id}"),
        ]
    ]
    if calendar_url:
        rows.append([InlineKeyboardButton(text="📅 Google Calendar-ga qo'shish", url=calendar_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_draft_message(
    contact_name: str,
    chat_id: int,
    draft_text: str,
    draft_id: Optional[int] = None,
    note: Optional[str] = None,
    incoming_text: Optional[str] = None,
) -> str:
    """Qoralama kartasining matnini tayyorlash."""
    safe_name = html.escape(str(contact_name))
    safe_text = html.escape(str(draft_text))
    id_line = f"🆔 <b>Qoralama ID:</b> <code>#{draft_id}</code>\n" if draft_id else ""
    note_line = f"📌 <b>Holat/Rejim:</b> <i>{html.escape(str(note))}</i>\n" if note else ""
    incoming_line = (
        f"📩 <b>Suhbatdosh yozgan xabar:</b>\n"
        f"<i>«{html.escape(str(incoming_text))}»</i>\n\n"
        if incoming_text else ""
    )

    return (
        "📝 <b>YANGI JAVOB QORALAMASI (Tasdiqlash uchun)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Kontakt:</b> {safe_name}\n"
        f"💬 <b>Chat ID:</b> <code>{chat_id}</code>\n"
        f"{id_line}"
        f"{note_line}"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{incoming_line}"
        f"💡 <b>Taklif etilayotgan javob:</b>\n"
        f"<i>«{safe_text}»</i>\n\n"
        "<i>Quyidagi tugmalar orqali tasdiqlang yoki tahrirlang:</i>"
    )


# -------------------------------------------------------------------------
# ASOSIY BUYRUQLAR (COMMANDS)
# -------------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Admin uchun /start buyrug'i."""
    await message.answer(
        "👋 <b>Assalomu alaykum, Xo'jayin!</b>\n\n"
        "Men sizning shaxsiy Telegram AI agentingizni boshqaruvchi botman.\n"
        "Barcha xabarlar, javob tasdiqlari, hisobotlar va tahlillar shu yerda boshqariladi.\n\n"
        "📌 <b>Asosiy buyruqlar:</b>\n"
        "• /holat — Agent holati, rejimlar va statistika\n"
        "• /xulosa — Bugungi yozishmalar tahlili va xulosasi\n"
        "• /qidir — Saqlangan xabarlar ichidan qidirish\n"
        "• /eslatma — Javobsiz qolgan xabarlar ro'yxati\n"
        "• /pauza va /davom — Javoblarni to'xtatish / tiklash\n"
        "• /rejim — Kontakt javob rejimini sozlash (tasdiq, avto, aralash, ochiq)\n"
        "• /ohang — Muloqot ohangini belgilash (oila, ish, notanish)\n"
        "• /xavfsizlik — Filtrlar va spamdan himoya tizimi\n"
        "• /yoz — Kontaktga xabar tayyorlash\n"
        "• /yordam — To'liq qo'llanma\n\n"
        "💡 <i>Shuningdek, to'g'ridan-to'g'ri erkin matn yozishingiz mumkin:</i>\n"
        "«Karimga ayt, ertaga borolmayman»",
        parse_mode="HTML",
    )


@router.message(Command("yordam"))
async def cmd_help(message: types.Message):
    """Qo'llanma va buyruqlar tushuntirishi."""
    help_text = (
        "🛠 <b>BOSHQARUV BOTI QO'LLANMASI</b>\n\n"
        "<b>1. Holat, xulosa va qidiruv:</b>\n"
        "• <code>/holat</code> — Agent holati, statistika va kontakt rejimlarini ko'rish.\n"
        "• <code>/xulosa</code> — Bugungi yozishmalarning qisqa executive xulosasi.\n"
        "• <code>/qidir &lt;so'z&gt;</code> — Saqlangan barcha yozishmalardan so'z qidirish.\n"
        "• <code>/eslatma [kun]</code> — N kundan beri javob berilmagan xabarlar (standart 3 kun).\n"
        "• <code>/pauza</code> va <code>/davom</code> — Agentni vaqtincha to'xtatish / davom ettirish.\n"
        "• <code>/xavfsizlik</code> — Xavfsizlik filtri, spam cheklovi va nozik mavzular.\n\n"
        "<b>2. Rejimlar va muloqot ohangi:</b>\n"
        "• <code>/rejim &lt;kontakt&gt; &lt;tasdiq|avto|aralash|ochiq&gt;</code> — Javob rejimini sozlash:\n"
        "  - <b>tasdiq</b>: Sizdan ruxsat so'rab qoralama yuboradi (standart).\n"
        "  - <b>avto</b>: O'zi mustaqil javob beradi (nozik mavzular bundan mustasno).\n"
        "  - <b>aralash</b>: Salom va ma'lumotlarga o'zi, muhimlariga tasdiq so'raydi.\n"
        "  - <b>ochiq</b>: Umuman javob bermaydi.\n"
        "• <code>/ohang &lt;kontakt&gt; &lt;oila|ish|notanish&gt;</code> — Kontakt uchun muloqot ohangini belgilash.\n\n"
        "<b>3. Erkin buyruqlar va xabar yuborish:</b>\n"
        "• <b>Erkin matn:</b> <i>«Karimga ayt, ertaga borolmayman»</i> — agent sizning uslubingizda tayyorlab, tasdiqlatib Karimga yuboradi.\n"
        "• <code>/yoz &lt;kontakt&gt; &lt;matn&gt;</code> — Kontaktga tasdiqlash uchun xabar qoralamasini chiqarish.\n"
        "• <code>/ai &lt;savol/matn&gt;</code> — Claude AI javobini bevosita botda sinab ko'rish.\n"
        "• <code>/test_qoralama</code> — Tugmalar va tahrirlash tizimini sinash uchun test qoralama.\n"
        "• <code>/cancel</code> — Joriy amaliyotni bekor qilish."
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("holat"))
async def cmd_status(message: types.Message):
    """Agent holati, statistika va sozlangan kontaktlar ro'yxati."""
    import safety
    is_paused = await db.is_global_paused()
    stats = await db.get_database_stats()
    contacts = await db.get_all_contact_settings()
    limiter_stats = safety.rate_limiter.get_stats()

    status_icon = "⏸ <b>PAUZA HOLATIDA</b>" if is_paused else "🟢 <b>FAOL ISHLAMOQDA</b>"

    text = (
        "📊 <b>AGENT HOLATI VA STATISTIKA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Holat:</b> {status_icon}\n"
        "⚙️ <b>Standart rejim:</b> <code>tasdiq</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📈 <b>Yozishmalar statistikasi:</b>\n"
        f"• Jami saqlangan xabarlar: <b>{stats['total_messages']}</b> ta\n"
        f"• 🗑 O'chirilgan xabarlar: <b>{stats['deleted_messages']}</b> ta\n"
        f"• ✏️ Tahrirlangan xabarlar: <b>{stats['edited_messages']}</b> ta\n"
        f"• 📁 Media fayllar: <b>{stats['media_messages']}</b> ta\n"
        f"• ⏳ Kutilayotgan qoralamalar: <b>{stats['pending_drafts']}</b> ta\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛡 <b>Xavfsizlik va limitlar:</b>\n"
        f"• Daqiqalik global limit: <b>{limiter_stats['global_sent_last_min']}/{limiter_stats['max_global']}</b> ta xabar\n"
        f"• Oxirgi 1 daqiqada faol chatlar: <b>{limiter_stats['active_chats_last_min']}</b> ta\n"
        "• Spam filtri: <b>Faol (3-10s kechikish + 'yozmoqda...' holati)</b>\n"
        "• Nozik mavzular filtri: <b>Faol (karta, kod, moliya, huquq, tibbiyot)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
    )

    if contacts:
        text += "👥 <b>Maxsus sozlangan kontaktlar:</b>\n"
        for c in contacts[:10]:
            name = c.get("contact_name") or c.get("contact_username") or c["chat_id"]
            mode = c.get("mode", "tasdiq")
            text += f"• <b>{html.escape(str(name))}</b>: <code>{mode}</code>\n"
        if len(contacts) > 10:
            text += f"<i>...va yana {len(contacts) - 10} ta kontakt</i>\n"
    else:
        text += "👥 Hozircha barcha kontaktlar standart <code>tasdiq</code> rejimida."

    await message.answer(text, parse_mode="HTML")


@router.message(Command("xavfsizlik"))
async def cmd_security(message: types.Message):
    """Xavfsizlik filtrlari va limitlar haqida batafsil ma'lumot."""
    import safety
    limiter_stats = safety.rate_limiter.get_stats()

    text = (
        "🛡 <b>XAVFSIZLIK VA CHEKLOVLAR TIZIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚫 <b>Avtomatik bloklanuvchi nozik mavzular:</b>\n"
        "• 💳 <b>Moliya:</b> Pul, karta raqamlari, to'lov, qarz, o'tkazma, kredit\n"
        "• 🔑 <b>Xavfsizlik:</b> Parollar, SMS tasdiqlash kodlari, PIN, CVV/OTP\n"
        "• 📜 <b>Shartnoma:</b> Bitim, kontrakt, imzo, kafolat, qat'iy va'dalar\n"
        "• 💊 <b>Tibbiyot:</b> Dori, tashxis, retsept, shifokor tavsiyasi\n"
        "• ⚖️ <b>Huquqiy:</b> Sud, prokuratura, ichki ishlar, ariza, jarima\n\n"
        "⚠️ <i>Ushbu mavzularda agent hech qachon o'zi javob bermaydi, "
        "darhol adminga qizil ogohlantirish yuboradi!</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ <b>Spam va Flood himoyasi:</b>\n"
        f"• Global limit: <b>{limiter_stats['max_global']}</b> ta xabar / daqiqa\n"
        f"• Bitta chat limiti: <b>{limiter_stats['max_per_chat']}</b> ta xabar / daqiqa\n"
        f"• So'nggi 1 daqiqada yuborilgan: <b>{limiter_stats['global_sent_last_min']}</b> ta\n"
        "• Kechikish: Xabar yuborishdan oldin <b>3-10 soniya</b> tabiiy kutish\n"
        "• Tabiiy holat: Javob berish oldidan <i>'yozmoqda...'</i> statusi yoqiladi\n"
        "• Guruhlar nazorati: Guruhda faqat sizga reply yoki @ism aytilsa ishlaydi"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("pauza"))
async def cmd_pause(message: types.Message):
    """Agentni global pauza qilish."""
    await db.set_global_paused(True)
    await message.answer(
        "⏸ <b>Agent vaqtincha to'xtatildi (PAUZA)!</b>\n\n"
        "Endi yangi xabarlarga avtomatik javoblar va tasdiq so'rovlari yuborilmaydi.\n"
        "Qayta faollashtirish uchun: /davom",
        parse_mode="HTML",
    )


@router.message(Command("davom"))
async def cmd_resume(message: types.Message):
    """Agent faoliyatini davom ettirish."""
    await db.set_global_paused(False)
    await message.answer(
        "▶️ <b>Agent faoliyati davom ettirildi!</b>\n\n"
        "Yozishmalarni qabul qilish va javoblarni rejim bo'yicha ko'rib chiqish faol.",
        parse_mode="HTML",
    )


@router.message(Command("rejim"))
async def cmd_set_mode(message: types.Message):
    """Kontakt rejimini belgilash: /rejim <kontakt> <tasdiq|avto|aralash|ochiq>."""
    args = (message.text or "").split(maxsplit=2)
    valid_modes = ["tasdiq", "avto", "aralash", "ochiq"]

    if len(args) < 3:
        await message.answer(
            "ℹ️ <b>Foydalanish:</b>\n"
            "<code>/rejim &lt;kontakt&gt; &lt;tasdiq|avto|aralash|ochiq&gt;</code>\n\n"
            "<b>Misollar:</b>\n"
            "• <code>/rejim @shaxzod avto</code>\n"
            "• <code>/rejim 12345678 aralash</code>\n"
            "• <code>/rejim Bobur tasdiq</code>\n\n"
            "<b>Rejimlar ma'nosi:</b>\n"
            "• <b>tasdiq</b>: Qoralama tayyorlab sizdan ruxsat so'raydi (standart).\n"
            "• <b>avto</b>: Agent o'zi mustaqil javob beradi.\n"
            "• <b>aralash</b>: Oddiylariga o'zi, muhimlariga tasdiq so'raydi.\n"
            "• <b>ochiq</b>: Agent bu kontaktga umuman javob qaytarmaydi.",
            parse_mode="HTML",
        )
        return

    contact_query = args[1].strip()
    mode = args[2].strip().lower()

    if mode not in valid_modes:
        await message.answer(
            f"❌ Noto'g'ri rejim: <code>{html.escape(mode)}</code>\n"
            f"Faqat quyidagilardan birini tanlang: <code>{', '.join(valid_modes)}</code>",
            parse_mode="HTML",
        )
        return

    contact_info = await db.find_contact(contact_query)
    if contact_info:
        chat_id = contact_info["chat_id"]
        contact_name = contact_info.get("contact_name") or contact_query
        contact_username = contact_info.get("contact_username")
        await db.set_contact_mode(
            chat_id=chat_id,
            mode=mode,
            contact_name=contact_name,
            contact_username=contact_username,
        )
        await message.answer(
            f"✅ <b>{html.escape(str(contact_name))}</b> uchun rejim <b>{mode}</b> ga muvaffaqiyatli o'zgartirildi!",
            parse_mode="HTML",
        )
    else:
        # Agar kontakt bazada bo'lmasa, agar ID yoki username kiritilgan bo'lsa yangi yozuv yaratamiz
        clean_q = contact_query.lstrip("@")
        if clean_q.lstrip("-").isdigit():
            chat_id = int(clean_q)
            await db.set_contact_mode(chat_id=chat_id, mode=mode, contact_name=contact_query)
            await message.answer(
                f"✅ Chat ID <code>{chat_id}</code> uchun rejim <b>{mode}</b> deb belgilandi.",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"⚠️ <b>{html.escape(contact_query)}</b> bazada topilmadi.\n"
                "Iltimos, kontakt bilan avval yozishgan bo'ling yoki uning aniq Telegram ID raqamini kiriting.",
                parse_mode="HTML",
            )


@router.message(Command("ohang"))
async def cmd_set_tone(message: types.Message):
    """Kontakt ohangini sozlash: /ohang <kontakt> <oila|ish|notanish>."""
    args = (message.text or "").split(maxsplit=2)
    valid_tones = ["oila", "ish", "notanish"]

    if len(args) < 3:
        await message.answer(
            "ℹ️ <b>Foydalanish:</b>\n"
            "<code>/ohang &lt;kontakt&gt; &lt;oila|ish|notanish&gt;</code>\n\n"
            "<b>Misollar:</b>\n"
            "• <code>/ohang @nodir oila</code>\n"
            "• <code>/ohang 12345678 ish</code>\n"
            "• <code>/ohang Sobir notanish</code>\n\n"
            "<b>Ohanglar ma'nosi:</b>\n"
            "• <b>oila</b>: Samimiy, erkin, do'stona (yaqinlar uchun).\n"
            "• <b>ish</b>: Rasmiy, ishchan, lo'nda (hamkasb va mijozlar uchun).\n"
            "• <b>notanish</b>: Qisqa, ehtiyotkor (yangi kontaktlar uchun).",
            parse_mode="HTML",
        )
        return

    contact_query = args[1].strip()
    tone = args[2].strip().lower()

    if tone not in valid_tones:
        await message.answer(
            f"❌ Noto'g'ri ohang: <code>{html.escape(tone)}</code>\n"
            f"Faqat quyidagilardan birini tanlang: <code>{', '.join(valid_tones)}</code>",
            parse_mode="HTML",
        )
        return

    contact_info = await db.find_contact(contact_query)
    if contact_info:
        chat_id = contact_info["chat_id"]
        name = contact_info.get("contact_name") or contact_query
        username = contact_info.get("contact_username")
        await db.set_contact_type(chat_id=chat_id, contact_type=tone, contact_name=name, contact_username=username)
        await message.answer(
            f"✅ <b>{html.escape(str(name))}</b> uchun muloqot ohangi <b>{tone}</b> ga sozlandi.",
            parse_mode="HTML",
        )
    else:
        clean_q = contact_query.lstrip("@")
        if clean_q.lstrip("-").isdigit():
            chat_id = int(clean_q)
            await db.set_contact_type(chat_id=chat_id, contact_type=tone, contact_name=contact_query)
            await message.answer(
                f"✅ Chat ID <code>{chat_id}</code> uchun muloqot ohangi <b>{tone}</b> deb belgilandi.",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"⚠️ <b>{html.escape(contact_query)}</b> bazada topilmadi.\n"
                "Iltimos, kontakt bilan avval yozishgan bo'ling yoki uning ID raqamini kiriting.",
                parse_mode="HTML",
            )


@router.message(Command("ai"))
async def cmd_test_ai(message: types.Message):
    """Claude AI javob berishini to'g'ridan-to'g'ri sinab ko'rish: /ai <savol yoki xabar>."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "ℹ️ <b>Foydalanish:</b> <code>/ai &lt;sinov xabari&gt;</code>\n\n"
            "Misol: <code>/ai Salom, bugun bo'shmisan?</code>",
            parse_mode="HTML",
        )
        return

    user_prompt = parts[1].strip()
    wait_msg = await message.answer("🧠 <i>Claude AI javob tayyorlamoqda...</i>", parse_mode="HTML")

    import ai
    reply = await ai.generate_reply(
        chat_id=message.from_user.id,
        incoming_message_text=user_prompt,
        contact_name="Admin (Test)",
        contact_type="oila",
    )

    if reply:
        safe_prompt = html.escape(user_prompt)
        safe_reply = html.escape(reply)
        await wait_msg.edit_text(
            f"💬 <b>Savol:</b> <i>«{safe_prompt}»</i>\n\n"
            f"🤖 <b>Claude javobi ({Config.CLAUDE_MODEL}):</b>\n"
            f"<b>«{safe_reply}»</b>",
            parse_mode="HTML",
        )
    else:
        await wait_msg.edit_text(
            "❌ Claude javob bera olmadi. Iltimos, <code>.env</code> faylida <code>ANTHROPIC_API_KEY</code> to'g'ri sozlanganligini tekshiring.",
            parse_mode="HTML",
        )


@router.message(Command("yoz"))
async def cmd_compose(message: types.Message):
    """Kontaktga agent orqali xabar qoralamasini tayyorlash: /yoz <kontakt> <matn>."""
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "ℹ️ <b>Foydalanish:</b> <code>/yoz &lt;kontakt&gt; &lt;xabar matni&gt;</code>\n\n"
            "Misol: <code>/yoz @sherzod Ertaga soat 15:00 da uchrashamiz</code>",
            parse_mode="HTML",
        )
        return

    contact_query = parts[1].strip()
    msg_text = parts[2].strip()

    contact_info = await db.find_contact(contact_query)
    if not contact_info:
        clean_q = contact_query.lstrip("@")
        if clean_q.lstrip("-").isdigit():
            chat_id = int(clean_q)
            contact_name = contact_query
        else:
            # Agar username bo'lsa Telethon userboti orqali entity olish imkoni ham bor
            chat_id = None
            contact_name = contact_query
    else:
        chat_id = contact_info["chat_id"]
        contact_name = contact_info.get("contact_name") or contact_query

    if not chat_id:
        await message.answer(
            f"❌ <b>{html.escape(contact_query)}</b> bo'yicha chat_id aniqlanmadi.\n"
            "Iltimos, ID raqami bilan yozing yoki kontakt bilan yozishganingizdan keyin urinib ko'ring.",
            parse_mode="HTML",
        )
        return

    # Qoralamani yaratish va adminga yuborish
    draft_id = await db.create_draft(
        chat_id=chat_id,
        draft_text=msg_text,
        contact_name=contact_name,
    )
    draft_card = format_draft_message(
        contact_name=contact_name,
        chat_id=chat_id,
        draft_text=msg_text,
        draft_id=draft_id,
    )
    sent_msg = await message.answer(
        draft_card,
        reply_markup=get_draft_keyboard(draft_id),
        parse_mode="HTML",
    )
    await db.update_draft_control_message(draft_id, sent_msg.message_id)


@router.message(Command("test_qoralama"))
async def cmd_test_draft(message: types.Message):
    """
    Stage 3 funksionalligini (tugmalar, tahrirlash, bekor qilish) sinash uchun test qoralama.
    Xabar o'zingizning 'Saved Messages' profilingizga yuboriladigan qilib tayyorlanadi.
    """
    my_id = message.from_user.id
    draft_text = "Assalomu alaykum! Bu agent tomonidan tayyorlangan sinov javob qoralamasi."
    contact_name = "O'zim (Saved Messages)"

    draft_id = await db.create_draft(
        chat_id=my_id,
        draft_text=draft_text,
        contact_name=contact_name,
    )
    draft_card = format_draft_message(
        contact_name=contact_name,
        chat_id=my_id,
        draft_text=draft_text,
        draft_id=draft_id,
    )

    sent_msg = await message.answer(
        draft_card,
        reply_markup=get_draft_keyboard(draft_id),
        parse_mode="HTML",
    )
    await db.update_draft_control_message(draft_id, sent_msg.message_id)


@router.message(Command("cancel"))
async def cmd_cancel_state(message: types.Message, state: FSMContext):
    """Joriy amaliyotni bekor qilish."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Hech qanday faol jarayon mavjud emas.")
        return
    await state.clear()
    await message.answer("🚫 Jarayon bekor qilindi.", parse_mode="HTML")


# -------------------------------------------------------------------------
# STAGE 6: Xulosa, Qidiruv, Eslatmalar va Erkin matn buyruqlari
# -------------------------------------------------------------------------

@router.message(Command("xulosa"))
async def cmd_summary(message: types.Message):
    """Bugungi yozishmalar xulosasi (Executive Summary)."""
    wait_msg = await message.answer("📊 <i>Bugungi yozishmalar tahlil qilinmoqda, kuting...</i>", parse_mode="HTML")
    today_msgs = await db.get_today_messages()
    if not today_msgs:
        await wait_msg.edit_text("📭 <b>Bugun hali hech qanday yozishmalar qayd etilmagan.</b>", parse_mode="HTML")
        return

    import ai
    summary_text = await ai.summarize_messages(today_msgs)
    try:
        await wait_msg.edit_text(summary_text, parse_mode="HTML")
    except Exception:
        await wait_msg.edit_text(summary_text)


@router.message(Command("qidir"))
async def cmd_search(message: types.Message):
    """Saqlangan yozishmalardan so'z yoki ibora bo'yicha qidirish: /qidir <so'z>."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "ℹ️ <b>Foydalanish:</b> <code>/qidir &lt;so'z&gt;</code>\n\n"
            "Misollar:\n"
            "• <code>/qidir uchrashuv</code>\n"
            "• <code>/qidir shartnoma</code>\n"
            "• <code>/qidir hisobot</code>",
            parse_mode="HTML",
        )
        return

    search_query = parts[1].strip()
    results = await db.search_messages(search_query, limit=8)

    if not results:
        await message.answer(
            f"🔍 <b>«{html.escape(search_query)}»</b> bo'yicha bazada hech qanday xabar topilmadi.",
            parse_mode="HTML",
        )
        return

    text = (
        f"🔍 <b>QIDIRUV NATIJALARI: «{html.escape(search_query)}»</b>\n"
        f"<i>Topildi: {len(results)} ta xabar</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for idx, r in enumerate(results, 1):
        direction = "📤 Men" if r.get("is_outgoing") else f"📥 {r.get('sender_name') or r.get('sender_id')}"
        time_str = r.get("created_at") or ""
        msg_text = r.get("text") or r.get("original_text") or ""

        safe_msg = html.escape(msg_text)
        safe_q = html.escape(search_query)
        highlighted = re.sub(
            rf"({re.escape(safe_q)})",
            r"<u><b>\1</b></u>",
            safe_msg,
            flags=re.IGNORECASE,
        )

        text += (
            f"<b>{idx}.</b> {direction} (<code>{r.get('chat_id')}</code>)\n"
            f"🕒 <i>{time_str}</i>\n"
            f"💬 {highlighted}\n"
            "────────────────────\n"
        )

    await message.answer(text, parse_mode="HTML")


@router.message(Command("eslatma"))
@router.message(Command("javobsiz"))
async def cmd_unanswered_reminder(message: types.Message):
    """Javobsiz qolgan xabarlarni ko'rish: /eslatma [kun]."""
    parts = (message.text or "").split(maxsplit=1)
    days = Config.UNANSWERED_REMINDER_DAYS
    if len(parts) > 1 and parts[1].strip().isdigit():
        days = int(parts[1].strip())

    wait_msg = await message.answer(f"⏳ <i>{days} kundan beri javobsiz qolgan xabarlar tekshirilmoqda...</i>", parse_mode="HTML")
    unanswered = await db.get_unanswered_messages(days=days)

    if not unanswered:
        await wait_msg.edit_text(
            f"🎉 <b>Ajoyib!</b> So'nggi <b>{days} kun</b> ichida barcha xabarlarga javob berilgan.",
            parse_mode="HTML",
        )
        return

    text = (
        f"⏳ <b>JAVOB KUTILAYOTGAN XABARLAR ({days}+ KUN)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for idx, m in enumerate(unanswered, 1):
        name = m.get("sender_name") or m.get("sender_username") or m.get("chat_id")
        created = m.get("created_at") or ""
        msg_snippet = html.escape((m.get("text") or "")[:70])
        username_str = f" (@{html.escape(m['sender_username'])})" if m.get("sender_username") else ""

        text += (
            f"<b>{idx}.</b> 👤 <b>{html.escape(str(name))}</b>{username_str}\n"
            f"   💬 Chat ID: <code>{m.get('chat_id')}</code>\n"
            f"   🕒 Yozilgan: <i>{created}</i>\n"
            f"   📝 «{msg_snippet}»\n"
            "────────────────────\n"
        )

    text += (
        "\n💡 <i>Javob yozish uchun: <code>/yoz &lt;kontakt&gt; &lt;matn&gt;</code> "
        "yoki erkin matn (masalan: 'Rustamga ayt, bugun ko'rib chiqaman') deb yozing.</i>"
    )

    await wait_msg.edit_text(text, parse_mode="HTML")


@router.message(Command("taqvim"))
@router.message(Command("uchrashuv"))
async def cmd_calendar(message: types.Message):
    """Google Calendar-ga tadbir qo'shish: /taqvim <uchrashuv matni>."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "📅 <b>GOOGLE CALENDAR & TAQVIM INTEGRATSIYASI</b>\n\n"
            "Uchrashuv yoki tadbirni taqvimga kiritish uchun quyidagicha yozing:\n"
            "• <code>/taqvim Ertaga soat 16:00 da Karim bilan uchrashuv</code>\n"
            "• <code>/taqvim Dushanba kuni soat 10:00 da hisobot topshirish</code>\n"
            "• <code>/taqvim 29-sentyabr soat 18:00 da do'stlar bilan kafeda</code>\n\n"
            "💡 <i>Agent sana va vaqtni avtomatik hisoblab, Google Calendar havolasi "
            "va telefoningiz uchun .ics faylini tayyorlab beradi!</i>",
            parse_mode="HTML",
        )
        return

    query_text = parts[1].strip()
    wait_msg = await message.answer("⏳ <i>Sana va vaqt tahlil qilinmoqda...</i>", parse_mode="HTML")

    import calendar_service
    event_data = await calendar_service.parse_meeting_event(query_text)

    if not event_data:
        await wait_msg.edit_text(
            "⚠️ <b>Matndan sana yoki vaqtni aniqlab bo'lmadi.</b>\n"
            "Iltimos, aniqroq yozing: masalan <i>«Ertaga soat 15:00 da uchrashuv»</i>",
            parse_mode="HTML",
        )
        return

    title = event_data["title"]
    start_t = event_data["start_time"]
    end_t = event_data["end_time"]
    cal_url = event_data["google_calendar_url"]
    ics_file = event_data.get("ics_file_path")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Google Calendar-ga qo'shish", url=cal_url)]
        ]
    )

    resp_text = (
        "📅 <b>TAQVIM TADBIRI TAYYORLANDI!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Tadbir:</b> {html.escape(title)}\n"
        f"🕒 <b>Boshlanishi:</b> <code>{start_t}</code>\n"
        f"⏳ <b>Tugashi:</b> <code>{end_t}</code>\n"
        f"📝 <b>Tafsilot:</b> <i>{html.escape(event_data.get('details', ''))}</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <i>Quyidagi tugma orqali Google Calendar-ga 1 bosishda saqlang:</i>"
    )

    await wait_msg.delete()
    if ics_file and os.path.exists(ics_file):
        ics_input = FSInputFile(ics_file, filename=f"{title[:20]}.ics")
        await message.answer_document(
            document=ics_input,
            caption=resp_text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await message.answer(resp_text, reply_markup=kb, parse_mode="HTML")


@router.message(F.photo)
async def handle_photo_analysis(message: types.Message):
    """Foydalanuvchi rasm, chek yoki skrinshot yuborganda tahlil qilish."""
    bot = get_control_bot()
    wait_msg = await message.answer("🔍 <i>Rasm/chek tahlil qilinmoqda (Gemini Vision)...</i>", parse_mode="HTML")

    import document_analyzer
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    save_path = Config.MEDIA_DIR / f"analysis_{photo.file_id[:10]}.jpg"
    await bot.download_file(file_info.file_path, destination=save_path)

    analysis_res = await document_analyzer.analyze_document_or_image(
        file_path=str(save_path),
        user_instruction=message.caption,
    )

    await wait_msg.delete()
    await message.answer(analysis_res, parse_mode="HTML")


@router.message(F.document)
async def handle_document_analysis(message: types.Message):
    """Foydalanuvchi PDF yoki boshqa hujjat yuborganda tahlil qilish."""
    bot = get_control_bot()
    doc = message.document
    wait_msg = await message.answer(f"📑 <i>«{html.escape(doc.file_name or 'Hujjat')}» tahlil qilinmoqda (Gemini)...</i>", parse_mode="HTML")

    import document_analyzer
    file_info = await bot.get_file(doc.file_id)
    ext = os.path.splitext(doc.file_name or "")[1] or ".bin"
    save_path = Config.MEDIA_DIR / f"analysis_{doc.file_id[:10]}{ext}"
    await bot.download_file(file_info.file_path, destination=save_path)

    analysis_res = await document_analyzer.analyze_document_or_image(
        file_path=str(save_path),
        user_instruction=message.caption,
    )

    await wait_msg.delete()
    await message.answer(analysis_res, parse_mode="HTML")


@router.message(F.voice | F.audio)
async def handle_voice_analysis(message: types.Message):
    """Foydalanuvchi ovozli xabar (voice/audio) yuborganda matnga o'girish (STT) va tahlil qilish."""
    bot = get_control_bot()
    wait_msg = await message.answer("🎙 <i>Ovozli xabar tinglanmoqda va matnga o'girilmoqda...</i>", parse_mode="HTML")

    try:
        voice_obj = message.voice or message.audio
        file_info = await bot.get_file(voice_obj.file_id)
        ext = ".ogg" if message.voice else os.path.splitext(file_info.file_path or ".mp3")[1]
        save_path = Config.MEDIA_DIR / f"voice_{voice_obj.file_id[:10]}{ext}"
        await bot.download_file(file_info.file_path, destination=save_path)

        import ai
        transcription = await ai.transcribe_voice(str(save_path))

        if not transcription:
            await wait_msg.edit_text(
                "❌ <b>Ovozli xabarni matnga o'girib bo'lmadi.</b>\n\n"
                "Ovoz juda qisqa, past yoki shovqinli bo'lishi mumkin.\n"
                "<i>(Eslatma: Google Gemini yoki Whisper orqali avtomatik tahlil qilinadi)</i>",
                parse_mode="HTML",
            )
            return

        # Taqvim tekshiruvi (agar ovozda uchrashuv yoki sana eslatilgan bo'lsa)
        import calendar_service
        cal_data = await calendar_service.extract_event_and_calendar_link(transcription)

        kb_rows = []
        if cal_data and cal_data.get("calendar_url"):
            kb_rows.append([InlineKeyboardButton(text="📅 Google Calendar-ga qo'shish", url=cal_data["calendar_url"])])

        reply_markup = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None

        # Buyruq tekshiruvi (masalan: "Karimga ayt ertaga borolmayman")
        parsed = await ai.parse_and_compose_freeform(transcription)
        if parsed and parsed.get("is_command") and parsed.get("contact_target"):
            contact_target = parsed["contact_target"].strip()
            composed_text = parsed.get("composed_text") or transcription

            res_text = (
                "🎙 <b>OVOZLI XABAR MATNGA O'GIRILDI:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"«<i>{html.escape(transcription)}</i>»\n\n"
                f"🎯 <b>Aniqlangan buyruq:</b> <b>{html.escape(contact_target)}</b> ga xabar yuborish\n"
                f"📝 <b>Tayyorlangan xabar:</b>\n<i>«{html.escape(composed_text)}»</i>\n\n"
                "👇 Yuborish uchun buyruqdan foydalanishingiz mumkin:\n"
                f"<code>/yoz {html.escape(contact_target)} {html.escape(composed_text)}</code>"
            )
        else:
            res_text = (
                "🎙 <b>OVOZLI XABAR MATNGA O'GIRILDI:</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"«<i>{html.escape(transcription)}</i>»"
            )

        await wait_msg.delete()
        await message.answer(res_text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ovozli xabarni tahlil qilishda xatolik: {e}", exc_info=True)
        await wait_msg.edit_text(f"❌ Xatolik yuz berdi: {html.escape(str(e))}")



@router.message(F.text, StateFilter(None))
async def handle_freeform_instruction(message: types.Message):
    """
    Erkin matn buyrug'i: Masalan "Karimga ayt, ertaga borolmayman".
    Agent Claude orqali buyruqni tahlil qiladi, kontaktni topadi va
    foydalanuvchi uslubida tayyor xabar qoralamasini tasdiqlash uchun chiqaradi.
    """
    text = (message.text or "").strip()
    if text.startswith("/"):
        # Noma'lum buyruqlar
        await message.answer("❓ Noma'lum buyruq. Mavjud buyruqlarni ko'rish uchun: /yordam")
        return

    wait_msg = await message.answer("🧠 <i>Buyruq tahlil qilinmoqda va xabar qoralamasi tayyorlanmoqda...</i>", parse_mode="HTML")

    import ai
    parsed = await ai.parse_and_compose_freeform(text)

    if not parsed or not parsed.get("is_command") or not parsed.get("contact_target"):
        agent_reply = await ai.call_llm(
            prompt=text,
            system_prompt=(
                "Sen foydalanuvchining shaxsiy Telegram AI agentsan. "
                "Foydalanuvchiga uning AI agenti ekanligingni bildirgan holda, samimiy, lo'nda va foydali javob qaytar (1-2 gap). "
                "Faqat tayyor javob matnini qaytar, ortiqcha izohsiz."
            ),
            max_tokens=250,
        )
        if agent_reply:
            await wait_msg.edit_text(agent_reply)
        else:
            await wait_msg.edit_text("🤖 <i>Men sizning AI agentingizman. Xizmatingizdaman!</i>", parse_mode="HTML")
        return

    contact_target = parsed["contact_target"].strip()
    composed_text = parsed.get("composed_text") or text

    # Kontaktni bazadan qidirish
    contact_info = await db.find_contact(contact_target)

    if not contact_info:
        clean_target = contact_target.lstrip("@")
        if clean_target.lstrip("-").isdigit():
            chat_id = int(clean_target)
            contact_name = contact_target
        else:
            # Telethon orqali foydalanuvchining dialoglaridan qidirish
            import userbot
            tele_client = userbot.get_userbot_client()
            found_entity = None
            try:
                if contact_target.startswith("@"):
                    found_entity = await tele_client.get_entity(contact_target)
                else:
                    search_lower = contact_target.lower()
                    # O'zbekcha x/h va imlo variantlarini inobatga olish
                    search_variants = {search_lower}
                    if search_lower.startswith("x"):
                        search_variants.add("h" + search_lower[1:])
                    elif search_lower.startswith("h"):
                        search_variants.add("x" + search_lower[1:])

                    async for dialog in tele_client.iter_dialogs(limit=100):
                        d_name = (dialog.name or "").lower()
                        d_user = (getattr(dialog.entity, "username", "") or "").lower()
                        if any(var in d_name or (d_user and var in d_user) for var in search_variants):
                            found_entity = dialog.entity
                            break
            except Exception as se:
                logger.warning(f"Telethon dialoglaridan kontakt qidirishda xatolik: {se}")

            if found_entity:
                chat_id = found_entity.id
                f_first = getattr(found_entity, "first_name", "") or ""
                f_last = getattr(found_entity, "last_name", "") or ""
                contact_name = f"{f_first} {f_last}".strip() or getattr(found_entity, "title", contact_target)
            else:
                await wait_msg.edit_text(
                    f"⚠️ <b>«{html.escape(contact_target)}»</b> ismli kontakt bazada yoki Telegram dialoglaringizda topilmadi.\n\n"
                    f"💡 <b>Tavsiya:</b> Kontaktning aniq @username ini kiriting:\n"
                    f"<code>/yoz @username {html.escape(composed_text)}</code>",
                    parse_mode="HTML",
                )
                return
    else:
        chat_id = contact_info["chat_id"]
        contact_name = contact_info.get("contact_name") or contact_target

    # Qoralamani yaratish va adminga tasdiqlash uchun yuborish
    draft_id = await db.create_draft(
        chat_id=chat_id,
        draft_text=composed_text,
        contact_name=contact_name,
    )

    card_text = format_draft_message(
        contact_name=contact_name,
        chat_id=chat_id,
        draft_text=composed_text,
        draft_id=draft_id,
        note=f"Erkin buyruq: «{text}»",
    )

    await wait_msg.delete()
    sent_msg = await message.answer(
        card_text,
        reply_markup=get_draft_keyboard(draft_id),
        parse_mode="HTML",
    )
    await db.update_draft_control_message(draft_id, sent_msg.message_id)


# -------------------------------------------------------------------------
# INLINE TUGMALARNI QAYTA ISHLASH (CALLBACKS)
# -------------------------------------------------------------------------

@router.callback_query(F.data.startswith("draft:send:"))
async def callback_draft_send(query: CallbackQuery):
    """[✅ Yuborish] tugmasi bosilganda."""
    draft_id_str = query.data.split(":")[-1]
    if not draft_id_str.isdigit():
        await query.answer("Noto'g'ri qoralama ID si!", show_alert=True)
        return

    draft_id = int(draft_id_str)
    draft = await db.get_draft(draft_id)

    if not draft:
        await query.answer("Qoralama topilmadi!", show_alert=True)
        return

    if draft["status"] != "pending":
        await query.answer(
            f"Bu qoralama allaqachon '{draft['status']}' holatida!", show_alert=True
        )
        return

    # Userbot orqali xabarni jo'natish
    import userbot
    chat_id = draft["chat_id"]
    text = draft["draft_text"]
    reply_to = draft.get("reply_to_msg_id")

    success = await userbot.send_userbot_message(chat_id=chat_id, text=text, reply_to=reply_to)

    if success:
        await db.update_draft_status(draft_id, "sent")
        await query.answer("✅ Xabar profilingizdan muvaffaqiyatli yuborildi!")

        # Boshqaruv xabarini yangilash
        safe_name = html.escape(str(draft.get("contact_name") or chat_id))
        safe_text = html.escape(str(text))
        now_str = datetime.now().strftime("%H:%M:%S, %d.%m.%Y")

        updated_card = (
            "✅ <b>XABAR YUBORILDI!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Kontakt:</b> {safe_name}\n"
            f"💬 <b>Chat ID:</b> <code>{chat_id}</code>\n"
            f"🆔 <b>Qoralama ID:</b> <code>#{draft_id}</code>\n"
            f"🕒 <b>Yuborilgan vaqt:</b> <code>{now_str}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>Yuborilgan matn:</b>\n"
            f"<i>«{safe_text}»</i>"
        )
        try:
            await query.message.edit_text(updated_card, parse_mode="HTML", reply_markup=None)
        except Exception as e:
            logger.warning(f"Xabarni tahrirlashda ogohlantirish: {e}")
    else:
        await query.answer(
            "❌ Userbot orqali yuborishda xatolik! Userbot ulanganligini tekshiring.",
            show_alert=True,
        )


@router.callback_query(F.data.startswith("draft:edit:"))
async def callback_draft_edit(query: CallbackQuery, state: FSMContext):
    """[✏️ Tahrirlash] tugmasi bosilganda."""
    draft_id_str = query.data.split(":")[-1]
    if not draft_id_str.isdigit():
        await query.answer("Noto'g'ri qoralama ID si!", show_alert=True)
        return

    draft_id = int(draft_id_str)
    draft = await db.get_draft(draft_id)

    if not draft:
        await query.answer("Qoralama topilmadi!", show_alert=True)
        return

    if draft["status"] != "pending":
        await query.answer("Faqat kutilayotgan qoralamani tahrirlash mumkin!", show_alert=True)
        return

    # FSM holatiga o'tish
    await state.set_state(EditDraftState.waiting_for_new_text)
    await state.update_data(
        draft_id=draft_id,
        chat_id=draft["chat_id"],
        contact_name=draft.get("contact_name"),
        original_msg_id=query.message.message_id,
    )

    await query.answer()
    safe_text = html.escape(str(draft["draft_text"]))
    await query.message.reply(
        "✏️ <b>Qoralama matnini tahrirlash</b>\n\n"
        "Eski matn:\n"
        f"<i>«{safe_text}»</i>\n\n"
        "✍️ <i>Iltimos, yangi tahrirlangan matnni yuboring (bekor qilish uchun /cancel deb yozing):</i>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("draft:cancel:"))
async def callback_draft_cancel(query: CallbackQuery):
    """[❌ Bekor qilish] tugmasi bosilganda."""
    draft_id_str = query.data.split(":")[-1]
    if not draft_id_str.isdigit():
        await query.answer("Noto'g'ri qoralama ID si!", show_alert=True)
        return

    draft_id = int(draft_id_str)
    draft = await db.get_draft(draft_id)

    if not draft:
        await query.answer("Qoralama topilmadi!", show_alert=True)
        return

    await db.update_draft_status(draft_id, "cancelled")
    await query.answer("❌ Qoralama bekor qilindi.")

    safe_name = html.escape(str(draft.get("contact_name") or draft["chat_id"]))
    safe_text = html.escape(str(draft["draft_text"]))

    cancelled_card = (
        "❌ <b>QORALAMA BEKOR QILINDI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Kontakt:</b> {safe_name}\n"
        f"💬 <b>Chat ID:</b> <code>{draft['chat_id']}</code>\n"
        f"🆔 <b>Qoralama ID:</b> <code>#{draft_id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<s>{safe_text}</s>"
    )
    try:
        await query.message.edit_text(cancelled_card, parse_mode="HTML", reply_markup=None)
    except Exception as e:
        logger.warning(f"Xabarni tahrirlashda ogohlantirish: {e}")


@router.message(EditDraftState.waiting_for_new_text)
async def process_new_draft_text(message: types.Message, state: FSMContext):
    """Tahrirlangan yangi matn kelganda qoralamani yangilash."""
    new_text = message.text or ""
    if not new_text.strip():
        await message.answer("Iltimos, bo'sh bo'lmagan matn kiriting:")
        return

    data = await state.get_data()
    draft_id = data.get("draft_id")
    chat_id = data.get("chat_id")
    contact_name = data.get("contact_name") or "Noma'lum"

    await db.update_draft_text(draft_id, new_text)
    await state.clear()

    # Yangilangan qoralama kartasini va tugmalarni yuborish
    updated_card = format_draft_message(
        contact_name=contact_name,
        chat_id=chat_id,
        draft_text=new_text,
        draft_id=draft_id,
    )
    await message.answer(
        f"✅ <b>Qoralama yangilandi!</b>\n\n{updated_card}",
        reply_markup=get_draft_keyboard(draft_id),
        parse_mode="HTML",
    )


# -------------------------------------------------------------------------
# YORDAMCHI FUNKSIYALAR
# -------------------------------------------------------------------------

async def send_draft_to_admin(
    chat_id: int,
    draft_text: str,
    contact_name: Optional[str] = None,
    reply_to_msg_id: Optional[int] = None,
    note: Optional[str] = None,
    incoming_text: Optional[str] = None,
) -> Optional[int]:
    """
    Yangi javob qoralamasini bazada yaratadi va boshqaruv botida
    adminga tasdiqlash tugmalari bilan yuboradi.
    """
    bot = get_control_bot()
    if not bot or not Config.ADMIN_USER_ID:
        logger.warning("Boshqaruv boti sozlanmagan, qoralama yuborilmadi.")
        return None

    draft_id = await db.create_draft(
        chat_id=chat_id,
        draft_text=draft_text,
        contact_name=contact_name,
        reply_to_msg_id=reply_to_msg_id,
    )

    card_text = format_draft_message(
        contact_name=contact_name or str(chat_id),
        chat_id=chat_id,
        draft_text=draft_text,
        draft_id=draft_id,
        note=note,
        incoming_text=incoming_text,
    )

    cal_url = None
    try:
        check_str = f"{incoming_text or ''} {draft_text}".lower()
        if any(w in check_str for w in ["ertaga", "soat", "uchrash", "dars", "shanba", "yakshanba", "dushanba", "seshanba", "chorshanba", "payshanba", "juma"]):
            import calendar_service
            ev = await calendar_service.parse_meeting_event(f"{incoming_text or ''} {draft_text}")
            if ev:
                cal_url = ev.get("google_calendar_url")
    except Exception as ce:
        logger.debug(f"Calendar check in draft error: {ce}")

    try:
        sent = await bot.send_message(
            chat_id=Config.ADMIN_USER_ID,
            text=card_text,
            reply_markup=get_draft_keyboard(draft_id, calendar_url=cal_url),
            parse_mode="HTML",
        )
        await db.update_draft_control_message(draft_id, sent.message_id)
        return draft_id
    except Exception as e:
        logger.error(f"Adminga qoralama yuborishda xatolik: {e}", exc_info=True)
        return None


async def send_safety_alert(
    chat_id: int,
    contact_name: Optional[str],
    incoming_text: str,
    category: str,
    reason: str,
    draft_id: Optional[int] = None,
    draft_text: Optional[str] = None,
) -> bool:
    """
    Xavfli yoki nozik mavzu (pul, karta, parol, tibbiyot, shartnoma, huquqiy)
    aniqlanganda adminga yuqori darajadagi ogohlantirish yuborish.
    Agent bu xabarga hech qachon o'zi javob bermaydi.
    """
    bot = get_control_bot()
    if not bot or not Config.ADMIN_USER_ID:
        return False

    safe_name = html.escape(str(contact_name or chat_id))
    safe_incoming = html.escape(str(incoming_text))
    safe_reason = html.escape(str(reason))
    now_str = datetime.now().strftime("%H:%M:%S, %d.%m.%Y")

    alert_text = (
        "🚨 <b>XAVFSIZLIK FILTRI OGOHLANTIRISHI!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Kontakt:</b> {safe_name}\n"
        f"💬 <b>Chat ID:</b> <code>{chat_id}</code>\n"
        f"🕒 <b>Vaqt:</b> <code>{now_str}</code>\n"
        f"🏷 <b>Toifa:</b> <code>{category.upper()}</code>\n"
        f"⚠️ <b>Sabab:</b> <i>{safe_reason}</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>Kelgan xabar:</b>\n"
        f"<i>«{safe_incoming}»</i>\n\n"
        "🛡 <b>Agent harakati:</b> <i>Xavfsizlik qoidalariga ko'ra agent ushbu xabarga mustaqil javob bermadi!</i>"
    )

    reply_markup = None
    if draft_id and draft_text:
        safe_draft = html.escape(str(draft_text))
        alert_text += (
            "\n\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>Taklif etilayotgan ehtiyotkor qoralama:</b>\n"
            f"<i>«{safe_draft}»</i>\n\n"
            "<i>Tugmalar orqali tekshirib tasdiqlang yoki bekor qiling:</i>"
        )
        reply_markup = get_draft_keyboard(draft_id)

    try:
        sent = await bot.send_message(
            chat_id=Config.ADMIN_USER_ID,
            text=alert_text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        if draft_id:
            await db.update_draft_control_message(draft_id, sent.message_id)
        return True
    except Exception as e:
        logger.error(f"Xavfsizlik ogohlantirishini yuborishda xatolik: {e}")
        return False


async def notify_auto_reply(
    chat_id: int,
    contact_name: str,
    incoming_text: str,
    reply_text: str,
    mode: str,
) -> bool:
    """Agent avtomatik javob qaytarganda adminga bildirishnoma yuborish."""
    bot = get_control_bot()
    if not bot or not Config.ADMIN_USER_ID:
        return False

    safe_name = html.escape(str(contact_name))
    safe_incoming = html.escape(str(incoming_text))
    safe_reply = html.escape(str(reply_text))
    now_str = datetime.now().strftime("%H:%M:%S")

    msg = (
        f"🤖 <b>AVTO-JAVOB YUBORILDI</b> (Rejim: <code>{mode}</code>)\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Kontakt:</b> {safe_name} (<code>{chat_id}</code>)\n"
        f"🕒 <b>Vaqt:</b> <code>{now_str}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>Kelgan xabar:</b>\n"
        f"<i>«{safe_incoming}»</i>\n\n"
        f"📤 <b>Yuborilgan javob:</b>\n"
        f"<b>«{safe_reply}»</b>"
    )
    try:
        await bot.send_message(
            chat_id=Config.ADMIN_USER_ID,
            text=msg,
            parse_mode="HTML",
        )
        return True
    except Exception as e:
        logger.error(f"Avto-javob bildirishnomasini yuborishda xatolik: {e}")
        return False


# -------------------------------------------------------------------------
# OMMABOP / NOTANISH FOYDALANUVCHILAR UCHUN AI AGENT JAVOBI
# -------------------------------------------------------------------------

@public_router.message(CommandStart())
async def public_start(message: types.Message):
    """Boshqa foydalanuvchilar botga /start bosganda."""
    await message.answer(
        "👋 <b>Assalomu alaykum!</b>\n\n"
        "Men profil egasining shaxsiy sun'iy intellekt (AI) agentiman 🤖.\n"
        "Xabarlaringizga o'zim javob bera olaman va barcha ma'lumotlarni profil egasiga yetkazaman.\n\n"
        "Qanday xabar yoki savolingiz bor?",
        parse_mode="HTML",
    )


@public_router.message(F.text)
async def public_text_message(message: types.Message):
    """Boshqa foydalanuvchilar botga yozganda AI agent o'zi javob beradi."""
    user_text = (message.text or "").strip()
    sender_name = message.from_user.full_name if message.from_user else "Foydalanuvchi"
    username = f"@{message.from_user.username}" if message.from_user and message.from_user.username else f"ID: {message.from_user.id}"

    wait_msg = await message.answer("💬 <i>AI agent javob tayyorlamoqda...</i>", parse_mode="HTML")

    import ai
    agent_reply = await ai.call_llm(
        prompt=user_text,
        system_prompt=(
            "Sen Telegram profil egasining shaxsiy AI agentsan. "
            "Suhbatdoshga o'zingning profil egasining AI agenti ekanligingni aytib, xushmuomala, qisqa va lo'nda javob ber (1-2 gap). "
            "Profil egasi hozir bandligi sababli xabarni qabul qilganingni va o'ziga yetkazishingni ma'lum qil. "
            "Faqat tayyor javob matnini qaytar, ortiqcha sarlavhasiz."
        ),
        max_tokens=250,
    )

    if not agent_reply:
        agent_reply = "Salom! Men profil egasining AI agentiman. U hozir band bo'lgani sababli xabaringizni qabul qildim va o'ziga yetkazib qo'yaman."

    await wait_msg.edit_text(agent_reply)

    # Adminga yangi xabar haqida bildirishnoma
    await notify_admin(
        f"📩 <b>Botga foydalanuvchidan yangi xabar keldi!</b>\n"
        f"👤 <b>Kimdan:</b> {html.escape(sender_name)} ({html.escape(username)})\n"
        f"💬 <b>Xabar:</b> «{html.escape(user_text)}»\n"
        f"🤖 <b>AI agent javobi:</b> «{html.escape(agent_reply)}»"
    )


def get_control_bot() -> Optional[Bot]:
    """Bot instansiyasini qaytarish."""
    global _bot
    if _bot is None and Config.BOT_TOKEN:
        _bot = Bot(token=Config.BOT_TOKEN)
    return _bot


def get_control_dispatcher() -> Dispatcher:
    """Dispatcher instansiyasini qaytarish (FSM xotirasi bilan)."""
    global _dp
    if _dp is None:
        storage = MemoryStorage()
        _dp = Dispatcher(storage=storage)
        _dp.include_router(router)
        _dp.include_router(public_router)
    return _dp


def format_deleted_message_text(info: Dict[str, Any]) -> str:
    """O'chirilgan xabar haqidagi ma'lumotni chiroyli matn holatiga keltirish."""
    sender_name = html.escape(str(info.get("sender_name") or "Noma'lum"))
    username = f" (@{html.escape(str(info['sender_username']))})" if info.get("sender_username") else ""
    sender_id = info.get("sender_id") or "Noma'lum"
    chat_id = info.get("chat_id") or "Noma'lum"
    created_at = info.get("created_at") or "Noma'lum"
    deleted_at = info.get("deleted_at") or "Hozirgina"
    raw_text = info.get("original_text") or info.get("text")
    text = html.escape(str(raw_text)) if raw_text else "<i>[Matn yo'q - faqat media fayl]</i>"

    direction = "📤 Chiquvchi (o'zingiz)" if info.get("is_outgoing") else "📥 Kiruvchi"

    alert_text = (
        "🗑 <b>O'CHIRILGAN XABAR ANIQLANDI!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🧭 <b>Turi:</b> {direction}\n"
        f"👤 <b>Kimdan:</b> {sender_name}{username}\n"
        f"🆔 <b>Sender ID:</b> <code>{sender_id}</code>\n"
        f"💬 <b>Chat ID:</b> <code>{chat_id}</code>\n"
        f"🕒 <b>Yozilgan vaqti:</b> <code>{created_at}</code>\n"
        f"❌ <b>O'chirilgan vaqti:</b> <code>{deleted_at}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Xabar matni:</b>\n{text}"
    )
    return alert_text


async def send_deleted_message_alert(info: Dict[str, Any]) -> bool:
    """
    O'chirilgan xabarni boshqaruv boti orqali adminga yuborish.
    Agar media fayl bo'lsa, faylni ham ilova qiladi.
    """
    bot = get_control_bot()
    if not bot or not Config.ADMIN_USER_ID:
        logger.warning(
            "Boshqaruv boti tokeni yoki ADMIN_USER_ID kiritilmagan. Xabarni yuborib bo'lmadi."
        )
        return False

    alert_text = format_deleted_message_text(info)
    media_path = info.get("media_path")
    media_type = info.get("media_type")

    try:
        if media_path and os.path.exists(media_path):
            file_input = FSInputFile(media_path)
            caption = alert_text if len(alert_text) <= 1024 else None

            if caption is None:
                await bot.send_message(
                    chat_id=Config.ADMIN_USER_ID,
                    text=alert_text,
                    parse_mode="HTML",
                )

            if media_type == "photo":
                await bot.send_photo(
                    chat_id=Config.ADMIN_USER_ID,
                    photo=file_input,
                    caption=caption,
                    parse_mode="HTML",
                )
            elif media_type == "voice":
                await bot.send_voice(
                    chat_id=Config.ADMIN_USER_ID,
                    voice=file_input,
                    caption=caption,
                    parse_mode="HTML",
                )
            elif media_type == "audio":
                await bot.send_audio(
                    chat_id=Config.ADMIN_USER_ID,
                    audio=file_input,
                    caption=caption,
                    parse_mode="HTML",
                )
            elif media_type == "video":
                await bot.send_video(
                    chat_id=Config.ADMIN_USER_ID,
                    video=file_input,
                    caption=caption,
                    parse_mode="HTML",
                )
            else:
                await bot.send_document(
                    chat_id=Config.ADMIN_USER_ID,
                    document=file_input,
                    caption=caption,
                    parse_mode="HTML",
                )
        else:
            await bot.send_message(
                chat_id=Config.ADMIN_USER_ID,
                text=alert_text,
                parse_mode="HTML",
            )
        logger.info(f"O'chirilgan xabar haqida adminga ({Config.ADMIN_USER_ID}) xabarnoma yuborildi.")
        return True
    except TelegramAPIError as te:
        logger.error(f"O'chirilgan xabarni Telegram Bot orqali yuborishda xatolik: {te}")
        return False
    except Exception as e:
        logger.error(f"Xabarnoma yuborishda kutilmagan xatolik: {e}", exc_info=True)
        return False


async def notify_admin(text: str) -> bool:
    """Adminga oddiy matnli xabar yuborish."""
    bot = get_control_bot()
    if not bot or not Config.ADMIN_USER_ID:
        return False
    try:
        await bot.send_message(chat_id=Config.ADMIN_USER_ID, text=text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Adminga xabar yuborishda xatolik: {e}")
        return False
