from django.contrib import admin

from apps.core.admin import EscopoAdmin, EscopoInlineMixin

from .models import ConferenciaCaixa, MovimentacaoCaixa, TurnoCaixa


class SomenteLeituraInline(EscopoInlineMixin):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False  # caixa só se movimenta pelo PDV/API (regras de caixa)

    def has_change_permission(self, request, obj=None):
        return False


class MovimentacaoInline(SomenteLeituraInline, admin.TabularInline):
    model = MovimentacaoCaixa
    fields = ["criado_em", "tipo", "forma_pagamento", "valor_centavos", "usuario", "motivo"]
    readonly_fields = fields


class ConferenciaInline(SomenteLeituraInline, admin.TabularInline):
    model = ConferenciaCaixa
    fields = ["forma_pagamento", "valor_esperado_centavos", "valor_informado_centavos", "diferenca_centavos"]
    readonly_fields = fields


@admin.register(TurnoCaixa)
class TurnoCaixaAdmin(EscopoAdmin):
    """Consulta de turnos. Abertura e fechamento acontecem no PDV."""

    caminho_loja = "loja"
    list_display = ["aberto_em", "usuario", "loja", "status", "valor_abertura_centavos", "diferenca_centavos"]
    list_filter = ["status"]
    date_hierarchy = "aberto_em"
    inlines = [MovimentacaoInline, ConferenciaInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
