from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True
STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"  # noqa: F405

# Sem Redis local? Use APFOOD_CHANNELS_MEMORIA=1 (só funciona com 1 processo).
if env.bool("APFOOD_CHANNELS_MEMORIA", default=False):
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Testes/dev: throttling não atrapalha
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"publico": "10000/min", "publico_pedido": "10000/min"}}  # noqa: F405
