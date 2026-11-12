"""Regras de acesso multiempresa.

Hierarquia:
    MASTER   — dono da plataforma. Vê e controla TODAS as empresas: cadastra,
               bloqueia, define limite de lojas, cria o admin de cada empresa.
    ADMIN    — administrador de UMA empresa. Acessa todas as lojas dela, cria
               lojas (até o limite do plano) e usuários da própria empresa.
    GERENTE  — só as lojas atribuídas a ele; gerencia operadores dessas lojas.
    OPERADOR — só as lojas atribuídas; usa o PDV.

Empresa bloqueada (inativa) = nenhum usuário dela acessa nada, só o MASTER.
Ninguém além do MASTER enxerga dados de outra empresa.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import PapelUsuario as P

#: Quem cada papel pode criar/editar (sempre dentro da própria empresa,
#: exceto o MASTER).
GERENCIA: dict[P, frozenset[P]] = {
    P.MASTER: frozenset(P),
    P.ADMIN: frozenset({P.ADMIN, P.GERENTE, P.OPERADOR}),
    P.GERENTE: frozenset({P.OPERADOR}),
    P.OPERADOR: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Acesso:
    """Retrato do que um usuário logado pode ver."""

    papel: P
    empresa_id: str | None = None
    lojas_ids: frozenset[str] = field(default_factory=frozenset)
    empresa_ativa: bool = True
    usuario_ativo: bool = True

    @property
    def eh_master(self) -> bool:
        return self.papel == P.MASTER

    @property
    def bloqueado(self) -> bool:
        if not self.usuario_ativo:
            return True
        return not self.eh_master and (self.empresa_id is None or not self.empresa_ativa)

    @property
    def ve_todas_as_lojas_da_empresa(self) -> bool:
        return self.papel == P.ADMIN


def validar_vinculo(papel: P, empresa_id: str | None) -> None:
    """MASTER não pertence a empresa; todos os outros pertencem a exatamente uma."""
    if papel == P.MASTER and empresa_id is not None:
        raise ValueError("usuário MASTER não pode estar vinculado a uma empresa")
    if papel != P.MASTER and empresa_id is None:
        raise ValueError(f"usuário {papel} precisa pertencer a uma empresa")


def pode_acessar_empresa(a: Acesso, empresa_id: str) -> bool:
    if a.bloqueado:
        return False
    return a.eh_master or a.empresa_id == empresa_id


def pode_acessar_loja(a: Acesso, loja_id: str, loja_empresa_id: str) -> bool:
    if not pode_acessar_empresa(a, loja_empresa_id):
        return False
    if a.eh_master or a.ve_todas_as_lojas_da_empresa:
        return True
    return loja_id in a.lojas_ids


def pode_cadastrar_empresa(a: Acesso) -> bool:
    return a.eh_master and not a.bloqueado


def pode_criar_loja(a: Acesso, empresa_id: str, lojas_atuais: int, limite: int | None) -> bool:
    """`limite=None` = ilimitado. O MASTER ignora o limite do plano."""
    if a.eh_master:
        return not a.bloqueado
    if a.papel != P.ADMIN or not pode_acessar_empresa(a, empresa_id):
        return False
    return limite is None or lojas_atuais < limite


def pode_gerenciar_usuario(a: Acesso, alvo_papel: P, alvo_empresa_id: str | None) -> bool:
    if a.bloqueado or alvo_papel not in GERENCIA[a.papel]:
        return False
    if a.eh_master:
        return True
    return alvo_empresa_id is not None and alvo_empresa_id == a.empresa_id
