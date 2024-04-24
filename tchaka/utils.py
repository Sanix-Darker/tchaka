from functools import lru_cache
from telegram import Message, Update, User
import logging
from hashlib import sha256
from random import randint

# We prevent flowing logs from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)


async def safe_truncate(message: str | None, at: int = 100) -> str:
    if message is None:
        return ""
    return message[:at]


@lru_cache
async def get_user_and_message(update: Update) -> tuple[User, Message]:
    """
    Return from an update the user and the message
    if One of them is None, raise

    """
    if (user := update.effective_user) is None or (message := update.message) is None:
        raise Exception(f"user or message is None :: {update}")

    if user.is_bot is True:
        raise Exception(f"bot detected :: {user.full_name=}")

    return user, message


async def build_user_hash(fullname: str) -> str:
    """
    Easy pizzy builder hash for given fullname

    lol, the salt 'should' prevent any reverse identification

    """

    usr = sha256((fullname + f"salt-{randint(1, 100)}").encode()).hexdigest()

    return f"u__{usr[:15]}"
