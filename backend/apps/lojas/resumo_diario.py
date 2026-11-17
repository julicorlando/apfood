"""Resumo do dia para o dono: vendas, pedidos, ticket, cancelados, entregas, mais vendidos,
nota média e tempo médio. Vai como push (app Empresa, se o Firebase estiver ligado) e
WhatsApp para os números da configuração, na hora escolhida (rotinas_diarias, de hora em hora)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from apfood_core.dinheiro import formatar
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.integracoes.tarefas import enfileirar, executor


def calcular(loja, dia=None) -> dict:
    from apps.pedidos.models import Avaliacao, ItemPedido, Pedido

    dia = dia or timezone.localdate()
    inicio = timezone.make_aware(datetime.combine(dia, time.min))
    fim = inicio + timedelta(days=1)
    qs = Pedido.objects.filter(loja=loja, criado_em__gte=inicio, criado_em__lt=fim)
    feitos = qs.filter(status="CONCLUIDO")
    fat = feitos.aggregate(s=Sum("total_centavos"))["s"] or 0
    n = feitos.count()
    top = list(ItemPedido.objects.filter(pedido__in=feitos).values("nome_produto")
               .annotate(q=Sum("quantidade")).order_by("-q")[:3])
    nota = Avaliacao.objects.filter(pedido__loja=loja, criado_em__gte=inicio, criado_em__lt=fim).aggregate(m=Avg("nota"), n=Count("id"))
    tempos = [(p.concluido_em - p.criado_em).total_seconds() / 60 for p in feitos.only("criado_em", "concluido_em")
              if p.concluido_em]
    return {
        "dia": dia.isoformat(), "faturamento_centavos": fat, "pedidos": n,
        "ticket_medio_centavos": round(fat / n) if n else 0,
        "cancelados": qs.filter(status__in=["CANCELADO", "RECUSADO"]).count(),
        "entregas": feitos.filter(tipo_atendimento="ENTREGA").count(),
        "mais_vendidos": [{"nome": t["nome_produto"], "quantidade": t["q"]} for t in top],
        "nota_media": round(nota["m"], 1) if nota["m"] else None, "avaliacoes": nota["n"],
        "tempo_medio_min": round(sum(tempos) / len(tempos)) if tempos else None,
    }


def texto(loja, r: dict) -> str:
    linhas = [f"📊 *Resumo de hoje — {loja.nome}*",
              f"💰 Vendas: *{formatar(r['faturamento_centavos'])}* em {r['pedidos']} pedido(s)",
              f"🧾 Ticket médio: {formatar(r['ticket_medio_centavos'])}"]
    if r["entregas"]:
        linhas.append(f"🛵 Entregas: {r['entregas']}")
    if r["cancelados"]:
        linhas.append(f"❌ Cancelados: {r['cancelados']}")
    if r["tempo_medio_min"]:
        linhas.append(f"⏱️ Tempo médio do pedido: {r['tempo_medio_min']} min")
    if r["nota_media"]:
        linhas.append(f"⭐ Nota média: {str(r['nota_media']).replace('.', ',')} ({r['avaliacoes']} avaliação(ões))")
    if r["mais_vendidos"]:
        linhas.append("🏆 Mais vendidos: " + ", ".join(f"{m['nome']} ({m['quantidade']})" for m in r["mais_vendidos"]))
    return "\n".join(linhas)


def numeros(loja) -> list[str]:
    out = []
    for parte in (loja.resumo_diario_whatsapp or "").replace(";", ",").split(","):
        d = "".join(c for c in parte if c.isdigit())
        if len(d) >= 10:
            out.append(d)
    return out


def enviar(loja, *, dia=None, chave_extra: str = "") -> dict:
    """Manda agora (push + WhatsApp). Retorna o resumo e para onde foi."""
    from apps.integracoes import push
    from apps.integracoes.models import Integracao

    r = calcular(loja, dia)
    corpo = texto(loja, r)
    sufixo = f"{r['dia']}{chave_extra}"
    push.para_loja(loja, f"Resumo de hoje: {formatar(r['faturamento_centavos'])}",
                   f"{r['pedidos']} pedido(s) · ticket {formatar(r['ticket_medio_centavos'])}",
                   {"tipo": "resumo.dia"}, chave=f"push-resumo-{loja.id}-{sufixo}")
    enviados = []
    integ = Integracao.ativa(loja, "WHATSAPP", "whatsapp")
    if integ is not None:
        for tel in numeros(loja):
            enfileirar("whatsapp.enviar", {"integracao_id": str(integ.id), "telefone": tel, "mensagem": corpo},
                       chave=f"resumo-{loja.id}-{tel}-{sufixo}")
            enviados.append(tel)
    return {"resumo": r, "texto": corpo, "whatsapp": enviados, "whatsapp_conectado": integ is not None,
            "push": push.ativo()}


def rodar(loja, agora=None) -> bool:
    """Chamado de hora em hora: envia uma vez por dia, na hora configurada."""
    agora = timezone.localtime(agora or timezone.now())
    if not loja.resumo_diario_ativo or agora.hour != (loja.resumo_diario_hora % 24):
        return False
    enfileirar("resumo.dia", {"loja_id": str(loja.id), "dia": agora.date().isoformat()},
               chave=f"resumo-dia-{loja.id}-{agora.date().isoformat()}")
    return True


@executor("resumo.dia")
def _tarefa(loja_id: str, dia: str):
    from datetime import date

    from apps.lojas.models import Loja

    loja = Loja.objects.filter(pk=loja_id).first()
    if loja is not None and loja.resumo_diario_ativo:
        enviar(loja, dia=date.fromisoformat(dia))
