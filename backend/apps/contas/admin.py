from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import LogAuditoria, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ["username", "first_name", "loja", "papel", "is_active"]
    list_filter = ["loja", "papel", "is_active"]
    fieldsets = UserAdmin.fieldsets + (("ApFood", {"fields": ["loja", "papel"]}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("ApFood", {"fields": ["loja", "papel"]}),)


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ["criado_em", "loja", "usuario", "acao", "entidade", "entidade_id"]
    list_filter = ["loja", "acao"]
    readonly_fields = [f.name for f in LogAuditoria._meta.fields]
