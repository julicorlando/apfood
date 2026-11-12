from django.contrib import admin

from .models import Dispositivo, Loja


@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    list_display = ["nome", "slug", "cidade", "aberta_para_pedidos"]
    prepopulated_fields = {"slug": ["nome"]}
    search_fields = ["nome", "slug"]


@admin.register(Dispositivo)
class DispositivoAdmin(admin.ModelAdmin):
    list_display = ["nome", "loja", "versao_app", "ultimo_sync_em", "ativo"]
    list_filter = ["loja", "ativo"]
