from django.contrib import admin

from .models import CategoriaDespesa, Despesa

admin.site.register(CategoriaDespesa)


@admin.register(Despesa)
class DespesaAdmin(admin.ModelAdmin):
    list_display = ["data_competencia", "descricao", "categoria", "valor_centavos", "forma_pagamento"]
    list_filter = ["loja", "categoria"]
    date_hierarchy = "data_competencia"
