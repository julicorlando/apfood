from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import CategoriaDespesa, Despesa, TaxaFormaPagamento


@admin.register(CategoriaDespesa)
class CategoriaDespesaAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "ativa"]


@admin.register(Despesa)
class DespesaAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["data_competencia", "descricao", "loja", "fornecedor", "valor_centavos", "data_vencimento", "data_pagamento"]
    list_filter = ["categoria"]
    date_hierarchy = "data_competencia"


@admin.register(TaxaFormaPagamento)
class TaxaFormaPagamentoAdmin(EscopoAdmin):
    caminho_loja = "loja"
    edicao_minima = "admin"
    list_display = ["forma_pagamento", "bandeira", "loja", "taxa_percentual", "taxa_fixa_centavos", "prazo_recebimento_dias"]
