"""API pública do cardápio digital (sem login). Escopo pela `slug` da loja."""

from datetime import timedelta

from django.conf import settings
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


def _whatsapp_ativo(loja) -> bool:
    from apps.integracoes.models import Integracao

    return Integracao.ativa(loja, "WHATSAPP", "whatsapp") is not None


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
        "agendamento": _agendamento(loja),
        "reservas": loja.aceita_reservas,
        # bairros com taxa cadastrada: sugestões no campo Bairro (o cliente ainda pode digitar outro)
        "recuperar_carrinho": bool(loja.carrinho_ativo and _whatsapp_ativo(loja)),
        "bairros": sorted({z.nome.strip() for z in ZonaEntrega.objects.ativos().filter(loja=loja, ativa=True, tipo="BAIRRO")}),
        "fidelidade": {"selos": loja.fidelidade_selos, "premio": loja.fidelidade_premio_descricao
                       or (f"R$ {loja.fidelidade_premio_centavos / 100:.2f} de crédito".replace(".", ",")
                           if loja.fidelidade_premio_centavos else "")} if loja.fidelidade_selos else None,
    }


def _agendamento(loja):
    from apps.pedidos import agendados

    dias = agendados.horarios_disponiveis(loja)
    return {"dias": dias} if dias else None


def dados_cardapio(loja, request) -> dict:
    from apps.api.views import promocoes_agora
    from apps.marketing.models import Promocao

    agora = timezone.now()
    promo_online = promocoes_agora(loja, canais=("ONLINE",))["ONLINE"]
    categorias = []
    componentes = {}
    from apps.cardapio.models import ComboItem

    for ci in ComboItem.objects.filter(combo__loja=loja).select_related("produto").order_by("ordem", "id"):
        componentes.setdefault(ci.combo_id, []).append(ci)
    for c in Categoria.objects.ativos().filter(loja=loja, ativa=True).order_by("ordem", "nome"):
        disponivel = c.disponivel_em(agora)
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
                "combo": _combo(componentes.get(p.id), p.preco_centavos),
            })
        if produtos:
            categorias.append({"id": str(c.id), "nome": c.nome, "descricao": c.descricao,
                               "disponivel": disponivel, "horario": c.texto_horario(agora),
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


def _combo(itens, preco) -> dict | None:
    """Combo: o que vem nele e quanto o cliente economiza em relação aos itens separados."""
    if not itens:
        return None
    de = sum(ci.produto.preco_centavos * ci.quantidade for ci in itens)
    return {"itens": [f"{ci.quantidade}x {ci.produto.nome}" for ci in itens],
            "produtos": [str(ci.produto_id) for ci in itens],
            "de_centavos": de, "economia_centavos": max(0, de - preco)}


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


def conferir_horarios(loja, itens, quando) -> None:
    """Cardápio por horário: produto de categoria fora do horário não entra no pedido online."""
    from apps.cardapio.models import Produto
    from apps.core.excecoes import ErroNegocio

    ids = [str(i.get("produto_id")) for i in itens if i.get("produto_id")]
    for p in Produto.objects.filter(loja=loja, pk__in=ids).select_related("categoria"):
        c = p.categoria
        if c is not None and not c.disponivel_em(quando):
            raise ErroNegocio(f"{p.nome}: {c.texto_horario(quando).lower() or 'fora do horário'}. Tire do carrinho para continuar.")


class CarrinhoAbertoView(Publica):
    """O cardápio avisa o carrinho de quem já informou o telefone; se não finalizar em
    `carrinho_minutos`, a loja manda um lembrete pelo WhatsApp (uma vez por dia)."""

    throttle_scope = "publico"

    def post(self, request, slug):
        from apps.marketing import carrinho

        loja = loja_publica(slug)
        carrinho.registrar(loja, telefone=str(request.data.get("telefone") or ""), nome=str(request.data.get("nome") or ""),
                           itens=request.data.get("itens") or [], total=request.data.get("total_centavos") or 0)
        return Response({"ok": True})


class PedidoPublicoView(Publica):
    throttle_scope = "publico_pedido"

    def post(self, request, slug):
        loja = loja_publica(slug)
        entrada = s.PedidoOnlineIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        conferir_horarios(loja, entrada.validated_data.get("itens") or [],
                          entrada.validated_data.get("agendado_para") or timezone.now())
        pedido = pedidos_srv.criar_pedido(loja, pedido_in(entrada.validated_data, loja))
        if pedido.telefone_cliente:  # finalizou: não manda lembrete de carrinho abandonado
            from apps.marketing.models import CarrinhoAberto

            CarrinhoAberto.objects.filter(loja=loja, telefone=pedido.telefone_cliente, convertido_em__isnull=True) \
                .update(convertido_em=timezone.now())
        resposta = {
            "token": pedido.token_rastreio, "numero": pedido.numero, "status": pedido.status,
            "total_centavos": pedido.total_centavos, "acompanhar": f"/pedido/{pedido.token_rastreio}/",
        }
        if entrada.validated_data.get("forma_pagamento_prevista") == "PIX" and request.data.get("pagar_pix_agora"):
            from apps.integracoes.models import Integracao

            if Integracao.ativa(loja, "PAGAMENTO", "mercadopago"):
                pg = pedidos_srv.cobrar_pix(pedido=pedido)
                resposta["pix"] = {"valor_centavos": pg.valor_centavos, **pg.dados_externos}
        if request.data.get("pagar_cartao_agora"):
            pg = pedidos_srv.cobrar_cartao(pedido=pedido)
            resposta["cartao_url"] = pg.dados_externos.get("checkout_url", "")
        return Response(resposta, status=status.HTTP_201_CREATED)


def rastreio_entrega(p) -> dict | None:
    """Onde está o entregador (só enquanto o pedido está "saiu para entrega" e a
    posição tem menos de 10 minutos)."""
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
                 distancia_km=round(km, 1), minutos=_minutos_trajeto(km))
    return r


VELOCIDADE_KMH = 20  # moto/carro na cidade
FATOR_RUA = 1.3      # distância em linha reta → pelas ruas
SEM_COORDENADAS_MIN = 20


def _minutos_trajeto(km: float) -> int:
    return max(3, round(km * FATOR_RUA / VELOCIDADE_KMH * 60) + 2)


def previsao(p) -> dict | None:
    """Quando o pedido chega (entrega) ou fica pronto (retirada/balcão): "chega em ~12 min".
    Saiu para entrega: pela posição do entregador; antes disso: preparo da loja + trajeto loja → cliente."""
    from apfood_core.entrega import distancia_km

    if p.status in ("CONCLUIDO", "CANCELADO", "RECUSADO") or (p.agendado_para and p.status == "PENDENTE"):
        return None
    agora = timezone.now()
    entrega = p.tipo_atendimento == "ENTREGA"
    tem_destino = p.entrega_latitude is not None and p.entrega_longitude is not None
    base = "estimativa"
    if p.status == "SAIU_PARA_ENTREGA":
        r = rastreio_entrega(p)
        if r and r.get("distancia_km") is not None:
            minutos, base = _minutos_trajeto(r["distancia_km"]), "entregador"
        else:
            l = p.loja
            km = (distancia_km(float(l.latitude), float(l.longitude), float(p.entrega_latitude), float(p.entrega_longitude))
                  if tem_destino and l.latitude is not None and l.longitude is not None else None)
            total = _minutos_trajeto(km) if km is not None else SEM_COORDENADAS_MIN
            andou = (agora - p.saiu_entrega_em).total_seconds() / 60 if p.saiu_entrega_em else 0
            minutos = max(2, round(total - andou))
    else:
        inicio = p.agendado_para if p.agendado_para and p.agendado_para > agora else (p.aceito_em or p.criado_em)
        pronto_em = inicio + timedelta(minutes=p.loja.tempo_preparo_min or 30)
        if p.status == "PRONTO":
            pronto_em = agora
        trajeto = 0
        if entrega:
            l = p.loja
            km = (distancia_km(float(l.latitude), float(l.longitude), float(p.entrega_latitude), float(p.entrega_longitude))
                  if tem_destino and l.latitude is not None and l.longitude is not None else None)
            trajeto = _minutos_trajeto(km) if km is not None else SEM_COORDENADAS_MIN
        chega = max(pronto_em, agora) + timedelta(minutes=trajeto)
        minutos = max(1, round((chega - agora).total_seconds() / 60))
    quando = agora + timedelta(minutes=minutos)
    return {"minutos": minutos, "ate": timezone.localtime(quando).strftime("%H:%M"), "base": base,
            "tipo": "chegada" if entrega else "pronto"}


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
            "previsao": previsao(p),
            "foto_entrega": request.build_absolute_uri(p.foto_entrega.url) if p.foto_entrega else None,
            "repetir": _repetir(p) if p.status in ("CONCLUIDO", "SAIU_PARA_ENTREGA", "PRONTO") else None,
            "pix": next(({"valor_centavos": x.valor_centavos, **x.dados_externos}
                         for x in p.pagamentos.filter(status="PENDENTE", forma="PIX") if x.dados_externos), None),
            # o cliente informa ao entregador na porta (o app do entregador pede para concluir)
            "codigo_entrega": p.codigo_entrega if p.tipo_atendimento == "ENTREGA" and p.entregador_id
            and p.status in ("RECEBIDO", "EM_PREPARO", "PRONTO", "SAIU_PARA_ENTREGA") else None,
            "entregador": p.entregador.nome.split()[0] if p.entregador_id and p.entregador.nome else None,
            "avaliacao": _avaliacao(p),
            "cartao_url": next((x.dados_externos.get("checkout_url") for x in p.pagamentos.filter(status="PENDENTE")
                                if (x.dados_externos or {}).get("checkout_url")), None),
            "agendado_para": p.agendado_para,
            "indicacao": _indicacao(p),
            "pode_avaliar": p.status == "CONCLUIDO" and _avaliacao(p) is None,
        })

    def post(self, request, token):
        """Avaliação opcional depois de receber: {"nota": 1-5, "comentario": ""}."""
        from apps.pedidos.models import Avaliacao

        p = get_object_or_404(Pedido.objects.select_related("loja"), token_rastreio=token)
        if p.status != "CONCLUIDO":
            return Response({"detail": "Dá para avaliar depois de receber o pedido."}, status=400)
        try:
            nota = int(request.data.get("nota"))
        except (TypeError, ValueError):
            nota = 0
        if not 1 <= nota <= 5:
            return Response({"detail": "Escolha de 1 a 5 estrelas."}, status=400)
        comentario = str(request.data.get("comentario") or "").strip()[:500]
        a, criada = Avaliacao.objects.get_or_create(pedido=p, defaults={"loja": p.loja, "nota": nota,
                                                                         "comentario": comentario})
        if not criada:
            return Response({"detail": "Este pedido já foi avaliado. Obrigado!"}, status=400)
        from apps.realtime.eventos import grupo_pdv, publicar

        publicar(grupo_pdv(p.loja_id), "pedido.avaliado", {"numero": p.numero, "nota": nota})
        return Response({"nota": a.nota, "comentario": a.comentario}, status=201)


