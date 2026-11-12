from django.contrib import admin

from .models import ConferenciaCaixa, MovimentacaoCaixa, TurnoCaixa


class MovimentacaoInline(admin.TabularInline):
    model = MovimentacaoCaixa
    extra = 0
    readonly_fields = ["criado_em", "tipo", "forma_pagamento", "valor_centavos", "usuario", "motivo"]
    exclude = ["loja", "pagamento", "despesa"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False  # movimentações só pelo PDV/API (regras de caixa)


class ConferenciaInline(admin.TabularInline):
    model = ConferenciaCaixa
    extra = 0


@admin.register(TurnoCaixa)
class TurnoCaixaAdmin(admin.ModelAdmin):
    list_display = ["aberto_em", "usuario", "loja", "status", "valor_abertura_centavos", "diferenca_centavos"]
    list_filter = ["loja", "status", "usuario"]
    date_hierarchy = "aberto_em"
    inlines = [MovimentacaoInline, ConferenciaInline]
