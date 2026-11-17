"""MASTER recebe as assinaturas pelo Mercado Pago configurado no painel."""

from datetime import date

import httpx
import pytest
from rest_framework.test import APIClient

from apps.contas.models import Usuario
from apps.integracoes.provedores import base
from apps.plataforma import cobranca
from apps.plataforma.models import ConfiguracaoPlataforma, Fatura, Plano


class MP:
    def __init__(self):
        self.chamadas = []

    def __call__(self, req: httpx.Request):
        self.chamadas.append(req)
        auth = req.headers.get("authorization", "")
        if "APP_USR-ruim" in auth:
            return httpx.Response(401, json={"message": "invalid access token"})
        if req.url.path == "/users/me":
            return httpx.Response(200, json={"id": 1, "nickname": "AXIONWEB"})
        if req.url.path == "/checkout/preferences":
            return httpx.Response(201, json={"id": "pref-1", "init_point": "https://mp.example/checkout/pref-1"})
        if req.url.path == "/v1/payments" and req.method == "POST":
            return httpx.Response(201, json={"id": 99, "status": "pending", "point_of_interaction": {
                "transaction_data": {"ticket_url": "https://mp.example/pix/99"}}})
        return httpx.Response(404, json={})


@pytest.fixture
def mp(monkeypatch):
    m = MP()
    monkeypatch.setattr(base, "transporte", httpx.MockTransport(m))
    return m


@pytest.fixture
def master(db):
    u = Usuario.objects.create_superuser("chefe", password="x")
    c = APIClient()
    c.force_authenticate(u)
    return c


@pytest.fixture
def fatura(loja):
    plano = Plano.objects.create(nome="Básico", preco_mensal_centavos=9900)
    return Fatura.objects.create(empresa=loja.empresa, plano=plano, competencia=date(2026, 11, 1),
                                 valor_centavos=9900, vencimento=date(2026, 11, 10))


def test_master_configura_token_conferido_e_cifrado(master, mp, settings):
    settings.APFOOD_MP_TOKEN_PLATAFORMA = ""
    assert master.get("/api/plataforma/recebimentos/").data["configurado"] is False
    r = master.put("/api/plataforma/recebimentos/", {"token": "APP_USR-ruim"}, format="json")
    assert r.status_code == 400 and "recusou" in str(r.data)
    r = master.put("/api/plataforma/recebimentos/", {"token": "APP_USR-bom", "metodo": "CHECKOUT"}, format="json")
    assert r.status_code == 200 and r.data["configurado"] and r.data["conta"] == "AXIONWEB" and r.data["origem"] == "painel"
    cfg = ConfiguracaoPlataforma.atual()
    assert "APP_USR-bom" not in cfg.mp_token_cifrado and cobranca.token_mp() == "APP_USR-bom"


def test_so_master_acessa(loja, db):
    admin = Usuario.objects.create_user("dono", password="x", papel="ADMIN", empresa=loja.empresa)
    c = APIClient()
    c.force_authenticate(admin)
    assert c.get("/api/plataforma/recebimentos/").status_code == 403


def test_cobranca_checkout_e_pix_e_baixa_manual(master, mp, fatura):
    master.put("/api/plataforma/recebimentos/", {"token": "APP_USR-bom", "metodo": "CHECKOUT"}, format="json")
    r = master.post(f"/api/faturas/{fatura.id}/cobrar/")
    assert r.status_code == 200 and r.data["link_pagamento"] == "https://mp.example/checkout/pref-1"
    master.put("/api/plataforma/recebimentos/", {"metodo": "PIX"}, format="json")
    r = master.post(f"/api/faturas/{fatura.id}/cobrar/")
    assert r.data["link_pagamento"] == "https://mp.example/pix/99"
    empresa = fatura.empresa
    empresa.ativa, empresa.motivo_bloqueio = False, cobranca.MOTIVO_INADIMPLENCIA
    empresa.save()
    r = master.post(f"/api/faturas/{fatura.id}/marcar-paga/", {"forma": "PIX"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "PAGA"
    empresa.refresh_from_db()
    assert empresa.ativa
    resumo = master.get("/api/plataforma/recebimentos/").data
    assert resumo["recebido_mes"]["valor_centavos"] == 9900


def test_gerar_links_em_lote(master, mp, fatura):
    master.put("/api/plataforma/recebimentos/", {"token": "APP_USR-bom", "metodo": "CHECKOUT"}, format="json")
    r = master.post("/api/plataforma/recebimentos/")
    assert r.data["gerados"] == 1 and r.data["sem_link"] == 0
