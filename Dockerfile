FROM python:3.12-slim as base


ENV POETRY_VERSION=2.1.3
RUN pip install "poetry==$POETRY_VERSION"


RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*


ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_NO_INTERACTION=1
ENV POETRY_HOME=/opt/poetry


WORKDIR /app


COPY pyproject.toml poetry.lock ./

RUN poetry install --no-root

COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]