## TCHAKA

This bot is a simple telegram bot that makes you in contacts with people
'around you anonymously'.

## HOW GET IT RUN

### WITH DOCKER

```bash
$ cp .env.example .env
# then set your own variables in .env file

$ docker build -t tchaka:latest -f ./Dockerfile .
$ docker run -ti tchaka
INFO:__main__:tchaka v0.0.1 started successfully...
INFO:telegram.ext.Application:Application started
INFO:tchaka.commands:/start :: send_message :: user.full_name='d4rk3r .'
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
INFO:__main__:tchaka v0.0.1 started successfully...
INFO:telegram.ext.Application:Application started
INFO:tchaka.commands:/start :: send_message :: user.full_name='d4rk3r .'
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
