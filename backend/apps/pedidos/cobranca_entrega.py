"""Cobrança na porta do cliente pelo app do entregador e repasse do dinheiro à loja.

Dinheiro  → o entregador digita quanto recebeu e quanto deu de troco; o pagamento
            fica "com o entregador" (PENDENTE + cobrado_em) até a loja receber o repasse.
Cartão    → maquininha da loja: o entregador marca como pago (confirmado na hora).
Pix       → QR gerado no app pelo gateway da loja; a confirmação do gateway conclui a
            entrega. Sem gateway: Pix na chave da loja, o entregador marca como pago.

Repasse   → o entregador informa quanto entregou; a loja informa quanto recebeu (os dois
            digitam). O dinheiro entra no caixa aberto de quem recebeu; diferença fica registrada
            e ajusta a gaveta (sangria/suprimento) para o caixa bater com o que entrou de fato."""

from __future__ import annotations

from apfood_core.dinheiro import formatar
from apfood_core.enums import FormaPagamento as F
from apfood_core.enums import StatusPagamento as SP
from apfood_core.enums import StatusPedido as S
from apfood_core.enums import TipoMovimentacaoCaixa as T
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.excecoes import ErroNegocio
from apps.realtime import eventos

from .models import Pagamento, Pedido, RepasseEntregador

FORMAS = {"DINHEIRO": F.DINHEIRO, "CARTAO_CREDITO": F.CARTAO_CREDITO, "CARTAO_DEBITO": F.CARTAO_DEBITO, "PIX": F.PIX}


def _pedido(pedido_id, e) -> Pedido:
    p = Pedido.objects.select_for_update(of=("self",)).select_related("loja").filter(pk=pedido_id, entregador=e).first()
    if p is None:
        raise ErroNegocio("pedido não encontrado")
    if p.status != S.SAIU_PARA_ENTREGA:
        raise ErroNegocio("confirme a retirada na loja antes de cobrar")
    return p


def _int(v, campo: str) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ErroNegocio("informe o valor", campo) from None
    if n < 0:
        raise ErroNegocio("valor inválido", campo)
    return n


def falta(p: Pedido) -> int:
    from . import services

    return max(0, p.total_centavos - services.total_pago(pedido=p))


def tem_gateway(loja) -> bool:
    from apps.integracoes.models import Integracao

    return Integracao.ativa(loja, "PAGAMENTO", "mercadopago") is not None


def _avisar_loja(p: Pedido, tipo: str, dados: dict) -> None:
    eventos.publicar(eventos.grupo_pdv(p.loja_id), tipo, {"pedido": str(p.id), "numero": p.numero, **dados})


@transaction.atomic
def cobrar(pedido_id, e, forma: str, *, recebido=None, troco=None, bandeira: str = "") -> Pagamento:
    """O entregador registra o que o cliente pagou na entrega."""
    from . import services

    if forma not in FORMAS:
        raise ErroNegocio("escolha dinheiro, cartão ou Pix", "forma")
    p = _pedido(pedido_id, e)
    valor = falta(p)
    if valor <= 0:
        raise ErroNegocio("este pedido já está pago")
    agora = timezone.now()
    base = {"pedido": p, "forma": FORMAS[forma], "valor_centavos": valor, "entregador": e, "cobrado_em": agora,
            "pago_online": False}
    services.limpar_pendentes(p)
    if forma == "DINHEIRO":
        rec, tr = _int(recebido, "valor_recebido_centavos"), _int(troco if troco not in (None, "") else 0, "troco_centavos")
        if rec - tr != valor:
            raise ErroNegocio(f"a conta não fecha: recebido {formatar(rec)} − troco {formatar(tr)} precisa dar "
                              f"{formatar(valor)}", "troco_centavos")
        pg = Pagamento.objects.create(**base, status=SP.PENDENTE, valor_recebido_centavos=rec, troco_centavos=tr)
        _avisar_loja(p, "pagamento.entregador", {"forma": forma, "valor_centavos": valor, "entregador": e.nome})
        return pg
    taxa, previsao = services._taxa_e_previsao(p.loja, FORMAS[forma], bandeira, valor)
    pg = Pagamento.objects.create(**base, status=SP.CONFIRMADO, confirmado_em=agora, bandeira=(bandeira or "")[:30],
                                  taxa_centavos=taxa, previsao_recebimento=previsao,
                                  dados_externos={"marcado_pelo_entregador": True})
    _avisar_loja(p, "pagamento.confirmado", {"valor_centavos": valor})
    return pg


