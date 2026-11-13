"""Painel web: login próprio, página única protegida e QR Code do cupom."""

from apfood_core.enums import PapelUsuario

from apps.contas.models import Usuario


def test_painel_exige_login(client):
    r = client.get("/painel/")
    assert r.status_code == 302 and r.url.startswith("/painel/entrar/")


def test_login_e_pagina_do_painel(client, operador):
    r = client.post("/painel/entrar/", {"username": "caixa", "password": "x"})
    assert r.status_code == 302 and r.url == "/painel/"
    r = client.get("/painel/")
    assert r.status_code == 200
    html = r.content.decode()
    assert "painel/js/app" in html and "vitrine/carrinho" in html
    assert client.cookies.get("csrftoken") is not None  # o JS envia no X-CSRFToken


def test_login_errado_mostra_mensagem(client, operador):
    r = client.post("/painel/entrar/", {"username": "caixa", "password": "errada"})
    assert r.status_code == 200
    assert "Usuário ou senha incorretos" in r.content.decode()


def test_empresa_bloqueada_nao_entra(client, operador, loja):
    loja.empresa.ativa = False
    loja.empresa.save()
    r = client.post("/painel/entrar/", {"username": "caixa", "password": "x"})
    assert r.status_code == 200
    assert "bloqueado" in r.content.decode()


def test_sair_encerra_a_sessao(client, operador):
    client.force_login(operador)
    r = client.post("/painel/sair/")
    assert r.status_code == 302
    assert client.get("/painel/").status_code == 302


def test_qrcode_svg(client, operador):
    client.force_login(operador)
    r = client.get("/painel/qrcode.svg", {"t": "00020126...pix"})
    assert r.status_code == 200 and r["Content-Type"] == "image/svg+xml"
    assert b"<svg" in r.content
    assert client.get("/painel/qrcode.svg").status_code == 400


def test_api_aceita_sessao_do_painel(client, operador):
    """O painel usa a mesma API do PDV, autenticado pela sessão."""
    client.force_login(operador)
    r = client.get("/api/eu/")
    assert r.status_code == 200 and r.json()["username"] == "caixa"
    r = client.get("/api/enums/")
    assert any(o["valor"] == "PIX" for o in r.json()["FormaPagamento"])


def test_master_entra_sem_empresa(client, db):
    Usuario.objects.create_superuser("chefe", password="segredo")
    r = client.post("/painel/entrar/", {"username": "chefe", "password": "segredo"})
    assert r.status_code == 302
    assert client.get("/painel/").status_code == 200
    assert Usuario.objects.get(username="chefe").papel == PapelUsuario.MASTER
