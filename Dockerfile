FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN pip install -U pip poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-root

COPY . .

CMD ["python", "-m", "tchaka.main"]
