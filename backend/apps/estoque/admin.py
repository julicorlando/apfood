from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import MovimentacaoEstoque


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(EscopoAdmin):
    """Kardex (somente leitura). Entradas e ajustes pelo PDV/API, que atualizam o saldo."""

    caminho_loja = "loja"
    list_display = ["criado_em", "produto", "tipo", "quantidade", "saldo_posterior", "usuario"]
    list_filter = ["tipo"]
    search_fields = ["produto__nome"]
    date_hierarchy = "criado_em"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
