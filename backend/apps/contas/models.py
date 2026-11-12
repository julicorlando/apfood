import uuid

from apfood_core import permissoes
from apfood_core.enums import PapelUsuario
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.db.models import Q

from apps.core.models import ModeloBase, choices, max_len


class UsuarioManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra):
        """`manage.py createsuperuser` cria um MASTER (sem empresa)."""
        extra.setdefault("papel", PapelUsuario.MASTER)
        extra.setdefault("empresa", None)
        return super().create_superuser(username, email, password, **extra)


class Usuario(AbstractUser):
    """Usuário do sistema. `username` é o login (único na plataforma toda).

    Papéis (regras em `apfood_core.permissoes`):
      MASTER   — plataforma: todas as empresas; sem empresa vinculada
      ADMIN    — todas as lojas da SUA empresa
      GERENTE  — só as lojas em `lojas`; relatórios, fechar caixa de outros
      OPERADOR — só as lojas em `lojas`; PDV e o PRÓPRIO caixa
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    empresa = models.ForeignKey(
        "lojas.Empresa",
        on_delete=models.PROTECT,
        related_name="usuarios",
        null=True,
        blank=True,  # null só para o MASTER
    )
    lojas = models.ManyToManyField(
        "lojas.Loja",
        related_name="usuarios",
        blank=True,
        help_text="Lojas que GERENTE/OPERADOR acessam. ADMIN acessa todas da empresa.",
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

    objects = UsuarioManager()

    class Meta:
        db_table = "usuarios"
        verbose_name = "usuário"
        ordering = ["first_name", "username"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(papel=PapelUsuario.MASTER) & Q(empresa__isnull=True))
                | (~Q(papel=PapelUsuario.MASTER) & Q(empresa__isnull=False)),
                name="usuario_vinculo_empresa",
            ),
        ]

    def __str__(self):
        return self.get_full_name() or self.username

    def clean(self):
        super().clean()
        try:
            permissoes.validar_vinculo(PapelUsuario(self.papel), self.empresa_id)
        except ValueError as exc:
            raise ValidationError({"empresa": str(exc)}) from exc

    def save(self, *args, **kwargs):
        # MASTER é superusuário do Django; ADMIN/GERENTE entram na retaguarda.
        self.is_superuser = self.papel == PapelUsuario.MASTER
        self.is_staff = self.papel != PapelUsuario.OPERADOR
        super().save(*args, **kwargs)

    # --- papéis e escopo ---
    @property
    def eh_master(self) -> bool:
        return self.papel == PapelUsuario.MASTER

    @property
    def eh_admin(self) -> bool:
        return self.eh_master or self.papel == PapelUsuario.ADMIN

    @property
    def eh_gerente(self) -> bool:
        return self.eh_admin or self.papel == PapelUsuario.GERENTE

    def acesso(self) -> permissoes.Acesso:
        """Retrato das permissões, usado pela API, pelo admin e pelo WebSocket."""
        lojas_ids = (
            frozenset(str(i) for i in self.lojas.values_list("id", flat=True))
            if self.papel in (PapelUsuario.GERENTE, PapelUsuario.OPERADOR)
            else frozenset()
        )
        return permissoes.Acesso(
            papel=PapelUsuario(self.papel),
            empresa_id=str(self.empresa_id) if self.empresa_id else None,
            lojas_ids=lojas_ids,
            empresa_ativa=bool(self.empresa and self.empresa.liberada),
            usuario_ativo=self.is_active,
        )

    def lojas_permitidas(self):
        """QuerySet das lojas que este usuário pode ver."""
        from apps.lojas.models import Loja

        a = self.acesso()
        if a.bloqueado:
            return Loja.objects.none()
        if a.eh_master:
            return Loja.objects.all()
        qs = Loja.objects.filter(empresa_id=self.empresa_id)
        if not a.ve_todas_as_lojas_da_empresa:
            qs = qs.filter(id__in=a.lojas_ids)
        return qs

    def pode_acessar_loja(self, loja) -> bool:
        return permissoes.pode_acessar_loja(self.acesso(), str(loja.id), str(loja.empresa_id))

    # --- PIN ---
    def definir_pin(self, pin: str) -> None:
        if not (pin.isdigit() and 4 <= len(pin) <= 6):
            raise ValueError("PIN deve ter de 4 a 6 dígitos")
        self.pin_hash = make_password(pin)

    def conferir_pin(self, pin: str) -> bool:
        return bool(self.pin_hash) and check_password(pin, self.pin_hash)


class LogAuditoria(ModeloBase):
    """Trilha de ações sensíveis: cancelamento, reabertura de caixa, ajuste de
    estoque, alteração de preço, bloqueio de empresa etc."""

    empresa = models.ForeignKey(
        "lojas.Empresa", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    loja = models.ForeignKey(
        "lojas.Loja", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    usuario = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    acao = models.CharField(max_length=60, help_text='"PEDIDO_CANCELADO", "EMPRESA_BLOQUEADA"...')
    entidade = models.CharField(max_length=60)
    entidade_id = models.CharField(max_length=64, blank=True)
    dados = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "logs_auditoria"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "criado_em"]),
            models.Index(fields=["loja", "criado_em"]),
            models.Index(fields=["entidade", "entidade_id"]),
        ]

    def __str__(self):
        return f"{self.acao} {self.entidade}:{self.entidade_id}"


@receiver(m2m_changed, sender=Usuario.lojas.through)
def _lojas_da_mesma_empresa(sender, instance, action, pk_set, **kwargs):
    """Impede vincular um usuário a loja de outra empresa (vale para admin, API e shell)."""
    if action != "pre_add" or not pk_set:
        return
    from apps.lojas.models import Loja

    if instance.empresa_id is None:
        raise ValidationError("usuário sem empresa não pode ter lojas")
    fora = Loja.objects.filter(pk__in=pk_set).exclude(empresa_id=instance.empresa_id)
    if fora.exists():
        raise ValidationError("loja de outra empresa: " + ", ".join(map(str, fora)))
