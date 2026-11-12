"""Isolamento multiempresa na retaguarda (Django admin).

Todo ModelAdmin do ApFood herda `EscopoAdmin` e declara o caminho até a loja
(`caminho_loja`) ou até a empresa (`caminho_empresa`). Resultado:
  • MASTER vê tudo;
  • ADMIN vê só a própria empresa (todas as lojas dela);
  • GERENTE vê só as lojas atribuídas;
  • listas, buscas, selects de chave estrangeira e o salvar respeitam isso.
A API (Passo 2) usa a mesma regra via `Usuario.lojas_permitidas()`.
"""

from django.contrib import admin
from django.core.exceptions import PermissionDenied


def limitar_relacionado(qs, user):
    """Restringe as opções de um select (FK/M2M) ao escopo do usuário."""
    if user.eh_master:
        return qs
    model = qs.model
    nomes = {f.name for f in model._meta.get_fields()}
    if model._meta.label == "lojas.Loja":
        return user.lojas_permitidas()
    if model._meta.label == "lojas.Empresa":
        return qs.filter(id=user.empresa_id)
    if "loja" in nomes:
        return qs.filter(loja__in=user.lojas_permitidas())
    if "empresa" in nomes:
        return qs.filter(empresa_id=user.empresa_id)
    if "grupo" in nomes:  # Adicional
        return qs.filter(grupo__loja__in=user.lojas_permitidas())
    if "cliente" in nomes:  # EnderecoCliente
        return qs.filter(cliente__loja__in=user.lojas_permitidas())
    return qs


class EscopoAdmin(admin.ModelAdmin):
    caminho_loja: str | None = None  # ex.: "loja", "grupo__loja", "turno__loja"
    caminho_empresa: str | None = None  # ex.: "empresa", "id"
    somente_master = False  # cadastro exclusivo da plataforma
    edicao_minima = "gerente"  # "gerente" ou "admin": quem pode criar/alterar/excluir

    # --- escopo -------------------------------------------------------------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.filtrar(qs, request.user)

    def filtrar(self, qs, user):
        if user.eh_master:
            return qs
        if user.acesso().bloqueado:
            return qs.none()
        if self.caminho_loja:
            return qs.filter(**{f"{self.caminho_loja}__in": user.lojas_permitidas()}).distinct()
        if self.caminho_empresa:
            return qs.filter(**{self.caminho_empresa: user.empresa_id})
        return qs.none()  # sem escopo declarado = invisível para não-master

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if field is not None and hasattr(field, "queryset"):
            field.queryset = limitar_relacionado(field.queryset, request.user)
        return field

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if field is not None and hasattr(field, "queryset"):
            field.queryset = limitar_relacionado(field.queryset, request.user)
        return field

    def save_model(self, request, obj, form, change):
        user = request.user
        if not user.eh_master:
            if hasattr(obj, "empresa_id") and obj.empresa_id is None and obj._meta.label != "lojas.Empresa":
                obj.empresa_id = user.empresa_id
            loja_id = getattr(obj, "loja_id", None)
            if loja_id is not None and not user.lojas_permitidas().filter(id=loja_id).exists():
                raise PermissionDenied("loja fora do seu acesso")
        super().save_model(request, obj, form, change)

    # --- permissões por papel (dispensa as permissões por model do Django) --
    def _pode_ver(self, request):
        u = request.user
        if not (u.is_active and u.is_staff):
            return False
        if self.somente_master:
            return u.eh_master
        return u.eh_gerente and not u.acesso().bloqueado

    def _pode_editar(self, request):
        if not self._pode_ver(request):
            return False
        return request.user.eh_admin if self.edicao_minima == "admin" else request.user.eh_gerente

    def has_module_permission(self, request):
        return self._pode_ver(request)

    def has_view_permission(self, request, obj=None):
        return self._pode_ver(request)

    def has_add_permission(self, request, *args):
        return self._pode_editar(request)

    def has_change_permission(self, request, obj=None):
        return self._pode_editar(request)

    def has_delete_permission(self, request, obj=None):
        return self._pode_editar(request)


class EscopoInlineMixin:
    """Mesma limitação de selects para inlines."""

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if field is not None and hasattr(field, "queryset") and not request.user.eh_master:
            field.queryset = limitar_relacionado(field.queryset, request.user)
        return field

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff and request.user.eh_gerente

    def has_add_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)
