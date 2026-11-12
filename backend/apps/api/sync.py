"""Sincronização com o PDV desktop.

PULL  GET  /api/sync/pull/?loja=<id>&desde=<iso>[&desde_produtos=<iso>...]
      Cadastros alterados desde o cursor (inclui excluídos: `excluido_em`).
PUSH  POST /api/sync/push/  {"loja": id, "operacoes": [{"id", "operacao", "payload"}]}
      Executa em ordem, cada uma num savepoint. Resposta por operação. O
      `id` da operação é registrado: reenviar devolve o mesmo resultado.
"""

import uuid

from apfood_core.enums import FormaPagamento, StatusPedido, TipoConferencia
from apfood_core.enums import TipoMovimentacaoCaixa as TMC
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.caixa import services as caixa
from apps.caixa.models import TurnoCaixa
from apps.cardapio.models import Adicional, Categoria, GrupoAdicional, Produto, ProdutoVariacao, SetorProducao
from apps.clientes.models import Cliente, EnderecoCliente, Entregador, ZonaEntrega
from apps.core.api import UsuarioLiberado, loja_da_requisicao
from apps.core.excecoes import ErroNegocio
from apps.lojas.models import OperacaoSincronizada
from apps.pedidos import services as pedidos_srv
from apps.pedidos.models import Pedido
from apps.salao import services as salao_srv
from apps.salao.models import Comanda, Mesa

from . import serializers as s
from .views import pedido_in

ENTIDADES = {
    "setores": (SetorProducao, "loja", s.SetorProducaoSerializer),
    "categorias": (Categoria, "loja", s.CategoriaSerializer),
    "produtos": (Produto, "loja", s.ProdutoSerializer),
    "variacoes": (ProdutoVariacao, "produto__loja", s.VariacaoSerializer),
    "grupos_adicionais": (GrupoAdicional, "loja", s.GrupoAdicionalSerializer),
    "adicionais": (Adicional, "grupo__loja", s.AdicionalSerializer),
    "clientes": (Cliente, "loja", s.ClienteSerializer),
    "enderecos": (EnderecoCliente, "cliente__loja", s.EnderecoSerializer),
    "zonas_entrega": (ZonaEntrega, "loja", s.ZonaEntregaSerializer),
    "entregadores": (Entregador, "loja", s.EntregadorSerializer),
    "mesas": (Mesa, "loja", s.MesaSerializer),
}
LIMITE = 2000


class PullView(APIView):
    permission_classes = [UsuarioLiberado]

    def get(self, request):
        loja = loja_da_requisicao(request)
        q = request.query_params
        pedidas = [e for e in q.get("entidades", "").split(",") if e] or list(ENTIDADES)
        resposta = {"servidor_em": timezone.now().isoformat(), "entidades": {}}
        for nome in pedidas:
            if nome not in ENTIDADES:
                raise ValidationError({"entidades": [f"desconhecida: {nome}"]})
            model, campo, ser = ENTIDADES[nome]
            qs = model.objects.filter(**{campo: loja}).order_by("atualizado_em")
            desde = q.get(f"desde_{nome}") or q.get("desde")
            if desde:
                dt = parse_datetime(desde)
                if dt is None:
                    raise ValidationError({"desde": ["data inválida (ISO 8601)"]})
                qs = qs.filter(atualizado_em__gt=dt)
            registros = list(qs[: LIMITE + 1])
            mais = len(registros) > LIMITE
            registros = registros[:LIMITE]
            resposta["entidades"][nome] = {
                "registros": ser(registros, many=True).data,
                "cursor": registros[-1].atualizado_em.isoformat() if registros else desde,
                "mais": mais,
            }
        return Response(resposta)


def _turno(payload, loja):
    return TurnoCaixa.objects.get(pk=payload["turno"], loja=loja)


def _validar(ser_cls, payload):
    ser = ser_cls(data=payload)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


def op_caixa_abrir(loja, u, p):
    d = _validar(s.AbrirTurnoIn, p)
    return s.TurnoOut(caixa.abrir_turno(u, loja, d["valor_abertura_centavos"], id=d.get("id"))).data


def op_caixa_movimento(loja, u, p):
    d = _validar(s.MovimentoIn, p)
    m = caixa.movimentar(_turno(p, loja), TMC(d["tipo"]), d["valor_centavos"], u, motivo=d["motivo"], id=d.get("id"))
    return s.MovimentacaoCaixaOut(m).data


def op_caixa_despesa(loja, u, p):
    d = _validar(s.DespesaCaixaIn, p)
    desp = caixa.pagar_despesa(_turno(p, loja), u, descricao=d["descricao"], valor_centavos=d["valor_centavos"],
                               id=d.get("id"))
    return {"id": str(desp.id)}


def op_caixa_fechar(loja, u, p):
    d = _validar(s.FecharTurnoIn, p)
    turno = _turno(p, loja)
    if turno.status == "FECHADO":
        return {"turno": str(turno.id), "ja_fechado": True}
    r = caixa.fechar_turno(turno, u, d["informado"], tipo_conferencia=TipoConferencia(d["tipo_conferencia"]),
                           observacao=d["observacao"])
    return {"turno": str(turno.id), "situacao": r.situacao, "diferenca_centavos": r.diferenca_centavos}


