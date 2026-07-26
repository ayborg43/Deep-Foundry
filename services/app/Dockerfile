FROM python:3.14-slim

WORKDIR /srv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake the static assets (Django admin, DRF) into the image so WhiteNoise can
# serve them; runs with settings defaults, touches no database.
RUN python manage.py collectstatic --noinput

# Stamp the build with its git SHA so /health can report exactly what's running.
# Pass at build time: docker build --build-arg APP_VERSION=$(git rev-parse --short HEAD)
ARG APP_VERSION=""
ENV APP_VERSION=$APP_VERSION

EXPOSE 8000

# Default to the ASGI web process; infra/docker-compose.yml overrides `command`
# to `celery -A config worker --loglevel=info` for the worker role — one
# image, two entrypoints, per ARCHITECTURE.md ADR-006.
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
