import json
from datetime import date

import httpx
import pytest
from apfood_core.enums import CanalVenda, FormaPagamento, StatusPedido, TipoAtendimento
from rest_framework.test import APIClient

from apps.caixa import services as caixa
from apps.fiscal import services as fiscal
from apps.fiscal.models import ConfiguracaoFiscal
from apps.integracoes.models import Integracao, Tarefa
from apps.integracoes.provedores import base
from apps.integracoes.tarefas import processar_lote
from apps.pedidos import services as ps
from apps.pedidos.models import Pedido
from apps.plataforma.models import Plano


class Provedor:
    """Servidor HTTP falso: registra chamadas e responde por (método, caminho)."""

    def __init__(self):
        self.rotas, self.chamadas = {}, []

    def __call__(self, req: httpx.Request):
        self.chamadas.append(req)
        for (metodo, trecho), resp in self.rotas.items():
            if req.method == metodo and trecho in req.url.path:
                status, corpo = resp(req) if callable(resp) else resp
                return httpx.Response(status, json=corpo) if corpo is not None else httpx.Response(status)
        return httpx.Response(404, json={"message": f"rota falsa não encontrada: {req.url.path}"})


@pytest.fixture
def provedor(monkeypatch):
    p = Provedor()
    monkeypatch.setattr(base, "transporte", httpx.MockTransport(p))
    return p


def venda(loja, cardapio, usuario, qtd=2):
    return ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.BALCAO, TipoAtendimento.RETIRADA,
                                             [ps.ItemIn(str(cardapio["lata"].id), qtd)]), usuario)


def integracao(loja, tipo, provedor, cred, config=None):
    i = Integracao(loja=loja, tipo=tipo, provedor=provedor, ativo=True, configuracao=config or {})
    i.definir_credenciais(cred)
    i.save()
    return i


def test_credenciais_cifradas(loja):
    i = integracao(loja, "PAGAMENTO", "mercadopago", {"access_token": "segredo-123"})
    i.refresh_from_db()
    assert "segredo-123" not in i.credenciais_cifradas
    assert i.obter_credenciais() == {"access_token": "segredo-123"}


def test_sem_emissor_imprime_cupom_nao_fiscal(loja, cardapio, operador):
    p = venda(loja, cardapio, operador)
    doc = fiscal.documento_da_venda(p)
    assert doc["tipo"] == "NAO_FISCAL"
    texto = "\n".join(l["texto"] for l in doc["linhas"])
    assert "NAO E DOCUMENTO FISCAL" in texto and "14,00" in texto
    vias = fiscal.cupons_cozinha(p)
    assert len(vias) == 1 and "LATA" in "\n".join(l["texto"].upper() for l in vias[0]["linhas"])


@pytest.fixture
def loja_fiscal(loja):
    plano = Plano.objects.create(nome="Fiscal", preco_mensal_centavos=1000, recursos=["fiscal"])
    loja.empresa.plano = plano
    loja.empresa.save()
    loja.cnpj = "12.345.678/0001-90"
    loja.save()
    ConfiguracaoFiscal.objects.create(loja=loja, ativa=True)
    integracao(loja, "FISCAL", "focusnfe", {"token": "tk"})
    return loja


def test_nfce_autorizada(loja_fiscal, cardapio, operador, provedor):
    caixa.abrir_turno(operador, loja_fiscal, 0)
    p = venda(loja_fiscal, cardapio, operador)
    with pytest.raises(Exception, match="pagamento completo"):
        fiscal.documento_da_venda(p)
    ps.registrar_pagamento(usuario=operador, pedido=p, forma=FormaPagamento.PIX, valor_centavos=1400)
    provedor.rotas[("POST", "/v2/nfce")] = (201, {
        "status": "autorizado", "numero": "15", "serie": "1", "chave_nfe": "NFe" + "3" * 44,
        "caminho_danfe": "/arquivos/danfe.html", "mensagem_sefaz": "Autorizado o uso da NF-e",
        "protocolo": "135260000000001", "qrcode_url": "https://sefaz.exemplo/qrcode?p=333|2|1",
        "url_consulta_nf": "https://sefaz.exemplo/consulta",
    })
    doc = fiscal.documento_da_venda(p, cpf="123.456.789-09")
    assert doc["tipo"] == "NFCE" and doc["nota"]["status"] == "AUTORIZADA" and doc["nota"]["numero"] == 15
    # DANFE NFC-e pronto para a térmica: chave, protocolo e QR Code
    textos = " ".join(l["texto"] for l in doc["linhas"])
    assert "DANFE NFC-e" in textos and "3333 3333" in textos and "135260000000001" in textos
    assert [l["texto"] for l in doc["linhas"] if l["qrcode"]] == ["https://sefaz.exemplo/qrcode?p=333|2|1"]
    enviado = json.loads(provedor.chamadas[-1].content)
    assert enviado["cpf_destinatario"] == "12345678909" and enviado["cnpj_emitente"] == "12345678000190"
    assert enviado["formas_pagamento"] == [{"forma_pagamento": "17", "valor_pagamento": "14.00"}]
    assert enviado["items"][0]["valor_bruto"] == "14.00"
    assert provedor.chamadas[-1].headers["authorization"].startswith("Basic ")
    # segunda chamada não emite de novo
    assert fiscal.documento_da_venda(p)["nota"]["id"] == doc["nota"]["id"]


