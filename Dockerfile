# ApFood — imagem única do servidor (web ASGI + workers). Contexto = raiz do repositório.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 apfood

WORKDIR /app
COPY core/ /app/core/
COPY backend/requirements/ /app/backend/requirements/
RUN cd /app/backend && pip install -r requirements/prod.txt

COPY backend/ /app/backend/
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && cd /app/backend \
    && DJANGO_SECRET_KEY=build DATABASE_URL=sqlite:////tmp/build.db python manage.py collectstatic --noinput \
    && mkdir -p /app/backend/media && chown -R apfood:apfood /app/backend/media /app/backend/staticfiles

USER apfood
WORKDIR /app/backend
EXPOSE 8000
# health check definido por serviço no docker-compose.prod.yml (só o "web" atende HTTP)
ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]
