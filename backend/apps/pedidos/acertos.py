"""Acerto com entregadores: quanto a loja paga a cada entregador pelas entregas
ainda não acertadas, descontando o dinheiro dos clientes que ficou com ele.

ganhos   = regra do cadastro (taxa de entrega ou valor fixo por entrega)
em mãos  = pagamentos em dinheiro cobrados na entrega (não online)
saldo    = ganhos − em mãos   (positivo: a loja paga; negativo: o entregador devolve)"""

from __future__ import annotations

from apfood_core.dinheiro import formatar
from apfood_core.enums import StatusPedido as S
from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Entregador
from apps.core.excecoes import ErroNegocio

from .models import AcertoEntregador, Pedido


def _pendentes(loja, entregador=None):
    qs = (Pedido.objects.filter(loja=loja, status=S.CONCLUIDO, entregador__isnull=False, acerto_entregador__isnull=True)
          .select_related("entregador").prefetch_related("pagamentos"))
    return qs.filter(entregador=entregador) if entregador is not None else qs


def _em_maos(p: Pedido) -> int:
    return sum(pg.valor_centavos for pg in p.pagamentos.all()
               if pg.forma == "DINHEIRO" and not pg.pago_online and pg.status in ("PENDENTE", "CONFIRMADO"))


def resumo(loja) -> list[dict]:
    por: dict = {}
    for p in _pendentes(loja):
        e = p.entregador
        r = por.setdefault(e.id, {"entregador_id": str(e.id), "entregador": e.nome, "regra": e.get_remuneracao_display(),
                                  "entregas": 0, "taxas_centavos": 0, "ganhos_centavos": 0, "em_maos_centavos": 0,
                                  "desde": None, "ate": None})
        r["entregas"] += 1
        r["taxas_centavos"] += p.taxa_entrega_centavos
        r["ganhos_centavos"] += e.ganho(p)
        r["em_maos_centavos"] += _em_maos(p)
        d = timezone.localtime(p.concluido_em).date() if p.concluido_em else p.data_referencia
        r["desde"] = min(r["desde"] or d, d)
        r["ate"] = max(r["ate"] or d, d)
    for r in por.values():
        r["saldo_centavos"] = r["ganhos_centavos"] - r["em_maos_centavos"]
    return sorted(por.values(), key=lambda r: -r["saldo_centavos"])


@transaction.atomic
def registrar(loja, entregador_id, *, pago_centavos: int, observacao: str = "", gerar_despesa: bool = True,
              usuario=None) -> AcertoEntregador:
    e = Entregador.objects.filter(loja=loja, pk=entregador_id).first()
    if e is None:
        raise ErroNegocio("entregador não encontrado")
    pedidos = list(_pendentes(loja, e).select_for_update(of=("self",)))
    if not pedidos:
        raise ErroNegocio("este entregador não tem entregas para acertar")
    datas = [timezone.localtime(p.concluido_em).date() if p.concluido_em else p.data_referencia for p in pedidos]
    a = AcertoEntregador.objects.create(
        loja=loja, entregador=e, inicio=min(datas), fim=max(datas), entregas=len(pedidos),
        ganhos_centavos=sum(e.ganho(p) for p in pedidos), em_maos_centavos=sum(_em_maos(p) for p in pedidos),
        pago_centavos=max(0, int(pago_centavos or 0)), observacao=(observacao or "")[:255], usuario=usuario,
    )
    Pedido.objects.filter(pk__in=[p.pk for p in pedidos]).update(acerto_entregador=a)
    if gerar_despesa and a.pago_centavos > 0:
        from apps.financeiro.models import Despesa

        hoje = timezone.localdate()
        a.despesa = Despesa.objects.create(
            loja=loja, descricao=f"Acerto entregador {e.nome} ({a.entregas} entregas)", valor_centavos=a.pago_centavos,
            data_competencia=hoje, data_vencimento=hoje, data_pagamento=hoje, forma_pagamento="DINHEIRO", usuario=usuario)
        a.save(update_fields=["despesa", "atualizado_em"])
    return a


