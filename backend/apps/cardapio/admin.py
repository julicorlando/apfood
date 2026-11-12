from django.contrib import admin

from .models import Adicional, Categoria, FichaTecnicaItem, GrupoAdicional, Produto, ProdutoGrupoAdicional


class FichaTecnicaInline(admin.TabularInline):
    model = FichaTecnicaItem
    fk_name = "produto"
    autocomplete_fields = ["insumo"]
    extra = 0


class GruposInline(admin.TabularInline):
    model = ProdutoGrupoAdicional
    extra = 0


class AdicionalInline(admin.TabularInline):
    model = Adicional
    extra = 0


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nome", "loja", "ordem", "ativa"]
    list_filter = ["loja", "ativa"]


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ["nome", "loja", "tipo", "categoria", "preco_centavos", "controla_estoque", "estoque_atual", "ativo"]
    list_filter = ["loja", "tipo", "categoria", "controla_estoque", "ativo"]
    search_fields = ["nome", "codigo"]
    inlines = [GruposInline, FichaTecnicaInline]


@admin.register(GrupoAdicional)
class GrupoAdicionalAdmin(admin.ModelAdmin):
    list_display = ["nome", "loja", "min_selecao", "max_selecao", "ativo"]
    inlines = [AdicionalInline]
