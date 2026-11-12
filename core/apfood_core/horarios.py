"""Horário de funcionamento: `[{"dia_semana": 0-6 (seg=0), "abre": "18:00", "fecha": "02:00"}]`.
Turno que passa da meia-noite (fecha < abre) vale até o horário de fechamento do dia seguinte."""

from __future__ import annotations

from datetime import datetime, time, timedelta


def _hora(texto: str) -> time:
    h, m = (texto or "00:00").split(":")[:2]
    return time(int(h) % 24, int(m))


def aberta_em(horarios: list[dict] | None, agora: datetime) -> bool:
    """Sem horários cadastrados = sempre aberta (vale só o botão "aberta para pedidos")."""
    if not horarios:
        return True
    for h in horarios:
        dia, abre, fecha = int(h["dia_semana"]), _hora(h["abre"]), _hora(h["fecha"])
        for base in (agora.date(), agora.date() - timedelta(days=1)):
            if base.weekday() != dia:
                continue
            inicio = datetime.combine(base, abre, agora.tzinfo)
            fim = datetime.combine(base + timedelta(days=1 if fecha <= abre else 0), fecha, agora.tzinfo)
            if inicio <= agora < fim:
                return True
    return False


def proxima_abertura(horarios: list[dict] | None, agora: datetime) -> datetime | None:
    if not horarios:
        return None
    candidatos = []
    for desloc in range(8):
        d = agora.date() + timedelta(days=desloc)
        for h in horarios:
            if int(h["dia_semana"]) == d.weekday():
                inicio = datetime.combine(d, _hora(h["abre"]), agora.tzinfo)
                if inicio > agora:
                    candidatos.append(inicio)
    return min(candidatos) if candidatos else None
