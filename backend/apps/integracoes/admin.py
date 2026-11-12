from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import Integracao, WebhookRecebido


@admin.register(Integracao)
class IntegracaoAdmin(EscopoAdmin):
    caminho_loja = "loja"
    edicao_minima = "admin"
    list_display = ["loja", "tipo", "provedor", "ativo", "ultimo_sucesso_em"]
    list_filter = ["tipo", "provedor", "ativo"]
    readonly_fields = ["ultimo_sucesso_em", "ultimo_erro"]


@admin.register(WebhookRecebido)
class WebhookRecebidoAdmin(EscopoAdmin):
    somente_master = True
    list_display = ["criado_em", "provedor", "evento", "loja", "processado_em"]
    list_filter = ["provedor", "evento"]
    readonly_fields = [f.name for f in WebhookRecebido._meta.fields]

    def has_add_permission(self, request):
        return False
