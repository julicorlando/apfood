from django.contrib import admin

from apps.core.admin import EscopoAdmin, EscopoInlineMixin

from .models import Compra, Fornecedor, ItemCompra


@admin.register(Fornecedor)
class FornecedorAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "cnpj", "telefone", "contato", "loja"]
    search_fields = ["nome", "cnpj"]


class ItemCompraInline(EscopoInlineMixin, admin.TabularInline):
    model = ItemCompra
    extra = 0
    autocomplete_fields = ["produto"]


@admin.register(Compra)
class CompraAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["data_entrada", "fornecedor", "numero_nota", "total_centavos", "status", "loja"]
    list_filter = ["status"]
    search_fields = ["numero_nota", "chave_nfe", "fornecedor__nome"]
    date_hierarchy = "data_entrada"
    inlines = [ItemCompraInline]
    readonly_fields = ["status", "despesa", "lancada_por", "lancada_em"]
    # Lançar/cancelar (estoque + conta a pagar) via serviço — ação no Passo 2
