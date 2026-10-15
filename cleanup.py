import os
import asyncio
from typing import Dict
from config import Config, logger
import db


async def cleanup_old_messages_and_media(days: int = Config.MESSAGE_RETENTION_DAYS) -> Dict[str, int]:
    """
    Belgilangan muddatdan (odatiy: 30 kun) eski xabarlarni bazadan va
    ularga tegishli media fayllarni diskdan o'chiradi.
    """
    logger.info(f"Eski ma'lumotlarni tozalash boshlandi (muddat: {days} kun)...")
    try:
        old_records = await db.get_and_delete_old_messages(days=days)
        deleted_messages_count = len(old_records)
        deleted_files_count = 0

        for record in old_records:
            media_path = record.get("media_path")
            if media_path and os.path.exists(media_path):
                try:
                    os.remove(media_path)
                    deleted_files_count += 1
                except OSError as fe:
                    logger.warning(f"Media faylni o'chirishda xatolik ({media_path}): {fe}")

        logger.info(
            f"Tozalash yakunlandi: {deleted_messages_count} ta eski xabar bazadan, "
            f"{deleted_files_count} ta media fayl diskdan tozalandi."
        )
        return {
            "deleted_messages": deleted_messages_count,
            "deleted_media_files": deleted_files_count,
        }
    except Exception as e:
        logger.error(f"Tozalash jarayonida xatolik yuz berdi: {e}", exc_info=True)
        return {"deleted_messages": 0, "deleted_media_files": 0}


async def start_cleanup_scheduler(interval_hours: int = 24) -> None:
    """
    Orqa fonda (background asyncio task) davriy ravishda har N soatda
    tozalash ishlarini bajarib turuvchi rejalashtiruvchi.
    """
    logger.info(f"Avtomatik tozalash xizmati ishga tushdi (interval: har {interval_hours} soatda).")
    while True:
        try:
            await cleanup_old_messages_and_media()
        except asyncio.CancelledError:
            logger.info("Tozalash xizmati to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Tozalash rejalashtiruvchisida kutilmagan xatolik: {e}")

        # Belgilangan soat kutish (sekundlarda)
        await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    # Test yoki qo'lda ishga tushirish uchun
    print("Qo'lda tozalash ishga tushirilmoqda...")
    asyncio.run(cleanup_old_messages_and_media())
