"""Cadastro self-service: página de planos cria empresa em teste + loja + admin."""

from apfood_core.enums import PapelUsuario, StatusAssinatura
from django.core import mail

from apps.contas.models import Usuario
from apps.lojas.models import Empresa, Loja
from apps.plataforma.models import Plano

DADOS = {"restaurante": "Burger do Zé", "cidade": "Recife", "nome": "José Silva", "email": "Ze@Exemplo.com",
         "telefone": "(81) 99999-0000", "senha": "Hamburguer#2026", "aceite": "on"}


def test_pagina_de_planos_mostra_planos_publicos(client, db):
    Plano.objects.create(nome="Básico", preco_mensal_centavos=9900, publico=True)
    Plano.objects.create(nome="Interno", preco_mensal_centavos=1, publico=False)
    html = client.get("/planos/").content.decode()
    assert "Básico" in html and "Interno" not in html and "Teste grátis" in html


def test_cadastro_cria_conta_em_teste_e_entra(client, db):
    plano = Plano.objects.create(nome="Básico", preco_mensal_centavos=9900, dias_trial=7)
    r = client.post("/planos/", {**DADOS, "plano": plano.pk})
    assert r.status_code == 302 and r.url.startswith("/painel/")
    u = Usuario.objects.get(username="ze@exemplo.com")
    assert u.papel == PapelUsuario.ADMIN and u.check_password(DADOS["senha"]) and u.first_name == "José"
    e = u.empresa
    assert e.status_assinatura == StatusAssinatura.TRIAL and e.plano == plano and e.trial_ate is not None
    loja = Loja.objects.get(empresa=e)
    assert loja.slug == "burger-do-ze" and loja.whatsapp == "81999990000"
    assert client.get("/painel/").status_code == 200  # já logado


def test_slug_repetido_ganha_numero(client, db):
    e = Empresa.objects.create(nome="Outra")
    Loja.objects.create(empresa=e, nome="Burger do Zé", slug="burger-do-ze")
    client.post("/planos/", DADOS)
    assert Loja.objects.filter(slug="burger-do-ze-2").exists()


def test_cadastro_recusa_email_repetido_e_dados_ruins(client, db):
    Usuario.objects.create_user("ze@exemplo.com", password="x", papel=PapelUsuario.ADMIN,
                                empresa=Empresa.objects.create(nome="X"))
    r = client.post("/planos/", {**DADOS, "telefone": "123", "aceite": ""})
    html = r.content.decode()
    assert r.status_code == 200 and "já tem cadastro" in html and "DDD" in html
    assert Empresa.objects.count() == 1


def test_robo_preenche_campo_escondido(client, db):
    client.post("/planos/", {**DADOS, "site": "http://spam"})
    assert not Usuario.objects.filter(username="ze@exemplo.com").exists()


def test_esqueci_senha_envia_link_que_funciona(client, operador):
    operador.email = "caixa@exemplo.com"
    operador.save()
    r = client.post("/painel/senha/esqueci/", {"email": "caixa@exemplo.com"})
    assert r.status_code == 302 and len(mail.outbox) == 1
    corpo = mail.outbox[0].body
    link = next(l for l in corpo.splitlines() if "/painel/senha/nova/" in l).strip()
    caminho = link.split("://", 1)[1].split("/", 1)[1]
    r = client.get("/" + caminho, follow=True)
    assert r.status_code == 200
    r = client.post(r.redirect_chain[-1][0], {"new_password1": "Nova#Senha2026", "new_password2": "Nova#Senha2026"})
    assert r.status_code == 302
    operador.refresh_from_db()
    assert operador.check_password("Nova#Senha2026")


def test_esqueci_senha_nao_revela_email_inexistente(client, db):
    r = client.post("/painel/senha/esqueci/", {"email": "ninguem@exemplo.com"})
    assert r.status_code == 302 and len(mail.outbox) == 0
