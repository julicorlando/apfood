import os

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


admin.site.site_header = "ApFood — Painel"
admin.site.site_title = "ApFood"
admin.site.index_title = "Gestão"
admin.site.site_url = "/"


def health(_request):
    return JsonResponse({"status": "ok", "app": "apfood"})


urlpatterns = [
    path("health/", health),
    path("admin/", admin.site.urls),
    # API REST (Passo 2) — consumida pelo PDV desktop
    path("api/auth/token/", TokenObtainPairView.as_view(), name="token"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/", include("apps.api.urls")),
    # Painel web (gestão + operação pelo navegador)
    path("painel/", include("apps.painel.urls")),
    # Cardápio digital público (Passo 4): /<slug-da-loja>/
    path("", include("apps.vitrine.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif os.environ.get("APFOOD_SERVIR_MEDIA") == "1":
    # Fotos dos produtos e logos (volume "media"). Para muito tráfego, troque por S3/CDN.
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns.insert(0, re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}))
