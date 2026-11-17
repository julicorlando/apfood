"""WhatsApp próprio pela Evolution API (servidor de código aberto, no mesmo Coolify).

Cada loja tem uma "instância" (um número de WhatsApp) que conecta lendo o QR Code
no painel, como no WhatsApp Web. Endpoints usados (v2):
  POST   /instance/create                  {instanceName, qrcode, integration}
  GET    /instance/connect/{inst}          → {base64, code, pairingCode} (QR)
  GET    /instance/connectionState/{inst}  → {instance: {state: open|connecting|close}}
  GET    /instance/fetchInstances?instanceName=  → número e nome do perfil
  DELETE /instance/logout/{inst}
  POST   /webhook/set/{inst}               {webhook: {enabled, url, events, ...}}
  POST   /message/sendText/{inst}          {number, text}
Cabeçalho "apikey" com a chave global (APFOOD_WHATSAPP_CHAVE).
"""

from __future__ import annotations

from django.conf import settings

from .base import ErroProvedor, checar, cliente

EVENTOS = ["MESSAGES_UPSERT", "CONNECTION_UPDATE"]


def configurado() -> bool:
    c = settings.APFOOD_WHATSAPP
    return bool(c["URL"] and c["CHAVE"])


def so_digitos_br(telefone: str) -> str:
    d = "".join(ch for ch in telefone or "" if ch.isdigit())
    return "55" + d if len(d) in (10, 11) else d


class Evolution:
    def __init__(self, instancia: str):
        if not configurado():
            raise ErroProvedor("servidor de WhatsApp não configurado (APFOOD_WHATSAPP_URL/CHAVE)")
        c = settings.APFOOD_WHATSAPP
        self.instancia = instancia
        self.http = cliente(c["URL"].rstrip("/"), headers={"apikey": c["CHAVE"]}, timeout=20)

    # ------------------------------------------------------------ instância
    def criar(self, webhook_url: str) -> dict:
        r = self.http.post("/instance/create", json={
            "instanceName": self.instancia, "qrcode": True, "integration": "WHATSAPP-BAILEYS",
            "groupsIgnore": True, "rejectCall": False, "alwaysOnline": False, "readMessages": False,
            "webhook": {"url": webhook_url, "byEvents": False, "base64": False, "events": EVENTOS},
        })
        if r.status_code in (400, 403) and "already" in r.text.lower():
            return {}
        dados = checar(r, "WhatsApp (criar)")
        self.definir_webhook(webhook_url)
        return dados

    def definir_webhook(self, url: str) -> dict:
        return checar(self.http.post(f"/webhook/set/{self.instancia}", json={"webhook": {
            "enabled": True, "url": url, "byEvents": False, "base64": False, "events": EVENTOS,
        }}), "WhatsApp (webhook)")

    def qrcode(self) -> dict:
        """{"base64": "data:image/png;base64,...", "codigo_pareamento": "..."} — vazio se já conectado."""
        r = checar(self.http.get(f"/instance/connect/{self.instancia}"), "WhatsApp (QR Code)")
        qr = r.get("qrcode") if isinstance(r.get("qrcode"), dict) else r
        return {"base64": qr.get("base64") or "", "codigo_pareamento": qr.get("pairingCode") or ""}

    def estado(self) -> str:
        """open | connecting | close | inexistente."""
        r = self.http.get(f"/instance/connectionState/{self.instancia}")
        if r.status_code == 404:
            return "inexistente"
        dados = checar(r, "WhatsApp (estado)")
        inst = dados.get("instance") or dados
        return inst.get("state") or "close"

    def perfil(self) -> dict:
        r = checar(self.http.get("/instance/fetchInstances", params={"instanceName": self.instancia}),
                   "WhatsApp (perfil)")
        item = (r[0] if isinstance(r, list) and r else r) or {}
        item = item.get("instance", item)
        numero = (item.get("ownerJid") or item.get("owner") or "").split("@")[0]
        return {"numero": numero, "nome": item.get("profileName") or ""}

    def desconectar(self) -> None:
        r = self.http.delete(f"/instance/logout/{self.instancia}")
        if r.status_code not in (200, 201, 400, 404):
            checar(r, "WhatsApp (desconectar)")

    # ------------------------------------------------------------ mensagens
    def enviar_texto(self, telefone: str, mensagem: str) -> dict:
        return checar(self.http.post(f"/message/sendText/{self.instancia}", json={
            "number": so_digitos_br(telefone), "text": mensagem, "delay": 800,
        }), "WhatsApp (enviar)")
