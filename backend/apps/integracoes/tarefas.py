"""Fila de tarefas: enfileirar (após o commit) e executar."""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Tarefa

log = logging.getLogger(__name__)
EXECUTORES: dict = {}


def executor(tipo: str):
    """Decorator: registra a função que executa um tipo de tarefa."""

    def registrar(fn):
        EXECUTORES[tipo] = fn
        return fn

    return registrar


def enfileirar(tipo: str, payload: dict, *, chave: str = "", atraso_s: int = 0) -> None:
    def criar():
        try:
            with transaction.atomic():
                Tarefa.objects.create(tipo=tipo, payload=payload, chave=chave,
                                      executar_em=timezone.now() + timedelta(seconds=atraso_s))
        except IntegrityError:
            pass  # já existe uma tarefa pendente com a mesma chave

    transaction.on_commit(criar)


def executar(tarefa: Tarefa) -> bool:
    _carregar_executores()
    fn = EXECUTORES.get(tarefa.tipo)
    tarefa.tentativas += 1
    try:
        if fn is None:
            raise RuntimeError(f"tipo de tarefa desconhecido: {tarefa.tipo}")
        with transaction.atomic():
            fn(**tarefa.payload)
        tarefa.status, tarefa.erro, tarefa.concluida_em = Tarefa.CONCLUIDA, "", timezone.now()
        ok = True
    except Exception as exc:  # noqa: BLE001
        log.warning("tarefa %s falhou (%s/%s): %s", tarefa.tipo, tarefa.tentativas, tarefa.max_tentativas, exc)
        tarefa.erro = str(exc)[:2000]
        if tarefa.tentativas >= tarefa.max_tentativas:
            tarefa.status = Tarefa.FALHOU
            if tarefa.tipo == "marketing.campanha":
                from apps.marketing.campanhas import falhou

                falhou(tarefa.payload.get("envio_id", ""), str(exc))
        else:
            tarefa.status = Tarefa.PENDENTE
            tarefa.executar_em = timezone.now() + timedelta(seconds=30 * 2 ** (tarefa.tentativas - 1))
        ok = False
    tarefa.save()
    return ok


def processar_lote(limite: int = 20) -> int:
    with transaction.atomic():
        ids = list(
            Tarefa.objects.select_for_update(skip_locked=True)
            .filter(status=Tarefa.PENDENTE, executar_em__lte=timezone.now())
            .values_list("id", flat=True)[:limite]
        )
        Tarefa.objects.filter(id__in=ids).update(status=Tarefa.EXECUTANDO)
    for t in Tarefa.objects.filter(id__in=ids):
        executar(t)
    return len(ids)


def _carregar_executores():
    """Importa os módulos que registram executores (uma vez)."""
    if EXECUTORES.get("_carregado"):
        return
    from apps.fiscal import services as _f  # noqa: F401
    from apps.integracoes import notificacoes as _n  # noqa: F401
    from apps.integracoes.provedores import ifood as _i  # noqa: F401
    from apps.marketing import campanhas as _m  # noqa: F401
    from apps.plataforma import cobranca as _c  # noqa: F401

    EXECUTORES["_carregado"] = True
