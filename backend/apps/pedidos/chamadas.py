"""Chamar entregador (app ApFood Entregador).

A loja toca em "Chamar entregador": o pedido é oferecido a um entregador
disponível por vez — o mais perto da loja primeiro, quem está livre antes de
quem já está entregando —, com 30 s para aceitar. Se recusar ou não responder,
vai para o próximo. Se em 2 min ninguém aceitar, a chamada volta para a loja
como "ninguém aceitou" (chamar de novo ou escolher outra forma de entrega).

O andamento é empurrado pela fila de tarefas (uma tarefa "entrega.avancar" no
fim de cada oferta) e também a cada consulta do app ou do painel.

Retirada e entrega exigem os códigos do pedido: o de retirada a loja informa ao
entregador; o de recebimento o cliente informa na porta."""

from __future__ import annotations

import math
from datetime import timedelta

from apfood_core.entrega import distancia_km
from apfood_core.enums import StatusPedido as S
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Entregador
from apps.core.excecoes import ErroNegocio
from apps.integracoes.tarefas import enfileirar, executor
from apps.realtime.eventos import grupo_pdv, publicar

from .models import ChamadaEntrega, Pedido

OFERTA_S = 30
TOTAL_S = 120
ONLINE_S = 90  # sem sinal do app há mais que isso = indisponível
PODE_CHAMAR = (S.RECEBIDO, S.EM_PREPARO, S.PRONTO)
MAX_TENTATIVAS_CODIGO = 8


# ----------------------------------------------------------------------------- entregadores
def disponiveis(loja):
    limite = timezone.now() - timedelta(seconds=ONLINE_S)
    return (Entregador.objects.ativos().filter(loja=loja, ativo=True, online=True, online_em__gte=limite)
            .exclude(pin_hash=""))


def _distancia_loja(loja, e) -> float | None:
    if None in (loja.latitude, loja.longitude, e.latitude, e.longitude):
        return None
    return distancia_km(float(loja.latitude), float(loja.longitude), float(e.latitude), float(e.longitude))


def _ordenados(loja, candidatos: list[Entregador]) -> list[Entregador]:
    ocupados = set(Pedido.objects.filter(entregador__in=candidatos, status=S.SAIU_PARA_ENTREGA)
                   .values_list("entregador_id", flat=True))

    def chave(e):
        d = _distancia_loja(loja, e)
        return (e.id in ocupados, d if d is not None else 9e9, e.nome)

    return sorted(candidatos, key=chave)


def _proximo(ch: ChamadaEntrega) -> Entregador | None:
    cands = [e for e in disponiveis(ch.loja) if str(e.id) not in ch.recusados]
    if not cands:
        return None
    ordem = _ordenados(ch.loja, cands)
    novos = [e for e in ordem if str(e.id) not in ch.ofertados]
    if novos:
        return novos[0]
    # todos já receberam: oferece de novo a quem recebeu há mais tempo (não repete o último, se houver outro)
    ultimo = ch.ofertados[-1] if ch.ofertados else None
    def ultima_vez(e):
        return max(i for i, x in enumerate(ch.ofertados) if x == str(e.id))
    ordem.sort(key=ultima_vez)
    outros = [e for e in ordem if str(e.id) != ultimo]
    return (outros or ordem)[0]


# ----------------------------------------------------------------------------- chamada
def resumo(ch: ChamadaEntrega | None) -> dict | None:
    if ch is None:
        return None
    agora = timezone.now()
    restante = lambda t: max(0, math.ceil((t - agora).total_seconds())) if t else 0  # noqa: E731
    return {
        "id": str(ch.id), "status": ch.status, "status_rotulo": ch.get_status_display(),
        "entregador_atual": ch.entregador_atual.nome if ch.entregador_atual_id else None,
        "segundos_oferta": restante(ch.oferta_ate) if ch.entregador_atual_id else 0,
        "segundos_total": restante(ch.expira_em) if ch.status == ChamadaEntrega.PROCURANDO else 0,
        "tentativas": len(ch.ofertados), "recusas": len(ch.recusados),
        "juntos": list(Pedido.objects.filter(pk__in=ch.juntos).values_list("numero", flat=True)) if ch.juntos else [],
        "aceita_por": ch.aceita_por.nome if ch.aceita_por_id else None,
        "disponiveis": disponiveis(ch.loja).count() if ch.status == ChamadaEntrega.PROCURANDO else None,
    }


