"""Rede / franquia: várias lojas da mesma empresa.

- resumo: faturamento, pedidos, ticket, cancelados e avaliação de cada loja no período;
- replicar: copia o cardápio (categorias, produtos, tamanhos, adicionais) de uma
  loja para outras — casando pelo nome; com `somente_precos`, só atualiza os
  preços do que já existe. Ficha técnica e estoque ficam de fora (cada loja tem
  os seus insumos)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Avg, Count, Q, Sum

from apps.cardapio.models import Adicional, Categoria, GrupoAdicional, Produto, ProdutoGrupoAdicional, ProdutoVariacao
from apps.pedidos.models import Avaliacao, Pedido


def resumo(lojas, inicio, fim) -> dict:
    linhas = []
    for l in lojas:
        ps = Pedido.objects.filter(loja=l, data_referencia__range=(inicio, fim))
        a = ps.aggregate(fat=Sum("total_centavos", filter=Q(status="CONCLUIDO")), n=Count("id", filter=Q(status="CONCLUIDO")),
                         canc=Count("id", filter=Q(status__in=["CANCELADO", "RECUSADO"])),
                         entregas=Count("id", filter=Q(status="CONCLUIDO", tipo_atendimento="ENTREGA")),
                         online=Count("id", filter=Q(status="CONCLUIDO", canal="ONLINE")))
        nota = Avaliacao.objects.filter(loja=l, criado_em__date__range=(inicio, fim)).aggregate(m=Avg("nota"))["m"]
        fat, n = a["fat"] or 0, a["n"] or 0
        linhas.append({"loja_id": str(l.id), "loja": l.nome, "cidade": l.cidade, "faturamento_centavos": fat, "pedidos": n,
                       "ticket_medio_centavos": fat // n if n else 0, "cancelados": a["canc"] or 0,
                       "entregas": a["entregas"] or 0, "online": a["online"] or 0,
                       "nota_media": round(nota, 2) if nota else None})
    linhas.sort(key=lambda x: -x["faturamento_centavos"])
    total_fat = sum(x["faturamento_centavos"] for x in linhas)
    total_n = sum(x["pedidos"] for x in linhas)
    for x in linhas:
        x["participacao"] = round(100 * x["faturamento_centavos"] / total_fat, 1) if total_fat else 0
    return {"lojas": linhas, "total": {"faturamento_centavos": total_fat, "pedidos": total_n,
                                       "ticket_medio_centavos": total_fat // total_n if total_n else 0,
                                       "cancelados": sum(x["cancelados"] for x in linhas)}}


def _por_nome(qs):
    return {x.nome.strip().lower(): x for x in qs}


@transaction.atomic
def replicar(origem, destino, *, somente_precos: bool = False) -> dict:
    if origem.empresa_id != destino.empresa_id or origem.pk == destino.pk:
        raise ValueError("lojas de empresas diferentes")
    cont = {"categorias": 0, "produtos_novos": 0, "produtos_atualizados": 0, "grupos": 0}

    # grupos de adicionais
    grupos_dest = _por_nome(GrupoAdicional.objects.ativos().filter(loja=destino))
    mapa_grupo = {}
    for g in GrupoAdicional.objects.ativos().filter(loja=origem).prefetch_related("adicionais"):
        gd = grupos_dest.get(g.nome.strip().lower())
        if gd is None:
            if somente_precos:
                continue
            gd = GrupoAdicional.objects.create(loja=destino, nome=g.nome, min_selecao=g.min_selecao, max_selecao=g.max_selecao,
                                               ordem=g.ordem, ativo=g.ativo)
            cont["grupos"] += 1
        mapa_grupo[g.id] = gd
        ads_dest = _por_nome(gd.adicionais.ativos())
        for a in g.adicionais.ativos():
            ad = ads_dest.get(a.nome.strip().lower())
            if ad is None and not somente_precos:
                Adicional.objects.create(grupo=gd, nome=a.nome, preco_centavos=a.preco_centavos, max_por_item=a.max_por_item,
                                         ativo=a.ativo, ordem=a.ordem)
            elif ad is not None and ad.preco_centavos != a.preco_centavos:
                ad.preco_centavos = a.preco_centavos
                ad.save(update_fields=["preco_centavos", "atualizado_em"])

    # categorias
    cats_dest = _por_nome(Categoria.objects.ativos().filter(loja=destino))
    mapa_cat = {}
    for c in Categoria.objects.ativos().filter(loja=origem):
        cd = cats_dest.get(c.nome.strip().lower())
        if cd is None and not somente_precos:
            cd = Categoria.objects.create(loja=destino, nome=c.nome, descricao=c.descricao, ordem=c.ordem, ativa=c.ativa,
                                          max_sabores=c.max_sabores, regra_preco_sabores=c.regra_preco_sabores,
                                          disponibilidade=c.disponibilidade)
            cont["categorias"] += 1
        if cd is not None:
            mapa_cat[c.id] = cd

    # produtos de venda
    prods_dest = _por_nome(Produto.objects.ativos().filter(loja=destino, tipo="VENDA"))
    for p in (Produto.objects.ativos().filter(loja=origem, tipo="VENDA")
              .prefetch_related("variacoes", "produtogrupoadicional_set")):
        pd = prods_dest.get(p.nome.strip().lower())
        if pd is None:
            if somente_precos:
                continue
            pd = Produto.objects.create(
                loja=destino, categoria=mapa_cat.get(p.categoria_id), tipo=p.tipo, nome=p.nome, descricao=p.descricao,
                imagem=p.imagem.name if p.imagem else "", codigo=p.codigo, gtin=p.gtin, preco_centavos=p.preco_centavos,
                custo_centavos=p.custo_centavos, ativo=p.ativo, disponivel_online=p.disponivel_online, ordem=p.ordem,
                ncm=p.ncm, cest=p.cest, cfop=p.cfop, origem=p.origem, cst_csosn=p.cst_csosn, aliquota_icms=p.aliquota_icms,
                unidade=p.unidade)
            cont["produtos_novos"] += 1
            for v in p.variacoes.ativos():
                ProdutoVariacao.objects.create(produto=pd, nome=v.nome, preco_centavos=v.preco_centavos,
                                               fator_insumos=v.fator_insumos, codigo=v.codigo, ordem=v.ordem, ativo=v.ativo)
            for pg in p.produtogrupoadicional_set.all():
                if pg.grupo_id in mapa_grupo:
                    ProdutoGrupoAdicional.objects.get_or_create(produto=pd, grupo=mapa_grupo[pg.grupo_id],
                                                                defaults={"ordem": pg.ordem})
            continue
        mudou = []
        if pd.preco_centavos != p.preco_centavos:
            pd.preco_centavos = p.preco_centavos
            mudou.append("preco_centavos")
        if not somente_precos and p.descricao and pd.descricao != p.descricao:
            pd.descricao = p.descricao
            mudou.append("descricao")
        if mudou:
            pd.save(update_fields=[*mudou, "atualizado_em"])
        vars_dest = _por_nome(pd.variacoes.ativos())
        for v in p.variacoes.ativos():
            vd = vars_dest.get(v.nome.strip().lower())
            if vd is not None and vd.preco_centavos != v.preco_centavos:
                vd.preco_centavos = v.preco_centavos
                vd.save(update_fields=["preco_centavos", "atualizado_em"])
                mudou.append("variacao")
            elif vd is None and not somente_precos:
                ProdutoVariacao.objects.create(produto=pd, nome=v.nome, preco_centavos=v.preco_centavos,
                                               fator_insumos=v.fator_insumos, codigo=v.codigo, ordem=v.ordem, ativo=v.ativo)
        if mudou:
            cont["produtos_atualizados"] += 1
    return cont
