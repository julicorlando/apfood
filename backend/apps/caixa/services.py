"""Regras de caixa por operador: abertura, sangria/suprimento, despesa paga da
gaveta, resumo e fechamento (cego ou detalhado)."""

from apfood_core import caixa as regras
from apfood_core.enums import FormaPagamento, StatusTurno, TipoConferencia
from apfood_core.enums import TipoMovimentacaoCaixa as T
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.excecoes import ErroNegocio

from .models import ConferenciaCaixa, MovimentacaoCaixa, TurnoCaixa


def turno_aberto(usuario, loja=None) -> TurnoCaixa | None:
    qs = TurnoCaixa.objects.filter(usuario=usuario, status=StatusTurno.ABERTO)
    if loja is not None:
        qs = qs.filter(loja=loja)
    return qs.first()


def exigir_turno(usuario, loja) -> TurnoCaixa:
    turno = turno_aberto(usuario, loja)
    if turno is None:
        raise ErroNegocio("abra o caixa antes de receber pagamentos")
    return turno


@transaction.atomic
def abrir_turno(usuario, loja, valor_abertura_centavos: int, *, dispositivo=None, id=None) -> TurnoCaixa:
    if id and (existente := TurnoCaixa.objects.filter(pk=id).first()):
        return existente  # reenvio do PDV (idempotente)
    if not usuario.pode_acessar_loja(loja):
        raise ErroNegocio("loja fora do seu acesso")
    if valor_abertura_centavos < 0:
        raise ErroNegocio("fundo de troco não pode ser negativo")
    if turno_aberto(usuario):
        raise ErroNegocio("você já tem um caixa aberto; feche-o antes de abrir outro")
    try:
        with transaction.atomic():
            return TurnoCaixa.objects.create(
                **({"id": id} if id else {}), loja=loja, usuario=usuario, dispositivo=dispositivo,
                valor_abertura_centavos=valor_abertura_centavos,
            )
    except IntegrityError as exc:  # corrida entre dois PCs
        raise ErroNegocio("você já tem um caixa aberto") from exc


def _travar_aberto(turno) -> TurnoCaixa:
    t = TurnoCaixa.objects.select_for_update().get(pk=turno.pk)
    if t.status != StatusTurno.ABERTO:
        raise ErroNegocio("este caixa já está fechado")
    return t


@transaction.atomic
def movimentar(turno, tipo: T, valor_centavos: int, usuario, *, motivo: str = "", id=None) -> MovimentacaoCaixa:
    """Sangria ou suprimento (gaveta de dinheiro)."""
    if id and (existente := MovimentacaoCaixa.objects.filter(pk=id).first()):
        return existente
    if tipo not in (T.SANGRIA, T.SUPRIMENTO):
        raise ErroNegocio("use sangria ou suprimento")
    if valor_centavos <= 0:
        raise ErroNegocio("valor deve ser positivo", "valor_centavos")
    t = _travar_aberto(turno)
    _exigir_dono_ou_gerente(t, usuario)
    if tipo == T.SANGRIA:
        if not motivo:
            raise ErroNegocio("informe o motivo da sangria", "motivo")
        if valor_centavos > esperado(t)[FormaPagamento.DINHEIRO]:
            raise ErroNegocio("sangria maior que o dinheiro em caixa")
    return MovimentacaoCaixa.objects.create(
        **({"id": id} if id else {}), loja_id=t.loja_id, turno=t, usuario=usuario, tipo=tipo,
        forma_pagamento=FormaPagamento.DINHEIRO, valor_centavos=valor_centavos, motivo=motivo,
    )


@transaction.atomic
def registrar_venda(turno, pagamento, usuario) -> MovimentacaoCaixa:
    t = _travar_aberto(turno)
    return MovimentacaoCaixa.objects.create(
        loja_id=t.loja_id, turno=t, usuario=usuario, tipo=T.VENDA, forma_pagamento=pagamento.forma,
        valor_centavos=pagamento.valor_centavos, pagamento=pagamento,
    )


@transaction.atomic
def registrar_estorno(turno, pagamento, usuario, motivo: str) -> MovimentacaoCaixa:
    t = _travar_aberto(turno)
    return MovimentacaoCaixa.objects.create(
        loja_id=t.loja_id, turno=t, usuario=usuario, tipo=T.ESTORNO_VENDA, forma_pagamento=pagamento.forma,
        valor_centavos=pagamento.valor_centavos, motivo=motivo,
    )


