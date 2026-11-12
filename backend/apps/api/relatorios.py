"""Relatórios gerenciais (gerente+). Período: ?inicio=AAAA-MM-DD&fim=AAAA-MM-DD
ou ?periodo=dia|semana|mes (padrão: hoje)."""

from datetime import date, timedelta

from apfood_core.relatorios import curva_abc, ticket_medio
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.caixa.models import TurnoCaixa
from apps.core.api import EhGerente, loja_da_requisicao
from apps.financeiro.models import Despesa
from apps.pedidos.models import ItemPedido, Pagamento, Pedido

from . import serializers as s


def periodo(request) -> tuple[date, date]:
    q = request.query_params
    hoje = timezone.localdate()
    if q.get("inicio") or q.get("fim"):
        inicio, fim = parse_date(q.get("inicio") or ""), parse_date(q.get("fim") or "")
        if not inicio or not fim or fim < inicio:
            raise ValidationError({"periodo": ["informe inicio e fim válidos (AAAA-MM-DD)"]})
        if (fim - inicio).days > 366:
            raise ValidationError({"periodo": ["máximo de 1 ano por consulta"]})
        return inicio, fim
    p = q.get("periodo", "dia")
    if p == "semana":
        return hoje - timedelta(days=hoje.weekday()), hoje
    if p == "mes":
        return hoje.replace(day=1), hoje
    return hoje, hoje


class Relatorio(APIView):
    permission_classes = [EhGerente]

    def base(self, request):
        loja = loja_da_requisicao(request)
        inicio, fim = periodo(request)
        return loja, inicio, fim


class VendasView(Relatorio):
    """Faturamento, ticket médio, por dia, por canal e por forma de pagamento."""

    def get(self, request):
        loja, inicio, fim = self.base(request)
        pedidos = Pedido.objects.filter(loja=loja, status="CONCLUIDO", data_referencia__range=(inicio, fim))
        tot = pedidos.aggregate(fat=Sum("total_centavos"), n=Count("id"), taxa=Sum("taxa_entrega_centavos"),
                                desc=Sum("desconto_centavos"))
        fat, n = tot["fat"] or 0, tot["n"] or 0
        por_dia = list(pedidos.values("data_referencia").annotate(faturamento=Sum("total_centavos"),
                                                                 pedidos=Count("id")).order_by("data_referencia"))
        por_canal = list(pedidos.values("canal").annotate(faturamento=Sum("total_centavos"), pedidos=Count("id")))
        pagamentos = Pagamento.objects.filter(
            Q(pedido__loja=loja) | Q(comanda__loja=loja), status="CONFIRMADO",
            confirmado_em__date__range=(inicio, fim),
        ).values("forma").annotate(bruto=Sum("valor_centavos"), taxas=Sum("taxa_centavos"), quantidade=Count("id"))
        cancelados = Pedido.objects.filter(loja=loja, status__in=["CANCELADO", "RECUSADO"],
                                           data_referencia__range=(inicio, fim)).count()
        return Response({
            "inicio": inicio, "fim": fim, "faturamento_centavos": fat, "pedidos": n,
            "ticket_medio_centavos": ticket_medio(fat, n), "taxas_entrega_centavos": tot["taxa"] or 0,
            "descontos_centavos": tot["desc"] or 0, "cancelados": cancelados,
            "por_dia": [{"data": d["data_referencia"], "faturamento_centavos": d["faturamento"], "pedidos": d["pedidos"],
                         "ticket_medio_centavos": ticket_medio(d["faturamento"], d["pedidos"])} for d in por_dia],
            "por_canal": [{"canal": c["canal"], "faturamento_centavos": c["faturamento"], "pedidos": c["pedidos"],
                           "percentual": round(c["faturamento"] * 100 / fat, 1) if fat else 0} for c in por_canal],
            "por_forma_pagamento": [{"forma": p["forma"], "bruto_centavos": p["bruto"], "taxas_centavos": p["taxas"],
                                     "liquido_centavos": p["bruto"] - p["taxas"], "quantidade": p["quantidade"]}
                                    for p in pagamentos],
        })


class CurvaABCView(Relatorio):
    def get(self, request):
        loja, inicio, fim = self.base(request)
        linhas = (
            ItemPedido.objects.filter(pedido__loja=loja, pedido__status="CONCLUIDO",
                                      pedido__data_referencia__range=(inicio, fim))
            .values("produto_id", "nome_produto").annotate(qtd=Sum("quantidade"), fat=Sum("total_centavos"))
        )
        # agrupa por produto (o nome do snapshot pode variar)
        agrupado: dict[str, list] = {}
        for l in linhas:
            chave = str(l["produto_id"] or l["nome_produto"])
            a = agrupado.setdefault(chave, [chave, l["nome_produto"], 0, 0])
            a[2] += l["qtd"]
            a[3] += l["fat"]
        abc = curva_abc([tuple(v) for v in agrupado.values()])
        return Response({"inicio": inicio, "fim": fim, "itens": [
            {"produto": l.chave, "nome": l.nome, "quantidade": l.quantidade, "faturamento_centavos": l.faturamento_centavos,
             "percentual": l.percentual, "acumulado": l.acumulado, "classe": l.classe} for l in abc
        ]})


