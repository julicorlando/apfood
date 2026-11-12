from django.contrib import admin

from apps.core.admin import EscopoAdmin, EscopoInlineMixin

from .models import HistoricoStatusPedido, ItemPedido, Pagamento, Pedido


class LeituraInline(EscopoInlineMixin):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ItemInline(LeituraInline, admin.TabularInline):
    model = ItemPedido
    fields = ["quantidade", "nome_produto", "preco_unitario_centavos", "total_adicionais_centavos", "total_centavos", "observacao"]
    readonly_fields = fields


class PagamentoInline(LeituraInline, admin.TabularInline):
    model = Pagamento
    fields = ["forma", "status", "valor_centavos", "troco_centavos", "turno", "confirmado_em"]
    readonly_fields = fields


class HistoricoInline(LeituraInline, admin.TabularInline):
    model = HistoricoStatusPedido
    fields = ["criado_em", "status_de", "status_para", "usuario", "observacao"]
    readonly_fields = fields


@admin.register(Pedido)
class PedidoAdmin(EscopoAdmin):
    """Consulta de pedidos. Lançamento e mudança de status pelo PDV/API."""

    caminho_loja = "loja"
    list_display = ["__str__", "data_referencia", "loja", "canal", "tipo_atendimento", "status", "total_centavos"]
    list_filter = ["canal", "status", "data_referencia"]
    search_fields = ["nome_cliente", "telefone_cliente", "token_rastreio"]
    date_hierarchy = "criado_em"
    inlines = [ItemInline, PagamentoInline, HistoricoInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