def _evento(ch: ChamadaEntrega) -> None:
    publicar(grupo_pdv(ch.loja_id), "entrega.chamada", {
        "pedido": str(ch.pedido_id), "numero": ch.pedido.numero, "status": ch.status,
        "entregador": ch.aceita_por.nome if ch.aceita_por_id else None,
    })


def _avisar_entregador(ch: ChamadaEntrega, e: Entregador) -> None:
    """Além do alerta no app: push (Firebase, se configurado) e WhatsApp (se a loja tiver o WhatsApp conectado)."""
    from apps.integracoes import push
    from apps.integracoes.models import Integracao

    push.para_entregador(e, "🛵 Nova entrega — aceite em 30 s", f"{ch.loja.nome} → {ch.pedido.entrega_bairro or 'cliente'}",
                         {"tipo": "oferta", "chamada": str(ch.id), "segundos": OFERTA_S},
                         chave=f"push-oferta-{ch.id}-{len(ch.ofertados)}")
    if len("".join(c for c in e.telefone if c.isdigit())) < 10:
        return
    integ = Integracao.ativa(ch.loja, "WHATSAPP", "whatsapp")
    if integ is None:
        return
    p = ch.pedido
    n = 1 + len(juntos_validos(ch))
    texto = (f"🛵 *{ch.loja.nome}*: {'%d entregas' % n if n > 1 else 'entrega'} disponível para {p.entrega_bairro or 'o cliente'}"
             f" (pedido #{p.numero}). Abra o app *ApFood Entregador* para aceitar — você tem {OFERTA_S} s.")
    enfileirar("whatsapp.enviar", {"integracao_id": str(integ.id), "telefone": e.telefone, "mensagem": texto},
               chave=f"oferta-{ch.id}-{len(ch.ofertados)}")


def _agendar(ch: ChamadaEntrega, quando) -> None:
    atraso = max(1, math.ceil((quando - timezone.now()).total_seconds()))
    enfileirar("entrega.avancar", {"chamada_id": str(ch.id)},
               chave=f"chamada-{ch.id}-{len(ch.ofertados)}-{len(ch.recusados)}-{int(quando.timestamp())}",
               atraso_s=atraso)


def ativa(pedido) -> ChamadaEntrega | None:
    return pedido.chamadas.filter(status=ChamadaEntrega.PROCURANDO).first()


def ultima(pedido) -> ChamadaEntrega | None:
    ch = pedido.chamadas.select_related("entregador_atual", "aceita_por", "loja", "pedido").first()
    return avancar(ch) if ch and ch.status == ChamadaEntrega.PROCURANDO else ch


def _pode_juntar(p: Pedido, outro: Pedido) -> bool:
    return (outro.loja_id == p.loja_id and outro.pk != p.pk and outro.tipo_atendimento == "ENTREGA"
            and outro.status in PODE_CHAMAR and not outro.entregador_id)


def juntos_validos(ch: ChamadaEntrega) -> list[Pedido]:
    """Pedidos que ainda podem ir junto nesta viagem (alguém pode ter mandado por outro entregador)."""
    if not ch.juntos:
        return []
    return [o for o in Pedido.objects.filter(pk__in=ch.juntos).order_by("criado_em") if _pode_juntar(ch.pedido, o)]