def gerar_pix(pedido_id, e) -> Pagamento:
    """QR Pix do gateway da loja, para o cliente pagar na hora."""
    from . import services

    with transaction.atomic():
        p = _pedido(pedido_id, e)
        if falta(p) <= 0:
            raise ErroNegocio("este pedido já está pago")
        if not tem_gateway(p.loja):
            raise ErroNegocio("esta loja não tem Pix automático: receba na chave Pix da loja e marque como pago")
        aberto = (p.pagamentos.filter(status=SP.PENDENTE, forma=F.PIX, entregador=e, pago_online=True)
                  .exclude(referencia_externa="").first())
        if aberto is not None and aberto.dados_externos.get("qr_code"):
            return aberto  # o mesmo QR (o cliente pode já ter escaneado)
    pg = services.cobrar_pix(pedido=p)
    Pagamento.objects.filter(pk=pg.pk).update(entregador=e)
    pg.entregador = e
    return pg


def situacao_pix(pedido_id, e) -> dict:
    """O app consulta enquanto mostra o QR. Se o webhook não chegou, pergunta ao gateway."""
    from apps.integracoes.models import Integracao
    from apps.integracoes.provedores.mercadopago import STATUS_PAGO, MercadoPago

    from . import services

    p = Pedido.objects.filter(pk=pedido_id, entregador=e).select_related("loja").first()
    if p is None:
        raise ErroNegocio("pedido não encontrado")
    pg = p.pagamentos.filter(forma=F.PIX, entregador=e, pago_online=True).order_by("-criado_em").first()
    if pg is not None and pg.status == SP.PENDENTE and pg.referencia_externa:
        integ = Integracao.ativa(p.loja, "PAGAMENTO", "mercadopago")
        try:
            info = MercadoPago(integ.obter_credenciais()["access_token"]).consultar(pg.referencia_externa) if integ else None
        except Exception:  # noqa: BLE001 — sem resposta do gateway: o webhook confirma depois
            info = None
        if info and info.get("status") == STATUS_PAGO:
            services.confirmar_pagamento_online(pg, valor_centavos=info.get("valor_centavos"))
            pg.refresh_from_db()
        p.refresh_from_db()
    return {"pago": bool(pg and pg.status == SP.CONFIRMADO), "concluido": p.status == S.CONCLUIDO,
            "falta_centavos": falta(p)}


# ----------------------------------------------------------------------------- repasse à loja
def _com_entregador(loja, e):
    return Pagamento.objects.filter(pedido__loja=loja, entregador=e, forma=F.DINHEIRO, status=SP.PENDENTE,
                                    cobrado_em__isnull=False, repasse__isnull=True)


def em_maos(loja, e) -> int:
    return _com_entregador(loja, e).aggregate(s=Sum("valor_centavos"))["s"] or 0


def _repasse_out(r: RepasseEntregador) -> dict:
    return {"id": str(r.id), "loja": r.loja.nome, "entregador_id": str(r.entregador_id), "entregador": r.entregador.nome,
            "status": r.status, "status_rotulo": r.get_status_display(), "entregas": r.pagamentos.count(),
            "esperado_centavos": r.esperado_centavos, "informado_entregador_centavos": r.informado_entregador_centavos,
            "informado_em": r.informado_em, "recebido_loja_centavos": r.recebido_loja_centavos,
            "recebido_em": r.recebido_em, "recebido_por": str(r.recebido_por) if r.recebido_por_id else "",
            "diferenca_centavos": r.diferenca_centavos, "observacao": r.observacao, "criado_em": r.criado_em}


