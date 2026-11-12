"""Mercado Pago — cobrança Pix dinâmica (QR Code + copia e cola).

POST /v1/payments (payment_method_id=pix, header X-Idempotency-Key)
GET  /v1/payments/{id}  — o webhook só avisa; o status é sempre conferido aqui.
Credenciais: {"access_token": "APP_USR-..."}.
"""

from decimal import Decimal

from .base import checar, cliente

STATUS_PAGO = "approved"


class MercadoPago:
    def __init__(self, access_token: str):
        self.http = cliente("https://api.mercadopago.com", headers={"Authorization": f"Bearer {access_token}"})

    def criar_pix(self, *, valor_centavos: int, descricao: str, email: str, referencia: str,
                  notification_url: str = "", expira_em: str = "") -> dict:
        corpo = {
            "transaction_amount": float(Decimal(valor_centavos) / 100),
            "description": descricao[:200], "payment_method_id": "pix",
            "payer": {"email": email or "cliente@apfood.app"}, "external_reference": referencia,
        }
        if notification_url:
            corpo["notification_url"] = notification_url
        if expira_em:
            corpo["date_of_expiration"] = expira_em
        r = checar(self.http.post("/v1/payments", json=corpo, headers={"X-Idempotency-Key": referencia}),
                   "Mercado Pago Pix")
        dados = (r.get("point_of_interaction") or {}).get("transaction_data") or {}
        return {"id": str(r["id"]), "status": r.get("status"), "qr_code": dados.get("qr_code", ""),
                "qr_code_base64": dados.get("qr_code_base64", ""), "ticket_url": dados.get("ticket_url", "")}

    def consultar(self, pagamento_id: str) -> dict:
        r = checar(self.http.get(f"/v1/payments/{pagamento_id}"), "Mercado Pago consulta")
        return {"id": str(r["id"]), "status": r.get("status"), "external_reference": r.get("external_reference"),
                "valor_centavos": int(round(Decimal(str(r.get("transaction_amount", 0))) * 100))}
