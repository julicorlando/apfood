from .base import *  # noqa: F401,F403

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # health check interno do container é HTTP
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------------- monitoramento de erros
# DJANGO_ADMINS="Fulano <fulano@x.com>, outro@x.com": recebem por e-mail cada erro 500
# (precisa de EMAIL_URL). SENTRY_DSN: liga o Sentry (erros com contexto, agrupados).
def _admin(item: str) -> tuple[str, str]:
    nome, _, email = item.strip().partition("<")
    return (nome.strip(), email.strip(" >")) if email else (nome.strip(), nome.strip())


ADMINS = [_admin(i) for i in env.list("DJANGO_ADMINS", default=[]) if i.strip()]  # noqa: F405
SERVER_EMAIL = DEFAULT_FROM_EMAIL  # noqa: F405

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "mail_admins": {"level": "ERROR", "filters": ["require_debug_false"],
                        "class": "django.utils.log.AdminEmailHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console", "mail_admins"], "level": "ERROR", "propagate": False},
        "apps": {"handlers": ["console", "mail_admins"], "level": "INFO", "propagate": False},
    },
}

SENTRY_DSN = env("SENTRY_DSN", default="")  # noqa: F405
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
    except ImportError:  # pragma: no cover - imagem sem a dependência
        sentry_sdk = None
    if sentry_sdk:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            environment=env("SENTRY_AMBIENTE", default="producao"),  # noqa: F405
            release=f"apfood@{env('APFOOD_VERSAO', default='dev')}",  # noqa: F405
            traces_sample_rate=env.float("SENTRY_TRACES", default=0.0),  # noqa: F405
            send_default_pii=False,  # não manda dados de clientes
        )