def para_app(entregadores) -> dict:
    """No app: dinheiro em mãos por loja e os últimos repasses."""
    lojas = []
    for e in entregadores:
        qs = _com_entregador(e.loja, e)
        lojas.append({"entregador_id": str(e.id), "loja": e.loja.nome, "em_maos_centavos": em_maos(e.loja, e),
                      "entregas": qs.count(),
                      "aguardando": [_repasse_out(r) for r in RepasseEntregador.objects.filter(
                          entregador=e, status=RepasseEntregador.ENVIADO).select_related("loja", "entregador")]})
    ultimos = (RepasseEntregador.objects.filter(entregador__in=entregadores).exclude(status=RepasseEntregador.ENVIADO)
               .select_related("loja", "entregador")[:10])
    return {"lojas": lojas, "ultimos": [_repasse_out(r) for r in ultimos]}


@transaction.atomic
def informar(e, valor) -> RepasseEntregador:
    """O entregador declara que entregou o dinheiro à loja."""
    valor = _int(valor, "valor_centavos")
    pgs = list(_com_entregador(e.loja, e).select_for_update())
    if not pgs:
        raise ErroNegocio("você não tem dinheiro de entregas para repassar a esta loja")
    r = RepasseEntregador.objects.create(loja=e.loja, entregador=e, esperado_centavos=sum(x.valor_centavos for x in pgs),
                                         informado_entregador_centavos=valor, informado_em=timezone.now())
    Pagamento.objects.filter(pk__in=[x.pk for x in pgs]).update(repasse=r)
    eventos.publicar(eventos.grupo_pdv(e.loja_id), "repasse.enviado",
                     {"repasse": str(r.id), "entregador": e.nome, "valor_centavos": valor})
    return r


def pendentes_loja(loja) -> dict:
    """Na loja: repasses a conferir e dinheiro que ainda está com cada entregador."""
    from apps.clientes.models import Entregador

    aguardando = RepasseEntregador.objects.filter(loja=loja, status=RepasseEntregador.ENVIADO).select_related(
        "loja", "entregador")
    com = []
    for e in Entregador.objects.filter(loja=loja, cobrancas__isnull=False).distinct():
        v = em_maos(loja, e)
        if v:
            com.append({"entregador_id": str(e.id), "entregador": e.nome, "em_maos_centavos": v,
                        "entregas": _com_entregador(loja, e).count()})
    feitos = (RepasseEntregador.objects.filter(loja=loja).exclude(status=RepasseEntregador.ENVIADO)
              .select_related("loja", "entregador", "recebido_por")[:30])
    return {"aguardando": [_repasse_out(r) for r in aguardando], "com_entregadores": com,
            "recebidos": [_repasse_out(r) for r in feitos]}


