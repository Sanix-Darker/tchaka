import os
from dotenv import load_dotenv

load_dotenv()

DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")
TG_TOKEN = os.getenv("TG_TOKEN")

LANG_MESSAGES = {
    "fr": {
        "WELCOME_MESSAGE": """Bienvenue sur Tchaka!
Commencez par envoyer votre localisation (aucun soucis, c est anonyme et rien
ne se sauvegardes)""",
        "HELP_MESSAGE": """/start - Pour demarrer.
/help - Comment cela fonctionne.
/stop - Pour stoper le bot et cleaner toutes vos infos.

Si vous avez toujours un problème, veuillez contacter le dév
@sanixdarker.""",
    },
    "en": {
        "WELCOME_MESSAGE": """Welcome to Tchaka!
Start by sending your localisation and get guided (No worries, it is anonym and not stored)""",
        "HELP_MESSAGE": """/start - To get started.
/help - How it works
/stop - To Stop the bot and clean all your infos.

If you still have a
problem, please contact the developer at @sanixdarker.
""",
    },
}