def sugestoes_juntar(p: Pedido, limite: int = 8) -> list[dict]:
    """Outros pedidos de entrega ainda sem entregador, do mais perto do destino deste ao mais longe."""
    from apfood_core.entrega import distancia_km

    out = []
    for o in Pedido.objects.filter(loja=p.loja, tipo_atendimento="ENTREGA", status__in=PODE_CHAMAR,
                                   entregador__isnull=True).exclude(pk=p.pk).order_by("criado_em")[:50]:
        km = None
        if None not in (p.entrega_latitude, p.entrega_longitude, o.entrega_latitude, o.entrega_longitude):
            km = round(distancia_km(float(p.entrega_latitude), float(p.entrega_longitude),
                                    float(o.entrega_latitude), float(o.entrega_longitude)), 1)
        mesmo = bool(p.entrega_bairro) and o.entrega_bairro.strip().lower() == p.entrega_bairro.strip().lower()
        out.append({"id": str(o.id), "numero": o.numero, "bairro": o.entrega_bairro, "status": o.status,
                    "cliente": o.nome_cliente, "distancia_km": km, "mesmo_bairro": mesmo})
    out.sort(key=lambda x: (not x["mesmo_bairro"] and (x["distancia_km"] is None or x["distancia_km"] > 3),
                            x["distancia_km"] if x["distancia_km"] is not None else 99))
    return out[:limite]


@transaction.atomic
def iniciar(pedido: Pedido, usuario=None, juntar=None) -> ChamadaEntrega:
    p = Pedido.objects.select_for_update().select_related("loja").get(pk=pedido.pk)
    if p.tipo_atendimento != "ENTREGA":
        raise ErroNegocio("só pedidos de entrega podem chamar entregador")
    if p.status not in PODE_CHAMAR:
        raise ErroNegocio("chame o entregador antes de o pedido sair para entrega")
    if p.entregador_id:
        raise ErroNegocio("este pedido já tem entregador")
    extras = []
    for oid in dict.fromkeys(str(x) for x in (juntar or [])):
        o = Pedido.objects.select_for_update().filter(pk=oid).first()
        if o is None or not _pode_juntar(p, o):
            raise ErroNegocio(f"o pedido #{o.numero if o else '?'} não pode ir junto (já tem entregador ou não é entrega)")
        extras.append(o)
    if (existente := ativa(p)) is not None:
        if not extras:
            return avancar(existente)
        cancelar(p)  # chamando de novo com mais pedidos juntos
    for o in extras:
        cancelar(o)  # a chamada que o outro pedido tinha passa a ser esta
    ch = ChamadaEntrega.objects.create(loja=p.loja, pedido=p, expira_em=timezone.now() + timedelta(seconds=TOTAL_S),
                                       criado_por=usuario, juntos=[str(o.id) for o in extras])
    return avancar(ch)


@transaction.atomic
def avancar(ch: ChamadaEntrega) -> ChamadaEntrega:
    ch = (ChamadaEntrega.objects.select_for_update(of=("self",))
          .select_related("pedido", "loja", "entregador_atual", "aceita_por").get(pk=ch.pk))
    if ch.status != ChamadaEntrega.PROCURANDO:
        return ch
    agora = timezone.now()
    p = ch.pedido
    if p.status not in PODE_CHAMAR or p.entregador_id:
        ch.status, ch.entregador_atual, ch.oferta_ate = ChamadaEntrega.CANCELADA, None, None
        ch.save()
        _evento(ch)
        return ch
    if agora >= ch.expira_em:
        ch.status, ch.entregador_atual, ch.oferta_ate = ChamadaEntrega.SEM_RESPOSTA, None, None
        ch.save()
        _evento(ch)
        from apps.integracoes import push

        push.para_loja(ch.loja, f"Ninguém aceitou o pedido #{p.numero}", "Chame de novo ou escolha outra forma de entrega.",
                       {"tipo": "entrega.sem_resposta", "pedido": str(p.id)}, chave=f"push-sem-{ch.id}")
        return ch
    if ch.entregador_atual_id and ch.oferta_ate and agora < ch.oferta_ate:
        return ch  # oferta em andamento
    prox = _proximo(ch)
    if prox is not None:
        ch.entregador_atual = prox
        ch.oferta_ate = min(agora + timedelta(seconds=OFERTA_S), ch.expira_em)
        ch.ofertados = [*ch.ofertados, str(prox.id)]
        ch.save()
        _avisar_entregador(ch, prox)
        _agendar(ch, ch.oferta_ate)
    else:  # ninguém disponível agora: confere de novo daqui a pouco (alguém pode ficar online)
        ch.entregador_atual, ch.oferta_ate = None, None
        ch.save()
        _agendar(ch, min(agora + timedelta(seconds=5), ch.expira_em))
    _evento(ch)
    return ch


