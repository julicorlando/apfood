import pytest
from apfood_core.enums import PapelUsuario as P
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.contas.models import Usuario
from apps.lojas.models import Empresa, Loja


@pytest.fixture
def cenario():
    a = Empresa.objects.create(nome="A")
    b = Empresa.objects.create(nome="B")
    a1 = Loja.objects.create(empresa=a, nome="A1", slug="a1")
    a2 = Loja.objects.create(empresa=a, nome="A2", slug="a2")
    b1 = Loja.objects.create(empresa=b, nome="B1", slug="b1")
    master = Usuario.objects.create_superuser("master", password="x")
    admin_a = Usuario.objects.create_user("admin_a", password="x", papel=P.ADMIN, empresa=a)
    op_a1 = Usuario.objects.create_user("op_a1", password="x", papel=P.OPERADOR, empresa=a)
    op_a1.lojas.set([a1])
    return locals()


def test_createsuperuser_vira_master(cenario):
    m = cenario["master"]
    assert m.papel == P.MASTER and m.empresa is None and m.is_superuser


def test_escopo_de_lojas(cenario):
    c = cenario
    # MASTER administra a plataforma: vê o cadastro de todas, mas não opera nenhuma
    assert set(c["master"].lojas_visiveis()) == {c["a1"], c["a2"], c["b1"]}
    assert not c["master"].lojas_permitidas().exists() and not c["master"].pode_acessar_loja(c["a1"])
    assert set(c["admin_a"].lojas_permitidas()) == {c["a1"], c["a2"]}
    assert set(c["op_a1"].lojas_permitidas()) == {c["a1"]}
    assert not c["op_a1"].pode_acessar_loja(c["b1"])


def test_empresa_bloqueada(cenario):
    c = cenario
    c["a"].ativa = False
    c["a"].save()
    admin = Usuario.objects.get(pk=c["admin_a"].pk)
    assert not admin.lojas_permitidas().exists()


def test_nao_vincula_loja_de_outra_empresa(cenario):
    with pytest.raises(ValidationError):
        cenario["op_a1"].lojas.add(cenario["b1"])


def test_constraint_vinculo_empresa():
    with pytest.raises(IntegrityError), transaction.atomic():
        Usuario.objects.create_user("sem_empresa", password="x", papel=P.OPERADOR)


def test_master_nao_opera_loja_de_cliente(cenario):
    from rest_framework.test import APIClient

    c = cenario
    api = APIClient()
    api.force_authenticate(c["master"])
    loja = c["a1"]
    assert api.get(f"/api/produtos/?loja={loja.id}").status_code == 403
    assert api.get(f"/api/pedidos/?loja={loja.id}").status_code == 403
    assert api.post(f"/api/categorias/?loja={loja.id}", {"nome": "X"}, format="json").status_code == 403
    r = api.get("/api/lojas/")  # mas continua vendo o cadastro de lojas, empresas e usuários
    assert r.status_code == 200 and len(r.data["results"]) == 3
    assert api.get("/api/eu/").data["lojas"] == []
