"""Conexão do WhatsApp da loja (QR Code no painel) e envio de mensagens.

A loja não cadastra nenhuma conta externa: clica em "Conectar", lê o QR Code
com o WhatsApp do celular (Aparelhos conectados) e pronto. A integração
WHATSAPP/"whatsapp" fica ativa enquanto o número estiver conectado.
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings

from .models import Integracao
from .provedores.evolution import Evolution, configurado

PROVEDOR = "whatsapp"


def nome_instancia(loja) -> str:
    return f"apfood-{str(loja.id).replace('-', '')[:16]}"


def chave_webhook(loja) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"whatsapp:{loja.id}".encode(), hashlib.sha256).hexdigest()[:24]


def url_webhook(loja) -> str:
    base = settings.APFOOD_WHATSAPP["WEBHOOK_BASE"] or settings.APFOOD["URL_PUBLICA"]
    return base.rstrip("/") + f"/api/webhooks/whatsapp/{loja.id}/{chave_webhook(loja)}/"


def integracao(loja, criar: bool = False) -> Integracao | None:
    i = Integracao.objects.filter(loja=loja, tipo="WHATSAPP", provedor=PROVEDOR).first()
    if i is None and criar:
        i = Integracao.objects.create(loja=loja, tipo="WHATSAPP", provedor=PROVEDOR, ativo=False,
                                      configuracao={"instancia": nome_instancia(loja)})
    return i


def cliente_da(integ: Integracao) -> Evolution:
    return Evolution((integ.configuracao or {}).get("instancia") or nome_instancia(integ.loja))


def situacao(loja) -> dict:
    """Para o painel: conectado?, número, e se o servidor está configurado."""
    i = integracao(loja)
    base = {"servidor": configurado(), "conectado": False, "estado": "desconectado", "numero": "", "nome": ""}
    if i is None or not configurado():
        return base
    try:
        estado = cliente_da(i).estado()
    except Exception as exc:  # noqa: BLE001
        return {**base, "estado": "erro", "erro": str(exc)[:200]}
    conectado = estado == "open"
    info = dict(i.configuracao or {})
    if conectado and not info.get("numero"):
        try:
            info.update(cliente_da(i).perfil())
        except Exception:  # noqa: BLE001
            pass
    if not conectado:
        info.pop("numero", None)
        info.pop("nome", None)
    if i.ativo != conectado or info != (i.configuracao or {}):
        i.ativo, i.configuracao = conectado, info
        i.save(update_fields=["ativo", "configuracao", "atualizado_em"])
    return {**base, "conectado": conectado, "estado": {"open": "conectado", "connecting": "aguardando leitura"}
            .get(estado, "desconectado"), "numero": info.get("numero", "") if conectado else "",
            "nome": info.get("nome", "") if conectado else ""}


def conectar(loja) -> dict:
    """Cria a instância (se preciso) e devolve o QR Code para ler no celular."""
    i = integracao(loja, criar=True)
    evo = cliente_da(i)
    if evo.estado() == "inexistente":
        evo.criar(url_webhook(loja))
    else:
        evo.definir_webhook(url_webhook(loja))
    if evo.estado() == "open":
        return {**situacao(loja), "qrcode": ""}
    qr = evo.qrcode()
    return {**situacao(loja), "qrcode": qr["base64"], "codigo_pareamento": qr["codigo_pareamento"]}


def desconectar(loja) -> dict:
    i = integracao(loja)
    if i is not None:
        try:
            cliente_da(i).desconectar()
        finally:
            i.ativo = False
            i.configuracao = {"instancia": (i.configuracao or {}).get("instancia") or nome_instancia(loja)}
            i.save(update_fields=["ativo", "configuracao", "atualizado_em"])
    return situacao(loja)


def evento_conexao(loja, estado: str) -> None:
    """CONNECTION_UPDATE do servidor: liga/desliga a integração na hora."""
    i = integracao(loja)
    if i is None:
        return
    conectado = estado == "open"
    if i.ativo != conectado:
        i.ativo = conectado
        if not conectado:
            i.configuracao = {"instancia": (i.configuracao or {}).get("instancia") or nome_instancia(loja)}
        i.save(update_fields=["ativo", "configuracao", "atualizado_em"])


def enviar(integ: Integracao, telefone: str, mensagem: str) -> None:
    try:
        cliente_da(integ).enviar_texto(telefone, mensagem)
    except Exception as exc:
        integ.registrar_erro(str(exc))
        raise
    integ.registrar_sucesso()