@executor("entrega.avancar")
def _tarefa_avancar(chamada_id: str):
    ch = ChamadaEntrega.objects.filter(pk=chamada_id).first()
    if ch is not None:
        avancar(ch)


def oferta_para(entregadores) -> ChamadaEntrega | None:
    """Oferta que está agora com um destes entregadores (já avançando as vencidas)."""
    ids = [e.id for e in entregadores]
    for ch in ChamadaEntrega.objects.filter(status=ChamadaEntrega.PROCURANDO, entregador_atual_id__in=ids):
        ch = avancar(ch)
        if ch.status == ChamadaEntrega.PROCURANDO and ch.entregador_atual_id in ids:
            return ch
    return None


@transaction.atomic
def aceitar(chamada_id, e: Entregador) -> ChamadaEntrega:
    ch = ChamadaEntrega.objects.select_for_update().select_related("pedido", "loja").filter(pk=chamada_id).first()
    if ch is None or ch.status != ChamadaEntrega.PROCURANDO:
        raise ErroNegocio("esta entrega não está mais disponível")
    if ch.entregador_atual_id != e.id or not ch.oferta_ate or timezone.now() > ch.oferta_ate + timedelta(seconds=3):
        raise ErroNegocio("o tempo para aceitar acabou")
    p = Pedido.objects.select_for_update().get(pk=ch.pedido_id)
    if p.entregador_id or p.status not in PODE_CHAMAR:
        raise ErroNegocio("esta entrega não está mais disponível")
    ch.status, ch.aceita_por, ch.aceita_em = ChamadaEntrega.ACEITA, e, timezone.now()
    ch.entregador_atual, ch.oferta_ate = None, None
    ch.save()
    p.entregador = e
    p.save(update_fields=["entregador", "atualizado_em"])
    from apps.realtime import eventos

    eventos.pedido_status(p)
    for o in juntos_validos(ch):  # a viagem leva os outros pedidos juntos
        o = Pedido.objects.select_for_update().get(pk=o.pk)
        if not o.entregador_id:
            o.entregador = e
            o.save(update_fields=["entregador", "atualizado_em"])
            eventos.pedido_status(o)
    _evento(ch)
    return ch


@transaction.atomic
def recusar(chamada_id, e: Entregador) -> None:
    ch = ChamadaEntrega.objects.select_for_update().filter(pk=chamada_id).first()
    if ch is None or ch.status != ChamadaEntrega.PROCURANDO or ch.entregador_atual_id != e.id:
        return
    ch.recusados = [*ch.recusados, str(e.id)]
    ch.entregador_atual, ch.oferta_ate = None, None
    ch.save()
    avancar(ch)


@transaction.atomic
def cancelar(pedido) -> None:
    for ch in ChamadaEntrega.objects.select_for_update().filter(pedido=pedido, status=ChamadaEntrega.PROCURANDO):
        ch.status, ch.entregador_atual, ch.oferta_ate = ChamadaEntrega.CANCELADA, None, None
        ch.save()
        _evento(ch)


# ----------------------------------------------------------------------------- códigos
def _conferir(p: Pedido, codigo: str, campo: str, rotulo: str) -> None:
    chave = f"codigo-{campo}-{p.id}"
    erros = cache.get(chave, 0)
    if erros >= MAX_TENTATIVAS_CODIGO:
        raise ErroNegocio(f"muitas tentativas: peça para a loja conferir o código de {rotulo}")
    if "".join(c for c in str(codigo) if c.isdigit()) != getattr(p, campo):
        cache.set(chave, erros + 1, 60 * 30)
        raise ErroNegocio(f"código de {rotulo} incorreto", "codigo")
    cache.delete(chave)