@transaction.atomic
def pagar_despesa(turno, usuario, *, descricao: str, valor_centavos: int, categoria=None, id=None):
    """Despesa paga com dinheiro da gaveta (ex.: gás, motoboy avulso)."""
    from apps.financeiro.models import Despesa

    if id and (existente := Despesa.objects.filter(pk=id).first()):
        return existente
    t = _travar_aberto(turno)
    if valor_centavos <= 0:
        raise ErroNegocio("valor deve ser positivo")
    if valor_centavos > esperado(t)[FormaPagamento.DINHEIRO]:
        raise ErroNegocio("valor maior que o dinheiro em caixa")
    hoje = timezone.localdate()
    despesa = Despesa.objects.create(
        **({"id": id} if id else {}), loja_id=t.loja_id, categoria=categoria, descricao=descricao,
        valor_centavos=valor_centavos, data_competencia=hoje, data_pagamento=hoje,
        forma_pagamento=FormaPagamento.DINHEIRO, turno=t, usuario=usuario,
    )
    MovimentacaoCaixa.objects.create(
        loja_id=t.loja_id, turno=t, usuario=usuario, tipo=T.DESPESA, forma_pagamento=FormaPagamento.DINHEIRO,
        valor_centavos=valor_centavos, motivo=descricao, despesa=despesa,
    )
    return despesa


def esperado(turno) -> dict:
    movs = [
        regras.Movimento(T(m.tipo), FormaPagamento(m.forma_pagamento), m.valor_centavos)
        for m in turno.movimentacoes.all()
    ]
    return regras.calcular_esperado(turno.valor_abertura_centavos, movs)


def resumo(turno, *, mostrar_esperado: bool = True) -> dict:
    """Resumo para a tela de caixa. Na conferência CEGA o operador não vê o
    esperado até fechar (`mostrar_esperado=False`)."""
    movs = list(turno.movimentacoes.all())
    por_tipo: dict[str, int] = {}
    for m in movs:
        por_tipo[m.tipo] = por_tipo.get(m.tipo, 0) + m.valor_centavos
    dados = {
        "turno": str(turno.id),
        "status": turno.status,
        "operador": str(turno.usuario),
        "aberto_em": turno.aberto_em.isoformat(),
        "valor_abertura_centavos": turno.valor_abertura_centavos,
        "totais_por_tipo": por_tipo,
        "quantidade_vendas": sum(1 for m in movs if m.tipo == T.VENDA),
    }
    if mostrar_esperado:
        dados["esperado"] = {f.value: v for f, v in esperado(turno).items()}
    return dados


def _exigir_dono_ou_gerente(turno, usuario):
    if turno.usuario_id != usuario.pk and not usuario.eh_gerente:
        raise ErroNegocio("só o operador do caixa ou um gerente pode fazer isso")


@transaction.atomic
def fechar_turno(
    turno, usuario, informado: dict, *, tipo_conferencia: TipoConferencia = TipoConferencia.CEGA,
    observacao: str = "",
) -> regras.ResultadoConferencia:
    """`informado` = {"DINHEIRO": 15000, "PIX": 3000, ...} contado pelo operador."""
    t = _travar_aberto(turno)
    _exigir_dono_ou_gerente(t, usuario)
    try:
        informado_enum = {FormaPagamento(k): int(v) for k, v in informado.items()}
    except (ValueError, TypeError) as exc:
        raise ErroNegocio("valores informados inválidos") from exc
    resultado = regras.conferir(esperado(t), informado_enum)
    ConferenciaCaixa.objects.bulk_create([
        ConferenciaCaixa(
            turno=t, forma_pagamento=l.forma, valor_esperado_centavos=l.esperado_centavos,
            valor_informado_centavos=l.informado_centavos, diferenca_centavos=l.diferenca_centavos,
        )
        for l in resultado.linhas
    ])
    t.status = StatusTurno.FECHADO
    t.fechado_em = timezone.now()
    t.fechado_por = usuario
    t.tipo_conferencia = tipo_conferencia
    t.total_esperado_centavos = resultado.total_esperado_centavos
    t.total_informado_centavos = resultado.total_informado_centavos
    t.diferenca_centavos = resultado.diferenca_centavos
    t.observacao_fechamento = observacao
    t.save()
    return resultado
