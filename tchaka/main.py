from telegram import Update
from tchaka.commands import (
    echo_callback,
    location_callback,
    start_callback,
    help_callback,
    error_handler,
)
from tchaka.utils import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from tchaka.config import TG_TOKEN, VERSION

_LOGGER = logging.getLogger(__name__)

HANDLERS = [
    CommandHandler("start", start_callback),
    CommandHandler("help", help_callback),
    MessageHandler(filters.LOCATION, location_callback),
    MessageHandler(filters.TEXT & ~filters.COMMAND, echo_callback),
]

if __name__ == "__main__":
    if TG_TOKEN is None:
        raise Exception("TG_TOKEN not found, please set it in .env")

    application = Application.builder().token(TG_TOKEN).build()
    for ha in HANDLERS:
        application.add_handler(ha)
    # send errors to the dev when they happens
    application.add_error_handler(error_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)
    _LOGGER.info(f"tchaka v{VERSION} started successfully...")
