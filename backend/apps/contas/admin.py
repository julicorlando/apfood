from apfood_core.enums import PapelUsuario
from apfood_core.permissoes import GERENCIA
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied

from apps.core.admin import EscopoAdmin

from .models import LogAuditoria, Usuario


@admin.register(Usuario)
class UsuarioAdmin(EscopoAdmin, UserAdmin):
    caminho_empresa = "empresa"
    list_display = ["username", "first_name", "empresa", "papel", "is_active"]
    list_filter = ["papel", "is_active"]
    filter_horizontal = ["lojas"]
    fieldsets = (
        (None, {"fields": ["username", "password"]}),
        ("Dados", {"fields": ["first_name", "last_name", "email"]}),
        ("Acesso", {"fields": ["empresa", "papel", "lojas", "is_active"]}),
        ("Datas", {"fields": ["last_login", "date_joined"]}),
    )
    add_fieldsets = (
        (None, {"fields": ["username", "password1", "password2"]}),
        ("Acesso", {"fields": ["first_name", "empresa", "papel", "lojas"]}),
    )
    readonly_fields = ["last_login", "date_joined"]

    def get_list_filter(self, request):
        return (["empresa"] if request.user.eh_master else []) + self.list_filter

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        u = request.user
        if u.eh_master:
            return qs
        # só enxerga quem pode gerenciar (+ ele mesmo)
        return qs.filter(papel__in=GERENCIA[PapelUsuario(u.papel)]) | qs.filter(pk=u.pk)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "papel" and not request.user.eh_master:
            permitidos = GERENCIA[PapelUsuario(request.user.papel)]
            kwargs["choices"] = [c for c in db_field.choices if c[0] in permitidos]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not request.user.eh_master:
            ro.append("empresa")  # preenchida automaticamente com a do usuário
            if obj is not None and obj.pk == request.user.pk:
                ro += ["papel", "lojas", "is_active"]  # ninguém se promove sozinho
        return ro

    def save_model(self, request, obj, form, change):
        u = request.user
        if not u.eh_master:
            obj.empresa_id = u.empresa_id
            if obj.pk != u.pk and obj.papel not in GERENCIA[PapelUsuario(u.papel)]:
                raise PermissionDenied("sem permissão para este papel")
        obj.full_clean(exclude=["password"])
        super().save_model(request, obj, form, change)


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(EscopoAdmin):
    caminho_empresa = "empresa"
    list_display = ["criado_em", "empresa", "loja", "usuario", "acao", "entidade", "entidade_id"]
    list_filter = ["acao"]
    readonly_fields = [f.name for f in LogAuditoria._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
