"""WhatsApp da loja conectado pelo QR Code (servidor Evolution API falso)."""

import json

import httpx
import pytest
from django.test import Client
from rest_framework.test import APIClient

from apps.integracoes import whatsapp
from apps.integracoes.models import Integracao
from apps.integracoes.provedores import base


class Evo:
    def __init__(self):
        self.estado, self.instancias, self.chamadas = "close", set(), []

    def __call__(self, req: httpx.Request):
        self.chamadas.append(req)
        assert req.headers["apikey"] == "chave-global"
        p = req.url.path
        if p == "/instance/create":
            nome = json.loads(req.content)["instanceName"]
            self.instancias.add(nome)
            return httpx.Response(201, json={"instance": {"instanceName": nome, "status": "created"}})
        nome = p.rstrip("/").split("/")[-1]
        if p.startswith("/instance/connectionState/"):
            if nome not in self.instancias:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json={"instance": {"instanceName": nome, "state": self.estado}})
        if p.startswith("/instance/connect/"):
            self.estado = "connecting"
            return httpx.Response(200, json={"base64": "data:image/png;base64,QR", "code": "1@x", "pairingCode": None})
        if p.startswith("/webhook/set/"):
            return httpx.Response(201, json={"webhook": json.loads(req.content)["webhook"]})
        if p == "/instance/fetchInstances":
            return httpx.Response(200, json=[{"name": nome, "ownerJid": "5581999990000@s.whatsapp.net",
                                              "profileName": "Burger Teste"}])
        if p.startswith("/instance/logout/"):
            self.estado = "close"
            return httpx.Response(200, json={"status": "SUCCESS"})
        return httpx.Response(404, json={"message": p})


@pytest.fixture
def evo(monkeypatch, settings):
    settings.APFOOD_WHATSAPP = {"URL": "http://whatsapp:8080", "CHAVE": "chave-global", "WEBHOOK_BASE": "http://web:8000"}
    e = Evo()
    monkeypatch.setattr(base, "transporte", httpx.MockTransport(e))
    return e


def api(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def test_conectar_ler_qr_e_desconectar(evo, loja, gerente):
    url = f"/api/whatsapp/?loja={loja.id}"
    assert api(gerente).get(url).data["conectado"] is False
    r = api(gerente).post(url, {"acao": "conectar"}, format="json").data
    assert r["qrcode"] == "data:image/png;base64,QR" and not r["conectado"]
    inst = whatsapp.nome_instancia(loja)
    assert inst in evo.instancias
    hook = next(json.loads(c.content) for c in evo.chamadas if c.url.path.startswith("/webhook/set/"))
    assert hook["webhook"]["url"] == f"http://web:8000/api/webhooks/whatsapp/{loja.id}/{whatsapp.chave_webhook(loja)}/"
    # leu o QR no celular
    evo.estado = "open"
    s = api(gerente).get(url).data
    assert s["conectado"] and s["numero"] == "5581999990000" and s["nome"] == "Burger Teste"
    assert Integracao.ativa(loja, "WHATSAPP", "whatsapp") is not None
    s = api(gerente).post(url, {"acao": "desconectar"}, format="json").data
    assert not s["conectado"] and Integracao.ativa(loja, "WHATSAPP", "whatsapp") is None


def test_webhook_de_conexao_liga_e_desliga(evo, loja):
    i = whatsapp.integracao(loja, criar=True)
    chave = whatsapp.chave_webhook(loja)
    Client().post(f"/api/webhooks/whatsapp/{loja.id}/{chave}/", {"event": "connection.update", "data": {"state": "open"}},
                  content_type="application/json")
    i.refresh_from_db()
    assert i.ativo
    Client().post(f"/api/webhooks/whatsapp/{loja.id}/{chave}/", {"event": "CONNECTION_UPDATE", "data": {"state": "close"}},
                  content_type="application/json")
    i.refresh_from_db()
    assert not i.ativo


def test_permissoes_e_servidor_ausente(loja, operador, gerente, settings):
    settings.APFOOD_WHATSAPP = {"URL": "", "CHAVE": "", "WEBHOOK_BASE": ""}
    assert api(operador).get(f"/api/whatsapp/?loja={loja.id}").status_code == 403
    assert api(gerente).get(f"/api/whatsapp/?loja={loja.id}").data["servidor"] is False
    r = api(gerente).post(f"/api/whatsapp/?loja={loja.id}", {"acao": "conectar"}, format="json")
    assert r.status_code == 400
