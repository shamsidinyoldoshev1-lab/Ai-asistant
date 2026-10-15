import aiosqlite
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any, AsyncIterator
from datetime import datetime, timedelta
from config import Config, logger

DB_PATH = Config.DATABASE_PATH


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Ma'lumotlar bazasi bilan xavfsiz ulanish hosil qilish uchun kontekst menejeri."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    """Baza jadvallarini yaratish va indekslarni sozlash."""
    async with get_db() as db:
        # Xabarlar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                sender_name TEXT,
                sender_username TEXT,
                text TEXT,
                media_path TEXT,
                media_type TEXT,
                is_outgoing INTEGER DEFAULT 0,
                is_deleted INTEGER DEFAULT 0,
                is_edited INTEGER DEFAULT 0,
                original_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP,
                edited_at TIMESTAMP
            )
        """)

        # Indekslar (tezkor qidiruv va tekshirish uchun)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_msg 
            ON messages(chat_id, telegram_message_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_created 
            ON messages(created_at)
        """)

        # Kontaktlar sozlamalari jadvali (rejimlar va ohang)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contact_settings (
                chat_id INTEGER PRIMARY KEY,
                contact_name TEXT,
                contact_username TEXT,
                mode TEXT DEFAULT 'tasdiq',
                contact_type TEXT DEFAULT 'notanish',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tizim sozlamalari jadvali (global pauza, rejimlar)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Qoralamalar jadvali (tasdiq kutayotgan javoblar)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                contact_name TEXT,
                reply_to_msg_id INTEGER,
                draft_text TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                control_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()
    logger.info("Ma'lumotlar bazasi (SQLite) muvaffaqiyatli ishga tushirildi.")


