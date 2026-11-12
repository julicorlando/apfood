"""Comandas e mesas: abrir, lançar rodadas, pedir a conta, dividir, juntar,
transferir e fechar."""

from apfood_core.enums import StatusComanda as C
from apfood_core.enums import StatusPedido
from apfood_core.precos import dividir_conta, taxa_servico
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.excecoes import ErroNegocio

from .models import Comanda

ATIVOS = [s for s in StatusPedido if s not in (StatusPedido.CANCELADO, StatusPedido.RECUSADO)]


@transaction.atomic
def abrir(loja, usuario, *, mesa=None, numero: str = "", nome_cliente: str = "", pessoas: int = 1, id=None) -> Comanda:
    if id and (existente := Comanda.objects.filter(pk=id).first()):
        return existente
    if mesa is not None and mesa.loja_id != loja.id:
        raise ErroNegocio("mesa de outra loja")
    from apps.caixa.services import turno_aberto

    return Comanda.objects.create(
        **({"id": id} if id else {}), loja=loja, mesa=mesa, numero=numero, nome_cliente=nome_cliente,
        pessoas=max(1, pessoas), taxa_servico_percentual=loja.taxa_servico_percentual,
        aberta_por=usuario, garcom=usuario, turno=turno_aberto(usuario, loja),
    )


def recalcular(comanda) -> Comanda:
    c = Comanda.objects.select_for_update().get(pk=comanda.pk)
    if c.status == C.FECHANDO:
        return c  # valores congelados após pedir a conta
    c.subtotal_centavos = c.pedidos.filter(status__in=ATIVOS).aggregate(s=Sum("total_centavos"))["s"] or 0
    c.taxa_servico_centavos = (
        taxa_servico(c.subtotal_centavos, c.taxa_servico_percentual) if c.cobrar_taxa_servico else 0
    )
    c.total_centavos = max(0, c.subtotal_centavos + c.taxa_servico_centavos + c.couvert_centavos - c.desconto_centavos)
    c.save()
    comanda.__dict__.update({k: getattr(c, k) for k in
                             ("subtotal_centavos", "taxa_servico_centavos", "total_centavos", "status")})
    return c


def _travar(comanda, *status) -> Comanda:
    c = Comanda.objects.select_for_update().get(pk=comanda.pk)
    if status and c.status not in status:
        raise ErroNegocio(f"comanda está {C(c.status).rotulo.lower()}")
    return c


@transaction.atomic
def ajustar(comanda, usuario, *, cobrar_taxa_servico=None, desconto_centavos=None, couvert_centavos=None):
    c = _travar(comanda, C.ABERTA)
    if desconto_centavos is not None:
        if not usuario.eh_gerente and desconto_centavos > 0:
            raise ErroNegocio("desconto na comanda exige gerente")
        c.desconto_centavos = desconto_centavos
    if cobrar_taxa_servico is not None:
        c.cobrar_taxa_servico = cobrar_taxa_servico
    if couvert_centavos is not None:
        c.couvert_centavos = couvert_centavos
    c.save()
    return recalcular(c)


@transaction.atomic
def pedir_conta(comanda, usuario) -> Comanda:
    c = recalcular(_travar(comanda, C.ABERTA))
    c.status = C.FECHANDO
    c.conta_pedida_em = timezone.now()
    c.save()
    return c


@transaction.atomic
def reabrir(comanda, usuario) -> Comanda:
    from apps.pedidos.services import total_pago

    c = _travar(comanda, C.FECHANDO)
    if total_pago(comanda=c):
        raise ErroNegocio("comanda com pagamento lançado não pode ser reaberta")
    c.status = C.ABERTA
    c.save()
    return recalcular(c)


def divisao_sugerida(comanda, pessoas: int | None = None) -> list[int]:
    from apps.pedidos.services import total_pago

    restante = comanda.total_centavos - total_pago(comanda=comanda)
    return dividir_conta(max(restante, 0), pessoas or comanda.pessoas)


@transaction.atomic
def fechar(comanda, usuario) -> Comanda:
    from apps.pedidos import services as pedidos

    c = _travar(comanda, C.ABERTA, C.FECHANDO)
    if c.status == C.ABERTA:
        c = pedir_conta(c, usuario)
    if pedidos.total_pago(comanda=c) < c.total_centavos:
        raise ErroNegocio("comanda ainda tem valor em aberto")
    for p in c.pedidos.filter(status__in=ATIVOS):
        pedidos.concluir(p, usuario)
    c.status = C.FECHADA
    c.fechada_em = timezone.now()
    c.fechada_por = usuario
    c.save()
    return c


@transaction.atomic
def transferir(comanda, mesa, usuario) -> Comanda:
    c = _travar(comanda, C.ABERTA, C.FECHANDO)
    if mesa.loja_id != c.loja_id:
        raise ErroNegocio("mesa de outra loja")
    c.mesa = mesa
    c.save()
    return c


@transaction.atomic
def juntar(origem, destino, usuario) -> Comanda:
    """Junta a comanda `origem` na `destino` (pedidos e pagamentos vão juntos)."""
    if origem.pk == destino.pk:
        raise ErroNegocio("escolha comandas diferentes")
    o = _travar(origem, C.ABERTA)
    d = _travar(destino, C.ABERTA)
    if o.loja_id != d.loja_id:
        raise ErroNegocio("comandas de lojas diferentes")
    o.pedidos.update(comanda=d)
    o.pagamentos.update(comanda=d)
    d.pessoas += o.pessoas
    d.save()
    o.status = C.CANCELADA
    o.unida_em = d
    o.fechada_em = timezone.now()
    o.fechada_por = usuario
    o.subtotal_centavos = o.taxa_servico_centavos = o.total_centavos = 0
    o.save()
    return recalcular(d)
