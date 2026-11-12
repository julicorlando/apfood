import uuid

from apfood_core.enums import PapelUsuario
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import ModeloBase, choices, max_len


class Usuario(AbstractUser):
    """Usuário do sistema. `username` é o login (único no sistema todo).

    Papéis:
      ADMIN    — tudo, incluindo cadastros, usuários e relatórios de todas as lojas
      GERENTE  — operação + relatórios + fechar/reabrir caixa de outros
      OPERADOR — PDV: lançar pedidos, abrir/fechar o PRÓPRIO caixa
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    loja = models.ForeignKey(
        "lojas.Loja",
        on_delete=models.CASCADE,
        related_name="usuarios",
        null=True,
        blank=True,  # null só para superusuário da plataforma
    )
    papel = models.CharField(
        max_length=max_len(PapelUsuario),
        choices=choices(PapelUsuario),
        default=PapelUsuario.OPERADOR,
    )
    pin_hash = models.CharField(
        max_length=128, blank=True, help_text="PIN curto para troca rápida de operador no PDV"
    )
    atualizado_em = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "usuarios"
        verbose_name = "usuário"
        ordering = ["first_name", "username"]

    def __str__(self):
        return self.get_full_name() or self.username

    # --- papéis ---
    @property
    def eh_admin(self) -> bool:
        return self.is_superuser or self.papel == PapelUsuario.ADMIN

    @property
    def eh_gerente(self) -> bool:
        return self.eh_admin or self.papel == PapelUsuario.GERENTE

    # --- PIN ---
    def definir_pin(self, pin: str) -> None:
        if not (pin.isdigit() and 4 <= len(pin) <= 6):
            raise ValueError("PIN deve ter de 4 a 6 dígitos")
        self.pin_hash = make_password(pin)

    def conferir_pin(self, pin: str) -> bool:
        return bool(self.pin_hash) and check_password(pin, self.pin_hash)


class LogAuditoria(ModeloBase):
    """Trilha de ações sensíveis: cancelamento, reabertura de caixa, ajuste de
    estoque, alteração de preço etc."""

    loja = models.ForeignKey("lojas.Loja", on_delete=models.CASCADE, related_name="+")
    usuario = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    acao = models.CharField(max_length=60, help_text='"PEDIDO_CANCELADO", "CAIXA_REABERTO"...')
    entidade = models.CharField(max_length=60)
    entidade_id = models.CharField(max_length=64, blank=True)
    dados = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "logs_auditoria"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["loja", "criado_em"]),
            models.Index(fields=["entidade", "entidade_id"]),
        ]

    def __str__(self):
        return f"{self.acao} {self.entidade}:{self.entidade_id}"
