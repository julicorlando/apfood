"""Endpoints autenticados (PDV desktop e retaguarda).

Convenções:
  • loja ativa: ?loja=<uuid> ou header X-Loja (opcional se o usuário só tem uma);
  • valores em centavos; datas ISO 8601;
  • operações aceitam `id` gerado no cliente (UUID) → reenvio idempotente.
"""

from apfood_core.enums import FormaPagamento, StatusPedido, StatusProducao, TipoConferencia
from apfood_core.enums import TipoMovimentacaoCaixa as TMC
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.caixa import services as caixa
from apps.caixa.models import TurnoCaixa
from apps.cardapio.models import Adicional, Categoria, GrupoAdicional, Produto, ProdutoVariacao, SetorProducao
from apps.clientes import services as clientes_srv
from apps.clientes.models import Cliente, EnderecoCliente, Entregador, ZonaEntrega
from apps.compras import services as compras_srv
from apps.compras.models import Compra, Fornecedor
from apps.core.api import CadastroViewSet, EhGerente, EscopoLojaMixin, UsuarioLiberado, loja_da_requisicao
from apps.core.excecoes import ErroNegocio
from apps.estoque import services as estoque_srv
from apps.estoque.models import MovimentacaoEstoque
from apps.financeiro.models import CategoriaDespesa, Despesa, TaxaFormaPagamento
from apps.marketing.models import Cupom
from apps.pedidos import services as pedidos_srv
from apps.pedidos.models import ItemPedido, Pedido
from apps.realtime import eventos
from apps.salao import services as salao_srv
from apps.salao.models import Comanda, Mesa

from . import serializers as s


# =============================================================================
# Sessão
# =============================================================================
class EuView(APIView):
    permission_classes = [UsuarioLiberado]

    def get(self, request):
        dados = s.UsuarioSerializer(request.user).data
        turno = caixa.turno_aberto(request.user)
        dados["turno_aberto"] = str(turno.id) if turno else None
        return Response(dados)


class PinView(APIView):
    """Troca rápida de operador no PDV: confere o PIN de outro usuário da mesma empresa."""

    permission_classes = [UsuarioLiberado]

    def post(self, request):
        from apps.contas.models import Usuario

        alvo = Usuario.objects.filter(username=request.data.get("username"), is_active=True).first()
        if alvo is None or alvo.empresa_id != request.user.empresa_id or not alvo.conferir_pin(str(request.data.get("pin", ""))):
            raise ErroNegocio("usuário ou PIN inválido")
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken.for_user(alvo)
        return Response({"access": str(token.access_token), "refresh": str(token),
                         "usuario": s.UsuarioSerializer(alvo).data})


# =============================================================================
# Cadastros (todos leem; gerente+ altera)
# =============================================================================
def cadastro_viewset(model_cls, serializer_cls, campo_loja="loja", filtros=(), busca=None, entidade=None):
    class VS(CadastroViewSet):
        queryset = model_cls.objects.all()
        serializer_class = serializer_cls
        filterset_fields = list(filtros)

    VS.campo_loja = campo_loja
    VS.__name__ = f"{model_cls.__name__}ViewSet"

    def perform_create(self, serializer):
        CadastroViewSet.perform_create(self, serializer)
        eventos.catalogo_alterado(self.get_loja().id, entidade or model_cls._meta.model_name)

    def perform_update(self, serializer):
        obj = serializer.save()
        loja_id = getattr(obj, "loja_id", None) or self.get_loja().id
        eventos.catalogo_alterado(loja_id, entidade or model_cls._meta.model_name)

    VS.perform_create, VS.perform_update = perform_create, perform_update
    return VS


SetorViewSet = cadastro_viewset(SetorProducao, s.SetorProducaoSerializer)
CategoriaViewSet = cadastro_viewset(Categoria, s.CategoriaSerializer, filtros=["ativa"])
_ProdutoBase = cadastro_viewset(Produto, s.ProdutoSerializer, filtros=["tipo", "categoria", "ativo", "controla_estoque"])


