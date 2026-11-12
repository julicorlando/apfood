from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import Comanda, Mesa


@admin.register(Mesa)
class MesaAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "area", "capacidade", "loja", "ativa"]
    list_filter = ["area", "ativa"]


@admin.register(Comanda)
class ComandaAdmin(EscopoAdmin):
    """Consulta. Abertura, pedidos e fechamento pelo PDV."""

    caminho_loja = "loja"
    list_display = ["__str__", "loja", "status", "pessoas", "total_centavos", "criado_em", "fechada_em"]
    list_filter = ["status"]
    date_hierarchy = "criado_em"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
