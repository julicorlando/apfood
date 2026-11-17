"""Atendente automático do WhatsApp (número da loja conectado pelo QR Code).

O servidor de WhatsApp chama /api/webhooks/whatsapp/<loja>/<chave>/ a cada
mensagem recebida. O atendente responde sozinho o básico — cardápio (link para pedir), status do
último pedido, horário, endereço e formas de pagamento — e, se o cliente pedir
um atendente, fica quieto por 2 horas com aquele número.

O pedido em si é feito pelo link do cardápio (com preço, adicionais e Pix
certinhos), não por texto solto no chat.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

PAUSA = timedelta(hours=2)
SAUDACAO_VALE = timedelta(hours=6)

INTENCOES = [
    ("atendente", r"\b(atendente|humano|pessoa|falar com|gerente|reclama|ajuda)\b|^4$"),
    ("status", r"\b(status|meu pedido|cade|demora|chegando|saiu|acompanhar|pedido \d+)\b|^2$"),
    ("horario", r"\b(horario|aberto|abert[ao]s?|abre|fecha|funciona|hoje)\b|^3$"),
    ("endereco", r"\b(endereco|onde fica|localizacao|retirar|retirada)\b"),
    ("pagamento", r"\b(pix|pagamento|cartao|credito|debito|vale|dinheiro)\b"),
    ("cardapio", r"\b(cardapio|menu|pedir|quero|pedido|preco|valor|promo|promocao|lanche|pizza|hamburguer)\b|^1$"),
]
STATUS_TEXTO = {
    "AGUARDANDO_ACEITE": "recebido, aguardando a loja confirmar",
    "RECEBIDO": "confirmado ✅", "EM_PREPARO": "em preparo 👨‍🍳", "PRONTO": "pronto 🍔",
    "SAIU_PARA_ENTREGA": "saiu para entrega 🛵", "CONCLUIDO": "concluído 🙏",
    "CANCELADO": "cancelado ❌", "RECUSADO": "recusado ❌",
}
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip()


def intencao(texto: str) -> str | None:
    t = _normalizar(texto)
    for nome, padrao in INTENCOES:
        if re.search(padrao, t):
            return nome
    return None


def _digitos(telefone: str) -> str:
    d = "".join(c for c in telefone or "" if c.isdigit())
    return d[2:] if d.startswith("55") and len(d) in (12, 13) else d


def _link(loja) -> str:
    return settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/{loja.slug}/"


def _menu() -> str:
    return "Responda com um número:\n1️⃣ Ver o cardápio e pedir\n2️⃣ Meu pedido\n3️⃣ Horário\n4️⃣ Falar com um atendente"


def boas_vindas(loja) -> str:
    modelo = loja.whatsapp_boas_vindas.strip() or "Olá! 👋 Aqui é a *{loja}*. Peça pelo nosso cardápio: {link}"
    try:
        texto = modelo.format(loja=loja.nome, link=_link(loja))
    except (KeyError, IndexError, ValueError):
        texto = modelo
    return f"{texto}\n\n{_menu()}"


def resp_cardapio(loja) -> str:
    from apps.marketing.models import Promocao

    hoje = timezone.localdate()
    promos = [p.nome for p in Promocao.objects.ativos().filter(loja=loja, ativa=True)
              if (not p.dias or hoje.weekday() in p.dias) and (not p.canais or "ONLINE" in p.canais)]
    extra = f"\n🔥 Hoje tem: {', '.join(promos[:3])}" if promos else ""
    return f"📋 Cardápio da *{loja.nome}*, é só escolher e finalizar:\n{_link(loja)}{extra}"


def resp_status(loja, telefone: str) -> str:
    from apps.pedidos.models import Pedido

    p = (Pedido.objects.filter(loja=loja, telefone_cliente=_digitos(telefone))
         .exclude(canal="MARKETPLACE").order_by("-criado_em").first())
    if p is None:
        return f"Não achei pedido neste número. Para pedir: {_link(loja)}"
    link = settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/pedido/{p.token_rastreio}/"
    quando = timezone.localtime(p.criado_em).strftime("%d/%m %H:%M")
    return f"Seu pedido *#{p.numero}* ({quando}) está *{STATUS_TEXTO.get(p.status, p.status.lower())}*.\nAcompanhe: {link}"


def resp_horario(loja) -> str:
    from apfood_core.horarios import aberta_em

    agora = timezone.localtime()
    aberta = loja.aberta_para_pedidos and aberta_em(loja.horarios, agora)
    linhas = []
    for h in loja.horarios or []:
        try:
            linhas.append(f"{DIAS[int(h['dia_semana'])]}: {h['abre']}–{h['fecha']}")
        except (KeyError, ValueError, IndexError, TypeError):
            continue
    situacao = "🟢 Estamos abertos agora!" if aberta else "🔴 Estamos fechados agora."
    return situacao + ("\n" + "\n".join(linhas) if linhas else "") + f"\nCardápio: {_link(loja)}"


def resp_endereco(loja) -> str:
    if not loja.logradouro:
        return f"Fale com a gente por aqui mesmo. Cardápio: {_link(loja)}"
    end = f"{loja.logradouro}, {loja.numero} — {loja.bairro}" + (f", {loja.cidade}" if loja.cidade else "")
    return f"📍 {end}"


def resp_pagamento(loja) -> str:
    from apps.integracoes.models import Integracao

    pix = Integracao.ativa(loja, "PAGAMENTO", "mercadopago") is not None
    return ("💳 Aceitamos Pix" + (" (pago na hora pelo cardápio)" if pix else "")
            + ", dinheiro, cartão de crédito e débito e vale-refeição.")


def _em_pausa(loja, telefone: str) -> bool:
    from apps.integracoes.models import WebhookRecebido

    return WebhookRecebido.objects.filter(provedor="whatsapp", loja=loja, evento="atendente.pausa",
                                          id_evento__startswith=f"pausa:{telefone}:",
                                          criado_em__gte=timezone.now() - PAUSA).exists()


def _saudou_recente(loja, telefone: str) -> bool:
    from apps.integracoes.models import WebhookRecebido

    return WebhookRecebido.objects.filter(provedor="whatsapp", loja=loja, evento="atendente.saudacao",
                                          id_evento__startswith=f"saudacao:{telefone}:",
                                          criado_em__gte=timezone.now() - SAUDACAO_VALE).exists()


def _marcar(loja, evento: str, telefone: str):
    from apps.integracoes.models import WebhookRecebido

    WebhookRecebido.objects.create(provedor="whatsapp", loja=loja, evento=evento, payload={"telefone": telefone},
                                   id_evento=f"{evento.split('.')[-1]}:{telefone}:{timezone.now().timestamp()}",
                                   processado_em=timezone.now())


def responder(loja, telefone: str, texto: str) -> str | None:
    """Resposta do atendente para uma mensagem (None = não responde)."""
    if not loja.whatsapp_atendente or _em_pausa(loja, telefone):
        return None
    alvo = intencao(texto)
    if alvo == "atendente":
        _marcar(loja, "atendente.pausa", telefone)
        return "Certo! 🙋 Já avisei a equipe, alguém vai te responder por aqui em instantes."
    if alvo is None:
        if _saudou_recente(loja, telefone):
            return f"Não entendi 😅\n{_menu()}"
        _marcar(loja, "atendente.saudacao", telefone)
        return boas_vindas(loja)
    if not _saudou_recente(loja, telefone):
        _marcar(loja, "atendente.saudacao", telefone)
    return {
        "cardapio": lambda: resp_cardapio(loja),
        "status": lambda: resp_status(loja, telefone),
        "horario": lambda: resp_horario(loja),
        "endereco": lambda: resp_endereco(loja),
        "pagamento": lambda: resp_pagamento(loja),
    }[alvo]()


def texto_da_mensagem(data: dict) -> tuple[str, str, str]:
    """(telefone, texto, id) de um MESSAGES_UPSERT; vazio se não for para responder."""
    chave = data.get("key") or {}
    jid = chave.get("remoteJid") or ""
    if chave.get("fromMe") or not jid.endswith("@s.whatsapp.net"):
        return "", "", ""  # mensagem nossa, grupo, status ou canal
    msg = data.get("message") or {}
    texto = (msg.get("conversation") or (msg.get("extendedTextMessage") or {}).get("text")
             or (msg.get("buttonsResponseMessage") or {}).get("selectedDisplayText") or "")
    return jid.split("@")[0], texto.strip(), str(chave.get("id") or "")


def processar_mensagem(loja, data: dict) -> str | None:
    """Mensagem recebida: responde pela fila de tarefas (o webhook volta na hora)."""
    from apps.integracoes.models import Integracao
    from apps.integracoes.tarefas import enfileirar

    telefone, texto, mid = texto_da_mensagem(data)
    if not texto or not telefone:
        return None
    integ = Integracao.ativa(loja, "WHATSAPP", "whatsapp")
    if integ is None:
        return None
    resposta = responder(loja, telefone, texto)
    if resposta:
        enfileirar("whatsapp.enviar", {"integracao_id": str(integ.id), "telefone": telefone, "mensagem": resposta},
                   chave=f"wa-bot-{mid or timezone.now().timestamp()}")
    return resposta
