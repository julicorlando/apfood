"""Base da API: permissões por papel e escopo multiempresa.

Toda view de dados de loja herda `EscopoLojaMixin`: o queryset é filtrado
pelas lojas que o usuário pode ver (`Usuario.lojas_permitidas()`), e a loja
"ativa" da requisição vem de `?loja=<uuid>`, do header `X-Loja` ou do corpo.
"""

import uuid

from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.lojas.models import Loja


class UsuarioLiberado(permissions.BasePermission):
    """Autenticado, ativo e com a empresa liberada (não bloqueada)."""

    message = "Acesso bloqueado. Fale com o administrador da plataforma."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and not u.acesso().bloqueado)


class EhGerente(UsuarioLiberado):
    message = "Requer perfil de gerente ou administrador."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.eh_gerente


class EhAdmin(UsuarioLiberado):
    message = "Requer perfil de administrador."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.eh_admin


class LeituraOuGerente(UsuarioLiberado):
    """Todos leem; só gerente+ cria/altera/exclui (cadastros)."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.method in permissions.SAFE_METHODS or request.user.eh_gerente


def loja_da_requisicao(request, obrigatoria: bool = True) -> Loja | None:
    """Resolve e valida a loja ativa da requisição."""
    loja_id = (
        request.query_params.get("loja")
        or request.headers.get("X-Loja")
        or (request.data.get("loja") if hasattr(request, "data") and isinstance(request.data, dict) else None)
    )
    permitidas = request.user.lojas_permitidas()
    if not loja_id:
        if permitidas.count() == 1:
            return permitidas.first()
        if obrigatoria:
            raise ValidationError({"loja": ["informe a loja (?loja=, header X-Loja ou campo loja)"]})
        return None
    try:
        uuid.UUID(str(loja_id))
    except ValueError as exc:
        raise ValidationError({"loja": ["loja inválida"]}) from exc
    loja = permitidas.filter(pk=loja_id).first()
    if loja is None:  # não revela se a loja existe em outra empresa
        raise PermissionDenied("loja fora do seu acesso")
    return loja


class EscopoLojaMixin:
    campo_loja = "loja"  # caminho até a loja no model (ex.: "grupo__loja")

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.filter(**{f"{self.campo_loja}__in": self.request.user.lojas_permitidas()})
        loja = loja_da_requisicao(self.request, obrigatoria=False)
        if loja is not None:
            qs = qs.filter(**{self.campo_loja: loja})
        return qs

    def get_loja(self) -> Loja:
        return loja_da_requisicao(self.request)

    def perform_create(self, serializer):
        if self.campo_loja == "loja":
            serializer.save(loja=self.get_loja())
        else:
            serializer.save()


class CadastroViewSet(EscopoLojaMixin, viewsets.ModelViewSet):
    """CRUD de cadastro da loja: todos leem, gerente+ altera. Exclusão é soft
    delete quando o model suporta (o PDV precisa saber que sumiu)."""

    permission_classes = [LeituraOuGerente]

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(qs, "ativos"):
            qs = qs.ativos()
        return qs

    def perform_destroy(self, instance):
        if hasattr(instance, "excluir"):
            instance.excluir()
        else:
            instance.delete()
