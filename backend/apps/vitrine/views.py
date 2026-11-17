"""Cardápio digital público (mobile-first): /<slug>/ e /pedido/<token>/.

A página já vem com o cardápio em JSON (json_script) — abre rápido no 4G e
sem uma segunda requisição. Carrinho, checkout e acompanhamento usam a API
pública (/api/publico/...)."""

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect, get_object_or_404, render
from django.views.decorators.cache import cache_control

from apps.api.publico import dados_cardapio, loja_publica
from apps.pedidos.models import Pedido


URL_RELEASES_PDV = "https://github.com/julicorlando/apfood/releases/latest"


@cache_control(max_age=300, public=True)
def empresas(request):
    """“Login empresas”: leva ao painel, ao teste grátis e aos downloads (PDV e apps)."""
    url_pdv = settings.APFOOD.get("PDV_URL") or URL_RELEASES_PDV
    return render(request, "vitrine/inicio.html", {"url_pdv": url_pdv})


@cache_control(max_age=30, public=True)
def cardapio(request, slug):
    try:
        loja = loja_publica(slug)
    except Http404:
        return render(request, "vitrine/indisponivel.html", status=404)
    dados = dados_cardapio(loja, request)
    return render(request, "vitrine/cardapio.html", {"loja": loja, "dados": dados, "cor": loja.cor_primaria})


@cache_control(no_store=True)
def acompanhar_pedido(request, token):
    pedido = get_object_or_404(Pedido.objects.select_related("loja"), token_rastreio=token)
    return render(request, "vitrine/acompanhar.html", {"pedido": pedido, "cor": pedido.loja.cor_primaria})


@cache_control(max_age=60, public=True)
def reservar(request, slug):
    try:
        loja = loja_publica(slug)
    except Http404:
        return render(request, "vitrine/indisponivel.html", status=404)
    if not loja.aceita_reservas:
        return redirect(f"/{loja.slug}/")
    return render(request, "vitrine/reserva.html", {"loja": loja, "cor": loja.cor_primaria})


@cache_control(no_store=True)
def totem(request, slug, token):
    """Totem de autoatendimento (tablet no balcão): link secreto gerado no painel."""
    import secrets

    try:
        loja = loja_publica(slug)
    except Http404:
        return render(request, "vitrine/indisponivel.html", status=404)
    if not loja.token_totem or not secrets.compare_digest(loja.token_totem, token):
        return render(request, "vitrine/indisponivel.html", status=404)
    dados = dados_cardapio(loja, request)
    dados["totem"] = {"token": token}
    return render(request, "vitrine/cardapio.html", {"loja": loja, "dados": dados, "cor": loja.cor_primaria})


@cache_control(no_store=True)
def cardapio_mesa(request, slug, token):
    """QR Code da mesa: o mesmo cardápio, mas o pedido vai para a comanda da mesa."""
    from apps.api.publico import mesa_publica

    try:
        loja = loja_publica(slug)
        mesa = mesa_publica(loja, token)
    except Http404:
        return render(request, "vitrine/indisponivel.html", status=404)
    dados = dados_cardapio(loja, request)
    dados["mesa"] = {"token": token, "nome": mesa.nome}
    return render(request, "vitrine/cardapio.html", {"loja": loja, "dados": dados, "cor": loja.cor_primaria})


def app_cliente(request):
    """Página inicial e app do cliente (o APK "ApFood" abre /app/): restaurantes da região."""
    return render(request, "vitrine/app.html", {"cor": "#f26a0f"})


def app_manifest(request):
    from django.http import JsonResponse
    from django.templatetags.static import static

    return JsonResponse({
        "name": "ApFood", "short_name": "ApFood", "start_url": "/app/", "scope": "/", "display": "standalone",
        "background_color": "#ffffff", "theme_color": "#f26a0f", "lang": "pt-BR",
        "icons": [{"src": static("marca/icone-192.png"), "sizes": "192x192", "type": "image/png"},
                  {"src": static("marca/icone-512.png"), "sizes": "512x512", "type": "image/png"}],
    }, content_type="application/manifest+json")


@cache_control(no_cache=True)
def app_entregador(request):
    """App ApFood Entregador (também é o que o APK abre)."""
    return render(request, "vitrine/entregador.html")


def app_entregador_manifest(request):
    from django.http import JsonResponse
    from django.templatetags.static import static

    return JsonResponse({
        "name": "ApFood Entregador", "short_name": "Entregador", "start_url": "/entregador/", "scope": "/entregador/",
        "display": "standalone", "background_color": "#1d1d1f", "theme_color": "#1d1d1f", "lang": "pt-BR",
        "icons": [{"src": static("marca/icone-192.png"), "sizes": "192x192", "type": "image/png"},
                  {"src": static("marca/icone-512.png"), "sizes": "512x512", "type": "image/png"}],
    }, content_type="application/manifest+json")


def baixar_app(request, qual):
    """Link fixo para o APK da versão publicada (GitHub Releases)."""
    from django.http import Http404

    arquivos = {"cliente": "ApFood-Cliente.apk", "empresa": "ApFood-Empresa.apk", "entregador": "ApFood-Entregador.apk"}
    if qual not in arquivos:
        raise Http404
    versao = settings.APFOOD.get("APPS_VERSAO") or "1.0.0"
    return redirect(f"https://github.com/julicorlando/apfood/releases/download/apps-v{versao}/{arquivos[qual]}")