def _repetir(p) -> list[dict]:
    """Itens do pedido no formato do carrinho do cardápio ("Peça de novo"): preços e disponibilidade
    são conferidos de novo pelo cardápio na hora."""
    itens = []
    for i in p.itens.prefetch_related("adicionais", "sabores"):
        if not i.produto_id:
            continue
        itens.append({"produto_id": str(i.produto_id), "quantidade": i.quantidade,
                      "variacao_id": str(i.variacao_id) if i.variacao_id else None,
                      "sabores": [str(x.produto_id) for x in i.sabores.all() if x.produto_id],
                      "adicionais": [{"adicional_id": str(a.adicional_id), "quantidade": a.quantidade}
                                     for a in i.adicionais.all() if a.adicional_id],
                      "observacao": i.observacao})
    return itens


def _indicacao(p):
    if not (p.cliente_id and p.loja.indicacao_ativa and p.status == "CONCLUIDO"):
        return None
    from apps.marketing.reconquista import codigo_indicacao

    return {"codigo": codigo_indicacao(p.cliente), "desconto_centavos": p.loja.indicacao_desconto_centavos,
            "premio_centavos": p.loja.indicacao_premio_centavos,
            "link": settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/{p.loja.slug}/"}


def _avaliacao(p):
    from apps.pedidos.models import Avaliacao

    try:
        a = p.avaliacao
    except Avaliacao.DoesNotExist:
        return None
    return {"nota": a.nota, "comentario": a.comentario}


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


class ReservaPublicaView(Publica):
    """POST /api/publico/lojas/<slug>/reservas/ {nome, telefone, pessoas, data_hora, observacao}"""

    throttle_scope = "publico_pedido"

    def post(self, request, slug):
        from django.utils.dateparse import parse_datetime

        from apps.salao import reservas

        loja = loja_publica(slug)
        quando = parse_datetime(str(request.data.get("data_hora", "")))
        if quando is None:
            return Response({"data_hora": ["escolha dia e horário"]}, status=400)
        try:
            pessoas = int(request.data.get("pessoas") or 0)
        except (TypeError, ValueError):
            pessoas = 0
        r = reservas.criar_publica(loja, nome=str(request.data.get("nome", "")), telefone=str(request.data.get("telefone", "")),
                                   pessoas=pessoas, data_hora=quando, observacao=str(request.data.get("observacao", "")))
        return Response({"id": str(r.id), "status": r.status,
                         "quando": timezone.localtime(r.data_hora).strftime("%d/%m às %H:%M")}, status=201)


class TotemPedidoView(Publica):
    """POST /api/publico/lojas/<slug>/totem/<token>/pedidos/
    {tipo_atendimento: CONSUMO_LOCAL|RETIRADA, nome_cliente, observacao, itens, pagar_pix}
    Pedido de balcão feito no totem: recebe a senha (ex.: 0124) e paga no caixa ou no Pix."""

    throttle_scope = "publico_pedido"

    def post(self, request, slug, token):
        import secrets

        from apfood_core.enums import CanalVenda, TipoAtendimento

        loja = loja_publica(slug)
        if not loja.token_totem or not secrets.compare_digest(loja.token_totem, token):
            return Response({"detail": "Totem desativado. Chame um atendente."}, status=404)
        tipo = request.data.get("tipo_atendimento")
        if tipo not in ("CONSUMO_LOCAL", "RETIRADA"):
            return Response({"detail": "Escolha comer aqui ou para levar."}, status=400)
        from .views import pedido_in

        if not (loja.ativa and loja.empresa.liberada):
            return Response({"detail": "Totem indisponível. Chame um atendente."}, status=400)
        entrada = s.ItemIn(many=True, data=request.data.get("itens") or [])
        entrada.is_valid(raise_exception=True)
        if not entrada.validated_data:
            return Response({"detail": "Escolha pelo menos um item."}, status=400)
        dados = {"canal": CanalVenda.BALCAO, "tipo_atendimento": TipoAtendimento(tipo), "itens": entrada.validated_data,
                 "nome_cliente": str(request.data.get("nome_cliente") or "")[:120],
                 "observacao": ("[Totem] " + str(request.data.get("observacao") or "")).strip()[:500],
                 "forma_pagamento_prevista": "PIX" if request.data.get("pagar_pix") else ""}
        pedido = pedidos_srv.criar_pedido(loja, pedido_in(dados, loja))
        resposta = {"numero": pedido.numero, "senha": pedido.senha or f"{pedido.numero:04d}",
                    "total_centavos": pedido.total_centavos, "token": pedido.token_rastreio}
        if request.data.get("pagar_pix"):
            from apps.integracoes.models import Integracao

            if Integracao.ativa(loja, "PAGAMENTO", "mercadopago"):
                pg = pedidos_srv.cobrar_pix(pedido=pedido)
                resposta["pix"] = {"valor_centavos": pg.valor_centavos, **pg.dados_externos}
        return Response(resposta, status=status.HTTP_201_CREATED)
