import os
import logging
import asyncio
import os.path as op
import tempfile

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from aiohttp import web

# ==== НАСТРОЙКИ ЧЕРЕЗ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====
TOKEN = os.environ["BOT_TOKEN"]  # задам на Render
PUBLIC_URL = os.environ["WEBHOOK_URL"].rstrip("/")  # https://<service>.onrender.com
PORT = int(os.environ.get("PORT", 10000))
PRICE_PER_CM3 = float(os.environ.get("PRICE_PER_CM3", "0.15"))  # € за см³

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("3dprint-bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋 Пришли мне STL-файл (как документ), и я посчитаю объём и примерную стоимость 3D-печати."
    )


# ---- обработка STL ----
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    # Проверяем расширение
    filename = (doc.file_name or "").lower()
    if not filename.endswith(".stl"):
        await update.message.reply_text("Пожалуйста, пришли файл с расширением .stl")
        return

    # Скачиваем во временный файл
    file = await doc.get_file()
    fd, tmp_path = tempfile.mkstemp(suffix=".stl")
    os.close(fd)  # закрываем дескриптор — будем работать по пути
    try:
        await file.download_to_drive(tmp_path)

        # Импорт здесь, чтобы ускорить старт (и меньше памяти держать на холостом ходу)
        import trimesh

        # Загружаем сетку (с защитой)
        mesh = trimesh.load(tmp_path, force="mesh")  # гарантируем именно меш
        if mesh is None or mesh.is_empty:
            await update.message.reply_text("Не удалось прочитать модель из STL. Проверь файл.")
            return

        # Попытка починки (на случай дыр/некорректных нормалей)
        try:
            mesh.remove_unreferenced_vertices()
            mesh.remove_duplicate_faces()
            mesh.fill_holes()  # может не всегда сработать, но попробуем
        except Exception:
            pass

        # Объём в мм³ → см³
        volume_mm3 = float(mesh.volume)
        volume_cm3 = volume_mm3 / 1000.0

        price = volume_cm3 * PRICE_PER_CM3

        await update.message.reply_text(
            f"📦 Объём модели: {volume_cm3:.2f} см³\n"
            f"💶 Оценка стоимости: {price:.2f} €\n\n"
            f"ℹ️ Тариф: {PRICE_PER_CM3:.2f} €/см³ (без учёта поддержек и инфилла)"
        )

    except Exception as e:
        log.exception("Ошибка обработки STL")
        await update.message.reply_text(f"Ошибка при обработке файла: {e}")
    finally:
        try:
            if op.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

async def healthcheck(request):
    return web.Response(text="OK")


async def run_bot():
    app = ApplicationBuilder().token(TOKEN).build()

    # handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # --- WEBHOOK ---
    webhook_path = f"/webhook/{TOKEN.split(':')[0]}"

    # создаём aiohttp web-сервер
    web_app = web.Application()
    web_app.router.add_get("/ping", healthcheck)

    # endpoint для Telegram webhook
    async def telegram_webhook(request):
        data = await request.json()
        await app.update_queue.put(Update.de_json(data, app.bot))
        return web.Response(text="ok")

    web_app.router.add_post(webhook_path, telegram_webhook)

    # запускаем webhook и aiohttp вместе
    await app.bot.delete_webhook()
    await app.bot.set_webhook(f"{PUBLIC_URL}{webhook_path}")
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"✅ Bot is running on {PUBLIC_URL}{webhook_path}")
    await app.initialize()
    await app.start()
    await asyncio.Event().wait()  # держим процесс активным


def main():
    asyncio.run(run_bot())



if __name__ == "__main__":
    # На всякий случай запускаем в отдельном потоке событий
    try:
        main()
    except KeyboardInterrupt:
        pass
