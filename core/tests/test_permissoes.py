import pytest

from apfood_core.enums import PapelUsuario as P
from apfood_core.permissoes import (
    Acesso,
    pode_acessar_empresa,
    pode_acessar_loja,
    pode_cadastrar_empresa,
    pode_criar_loja,
    pode_gerenciar_usuario,
    validar_vinculo,
)

MASTER = Acesso(P.MASTER)
ADMIN_A = Acesso(P.ADMIN, empresa_id="A")
GERENTE_A1 = Acesso(P.GERENTE, empresa_id="A", lojas_ids=frozenset({"a1"}))
OPERADOR_A2 = Acesso(P.OPERADOR, empresa_id="A", lojas_ids=frozenset({"a2"}))


def test_master_ve_tudo():
    assert pode_acessar_empresa(MASTER, "A")
    assert pode_acessar_empresa(MASTER, "B")
    assert pode_acessar_loja(MASTER, "b1", "B")
    assert pode_cadastrar_empresa(MASTER)


def test_empresa_nao_ve_outra_empresa():
    assert pode_acessar_empresa(ADMIN_A, "A")
    assert not pode_acessar_empresa(ADMIN_A, "B")
    assert not pode_acessar_loja(ADMIN_A, "b1", "B")
    # mesmo que alguém forje o id de uma loja de outra empresa na lista
    intruso = Acesso(P.GERENTE, empresa_id="A", lojas_ids=frozenset({"b1"}))
    assert not pode_acessar_loja(intruso, "b1", "B")


def test_admin_ve_todas_as_lojas_da_empresa():
    assert pode_acessar_loja(ADMIN_A, "a1", "A")
    assert pode_acessar_loja(ADMIN_A, "a2", "A")


def test_gerente_e_operador_so_lojas_atribuidas():
    assert pode_acessar_loja(GERENTE_A1, "a1", "A")
    assert not pode_acessar_loja(GERENTE_A1, "a2", "A")
    assert pode_acessar_loja(OPERADOR_A2, "a2", "A")
    assert not pode_acessar_loja(OPERADOR_A2, "a1", "A")


def test_empresa_bloqueada_ou_usuario_inativo():
    bloqueado = Acesso(P.ADMIN, empresa_id="A", empresa_ativa=False)
    assert not pode_acessar_empresa(bloqueado, "A")
    assert not pode_acessar_loja(bloqueado, "a1", "A")
    inativo = Acesso(P.ADMIN, empresa_id="A", usuario_ativo=False)
    assert not pode_acessar_empresa(inativo, "A")


def test_so_master_cadastra_empresa():
    assert not pode_cadastrar_empresa(ADMIN_A)


def test_limite_de_lojas():
    assert pode_criar_loja(ADMIN_A, "A", lojas_atuais=1, limite=2)
    assert not pode_criar_loja(ADMIN_A, "A", lojas_atuais=2, limite=2)
    assert pode_criar_loja(ADMIN_A, "A", lojas_atuais=50, limite=None)
    assert not pode_criar_loja(ADMIN_A, "B", lojas_atuais=0, limite=None)
    assert not pode_criar_loja(GERENTE_A1, "A", lojas_atuais=0, limite=None)
    assert pode_criar_loja(MASTER, "A", lojas_atuais=2, limite=2)


def test_gerenciar_usuarios():
    assert pode_gerenciar_usuario(MASTER, P.ADMIN, "B")
    assert pode_gerenciar_usuario(ADMIN_A, P.OPERADOR, "A")
    assert not pode_gerenciar_usuario(ADMIN_A, P.OPERADOR, "B")
    assert not pode_gerenciar_usuario(ADMIN_A, P.MASTER, None)
    assert pode_gerenciar_usuario(GERENTE_A1, P.OPERADOR, "A")
    assert not pode_gerenciar_usuario(GERENTE_A1, P.GERENTE, "A")
    assert not pode_gerenciar_usuario(OPERADOR_A2, P.OPERADOR, "A")


def test_vinculo():
    validar_vinculo(P.MASTER, None)
    validar_vinculo(P.OPERADOR, "A")
    with pytest.raises(ValueError):
        validar_vinculo(P.MASTER, "A")
    with pytest.raises(ValueError):
        validar_vinculo(P.ADMIN, None)