class ProdutoViewSet(_ProdutoBase):
    @action(detail=True, methods=["get", "put"])
    def grupos(self, request, pk=None):
        """PUT {"grupos": [id, ...]} — grupos de adicionais oferecidos, na ordem."""
        from apps.cardapio.models import ProdutoGrupoAdicional

        produto = self.get_object()
        if request.method == "PUT":
            if not request.user.eh_gerente:
                raise PermissionDenied("requer gerente")
            ids = request.data.get("grupos") or []
            grupos = {str(g.id): g for g in GrupoAdicional.objects.ativos().filter(loja=produto.loja, id__in=ids)}
            if len(grupos) != len(set(map(str, ids))):
                raise ErroNegocio("grupo inexistente ou de outra loja", "grupos")
            ProdutoGrupoAdicional.objects.filter(produto=produto).delete()
            ProdutoGrupoAdicional.objects.bulk_create(
                [ProdutoGrupoAdicional(produto=produto, grupo=grupos[str(g)], ordem=i) for i, g in enumerate(ids)]
            )
            produto.save(update_fields=["atualizado_em"])  # PDV percebe no próximo pull
            eventos.catalogo_alterado(produto.loja_id, "produto")
        return Response(s.ProdutoSerializer(produto).data["grupos_adicionais"])

    @action(detail=True, methods=["get", "put"])
    def ficha(self, request, pk=None):
        """PUT [{"insumo": id, "quantidade": "0.150"}, ...] — ficha técnica completa."""
        from apps.cardapio.models import FichaTecnicaItem

        produto = self.get_object()
        if request.method == "PUT":
            if not request.user.eh_gerente:
                raise PermissionDenied("requer gerente")
            linhas = s.FichaSerializer(data=request.data, many=True)
            linhas.is_valid(raise_exception=True)
            for l in linhas.validated_data:
                if l["insumo"].loja_id != produto.loja_id or l["insumo"].pk == produto.pk:
                    raise ErroNegocio("insumo inválido", "insumo")
            FichaTecnicaItem.objects.filter(produto=produto).delete()
            FichaTecnicaItem.objects.bulk_create([FichaTecnicaItem(produto=produto, **l) for l in linhas.validated_data])
            produto.save(update_fields=["atualizado_em"])
        return Response(s.FichaSerializer(produto.ficha_tecnica.all(), many=True).data)
GrupoAdicionalViewSet = cadastro_viewset(GrupoAdicional, s.GrupoAdicionalSerializer)
ZonaViewSet = cadastro_viewset(ZonaEntrega, s.ZonaEntregaSerializer)
EntregadorViewSet = cadastro_viewset(Entregador, s.EntregadorSerializer, filtros=["ativo"])
MesaViewSet = cadastro_viewset(Mesa, s.MesaSerializer, filtros=["area", "ativa"])
FornecedorViewSet = cadastro_viewset(Fornecedor, s.FornecedorSerializer)
CupomViewSet = cadastro_viewset(Cupom, s.CupomSerializer, filtros=["ativo"])
CategoriaDespesaViewSet = cadastro_viewset(CategoriaDespesa, s.CategoriaDespesaSerializer)
TaxaFormaPagamentoViewSet = cadastro_viewset(TaxaFormaPagamento, s.TaxaFormaPagamentoSerializer)


class _FilhoDeProdutoViewSet(CadastroViewSet):
    """Variações/adicionais: a loja vem do pai; valida que o pai é da loja."""

    pai_campo = ""

    def perform_create(self, serializer):
        pai = serializer.validated_data[self.pai_campo]
        if not self.request.user.lojas_permitidas().filter(pk=pai.loja_id).exists():
            raise PermissionDenied("fora do seu acesso")
        serializer.save()
        eventos.catalogo_alterado(pai.loja_id, self.pai_campo)

    perform_update = perform_create


class VariacaoViewSet(_FilhoDeProdutoViewSet):
    queryset = ProdutoVariacao.objects.all()
    serializer_class = s.VariacaoSerializer
    campo_loja = "produto__loja"
    pai_campo = "produto"
    filterset_fields = ["produto"]


class AdicionalViewSet(_FilhoDeProdutoViewSet):
    queryset = Adicional.objects.all()
    serializer_class = s.AdicionalSerializer
    campo_loja = "grupo__loja"
    pai_campo = "grupo"
    filterset_fields = ["grupo"]


