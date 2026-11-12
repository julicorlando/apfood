import pytest
from apfood_core.enums import CanalVenda, FormaPagamento, StatusAssinatura, TipoAtendimento
from django.db import IntegrityError, transaction

from apps.contas.models import Usuario
from apps.lojas.models import Empresa, Loja
from apps.pedidos.models import Pagamento, Pedido
from apps.plataforma.models import Plano
from apps.salao.models import Comanda


@pytest.fixture
def loja():
    e = Empresa.objects.create(nome="E")
    return Loja.objects.create(empresa=e, nome="L", slug="l")


def test_pagamento_precisa_de_pedido_ou_comanda(loja):
    pedido = Pedido.objects.create(
        loja=loja, canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.RETIRADA, total_centavos=1000
    )
    comanda = Comanda.objects.create(loja=loja)
    Pagamento.objects.create(pedido=pedido, forma=FormaPagamento.PIX, valor_centavos=1000)
    Pagamento.objects.create(comanda=comanda, forma=FormaPagamento.PIX, valor_centavos=1000)
    with pytest.raises(IntegrityError), transaction.atomic():
        Pagamento.objects.create(forma=FormaPagamento.PIX, valor_centavos=1000)
    with pytest.raises(IntegrityError), transaction.atomic():
        Pagamento.objects.create(pedido=pedido, comanda=comanda, forma=FormaPagamento.PIX, valor_centavos=1)


def test_entrega_exige_endereco_exceto_marketplace(loja):
    with pytest.raises(IntegrityError), transaction.atomic():
        Pedido.objects.create(loja=loja, canal=CanalVenda.DELIVERY, tipo_atendimento=TipoAtendimento.ENTREGA)
    Pedido.objects.create(
        loja=loja, canal=CanalVenda.MARKETPLACE, tipo_atendimento=TipoAtendimento.ENTREGA,
        marketplace="IFOOD", id_externo="abc",
    )
    with pytest.raises(IntegrityError), transaction.atomic():  # mesmo pedido do iFood duas vezes
        Pedido.objects.create(
            loja=loja, canal=CanalVenda.MARKETPLACE, tipo_atendimento=TipoAtendimento.ENTREGA,
            marketplace="IFOOD", id_externo="abc",
        )


def test_limites_e_bloqueio_pelo_plano(loja):
    plano = Plano.objects.create(nome="P", preco_mensal_centavos=100, limite_lojas=2, recursos=["mesas"])
    e = loja.empresa
    e.plano = plano
    e.save()
    assert e.limite_lojas_efetivo == 2 and e.tem_recurso("mesas") and not e.tem_recurso("fiscal")
    e.limite_lojas = 5
    assert e.limite_lojas_efetivo == 5
    e.status_assinatura = StatusAssinatura.CANCELADA
    e.save()
    admin = Usuario.objects.create_user("a", password="x", papel="ADMIN", empresa=e)
    assert not admin.lojas_permitidas().exists()