def retirar(pedido_id, e: Entregador, codigo: str) -> Pedido:
    """Entregador pegou o pedido na loja (código de retirada) → saiu para entrega."""
    from . import services

    p = Pedido.objects.filter(pk=pedido_id, entregador=e).select_related("loja").first()
    if p is None:
        raise ErroNegocio("pedido não encontrado")
    if p.status == S.SAIU_PARA_ENTREGA:
        return p
    if p.status != S.PRONTO:
        raise ErroNegocio("o pedido ainda não está pronto na loja")
    _conferir(p, codigo, "codigo_retirada", "retirada")
    with transaction.atomic():
        return services.transicionar(p, S.SAIU_PARA_ENTREGA, None, motivo=f"retirado por {e.nome}", entregador_id=e.id)


def entregar(pedido_id, e: Entregador, codigo: str, *, exigir_pagamento: bool = True) -> Pedido:
    """Entregue ao cliente (código de recebimento) → concluído. No app, o pagamento precisa estar
    registrado antes; no link antigo (sem app) a loja recebe como sempre."""
    from . import services

    p = Pedido.objects.filter(pk=pedido_id, entregador=e).select_related("loja").first()
    if p is None:
        raise ErroNegocio("pedido não encontrado")
    if p.status == S.CONCLUIDO:
        return p
    if p.status != S.SAIU_PARA_ENTREGA:
        raise ErroNegocio("confirme a retirada na loja antes")
    from apfood_core.dinheiro import formatar

    from .cobranca_entrega import falta

    if exigir_pagamento and (resta := falta(p)) > 0:
        raise ErroNegocio(f"registre o pagamento de {formatar(resta)} antes de concluir a entrega")
    _conferir(p, codigo, "codigo_entrega", "recebimento")
    with transaction.atomic():
        return services.transicionar(p, S.CONCLUIDO, None, motivo=f"entregue por {e.nome}")


def entregar_com_foto(pedido_id, e: Entregador, arquivo, observacao: str = "") -> Pedido:
    """Cliente não estava / não atendeu: o entregador deixa o pedido e registra uma foto no lugar do
    código de recebimento. A foto fica no pedido (loja e cliente veem)."""
    import io

    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps, UnidentifiedImageError

    from . import services
    from .cobranca_entrega import falta

    p = Pedido.objects.filter(pk=pedido_id, entregador=e).select_related("loja").first()
    if p is None:
        raise ErroNegocio("pedido não encontrado")
    if p.status == S.CONCLUIDO:
        return p
    if p.status != S.SAIU_PARA_ENTREGA:
        raise ErroNegocio("confirme a retirada na loja antes")
    if falta(p) > 0:
        raise ErroNegocio("este pedido ainda não está pago: sem o cliente não dá para cobrar — fale com a loja")
    if arquivo is None:
        raise ErroNegocio("tire a foto do pedido no local da entrega", "foto")
    if getattr(arquivo, "size", 0) > 12 * 1024 * 1024:
        raise ErroNegocio("foto muito grande", "foto")
    try:
        img = ImageOps.exif_transpose(Image.open(arquivo)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ErroNegocio("não consegui ler a foto: tente de novo", "foto") from exc
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    p.foto_entrega.save(f"{p.id}.jpg", ContentFile(buf.getvalue()), save=False)
    p.save(update_fields=["foto_entrega", "atualizado_em"])
    motivo = "entregue com foto (cliente ausente)" + (f": {observacao.strip()[:120]}" if observacao and observacao.strip() else "")
    with transaction.atomic():
        return services.transicionar(p, S.CONCLUIDO, None, motivo=f"{motivo} — {e.nome}")
