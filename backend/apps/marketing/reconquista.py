"""Reconquista de clientes por WhatsApp (automático, uma vez por dia):

- quem sumiu: N dias sem pedir → mensagem com cupom (uma vez por "sumiço");
- aniversário: no dia, com cupom (uma vez por ano);
- indicação: cada cliente tem um código; o amigo ganha desconto no 1º pedido e
  quem indicou ganha cashback quando o pedido do amigo é concluído.

Só para clientes que aceitaram receber ofertas (aceita_marketing) e se a loja
tiver o WhatsApp conectado. Roda das 10h às 20h (rotinas_diarias, de hora em hora)."""

from __future__ import annotations

import random
import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import F, Max
from django.utils import timezone

from apps.integracoes.tarefas import enfileirar


def _link(loja) -> str:
    return settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/{loja.slug}/"


def _cupom_ativo(loja, codigo: str):
    from .models import Cupom

    if not codigo:
        return None
    return Cupom.objects.ativos().filter(loja=loja, codigo__iexact=codigo.strip(), ativo=True).first()


def _enviar(integ, cliente, texto: str, chave: str) -> None:
    enfileirar("whatsapp.enviar", {"integracao_id": str(integ.id), "telefone": cliente.telefone, "mensagem": texto},
               chave=chave)


def rodar(loja, agora=None) -> dict:
    from apps.clientes.models import Cliente
    from apps.integracoes.models import Integracao
    from apps.pedidos.models import Pedido

    agora = timezone.localtime(agora or timezone.now())
    feito = {"reconquista": 0, "aniversario": 0}
    integ = Integracao.ativa(loja, "WHATSAPP", "whatsapp")
    if integ is None or not (10 <= agora.hour < 20):
        return feito
    hoje = agora.date()
    base = Cliente.objects.ativos().filter(loja=loja, aceita_marketing=True, anonimizado_em__isnull=True)

    if loja.reconquista_ativa and loja.reconquista_dias:
        limite = agora - timedelta(days=loja.reconquista_dias)
        ultimos = (Pedido.objects.filter(loja=loja, status="CONCLUIDO", cliente__in=base)
                   .values("cliente").annotate(ult=Max("concluido_em")).filter(ult__lte=limite, ult__gte=limite - timedelta(days=60)))
        cupom = _cupom_ativo(loja, loja.reconquista_cupom)
        for u in ultimos:
            c = base.filter(pk=u["cliente"]).first()
            if c is None or len(c.telefone) < 10:
                continue
            if c.reconquista_enviada_em and c.reconquista_enviada_em >= timezone.localtime(u["ult"]).date():
                continue  # já mandou depois do último pedido
            nome = c.nome.split()[0] if c.nome else ""
            texto = (f"Oi{', ' + nome if nome else ''}! Sentimos sua falta aqui na *{loja.nome}* 🧡"
                     + (f"\nUse o cupom *{cupom.codigo}* no seu próximo pedido." if cupom else "")
                     + f"\nPeça pelo cardápio: {_link(loja)}\n(Para não receber mais, responda SAIR.)")
            _enviar(integ, c, texto, f"reconquista-{c.id}-{hoje}")
            Cliente.objects.filter(pk=c.pk).update(reconquista_enviada_em=hoje)
            feito["reconquista"] += 1

    if loja.aniversario_ativo:
        cupom = _cupom_ativo(loja, loja.aniversario_cupom)
        for c in base.filter(data_nascimento__month=hoje.month, data_nascimento__day=hoje.day):
            if len(c.telefone) < 10 or (c.aniversario_enviado_em and c.aniversario_enviado_em.year == hoje.year):
                continue
            nome = c.nome.split()[0] if c.nome else ""
            texto = (f"🎉 Feliz aniversário{', ' + nome if nome else ''}! A *{loja.nome}* deseja um dia incrível."
                     + (f"\nPresente: cupom *{cupom.codigo}* para usar no seu pedido." if cupom else "")
                     + f"\n{_link(loja)}")
            _enviar(integ, c, texto, f"aniversario-{c.id}-{hoje.year}")
            Cliente.objects.filter(pk=c.pk).update(aniversario_enviado_em=hoje)
            feito["aniversario"] += 1
    return feito


# ----------------------------------------------------------------------------- indicação
def codigo_indicacao(cliente) -> str:
    """Código do cliente (cria o cupom de indicação na primeira vez)."""
    from apfood_core.enums import TipoCupom

    from apps.clientes.models import Cliente

    from .models import Cupom

    loja = cliente.loja
    if cliente.codigo_indicacao:
        Cupom.objects.filter(indicacao_de=cliente).update(valor=Decimal(loja.indicacao_desconto_centavos) / 100)
        return cliente.codigo_indicacao
    prefixo = re.sub(r"[^A-Z]", "", (cliente.nome or "AMIGO").upper().replace("Ç", "C"))[:5] or "AMIGO"
    for _ in range(20):
        codigo = f"{prefixo}{random.randint(100, 999)}"
        if not Cupom.objects.filter(loja=loja, codigo=codigo).exists():
            break
    Cupom.objects.create(loja=loja, codigo=codigo, descricao=f"Indicação de {cliente.nome}"[:160],
                         tipo=TipoCupom.VALOR_FIXO, valor=Decimal(loja.indicacao_desconto_centavos) / 100,
                         somente_primeira_compra=True, usos_por_cliente=1, indicacao_de=cliente, ativo=True)
    Cliente.objects.filter(pk=cliente.pk).update(codigo_indicacao=codigo)
    cliente.codigo_indicacao = codigo
    return codigo


def premiar_indicacao(pedido) -> None:
    """Pedido concluído com cupom de indicação: quem indicou ganha o cashback (uma vez por amigo)."""
    from apps.clientes.models import Cliente

    cupom = pedido.cupom if pedido.cupom_id else None
    if cupom is None or not cupom.indicacao_de_id or not pedido.cliente_id or not pedido.loja.indicacao_ativa:
        return
    if cupom.indicacao_de_id == pedido.cliente_id:
        return
    amigo = Cliente.objects.filter(pk=pedido.cliente_id, indicado_por__isnull=True).first()
    if amigo is None:
        return
    Cliente.objects.filter(pk=amigo.pk).update(indicado_por_id=cupom.indicacao_de_id)
    premio = pedido.loja.indicacao_premio_centavos
    if premio:
        Cliente.objects.filter(pk=cupom.indicacao_de_id).update(saldo_cashback_centavos=F("saldo_cashback_centavos") + premio)
