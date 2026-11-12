from django.contrib import admin

from .models import Cliente, EnderecoCliente, Entregador, ZonaEntrega


class EnderecoInline(admin.StackedInline):
    model = EnderecoCliente
    extra = 0


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nome", "telefone", "loja"]
    search_fields = ["nome", "telefone"]
    list_filter = ["loja"]
    inlines = [EnderecoInline]


@admin.register(ZonaEntrega)
class ZonaEntregaAdmin(admin.ModelAdmin):
    list_display = ["nome", "loja", "tipo", "raio_max_km", "taxa_centavos", "ativa"]
    list_filter = ["loja", "tipo", "ativa"]


@admin.register(Entregador)
class EntregadorAdmin(admin.ModelAdmin):
    list_display = ["nome", "telefone", "loja", "ativo"]
