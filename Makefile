.PHONY: install run format lint test help

RUFF=ruff check tchaka tests
FORMAT=ruff format tchaka tests
MYPY=mypy tchaka tests

install: ## Install pip poetry
	pip install -U pip poetry
	poetry install --no-root

run:  ## Run the service.
	python -m tchaka.main

format:  ## Reformat project code.
	${RUFF} --fix
	${FORMAT}

lint:  ## Lint project code.
	${RUFF}
	${FORMAT} --check
	${MYPY}

test: ## Run tests
	pytest -s -vv ./tests/

help: ## Show this help.
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
