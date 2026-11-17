"""Carrinho abandonado: quem montou o pedido no cardápio, informou o telefone e não
finalizou recebe UM lembrete pelo WhatsApp depois de `carrinho_minutos` (no máximo um por
dia por telefone, só das 9h às 22h e só se a loja tiver o WhatsApp conectado)."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.integracoes.tarefas import enfileirar, executor

from .models import CarrinhoAberto


def _tel(t: str) -> str:
    return "".join(c for c in (t or "") if c.isdigit())[:13]


def registrar(loja, *, telefone: str, nome: str = "", itens=None, total=0) -> CarrinhoAberto | None:
    tel = _tel(telefone)
    if not loja.carrinho_ativo or len(tel) < 10:
        return None
    itens = [str(x)[:80] for x in (itens or []) if str(x).strip()][:15]
    if not itens:
        return None
    try:
        total = max(0, int(total))
    except (TypeError, ValueError):
        total = 0
    c, _ = CarrinhoAberto.objects.update_or_create(
        loja=loja, telefone=tel,
        defaults={"nome": (nome or "").strip()[:120], "itens": itens, "total_centavos": total, "convertido_em": None})
    enfileirar("carrinho.lembrar", {"carrinho_id": str(c.id), "versao": c.atualizado_em.isoformat()},
               chave=f"carrinho-{c.id}-{int(c.atualizado_em.timestamp())}", atraso_s=max(5, loja.carrinho_minutos) * 60)
    return c


def mensagem(c: CarrinhoAberto) -> str:
    loja = c.loja
    link = settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/{loja.slug}/"
    nome = c.nome.split(" ")[0] if c.nome else ""
    itens = ", ".join(c.itens[:4]) + ("…" if len(c.itens) > 4 else "")
    texto = (f"Oi{' ' + nome if nome else ''}! 😊 Seu pedido na *{loja.nome}* ficou no carrinho: {itens}."
             f"\nÉ só finalizar por aqui: {link}")
    if loja.carrinho_cupom:
        texto += f"\nUse o cupom *{loja.carrinho_cupom}* para ganhar um desconto."
    return texto


@executor("carrinho.lembrar")
def lembrar(carrinho_id: str, versao: str = "", _agora=None):
    from apps.integracoes.models import Integracao
    from apps.pedidos.models import Pedido

    c = CarrinhoAberto.objects.select_related("loja").filter(pk=carrinho_id).first()
    if c is None or c.convertido_em or not c.loja.carrinho_ativo:
        return
    if versao and c.atualizado_em.isoformat() != versao:
        return  # o cliente mexeu no carrinho depois: vale o lembrete mais novo
    agora = timezone.localtime(_agora or timezone.now())
    if c.avisado_em and agora - c.avisado_em < timedelta(hours=24):
        return
    if not (9 <= agora.hour < 22):
        return
    if Pedido.objects.filter(loja=c.loja, telefone_cliente=c.telefone, criado_em__gte=c.criado_em - timedelta(minutes=5)).exists():
        CarrinhoAberto.objects.filter(pk=c.pk).update(convertido_em=timezone.now())
        return
    integ = Integracao.ativa(c.loja, "WHATSAPP", "whatsapp")
    if integ is None:
        return
    enfileirar("whatsapp.enviar", {"integracao_id": str(integ.id), "telefone": c.telefone, "mensagem": mensagem(c)},
               chave=f"carrinho-msg-{c.id}-{agora:%Y%m%d}")
    CarrinhoAberto.objects.filter(pk=c.pk).update(avisado_em=timezone.now())
