"""E-mails da cobrança da assinatura (plataforma → empresa).

Vai para o e-mail da empresa e dos ADMIN dela. Sem EMAIL_URL configurado
o Django usa o backend de console (só aparece no log). Nunca derruba a
rotina: falha de envio fica no log.
"""

import logging

from apfood_core.dinheiro import formatar
from django.conf import settings
from django.core.mail import send_mail

log = logging.getLogger(__name__)


def destinatarios(empresa) -> list[str]:
    from apfood_core.enums import PapelUsuario

    from apps.contas.models import Usuario

    emails = {empresa.email} if empresa.email else set()
    emails |= set(
        Usuario.objects.filter(empresa=empresa, papel=PapelUsuario.ADMIN, is_active=True)
        .exclude(email="").values_list("email", flat=True)
    )
    return sorted(e for e in emails if e)


def _painel() -> str:
    return settings.APFOOD["URL_PUBLICA"].rstrip("/") + "/painel/#/empresa"


def _enviar(empresa, assunto: str, corpo: str) -> bool:
    para = destinatarios(empresa)
    if not para:
        log.warning("empresa %s sem e-mail para aviso de cobrança: %s", empresa.pk, assunto)
        return False
    rodape = f"\n\nAcompanhe em {_painel()}\n\n— Equipe ApFood"
    try:
        send_mail(f"ApFood — {assunto}", corpo + rodape, None, para)
        return True
    except Exception:  # noqa: BLE001
        log.exception("falha ao enviar aviso de cobrança para %s", empresa.pk)
        return False


def _linha_pagamento(fatura) -> str:
    if fatura.link_pagamento:
        return f"Pague pelo Pix: {fatura.link_pagamento}"
    return "O link de pagamento aparece no painel, em Minha empresa."


def _fatura(fatura) -> str:
    return (f"Fatura {fatura.competencia:%m/%Y}" + (f" — plano {fatura.plano}" if fatura.plano_id else "")
            + f"\nValor: {formatar(fatura.valor_centavos)}\nVencimento: {fatura.vencimento:%d/%m/%Y}")


def nova_fatura(f):
    return _enviar(f.empresa, f"fatura {f.competencia:%m/%Y}",
                   f"Olá, {f.empresa.nome}!\n\nSua fatura do ApFood está disponível.\n\n{_fatura(f)}\n\n{_linha_pagamento(f)}")


def lembrete(f):
    return _enviar(f.empresa, f"fatura vence em {f.vencimento:%d/%m}",
                   f"Olá, {f.empresa.nome}!\n\nLembrete: sua fatura vence em breve.\n\n{_fatura(f)}\n\n{_linha_pagamento(f)}")


def vencida(f, dias_tolerancia: int):
    return _enviar(f.empresa, "fatura vencida",
                   f"Olá, {f.empresa.nome}!\n\nNão identificamos o pagamento da fatura abaixo.\n\n{_fatura(f)}\n\n"
                   f"{_linha_pagamento(f)}\n\nSem o pagamento, o acesso é suspenso {dias_tolerancia} dias "
                   "após o vencimento. Se já pagou, desconsidere.")


def bloqueada(f):
    return _enviar(f.empresa, "acesso suspenso",
                   f"Olá, {f.empresa.nome}!\n\nO acesso ao ApFood foi suspenso por falta de pagamento.\n\n{_fatura(f)}\n\n"
                   f"{_linha_pagamento(f)}\n\nO acesso volta sozinho assim que o pagamento for confirmado. "
                   "Seus dados continuam guardados.")


def pagamento_confirmado(f):
    return _enviar(f.empresa, "pagamento confirmado",
                   f"Olá, {f.empresa.nome}!\n\nRecebemos o pagamento. Obrigado!\n\n{_fatura(f)}")


def fim_do_teste(empresa, dias: int):
    plano = f"o plano {empresa.plano}" if empresa.plano_id else "um plano"
    valor = f" ({formatar(empresa.plano.preco_mensal_centavos)}/mês)" if empresa.plano_id else ""
    return _enviar(empresa, f"seu teste grátis termina em {dias} dias",
                   f"Olá, {empresa.nome}!\n\nSeu período de teste termina em {empresa.trial_ate:%d/%m/%Y}. "
                   f"Depois disso a cobrança começa com {plano}{valor}. Você pode trocar de plano no painel, "
                   "em Minha empresa.")
