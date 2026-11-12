"""iFood — Merchant API (pedidos).

Fluxo: polling de eventos a cada 30 s (`python manage.py ifood_polling`) →
evento PLACED: busca o pedido, importa como Pedido (canal MARKETPLACE,
PENDENTE na fila do PDV) e confirma o recebimento do evento (acknowledgment).
Ações do PDV voltam ao iFood por tarefa: aceitar → confirm, em preparo →
startPreparation, pronto → readyToPickup, saiu → dispatch, cancelar →
requestCancellation. Evento CANCELLED do iFood cancela o pedido aqui.

Credenciais (Integracao MARKETPLACE "ifood"): {"client_id", "client_secret"} ou
APFOOD_IFOOD_CLIENT_ID/SECRET no servidor (app único p/ todas as lojas).
Configuração: {"merchant_id": "uuid da loja no iFood"}.
⚠ Validar em homologação com as credenciais de teste do Portal do Parceiro.
"""

import logging
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

from .base import checar, cliente

log = logging.getLogger(__name__)
BASE = "https://merchant-api.ifood.com.br"
CODIGOS_NOVO = {"PLC", "PLACED"}
CODIGOS_CANCELADO = {"CAN", "CANCELLED"}


class IFood:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id, self.client_secret = client_id, client_secret
        self.http = cliente(BASE)

    def _token(self) -> str:
        chave = f"ifood-token-{self.client_id}"
        if tok := cache.get(chave):
            return tok
        r = checar(self.http.post("/authentication/v1.0/oauth/token", data={
            "grantType": "client_credentials", "clientId": self.client_id, "clientSecret": self.client_secret,
        }), "iFood autenticação")
        cache.set(chave, r["accessToken"], max(60, int(r.get("expiresIn", 3600)) - 120))
        return r["accessToken"]

    def _h(self, **extra):
        return {"Authorization": f"Bearer {self._token()}", **extra}

    def eventos(self, merchant_ids: list[str]) -> list[dict]:
        r = self.http.get("/order/v1.0/events:polling", headers=self._h(**{"x-polling-merchants": ",".join(merchant_ids)}))
        if r.status_code == 204:
            return []
        return checar(r, "iFood polling") or []

    def confirmar_eventos(self, ids: list[str]) -> None:
        if ids:
            checar(self.http.post("/order/v1.0/events/acknowledgment", json=[{"id": i} for i in ids], headers=self._h()),
                   "iFood acknowledgment")

    def pedido(self, order_id: str) -> dict:
        return checar(self.http.get(f"/order/v1.0/orders/{order_id}", headers=self._h()), "iFood pedido")

    def acao(self, order_id: str, acao: str, corpo: dict | None = None) -> None:
        checar(self.http.post(f"/order/v1.0/orders/{order_id}/{acao}", json=corpo, headers=self._h()),
               f"iFood {acao}")


def cliente_da_integracao(integracao) -> IFood:
    cred = integracao.obter_credenciais()
    cid = cred.get("client_id") or getattr(settings, "APFOOD_IFOOD_CLIENT_ID", "")
    sec = cred.get("client_secret") or getattr(settings, "APFOOD_IFOOD_CLIENT_SECRET", "")
    if not cid or not sec:
        raise ValueError("credenciais do iFood não configuradas")
    return IFood(cid, sec)


def _c(valor) -> int:
    return int((Decimal(str(valor or 0)) * 100).quantize(Decimal("1")))


FORMAS = {"CASH": "DINHEIRO", "CREDIT": "CARTAO_CREDITO", "DEBIT": "CARTAO_DEBITO", "PIX": "PIX",
          "MEAL_VOUCHER": "VOUCHER", "FOOD_VOUCHER": "VOUCHER"}


