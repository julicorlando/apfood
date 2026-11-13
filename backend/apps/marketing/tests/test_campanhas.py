"""Campanhas de WhatsApp: público, texto personalizado, fila espaçada e contagem."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.clientes.models import Cliente
from apps.integracoes import tarefas
from apps.integracoes.models import Integracao, Tarefa
from apps.marketing.models import Campanha, EnvioCampanha


@pytest.fixture
def whatsapp(loja):
    i = Integracao.objects.create(loja=loja, tipo="WHATSAPP", provedor="zapi", ativo=True)
    i.definir_credenciais({"instance": "i", "token": "t"})
    i.save()
    return i


@pytest.fixture
def clientes(loja):
    return [
        Cliente.objects.create(loja=loja, nome="Ana Souza", telefone="11999990001", aceita_marketing=True,
                               saldo_cashback_centavos=750),
        Cliente.objects.create(loja=loja, nome="Bia", telefone="11999990002", aceita_marketing=True),
        Cliente.objects.create(loja=loja, nome="Caio", telefone="11999990003", aceita_marketing=False),
    ]


def api(u):
    c = APIClient()
    c.force_authenticate(u)
    return c


def test_previa_so_quem_aceitou_e_texto_personalizado(gerente, loja, clientes):
    c = Campanha.objects.create(loja=loja, nome="Promo", mensagem="Oi {nome}! Seu saldo: {cashback}. {link}")
    r = api(gerente).get(f"/api/campanhas/{c.id}/previa/?loja={loja.id}")
    assert r.status_code == 200 and r.data["total"] == 2
    assert r.data["exemplo"].startswith("Oi Ana! Seu saldo: R$ 7,50.") and "/burger-centro/" in r.data["exemplo"]
    c.publico = Campanha.CASHBACK
    c.save()
    assert api(gerente).get(f"/api/campanhas/{c.id}/previa/?loja={loja.id}").data["total"] == 1


def test_inativos_exclui_quem_comprou_recente(loja, cardapio, operador, clientes):
    from apfood_core.enums import CanalVenda, TipoAtendimento

    from apps.marketing import campanhas
    from apps.pedidos import services as ps
    from apps.pedidos.models import Pedido

    c = Campanha.objects.create(loja=loja, nome="Volta", mensagem="x", publico=Campanha.INATIVOS, dias_inativo=30)
    ps.criar_pedido(loja, ps.PedidoIn(canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.RETIRADA,
                                      telefone_cliente=clientes[0].telefone, nome_cliente="Ana Souza",
                                      itens=[ps.ItemIn(str(cardapio["lata"].id), 1)]), operador)
    assert [x.nome for x in campanhas.publico(c)] == ["Bia"]
    Pedido.objects.filter(cliente=clientes[0]).update(criado_em=timezone.now() - timedelta(days=40))
    assert sorted(x.nome for x in campanhas.publico(c)) == ["Ana Souza", "Bia"]


def test_enviar_exige_whatsapp(gerente, loja, clientes):
    c = Campanha.objects.create(loja=loja, nome="Promo", mensagem="Oi {nome}")
    r = api(gerente).post(f"/api/campanhas/{c.id}/enviar/?loja={loja.id}")
    assert r.status_code == 400 and "WhatsApp" in str(r.data)


def test_envio_pela_fila_conta_e_conclui(gerente, loja, clientes, whatsapp, django_capture_on_commit_callbacks):
    c = Campanha.objects.create(loja=loja, nome="Promo", mensagem="Oi {nome}")
    with django_capture_on_commit_callbacks(execute=True):
        r = api(gerente).post(f"/api/campanhas/{c.id}/enviar/?loja={loja.id}")
    assert r.status_code == 200 and r.data["status"] == "ENVIANDO" and r.data["total"] == 2
    ts = list(Tarefa.objects.filter(tipo="marketing.campanha").order_by("executar_em"))
    assert len(ts) == 2 and (ts[1].executar_em - ts[0].executar_em).total_seconds() >= 7  # espaçadas
    assert api(gerente).patch(f"/api/campanhas/{c.id}/?loja={loja.id}", {"nome": "x"}, format="json").status_code == 400

    with mock.patch("apps.integracoes.provedores.zapi.ZApi.enviar_texto") as enviar:
        assert tarefas.executar(ts[0]) is True
        enviar.side_effect = RuntimeError("número inválido")
        ts[1].max_tentativas = 1
        assert tarefas.executar(ts[1]) is False
    c.refresh_from_db()
    assert (c.enviados, c.falhas, c.status) == (1, 1, Campanha.CONCLUIDA)
    assert EnvioCampanha.objects.filter(campanha=c, status="FALHOU").count() == 1


def test_operador_nao_ve_campanhas(operador, loja):
    assert api(operador).get(f"/api/campanhas/?loja={loja.id}").status_code == 403
