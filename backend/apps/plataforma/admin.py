from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import Fatura, Plano


@admin.register(Plano)
class PlanoAdmin(EscopoAdmin):
    somente_master = True
    list_display = ["nome", "preco_mensal_centavos", "limite_lojas", "limite_usuarios", "recursos", "publico", "ativo"]


@admin.register(Fatura)
class FaturaAdmin(EscopoAdmin):
    """MASTER vê todas; ADMIN da empresa vê as faturas dela (somente leitura)."""

    caminho_empresa = "empresa"
    edicao_minima = "admin"
    list_display = ["empresa", "competencia", "valor_centavos", "vencimento", "status", "pago_em"]
    list_filter = ["status"]
    date_hierarchy = "competencia"

    def has_add_permission(self, request):
        return request.user.eh_master

    def has_change_permission(self, request, obj=None):
        return request.user.eh_master

    def has_delete_permission(self, request, obj=None):
        return request.user.eh_master
