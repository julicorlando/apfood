"""Pedido agendado / encomenda: o cliente escolhe dia e horário (dentro do
funcionamento da loja, com antecedência mínima e até N dias à frente).

A loja recebe o pedido na hora (com a etiqueta "agendado para") e um lembrete
quando chega a hora de preparar (tempo de preparo + 15 min antes)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from apfood_core.horarios import aberta_em
from django.utils import timezone

from apps.core.excecoes import ErroNegocio
from apps.integracoes.tarefas import enfileirar, executor

PASSO_MIN = 15


def horarios_disponiveis(loja, agora=None) -> list[dict]:
    """[{"data": "2026-11-18", "rotulo": "qua., 18/11", "horarios": ["11:00", ...]}]"""
    if not loja.aceita_agendamento:
        return []
    agora = timezone.localtime(agora or timezone.now())
    minimo = agora + timedelta(minutes=max(loja.agendamento_antecedencia_min, 15))
    tz = timezone.get_current_timezone()
    dias = []
    for d in range(0, max(1, loja.agendamento_dias_max) + 1):
        dia = (agora + timedelta(days=d)).date()
        slots = []
        for m in range(0, 24 * 60, PASSO_MIN):
            dt = timezone.make_aware(datetime.combine(dia, time(m // 60, m % 60)), tz)
            if dt >= minimo and aberta_em(loja.horarios, dt):
                slots.append(f"{m // 60:02d}:{m % 60:02d}")
        if slots:
            semana = ["seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom."][dia.weekday()]
            rotulo = "Hoje" if d == 0 else "Amanhã" if d == 1 else f"{semana}, {dia:%d/%m}"
            dias.append({"data": dia.isoformat(), "rotulo": rotulo, "horarios": slots})
    return dias


def validar(loja, quando) -> datetime:
    if not loja.aceita_agendamento:
        raise ErroNegocio("esta loja não aceita pedidos agendados", "agendado_para")
    if timezone.is_naive(quando):
        quando = timezone.make_aware(quando, timezone.get_current_timezone())
    agora = timezone.now()
    if quando < agora + timedelta(minutes=max(loja.agendamento_antecedencia_min, 15) - 1):
        raise ErroNegocio(f"agende com pelo menos {loja.agendamento_antecedencia_min} minutos de antecedência", "agendado_para")
    if quando > agora + timedelta(days=loja.agendamento_dias_max + 1):
        raise ErroNegocio(f"agende para no máximo {loja.agendamento_dias_max} dias à frente", "agendado_para")
    if not aberta_em(loja.horarios, timezone.localtime(quando)):
        raise ErroNegocio("a loja não funciona nesse horário", "agendado_para")
    return quando


def agendar_lembrete(pedido) -> None:
    if not pedido.agendado_para:
        return
    antes = timedelta(minutes=(pedido.loja.tempo_preparo_min or 30) + 15)
    atraso = int((pedido.agendado_para - antes - timezone.now()).total_seconds())
    enfileirar("pedido.lembrete_agendado", {"pedido_id": str(pedido.id)}, chave=f"lembrete-{pedido.id}",
               atraso_s=max(0, atraso))


@executor("pedido.lembrete_agendado")
def lembrete(pedido_id: str):
    from apps.integracoes import push
    from apps.realtime.eventos import grupo_pdv, publicar

    from .models import Pedido

    p = Pedido.objects.filter(pk=pedido_id).select_related("loja").first()
    if p is None or p.status in ("CONCLUIDO", "CANCELADO", "RECUSADO"):
        return
    hora = timezone.localtime(p.agendado_para).strftime("%H:%M")
    publicar(grupo_pdv(p.loja_id), "pedido.lembrete", {"pedido": str(p.id), "numero": p.numero, "hora": hora})
    push.para_loja(p.loja, f"⏰ Pedido agendado #{p.numero}", f"Para as {hora}: hora de começar o preparo.",
                   {"tipo": "pedido.lembrete", "pedido": str(p.id)}, chave=f"push-lembrete-{p.id}")
