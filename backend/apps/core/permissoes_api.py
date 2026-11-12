"""Permissões da API por papel. Módulo sem dependências de views/viewsets:
o DRF importa a permissão padrão (settings) durante a própria inicialização."""

from rest_framework import permissions


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
