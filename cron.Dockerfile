# Use the main application's Docker image as a base
# This assumes the main Dockerfile is built first or is available
# We will use a multi-stage build to copy the environment.
FROM python:3.12-slim as base

# Set up poetry
# Set up poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VERSION=2.1.3
ENV PATH="$POETRY_HOME/bin:$PATH"
RUN apt-get update && apt-get install -y curl && \
    curl -sSL https://install.python-poetry.org | python -

# Copy project files and install dependencies
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry lock
RUN poetry install --no-root --only=main

# Final stage for the cron container
FROM base as cron-runner

# Install cron
RUN apt-get update && apt-get install -y cron

# Copy the application code
COPY . /app

# Copy the crontab file to the cron.d directory
COPY crontab /etc/cron.d/monthly-task
# Give execution rights on the crontab file
RUN chmod 0644 /etc/cron.d/monthly-task

# Create a log file to be able to run tail
RUN touch /var/log/cron.log

# The command to run cron in the foreground and tail the log
CMD cron && tail -f /var/log/cron.log