async def save_message(
    telegram_message_id: int,
    chat_id: int,
    sender_id: int,
    sender_name: Optional[str] = None,
    sender_username: Optional[str] = None,
    text: Optional[str] = None,
    media_path: Optional[str] = None,
    media_type: Optional[str] = None,
    is_outgoing: bool = False,
) -> int:
    """Yangi xabarni bazaga saqlash."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO messages (
                telegram_message_id,
                chat_id,
                sender_id,
                sender_name,
                sender_username,
                text,
                media_path,
                media_type,
                is_outgoing
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_message_id,
                chat_id,
                sender_id,
                sender_name,
                sender_username,
                text,
                media_path,
                media_type,
                1 if is_outgoing else 0,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_message(chat_id: int, telegram_message_id: int) -> Optional[Dict[str, Any]]:
    """Xabarni chat_id va telegram_message_id bo'yicha olish."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT * FROM messages 
            WHERE chat_id = ? AND telegram_message_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (chat_id, telegram_message_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def mark_message_deleted(telegram_message_id: int, chat_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Xabarni o'chirilgan deb belgilash va uning asl ma'lumotlarini qaytarish."""
    async with get_db() as db:
        if chat_id is not None:
            query = """
                SELECT * FROM messages 
                WHERE chat_id = ? AND telegram_message_id = ?
                ORDER BY id DESC LIMIT 1
            """
            params = (chat_id, telegram_message_id)
        else:
            query = """
                SELECT * FROM messages 
                WHERE telegram_message_id = ?
                ORDER BY id DESC LIMIT 1
            """
            params = (telegram_message_id,)

        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            msg_data = dict(row)

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        record_id = msg_data["id"]
        await db.execute(
            """
            UPDATE messages 
            SET is_deleted = 1, deleted_at = ?
            WHERE id = ?
            """,
            (now, record_id),
        )
        await db.commit()
        msg_data["deleted_at"] = now
        msg_data["is_deleted"] = 1
        return msg_data


async def update_message_text(
    telegram_message_id: int,
    new_text: str,
    chat_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Tahrirlangan xabarning eski va yangi matnini yangilash."""
    async with get_db() as db:
        if chat_id is not None:
            query = """
                SELECT * FROM messages 
                WHERE chat_id = ? AND telegram_message_id = ?
                ORDER BY id DESC LIMIT 1
            """
            params = (chat_id, telegram_message_id)
        else:
            query = """
                SELECT * FROM messages 
                WHERE telegram_message_id = ?
                ORDER BY id DESC LIMIT 1
            """
            params = (telegram_message_id,)

        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            old_data = dict(row)

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        original = old_data.get("original_text") or old_data.get("text")
        record_id = old_data["id"]
        await db.execute(
            """
            UPDATE messages 
            SET is_edited = 1,
                original_text = ?,
                text = ?,
                edited_at = ?
            WHERE id = ?
            """,
            (original, new_text, now, record_id),
        )
        await db.commit()
        return old_data


async def get_and_delete_old_messages(days: int = 30) -> List[Dict[str, Any]]:
    """N kundan eski xabarlarni bazadan olish va o'chirish."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        async with db.execute(
            "SELECT id, media_path FROM messages WHERE created_at < ?",
            (cutoff_str,),
        ) as cursor:
            rows = await cursor.fetchall()
            old_messages = [dict(r) for r in rows]

        if old_messages:
            await db.execute(
                "DELETE FROM messages WHERE created_at < ?",
                (cutoff_str,),
            )
            await db.commit()
        return old_messages


async def get_contact_settings(chat_id: int) -> Dict[str, Any]:
    """Kontakt parametrlarini olish (rejim, ohang). Standart rejim: 'tasdiq'."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM contact_settings WHERE chat_id = ?",
            (chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return {
                "chat_id": chat_id,
                "contact_name": None,
                "contact_username": None,
                "mode": getattr(Config, "DEFAULT_MODE", "avto"),
                "contact_type": "notanish",
            }


async def set_contact_mode(
    chat_id: int,
    mode: str,
    contact_name: Optional[str] = None,
    contact_username: Optional[str] = None,
    contact_type: Optional[str] = None,
) -> None:
    """Kontakt rejimini belgilash yoki yangilash."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO contact_settings (chat_id, contact_name, contact_username, mode, contact_type, updated_at)
            VALUES (?, ?, ?, ?, COALESCE(?, 'notanish'), ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                mode = excluded.mode,
                contact_name = COALESCE(excluded.contact_name, contact_settings.contact_name),
                contact_username = COALESCE(excluded.contact_username, contact_settings.contact_username),
                contact_type = COALESCE(excluded.contact_type, contact_settings.contact_type),
                updated_at = excluded.updated_at
            """,
            (chat_id, contact_name, contact_username, mode, contact_type, now),
        )
        await db.commit()


async def set_contact_type(
    chat_id: int,
    contact_type: str,
    contact_name: Optional[str] = None,
    contact_username: Optional[str] = None,
) -> None:
    """Kontakt turini/ohangini belgilash ('oila', 'ish', 'notanish')."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO contact_settings (chat_id, contact_name, contact_username, mode, contact_type, updated_at)
            VALUES (?, ?, ?, 'tasdiq', ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                contact_type = excluded.contact_type,
                contact_name = COALESCE(excluded.contact_name, contact_settings.contact_name),
                contact_username = COALESCE(excluded.contact_username, contact_settings.contact_username),
                updated_at = excluded.updated_at
            """,
            (chat_id, contact_name, contact_username, contact_type, now),
        )
        await db.commit()


async def get_last_messages(chat_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """Kontakt bilan oxirgi N ta xabarni olish (AI konteksti uchun)."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT * FROM (
                SELECT * FROM messages 
                WHERE chat_id = ? AND text IS NOT NULL AND text != ''
                ORDER BY id DESC 
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (chat_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# -------------------------------------------------------------------------
# STAGE 3: Tizim sozlamalari va pauza boshqaruvi
# -------------------------------------------------------------------------

async def get_setting(key: str, default: str = "") -> str:
    """Tizim sozlamasini olish."""
    async with get_db() as db:
        async with db.execute("SELECT value FROM system_settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row["value"]
            return default


async def set_setting(key: str, value: str) -> None:
    """Tizim sozlamasini saqlash yoki yangilash."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO system_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await db.commit()


async def is_global_paused() -> bool:
    """Agent global pauza holatidami yoki yo'qligini tekshirish."""
    val = await get_setting("is_paused", "0")
    return val == "1"


async def set_global_paused(paused: bool) -> None:
    """Agentni global pauzaga qo'yish yoki davom ettirish."""
    await set_setting("is_paused", "1" if paused else "0")


# -------------------------------------------------------------------------
# STAGE 3: Qoralamalar (Drafts) bilan ishlash
# -------------------------------------------------------------------------

async def create_draft(
    chat_id: int,
    draft_text: str,
    contact_name: Optional[str] = None,
    reply_to_msg_id: Optional[int] = None,
) -> int:
    """Yangi javob qoralamasini bazada yaratish."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO drafts (chat_id, contact_name, reply_to_msg_id, draft_text, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (chat_id, contact_name, reply_to_msg_id, draft_text),
        )
        await db.commit()
        return cursor.lastrowid


async def get_draft(draft_id: int) -> Optional[Dict[str, Any]]:
    """ID bo'yicha qoralama ma'lumotlarini olish."""
    async with get_db() as db:
        async with db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def update_draft_text(draft_id: int, new_text: str) -> None:
    """Qoralama matnini tahrirlash."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        await db.execute(
            "UPDATE drafts SET draft_text = ?, updated_at = ? WHERE id = ?",
            (new_text, now, draft_id),
        )
        await db.commit()


async def update_draft_status(draft_id: int, status: str) -> None:
    """Qoralama holatini o'zgartirish ('pending', 'sent', 'cancelled')."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        await db.execute(
            "UPDATE drafts SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, draft_id),
        )
        await db.commit()


async def update_draft_control_message(draft_id: int, control_message_id: int) -> None:
    """Boshqaruv botidagi xabar ID sini saqlash."""
    async with get_db() as db:
        await db.execute(
            "UPDATE drafts SET control_message_id = ? WHERE id = ?",
            (control_message_id, draft_id),
        )
        await db.commit()


# -------------------------------------------------------------------------
# STAGE 3: Kontaktlarni qidirish va statistika
# -------------------------------------------------------------------------

async def find_contact(query: str) -> Optional[Dict[str, Any]]:
    """
    Kontaktni username, ID yoki ism bo'yicha topish.
    Avval contact_settings dan, topilmasa messages jadvalidan qidiradi.
    """
    clean_query = query.strip().lstrip("@")
    async with get_db() as db:
        # 1. Agar raqam bo'lsa chat_id bo'yicha
        if clean_query.lstrip("-").isdigit():
            target_id = int(clean_query)
            async with db.execute(
                "SELECT * FROM contact_settings WHERE chat_id = ?", (target_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

            # messages jadvalidan tekshirish
            async with db.execute(
                "SELECT chat_id, sender_name as contact_name, sender_username as contact_username "
                "FROM messages WHERE chat_id = ? OR sender_id = ? ORDER BY id DESC LIMIT 1",
                (target_id, target_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    d = dict(row)
                    d["mode"] = "tasdiq"
                    return d

        # 2. Username bo'yicha qidiruv
        async with db.execute(
            "SELECT * FROM contact_settings WHERE LOWER(contact_username) = LOWER(?)",
            (clean_query,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        async with db.execute(
            "SELECT chat_id, sender_name as contact_name, sender_username as contact_username "
            "FROM messages WHERE LOWER(sender_username) = LOWER(?) ORDER BY id DESC LIMIT 1",
            (clean_query,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d["mode"] = "tasdiq"
                return d

        # 3. Ism bo'yicha qidiruv (LIKE)
        like_query = f"%{clean_query}%"
        async with db.execute(
            "SELECT * FROM contact_settings WHERE LOWER(contact_name) LIKE LOWER(?) ORDER BY updated_at DESC LIMIT 1",
            (like_query,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        async with db.execute(
            "SELECT chat_id, sender_name as contact_name, sender_username as contact_username "
            "FROM messages WHERE LOWER(sender_name) LIKE LOWER(?) ORDER BY id DESC LIMIT 1",
            (like_query,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d["mode"] = "tasdiq"
                return d

    return None


async def get_all_contact_settings() -> List[Dict[str, Any]]:
    """Barcha saqlangan kontakt sozlamalarini olish."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM contact_settings ORDER BY updated_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_database_stats() -> Dict[str, Any]:
    """Baza va xizmat bo'yicha umumiy statistikani olish."""
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) as cnt FROM messages") as c:
            total_msgs = (await c.fetchone())["cnt"]
        async with db.execute("SELECT COUNT(*) as cnt FROM messages WHERE is_deleted = 1") as c:
            deleted_msgs = (await c.fetchone())["cnt"]
        async with db.execute("SELECT COUNT(*) as cnt FROM messages WHERE is_edited = 1") as c:
            edited_msgs = (await c.fetchone())["cnt"]
        async with db.execute("SELECT COUNT(*) as cnt FROM messages WHERE media_path IS NOT NULL") as c:
            media_msgs = (await c.fetchone())["cnt"]
        async with db.execute("SELECT COUNT(*) as cnt FROM drafts WHERE status = 'pending'") as c:
            pending_drafts = (await c.fetchone())["cnt"]
        async with db.execute("SELECT COUNT(*) as cnt FROM contact_settings") as c:
            custom_contacts = (await c.fetchone())["cnt"]

        return {
            "total_messages": total_msgs,
            "deleted_messages": deleted_msgs,
            "edited_messages": edited_msgs,
            "media_messages": media_msgs,
            "pending_drafts": pending_drafts,
            "custom_contacts": custom_contacts,
        }


