"""Webhooks de provedores. O corpo do aviso NÃO é confiável: guardamos o
evento (idempotência/auditoria) e conferimos o status direto na API do provedor."""

import logging

from django.conf import settings
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
            info = MercadoPago(settings.APFOOD_MP_TOKEN_PLATAFORMA).consultar(pid)
            ref = info.get("external_reference") or ""
            if info["status"] == STATUS_PAGO and ref.startswith("fatura-"):
                fatura = Fatura.objects.get(pk=ref.removeprefix("fatura-"))
                if info["valor_centavos"] >= fatura.valor_centavos:
                    cobranca.confirmar_fatura(fatura)
            wh.processado_em = timezone.now()
        except Exception as exc:  # noqa: BLE001
            log.exception("webhook MP plataforma")
            wh.erro = str(exc)[:2000]
        wh.save()
        return Response({"ok": True})
