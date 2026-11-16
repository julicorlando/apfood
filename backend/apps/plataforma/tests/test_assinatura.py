"""Cobrança da assinatura: e-mails, link de pagamento no login bloqueado,
faixa do painel e troca de plano pelo ADMIN."""

from datetime import date, timedelta

import pytest
from apfood_core.enums import PapelUsuario, StatusAssinatura, StatusFatura
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.contas.models import Usuario
from apps.plataforma import cobranca
from apps.plataforma.models import Fatura, Plano


@pytest.fixture
def admin(loja):
    return Usuario.objects.create_user("dono", password="Senha#123", email="dono@burger.com",
                                       papel=PapelUsuario.ADMIN, empresa=loja.empresa)


@pytest.fixture
def plano(db):
    return Plano.objects.create(nome="Básico", preco_mensal_centavos=9900, limite_lojas=1)


@pytest.fixture
def empresa(loja, plano, admin):
    e = loja.empresa
    e.plano, e.status_assinatura, e.dia_vencimento, e.email = plano, StatusAssinatura.ATIVA, 5, "fin@burger.com"
    e.save()
    return e


def api(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def test_rotina_avisa_fatura_nova_vencida_e_bloqueio(empresa, django_capture_on_commit_callbacks):
    cobranca.rotina_diaria(date(2026, 11, 1))
    [m] = mail.outbox
    assert "fatura 11/2026" in m.subject and set(m.to) == {"dono@burger.com", "fin@burger.com"}
    assert "R$ 99,00" in m.body and "05/11/2026" in m.body

    mail.outbox.clear()
    cobranca.rotina_diaria(date(2026, 11, 2))  # lembrete: vence em 3 dias
    assert [m.subject for m in mail.outbox] == ["ApFood — fatura vence em 05/11"]

    mail.outbox.clear()
    cobranca.rotina_diaria(date(2026, 11, 6))
    cobranca.rotina_diaria(date(2026, 11, 7))  # não repete o aviso de vencida
    assert [m.subject for m in mail.outbox] == ["ApFood — fatura vencida"]

    mail.outbox.clear()
    cobranca.rotina_diaria(date(2026, 11, 20))
    assert [m.subject for m in mail.outbox] == ["ApFood — acesso suspenso"]

    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        cobranca.confirmar_fatura(Fatura.objects.get(empresa=empresa))
    assert [m.subject for m in mail.outbox] == ["ApFood — pagamento confirmado"]


def test_aviso_de_fim_do_teste(loja, plano, admin):
    e = loja.empresa
    e.plano, e.status_assinatura, e.trial_ate = plano, StatusAssinatura.TRIAL, date(2026, 11, 13)
    e.save()
    r = cobranca.rotina_diaria(date(2026, 11, 10))
    assert r["fim_de_teste"] == 1
    assert "teste grátis termina em 3 dias" in mail.outbox[0].subject and "13/11/2026" in mail.outbox[0].body


def test_login_bloqueado_por_falta_de_pagamento_mostra_pix(client, empresa):
    hoje = timezone.localdate()
    Fatura.objects.create(empresa=empresa, plano=empresa.plano, competencia=hoje.replace(day=1), valor_centavos=9900,
                          vencimento=hoje - timedelta(days=20), link_pagamento="https://mp.example/pix/1")
    empresa.ativa, empresa.motivo_bloqueio = False, cobranca.MOTIVO_INADIMPLENCIA
    empresa.save()
    html = client.post("/painel/entrar/", {"username": "dono", "password": "Senha#123"}).content.decode()
    assert "falta de pagamento" in html and "https://mp.example/pix/1" in html and "R$ 99,00" in html

    empresa.motivo_bloqueio = "outro motivo"
    empresa.save()
    html = client.post("/painel/entrar/", {"username": "dono", "password": "Senha#123"}).content.decode()
    assert "Fale com o administrador" in html and "mp.example" not in html


def test_senha_errada_nao_mostra_fatura(client, empresa):
    Fatura.objects.create(empresa=empresa, competencia=date(2026, 11, 1), valor_centavos=9900,
                          vencimento=date(2026, 11, 5), link_pagamento="https://mp.example/pix/1")
    empresa.ativa, empresa.motivo_bloqueio = False, cobranca.MOTIVO_INADIMPLENCIA
    empresa.save()
    html = client.post("/painel/entrar/", {"username": "dono", "password": "errada"}).content.decode()
    assert "mp.example" not in html


def test_api_assinatura_mostra_fatura_e_troca_plano(empresa, admin, gerente, loja):
    hoje = timezone.localdate()
    Fatura.objects.create(empresa=empresa, plano=empresa.plano, competencia=hoje.replace(day=1), valor_centavos=9900,
                          vencimento=hoje - timedelta(days=1))
    pro = Plano.objects.create(nome="Pro", preco_mensal_centavos=19900, limite_lojas=5)
    Plano.objects.create(nome="Interno", preco_mensal_centavos=1, publico=False)

    assert api(gerente).get("/api/assinatura/").status_code == 403
    r = api(admin).get("/api/assinatura/")
    assert r.status_code == 200
    assert r.data["fatura_aberta"]["vencida"] and r.data["fatura_aberta"]["status"] == StatusFatura.ABERTA
    assert {p["nome"] for p in r.data["planos"]} == {"Básico", "Pro"}

    r = api(admin).post("/api/assinatura/", {"plano": str(pro.id)}, format="json")
    assert r.status_code == 200 and r.data["plano_nome"] == "Pro"
    empresa.refresh_from_db()
    assert empresa.plano == pro
    assert Fatura.objects.get(empresa=empresa).valor_centavos == 9900  # fatura já gerada não muda


def test_troca_de_plano_respeita_limite_de_lojas(empresa, admin, loja):
    from apps.lojas.models import Loja

    Loja.objects.create(empresa=empresa, nome="Filial", slug="filial")
    mini = Plano.objects.create(nome="Mini", preco_mensal_centavos=4900, limite_lojas=1)
    r = api(admin).post("/api/assinatura/", {"plano": str(mini.id)}, format="json")
    assert r.status_code == 400 and "1 loja" in str(r.data)
    interno = Plano.objects.create(nome="Interno", preco_mensal_centavos=1, publico=False)
    assert api(admin).post("/api/assinatura/", {"plano": str(interno.id)}, format="json").status_code == 400
