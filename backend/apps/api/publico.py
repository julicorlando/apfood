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


class CardapioPublicoView(Publica):
    def get(self, request, slug):
        loja = loja_publica(slug)
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
                    "id": str(p.id), "nome": p.nome, "descricao": p.descricao,
                    "imagem": request.build_absolute_uri(p.imagem.url) if p.imagem else None,
                    "preco_centavos": p.preco_centavos, "esgotado": pausado,
                    "variacoes": [{"id": str(v.id), "nome": v.nome, "preco_centavos": v.preco_centavos}
                                  for v in p.variacoes.ativos().filter(ativo=True)],
                    "grupos": grupos,
                })
            if produtos:
                categorias.append({"id": str(c.id), "nome": c.nome, "descricao": c.descricao,
                                   "max_sabores": c.max_sabores, "regra_preco_sabores": c.regra_preco_sabores,
                                   "produtos": produtos})
        return Response({
            "loja": {
                "nome": loja.nome, "slug": loja.slug, "logo": request.build_absolute_uri(loja.logo.url) if loja.logo else None,
                "cor_primaria": loja.cor_primaria, "telefone": loja.telefone, "whatsapp": loja.whatsapp,
                "aberta": loja.aberta_para_pedidos, "horarios": loja.horarios,
                "pedido_minimo_centavos": loja.pedido_minimo_centavos, "tempo_preparo_min": loja.tempo_preparo_min,
                "endereco": f"{loja.logradouro}, {loja.numero} — {loja.bairro}" if loja.logradouro else "",
            },
            "categorias": categorias,
        })


class TaxaEntregaPublicaView(Publica):
    throttle_scope = "publico"

    def post(self, request, slug):
        loja = loja_publica(slug)
        zona, dist = calcular_taxa_entrega(loja, bairro=request.data.get("bairro"),
                                           latitude=request.data.get("latitude"), longitude=request.data.get("longitude"))
        return Response({"taxa_centavos": zona.taxa_centavos, "tempo_estimado_min": zona.tempo_estimado_min})


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
        return Response({
            "loja": p.loja.nome, "numero": p.numero, "status": p.status,
            "etapa": ETAPA_CLIENTE[StatusPedido(p.status)], "tipo_atendimento": p.tipo_atendimento,
            "itens": [{"quantidade": i.quantidade, "nome": i.nome_produto, "variacao": i.nome_variacao,
                       "total_centavos": i.total_centavos} for i in p.itens.all()],
            "subtotal_centavos": p.subtotal_centavos, "taxa_entrega_centavos": p.taxa_entrega_centavos,
            "desconto_centavos": p.desconto_centavos, "total_centavos": p.total_centavos,
            "criado_em": p.criado_em, "aceito_em": p.aceito_em, "saiu_entrega_em": p.saiu_entrega_em,
            "concluido_em": p.concluido_em, "motivo_cancelamento": p.motivo_cancelamento,
            "pago": sum(x.valor_centavos for x in p.pagamentos.filter(status="CONFIRMADO")) >= p.total_centavos,
            "pix": next(({"valor_centavos": x.valor_centavos, **x.dados_externos}
                         for x in p.pagamentos.filter(status="PENDENTE", forma="PIX") if x.dados_externos), None),
        })
