## TCHAKA

This bot makes you in contact with people 'around' you anonymously based on
your localisation.

No DATA saved + all IN MEMORY...

## COMMANDS

- `/start` - Get started.
- `/help` - Show how it works.
- `/check` - See how many people are currently around you (within the
  configured range).
- `/stop` - Stop the bot and clean all your info.
- Send your **location** to join the area around you.
- Send any **text** to relay it anonymously to everyone currently around you.

## CONFIGURATION

Copy `.env.example` to `.env` and set your values. Required and optional
variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TG_TOKEN` | yes | - | Telegram bot token from @BotFather. |
| `DEVELOPER_CHAT_ID` | no | - | Chat that receives error reports. If unset, errors are only logged. |
| `TCHAKA_RANGE_KM` | no | `5` | Radius (km) that defines "around you". |
| `TCHAKA_IDLE_TTL_SECONDS` | no | `3600` | Idle time before a user is auto-evicted (~1h). |
| `TCHAKA_SWEEP_INTERVAL_SECONDS` | no | `300` | How often the idle-eviction sweep runs. |
| `TCHAKA_MAX_RELAY_CHARS` | no | `500` | Max length of a relayed message body. |
| `TCHAKA_MAX_ERROR_CHARS` | no | `3500` | Max length of an error report (< Telegram's 4096 limit). |

Numeric values fall back to their defaults if missing or malformed; only a
missing `TG_TOKEN` stops the bot from starting.

## HOW GET IT RUN

### WITH DOCKER

```bash
$ cp .env.example .env
# then set your own variables in .env file

$ docker build -t tchaka:latest -f ./Dockerfile .
$ docker run -ti tchaka
INFO:__main__:tchaka started successfully...
INFO:telegram.ext.Application:Application started
```

### NO DOCKER

```bash
$ cp .env.example .env
# then set your own variables in .env file

$ make install
# to install libs...

$ make run
# to start the bot...
python -m tchaka.main
INFO:__main__:tchaka started successfully...
INFO:telegram.ext.Application:Application started
```

### BONUS (for dev)

```bash
$ make help
format               Reformat project code.
help                 Show this help.
install              Install pip poetry
lint                 Lint project code.
run                  Run the service.
test                 Run tests
```

## CONTRIBUTOR-NOTE

If you want to make contributions, make sure to create an issue first if
possible, let's discuss about it and then start a PR :).
Contributions are always welcome.

## AUTHOR

- [sanixdk](https://github.com/sanix-darker)
