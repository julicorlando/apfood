from django.contrib import admin

from apps.core.admin import EscopoAdmin, EscopoInlineMixin

from .models import Adicional, Categoria, FichaTecnicaItem, GrupoAdicional, Produto, ProdutoGrupoAdicional


class FichaTecnicaInline(EscopoInlineMixin, admin.TabularInline):
    model = FichaTecnicaItem
    fk_name = "produto"
    autocomplete_fields = ["insumo"]
    extra = 0


class GruposInline(EscopoInlineMixin, admin.TabularInline):
    model = ProdutoGrupoAdicional
    extra = 0


class AdicionalInline(EscopoInlineMixin, admin.TabularInline):
    model = Adicional
    extra = 0


@admin.register(Categoria)
class CategoriaAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "ordem", "ativa"]
    list_filter = ["ativa"]


@admin.register(Produto)
class ProdutoAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "tipo", "categoria", "preco_centavos", "controla_estoque", "estoque_atual", "ativo"]
    list_filter = ["tipo", "controla_estoque", "ativo"]
    search_fields = ["nome", "codigo"]
    inlines = [GruposInline, FichaTecnicaInline]


@admin.register(GrupoAdicional)
class GrupoAdicionalAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "min_selecao", "max_selecao", "ativo"]
    inlines = [AdicionalInline]
