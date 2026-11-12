from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import ConfiguracaoFiscal, NotaFiscal


@admin.register(ConfiguracaoFiscal)
class ConfiguracaoFiscalAdmin(EscopoAdmin):
    caminho_loja = "loja"
    edicao_minima = "admin"
    list_display = ["loja", "ativa", "regime_tributario", "modelo_padrao", "ambiente", "emitir_automaticamente"]


@admin.register(NotaFiscal)
class NotaFiscalAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["criado_em", "loja", "modelo", "numero", "status", "valor_total_centavos", "ambiente"]
    list_filter = ["status", "modelo", "ambiente"]
    search_fields = ["chave", "numero", "cpf_cnpj_consumidor"]
    date_hierarchy = "criado_em"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