class ClienteViewSet(CadastroViewSet):
    queryset = Cliente.objects.all()
    serializer_class = s.ClienteSerializer

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("enderecos")
        if q := self.request.query_params.get("busca"):
            qs = qs.filter(Q(nome__icontains=q) | Q(telefone__contains="".join(c for c in q if c.isdigit()) or q))
        return qs

    @action(detail=False, methods=["get"], url_path="por-telefone")
    def por_telefone(self, request):
        """Delivery por telefone: devolve o cliente com endereços para autopreencher."""
        achados = clientes_srv.buscar_por_telefone(self.get_loja(), request.query_params.get("telefone", ""))
        return Response(s.ClienteSerializer(achados, many=True).data)

    def perform_create(self, serializer):
        serializer.save(loja=self.get_loja())


class EnderecoViewSet(CadastroViewSet):
    queryset = EnderecoCliente.objects.all()
    serializer_class = s.EnderecoSerializer
    campo_loja = "cliente__loja"
    filterset_fields = ["cliente"]

    def perform_create(self, serializer):
        if not self.request.user.lojas_permitidas().filter(pk=serializer.validated_data["cliente"].loja_id).exists():
            raise PermissionDenied("fora do seu acesso")
        serializer.save()


class DespesaViewSet(CadastroViewSet):
    """Contas a pagar. `?em_aberto=1` lista as não pagas por vencimento."""

    queryset = Despesa.objects.select_related("categoria", "fornecedor")
    serializer_class = s.DespesaSerializer
    permission_classes = [EhGerente]
    filterset_fields = ["categoria", "fornecedor"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("em_aberto"):
            qs = qs.filter(data_pagamento__isnull=True).order_by("data_vencimento")
        return qs

    def perform_create(self, serializer):
        serializer.save(loja=self.get_loja(), usuario=self.request.user)


class TaxaEntregaView(APIView):
    permission_classes = [UsuarioLiberado]

    def post(self, request):
        loja = loja_da_requisicao(request)
        zona, dist = clientes_srv.calcular_taxa_entrega(
            loja, bairro=request.data.get("bairro"), latitude=request.data.get("latitude"),
            longitude=request.data.get("longitude"),
        )
        return Response({"zona": str(zona.id), "nome": zona.nome, "taxa_centavos": zona.taxa_centavos,
                         "tempo_estimado_min": zona.tempo_estimado_min,
                         "distancia_km": round(dist, 2) if dist is not None else None})


# =============================================================================
# Pedidos
# =============================================================================
def pedido_in(dados: dict, loja, request=None) -> pedidos_srv.PedidoIn:
    itens = [
        pedidos_srv.ItemIn(
            produto_id=str(i["produto_id"]), quantidade=i["quantidade"],
            variacao_id=str(i["variacao_id"]) if i.get("variacao_id") else None,
            sabores=[str(x) for x in i.get("sabores", [])],
            adicionais=[pedidos_srv.AdicionalIn(str(a["adicional_id"]), a["quantidade"]) for a in i.get("adicionais", [])],
            observacao=i.get("observacao", ""),
        )
        for i in dados["itens"]
    ]
    comanda = None
    if dados.get("comanda"):
        comanda = get_object_or_404(Comanda, pk=dados["comanda"], loja=loja)
    endereco = dados.get("endereco")
    return pedidos_srv.PedidoIn(
        canal=dados["canal"], tipo_atendimento=dados["tipo_atendimento"], itens=itens,
        id=str(dados["id"]) if dados.get("id") else None, origem_contato=dados.get("origem_contato", ""),
        nome_cliente=dados.get("nome_cliente", ""), telefone_cliente=dados.get("telefone_cliente", ""),
        mesa=dados.get("mesa", ""), senha=dados.get("senha", ""), comanda=comanda,
        endereco=dict(endereco) if endereco else None, taxa_entrega_centavos=dados.get("taxa_entrega_centavos"),
        desconto_centavos=dados.get("desconto_centavos", 0), acrescimo_centavos=dados.get("acrescimo_centavos", 0),
        cupom_codigo=dados.get("cupom_codigo", ""), troco_para_centavos=dados.get("troco_para_centavos"),
        forma_pagamento_prevista=dados.get("forma_pagamento_prevista", ""), observacao=dados.get("observacao", ""),
        cpf_nota=dados.get("cpf_nota", ""),
        entregador_id=str(dados["entregador_id"]) if dados.get("entregador_id") else None,
        marketplace=dados.get("marketplace", ""), id_externo=dados.get("id_externo", ""),
        codigo_externo=dados.get("codigo_externo", ""), codigo_local=dados.get("codigo_local", ""),
    )


class PedidoViewSet(EscopoLojaMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Fila do PDV: `?status=PENDENTE&status=EM_PREPARO`, `?canal=ONLINE`, `?data=2026-11-12`,
    `?abertos=1` (não finalizados)."""

    queryset = Pedido.objects.prefetch_related("itens__adicionais", "itens__sabores", "pagamentos", "historico")
    serializer_class = s.PedidoOut
    permission_classes = [UsuarioLiberado]
    filterset_fields = ["canal", "tipo_atendimento", "comanda", "data_referencia", "entregador"]

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if st := p.getlist("status"):
            qs = qs.filter(status__in=st)
        if p.get("abertos"):
            qs = qs.exclude(status__in=["CONCLUIDO", "CANCELADO", "RECUSADO"])
        if d := p.get("data"):
            qs = qs.filter(data_referencia=d)
        return qs

    def create(self, request):
        loja = loja_da_requisicao(request)
        entrada = s.PedidoIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        if entrada.validated_data["canal"] == "ONLINE":
            raise ErroNegocio("pedidos online entram pelo cardápio público")
        pedido = pedidos_srv.criar_pedido(loja, pedido_in(entrada.validated_data, loja), request.user)
        return Response(s.PedidoOut(pedido).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        entrada = s.StatusIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        p = pedidos_srv.transicionar(self.get_object(), StatusPedido(d["status"]), request.user,
                                     motivo=d["motivo"], entregador_id=d.get("entregador_id"))
        return Response(s.PedidoOut(p).data)

    @action(detail=True, methods=["post"])
    def pagamentos(self, request, pk=None):
        entrada = s.PagamentoIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        pg = pedidos_srv.registrar_pagamento(
            usuario=request.user, pedido=self.get_object(), forma=FormaPagamento(d["forma"]),
            valor_centavos=d["valor_centavos"], valor_recebido_centavos=d.get("valor_recebido_centavos"),
            bandeira=d["bandeira"], referencia_externa=d["referencia_externa"], pago_online=d["pago_online"],
            id=d.get("id"),
        )
        return Response(s.PagamentoOut(pg).data, status=status.HTTP_201_CREATED)


class CozinhaViewSet(EscopoLojaMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Tela da cozinha (KDS): itens por setor. `?setor=<uuid>`."""

    queryset = ItemPedido.objects.select_related("pedido", "setor").prefetch_related("adicionais", "sabores")
    serializer_class = s.ItemOut
    permission_classes = [UsuarioLiberado]
    campo_loja = "pedido__loja"

    def get_queryset(self):
        qs = super().get_queryset().filter(
            status_producao__in=[StatusProducao.AGUARDANDO, StatusProducao.EM_PREPARO],
            pedido__status__in=["RECEBIDO", "EM_PREPARO"],
        ).order_by("criado_em")
        if setor := self.request.query_params.get("setor"):
            qs = qs.filter(setor_id=setor)
        return qs

    def list(self, request, *args, **kwargs):
        itens = self.get_queryset()[:300]
        return Response([
            {**s.ItemOut(i).data, "pedido": {"id": str(i.pedido_id), "numero": i.pedido.numero,
                                             "mesa": i.pedido.mesa, "nome_cliente": i.pedido.nome_cliente,
                                             "tipo_atendimento": i.pedido.tipo_atendimento}}
            for i in itens
        ])

    @action(detail=True, methods=["post"])
    def avancar(self, request, pk=None):
        """AGUARDANDO → EM_PREPARO → PRONTO. Quando todos os itens ficam prontos,
        o pedido vai para PRONTO."""
        item = get_object_or_404(ItemPedido.objects.filter(pedido__loja__in=request.user.lojas_permitidas()), pk=pk)
        agora = timezone.now()
        if item.status_producao == StatusProducao.AGUARDANDO:
            item.status_producao, item.producao_iniciada_em = StatusProducao.EM_PREPARO, agora
            if item.pedido.status == StatusPedido.RECEBIDO:
                pedidos_srv.transicionar(item.pedido, StatusPedido.EM_PREPARO, request.user)
        elif item.status_producao == StatusProducao.EM_PREPARO:
            item.status_producao, item.pronto_em = StatusProducao.PRONTO, agora
        item.save()
        pedido = Pedido.objects.get(pk=item.pedido_id)
        if not pedido.itens.exclude(status_producao__in=[StatusProducao.PRONTO, StatusProducao.ENTREGUE]).exists():
            if pedido.status in (StatusPedido.RECEBIDO, StatusPedido.EM_PREPARO):
                pedidos_srv.transicionar(pedido, StatusPedido.PRONTO, request.user)
        return Response(s.ItemOut(item).data)


# =============================================================================
# Caixa
# =============================================================================
class TurnoViewSet(EscopoLojaMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Operador vê os próprios turnos; gerente+ vê todos da loja."""

    queryset = TurnoCaixa.objects.select_related("usuario")
    serializer_class = s.TurnoOut
    permission_classes = [UsuarioLiberado]
    filterset_fields = ["status", "usuario"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs if self.request.user.eh_gerente else qs.filter(usuario=self.request.user)

    @action(detail=False, methods=["post"])
    def abrir(self, request):
        entrada = s.AbrirTurnoIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        t = caixa.abrir_turno(request.user, loja_da_requisicao(request), entrada.validated_data["valor_abertura_centavos"],
                              id=entrada.validated_data.get("id"))
        return Response(s.TurnoOut(t).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def atual(self, request):
        t = caixa.turno_aberto(request.user)
        if t is None:
            return Response({"detail": "nenhum caixa aberto"}, status=status.HTTP_404_NOT_FOUND)
        return Response({**s.TurnoOut(t).data, "resumo": self._resumo(t, request)})

    def _resumo(self, t, request):
        # Conferência cega: operador não vê o esperado; gerente vê.
        return caixa.resumo(t, mostrar_esperado=request.user.eh_gerente or t.status == "FECHADO")

    @action(detail=True, methods=["get"])
    def resumo(self, request, pk=None):
        return Response(self._resumo(self.get_object(), request))

    @action(detail=True, methods=["post"])
    def movimentos(self, request, pk=None):
        entrada = s.MovimentoIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        m = caixa.movimentar(self.get_object(), TMC(d["tipo"]), d["valor_centavos"], request.user,
                             motivo=d["motivo"], id=d.get("id"))
        return Response(s.MovimentacaoCaixaOut(m).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def despesas(self, request, pk=None):
        entrada = s.DespesaCaixaIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        turno = self.get_object()
        categoria = CategoriaDespesa.objects.filter(pk=d.get("categoria"), loja=turno.loja).first() if d.get("categoria") else None
        desp = caixa.pagar_despesa(turno, request.user, descricao=d["descricao"], valor_centavos=d["valor_centavos"],
                                   categoria=categoria, id=d.get("id"))
        return Response(s.DespesaSerializer(desp).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def fechar(self, request, pk=None):
        entrada = s.FecharTurnoIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        turno = self.get_object()
        r = caixa.fechar_turno(turno, request.user, d["informado"],
                               tipo_conferencia=TipoConferencia(d["tipo_conferencia"]), observacao=d["observacao"])
        turno.refresh_from_db()
        return Response({
            **s.TurnoOut(turno).data, "situacao": r.situacao,
            "conferencia": s.ConferenciaOut(turno.conferencias.all(), many=True).data,
        })


# =============================================================================
# Salão
# =============================================================================
class ComandaViewSet(EscopoLojaMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Comanda.objects.select_related("mesa").prefetch_related("pagamentos")
    serializer_class = s.ComandaOut
    permission_classes = [UsuarioLiberado]
    filterset_fields = ["status", "mesa"]

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(status__in=["ABERTA", "FECHANDO"]) if self.request.query_params.get("abertas") else qs

    def create(self, request):
        entrada = s.AbrirComandaIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        loja = loja_da_requisicao(request)
        mesa = get_object_or_404(Mesa, pk=d["mesa"], loja=loja) if d.get("mesa") else None
        c = salao_srv.abrir(loja, request.user, mesa=mesa, numero=d["numero"], nome_cliente=d["nome_cliente"],
                            pessoas=d["pessoas"], id=d.get("id"))
        return Response(s.ComandaOut(c).data, status=status.HTTP_201_CREATED)

    def _ok(self, c):
        c.refresh_from_db()
        return Response(s.ComandaOut(c).data)

    @action(detail=True, methods=["get"])
    def pedidos(self, request, pk=None):
        return Response(s.PedidoOut(self.get_object().pedidos.all(), many=True).data)

    @action(detail=True, methods=["post"], url_path="pedir-conta")
    def pedir_conta(self, request, pk=None):
        return self._ok(salao_srv.pedir_conta(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def reabrir(self, request, pk=None):
        return self._ok(salao_srv.reabrir(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def ajustar(self, request, pk=None):
        d = request.data
        return self._ok(salao_srv.ajustar(
            self.get_object(), request.user, cobrar_taxa_servico=d.get("cobrar_taxa_servico"),
            desconto_centavos=d.get("desconto_centavos"), couvert_centavos=d.get("couvert_centavos"),
        ))

    @action(detail=True, methods=["get"])
    def divisao(self, request, pk=None):
        pessoas = int(request.query_params.get("pessoas") or 0) or None
        return Response({"partes_centavos": salao_srv.divisao_sugerida(self.get_object(), pessoas)})

    @action(detail=True, methods=["post"])
    def pagamentos(self, request, pk=None):
        entrada = s.PagamentoIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        pg = pedidos_srv.registrar_pagamento(
            usuario=request.user, comanda=self.get_object(), forma=FormaPagamento(d["forma"]),
            valor_centavos=d["valor_centavos"], valor_recebido_centavos=d.get("valor_recebido_centavos"),
            bandeira=d["bandeira"], referencia_externa=d["referencia_externa"], id=d.get("id"),
        )
        return Response(s.PagamentoOut(pg).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def fechar(self, request, pk=None):
        return self._ok(salao_srv.fechar(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def transferir(self, request, pk=None):
        c = self.get_object()
        mesa = get_object_or_404(Mesa, pk=request.data.get("mesa"), loja=c.loja)
        return self._ok(salao_srv.transferir(c, mesa, request.user))

    @action(detail=True, methods=["post"])
    def juntar(self, request, pk=None):
        destino = self.get_object()
        origem = get_object_or_404(self.get_queryset(), pk=request.data.get("origem"))
        return self._ok(salao_srv.juntar(origem, destino, request.user))


# =============================================================================
# Estoque e compras
# =============================================================================
class EstoqueViewSet(EscopoLojaMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Kardex (`?produto=`) e operações manuais (entrada, perda, inventário)."""

    queryset = MovimentacaoEstoque.objects.select_related("produto")
    serializer_class = s.MovimentacaoEstoqueOut
    permission_classes = [EhGerente]
    filterset_fields = ["produto", "tipo", "pedido"]

    @action(detail=False, methods=["get"], url_path="abaixo-do-minimo")
    def abaixo_do_minimo(self, request):
        from django.db.models import F

        qs = Produto.objects.ativos().filter(
            loja=loja_da_requisicao(request), controla_estoque=True, estoque_minimo__isnull=False,
            estoque_atual__lte=F("estoque_minimo"),
        )
        return Response([{"id": str(p.id), "nome": p.nome, "unidade": p.unidade, "estoque_atual": p.estoque_atual,
                          "estoque_minimo": p.estoque_minimo} for p in qs])

    @action(detail=False, methods=["post"])
    def operacao(self, request):
        entrada = s.EstoqueIn(data=request.data)
        entrada.is_valid(raise_exception=True)
        d = entrada.validated_data
        produto = get_object_or_404(Produto, pk=d["produto"], loja=loja_da_requisicao(request))
        if d["operacao"] == "ENTRADA":
            mov = estoque_srv.registrar_entrada(produto, d["quantidade"], d.get("custo_unitario_centavos"),
                                                usuario=request.user, motivo=d["motivo"])
        elif d["operacao"] == "PERDA":
            mov = estoque_srv.registrar_perda(produto, d["quantidade"], usuario=request.user, motivo=d["motivo"])
        else:
            mov = estoque_srv.ajustar_inventario(produto, d["quantidade"], usuario=request.user,
                                                 motivo=d["motivo"] or "inventário")
        return Response(s.MovimentacaoEstoqueOut(mov).data if mov else {"detail": "saldo já confere"},
                        status=status.HTTP_201_CREATED if mov else status.HTTP_200_OK)


class CompraViewSet(EscopoLojaMixin, viewsets.ModelViewSet):
    queryset = Compra.objects.select_related("fornecedor").prefetch_related("itens")
    serializer_class = s.CompraSerializer
    permission_classes = [EhGerente]
    filterset_fields = ["status", "fornecedor"]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    @action(detail=True, methods=["post"])
    def lancar(self, request, pk=None):
        c = compras_srv.lancar(self.get_object(), request.user)
        return Response(s.CompraSerializer(c).data)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        motivo = request.data.get("motivo") or ""
        if not motivo:
            raise ErroNegocio("informe o motivo", "motivo")
        return Response(s.CompraSerializer(compras_srv.cancelar(self.get_object(), request.user, motivo)).data)


# =============================================================================
# Documento da venda, cupons e Pix
# =============================================================================
from apps.fiscal import services as fiscal_srv  # noqa: E402
from apps.fiscal.models import NotaFiscal  # noqa: E402


def _largura(request) -> int:
    return 32 if str(request.query_params.get("largura") or request.data.get("largura") or "") == "32" else 48


def _pix_out(pg):
    return {"pagamento": str(pg.id), "valor_centavos": pg.valor_centavos, "status": pg.status,
            "referencia_externa": pg.referencia_externa, **pg.dados_externos}


class DocumentosPedidoMixin:
    @action(detail=True, methods=["post"])
    def documento(self, request, pk=None):
        """Finalizou a venda: NFC-e se houver emissor; senão, cupom não fiscal."""
        return Response(fiscal_srv.documento_da_venda(self.get_object(), cpf=request.data.get("cpf", ""),
                                                      largura=_largura(request)))

    @action(detail=True, methods=["get"])
    def cupom(self, request, pk=None):
        """?tipo=venda (comprovante não fiscal) | cozinha (uma via por setor)."""
        pedido = self.get_object()
        if request.query_params.get("tipo") == "cozinha":
            return Response({"vias": fiscal_srv.cupons_cozinha(pedido, _largura(request))})
        return Response({"linhas": fiscal_srv.linhas_para_json(fiscal_srv.cupom_venda(pedido, _largura(request)))})

    @action(detail=True, methods=["post"])
    def pix(self, request, pk=None):
        pg = pedidos_srv.cobrar_pix(pedido=self.get_object(), valor_centavos=request.data.get("valor_centavos"))
        return Response(_pix_out(pg), status=status.HTTP_201_CREATED)


PedidoViewSet.documento = DocumentosPedidoMixin.documento
PedidoViewSet.cupom = DocumentosPedidoMixin.cupom
PedidoViewSet.pix = DocumentosPedidoMixin.pix


def _anexar(viewset, nome, metodos, fn):
    """Anexa uma action a um ViewSet já definido (DRF exige __name__ == atributo)."""
    fn.__name__ = nome
    setattr(viewset, nome, action(detail=True, methods=metodos)(fn))


def _cupom_comanda(self, request, pk=None):
    return Response({"linhas": fiscal_srv.linhas_para_json(fiscal_srv.cupom_comanda(self.get_object(), _largura(request)))})


def _pix_comanda(self, request, pk=None):
    pg = pedidos_srv.cobrar_pix(comanda=self.get_object(), valor_centavos=request.data.get("valor_centavos"))
    return Response(_pix_out(pg), status=status.HTTP_201_CREATED)


def _cupom_turno(self, request, pk=None):
    turno = self.get_object()
    if turno.status != "FECHADO" and not request.user.eh_gerente:
        raise PermissionDenied("o relatório do caixa sai após o fechamento")
    return Response({"linhas": fiscal_srv.linhas_para_json(fiscal_srv.cupom_fechamento(turno, _largura(request)))})


_anexar(ComandaViewSet, "cupom", ["get"], _cupom_comanda)
_anexar(ComandaViewSet, "pix", ["post"], _pix_comanda)
_anexar(TurnoViewSet, "cupom", ["get"], _cupom_turno)


class NotaFiscalSerializer(s.serializers.ModelSerializer):
    class Meta:
        model = NotaFiscal
        fields = "__all__"


class NotaFiscalViewSet(EscopoLojaMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = NotaFiscal.objects.all()
    serializer_class = NotaFiscalSerializer
    permission_classes = [EhGerente]
    filterset_fields = ["status", "modelo", "pedido"]

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        nota = fiscal_srv.cancelar_nota(self.get_object(), request.data.get("justificativa", ""))
        return Response(NotaFiscalSerializer(nota).data)

    @action(detail=True, methods=["post"])
    def reemitir(self, request, pk=None):
        nota = self.get_object()
        if nota.status != "REJEITADA" or not nota.pedido_id:
            raise ErroNegocio("só notas rejeitadas podem ser reemitidas")
        return Response(NotaFiscalSerializer(fiscal_srv.emitir_nfce(nota.pedido, cpf=nota.cpf_cnpj_consumidor)).data)
