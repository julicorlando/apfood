"""Webhooks de provedores. O corpo do aviso NÃO é confiável: guardamos o
evento (idempotência/auditoria) e conferimos o status direto na API do provedor."""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integracoes.models import Integracao, WebhookRecebido
from apps.integracoes.provedores.mercadopago import STATUS_PAGO, MercadoPago
from apps.lojas.models import Loja
from apps.pedidos import services as pedidos_srv
from apps.pedidos.models import Pagamento
from apps.plataforma import cobranca
from apps.plataforma.models import Fatura

log = logging.getLogger(__name__)


def _uuid(valor):
    import uuid

    try:
        return uuid.UUID(str(valor))
    except (ValueError, TypeError):
        return None


def _id_pagamento(request) -> str:
    dados = request.data if isinstance(request.data, dict) else {}
    return str((dados.get("data") or {}).get("id") or request.query_params.get("data.id")
               or request.query_params.get("id") or "")


def _registrar(provedor, loja, request, pid) -> WebhookRecebido | None:
    evento = (request.data.get("action") if isinstance(request.data, dict) else "") or "payment"
    try:
        with transaction.atomic():
            return WebhookRecebido.objects.create(provedor=provedor, loja=loja, evento=evento,
                                                  id_evento=f"{evento}:{pid}", payload=request.data or {})
    except IntegrityError:
        return WebhookRecebido.objects.filter(provedor=provedor, id_evento=f"{evento}:{pid}").first()


class Webhook(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class MercadoPagoLojaWebhook(Webhook):
    def post(self, request, loja_id):
        pid = _id_pagamento(request)
        loja = Loja.objects.filter(pk=loja_id).first()
        if not pid or loja is None:
            return Response({"ok": True})  # sempre 200: o MP reenvia em caso de erro
        wh = _registrar("mercadopago", loja, request, pid)
        if wh is None or wh.processado_em:
            return Response({"ok": True})
        integ = Integracao.ativa(loja, "PAGAMENTO", "mercadopago")
        try:
            info = MercadoPago(integ.obter_credenciais()["access_token"]).consultar(pid)
            pg = Pagamento.objects.filter(referencia_externa=info["id"]).first()
            if pg is None and info.get("external_reference"):
                # Checkout (cartão): o pagamento nasce no MP; a referência é o id do nosso Pagamento
                pg = Pagamento.objects.filter(pk=_uuid(info["external_reference"]), referencia_externa__startswith="pref:",
                                              pedido__loja=loja).first() if _uuid(info["external_reference"]) else None
                if pg is not None and info["status"] == STATUS_PAGO:
                    forma = {"credit_card": "CARTAO_CREDITO", "debit_card": "CARTAO_DEBITO", "bank_transfer": "PIX",
                             "account_money": "PIX"}.get(info.get("tipo"), pg.forma)
                    Pagamento.objects.filter(pk=pg.pk).update(referencia_externa=info["id"], forma=forma,
                                                             bandeira=(info.get("bandeira") or "")[:20])
                    pg.refresh_from_db()
            if pg and info["status"] == STATUS_PAGO and str(pg.id) == str(info.get("external_reference")):
                pedidos_srv.confirmar_pagamento_online(pg, valor_centavos=info["valor_centavos"])
            wh.processado_em = timezone.now()
        except Exception as exc:  # noqa: BLE001
            log.exception("webhook MP loja %s", loja_id)
            wh.erro = str(exc)[:2000]
        wh.save()
        return Response({"ok": True})


class MercadoPagoPlataformaWebhook(Webhook):
    def post(self, request):
        pid = _id_pagamento(request)
        if not pid:
            return Response({"ok": True})
        wh = _registrar("mercadopago-plataforma", None, request, pid)
        if wh is None or wh.processado_em:
            return Response({"ok": True})
        try:
            info = MercadoPago(cobranca.token_mp()).consultar(pid)
            ref = info.get("external_reference") or ""
            if info["status"] == STATUS_PAGO and ref.startswith("fatura-"):
                # "fatura-<uuid>" ou "fatura-<uuid>-<data>" (Pix gerado de novo)
                fatura = Fatura.objects.get(pk=ref.removeprefix("fatura-")[:36])
                if info["valor_centavos"] >= fatura.valor_centavos:
                    cobranca.confirmar_fatura(fatura)
            wh.processado_em = timezone.now()
        except Exception as exc:  # noqa: BLE001
            log.exception("webhook MP plataforma")
            wh.erro = str(exc)[:2000]
        wh.save()
        return Response({"ok": True})


class WhatsAppWebhook(Webhook):
    """Eventos do servidor de WhatsApp (Evolution API) da loja: mensagem recebida
    (atendente automático) e mudança de conexão (conectou/desconectou)."""

    def post(self, request, loja_id, chave):
        import hmac

        from apps.integracoes import atendente, whatsapp

        loja = Loja.objects.filter(pk=loja_id).first()
        if loja is None or not hmac.compare_digest(chave, whatsapp.chave_webhook(loja)):
            return Response({"ok": False}, status=404)
        corpo = request.data if isinstance(request.data, dict) else {}
        evento = str(corpo.get("event") or "").lower().replace("_", ".")
        data = corpo.get("data") or {}
        if evento == "connection.update":
            whatsapp.evento_conexao(loja, str((data or {}).get("state") or ""))
            return Response({"ok": True})
        if evento != "messages.upsert" or not isinstance(data, dict):
            return Response({"ok": True})
        mid = str((data.get("key") or {}).get("id") or "")
        wh = _registrar("whatsapp", loja, request, mid) if mid else None
        if mid and (wh is None or wh.processado_em):
            return Response({"ok": True})
        try:
            atendente.processar_mensagem(loja, data)
            if wh:
                wh.processado_em = timezone.now()
        except Exception as exc:  # noqa: BLE001
            log.exception("webhook WhatsApp loja %s", loja_id)
            if wh:
                wh.erro = str(exc)[:2000]
        if wh:
            wh.save()
        return Response({"ok": True})
