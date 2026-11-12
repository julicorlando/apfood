from django.contrib import admin

from .models import MovimentacaoEstoque


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = ["criado_em", "produto", "tipo", "quantidade", "saldo_posterior", "usuario"]
    list_filter = ["loja", "tipo"]
    search_fields = ["produto__nome"]
    date_hierarchy = "criado_em"