@transaction.atomic
def receber(loja, usuario, *, valor, repasse_id=None, entregador_id=None, observacao: str = "") -> RepasseEntregador:
    """A loja confere o dinheiro entregue pelo entregador. Entra no caixa aberto de quem recebeu."""
    from apps.caixa import services as caixa
    from apps.caixa.models import MovimentacaoCaixa
    from apps.clientes.models import Entregador

    valor = _int(valor, "valor_centavos")
    turno = caixa.exigir_turno(usuario, loja)
    if repasse_id:
        r = RepasseEntregador.objects.select_for_update().filter(pk=repasse_id, loja=loja).first()
        if r is None:
            raise ErroNegocio("repasse não encontrado")
        if r.status != RepasseEntregador.ENVIADO:
            raise ErroNegocio("este repasse já foi recebido")
    else:
        e = Entregador.objects.filter(pk=entregador_id, loja=loja).first()
        if e is None:
            raise ErroNegocio("entregador não encontrado")
        pgs = list(_com_entregador(loja, e).select_for_update())
        if not pgs:
            raise ErroNegocio("este entregador não tem dinheiro de entregas a repassar")
        r = RepasseEntregador.objects.create(loja=loja, entregador=e, esperado_centavos=sum(x.valor_centavos for x in pgs))
        Pagamento.objects.filter(pk__in=[x.pk for x in pgs]).update(repasse=r)
    agora = timezone.now()
    for pg in r.pagamentos.select_for_update().filter(status=SP.PENDENTE):
        pg.status, pg.confirmado_em, pg.turno, pg.recebido_por = SP.CONFIRMADO, agora, turno, usuario
        pg.save(update_fields=["status", "confirmado_em", "turno", "recebido_por", "atualizado_em"])
        caixa.registrar_venda(turno, pg, usuario)
    dif = valor - r.esperado_centavos
    if dif:  # a gaveta fica com o que entrou de fato
        MovimentacaoCaixa.objects.create(
            loja_id=loja.id, turno=turno, usuario=usuario, tipo=T.SUPRIMENTO if dif > 0 else T.SANGRIA,
            forma_pagamento=F.DINHEIRO, valor_centavos=abs(dif),
            motivo=f"{'Sobra' if dif > 0 else 'Falta'} no repasse do entregador {r.entregador.nome}"[:255])
    confere = dif == 0 and (r.informado_entregador_centavos is None or r.informado_entregador_centavos == valor)
    r.recebido_loja_centavos, r.recebido_em, r.recebido_por, r.turno = valor, agora, usuario, turno
    r.status = RepasseEntregador.CONFERIDO if confere else RepasseEntregador.DIVERGENTE
    r.observacao = (observacao or r.observacao or "")[:255]
    r.save()
    return r


def abater_no_acerto(loja, e, acerto, pedido_ids) -> int:
    """No acerto, o dinheiro que ainda está com o entregador é descontado dos ganhos: deixa de
    estar "em mãos" (registrado como repasse abatido) para não ser cobrado duas vezes."""
    pgs = list(Pagamento.objects.select_for_update().filter(
        pedido_id__in=pedido_ids, entregador=e, forma=F.DINHEIRO, status=SP.PENDENTE, cobrado_em__isnull=False))
    if not pgs:
        return 0
    agora = timezone.now()
    sem = [x for x in pgs if x.repasse_id is None]
    if sem:
        total = sum(x.valor_centavos for x in sem)
        novo = RepasseEntregador.objects.create(loja=loja, entregador=e, esperado_centavos=total,
                                                recebido_loja_centavos=total, recebido_em=agora,
                                                recebido_por=acerto.usuario, status=RepasseEntregador.CONFERIDO,
                                                observacao="abatido no acerto do entregador", acerto=acerto)
        Pagamento.objects.filter(pk__in=[x.pk for x in sem]).update(repasse=novo)
    Pagamento.objects.filter(pk__in=[x.pk for x in pgs]).update(status=SP.CONFIRMADO, confirmado_em=agora)
    # repasses que o entregador declarou mas a loja não conferiu: resolvidos pelo acerto
    for r in RepasseEntregador.objects.filter(pk__in={x.repasse_id for x in pgs if x.repasse_id},
                                              status=RepasseEntregador.ENVIADO):
        if not r.pagamentos.filter(status=SP.PENDENTE).exists():
            r.status, r.recebido_loja_centavos, r.recebido_em = RepasseEntregador.CONFERIDO, r.esperado_centavos, agora
            r.recebido_por, r.acerto, r.observacao = acerto.usuario, acerto, "abatido no acerto do entregador"
            r.save()
    return sum(x.valor_centavos for x in pgs)
