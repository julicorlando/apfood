"""Atendente automático do WhatsApp."""

import pytest
from apfood_core.enums import CanalVenda, TipoAtendimento
from django.test import Client

from apps.integracoes import atendente
from apps.integracoes.models import Integracao
from apps.pedidos import services as ps

TEL = "5581999990000"


@pytest.fixture
def loja_bot(loja):
    loja.whatsapp_atendente = True
    loja.logradouro, loja.numero, loja.bairro = "Rua do Sol", "10", "Boa Vista"
    loja.save()
    i = Integracao(loja=loja, tipo="WHATSAPP", provedor="zapi", ativo=True)
    i.definir_credenciais({"instance": "x", "token": "y"})
    i.save()
    return loja


def test_intencoes():
    assert atendente.intencao("Quero ver o cardápio") == "cardapio"
    assert atendente.intencao("cadê meu pedido??") == "status"
    assert atendente.intencao("Vocês estão abertos hoje?") == "horario"
    assert atendente.intencao("4") == "atendente"
    assert atendente.intencao("bom dia") is None


def test_conversa(loja_bot, cardapio, operador):
    r = atendente.responder(loja_bot, TEL, "oi")
    assert "Responda com um número" in r and f"/{loja_bot.slug}/" in r
    assert "Não entendi" in atendente.responder(loja_bot, TEL, "blá")  # já saudou
    assert f"/{loja_bot.slug}/" in atendente.responder(loja_bot, TEL, "1")
    assert "Não achei pedido" in atendente.responder(loja_bot, TEL, "2")
    p = ps.criar_pedido(loja_bot, ps.PedidoIn(CanalVenda.BALCAO, TipoAtendimento.RETIRADA,
                                              [ps.ItemIn(str(cardapio["lata"].id), 1)],
                                              telefone_cliente="81999990000", nome_cliente="Ana"), operador)
    r = atendente.responder(loja_bot, TEL, "meu pedido")
    assert f"#{p.numero}" in r and p.token_rastreio in r
    assert "Rua do Sol" in atendente.responder(loja_bot, TEL, "qual o endereço?")
    assert "Pix" in atendente.responder(loja_bot, TEL, "aceita pix?")
    assert "equipe" in atendente.responder(loja_bot, TEL, "quero falar com atendente")
    assert atendente.responder(loja_bot, TEL, "oi") is None  # pausado: humano assume


def test_desligado_nao_responde(loja):
    assert atendente.responder(loja, TEL, "oi") is None


def test_webhook_com_chave(loja_bot, django_capture_on_commit_callbacks):
    from apps.integracoes.models import Tarefa

    base = f"/api/webhooks/zapi/{loja_bot.id}/"
    msg = {"phone": TEL, "fromMe": False, "isGroup": False, "messageId": "M1", "text": {"message": "oi"}}
    assert Client().post(base + "errada/", msg, content_type="application/json").status_code == 404
    with django_capture_on_commit_callbacks(execute=True):
        r = Client().post(base + atendente.chave_webhook(loja_bot) + "/", msg, content_type="application/json")
        Client().post(base + atendente.chave_webhook(loja_bot) + "/", msg, content_type="application/json")  # repetido
        Client().post(base + atendente.chave_webhook(loja_bot) + "/", {**msg, "messageId": "M2", "fromMe": True},
                      content_type="application/json")
    assert r.status_code == 200
    tarefas = Tarefa.objects.filter(tipo="whatsapp.enviar")
    assert tarefas.count() == 1 and "Responda com um número" in tarefas.get().payload["mensagem"]