def recibo(a: AcertoEntregador, largura: int = 48) -> list[dict]:
    def l(texto="", **kw):  # noqa: E743
        return {"texto": texto, "negrito": kw.get("negrito", False), "grande": kw.get("grande", False),
                "alinhamento": kw.get("alinhamento", "esquerda"), "corte": kw.get("corte", False), "qrcode": ""}

    def par(a_, b_):
        return l(a_ + " " * max(1, largura - len(a_) - len(b_)) + b_)

    saldo = a.ganhos_centavos - a.em_maos_centavos
    return [
        l(a.loja.nome, negrito=True, alinhamento="centro"),
        l("RECIBO DE ACERTO — ENTREGADOR", negrito=True, alinhamento="centro"),
        l("-" * largura),
        par("Entregador", a.entregador.nome),
        par("Período", f"{a.inicio:%d/%m/%Y} a {a.fim:%d/%m/%Y}"),
        par("Entregas", str(a.entregas)),
        l("-" * largura),
        par("Ganhos pelas entregas", formatar(a.ganhos_centavos)),
        par("Dinheiro de clientes com ele", f"- {formatar(a.em_maos_centavos)}"),
        par("Saldo calculado", formatar(saldo)),
        par("VALOR PAGO", formatar(a.pago_centavos)),
        l(f"Obs.: {a.observacao}") if a.observacao else l(),
        l("-" * largura),
        l(f"Emitido em {timezone.localtime(a.criado_em):%d/%m/%Y %H:%M}"),
        l(), l(), l("_" * min(largura, 36), alinhamento="centro"),
        l(a.entregador.nome, alinhamento="centro"),
        l("", corte=True),
    ]


def para_app(entregadores) -> dict:
    """No app do entregador: o que falta acertar e os últimos acertos."""
    pend = Pedido.objects.filter(entregador__in=entregadores, status=S.CONCLUIDO, acerto_entregador__isnull=True)
    por_id = {e.id: e for e in entregadores}
    acertos = AcertoEntregador.objects.filter(entregador__in=entregadores).select_related("loja")[:10]
    return {
        "pendente_centavos": sum(por_id[p.entregador_id].ganho(p) for p in pend),
        "pendente_entregas": pend.count(),
        "acertos": [{"loja": x.loja.nome, "em": x.criado_em, "entregas": x.entregas, "pago_centavos": x.pago_centavos,
                     "inicio": x.inicio, "fim": x.fim} for x in acertos],
    }


def delivery_no_periodo(loja, inicio, fim) -> dict:
    """Delivery concluído entre `inicio` e `fim` (datetimes): para o fechamento de caixa.
    online = pago pelo app/cardápio (Pix/cartão online); na entrega = cobrado pelo entregador ou no balcão."""
    from apfood_core.enums import TipoAtendimento

    ps = list(Pedido.objects.filter(loja=loja, status=S.CONCLUIDO, tipo_atendimento=TipoAtendimento.ENTREGA,
                                    concluido_em__gte=inicio, concluido_em__lt=fim)
              .select_related("entregador").prefetch_related("pagamentos"))
    online: dict[str, int] = {}
    na_entrega: dict[str, int] = {}
    a_receber = 0
    por_entregador: dict[str, dict] = {}
    for p in ps:
        pago = 0
        for pg in p.pagamentos.all():
            if pg.status != "CONFIRMADO":
                continue
            alvo = online if pg.pago_online else na_entrega
            alvo[pg.forma] = alvo.get(pg.forma, 0) + pg.valor_centavos
            pago += pg.valor_centavos
        falta = max(0, p.total_centavos - pago)
        a_receber += falta
        nome = p.entregador.nome if p.entregador_id else "Sem entregador / própria"
        e = por_entregador.setdefault(nome, {"entregador": nome, "entregas": 0, "total_centavos": 0, "taxas_centavos": 0,
                                             "dinheiro_centavos": 0, "a_receber_centavos": 0})
        e["entregas"] += 1
        e["total_centavos"] += p.total_centavos
        e["taxas_centavos"] += p.taxa_entrega_centavos
        e["dinheiro_centavos"] += _em_maos(p)
        e["a_receber_centavos"] += falta
    return {
        "pedidos": len(ps), "total_centavos": sum(p.total_centavos for p in ps),
        "taxas_centavos": sum(p.taxa_entrega_centavos for p in ps),
        "online": online, "online_centavos": sum(online.values()),
        "na_entrega": na_entrega, "na_entrega_centavos": sum(na_entrega.values()),
        "a_receber_centavos": a_receber,
        "por_entregador": sorted(por_entregador.values(), key=lambda x: -x["total_centavos"]),
    }
