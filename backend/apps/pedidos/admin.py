from django.contrib import admin

from .models import HistoricoStatusPedido, ItemPedido, ItemPedidoAdicional, Pagamento, Pedido


class ItemInline(admin.TabularInline):
    model = ItemPedido
    extra = 0


class PagamentoInline(admin.TabularInline):
    model = Pagamento
    extra = 0


class HistoricoInline(admin.TabularInline):
    model = HistoricoStatusPedido
    extra = 0
    readonly_fields = ["criado_em", "status_de", "status_para", "usuario", "observacao"]


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ["__str__", "data_referencia", "loja", "canal", "tipo_atendimento", "status", "total_centavos"]
    list_filter = ["loja", "canal", "status", "data_referencia"]
    search_fields = ["nome_cliente", "telefone_cliente", "token_rastreio"]
    date_hierarchy = "criado_em"
    inlines = [ItemInline, PagamentoInline, HistoricoInline]


admin.site.register(ItemPedidoAdicional)
