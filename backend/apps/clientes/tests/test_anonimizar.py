"""LGPD: o gerente anonimiza o cliente; pedidos ficam (valores), sem dados pessoais."""

from apfood_core.enums import CanalVenda, PapelUsuario, TipoAtendimento
from rest_framework.test import APIClient

from apps.clientes.models import Cliente, EnderecoCliente
from apps.contas.models import Usuario
from apps.pedidos import services as ps
from apps.pedidos.models import Pedido


def api(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def test_gerente_anonimiza_cliente_e_pedidos(loja, cardapio, gerente, operador):
    c = Cliente.objects.create(loja=loja, nome="Ana Souza", telefone="11999990000", email="ana@x.com",
                               cpf="12345678909", aceita_marketing=True)
    EnderecoCliente.objects.create(cliente=c, logradouro="Rua A", numero="10", bairro="Centro", cidade="SP", principal=True)
    p = ps.criar_pedido(loja, ps.PedidoIn(
        canal=CanalVenda.DELIVERY, tipo_atendimento=TipoAtendimento.ENTREGA, nome_cliente="Ana Souza",
        telefone_cliente="11999990000", taxa_entrega_centavos=500, forma_pagamento_prevista="PIX",
        endereco={"logradouro": "Rua A", "numero": "10", "bairro": "Centro", "cidade": "SP"},
        itens=[ps.ItemIn(str(cardapio["lata"].id), 1)],
    ), operador)
    assert Pedido.objects.get(pk=p.pk).cliente_id == c.id
    total = Pedido.objects.get(pk=p.pk).total_centavos

    assert api(operador).post(f"/api/clientes/{c.id}/anonimizar/?loja={loja.id}").status_code == 403
    r = api(gerente).post(f"/api/clientes/{c.id}/anonimizar/?loja={loja.id}")
    assert r.status_code == 200, r.content

    c.refresh_from_db()
    assert c.anonimizado_em and c.nome == "Cliente anonimizado" and c.telefone.startswith("00")
    assert (c.email, c.cpf, c.aceita_marketing) == ("", "", False)
    assert not c.enderecos.ativos().exists()
    assert not EnderecoCliente.objects.filter(logradouro="Rua A").exists()
    p = Pedido.objects.get(pk=p.pk)
    assert (p.nome_cliente, p.telefone_cliente, p.entrega_bairro) == ("", "", "")
    assert p.total_centavos == total  # relatórios continuam batendo

    # o mesmo telefone pode voltar a ser cliente (cadastro novo)
    Cliente.objects.create(loja=loja, nome="Ana", telefone="11999990000")


def test_dois_anonimizados_na_mesma_loja_nao_colidem(loja, gerente):
    from apps.clientes.services import anonimizar

    a = anonimizar(Cliente.objects.create(loja=loja, nome="A", telefone="11911110000"))
    b = anonimizar(Cliente.objects.create(loja=loja, nome="B", telefone="11922220000"))
    assert a.telefone != b.telefone
    assert anonimizar(a).anonimizado_em == a.anonimizado_em  # idempotente


def test_admin_tambem_anonimiza(loja):
    admin = Usuario.objects.create_user("dono", password="x", papel=PapelUsuario.ADMIN, empresa=loja.empresa)
    c = Cliente.objects.create(loja=loja, nome="Zé", telefone="11933330000")
    assert api(admin).post(f"/api/clientes/{c.id}/anonimizar/?loja={loja.id}").status_code == 200
