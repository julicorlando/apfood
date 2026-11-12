from apfood_core import permissoes
from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import Dispositivo, Empresa, Loja


class LojaInline(admin.TabularInline):
    model = Loja
    fields = ["nome", "slug", "cidade", "ativa", "aberta_para_pedidos"]
    show_change_link = True
    extra = 0


@admin.register(Empresa)
class EmpresaAdmin(EscopoAdmin):
    """MASTER cadastra e bloqueia empresas; o ADMIN da empresa só vê a dele
    (sem poder mexer em plano, limites ou bloqueio)."""

    caminho_empresa = "id"
    edicao_minima = "admin"
    list_display = ["nome", "cnpj", "responsavel", "ativa", "limite_lojas", "qtd_lojas", "criado_em"]
    list_filter = ["ativa"]
    search_fields = ["nome", "razao_social", "cnpj", "email"]
    inlines = [LojaInline]
    campos_do_master = ["ativa", "motivo_bloqueio", "limite_lojas", "limite_usuarios", "observacoes"]

    @admin.display(description="lojas")
    def qtd_lojas(self, obj):
        return obj.lojas.count()

    def get_readonly_fields(self, request, obj=None):
        return [] if request.user.eh_master else self.campos_do_master

    def get_inlines(self, request, obj):
        return self.inlines if request.user.eh_master else []

    def has_add_permission(self, request):
        return permissoes.pode_cadastrar_empresa(request.user.acesso())

    def has_delete_permission(self, request, obj=None):
        return request.user.eh_master


@admin.register(Loja)
class LojaAdmin(EscopoAdmin):
    caminho_loja = "id"
    edicao_minima = "admin"
    list_display = ["nome", "empresa", "slug", "cidade", "ativa", "aberta_para_pedidos"]
    list_filter = ["empresa", "ativa"]
    prepopulated_fields = {"slug": ["nome"]}
    search_fields = ["nome", "slug", "empresa__nome"]

    def get_list_filter(self, request):
        return self.list_filter if request.user.eh_master else ["ativa"]

    def has_add_permission(self, request):
        u = request.user
        if not super().has_add_permission(request):
            return False
        if u.eh_master:
            return True
        e = u.empresa
        return permissoes.pode_criar_loja(u.acesso(), str(e.id), e.lojas.count(), e.limite_lojas)


@admin.register(Dispositivo)
class DispositivoAdmin(EscopoAdmin):
    caminho_loja = "loja"
    edicao_minima = "admin"
    list_display = ["nome", "loja", "versao_app", "ultimo_sync_em", "ativo"]
    list_filter = ["ativo"]
    exclude = ["token_hash"]
