"""API de gestão usada pelo painel web: mesmas regras do admin do Django."""

import pytest
from apfood_core.enums import PapelUsuario
from rest_framework.test import APIClient

from apps.contas.models import Usuario
from apps.integracoes.models import Integracao
from apps.lojas.models import Empresa, Loja


def cliente(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


@pytest.fixture
def admin(loja):
    return Usuario.objects.create_user("dono", password="x", papel=PapelUsuario.ADMIN, empresa=loja.empresa)


@pytest.fixture
def master(db):
    return Usuario.objects.create_superuser("chefe", password="x")


@pytest.fixture
def outra_loja(db):
    e = Empresa.objects.create(nome="Outra")
    return Loja.objects.create(empresa=e, nome="Outra Loja", slug="outra-loja")


# --- lojas ------------------------------------------------------------------
def test_operador_le_so_a_propria_loja(operador, loja, outra_loja):
    r = cliente(operador).get("/api/lojas/")
    assert r.status_code == 200
    assert [l["id"] for l in r.data["results"]] == [str(loja.id)]


def test_operador_nao_altera_loja(operador, loja):
    r = cliente(operador).patch(f"/api/lojas/{loja.id}/", {"nome": "X"}, format="json")
    assert r.status_code == 403


def test_admin_altera_loja_mas_nao_troca_de_empresa(admin, loja, outra_loja):
    r = cliente(admin).patch(f"/api/lojas/{loja.id}/", {"nome": "Novo Nome", "empresa": str(outra_loja.empresa_id),
                                                         "cor_primaria": "#112233"}, format="json")
    assert r.status_code == 200, r.data
    loja.refresh_from_db()
    assert loja.nome == "Novo Nome" and loja.empresa_id != outra_loja.empresa_id


def test_admin_nao_ve_loja_de_outra_empresa(admin, outra_loja):
    assert cliente(admin).get(f"/api/lojas/{outra_loja.id}/").status_code == 404


def test_admin_cria_loja_respeitando_limite(admin, loja):
    loja.empresa.limite_lojas = 1
    loja.empresa.save()
    r = cliente(admin).post("/api/lojas/", {"nome": "Filial", "slug": "filial"}, format="json")
    assert r.status_code == 403
    loja.empresa.limite_lojas = 2
    loja.empresa.save()
    r = cliente(admin).post("/api/lojas/", {"nome": "Filial", "slug": "filial"}, format="json")
    assert r.status_code == 201, r.data
    assert Loja.objects.get(slug="filial").empresa_id == loja.empresa_id


def test_gerente_abre_loja_para_pedidos(gerente, loja):
    loja.aberta_para_pedidos = False
    loja.save()
    r = cliente(gerente).post(f"/api/lojas/{loja.id}/pedidos-online/", {"aberta": True}, format="json")
    assert r.status_code == 200
    loja.refresh_from_db()
    assert loja.aberta_para_pedidos is True


# --- empresas -----------------------------------------------------------------
def test_admin_nao_cadastra_empresa_nem_muda_plano(admin, loja):
    c = cliente(admin)
    assert c.post("/api/empresas/", {"nome": "Nova"}, format="json").status_code == 403
    r = c.patch(f"/api/empresas/{loja.empresa_id}/", {"telefone": "1199", "ativa": False}, format="json")
    assert r.status_code == 200
    loja.empresa.refresh_from_db()
    assert loja.empresa.telefone == "1199" and loja.empresa.ativa is True


def test_master_faz_onboarding_completo(master):
    r = cliente(master).post("/api/empresas/onboarding/", {
        "empresa": {"nome": "Hamburgueria Nova"},
        "loja": {"nome": "Centro", "slug": "nova-centro"},
        "admin": {"username": "novo-admin", "password": "segredo123", "first_name": "Ana"},
    }, format="json")
    assert r.status_code == 201, r.data
    u = Usuario.objects.get(username="novo-admin")
    assert u.papel == PapelUsuario.ADMIN and u.empresa.nome == "Hamburgueria Nova"
    assert u.check_password("segredo123")
    assert Loja.objects.get(slug="nova-centro").empresa_id == u.empresa_id


def test_onboarding_invalido_nao_grava_nada(master):
    r = cliente(master).post("/api/empresas/onboarding/", {
        "empresa": {"nome": "Sem Loja"}, "loja": {"nome": "X"}, "admin": {"username": "a"},
    }, format="json")
    assert r.status_code == 400
    assert not Empresa.objects.filter(nome="Sem Loja").exists()


# --- usuários -----------------------------------------------------------------
def test_gerente_cria_operador_da_sua_loja(gerente, loja):
    r = cliente(gerente).post("/api/usuarios/", {"username": "novo-caixa", "password": "senha123", "papel": "OPERADOR",
                                                 "lojas": [str(loja.id)], "pin": "1234"}, format="json")
    assert r.status_code == 201, r.data
    u = Usuario.objects.get(username="novo-caixa")
    assert u.empresa_id == loja.empresa_id and u.conferir_pin("1234")
    assert "password" not in r.data and r.data["tem_pin"] is True


def test_gerente_nao_cria_admin(gerente):
    r = cliente(gerente).post("/api/usuarios/", {"username": "x", "password": "senha123", "papel": "ADMIN"},
                              format="json")
    assert r.status_code == 403


def test_admin_nao_atribui_loja_de_outra_empresa(admin, outra_loja):
    r = cliente(admin).post("/api/usuarios/", {"username": "x", "password": "senha123", "papel": "OPERADOR",
                                               "lojas": [str(outra_loja.id)]}, format="json")
    assert r.status_code == 400


def test_limite_de_usuarios(admin, loja):
    loja.empresa.limite_usuarios = 1
    loja.empresa.save()
    r = cliente(admin).post("/api/usuarios/", {"username": "x", "password": "senha123", "papel": "OPERADOR"},
                            format="json")
    assert r.status_code == 403


def test_ninguem_se_promove_e_excluir_desativa(gerente, operador):
    c = cliente(gerente)
    r = c.patch(f"/api/usuarios/{gerente.id}/", {"papel": "ADMIN", "first_name": "Gê"}, format="json")
    assert r.status_code == 200
    gerente.refresh_from_db()
    assert gerente.papel == "GERENTE" and gerente.first_name == "Gê"
    assert c.delete(f"/api/usuarios/{operador.id}/").status_code == 204
    operador.refresh_from_db()
    assert operador.is_active is False
    assert c.delete(f"/api/usuarios/{gerente.id}/").status_code == 403


def test_operador_nao_lista_usuarios(operador):
    assert cliente(operador).get("/api/usuarios/").status_code == 403


# --- integrações e fiscal -----------------------------------------------------------
def test_credenciais_ficam_cifradas_e_nao_voltam(admin, loja):
    c = cliente(admin)
    r = c.post(f"/api/integracoes/?loja={loja.id}", {"tipo": "FISCAL", "provedor": "focusnfe", "ativo": True,
                                                    "credenciais": {"token": "segredo"}}, format="json")
    assert r.status_code == 201, r.data
    assert "credenciais" not in r.data and r.data["tem_credenciais"] is True
    i = Integracao.objects.get(loja=loja)
    assert "segredo" not in i.credenciais_cifradas and i.obter_credenciais() == {"token": "segredo"}
    r = c.patch(f"/api/integracoes/{i.id}/?loja={loja.id}", {"ativo": False}, format="json")
    assert r.status_code == 200
    assert Integracao.objects.get(pk=i.pk).obter_credenciais() == {"token": "segredo"}


def test_gerente_nao_mexe_em_integracoes(gerente, loja):
    assert cliente(gerente).get(f"/api/integracoes/?loja={loja.id}").status_code == 403


def test_configuracao_fiscal_cria_e_recusa_sat(admin, loja):
    c = cliente(admin)
    r = c.get(f"/api/fiscal/configuracao/?loja={loja.id}")
    assert r.status_code == 200 and r.data["id"] is None
    r = c.put(f"/api/fiscal/configuracao/?loja={loja.id}", {"ativa": True, "serie": 2}, format="json")
    assert r.status_code == 200, r.data
    assert loja.config_fiscal.serie == 2
    r = c.put(f"/api/fiscal/configuracao/?loja={loja.id}", {"modelo_padrao": "SAT"}, format="json")
    assert r.status_code == 400


# --- plataforma ---------------------------------------------------------------
def test_planos_admin_le_master_altera(admin, master):
    assert cliente(admin).post("/api/planos/", {"nome": "Pro", "preco_mensal_centavos": 9900},
                               format="json").status_code == 403
    r = cliente(master).post("/api/planos/", {"nome": "Pro", "preco_mensal_centavos": 9900}, format="json")
    assert r.status_code == 201
    assert cliente(admin).get("/api/planos/").status_code == 200
