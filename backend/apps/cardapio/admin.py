from django.contrib import admin

from apps.core.admin import EscopoAdmin, EscopoInlineMixin

from .models import (
    Adicional,
    Categoria,
    FichaTecnicaItem,
    GrupoAdicional,
    Produto,
    ProdutoGrupoAdicional,
    ProdutoVariacao,
    SetorProducao,
)


class FichaTecnicaInline(EscopoInlineMixin, admin.TabularInline):
    model = FichaTecnicaItem
    fk_name = "produto"
    autocomplete_fields = ["insumo"]
    extra = 0


class VariacaoInline(EscopoInlineMixin, admin.TabularInline):
    model = ProdutoVariacao
    extra = 0
    fields = ["nome", "preco_centavos", "fator_insumos", "codigo", "ordem", "ativo"]


class GruposInline(EscopoInlineMixin, admin.TabularInline):
    model = ProdutoGrupoAdicional
    extra = 0


class AdicionalInline(EscopoInlineMixin, admin.TabularInline):
    model = Adicional
    extra = 0


@admin.register(SetorProducao)
class SetorProducaoAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "impressora", "ativo"]


@admin.register(Categoria)
class CategoriaAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "setor", "max_sabores", "ordem", "ativa"]
    list_filter = ["ativa"]


@admin.register(Produto)
class ProdutoAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "tipo", "categoria", "preco_centavos", "controla_estoque", "estoque_atual", "pausado", "ativo"]
    list_filter = ["tipo", "controla_estoque", "pausado", "ativo"]
    list_editable = ["pausado"]
    search_fields = ["nome", "codigo", "gtin"]
    inlines = [VariacaoInline, GruposInline, FichaTecnicaInline]
    fieldsets = [
        (None, {"fields": ["loja", "tipo", "categoria", "nome", "descricao", "imagem", "codigo", "gtin"]}),
        ("Venda", {"fields": ["preco_centavos", "custo_centavos", "ativo", "disponivel_online",
                              "pausado", "pausado_ate", "ordem", "setor"]}),
        ("Estoque", {"fields": ["controla_estoque", "baixar_insumos", "unidade", "estoque_atual", "estoque_minimo"]}),
        ("Fiscal", {"classes": ["collapse"], "fields": ["ncm", "cest", "cfop", "origem", "cst_csosn", "aliquota_icms"]}),
    ]


@admin.register(GrupoAdicional)
class GrupoAdicionalAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "min_selecao", "max_selecao", "ativo"]
    inlines = [AdicionalInline]
