from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import Cupom


@admin.register(Cupom)
class CupomAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["codigo", "tipo", "valor", "loja", "usos", "usos_maximos", "valido_ate", "ativo"]
    list_filter = ["tipo", "ativo"]
    search_fields = ["codigo"]
    readonly_fields = ["usos"]