def test_nfce_rejeitada_cai_para_cupom(loja_fiscal, cardapio, operador, provedor):
    caixa.abrir_turno(operador, loja_fiscal, 0)
    p = venda(loja_fiscal, cardapio, operador)
    ps.registrar_pagamento(usuario=operador, pedido=p, forma=FormaPagamento.DINHEIRO, valor_centavos=1400)
    provedor.rotas[("POST", "/v2/nfce")] = (422, {"mensagem": "NCM inválido"})
    doc = fiscal.documento_da_venda(p)
    assert doc["tipo"] == "NAO_FISCAL" and "NCM inválido" in doc["aviso"]


def test_pix_com_webhook(loja, cardapio, operador, provedor):
    integracao(loja, "PAGAMENTO", "mercadopago", {"access_token": "APP_USR-x"})
    p = venda(loja, cardapio, operador)
    provedor.rotas[("POST", "/v1/payments")] = (201, {"id": 999, "status": "pending", "point_of_interaction": {
        "transaction_data": {"qr_code": "000201...", "qr_code_base64": "iVBOR", "ticket_url": "https://mp/t"}}})
    pg = ps.cobrar_pix(pedido=p)
    assert pg.status == "PENDENTE" and pg.dados_externos["qr_code"] == "000201..."
    assert provedor.chamadas[-1].headers["x-idempotency-key"] == str(pg.id)

    provedor.rotas[("GET", "/v1/payments/999")] = (200, {"id": 999, "status": "approved",
                                                         "external_reference": str(pg.id), "transaction_amount": 14.0})
    api = APIClient()
    for _ in range(2):  # webhook repetido é ignorado
        assert api.post(f"/api/webhooks/mercadopago/{loja.id}/", {"action": "payment.updated", "data": {"id": "999"}},
                        format="json").status_code == 200
    pg.refresh_from_db()
    assert pg.status == "CONFIRMADO" and pg.pago_online and pg.turno is None
    assert sum(1 for c in provedor.chamadas if c.method == "GET") == 1


def test_whatsapp_por_tarefa(loja, cardapio, operador, provedor, django_capture_on_commit_callbacks):
    integracao(loja, "WHATSAPP", "zapi", {"instance": "I1", "token": "T1", "client_token": "C1"})
    provedor.rotas[("POST", "/send-text")] = (200, {"zaapId": "z", "messageId": "m"})
    with django_capture_on_commit_callbacks(execute=True):
        p = ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.DELIVERY, TipoAtendimento.RETIRADA,
                                              [ps.ItemIn(str(cardapio["lata"].id))], telefone_cliente="11987654321",
                                              nome_cliente="Ana"), operador)
        ps.transicionar(p, StatusPedido.PRONTO, operador)
    assert Tarefa.objects.filter(tipo="whatsapp.enviar").count() == 1
    processar_lote()
    t = Tarefa.objects.get()
    assert t.status == "CONCLUIDA", t.erro
    req = provedor.chamadas[-1]
    assert "/instances/I1/token/T1/send-text" in req.url.path and req.headers["client-token"] == "C1"
    corpo = json.loads(req.content)
    assert corpo["phone"] == "5511987654321" and "pronto para retirada" in corpo["message"]


def test_tarefa_com_falha_reagenda(loja, cardapio, operador, provedor, django_capture_on_commit_callbacks):
    integracao(loja, "WHATSAPP", "zapi", {"instance": "I", "token": "T"})
    provedor.rotas[("POST", "/send-text")] = (500, {"error": "fora do ar"})
    with django_capture_on_commit_callbacks(execute=True):
        p = ps.criar_pedido(loja, ps.PedidoIn(CanalVenda.DELIVERY, TipoAtendimento.RETIRADA,
                                              [ps.ItemIn(str(cardapio["lata"].id))], telefone_cliente="11987654321"),
                            operador)
        ps.transicionar(p, StatusPedido.PRONTO, operador)
    processar_lote()
    t = Tarefa.objects.get()
    assert t.status == "PENDENTE" and t.tentativas == 1 and "fora do ar" in t.erro


