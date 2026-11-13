"""Campanhas de WhatsApp (Z-API): só para clientes que aceitaram promoções.

Cada mensagem vira uma tarefa na fila, espaçadas por INTERVALO_S segundos
para não parecer spam ao WhatsApp. Falhas são tentadas de novo pela fila."""

from datetime import timedelta

from apfood_core.dinheiro import formatar
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.excecoes import ErroNegocio
from apps.integracoes.tarefas import enfileirar, executor

from .models import Campanha, EnvioCampanha

INTERVALO_S = 8


def publico(campanha):
    from apps.clientes.models import Cliente

    qs = Cliente.objects.ativos().filter(loja=campanha.loja, aceita_marketing=True, anonimizado_em__isnull=True) \
        .exclude(telefone="")
    if campanha.publico == Campanha.CASHBACK:
        qs = qs.filter(saldo_cashback_centavos__gt=0)
    elif campanha.publico == Campanha.INATIVOS:
        limite = timezone.now() - timedelta(days=campanha.dias_inativo)
        qs = qs.exclude(pedidos__criado_em__gte=limite)
    return qs.distinct().order_by("nome")


def texto(campanha, cliente) -> str:
    link = settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/{campanha.loja.slug}/"
    primeiro = (cliente.nome or "").split(" ")[0] or "cliente"
    valores = {"nome": primeiro, "loja": campanha.loja.nome, "cashback": formatar(cliente.saldo_cashback_centavos),
               "link": link}
    saida = campanha.mensagem
    for chave, valor in valores.items():
        saida = saida.replace("{" + chave + "}", valor)
    return saida.strip()


def _integracao(loja):
    from apps.integracoes.models import Integracao

    integ = Integracao.ativa(loja, "WHATSAPP")
    if integ is None:
        raise ErroNegocio("ative a integração de WhatsApp (Z-API) em Configurações → Integrações")
    return integ


@transaction.atomic
def iniciar(campanha, usuario) -> Campanha:
    c = Campanha.objects.select_for_update().get(pk=campanha.pk)
    if c.status != Campanha.RASCUNHO:
        raise ErroNegocio("esta campanha já foi enviada")
    if not c.mensagem.strip():
        raise ErroNegocio("escreva a mensagem", "mensagem")
    _integracao(c.loja)
    envios, vistos = [], set()
    for cliente in publico(c):
        tel = "".join(ch for ch in cliente.telefone if ch.isdigit())
        if len(tel) < 10 or tel in vistos:
            continue
        vistos.add(tel)
        envios.append(EnvioCampanha(campanha=c, cliente=cliente, telefone=tel, texto=texto(c, cliente)))
    if not envios:
        raise ErroNegocio("nenhum cliente neste público aceitou receber promoções")
    EnvioCampanha.objects.bulk_create(envios)
    for i, e in enumerate(envios):
        enfileirar("marketing.campanha", {"envio_id": str(e.id)}, chave=f"camp-{e.id}", atraso_s=i * INTERVALO_S)
    c.status, c.total, c.iniciada_em, c.criado_por = Campanha.ENVIANDO, len(envios), timezone.now(), usuario
    c.save()
    return c


def _talvez_concluir(campanha_id):
    if not EnvioCampanha.objects.filter(campanha_id=campanha_id, status=EnvioCampanha.PENDENTE).exists():
        Campanha.objects.filter(pk=campanha_id, status=Campanha.ENVIANDO).update(
            status=Campanha.CONCLUIDA, concluida_em=timezone.now())


@executor("marketing.campanha")
def enviar(envio_id: str):
    from apps.integracoes.provedores.zapi import ZApi

    e = EnvioCampanha.objects.select_related("campanha__loja").select_for_update().filter(pk=envio_id).first()
    if e is None or e.status != EnvioCampanha.PENDENTE:
        return
    integ = _integracao(e.campanha.loja)
    c = integ.obter_credenciais()
    try:
        ZApi(c["instance"], c["token"], c.get("client_token", "")).enviar_texto(e.telefone, e.texto)
    except Exception as exc:
        integ.registrar_erro(str(exc))
        raise  # a fila tenta de novo; na última tentativa, `falhou` marca o envio
    e.status = EnvioCampanha.ENVIADO
    e.save(update_fields=["status", "atualizado_em"])
    Campanha.objects.filter(pk=e.campanha_id).update(enviados=F("enviados") + 1)
    _talvez_concluir(e.campanha_id)


def falhou(envio_id: str, erro: str):
    """Chamado pela fila quando o envio esgota as tentativas."""
    e = EnvioCampanha.objects.filter(pk=envio_id, status=EnvioCampanha.PENDENTE).first()
    if e is None:
        return
    e.status, e.erro = EnvioCampanha.FALHOU, erro[:255]
    e.save(update_fields=["status", "erro", "atualizado_em"])
    Campanha.objects.filter(pk=e.campanha_id).update(falhas=F("falhas") + 1)
    _talvez_concluir(e.campanha_id)
