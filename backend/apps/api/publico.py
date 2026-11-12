"""API pública do cardápio digital (sem login). Escopo pela `slug` da loja."""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cardapio.models import Categoria, ProdutoGrupoAdicional
from apps.clientes.services import calcular_taxa_entrega
from apps.lojas.models import Loja
from apps.pedidos import services as pedidos_srv
from apps.pedidos.models import Pedido

from . import serializers as s
from .views import pedido_in


def loja_publica(slug):
    loja = get_object_or_404(Loja.objects.select_related("empresa"), slug=slug, ativa=True)
    if not loja.empresa.liberada:
        from django.http import Http404

        raise Http404
    return loja


class Publica(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


def _url(request, arquivo):
    return request.build_absolute_uri(arquivo.url) if arquivo else None


def dados_loja_publica(loja, request) -> dict:
    from apfood_core.horarios import aberta_em, proxima_abertura

    from apps.clientes.models import ZonaEntrega
    from apps.integracoes.models import Integracao

    agora = timezone.localtime()
    proxima = proxima_abertura(loja.horarios, agora)
    return {
        "nome": loja.nome, "slug": loja.slug, "logo": _url(request, loja.logo), "cor_primaria": loja.cor_primaria,
        "telefone": loja.telefone, "whatsapp": loja.whatsapp,
        "aberta": bool(loja.aberta_para_pedidos and aberta_em(loja.horarios, agora)),
        "proxima_abertura": proxima.isoformat() if proxima and not aberta_em(loja.horarios, agora) else None,
        "horarios": loja.horarios, "pedido_minimo_centavos": loja.pedido_minimo_centavos,
        "tempo_preparo_min": loja.tempo_preparo_min,
        "endereco": f"{loja.logradouro}, {loja.numero} — {loja.bairro}" if loja.logradouro else "",
        "entrega": ZonaEntrega.objects.ativos().filter(loja=loja, ativa=True).exists(),
        "retirada": True,
        "pix_online": Integracao.ativa(loja, "PAGAMENTO", "mercadopago") is not None,
    }


def dados_cardapio(loja, request) -> dict:
    agora = timezone.now()
    categorias = []
    for c in Categoria.objects.ativos().filter(loja=loja, ativa=True).order_by("ordem", "nome"):
        produtos = []
        for p in c.produtos.ativos().filter(ativo=True, disponivel_online=True, tipo="VENDA").order_by("ordem", "nome"):
            pausado = p.pausado and (p.pausado_ate is None or p.pausado_ate > agora)
            grupos = []
            for pg in ProdutoGrupoAdicional.objects.filter(
                produto=p, grupo__ativo=True, grupo__excluido_em__isnull=True
            ).select_related("grupo").order_by("ordem"):
                g = pg.grupo
                grupos.append({
                    "id": str(g.id), "nome": g.nome, "min": g.min_selecao, "max": g.max_selecao,
                    "opcoes": [{"id": str(a.id), "nome": a.nome, "preco_centavos": a.preco_centavos,
                                "max_por_item": a.max_por_item}
                               for a in g.adicionais.ativos().filter(ativo=True)],
                })
            produtos.append({
                "id": str(p.id), "nome": p.nome, "descricao": p.descricao, "imagem": _url(request, p.imagem),
                "preco_centavos": p.preco_centavos, "esgotado": pausado,
                "variacoes": [{"id": str(v.id), "nome": v.nome, "preco_centavos": v.preco_centavos}
                              for v in p.variacoes.ativos().filter(ativo=True)],
                "grupos": grupos,
            })
        if produtos:
            categorias.append({"id": str(c.id), "nome": c.nome, "descricao": c.descricao,
                               "max_sabores": c.max_sabores, "regra_preco_sabores": c.regra_preco_sabores,
                               "produtos": produtos})
    return {"loja": dados_loja_publica(loja, request), "categorias": categorias}


class CardapioPublicoView(Publica):
    def get(self, request, slug):
        return Response(dados_cardapio(loja_publica(slug), request))


class CupomPublicoView(Publica):
    """Confere o cupom antes de enviar o pedido: {codigo, subtotal_centavos, taxa_entrega_centavos, telefone}."""

    throttle_scope = "publico"

    def post(self, request, slug):
        from apfood_core.enums import CanalVenda, TipoAtendimento

        loja = loja_publica(slug)
        try:
            subtotal = int(request.data.get("subtotal_centavos") or 0)
            taxa = int(request.data.get("taxa_entrega_centavos") or 0)
        except (TypeError, ValueError):
            subtotal = taxa = 0
        dados = pedidos_srv.PedidoIn(canal=CanalVenda.ONLINE, tipo_atendimento=TipoAtendimento.RETIRADA, itens=[],
                                     telefone_cliente=str(request.data.get("telefone") or ""))
        cupom, desconto = pedidos_srv._cupom(loja, str(request.data.get("codigo") or ""), subtotal, taxa, dados)
        return Response({"codigo": cupom.codigo, "descricao": cupom.descricao, "desconto_centavos": desconto})


class TaxaEntregaPublicaView(Publica):
    throttle_scope = "publico"

    def post(self, request, slug):
        loja = loja_publica(slug)
        endereco = {k: request.data.get(k, "") or "" for k in ("logradouro", "numero", "bairro", "cidade", "cep")}
        zona, dist = calcular_taxa_entrega(loja, bairro=request.data.get("bairro"),
                                           latitude=request.data.get("latitude"), longitude=request.data.get("longitude"),
                                           endereco=endereco if endereco["logradouro"] else None)
        return Response({"taxa_centavos": zona.taxa_centavos, "tempo_estimado_min": zona.tempo_estimado_min,
                         "latitude": endereco.get("latitude"), "longitude": endereco.get("longitude")})


class PedidoPublicoView(Publica):
    throttle_scope = "publico_pedido"

    def post(self, request, slug):
        loja = loja_publica(slug)
        entrada = s.PedidoOnlineIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        pedido = pedidos_srv.criar_pedido(loja, pedido_in(entrada.validated_data, loja))
        resposta = {
            "token": pedido.token_rastreio, "numero": pedido.numero, "status": pedido.status,
            "total_centavos": pedido.total_centavos, "acompanhar": f"/pedido/{pedido.token_rastreio}/",
        }
        if entrada.validated_data.get("forma_pagamento_prevista") == "PIX" and request.data.get("pagar_pix_agora"):
            from apps.integracoes.models import Integracao

            if Integracao.ativa(loja, "PAGAMENTO", "mercadopago"):
                pg = pedidos_srv.cobrar_pix(pedido=pedido)
                resposta["pix"] = {"valor_centavos": pg.valor_centavos, **pg.dados_externos}
        return Response(resposta, status=status.HTTP_201_CREATED)


class AcompanharPedidoView(Publica):
    def get(self, request, token):
        from apfood_core.enums import StatusPedido
        from apfood_core.pedido_status import ETAPA_CLIENTE

        p = get_object_or_404(Pedido.objects.select_related("loja"), token_rastreio=token)
        prevista = next((x.forma for x in p.pagamentos.filter(status="PENDENTE")), "")
        return Response({
            "loja": p.loja.nome, "loja_slug": p.loja.slug, "whatsapp": p.loja.whatsapp or p.loja.telefone,
            "cor_primaria": p.loja.cor_primaria, "tempo_preparo_min": p.loja.tempo_preparo_min,
            "numero": p.numero, "status": p.status, "forma_prevista": prevista, "troco_para_centavos": p.troco_para_centavos,
            "endereco": f"{p.entrega_logradouro}, {p.entrega_numero} — {p.entrega_bairro}" if p.entrega_logradouro else "",
            "etapa": ETAPA_CLIENTE[StatusPedido(p.status)], "tipo_atendimento": p.tipo_atendimento,
            "itens": [{"quantidade": i.quantidade, "nome": i.nome_produto, "variacao": i.nome_variacao,
                       "total_centavos": i.total_centavos, "observacao": i.observacao,
                       "adicionais": [f"{a.quantidade}x {a.nome}" for a in i.adicionais.all()]}
                      for i in p.itens.prefetch_related("adicionais")],
            "subtotal_centavos": p.subtotal_centavos, "taxa_entrega_centavos": p.taxa_entrega_centavos,
            "desconto_centavos": p.desconto_centavos, "total_centavos": p.total_centavos,
            "criado_em": p.criado_em, "aceito_em": p.aceito_em, "saiu_entrega_em": p.saiu_entrega_em,
            "concluido_em": p.concluido_em, "motivo_cancelamento": p.motivo_cancelamento,
            "pago": sum(x.valor_centavos for x in p.pagamentos.filter(status="CONFIRMADO")) >= p.total_centavos,
            "pix": next(({"valor_centavos": x.valor_centavos, **x.dados_externos}
                         for x in p.pagamentos.filter(status="PENDENTE", forma="PIX") if x.dados_externos), None),
        })
