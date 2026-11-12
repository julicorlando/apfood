"""Base da API: permissões por papel e escopo multiempresa.

Toda view de dados de loja herda `EscopoLojaMixin`: o queryset é filtrado
pelas lojas que o usuário pode ver (`Usuario.lojas_permitidas()`), e a loja
"ativa" da requisição vem de `?loja=<uuid>`, do header `X-Loja` ou do corpo.
"""

import uuid

from rest_framework import permissions, viewsets  # noqa: F401
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.lojas.models import Loja

from .permissoes_api import EhAdmin, EhGerente, LeituraOuGerente, UsuarioLiberado  # noqa: F401


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