# -------------------------------------------------------------------------
# STAGE 6: Qidiruv, xulosa, eslatmalar va ovozli xabarlar
# -------------------------------------------------------------------------

async def search_messages(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Saqlangan xabarlar ichidan so'z yoki ibora bo'yicha qidirish."""
    like_pattern = f"%{query.strip()}%"
    async with get_db() as db:
        async with db.execute(
            """
            SELECT * FROM messages 
            WHERE (text LIKE ? OR original_text LIKE ?)
            ORDER BY created_at DESC 
            LIMIT ?
            """,
            (like_pattern, like_pattern, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_today_messages() -> List[Dict[str, Any]]:
    """Bugungi (so'nggi 24 soatdagi) barcha xabarlarni olish (xulosa uchun)."""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        async with db.execute(
            """
            SELECT * FROM messages 
            WHERE created_at >= ? AND text IS NOT NULL AND text != ''
            ORDER BY chat_id, created_at ASC
            """,
            (cutoff_str,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_unanswered_messages(days: int = 3) -> List[Dict[str, Any]]:
    """
    N kundan beri javobsiz kutib turgan kiruvchi xabarlarni aniqlash.
    Faqat eng oxirgi kiruvchi xabari javobsiz qolgan kontaktlarni qaytaradi.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        query = """
            SELECT m.* FROM messages m
            WHERE m.is_outgoing = 0
              AND m.is_deleted = 0
              AND m.created_at <= ?
              AND m.text IS NOT NULL
              AND m.text != ''
              AND NOT EXISTS (
                  SELECT 1 FROM messages out_m
                  WHERE out_m.chat_id = m.chat_id
                    AND out_m.is_outgoing = 1
                    AND out_m.created_at >= m.created_at
              )
              AND m.id = (
                  SELECT MAX(last_in.id) FROM messages last_in
                  WHERE last_in.chat_id = m.chat_id
                    AND last_in.is_outgoing = 0
              )
            ORDER BY m.created_at ASC
        """
        async with db.execute(query, (cutoff_str,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def update_message_transcription(telegram_message_id: int, chat_id: int, transcription: str) -> None:
    """Ovozli xabar transkripsiyasini xabar matniga saqlash."""
    async with get_db() as db:
        await db.execute(
            """
            UPDATE messages 
            SET text = ?
            WHERE telegram_message_id = ? AND chat_id = ?
            """,
            (f"[🎙 Ovozli xabar]: {transcription}", telegram_message_id, chat_id),
        )
        await db.commit()

