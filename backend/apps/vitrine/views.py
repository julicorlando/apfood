"""Cardápio digital público (mobile-first): /<slug>/ e /pedido/<token>/.

A página já vem com o cardápio em JSON (json_script) — abre rápido no 4G e
sem uma segunda requisição. Carrinho, checkout e acompanhamento usam a API
pública (/api/publico/...)."""

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import cache_control

from apps.api.publico import dados_cardapio, loja_publica
from apps.pedidos.models import Pedido


URL_RELEASES_PDV = "https://github.com/julicorlando/apfood/releases/latest"


@cache_control(max_age=300, public=True)
def inicio(request):
    """Página inicial do domínio: leva ao painel e ao download do PDV."""
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
