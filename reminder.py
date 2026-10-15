import asyncio
import html
from config import Config, logger
import db
import control_bot


async def check_and_send_unanswered_reminders():
    """
    N kundan beri javobsiz qolgan xabarlarni tekshirish va
    boshqaruv boti orqali adminga chiroyli eslatma yo'llash.
    """
    try:
        days = Config.UNANSWERED_REMINDER_DAYS
        unanswered = await db.get_unanswered_messages(days=days)
        if not unanswered:
            return

        bot = control_bot.get_control_bot()
        if not bot or not Config.ADMIN_USER_ID:
            return

        text = (
            f"🔔 <b>KUNLIK ESLATMA: JAVOBSIZ XABARLAR ({days}+ KUN)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Sizda <b>{len(unanswered)} ta</b> kontaktning javobsiz kutib turgan xabari mavjud:\n\n"
        )
        for idx, m in enumerate(unanswered[:5], 1):
            name = html.escape(str(m.get("sender_name") or m.get("sender_username") or m.get("chat_id")))
            snippet = html.escape((m.get("text") or "")[:60])
            text += f"<b>{idx}.</b> 👤 <b>{name}</b>: <i>«{snippet}»</i>\n"

        if len(unanswered) > 5:
            text += f"\n<i>...va yana {len(unanswered) - 5} ta kontakt (/eslatma orqali ko'ring)</i>\n"

        text += (
            "\n━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Javob yozish uchun: «Karimga ayt, ko'rib chiqdim» deb yozing "
            "yoki <code>/yoz @kontakt matn</code> dan foydalaning.</i>"
        )

        await bot.send_message(chat_id=Config.ADMIN_USER_ID, text=text, parse_mode="HTML")
        logger.info(f"{len(unanswered)} ta javobsiz xabar haqida adminga eslatma yuborildi.")
    except Exception as e:
        logger.error(f"Javobsiz xabarlar eslatmasini yuborishda xatolik: {e}")


async def start_reminder_scheduler(interval_hours: int = 12):
    """
    Orqa fonda har N soatda (standart 12 soatda bir) javobsiz
    xabarlarni avtomatik tekshirib boruvchi tsikl.
    """
    logger.info(f"Javobsiz xabarlar eslatuvchi xizmati ishga tushdi (Har {interval_hours} soatda tekshiradi).")
    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            await check_and_send_unanswered_reminders()
        except asyncio.CancelledError:
            logger.info("Javobsiz xabarlar eslatuvchi xizmati to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Eslatmalar xizmatida xatolik: {e}")
            await asyncio.sleep(60)
