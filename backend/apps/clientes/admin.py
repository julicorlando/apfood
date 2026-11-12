from django.contrib import admin

from apps.core.admin import EscopoAdmin, EscopoInlineMixin

from .models import Cliente, EnderecoCliente, Entregador, ZonaEntrega


class EnderecoInline(EscopoInlineMixin, admin.StackedInline):
    model = EnderecoCliente
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "telefone", "loja"]
    search_fields = ["nome", "telefone"]
    inlines = [EnderecoInline]


@admin.register(ZonaEntrega)
class ZonaEntregaAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "loja", "tipo", "raio_max_km", "taxa_centavos", "ativa"]
    list_filter = ["tipo", "ativa"]


@admin.register(Entregador)
class EntregadorAdmin(EscopoAdmin):
    caminho_loja = "loja"
    list_display = ["nome", "telefone", "loja", "ativo"]