IFOOD_PEDIDO = {
    "id": "if-123", "displayId": "8821", "orderType": "DELIVERY",
    "customer": {"name": "Bruno", "phone": {"number": "0800 123"}},
    "delivery": {"deliveryAddress": {"streetName": "Rua X", "streetNumber": "9", "neighborhood": "Centro",
                                     "city": "SP", "coordinates": {"latitude": -23.5, "longitude": -46.6}}},
    "items": [{"name": "Lata", "externalCode": "LATA-1", "quantity": 2, "unitPrice": 7.0, "totalPrice": 14.0,
               "options": []}],
    "total": {"subTotal": 14.0, "deliveryFee": 5.0, "benefits": 0, "orderAmount": 19.0},
    "payments": {"methods": [{"method": "CREDIT", "type": "ONLINE", "value": 19.0}]},
}


def test_ifood_importa_pedido_e_devolve_status(loja, cardapio, operador, provedor, django_capture_on_commit_callbacks):
    lata = cardapio["lata"]
    lata.codigo = "LATA-1"
    lata.save()
    integ = integracao(loja, "MARKETPLACE", "ifood", {"client_id": "c", "client_secret": "s"}, {"merchant_id": "m-1"})
    provedor.rotas[("POST", "/oauth/token")] = (200, {"accessToken": "tok", "expiresIn": 21600})
    provedor.rotas[("GET", "/events:polling")] = (200, [{"id": "ev-1", "code": "PLC", "orderId": "if-123"}])
    provedor.rotas[("GET", "/orders/if-123")] = (200, IFOOD_PEDIDO)
    provedor.rotas[("POST", "/acknowledgment")] = (202, None)
    provedor.rotas[("POST", "/orders/if-123/confirm")] = (202, None)

    from apps.integracoes.provedores.ifood import sincronizar

    assert sincronizar(integ) == 1
    assert sincronizar(integ) == 0 or Pedido.objects.count() == 1  # evento repetido não duplica
    p = Pedido.objects.get(id_externo="if-123")
    assert p.canal == "MARKETPLACE" and p.status == "PENDENTE" and p.total_centavos == 1900
    assert p.itens.get().produto == lata and p.pagamentos.get().status == "CONFIRMADO"
    ack = [c for c in provedor.chamadas if "acknowledgment" in c.url.path][0]
    assert json.loads(ack.content) == [{"id": "ev-1"}]
    assert ack.headers["authorization"] == "Bearer tok"

    with django_capture_on_commit_callbacks(execute=True):
        ps.transicionar(p, StatusPedido.RECEBIDO, operador)
    processar_lote()
    assert any(c.url.path.endswith("/orders/if-123/confirm") for c in provedor.chamadas)


def test_cobranca_inadimplencia_e_reativacao(loja, gerente):
    from apps.plataforma import cobranca

    plano = Plano.objects.create(nome="B", preco_mensal_centavos=9900)
    e = loja.empresa
    e.plano, e.status_assinatura, e.dia_vencimento = plano, "ATIVA", 5
    e.save()
    [f] = cobranca.gerar_faturas(date(2026, 11, 1))
    assert f.valor_centavos == 9900 and f.vencimento == date(2026, 11, 5)
    assert cobranca.gerar_faturas(date(2026, 11, 2)) == []  # uma por mês
    cobranca.atualizar_inadimplencia(date(2026, 11, 8))
    e.refresh_from_db()
    assert e.status_assinatura == "INADIMPLENTE" and e.ativa
    cobranca.atualizar_inadimplencia(date(2026, 11, 20))
    e.refresh_from_db()
    from apps.contas.models import Usuario

    assert not e.ativa and not Usuario.objects.get(pk=gerente.pk).lojas_permitidas().exists()
    cobranca.confirmar_fatura(f)
    e.refresh_from_db()
    assert e.ativa and e.status_assinatura == "ATIVA"


@pytest.mark.django_db(transaction=True)
def test_websocket_com_jwt(loja, operador):
    from asgiref.sync import async_to_sync
    from channels.testing import WebsocketCommunicator
    from rest_framework_simplejwt.tokens import AccessToken

    from config.asgi import application

    async def conectar(token):
        com = WebsocketCommunicator(application, f"/ws/pdv/{loja.id}/?token={token}",
                                    headers=[(b"origin", b"http://localhost")])
        ok, _ = await com.connect()
        await com.disconnect()
        return ok

    assert async_to_sync(conectar)(str(AccessToken.for_user(operador))) is True
    assert async_to_sync(conectar)("invalido") is False
