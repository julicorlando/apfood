"""Reservas de mesa: pelo link da loja (cliente) ou no painel. Avisos por WhatsApp
(se a loja tiver o número conectado) e no painel."""

from __future__ import annotations

from datetime import timedelta

from apfood_core.horarios import aberta_em
from django.utils import timezone

from apps.core.excecoes import ErroNegocio

from .models import Reserva


def _quando(r: Reserva) -> str:
    return timezone.localtime(r.data_hora).strftime("%d/%m às %H:%M")


def avisar_cliente(r: Reserva, texto: str, chave: str) -> None:
    from apps.integracoes.models import Integracao
    from apps.integracoes.tarefas import enfileirar

    integ = Integracao.ativa(r.loja, "WHATSAPP", "whatsapp")
    if integ is None or len(r.telefone) < 10:
        return
    enfileirar("whatsapp.enviar", {"integracao_id": str(integ.id), "telefone": r.telefone, "mensagem": texto}, chave=chave)


def criar_publica(loja, *, nome: str, telefone: str, pessoas: int, data_hora, observacao: str = "") -> Reserva:
    if not loja.aceita_reservas:
        raise ErroNegocio("esta loja não está aceitando reservas pelo site")
    tel = "".join(c for c in telefone if c.isdigit())[-11:]
    if len(tel) < 10:
        raise ErroNegocio("informe o celular com DDD", "telefone")
    if not nome.strip():
        raise ErroNegocio("informe o seu nome", "nome")
    if not 1 <= pessoas <= 40:
        raise ErroNegocio("número de pessoas inválido", "pessoas")
    if timezone.is_naive(data_hora):
        data_hora = timezone.make_aware(data_hora, timezone.get_current_timezone())
    agora = timezone.now()
    if data_hora < agora + timedelta(minutes=30):
        raise ErroNegocio("reserve com pelo menos 30 minutos de antecedência", "data_hora")
    if data_hora > agora + timedelta(days=60):
        raise ErroNegocio("reservas até 60 dias à frente", "data_hora")
    if not aberta_em(loja.horarios, timezone.localtime(data_hora)):
        raise ErroNegocio("a loja não funciona nesse horário", "data_hora")
    r = Reserva.objects.create(loja=loja, nome=nome.strip()[:120], telefone=tel, pessoas=pessoas, data_hora=data_hora,
                               observacao=(observacao or "").strip()[:255], origem="SITE")
    notificar_loja(r)
    avisar_cliente(r, f"📅 *{loja.nome}*: recebemos seu pedido de reserva para {r.pessoas} pessoa(s) em {_quando(r)}. "
                      "Avisamos aqui quando for confirmada.", f"reserva-{r.id}-recebida")
    return r


def notificar_loja(r: Reserva) -> None:
    from apps.integracoes import push
    from apps.realtime.eventos import grupo_pdv, publicar

    publicar(grupo_pdv(r.loja_id), "reserva.nova", {"nome": r.nome, "pessoas": r.pessoas, "quando": _quando(r)})
    push.para_loja(r.loja, "📅 Nova reserva", f"{r.nome} · {r.pessoas} pessoa(s) · {_quando(r)}",
                   {"tipo": "reserva", "reserva": str(r.id)}, chave=f"push-reserva-{r.id}")


def mudar_status(r: Reserva, status: str, usuario=None) -> Reserva:
    validos = {Reserva.CONFIRMADA, Reserva.CANCELADA, Reserva.CHEGOU, Reserva.NAO_VEIO, Reserva.PENDENTE}
    if status not in validos:
        raise ErroNegocio("status inválido")
    r.status = status
    if status == Reserva.CHEGOU and r.mesa_id and not r.comanda_id:
        from . import services
        from .models import Comanda

        aberta = Comanda.objects.filter(mesa_id=r.mesa_id, status__in=["ABERTA", "FECHANDO"]).first()
        r.comanda = aberta or services.abrir(r.loja, usuario, mesa=r.mesa, nome_cliente=r.nome, pessoas=r.pessoas)
    r.save()
    if status == Reserva.CONFIRMADA:
        mesa = f" (mesa {r.mesa.nome})" if r.mesa_id else ""
        avisar_cliente(r, f"✅ *{r.loja.nome}*: sua reserva para {r.pessoas} pessoa(s) em {_quando(r)}{mesa} está confirmada. "
                          "Até lá!", f"reserva-{r.id}-confirmada")
    elif status == Reserva.CANCELADA:
        avisar_cliente(r, f"❌ *{r.loja.nome}*: sua reserva de {_quando(r)} foi cancelada. Qualquer dúvida, fale com a gente.",
                       f"reserva-{r.id}-cancelada")
    return r
