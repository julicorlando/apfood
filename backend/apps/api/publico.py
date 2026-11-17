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
        "fidelidade": {"selos": loja.fidelidade_selos, "premio": loja.fidelidade_premio_descricao
                       or (f"R$ {loja.fidelidade_premio_centavos / 100:.2f} de crédito".replace(".", ",")
                           if loja.fidelidade_premio_centavos else "")} if loja.fidelidade_selos else None,
    }


def dados_cardapio(loja, request) -> dict:
    from apps.api.views import promocoes_agora
    from apps.marketing.models import Promocao

    agora = timezone.now()
    promo_online = promocoes_agora(loja, canais=("ONLINE",))["ONLINE"]
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
                "promocao": promo_online.get(str(p.id)),
            })
        if produtos:
            categorias.append({"id": str(c.id), "nome": c.nome, "descricao": c.descricao,
                               "max_sabores": c.max_sabores, "regra_preco_sabores": c.regra_preco_sabores,
                               "produtos": produtos})
    # promoções do dia (para a faixa no topo do cardápio), mesmo as que começam mais tarde
    hoje = timezone.localdate()
    do_dia = []
    for promo in Promocao.objects.ativos().filter(loja=loja, ativa=True).order_by("hora_inicio", "nome"):
        r = promo.regra()
        if r.canais and "ONLINE" not in r.canais:
            continue
        if (r.dias and hoje.weekday() not in r.dias) or (r.data_inicio and hoje < r.data_inicio) \
                or (r.data_fim and hoje > r.data_fim):
            continue
        do_dia.append({"nome": promo.nome, "descricao": promo.descricao, "resumo": r.descricao()})
    return {"loja": dados_loja_publica(loja, request), "categorias": categorias, "promocoes": do_dia}


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


def rastreio_entrega(p) -> dict | None:
    """Onde está o entregador (só enquanto o pedido está "saiu para entrega" e a
    posição tem menos de 10 minutos)."""
    from datetime import timedelta

    from apfood_core.entrega import distancia_km

    e = p.entregador if p.entregador_id else None
    if p.status != "SAIU_PARA_ENTREGA" or e is None or e.latitude is None or not e.localizacao_em:
        return None
    if timezone.now() - e.localizacao_em > timedelta(minutes=10):
        return None
    r = {"entregador": e.nome.split(" ")[0], "latitude": float(e.latitude), "longitude": float(e.longitude),
         "atualizado_em": e.localizacao_em}
    if p.entrega_latitude is not None and p.entrega_longitude is not None:
        km = distancia_km(float(e.latitude), float(e.longitude), float(p.entrega_latitude), float(p.entrega_longitude))
        r.update(destino={"latitude": float(p.entrega_latitude), "longitude": float(p.entrega_longitude)},
                 distancia_km=round(km, 1), minutos=max(1, round(km / 20 * 60)))  # ~20 km/h na cidade
    return r


class AcompanharPedidoView(Publica):
    def get(self, request, token):
        from apfood_core.enums import StatusPedido
        from apfood_core.pedido_status import ETAPA_CLIENTE

        p = get_object_or_404(Pedido.objects.select_related("loja", "cliente", "entregador"), token_rastreio=token)
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
            "fidelidade": {"selos": p.cliente.selos, "meta": p.loja.fidelidade_selos,
                           "saldo_centavos": p.cliente.saldo_cashback_centavos}
            if p.cliente_id and p.loja.fidelidade_selos else None,
            "rastreio": rastreio_entrega(p),
            "pix": next(({"valor_centavos": x.valor_centavos, **x.dados_externos}
                         for x in p.pagamentos.filter(status="PENDENTE", forma="PIX") if x.dados_externos), None),
        })


# =============================================================================
# Autoatendimento na mesa (QR Code)
# =============================================================================
def mesa_publica(loja, token):
    from apps.salao.models import Mesa

    mesa = Mesa.objects.ativos().filter(loja=loja, token_qr=token, ativa=True).first()
    if mesa is None or not loja.pedido_na_mesa:
        from django.http import Http404

        raise Http404
    return mesa


def comanda_da_mesa(loja, mesa):
    """Comanda aberta da mesa; abre uma se a mesa está livre."""
    from apps.salao import services as salao_srv
    from apps.salao.models import ABERTAS, Comanda

    c = Comanda.objects.filter(loja=loja, mesa=mesa, status__in=ABERTAS).order_by("criado_em").first()
    if c is None:
        c = salao_srv.abrir(loja, None, mesa=mesa)
    return c


class MesaPublicaView(Publica):
    """GET: conta parcial da mesa (o cliente vê o que já pediu)."""

    def get(self, request, slug, token):
        from apps.pedidos.services import total_pago
        from apps.salao.models import ABERTAS, Comanda

        loja = loja_publica(slug)
        mesa = mesa_publica(loja, token)
        c = Comanda.objects.filter(loja=loja, mesa=mesa, status__in=ABERTAS).first()
        if c is None:
            return Response({"mesa": mesa.nome, "aberta": False, "itens": [], "total_centavos": 0, "pago_centavos": 0})
        itens = [{"quantidade": i.quantidade, "nome": i.nome_produto, "total_centavos": i.total_centavos}
                 for p in c.pedidos.exclude(status__in=["CANCELADO", "RECUSADO"]).prefetch_related("itens")
                 for i in p.itens.all()]
        return Response({"mesa": mesa.nome, "aberta": True, "status": c.status, "itens": itens,
                         "subtotal_centavos": c.subtotal_centavos, "taxa_servico_centavos": c.taxa_servico_centavos,
                         "total_centavos": c.total_centavos, "pago_centavos": total_pago(comanda=c)})


