"""Cobrança das empresas pela plataforma (MASTER).

Rotina diária (`python manage.py cobranca_diaria`):
  1. gera a fatura do mês de cada empresa com plano (fora do trial);
  2. cria o Pix da fatura no Mercado Pago da PLATAFORMA (APFOOD_MP_TOKEN_PLATAFORMA);
  3. fatura vencida → empresa INADIMPLENTE; vencida há mais de
     APFOOD_DIAS_TOLERANCIA dias → empresa bloqueada (ativa=False).
Pagamento confirmado (webhook) → fatura PAGA e empresa reativada se o bloqueio
foi por inadimplência.
"""

import calendar
import logging
from datetime import date, timedelta

from apfood_core.enums import StatusAssinatura, StatusFatura
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integracoes.tarefas import executor

from . import avisos
from .models import Fatura

log = logging.getLogger(__name__)
MOTIVO_INADIMPLENCIA = "Bloqueio automático por inadimplência"


def _vencimento(competencia: date, dia: int) -> date:
    ultimo = calendar.monthrange(competencia.year, competencia.month)[1]
    return competencia.replace(day=min(max(dia, 1), ultimo))


def gerar_faturas(hoje: date | None = None) -> list[Fatura]:
    from apps.lojas.models import Empresa

    hoje = hoje or timezone.localdate()
    competencia = hoje.replace(day=1)
    criadas = []
    for e in Empresa.objects.filter(plano__isnull=False).exclude(status_assinatura=StatusAssinatura.CANCELADA):
        if e.status_assinatura == StatusAssinatura.TRIAL and e.trial_ate and e.trial_ate >= hoje:
            continue
        fatura, nova = Fatura.objects.get_or_create(
            empresa=e, competencia=competencia,
            defaults={"plano": e.plano, "valor_centavos": e.plano.preco_mensal_centavos,
                      "vencimento": _vencimento(competencia, e.dia_vencimento)},
        )
        if nova:
            criadas.append(fatura)
            if e.status_assinatura == StatusAssinatura.TRIAL:
                e.status_assinatura = StatusAssinatura.ATIVA
                e.save(update_fields=["status_assinatura", "atualizado_em"])
    return criadas


def gerar_pix(fatura: Fatura) -> None:
    from apps.integracoes.provedores.mercadopago import MercadoPago

    token = getattr(settings, "APFOOD_MP_TOKEN_PLATAFORMA", "")
    if not token or fatura.link_pagamento or fatura.valor_centavos <= 0:
        return
    url = settings.APFOOD["URL_PUBLICA"].rstrip("/") + "/api/webhooks/mercadopago/plataforma/"
    pix = MercadoPago(token).criar_pix(
        valor_centavos=fatura.valor_centavos, descricao=f"ApFood {fatura.plano or ''} {fatura.competencia:%m/%Y}",
        email=fatura.empresa.email, referencia=f"fatura-{fatura.id}",
        notification_url=url if url.startswith("https://") else "",
    )
    fatura.referencia_externa, fatura.link_pagamento = pix["id"], pix["ticket_url"]
    fatura.save(update_fields=["referencia_externa", "link_pagamento", "atualizado_em"])


def atualizar_inadimplencia(hoje: date | None = None) -> dict:
    hoje = hoje or timezone.localdate()
    tolerancia = int(getattr(settings, "APFOOD_DIAS_TOLERANCIA", 10))
    inadimplentes, bloqueadas = 0, 0
    vencidas = (Fatura.objects.filter(status=StatusFatura.ABERTA, vencimento__lt=hoje)
                .select_related("empresa", "plano").order_by("vencimento"))
    empresas = {}  # uma instância por empresa (várias faturas vencidas não duplicam avisos)
    for f in vencidas:
        e = empresas.setdefault(f.empresa_id, f.empresa)
        f.empresa = e
        if e.status_assinatura != StatusAssinatura.INADIMPLENTE:
            e.status_assinatura = StatusAssinatura.INADIMPLENTE
            inadimplentes += 1
            e.save()
            avisos.vencida(f, tolerancia)
        if (hoje - f.vencimento).days > tolerancia and e.ativa:
            e.ativa, e.motivo_bloqueio = False, MOTIVO_INADIMPLENCIA
            bloqueadas += 1
            e.save()
            avisos.bloqueada(f)
    return {"inadimplentes": inadimplentes, "bloqueadas": bloqueadas}


