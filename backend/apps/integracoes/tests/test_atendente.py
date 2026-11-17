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
    Integracao.objects.create(loja=loja, tipo="WHATSAPP", provedor="whatsapp", ativo=True,
                              configuracao={"instancia": "loja1"})
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


def msg(texto, mid="M1", **chave):
    return {"event": "messages.upsert", "instance": "loja1",
            "data": {"key": {"remoteJid": f"{TEL}@s.whatsapp.net", "fromMe": False, "id": mid, **chave},
                     "pushName": "Ana", "message": {"conversation": texto}}}


def test_webhook_com_chave(loja_bot, django_capture_on_commit_callbacks):
    from apps.integracoes import whatsapp
    from apps.integracoes.models import Tarefa

    base = f"/api/webhooks/whatsapp/{loja_bot.id}/"
    certo = base + whatsapp.chave_webhook(loja_bot) + "/"
    assert Client().post(base + "errada/", msg("oi"), content_type="application/json").status_code == 404
    with django_capture_on_commit_callbacks(execute=True):
        r = Client().post(certo, msg("oi"), content_type="application/json")
        Client().post(certo, msg("oi"), content_type="application/json")  # repetido
        Client().post(certo, msg("oi", "M2", fromMe=True), content_type="application/json")  # nossa
        Client().post(certo, {**msg("oi", "M3"), "data": {**msg("oi", "M3")["data"],
                      "key": {"remoteJid": "1203@g.us", "fromMe": False, "id": "M3"}}},
                      content_type="application/json")  # grupo
        Client().post(certo, {"event": "messages.upsert", "data": {"key": {"remoteJid": f"{TEL}@s.whatsapp.net",
                      "id": "M4"}, "message": {"extendedTextMessage": {"text": "1"}}}}, content_type="application/json")
    assert r.status_code == 200
    textos = [t.payload["mensagem"] for t in Tarefa.objects.filter(tipo="whatsapp.enviar").order_by("criado_em")]
    assert len(textos) == 2 and "Responda com um número" in textos[0] and f"/{loja_bot.slug}/" in textos[1]