def op_pedido_criar(loja, u, p):
    d = _validar(s.PedidoIn, p)
    if d["canal"] == "ONLINE":
        raise ErroNegocio("canal ONLINE não é aceito pelo PDV")
    pedido = pedidos_srv.criar_pedido(loja, pedido_in(d, loja), u)
    return {"id": str(pedido.id), "numero": pedido.numero, "token_rastreio": pedido.token_rastreio,
            "total_centavos": pedido.total_centavos}


def op_pedido_status(loja, u, p):
    d = _validar(s.StatusIn, p)
    pedido = Pedido.objects.get(pk=p["pedido"], loja=loja)
    pedido = pedidos_srv.transicionar(pedido, StatusPedido(d["status"]), u, motivo=d["motivo"],
                                      entregador_id=d.get("entregador_id"))
    return {"id": str(pedido.id), "status": pedido.status}


def _pagamento(loja, u, p, **alvo):
    d = _validar(s.PagamentoIn, p)
    pg = pedidos_srv.registrar_pagamento(
        usuario=u, forma=FormaPagamento(d["forma"]), valor_centavos=d["valor_centavos"],
        valor_recebido_centavos=d.get("valor_recebido_centavos"), bandeira=d["bandeira"],
        referencia_externa=d["referencia_externa"], pago_online=d["pago_online"], id=d.get("id"), **alvo,
    )
    return {"id": str(pg.id), "troco_centavos": pg.troco_centavos}


def op_pedido_pagamento(loja, u, p):
    return _pagamento(loja, u, p, pedido=Pedido.objects.get(pk=p["pedido"], loja=loja))


def op_comanda_abrir(loja, u, p):
    d = _validar(s.AbrirComandaIn, p)
    mesa = Mesa.objects.get(pk=d["mesa"], loja=loja) if d.get("mesa") else None
    c = salao_srv.abrir(loja, u, mesa=mesa, numero=d["numero"], nome_cliente=d["nome_cliente"],
                        pessoas=d["pessoas"], id=d.get("id"))
    return {"id": str(c.id)}


def op_comanda_pagamento(loja, u, p):
    return _pagamento(loja, u, p, comanda=Comanda.objects.get(pk=p["comanda"], loja=loja))


def op_comanda_fechar(loja, u, p):
    c = Comanda.objects.get(pk=p["comanda"], loja=loja)
    if c.status == "FECHADA":
        return {"id": str(c.id), "ja_fechada": True}
    return {"id": str(salao_srv.fechar(c, u).id)}


OPERACOES = {
    "caixa.abrir": op_caixa_abrir,
    "caixa.movimento": op_caixa_movimento,
    "caixa.despesa": op_caixa_despesa,
    "caixa.fechar": op_caixa_fechar,
    "pedido.criar": op_pedido_criar,
    "pedido.status": op_pedido_status,
    "pedido.pagamento": op_pedido_pagamento,
    "comanda.abrir": op_comanda_abrir,
    "comanda.pagamento": op_comanda_pagamento,
    "comanda.fechar": op_comanda_fechar,
}


def _erro(exc) -> str:
    if isinstance(exc, ErroNegocio):
        return exc.mensagem
    if isinstance(exc, APIException):
        return str(exc.detail)
    if exc.__class__.__name__ == "DoesNotExist":
        return "registro não encontrado"
    return "erro interno"


class PushView(APIView):
    permission_classes = [UsuarioLiberado]

    def post(self, request):
        loja = loja_da_requisicao(request)
        ops = request.data.get("operacoes")
        if not isinstance(ops, list) or len(ops) > 200:
            raise ValidationError({"operacoes": ["envie uma lista de até 200 operações"]})
        resultados = []
        for op in ops:
            op_id, nome, payload = op.get("id"), op.get("operacao"), op.get("payload") or {}
            try:
                op_id = str(uuid.UUID(str(op_id)))
            except ValueError:
                op_id = None
            if not op_id or nome not in OPERACOES:
                resultados.append({"id": op_id, "ok": False, "erro": "operação inválida"})
                continue
            if registro := OperacaoSincronizada.objects.filter(pk=op_id).first():
                resultados.append({"id": op_id, "ok": registro.ok, **registro.resultado, "repetida": True})
                continue
            try:
                with transaction.atomic():
                    res = {"resultado": OPERACOES[nome](loja, request.user, payload)}
                ok = True
            except Exception as exc:  # noqa: BLE001 — cada operação responde por si
                if not isinstance(exc, (APIException, ErroNegocio)) and exc.__class__.__name__ != "DoesNotExist":
                    import logging

                    logging.getLogger(__name__).exception("sync: falha em %s", nome)
                res, ok = {"erro": _erro(exc)}, False
            OperacaoSincronizada.objects.create(id=op_id, loja=loja, usuario=request.user, operacao=nome,
                                                ok=ok, resultado=res)
            resultados.append({"id": op_id, "ok": ok, **res})
        return Response({"resultados": resultados})