@transaction.atomic
def confirmar_fatura(fatura: Fatura, forma: str = "PIX") -> Fatura:
    f = Fatura.objects.select_for_update().select_related("empresa").get(pk=fatura.pk)
    if f.status == StatusFatura.PAGA:
        return f
    f.status, f.pago_em, f.forma_pagamento = StatusFatura.PAGA, timezone.now(), forma
    f.save()
    e = f.empresa
    if not Fatura.objects.filter(empresa=e, status=StatusFatura.ABERTA, vencimento__lt=timezone.localdate()).exists():
        e.status_assinatura = StatusAssinatura.ATIVA
        if not e.ativa and e.motivo_bloqueio == MOTIVO_INADIMPLENCIA:
            e.ativa, e.motivo_bloqueio = True, ""
        e.save()
    transaction.on_commit(lambda: avisos.pagamento_confirmado(f))
    return f


def rotina_diaria(hoje: date | None = None) -> dict:
    hoje = hoje or timezone.localdate()
    criadas = gerar_faturas(hoje)
    for f in Fatura.objects.filter(status=StatusFatura.ABERTA, link_pagamento=""):
        try:
            gerar_pix(f)
        except Exception:  # noqa: BLE001
            log.exception("falha ao gerar Pix da fatura %s", f.id)
    for f in criadas:
        f.refresh_from_db()  # pega o link do Pix
        avisos.nova_fatura(f)
    lembretes = lembrete_vencimento(DIAS_LEMBRETE, hoje)
    for f in lembretes:
        avisos.lembrete(f)
    testes = fim_do_teste(DIAS_LEMBRETE, hoje)
    for e in testes:
        avisos.fim_do_teste(e, DIAS_LEMBRETE)
    return {"faturas_criadas": len(criadas), "lembretes": len(lembretes), "fim_de_teste": len(testes),
            **atualizar_inadimplencia(hoje)}


@executor("plataforma.rotina_diaria")
def _tarefa_rotina():
    rotina_diaria()


DIAS_LEMBRETE = 3


def lembrete_vencimento(dias: int = DIAS_LEMBRETE, hoje: date | None = None) -> list[Fatura]:
    """Faturas que vencem daqui a `dias` (a rotina roda 1x/dia: um aviso só)."""
    alvo = (hoje or timezone.localdate()) + timedelta(days=dias)
    return list(Fatura.objects.filter(status=StatusFatura.ABERTA, vencimento=alvo).select_related("empresa", "plano"))


def fim_do_teste(dias: int = DIAS_LEMBRETE, hoje: date | None = None) -> list:
    from apps.lojas.models import Empresa

    alvo = (hoje or timezone.localdate()) + timedelta(days=dias)
    return list(Empresa.objects.filter(status_assinatura=StatusAssinatura.TRIAL, trial_ate=alvo, ativa=True)
                .select_related("plano"))


def fatura_em_aberto(empresa) -> Fatura | None:
    """A fatura mais antiga a pagar (a que libera o acesso)."""
    return (Fatura.objects.filter(empresa=empresa, status=StatusFatura.ABERTA)
            .select_related("plano").order_by("vencimento").first())


def trocar_plano(empresa, plano) -> None:
    """Troca feita pelo ADMIN. Vale a partir da próxima fatura (as já geradas
    não mudam). Respeita os limites do plano novo."""
    from django.core.exceptions import ValidationError

    if not plano.ativo or not plano.publico:
        raise ValidationError({"plano": ["plano indisponível"]})
    lojas = empresa.lojas.count()
    if plano.limite_lojas is not None and empresa.limite_lojas is None and lojas > plano.limite_lojas:
        raise ValidationError({"plano": [f"este plano permite {plano.limite_lojas} loja(s); você tem {lojas}"]})
    usuarios = empresa.usuarios.filter(is_active=True).count()
    if plano.limite_usuarios is not None and empresa.limite_usuarios is None and usuarios > plano.limite_usuarios:
        raise ValidationError({"plano": [f"este plano permite {plano.limite_usuarios} usuário(s); você tem {usuarios}"]})
    empresa.plano = plano
    empresa.save(update_fields=["plano", "atualizado_em"])
