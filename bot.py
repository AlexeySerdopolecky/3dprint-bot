import logging
import os
import trimesh
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = "8393949970:AAE93YftQcQJent3oTRbW9S6OH_8ddnbrpM"
PRICE_PER_CM3 = 0.15  # евро за куб. сантиметр

logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋 Отправь мне STL-файл модели, и я рассчитаю примерную стоимость 3D-печати."
    )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    file_path = f"model_{update.message.from_user.id}.stl"
    await file.download_to_drive(file_path)

    try:
        mesh = trimesh.load(file_path)
        volume_mm3 = mesh.volume
        volume_cm3 = volume_mm3 / 1000
        price = volume_cm3 * PRICE_PER_CM3

        await update.message.reply_text(
            f"📦 Объём модели: {volume_cm3:.2f} см³\n💶 Примерная стоимость печати: {price:.2f} €"
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке файла: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))

    app.run_polling()


if __name__ == "__main__":
    main()
