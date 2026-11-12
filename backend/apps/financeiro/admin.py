from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import CategoriaDespesa, Despesa


@admin.register(CategoriaDespesa)
class CategoriaDespesaAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "ativa"]


@admin.register(Despesa)
class DespesaAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["data_competencia", "descricao", "loja", "categoria", "valor_centavos", "forma_pagamento"]
    list_filter = ["categoria"]
    date_hierarchy = "data_competencia"
