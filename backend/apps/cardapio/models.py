from decimal import Decimal

from apfood_core.enums import TipoProduto, UnidadeMedida
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.core.models import DaLoja, ModeloSincronizavel, choices, max_len

QTD = {"max_digits": 12, "decimal_places": 3}


class Categoria(DaLoja, ModeloSincronizavel):
    nome = models.CharField(max_length=80)
    descricao = models.CharField(max_length=255, blank=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    ativa = models.BooleanField(default=True)

    class Meta:
        db_table = "categorias"
        ordering = ["ordem", "nome"]
        indexes = [models.Index(fields=["loja", "atualizado_em"])]

    def __str__(self):
        return self.nome


class Produto(DaLoja, ModeloSincronizavel):
    """Produtos vendáveis E insumos na mesma tabela (campo `tipo`), o que
    simplifica estoque e ficha técnica.

    Estoque (opcional por produto):
      • controla_estoque=True → o próprio produto tem saldo e é baixado na venda
        (lata de refrigerante, embalagem, insumo).
      • baixar_insumos=True  → na venda, baixa os insumos da ficha técnica
        (X-Burguer baixa pão, carne, queijo).
      • ambos False          → não mexe em estoque (lanche artesanal simples).
    """

    categoria = models.ForeignKey(
        Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name="produtos"
    )
    tipo = models.CharField(
        max_length=max_len(TipoProduto), choices=choices(TipoProduto), default=TipoProduto.VENDA
    )
    nome = models.CharField(max_length=120)
    descricao = models.TextField(blank=True)
    imagem = models.ImageField(upload_to="produtos/", blank=True)
    codigo = models.CharField(max_length=40, blank=True, help_text="SKU / código de barras")
    preco_centavos = models.PositiveIntegerField(default=0)
    custo_centavos = models.PositiveIntegerField(null=True, blank=True)
    ativo = models.BooleanField(default=True)
    disponivel_online = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    # Estoque
    controla_estoque = models.BooleanField(default=False)
    baixar_insumos = models.BooleanField(default=False)
    unidade = models.CharField(
        max_length=max_len(UnidadeMedida), choices=choices(UnidadeMedida), default=UnidadeMedida.UN
    )
    estoque_atual = models.DecimalField(default=Decimal("0"), **QTD)
    estoque_minimo = models.DecimalField(null=True, blank=True, **QTD)

    grupos_adicionais = models.ManyToManyField(
        "GrupoAdicional", through="ProdutoGrupoAdicional", related_name="produtos", blank=True
    )

    class Meta:
        db_table = "produtos"
        ordering = ["ordem", "nome"]
        indexes = [
            models.Index(fields=["loja", "tipo", "ativo"]),
            models.Index(fields=["loja", "atualizado_em"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["loja", "codigo"], condition=~Q(codigo=""), name="produto_codigo_unico"
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def abaixo_do_minimo(self) -> bool:
        return (
            self.controla_estoque
            and self.estoque_minimo is not None
            and self.estoque_atual <= self.estoque_minimo
        )


class FichaTecnicaItem(models.Model):
    """Quanto de cada insumo um produto consome por unidade vendida."""

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="ficha_tecnica")
    insumo = models.ForeignKey(Produto, on_delete=models.PROTECT, related_name="usado_em_fichas")
    quantidade = models.DecimalField(
        validators=[MinValueValidator(Decimal("0.001"))], help_text="na unidade do insumo", **QTD
    )

    class Meta:
        db_table = "fichas_tecnicas"
        constraints = [
            models.UniqueConstraint(fields=["produto", "insumo"], name="ficha_insumo_unico"),
            models.CheckConstraint(condition=~Q(produto=F("insumo")), name="ficha_nao_recursiva"),
            models.CheckConstraint(condition=Q(quantidade__gt=0), name="ficha_quantidade_positiva"),
        ]

    def __str__(self):
        return f"{self.produto} ← {self.quantidade} {self.insumo}"


class GrupoAdicional(DaLoja, ModeloSincronizavel):
    """Ex.: "Ponto da carne" (mín 1, máx 1), "Adicionais" (mín 0, máx 10)."""

    nome = models.CharField(max_length=80)
    min_selecao = models.PositiveSmallIntegerField(default=0)
    max_selecao = models.PositiveSmallIntegerField(default=1)
    ordem = models.PositiveSmallIntegerField(default=0)
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "grupos_adicionais"
        verbose_name_plural = "grupos de adicionais"
        ordering = ["ordem", "nome"]
        indexes = [models.Index(fields=["loja", "atualizado_em"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(max_selecao__gte=F("min_selecao")), name="grupo_min_max"
            ),
        ]

    def __str__(self):
        return self.nome


class ProdutoGrupoAdicional(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    grupo = models.ForeignKey(GrupoAdicional, on_delete=models.CASCADE)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "produtos_grupos_adicionais"
        ordering = ["ordem"]
        constraints = [
            models.UniqueConstraint(fields=["produto", "grupo"], name="produto_grupo_unico")
        ]


class Adicional(ModeloSincronizavel):
    grupo = models.ForeignKey(GrupoAdicional, on_delete=models.CASCADE, related_name="adicionais")
    nome = models.CharField(max_length=80)
    preco_centavos = models.PositiveIntegerField(default=0)
    max_por_item = models.PositiveSmallIntegerField(default=1, help_text="ex.: bacon extra até 3x")
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    # Opcional: adicional que consome insumo ("Bacon extra" baixa 0,030 kg de bacon)
    insumo = models.ForeignKey(
        Produto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adicionais_que_consomem",
        limit_choices_to={"tipo": TipoProduto.INSUMO},
    )
    quantidade_insumo = models.DecimalField(null=True, blank=True, **QTD)

    class Meta:
        db_table = "adicionais"
        verbose_name_plural = "adicionais"
        ordering = ["ordem", "nome"]
        constraints = [
            models.CheckConstraint(
                condition=Q(insumo__isnull=True) | Q(quantidade_insumo__gt=0),
                name="adicional_insumo_com_quantidade",
            ),
        ]

    def __str__(self):
        return self.nome
