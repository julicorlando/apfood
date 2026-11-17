"""Tela do entregador: um link secreto por entregador, aberto no celular.

Mostra as entregas que estão com ele (saiu para entrega), com endereço, mapa,
botão de ligar e o valor a cobrar, e marca o pedido como entregue."""

from urllib.parse import quote

from apfood_core.dinheiro import formatar
from apfood_core.enums import StatusPedido
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.clientes.models import Entregador
from apps.core.excecoes import ErroNegocio
from apps.pedidos import services as pedidos_srv
from apps.pedidos.models import Pedido


def _entregador(token: str) -> Entregador:
    if len(token) < 20:
        raise Http404
    e = Entregador.objects.ativos().filter(token_acesso=token, ativo=True).select_related("loja").first()
    if e is None:
        raise Http404
    return e


def _cartao(p: Pedido) -> dict:
    endereco = ", ".join(x for x in [f"{p.entrega_logradouro} {p.entrega_numero}".strip(), p.entrega_complemento,
                                       p.entrega_bairro, p.entrega_cidade] if x)
    pago = sum(pg.valor_centavos for pg in p.pagamentos.all() if pg.status == "CONFIRMADO")
    if p.entrega_latitude and p.entrega_longitude:
        mapa = f"https://www.google.com/maps/dir/?api=1&destination={p.entrega_latitude},{p.entrega_longitude}"
    else:
        mapa = f"https://www.google.com/maps/dir/?api=1&destination={quote(endereco)}"
    pendente = next((pg for pg in p.pagamentos.all() if pg.status == "PENDENTE"), None)
    cobrar = max(0, p.total_centavos - pago)
    return {"p": p, "endereco": endereco, "mapa": mapa, "cobrar": cobrar, "cobrar_txt": formatar(cobrar),
            "troco_txt": formatar(p.troco_para_centavos) if p.troco_para_centavos else "",
            "forma": pendente.get_forma_display() if pendente else ""}


@never_cache
def painel_entregador(request, token):
    e = _entregador(token)
    pedidos = (Pedido.objects.filter(entregador=e, status=StatusPedido.SAIU_PARA_ENTREGA)
               .prefetch_related("pagamentos", "itens").order_by("saiu_entrega_em"))
    return render(request, "painel/entregador.html", {"entregador": e, "cartoes": [_cartao(p) for p in pedidos],
                                                      "aviso": request.GET.get("ok")})


@require_POST
def marcar_entregue(request, token, pedido):
    e = _entregador(token)
    p = get_object_or_404(Pedido, pk=pedido, entregador=e)
    try:
        pedidos_srv.transicionar(p, StatusPedido.CONCLUIDO, None, motivo=f"entregue por {e.nome}")
    except ErroNegocio:
        pass  # já concluído/cancelado: só volta para a lista
    return redirect(f"/entrega/{token}/?ok={p.numero}")


@csrf_exempt  # protegido pelo token secreto do link; o celular manda só lat/lng
@require_POST
def localizacao(request, token):
    """Posição do celular do entregador (a cada ~20 s com a página aberta).
    O cliente vê no acompanhamento do pedido enquanto estiver "saiu para entrega"."""
    import json
    from decimal import Decimal, InvalidOperation

    e = _entregador(token)
    try:
        dados = json.loads(request.body or b"{}")
        lat, lng = Decimal(str(dados["latitude"])), Decimal(str(dados["longitude"]))
    except (ValueError, KeyError, InvalidOperation, TypeError):
        return JsonResponse({"ok": False}, status=400)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return JsonResponse({"ok": False}, status=400)
    Entregador.objects.filter(pk=e.pk).update(latitude=round(lat, 7), longitude=round(lng, 7),
                                              localizacao_em=timezone.now())
    return JsonResponse({"ok": True})