def normalizar_pedido(o: dict) -> dict:
    """Pedido do iFood → formato de `importar_pedido_externo`."""
    entrega = (o.get("delivery") or {}).get("deliveryAddress") or {}
    coord = entrega.get("coordinates") or {}
    total = o.get("total") or {}
    pagamentos = []
    for m in (o.get("payments") or {}).get("methods") or []:
        online = (m.get("type") or "").upper() == "ONLINE"
        pagamentos.append({
            "forma": "MARKETPLACE" if online else FORMAS.get((m.get("method") or "").upper(), "OUTRO"),
            "valor_centavos": _c(m.get("value")), "pago": online,
            "troco_para_centavos": _c((m.get("cash") or {}).get("changeFor")) or None,
        })
    tipo = {"DELIVERY": "ENTREGA", "TAKEOUT": "RETIRADA", "DINE_IN": "CONSUMO_LOCAL"}.get(o.get("orderType"), "ENTREGA")
    return {
        "marketplace": "IFOOD", "id_externo": o["id"], "codigo_externo": str(o.get("displayId") or ""),
        "tipo_atendimento": tipo,
        "nome_cliente": (o.get("customer") or {}).get("name", ""),
        "telefone_cliente": ((o.get("customer") or {}).get("phone") or {}).get("number", ""),
        "endereco": {
            "logradouro": entrega.get("streetName", ""), "numero": entrega.get("streetNumber", ""),
            "complemento": entrega.get("complement", ""), "bairro": entrega.get("neighborhood", ""),
            "cidade": entrega.get("city", ""), "cep": entrega.get("postalCode", ""),
            "referencia": entrega.get("reference", ""),
            "latitude": coord.get("latitude"), "longitude": coord.get("longitude"),
        } if entrega else None,
        "itens": [{
            "codigo": it.get("externalCode") or "", "nome": it.get("name", ""), "quantidade": int(it.get("quantity") or 1),
            "unitario_centavos": _c(it.get("unitPrice")), "total_centavos": _c(it.get("totalPrice")),
            "observacao": it.get("observations") or "",
            "adicionais": [{"codigo": op.get("externalCode") or "", "nome": op.get("name", ""),
                            "quantidade": int(op.get("quantity") or 1), "unitario_centavos": _c(op.get("unitPrice"))}
                           for op in it.get("options") or []],
        } for it in o.get("items") or []],
        "subtotal_centavos": _c(total.get("subTotal")), "taxa_entrega_centavos": _c(total.get("deliveryFee")),
        "desconto_centavos": _c(total.get("benefits")), "acrescimo_centavos": _c(total.get("additionalFees")),
        "total_centavos": _c(total.get("orderAmount")), "pagamentos": pagamentos,
        "observacao": o.get("extraInfo") or "",
    }


def sincronizar(integracao) -> int:
    """Um ciclo de polling para a loja da integração. Retorna pedidos importados."""
    from apps.pedidos import services as ps
    from apps.pedidos.models import Pedido

    merchant = (integracao.configuracao or {}).get("merchant_id")
    if not merchant:
        raise ValueError("merchant_id do iFood não configurado")
    api = cliente_da_integracao(integracao)
    importados, confirmar = 0, []
    for ev in api.eventos([merchant]):
        codigo = ev.get("code") or ev.get("fullCode")
        try:
            if codigo in CODIGOS_NOVO:
                ps.importar_pedido_externo(integracao.loja, normalizar_pedido(api.pedido(ev["orderId"])))
                importados += 1
            elif codigo in CODIGOS_CANCELADO:
                p = Pedido.objects.filter(loja=integracao.loja, marketplace="IFOOD", id_externo=ev["orderId"]).first()
                if p and p.status not in ("CANCELADO", "RECUSADO", "CONCLUIDO"):
                    ps.transicionar(p, ps.S.CANCELADO, None, motivo="cancelado no iFood", origem_externa=True)
            confirmar.append(ev["id"])
        except Exception:  # noqa: BLE001 — sem ack, o evento volta no próximo polling
            log.exception("iFood: falha no evento %s", ev.get("id"))
    api.confirmar_eventos(confirmar)
    integracao.registrar_sucesso()
    return importados


ACOES = {"RECEBIDO": "confirm", "EM_PREPARO": "startPreparation", "PRONTO": "readyToPickup",
         "SAIU_PARA_ENTREGA": "dispatch"}


def acao_para_status(status: str) -> str | None:
    return ACOES.get(status)


from apps.integracoes.tarefas import executor  # noqa: E402


@executor("ifood.acao")
def executar_acao(integracao_id: str, order_id: str, acao: str, corpo: dict | None = None):
    from apps.integracoes.models import Integracao

    api = cliente_da_integracao(Integracao.objects.get(pk=integracao_id))
    api.acao(order_id, acao, corpo)
