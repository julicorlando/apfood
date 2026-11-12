#!/bin/sh
# Papéis do container: web (padrão) | tarefas | ifood | cobranca
set -e
PAPEL="${1:-web}"
export APFOOD_PAPEL="$PAPEL"

esperar_banco() {
  python - <<'PY'
import os, sys, time
import django
django.setup()
from django.db import connection
for tentativa in range(60):
    try:
        connection.ensure_connection()
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"aguardando o banco... ({exc.__class__.__name__})", flush=True)
        time.sleep(2)
sys.exit("banco indisponível")
PY
}

esperar_banco
case "$PAPEL" in
  web)
    python manage.py migrate --noinput
    if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
      python manage.py createsuperuser --noinput --username "$DJANGO_SUPERUSER_USERNAME" \
        --email "${DJANGO_SUPERUSER_EMAIL:-admin@localhost}" 2>/dev/null || true
    fi
    exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 \
      --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips="*" --lifespan off
    ;;
  tarefas) exec python manage.py processar_tarefas ;;
  ifood)   exec python manage.py ifood_polling ;;
  cobranca)
    while true; do python manage.py cobranca_diaria || true; sleep 86400; done
    ;;
  *) exec "$@" ;;
esac
