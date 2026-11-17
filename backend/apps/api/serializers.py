"""Serializers da API. Entradas de operação (pedido, pagamento, caixa) são
serializers "de comando" que alimentam os services — nunca gravam direto."""

from apfood_core.enums import (
    CanalVenda, FormaPagamento, OrigemContato, StatusPedido, TipoAtendimento, TipoConferencia,
)
from rest_framework import serializers

from apps.caixa.models import ConferenciaCaixa, MovimentacaoCaixa, TurnoCaixa
from apps.cardapio.models import (
    Adicional, Categoria, FichaTecnicaItem, GrupoAdicional, Produto, ProdutoGrupoAdicional, ProdutoVariacao,
    SetorProducao,
)
from apps.clientes.models import Cliente, EnderecoCliente, Entregador, ZonaEntrega
from apps.compras.models import Compra, Fornecedor, ItemCompra
from apps.contas.models import Usuario
from apps.estoque.models import MovimentacaoEstoque
from apps.financeiro.models import CategoriaDespesa, Despesa, TaxaFormaPagamento
from apps.lojas.models import Loja
from apps.marketing.models import Cupom, Promocao
from apps.pedidos.models import HistoricoStatusPedido, ItemPedido, ItemPedidoAdicional, ItemPedidoSabor, Pagamento, Pedido
from apps.salao.models import Comanda, Mesa


