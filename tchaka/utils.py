from functools import lru_cache
from typing import Any
from telegram import Message, Update, User
import logging
import html
from hashlib import sha256
from random import randint

MAX_STR_SENT_BACK = 1000
# We prevent flowing logs from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO)


def safe_truncate(message: str | None, at: int = 100) -> str:
    message = message or ""

    points = ""
    if len(message) > at:
        points = "..."

    return message[:at] + points


def html_format_text(strr: str) -> str:
    return html.escape(str(safe_truncate(strr, MAX_STR_SENT_BACK)))


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

    return f"u{usr[:5]}"


def build_welcome_location_message_for_current_user(
    user_new_name: str,
    users_list: dict[str, Any],
    lang: str,
) -> str:
    """
    Build location received message

    """

    if lang == "fr":
        suggest_to_connect = (
            (
                f"Il y a ({len(users_list)-1}) personnes dans la meme zone que "
                "vous. ils sont avertis.\n"
                "N'hesitez pas a dire bonjour.\n"
            )
            if len(users_list) > 1
            else ("0 utilisateurs ici pour le moment.\n")
        )
        final_msg = (
            f"Localisation reçue !!!\n"
            f"Maintenant, vous etes ***__{user_new_name}__***.\n"
            f"{suggest_to_connect}\n"
            "Remarque : Tout ici est crypte et le chat sera nettoye lorsque vous changerez de lieu.\n\n"
            "Pour toute question, signalez au dev @sanixdarker"
        )
    else:
        suggest_to_connect = (
            (
                f"There is ({len(users_list)-1}) people in the same area than "
                "you. They just get notified.\n"
                "Feel free to say hi.\n"
            )
            if len(users_list) > 1
            else ("0 users here for now.\n")
        )
        final_msg = (
            f"Location received !!!\n"
            f"Now, your are ***__{user_new_name}__***.\n"
            f"{suggest_to_connect}\n"
            "Note: Everything here is encrypted and the chat will be cleaned when you change place.\n"
            "For any question, please address to @sanixdarker"
        )

    return final_msg
