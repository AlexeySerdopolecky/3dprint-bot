import os
import logging
import asyncio
import os.path as op
import tempfile

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from aiohttp import web

# ==== НАСТРОЙКИ ЧЕРЕЗ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====
TOKEN = os.environ["BOT_TOKEN"]                     # Render: env var
PUBLIC_URL = os.environ["WEBHOOK_URL"].rstrip("/")  # https://<service>.onrender.com
PORT = int(os.environ.get("PORT", 10000))
PRICE_PER_CM3 = float(os.environ.get("PRICE_PER_CM3", "0.15"))  # € за см³

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("life3done-bot")

# ==== CALLBACK KEYS ====
CB_MAIN = "main"
CB_MENU = "menu"
CB_FREE = "free_models"
CB_CALC = "calc"
CB_CONTACTS = "contacts"
CB_BACK = "back"
CB_ABOUT = "about"

# ==== КЛАВИАТУРЫ ====
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧭 Меню", callback_data=CB_MENU)],
        [InlineKeyboardButton("ℹ️ О проекте", callback_data=CB_ABOUT)],
        [InlineKeyboardButton("💖 Поддержать проект", url="https://t.me/oleksiiserdopoletskyi")],
    ])

def kb_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Бесплатные модели из роликов", callback_data=CB_FREE)],
        [InlineKeyboardButton("⚙️ Индивидуальный просчёт 3D-печати", callback_data=CB_CALC)],
        [InlineKeyboardButton("📞 Контакты для связи", callback_data=CB_CONTACTS)],
        [InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK)],
    ])

def kb_free_models() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 Излучатель узкий", url="https://www.dropbox.com/scl/fi/fwsqvdn2adhsgsdk02wut/07.02.01.01.010.STL?rlkey=42hno4nt84g8n8n6m0cjx46mz&dl=0")],
        [InlineKeyboardButton("📎 Приёмник узкий", url="https://www.dropbox.com/scl/fi/xnk1eybil4i59uqi5p5pn/07.02.01.02.010.STL?rlkey=rjx1v5e8d7anq1dv51py0fcfi&dl=0")],
        [InlineKeyboardButton("🔙 Назад", callback_data=CB_MENU)],
    ])

def kb_calc_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data=CB_MENU)],
    ])

def kb_contacts() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Telegram", url="https://t.me/oleksiiserdopoletskyi")],
        [InlineKeyboardButton("📸 Instagram", url="https://www.instagram.com/alekseipoletskii")],
        [InlineKeyboardButton("🔙 Назад", callback_data=CB_MENU)],
    ])

# ==== HANDLERS ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass

    text = (
        "Привет! 👋 Я бот *Life3Done*.\n"
        "Здесь ты можешь скачать модели из роликов или сделать предварительный просчёт стоимости твоей 3D-детали."
    )
    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=kb_main(),
            parse_mode="Markdown"
        )

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data

    if data in (CB_MAIN, CB_BACK):
        await query.message.edit_text(
            "Привет! 👋 Я бот *Life3Done*.\n"
            "Здесь ты можешь скачать модели из роликов или сделать предварительный просчёт стоимости твоей 3D-детали.",
            reply_markup=kb_main(),
            parse_mode="Markdown",
        )
        return

    if data == CB_MENU:
        await query.message.edit_text(
            "🧭 *Меню* — выбери раздел:",
            reply_markup=kb_menu(),
            parse_mode="Markdown",
        )
        return

    if data == CB_FREE:
        await query.message.edit_text(
            "📂 *Бесплатные модели из роликов* — выбери файл:",
            reply_markup=kb_free_models(),
            parse_mode="Markdown",
        )
        return

    if data == CB_CALC:
        await query.message.edit_text(
            "⚙️ *Индивидуальный просчёт 3D-печати*\n\n"
            "Отправь STL-файл *как документ*, и я посчитаю объём и примерную стоимость.",
            reply_markup=kb_calc_back(),
            parse_mode="Markdown",
        )
        return

    if data == CB_CONTACTS:
        await query.message.edit_text(
            "📞 *Контакты для связи:*",
            reply_markup=kb_contacts(),
            parse_mode="Markdown",
        )
        return

    if data == CB_ABOUT:
        await query.message.edit_text(
            "ℹ️ *О проекте*\n\n"
            "Этот бот создан для демонстрации и распространения полезных 3D-моделей, "
            "а также для расчёта стоимости индивидуальной 3D-печати. "
            "Цель проекта — показать, как 3D-печать может сделать повседневную жизнь удобнее и креативнее.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK)]]),
            parse_mode="Markdown",
        )
        return

# ---- обработка STL ----
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    filename = (doc.file_name or "").lower()
    if not filename.endswith(".stl"):
        await update.message.reply_text("Пожалуйста, пришли файл с расширением .stl")
        return

    if doc.file_size and doc.file_size > 30 * 1024 * 1024:
        await update.message.reply_text("Файл слишком большой. Пожалуйста, отправь STL до 30 МБ.")
        return

    file = await doc.get_file()
    fd, tmp_path = tempfile.mkstemp(suffix=".stl")
    os.close(fd)
    try:
        await file.download_to_drive(tmp_path)

        import trimesh

        mesh = trimesh.load(tmp_path, force="mesh")
        if mesh is None or mesh.is_empty:
            await update.message.reply_text("Не удалось прочитать модель из STL. Проверь файл.")
            return

        try:
            mesh.remove_unreferenced_vertices()
            mesh.remove_duplicate_faces()
            mesh.fill_holes()
        except Exception:
            pass

        volume_mm3 = float(mesh.volume)
        volume_cm3 = volume_mm3 / 1000.0
        price = volume_cm3 * PRICE_PER_CM3

        await update.message.reply_text(
            f"📦 Объём модели: {volume_cm3:.2f} см³\n"
            f"💶 Оценка стоимости: {price:.2f} €\n\n"
            f"ℹ️ Тариф: {PRICE_PER_CM3:.2f} €/см³ (без учёта поддержек и инфилла)"
        )

        # 💡 Добавляем меню после расчёта, чтобы кнопки всегда были снизу
        await update.message.reply_text(
            "👇 Вы можете вернуться в меню:",
            reply_markup=kb_main()
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

# ---- healthcheck для cron-job.org ----
async def healthcheck(request):
    return web.Response(text="OK")

# ---- aiohttp + webhook ----
async def run_bot():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    webhook_path = f"/webhook/{TOKEN.split(':')[0]}"

    web_app = web.Application()
    web_app.router.add_get("/ping", healthcheck)

    async def telegram_webhook(request):
        data = await request.json()
        await app.update_queue.put(Update.de_json(data, app.bot))
        return web.Response(text="ok")

    web_app.router.add_post(webhook_path, telegram_webhook)

    await app.bot.delete_webhook()
    await app.bot.set_webhook(f"{PUBLIC_URL}{webhook_path}")
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"✅ Bot is running on {PUBLIC_URL}{webhook_path}")
    await app.initialize()
    await app.start()
    await asyncio.Event().wait()

def main():
    asyncio.run(run_bot())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
