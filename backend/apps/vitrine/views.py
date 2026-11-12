"""Cardápio digital público (mobile-first): /<slug>/ e /pedido/<token>/.

A página já vem com o cardápio em JSON (json_script) — abre rápido no 4G e
sem uma segunda requisição. Carrinho, checkout e acompanhamento usam a API
pública (/api/publico/...)."""

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import cache_control

from apps.api.publico import dados_cardapio, loja_publica
from apps.pedidos.models import Pedido


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