class PedidoMesaView(Publica):
    throttle_scope = "publico_pedido"

    def post(self, request, slug, token):
        from apps.core.excecoes import ErroNegocio

        from .views import pedido_in

        loja = loja_publica(slug)
        if not loja.aberta_para_pedidos:
            raise ErroNegocio("a loja não está recebendo pedidos agora — chame o garçom")
        mesa = mesa_publica(loja, token)
        entrada = s.PedidoMesaIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        comanda = comanda_da_mesa(loja, mesa)
        if comanda.status != "ABERTA":
            raise ErroNegocio("a conta desta mesa já foi pedida — chame o garçom para pedir mais")
        dados = {**entrada.validated_data, "comanda": comanda.id, "mesa": mesa.nome[:10]}
        dados["observacao"] = ("[pedido pelo QR da mesa] " + dados.get("observacao", "")).strip()
        pedido = pedidos_srv.criar_pedido(loja, pedido_in(dados, loja))
        return Response({"token": pedido.token_rastreio, "numero": pedido.numero, "status": pedido.status,
                         "total_centavos": pedido.total_centavos, "mesa": mesa.nome,
                         "acompanhar": f"/pedido/{pedido.token_rastreio}/"}, status=status.HTTP_201_CREATED)


# =============================================================================
# App do cliente: restaurantes da região
# =============================================================================
class LojasPublicasView(Publica):
    """GET /api/publico/lojas/?lat=&lng=&raio=&cidade=&busca=

    Com lat/lng: lojas até `raio` km (padrão 25), da mais perto para a mais longe.
    Sem localização: filtra pela cidade (se informada). Abertas primeiro."""

    def get(self, request):
        from apfood_core.entrega import distancia_km
        from django.db.models import Q

        from apps.clientes.models import ZonaEntrega
        from apps.marketing.models import Promocao

        q = request.query_params
        try:
            lat, lng = float(q.get("lat")), float(q.get("lng"))
        except (TypeError, ValueError):
            lat = lng = None
        try:
            raio = min(float(q.get("raio") or 25), 100)
        except ValueError:
            raio = 25
        lojas = (Loja.objects.select_related("empresa")
                 .filter(ativa=True, aparecer_no_app=True, empresa__ativa=True))
        if busca := (q.get("busca") or "").strip():
            lojas = lojas.filter(Q(nome__icontains=busca) | Q(bairro__icontains=busca) | Q(cidade__icontains=busca))
        if (cidade := (q.get("cidade") or "").strip()) and lat is None:
            lojas = lojas.filter(cidade__iexact=cidade)
        agora = timezone.localtime()
        hoje = agora.date()
        com_entrega = set(ZonaEntrega.objects.ativos().filter(ativa=True).values_list("loja_id", flat=True).distinct())
        promos = {}
        for p in Promocao.objects.ativos().filter(ativa=True, loja__in=lojas):
            r = p.regra()
            if (not r.dias or hoje.weekday() in r.dias) and (not r.canais or "ONLINE" in r.canais):
                promos.setdefault(p.loja_id, []).append(p.nome)
        saida, sem_coordenadas, cidades_perto = [], [], set()
        for lj in lojas[:300]:
            if not lj.empresa.liberada:
                continue
            dist = None
            if lat is not None and lj.latitude is not None and lj.longitude is not None:
                dist = round(distancia_km(lat, lng, float(lj.latitude), float(lj.longitude)), 1)
                if dist > raio:
                    continue
                cidades_perto.add((lj.cidade or "").strip().lower())
            elif lat is not None:
                sem_coordenadas.append(lj)  # entra só se for da mesma cidade das lojas próximas
                continue
            saida.append(self._item(request, lj, dist, agora, com_entrega, promos))
        for lj in sem_coordenadas:
            if lj.cidade and lj.cidade.strip().lower() in cidades_perto:
                saida.append(self._item(request, lj, None, agora, com_entrega, promos))
        saida.sort(key=lambda x: (not x["aberta"], x["distancia_km"] if x["distancia_km"] is not None else 9e9,
                                  x["nome"]))
        cidades = sorted({c for c in Loja.objects.filter(ativa=True, aparecer_no_app=True)
                         .exclude(cidade="").values_list("cidade", flat=True)})
        return Response({"lojas": saida[:100], "cidades": cidades})

    @staticmethod
    def _item(request, lj, dist, agora, com_entrega, promos):
        from apfood_core.horarios import aberta_em

        return {
            "nome": lj.nome, "slug": lj.slug, "logo": _url(request, lj.logo), "cor_primaria": lj.cor_primaria,
            "bairro": lj.bairro, "cidade": lj.cidade,
            "aberta": bool(lj.aberta_para_pedidos and aberta_em(lj.horarios, agora)),
            "distancia_km": dist, "tempo_preparo_min": lj.tempo_preparo_min,
            "entrega": lj.id in com_entrega, "pedido_minimo_centavos": lj.pedido_minimo_centavos,
            "promocoes": promos.get(lj.id, [])[:2],
        }
