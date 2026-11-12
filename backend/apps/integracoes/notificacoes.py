"""Avisos ao cliente por WhatsApp a cada etapa do pedido (se a loja tiver a
integração WHATSAPP ativa e o pedido tiver telefone)."""

from django.conf import settings

from apps.integracoes.tarefas import enfileirar, executor

MENSAGENS = {
    "RECEBIDO": "✅ *{loja}*: recebemos seu pedido *#{numero}*! Acompanhe: {link}",
    "EM_PREPARO": "👨‍🍳 Seu pedido *#{numero}* está sendo preparado.",
    "PRONTO": "🍔 Seu pedido *#{numero}* está pronto{retirada}.",
    "SAIU_PARA_ENTREGA": "🛵 Seu pedido *#{numero}* saiu para entrega!",
    "CONCLUIDO": "🙏 Obrigado por pedir na *{loja}*! Bom apetite.",
    "CANCELADO": "❌ Seu pedido *#{numero}* foi cancelado. {motivo}",
    "RECUSADO": "❌ Não conseguimos aceitar seu pedido *#{numero}*. {motivo}",
}
CANAIS = {"ONLINE", "DELIVERY"}


def mensagem(pedido) -> str | None:
    modelo = MENSAGENS.get(pedido.status)
    if not modelo:
        return None
    link = settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/pedido/{pedido.token_rastreio}/"
    return modelo.format(
        loja=pedido.loja.nome, numero=pedido.numero, link=link, motivo=pedido.motivo_cancelamento,
        retirada=" para retirada" if pedido.tipo_atendimento == "RETIRADA" else "",
    ).strip()


def notificar_status(pedido) -> None:
    from apps.integracoes.models import Integracao

    if pedido.canal not in CANAIS or len(pedido.telefone_cliente) < 10:
        return
    if pedido.status == "PRONTO" and pedido.tipo_atendimento == "ENTREGA":
        return  # cliente de entrega recebe "saiu para entrega"
    integ = Integracao.ativa(pedido.loja, "WHATSAPP")
    if integ is None or not (texto := mensagem(pedido)):
        return
    enfileirar("whatsapp.enviar", {"integracao_id": str(integ.id), "telefone": pedido.telefone_cliente,
                                   "mensagem": texto}, chave=f"wa-{pedido.id}-{pedido.status}")


@executor("whatsapp.enviar")
def enviar(integracao_id: str, telefone: str, mensagem: str):
    from apps.integracoes.models import Integracao
    from apps.integracoes.provedores.zapi import ZApi

    integ = Integracao.objects.get(pk=integracao_id)
    c = integ.obter_credenciais()
    try:
        ZApi(c["instance"], c["token"], c.get("client_token", "")).enviar_texto(telefone, mensagem)
    except Exception as exc:
        integ.registrar_erro(str(exc))
        raise
    integ.registrar_sucesso()
