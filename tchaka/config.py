import os
from dotenv import load_dotenv

load_dotenv()

DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")
TG_TOKEN = os.getenv("TG_TOKEN")
VERSION = os.getenv("VERSION")

LANG_MESSAGES = {
    "fr": {
        "WELCOME_MESSAGE": """Bienvenue sur Tchaka!
Votre Chat_id est:""",
        "HELP_MESSAGE": """/start - Pour obtenir votre chat_id.
/help - Comment cela fonctionne.

Si vous avez toujours un problème, veuillez contacter le dév à
@sanixdarker.""",
    },
    "en": {
        "WELCOME_MESSAGE": """Welcome to Tchaka!
Your Chat_id is :""",
        "HELP_MESSAGE": """/start - To get your chat_id.
/help - How it works.

If you still have a
problem, please contact the developer at @sanixdarker.
""",
    },
}
