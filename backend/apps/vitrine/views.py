"""Cardápio digital público (mobile-first). Esqueleto — Passo 4."""

from django.shortcuts import get_object_or_404, render

from apps.cardapio.models import Categoria
from apps.lojas.models import Loja
from apps.pedidos.models import Pedido


def cardapio(request, slug):
    loja = get_object_or_404(Loja, slug=slug)
    categorias = (
        Categoria.objects.ativos()
        .filter(loja=loja, ativa=True)
        .prefetch_related("produtos")
    )
    return render(request, "vitrine/cardapio.html", {"loja": loja, "categorias": categorias})


def acompanhar_pedido(request, token):
    pedido = get_object_or_404(Pedido.objects.select_related("loja"), token_rastreio=token)
    return render(request, "vitrine/acompanhar.html", {"pedido": pedido})