class BaseLoja(serializers.ModelSerializer):
    """Cadastro de loja: `loja` é sempre definida pela view (escopo), e toda
    chave estrangeira informada precisa ser da MESMA loja."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        view = self.context.get("view")
        if self.instance is not None and getattr(self.instance, "loja_id", None):
            loja_id = self.instance.loja_id
        elif view is not None and hasattr(view, "get_loja"):
            loja_id = view.get_loja().id
        else:
            return attrs
        for nome, valor in attrs.items():
            if getattr(valor, "loja_id", loja_id) != loja_id:
                raise serializers.ValidationError({nome: ["pertence a outra loja"]})
        return attrs

    class Meta:
        exclude = ["loja"]
        read_only_fields = ["id", "criado_em", "atualizado_em", "excluido_em"]


def cadastro(model_cls, **extra_meta):
    meta = type("Meta", (BaseLoja.Meta,), {"model": model_cls, **extra_meta})
    return type(f"{model_cls.__name__}Serializer", (BaseLoja,), {"Meta": meta})


# --- contas / lojas ---------------------------------------------------------
class LojaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loja
        exclude = ["empresa"]


class UsuarioSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="__str__", read_only=True)
    lojas = serializers.SerializerMethodField()
    empresa = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ["id", "username", "nome", "papel", "empresa", "lojas"]

    def get_lojas(self, u):
        return [{"id": str(l.id), "nome": l.nome, "slug": l.slug} for l in u.lojas_permitidas()]

    def get_empresa(self, u):
        return {"id": str(u.empresa_id), "nome": u.empresa.nome} if u.empresa_id else None


# --- cardápio -----------------------------------------------------------------
SetorProducaoSerializer = cadastro(SetorProducao)
CategoriaSerializer = cadastro(Categoria)


class VariacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProdutoVariacao
        fields = ["id", "produto", "nome", "preco_centavos", "fator_insumos", "codigo", "ordem", "ativo",
                  "atualizado_em", "excluido_em"]
        read_only_fields = ["id", "atualizado_em", "excluido_em"]


class FichaSerializer(serializers.ModelSerializer):
    class Meta:
        model = FichaTecnicaItem
        fields = ["id", "insumo", "quantidade"]


class ProdutoSerializer(BaseLoja):
    variacoes = serializers.SerializerMethodField()
    grupos_adicionais = serializers.SerializerMethodField()
    abaixo_do_minimo = serializers.BooleanField(read_only=True)

    class Meta(BaseLoja.Meta):
        model = Produto
        read_only_fields = BaseLoja.Meta.read_only_fields + ["estoque_atual", "custo_centavos"]

    def get_variacoes(self, p):
        return VariacaoSerializer(p.variacoes.ativos().filter(ativo=True), many=True).data

    def get_grupos_adicionais(self, p):
        return [str(g) for g in ProdutoGrupoAdicional.objects.filter(produto=p).values_list("grupo_id", flat=True)]


class AdicionalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Adicional
        fields = "__all__"
        read_only_fields = ["id", "criado_em", "atualizado_em", "excluido_em"]


class GrupoAdicionalSerializer(BaseLoja):
    adicionais = serializers.SerializerMethodField()

    class Meta(BaseLoja.Meta):
        model = GrupoAdicional

    def get_adicionais(self, g):
        return AdicionalSerializer(g.adicionais.ativos().filter(ativo=True), many=True).data


# --- clientes / entrega -----------------------------------------------------
class EnderecoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnderecoCliente
        fields = "__all__"
        read_only_fields = ["id", "criado_em", "atualizado_em", "excluido_em"]


class ClienteSerializer(BaseLoja):
    enderecos = serializers.SerializerMethodField()
    selos_meta = serializers.SerializerMethodField()

    def get_selos_meta(self, c):
        return c.loja.fidelidade_selos

    class Meta(BaseLoja.Meta):
        model = Cliente

    def get_enderecos(self, c):
        return EnderecoSerializer(c.enderecos.ativos(), many=True).data


ZonaEntregaSerializer = cadastro(ZonaEntrega)
_EntregadorBase = cadastro(Entregador)


class EntregadorSerializer(_EntregadorBase):
    """Cadastro do entregador. `pin` (4 a 6 números) é o acesso ao app ApFood Entregador:
    a loja define o inicial (ou redefine) e o entregador pode trocar no app."""

    pin = serializers.RegexField(r"^\d{4,6}$", write_only=True, required=False, allow_blank=True,
                                 error_messages={"invalid": "PIN com 4 a 6 números"})
    tem_pin = serializers.SerializerMethodField()
    online_agora = serializers.SerializerMethodField()

    class Meta(_EntregadorBase.Meta):
        exclude = ["loja", "pin_hash"]

    def get_tem_pin(self, e):
        return bool(e.pin_hash)

    def get_online_agora(self, e):
        from datetime import timedelta

        from django.utils import timezone

        return bool(e.online and e.online_em and e.online_em >= timezone.now() - timedelta(seconds=90))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        tel = "".join(c for c in (attrs.get("telefone") or getattr(self.instance, "telefone", "") or "") if c.isdigit())
        if attrs.get("pin") and len(tel) < 10:
            raise serializers.ValidationError({"telefone": ["informe o celular com DDD: é o login do app"]})
        return attrs

    def _pin(self, e, pin):
        if pin:
            e.definir_pin(pin, trocado=False)
            e.save(update_fields=["pin_hash", "pin_trocado", "atualizado_em"])
        return e

    def create(self, validated_data):
        pin = validated_data.pop("pin", "")
        return self._pin(super().create(validated_data), pin)

    def update(self, instance, validated_data):
        pin = validated_data.pop("pin", "")
        return self._pin(super().update(instance, validated_data), pin)
MesaSerializer = cadastro(Mesa)
FornecedorSerializer = cadastro(Fornecedor)
CupomSerializer = cadastro(Cupom, read_only_fields=BaseLoja.Meta.read_only_fields + ["usos"])


class PromocaoSerializer(BaseLoja):
    resumo = serializers.SerializerMethodField()

    class Meta(BaseLoja.Meta):
        model = Promocao

    def get_resumo(self, p):
        return p.regra().descricao()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        tipo = attrs.get("tipo", getattr(self.instance, "tipo", "PERCENTUAL"))
        valor = attrs.get("valor", getattr(self.instance, "valor", 0))
        if tipo == "PERCENTUAL" and not 1 <= valor <= 100:
            raise serializers.ValidationError({"valor": ["o percentual vai de 1 a 100"]})
        if valor <= 0 and tipo != "PRECO_FIXO":
            raise serializers.ValidationError({"valor": ["informe o desconto"]})
        dias = attrs.get("dias")
        if dias is not None and (not isinstance(dias, list) or any(d not in range(7) for d in dias)):
            raise serializers.ValidationError({"dias": ["dias de 0 (segunda) a 6 (domingo)"]})
        canais = attrs.get("canais")
        if canais and any(c not in ("ONLINE", "BALCAO", "DELIVERY", "MESA") for c in canais):
            raise serializers.ValidationError({"canais": ["canal inválido"]})
        ini, fim = attrs.get("data_inicio"), attrs.get("data_fim")
        if ini and fim and fim < ini:
            raise serializers.ValidationError({"data_fim": ["termina antes de começar"]})
        # produtos/categorias precisam ser da mesma loja
        view = self.context.get("view")
        loja_id = getattr(self.instance, "loja_id", None) or (view.get_loja().id if view and hasattr(view, "get_loja") else None)
        if loja_id:
            from apps.cardapio.models import Categoria as Cat
            from apps.cardapio.models import Produto as Prod

            for campo, modelo in (("produtos", Prod), ("categorias", Cat)):
                ids = [str(x) for x in attrs.get(campo) or []]
                if ids and modelo.objects.filter(loja_id=loja_id, id__in=ids).count() != len(set(ids)):
                    raise serializers.ValidationError({campo: ["item de outra loja ou inexistente"]})
                if campo in attrs:
                    attrs[campo] = sorted(set(ids))
        return attrs
CategoriaDespesaSerializer = cadastro(CategoriaDespesa)
TaxaFormaPagamentoSerializer = cadastro(TaxaFormaPagamento)


class DespesaSerializer(BaseLoja):
    class Meta(BaseLoja.Meta):
        model = Despesa
        read_only_fields = BaseLoja.Meta.read_only_fields + ["turno", "usuario"]


# --- pedidos ----------------------------------------------------------------
class ItemAdicionalOut(serializers.ModelSerializer):
    class Meta:
        model = ItemPedidoAdicional
        fields = ["adicional", "nome", "quantidade", "preco_unitario_centavos"]


class ItemSaborOut(serializers.ModelSerializer):
    class Meta:
        model = ItemPedidoSabor
        fields = ["produto", "nome", "preco_unitario_centavos"]


class ItemOut(serializers.ModelSerializer):
    adicionais = ItemAdicionalOut(many=True, read_only=True)
    sabores = ItemSaborOut(many=True, read_only=True)

    class Meta:
        model = ItemPedido
        exclude = ["pedido", "criado_em"]


class PagamentoOut(serializers.ModelSerializer):
    pagador = serializers.SerializerMethodField()

    class Meta:
        model = Pagamento
        fields = "__all__"

    def get_pagador(self, pg):
        return (pg.dados_externos or {}).get("pagador", "")


class HistoricoOut(serializers.ModelSerializer):
    class Meta:
        model = HistoricoStatusPedido
        fields = ["status_de", "status_para", "usuario", "observacao", "criado_em"]


class PedidoOut(serializers.ModelSerializer):
    entregador_nome = serializers.CharField(source="entregador.nome", read_only=True, default=None)
    itens = ItemOut(many=True, read_only=True)
    pagamentos = PagamentoOut(many=True, read_only=True)
    historico = HistoricoOut(many=True, read_only=True)

    class Meta:
        model = Pedido
        fields = "__all__"


class AdicionalIn(serializers.Serializer):
    adicional_id = serializers.UUIDField()
    quantidade = serializers.IntegerField(min_value=1, default=1)


class ItemIn(serializers.Serializer):
    produto_id = serializers.UUIDField()
    quantidade = serializers.IntegerField(min_value=1, default=1)
    variacao_id = serializers.UUIDField(required=False, allow_null=True)
    sabores = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    adicionais = AdicionalIn(many=True, required=False, default=list)
    observacao = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)


class EnderecoIn(serializers.Serializer):
    logradouro = serializers.CharField(max_length=160)
    numero = serializers.CharField(max_length=20)
    complemento = serializers.CharField(required=False, allow_blank=True, default="")
    bairro = serializers.CharField(max_length=80)
    cidade = serializers.CharField(required=False, allow_blank=True, default="")
    cep = serializers.CharField(required=False, allow_blank=True, default="")
    referencia = serializers.CharField(required=False, allow_blank=True, default="")
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)


class PedidoIn(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    canal = serializers.ChoiceField(CanalVenda.choices())
    tipo_atendimento = serializers.ChoiceField(TipoAtendimento.choices())
    origem_contato = serializers.ChoiceField(OrigemContato.choices(), required=False, allow_blank=True, default="")
    itens = ItemIn(many=True)
    nome_cliente = serializers.CharField(required=False, allow_blank=True, default="", max_length=120)
    telefone_cliente = serializers.CharField(required=False, allow_blank=True, default="", max_length=20)
    mesa = serializers.CharField(required=False, allow_blank=True, default="", max_length=10)
    senha = serializers.CharField(required=False, allow_blank=True, default="", max_length=10)
    comanda = serializers.UUIDField(required=False, allow_null=True)
    endereco = EnderecoIn(required=False, allow_null=True)
    taxa_entrega_centavos = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    desconto_centavos = serializers.IntegerField(min_value=0, default=0)
    acrescimo_centavos = serializers.IntegerField(min_value=0, default=0)
    cupom_codigo = serializers.CharField(required=False, allow_blank=True, default="")
    troco_para_centavos = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    forma_pagamento_prevista = serializers.ChoiceField(FormaPagamento.choices(), required=False, allow_blank=True, default="")
    observacao = serializers.CharField(required=False, allow_blank=True, default="")
    cpf_nota = serializers.CharField(required=False, allow_blank=True, default="", max_length=18)
    entregador_id = serializers.UUIDField(required=False, allow_null=True)
    marketplace = serializers.CharField(required=False, allow_blank=True, default="")
    id_externo = serializers.CharField(required=False, allow_blank=True, default="")
    codigo_externo = serializers.CharField(required=False, allow_blank=True, default="")
    codigo_local = serializers.CharField(required=False, allow_blank=True, default="", max_length=20)
    usar_cashback_centavos = serializers.IntegerField(min_value=0, default=0)


class PedidoOnlineIn(PedidoIn):
    """Cardápio público: canal fixo ONLINE, sem desconto/taxa manual."""

    canal = serializers.HiddenField(default=CanalVenda.ONLINE)
    tipo_atendimento = serializers.ChoiceField([TipoAtendimento.ENTREGA.value, TipoAtendimento.RETIRADA.value])
    nome_cliente = serializers.CharField(max_length=120)
    telefone_cliente = serializers.CharField(max_length=20)
    forma_pagamento_prevista = serializers.ChoiceField(
        [f.value for f in (FormaPagamento.DINHEIRO, FormaPagamento.PIX, FormaPagamento.CARTAO_CREDITO,
                           FormaPagamento.CARTAO_DEBITO, FormaPagamento.VOUCHER)]
    )

    def get_fields(self):
        campos = super().get_fields()
        for nome in ("taxa_entrega_centavos", "desconto_centavos", "acrescimo_centavos", "comanda", "entregador_id",
                     "marketplace", "id_externo", "codigo_externo", "codigo_local", "mesa", "senha", "origem_contato",
                     "usar_cashback_centavos"):
            campos.pop(nome, None)
        return campos


class PedidoMesaIn(PedidoIn):
    """Autoatendimento pelo QR Code da mesa: só itens, nome e observação."""

    canal = serializers.HiddenField(default=CanalVenda.MESA)
    tipo_atendimento = serializers.HiddenField(default=TipoAtendimento.CONSUMO_LOCAL)

    def get_fields(self):
        campos = super().get_fields()
        for nome in list(campos):
            if nome not in ("canal", "tipo_atendimento", "itens", "nome_cliente", "telefone_cliente", "observacao"):
                campos.pop(nome)
        return campos


class StatusIn(serializers.Serializer):
    status = serializers.ChoiceField(StatusPedido.choices())
    motivo = serializers.CharField(required=False, allow_blank=True, default="")
    entregador_id = serializers.UUIDField(required=False, allow_null=True)


class PagamentoIn(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    forma = serializers.ChoiceField(FormaPagamento.choices())
    valor_centavos = serializers.IntegerField(min_value=1)
    valor_recebido_centavos = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    bandeira = serializers.CharField(required=False, allow_blank=True, default="")
    referencia_externa = serializers.CharField(required=False, allow_blank=True, default="")
    pago_online = serializers.BooleanField(default=False)
    pagador = serializers.CharField(required=False, allow_blank=True, default="", max_length=60,
                                    help_text='quem pagou esta parte (mesa): "Cliente 1", "João"')


# --- caixa ------------------------------------------------------------------
class TurnoOut(serializers.ModelSerializer):
    class Meta:
        model = TurnoCaixa
        fields = "__all__"


class MovimentacaoCaixaOut(serializers.ModelSerializer):
    class Meta:
        model = MovimentacaoCaixa
        fields = "__all__"


class ConferenciaOut(serializers.ModelSerializer):
    class Meta:
        model = ConferenciaCaixa
        exclude = ["turno"]


class AbrirTurnoIn(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    valor_abertura_centavos = serializers.IntegerField(min_value=0)


class MovimentoIn(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    tipo = serializers.ChoiceField(["SANGRIA", "SUPRIMENTO"])
    valor_centavos = serializers.IntegerField(min_value=1)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class DespesaCaixaIn(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    descricao = serializers.CharField(max_length=160)
    valor_centavos = serializers.IntegerField(min_value=1)
    categoria = serializers.UUIDField(required=False, allow_null=True)


class FecharTurnoIn(serializers.Serializer):
    informado = serializers.DictField(child=serializers.IntegerField(min_value=0))
    tipo_conferencia = serializers.ChoiceField(TipoConferencia.choices(), default=TipoConferencia.CEGA)
    observacao = serializers.CharField(required=False, allow_blank=True, default="")


# --- salão ------------------------------------------------------------------
class ComandaOut(serializers.ModelSerializer):
    pagamentos = PagamentoOut(many=True, read_only=True)

    class Meta:
        model = Comanda
        fields = "__all__"


class AbrirComandaIn(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    mesa = serializers.UUIDField(required=False, allow_null=True)
    numero = serializers.CharField(required=False, allow_blank=True, default="")
    nome_cliente = serializers.CharField(required=False, allow_blank=True, default="")
    pessoas = serializers.IntegerField(min_value=1, default=1)


# --- estoque / compras ------------------------------------------------------
class MovimentacaoEstoqueOut(serializers.ModelSerializer):
    produto_nome = serializers.CharField(source="produto.nome", read_only=True)

    class Meta:
        model = MovimentacaoEstoque
        fields = "__all__"


class EstoqueIn(serializers.Serializer):
    produto = serializers.UUIDField()
    operacao = serializers.ChoiceField(["ENTRADA", "PERDA", "INVENTARIO"])
    quantidade = serializers.DecimalField(max_digits=12, decimal_places=3)
    custo_unitario_centavos = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class ItemCompraSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemCompra
        exclude = ["compra"]


class CompraSerializer(BaseLoja):
    itens = ItemCompraSerializer(many=True)

    class Meta(BaseLoja.Meta):
        model = Compra
        read_only_fields = ["id", "criado_em", "atualizado_em", "status", "total_centavos", "despesa",
                            "lancada_por", "lancada_em"]

    def create(self, dados):
        itens = dados.pop("itens")
        compra = Compra.objects.create(**dados)
        self._salvar_itens(compra, itens)
        return compra

    def update(self, compra, dados):
        if compra.status != "RASCUNHO":
            raise serializers.ValidationError("só compras em rascunho podem ser alteradas")
        itens = dados.pop("itens", None)
        compra = super().update(compra, dados)
        if itens is not None:
            compra.itens.all().delete()
            self._salvar_itens(compra, itens)
        return compra

    def _salvar_itens(self, compra, itens):
        from apps.compras.services import recalcular_total

        for i in itens:
            if i["produto"].loja_id != compra.loja_id:
                raise serializers.ValidationError({"itens": ["produto de outra loja"]})
            ItemCompra.objects.create(compra=compra, **i)
        recalcular_total(compra)