class FechamentosView(Relatorio):
    """Fechamentos de caixa por operador/data, com quebra/sobra por forma."""

    def get(self, request):
        loja, inicio, fim = self.base(request)
        qs = TurnoCaixa.objects.filter(loja=loja, status="FECHADO", fechado_em__date__range=(inicio, fim)) \
            .select_related("usuario").prefetch_related("conferencias").order_by("-fechado_em")
        if u := request.query_params.get("usuario"):
            qs = qs.filter(usuario_id=u)
        turnos = [{
            **s.TurnoOut(t).data, "operador": str(t.usuario),
            "conferencia": s.ConferenciaOut(t.conferencias.all(), many=True).data,
        } for t in qs]
        por_operador: dict[str, dict] = {}
        for t in qs:
            o = por_operador.setdefault(str(t.usuario_id), {"operador": str(t.usuario), "turnos": 0, "diferenca_centavos": 0})
            o["turnos"] += 1
            o["diferenca_centavos"] += t.diferenca_centavos or 0
        return Response({"inicio": inicio, "fim": fim, "por_operador": list(por_operador.values()), "turnos": turnos})


class FluxoCaixaView(Relatorio):
    """Entradas (pagamentos confirmados, líquido de taxas) × saídas (despesas
    pagas) por dia, mais o que há a receber e a pagar."""

    def get(self, request):
        loja, inicio, fim = self.base(request)
        pg = Pagamento.objects.filter(Q(pedido__loja=loja) | Q(comanda__loja=loja), status="CONFIRMADO")
        entradas = {e["dia"]: e for e in pg.filter(confirmado_em__date__range=(inicio, fim))
                    .annotate(dia=TruncDate("confirmado_em")).values("dia")
                    .annotate(bruto=Sum("valor_centavos"), taxas=Sum("taxa_centavos"))}
        despesas = Despesa.objects.ativos().filter(loja=loja)
        saidas = {d["data_pagamento"]: d["total"] for d in despesas.filter(data_pagamento__range=(inicio, fim))
                  .values("data_pagamento").annotate(total=Sum("valor_centavos"))}
        dias, dia = [], inicio
        while dia <= fim:
            e = entradas.get(dia, {})
            bruto, taxas, saida = e.get("bruto") or 0, e.get("taxas") or 0, saidas.get(dia, 0)
            dias.append({"data": dia, "entradas_brutas_centavos": bruto, "taxas_centavos": taxas,
                         "entradas_liquidas_centavos": bruto - taxas, "saidas_centavos": saida,
                         "saldo_centavos": bruto - taxas - saida})
            dia += timedelta(days=1)
        hoje = timezone.localdate()
        a_receber = pg.filter(previsao_recebimento__gt=hoje).aggregate(v=Sum("valor_centavos"), t=Sum("taxa_centavos"))
        a_pagar = despesas.filter(data_pagamento__isnull=True).aggregate(v=Sum("valor_centavos"))
        return Response({
            "inicio": inicio, "fim": fim, "dias": dias,
            "total_entradas_liquidas_centavos": sum(d["entradas_liquidas_centavos"] for d in dias),
            "total_saidas_centavos": sum(d["saidas_centavos"] for d in dias),
            "a_receber_centavos": (a_receber["v"] or 0) - (a_receber["t"] or 0),
            "a_pagar_centavos": a_pagar["v"] or 0,
        })


class PlataformaResumoView(APIView):
    """Visão consolidada do MASTER: empresas, lojas e faturamento no período."""

    permission_classes = [EhGerente]

    def get(self, request):
        if not request.user.eh_master:
            raise PermissionDenied("somente o MASTER")
        from apps.lojas.models import Empresa

        inicio, fim = periodo(request)
        dados = []
        for e in Empresa.objects.select_related("plano").prefetch_related("lojas"):
            agg = Pedido.objects.filter(loja__empresa=e, status="CONCLUIDO", data_referencia__range=(inicio, fim)) \
                .aggregate(fat=Sum("total_centavos"), n=Count("id"))
            dados.append({"id": str(e.id), "nome": e.nome, "plano": e.plano.nome if e.plano else None,
                          "status_assinatura": e.status_assinatura, "ativa": e.ativa, "lojas": e.lojas.count(),
                          "faturamento_centavos": agg["fat"] or 0, "pedidos": agg["n"] or 0})
        return Response({"inicio": inicio, "fim": fim, "empresas": dados,
                         "total_faturamento_centavos": sum(d["faturamento_centavos"] for d in dados)})
