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

    def criar_preferencia(self, *, titulo: str, valor_centavos: int, referencia: str, email: str = "",
                          notification_url: str = "", voltar_para: str = "") -> dict:
        """Checkout Pro: página do Mercado Pago com Pix, cartão (até 12x) e boleto."""
        corpo = {
            "items": [{"title": titulo[:250], "quantity": 1, "currency_id": "BRL",
                       "unit_price": float(Decimal(valor_centavos) / 100)}],
            "external_reference": referencia,
            "statement_descriptor": "APFOOD",
        }
        if email:
            corpo["payer"] = {"email": email}
        if notification_url:
            corpo["notification_url"] = notification_url
        if voltar_para:
            corpo["back_urls"] = {"success": voltar_para, "pending": voltar_para, "failure": voltar_para}
            corpo["auto_return"] = "approved"
        r = checar(self.http.post("/checkout/preferences", json=corpo,
                                  headers={"X-Idempotency-Key": f"pref-{referencia}"}), "Mercado Pago Checkout")
        return {"id": str(r["id"]), "init_point": r.get("init_point", "")}

    def conta(self) -> dict:
        """Confere o token: dados da conta do Mercado Pago."""
        r = checar(self.http.get("/users/me"), "Mercado Pago conta")
        return {"id": str(r.get("id", "")), "apelido": r.get("nickname", ""), "email": r.get("email", "")}

    def consultar(self, pagamento_id: str) -> dict:
        r = checar(self.http.get(f"/v1/payments/{pagamento_id}"), "Mercado Pago consulta")
        return {"id": str(r["id"]), "status": r.get("status"), "external_reference": r.get("external_reference"),
                "valor_centavos": int(round(Decimal(str(r.get("transaction_amount", 0))) * 100))}
