"""Regras de pedido: criação, mudança de status e pagamentos.

Preços SEMPRE vêm do banco — nunca do cliente (cardápio online ou PDV). O PDV
pode enviar o `id` (UUID) gerado offline: reenviar o mesmo pedido devolve o
existente em vez de duplicar.
"""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from apfood_core import pedido_status as fluxo
from apfood_core import totais
from apfood_core.dinheiro import calcular_troco
from apfood_core.enums import (
    CanalVenda,
    FormaPagamento,
    MomentoBaixaEstoque,
    RegraPrecoSabores,
    StatusPagamento,
    StatusPedido,
    TipoAtendimento,
)
from apfood_core.precos import Cupom as RegraCupom
from apfood_core.precos import CupomInvalido, calcular_desconto_cupom, preco_sabores
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.caixa import services as caixa
from apps.cardapio.models import Adicional, Produto, ProdutoGrupoAdicional, ProdutoVariacao
from apps.core.excecoes import ErroNegocio
from apps.estoque import services as estoque
from apps.lojas.models import SequenciaPedido
from apps.realtime import eventos

from .models import HistoricoStatusPedido, ItemPedido, ItemPedidoAdicional, ItemPedidoSabor, Pagamento, Pedido

S = StatusPedido
FORMAS_SEM_CAIXA = {FormaPagamento.MARKETPLACE}


# =============================================================================
# Entrada
# =============================================================================
@dataclass
class AdicionalIn:
    adicional_id: str
    quantidade: int = 1


@dataclass
class ItemIn:
    produto_id: str
    quantidade: int = 1
    variacao_id: str | None = None
    sabores: list[str] = field(default_factory=list)  # ids de produtos (inclui o principal)
    adicionais: list[AdicionalIn] = field(default_factory=list)
    observacao: str = ""


@dataclass
class PedidoIn:
    canal: CanalVenda
    tipo_atendimento: TipoAtendimento
    itens: list[ItemIn]
    id: str | None = None
    origem_contato: str = ""
    nome_cliente: str = ""
    telefone_cliente: str = ""
    mesa: str = ""
    senha: str = ""
    comanda: object = None
    endereco: dict | None = None  # logradouro, numero, complemento, bairro, cidade, cep, referencia, latitude, longitude
    taxa_entrega_centavos: int | None = None  # só PDV pode informar manualmente
    desconto_centavos: int = 0
    acrescimo_centavos: int = 0
    cupom_codigo: str = ""
    troco_para_centavos: int | None = None
    forma_pagamento_prevista: str = ""  # online: "pagar na entrega com..."
    observacao: str = ""
    cpf_nota: str = ""
    entregador_id: str | None = None
    marketplace: str = ""
    id_externo: str = ""
    codigo_externo: str = ""
    codigo_local: str = ""
    dispositivo: object = None


# =============================================================================
# Montagem dos itens
# =============================================================================
def _montar_itens(loja, dados: PedidoIn):
    """Valida e precifica os itens. Retorna (linhas, itens_core)."""
    if not dados.itens:
        raise ErroNegocio("o pedido não tem itens", "itens")
    online = dados.canal == CanalVenda.ONLINE
    ids = {i.produto_id for i in dados.itens} | {s for i in dados.itens for s in i.sabores}
    produtos = {
        str(p.id): p
        for p in Produto.objects.ativos().filter(loja=loja, id__in=ids, ativo=True).select_related("categoria")
    }
    agora = timezone.now()

    def produto(pid):
        p = produtos.get(str(pid))
        if p is None:
            raise ErroNegocio("produto indisponível ou inexistente", "itens")
        if p.pausado and (p.pausado_ate is None or p.pausado_ate > agora):
            raise ErroNegocio(f"'{p.nome}' está esgotado no momento", "itens")
        if online and not p.disponivel_online:
            raise ErroNegocio(f"'{p.nome}' não está disponível online", "itens")
        return p

    linhas, itens_core = [], []
    for it in dados.itens:
        if it.quantidade <= 0:
            raise ErroNegocio("quantidade deve ser positiva", "itens")
        p = produto(it.produto_id)

        variacao = None
        if it.variacao_id:
            variacao = ProdutoVariacao.objects.ativos().filter(pk=it.variacao_id, produto=p, ativo=True).first()
            if variacao is None:
                raise ErroNegocio(f"tamanho inválido para '{p.nome}'", "itens")
        elif p.variacoes.ativos().filter(ativo=True).exists():
            raise ErroNegocio(f"escolha o tamanho de '{p.nome}'", "itens")

        # --- sabores (pizza meio a meio) ---
        sabores = []
        preco_unit = variacao.preco_centavos if variacao else p.preco_centavos
        if it.sabores and len(it.sabores) > 1:
            cat = p.categoria
            if cat is None or len(it.sabores) > cat.max_sabores:
                raise ErroNegocio(f"'{p.nome}' aceita no máximo {cat.max_sabores if cat else 1} sabor(es)", "itens")
            for sid in it.sabores:
                sp = produto(sid)
                if sp.categoria_id != p.categoria_id:
                    raise ErroNegocio("sabores devem ser da mesma categoria", "itens")
                if variacao:
                    sv = sp.variacoes.ativos().filter(nome=variacao.nome, ativo=True).first()
                    if sv is None:
                        raise ErroNegocio(f"'{sp.nome}' não tem o tamanho {variacao.nome}", "itens")
                    preco = sv.preco_centavos
                else:
                    preco = sp.preco_centavos
                sabores.append((sp, preco))
            preco_unit = preco_sabores([pr for _, pr in sabores], RegraPrecoSabores(cat.regra_preco_sabores))

        # --- adicionais ---
        grupos = {
            str(g.grupo_id): g.grupo
            for g in ProdutoGrupoAdicional.objects.filter(produto=p, grupo__ativo=True, grupo__excluido_em__isnull=True)
            .select_related("grupo")
        }
        escolhidos, adicionais = [], []
        if it.adicionais:
            mapa = {
                str(a.id): a
                for a in Adicional.objects.ativos().filter(
                    id__in=[a.adicional_id for a in it.adicionais], ativo=True, grupo_id__in=list(grupos)
                )
            }
            for a_in in it.adicionais:
                a = mapa.get(str(a_in.adicional_id))
                if a is None:
                    raise ErroNegocio(f"adicional inválido para '{p.nome}'", "itens")
                if not 1 <= a_in.quantidade <= a.max_por_item:
                    raise ErroNegocio(f"'{a.nome}': até {a.max_por_item} por item", "itens")
                adicionais.append((a, a_in.quantidade))
                escolhidos.append(totais.AdicionalEscolhido(str(a.grupo_id), str(a.id), a.preco_centavos, a_in.quantidade))
        regras = [totais.RegraGrupo(gid, g.nome, g.min_selecao, g.max_selecao) for gid, g in grupos.items()]
        if erros := totais.validar_adicionais(regras, escolhidos):
            raise ErroNegocio(f"{p.nome}: " + "; ".join(erros), "itens")

        item_core = totais.Item(preco_unit, it.quantidade, escolhidos)
        itens_core.append(item_core)
        linhas.append({
            "produto": p, "variacao": variacao, "sabores": sabores, "adicionais": adicionais,
            "quantidade": it.quantidade, "preco_unit": preco_unit, "observacao": it.observacao[:255],
            "total_adicionais": item_core.adicionais_por_unidade_centavos, "total": item_core.total_centavos,
            "nome": p.nome if len(sabores) < 2 else " / ".join(f"1/{len(sabores)} {sp.nome}" for sp, _ in sabores),
        })
    return linhas, itens_core


def _cupom(loja, codigo: str, subtotal: int, taxa: int, dados: PedidoIn):
    from apps.marketing.models import Cupom, UsoCupom

    c = Cupom.objects.ativos().filter(loja=loja, codigo=codigo.strip().upper()).first()
    if c is None:
        raise ErroNegocio("cupom não encontrado", "cupom_codigo")
    if c.canais and dados.canal not in c.canais:
        raise ErroNegocio("cupom não vale para este canal", "cupom_codigo")
    tel = "".join(ch for ch in dados.telefone_cliente if ch.isdigit())
    if c.usos_por_cliente or c.somente_primeira_compra:
        if not tel:
            raise ErroNegocio("informe o telefone para usar este cupom", "cupom_codigo")
        if c.usos_por_cliente and UsoCupom.objects.filter(cupom=c, telefone=tel).count() >= c.usos_por_cliente:
            raise ErroNegocio("você já usou este cupom", "cupom_codigo")
        if c.somente_primeira_compra and Pedido.objects.filter(
            loja=loja, telefone_cliente=tel).exclude(status__in=[S.CANCELADO, S.RECUSADO]).exists():
            raise ErroNegocio("cupom válido só na primeira compra", "cupom_codigo")
    regra = RegraCupom(c.tipo, c.valor, c.pedido_minimo_centavos, c.desconto_maximo_centavos,
                       c.valido_de, c.valido_ate, c.usos_maximos, c.usos, c.ativo)
    try:
        return c, calcular_desconto_cupom(regra, subtotal, taxa, timezone.now())
    except CupomInvalido as exc:
        raise ErroNegocio(str(exc), "cupom_codigo") from exc


# =============================================================================
# Criação
# =============================================================================
@transaction.atomic
def criar_pedido(loja, dados: PedidoIn, usuario=None) -> Pedido:
    if dados.id:
        dados.id = uuid.UUID(str(dados.id))
    if dados.id and (existente := Pedido.objects.filter(pk=dados.id).first()):
        if existente.loja_id != loja.id:
            raise ErroNegocio("id de pedido já usado")
        return existente
    if dados.marketplace and dados.id_externo and (
        existente := Pedido.objects.filter(loja=loja, marketplace=dados.marketplace, id_externo=dados.id_externo).first()
    ):
        return existente

    online = dados.canal == CanalVenda.ONLINE
    if online and not (loja.aberta_para_pedidos and loja.empresa.liberada and loja.ativa):
        raise ErroNegocio("a loja não está recebendo pedidos agora")
    if online:
        from apfood_core.horarios import aberta_em

        if not aberta_em(loja.horarios, timezone.localtime()):
            raise ErroNegocio("a loja está fora do horário de funcionamento")
    if dados.comanda is not None and dados.comanda.status != "ABERTA":
        raise ErroNegocio("comanda não está aberta")

    linhas, itens_core = _montar_itens(loja, dados)
    subtotal = sum(l["total"] for l in linhas)

    # --- entrega ---
    zona, taxa = None, 0
    end = dados.endereco or {}
    if dados.tipo_atendimento == TipoAtendimento.ENTREGA and dados.canal != CanalVenda.MARKETPLACE:
        if not end.get("logradouro") or not end.get("numero") or not end.get("bairro"):
            raise ErroNegocio("informe rua, número e bairro da entrega", "endereco")
        if dados.taxa_entrega_centavos is not None and not online:
            taxa = dados.taxa_entrega_centavos  # atendente definiu a taxa
        else:
            from apps.clientes.services import calcular_taxa_entrega

            end = dict(end)
            zona, _ = calcular_taxa_entrega(
                loja, bairro=end.get("bairro"), latitude=end.get("latitude"), longitude=end.get("longitude"), endereco=end
            )
            taxa = zona.taxa_centavos
    elif dados.canal == CanalVenda.MARKETPLACE and dados.taxa_entrega_centavos:
        taxa = dados.taxa_entrega_centavos

    if online and subtotal < loja.pedido_minimo_centavos:
        raise ErroNegocio("pedido abaixo do valor mínimo da loja")

    # --- descontos ---
    cupom, desconto = None, 0
    if dados.cupom_codigo:
        cupom, desconto = _cupom(loja, dados.cupom_codigo, subtotal, taxa, dados)
    if not online:  # desconto/acréscimo manual só no PDV
        desconto += dados.desconto_centavos
    acrescimo = 0 if online else dados.acrescimo_centavos
    t = totais.calcular_totais(itens_core, taxa, min(desconto, subtotal + taxa), acrescimo)

    if dados.troco_para_centavos is not None and dados.troco_para_centavos < t.total_centavos:
        raise ErroNegocio("troco para um valor menor que o total", "troco_para_centavos")

    # --- cria ---
    status = fluxo.status_inicial(online, loja.aceite_automatico)
    agora = timezone.now()
    tel = "".join(ch for ch in dados.telefone_cliente if ch.isdigit())
    cliente = None
    if tel and dados.canal in (CanalVenda.ONLINE, CanalVenda.DELIVERY):
        from apps.clientes.services import salvar_cliente_do_pedido

        cliente = salvar_cliente_do_pedido(loja, nome=dados.nome_cliente, telefone=tel, endereco=end or None)

    pedido = Pedido.objects.create(
        **({"id": dados.id} if dados.id else {}),
        loja=loja, numero=SequenciaPedido.proximo(loja, timezone.localdate()), codigo_local=dados.codigo_local,
        canal=dados.canal, origem_contato=dados.origem_contato, tipo_atendimento=dados.tipo_atendimento,
        status=status, cliente=cliente, nome_cliente=dados.nome_cliente[:120], telefone_cliente=tel,
        mesa=dados.mesa, senha=dados.senha, comanda=dados.comanda,
        marketplace=dados.marketplace, id_externo=dados.id_externo, codigo_externo=dados.codigo_externo,
        entrega_logradouro=end.get("logradouro", "") or "", entrega_numero=end.get("numero", "") or "",
        entrega_complemento=end.get("complemento", "") or "", entrega_bairro=end.get("bairro", "") or "",
        entrega_cidade=end.get("cidade", "") or "", entrega_cep=end.get("cep", "") or "",
        entrega_referencia=end.get("referencia", "") or "",
        entrega_latitude=end.get("latitude"), entrega_longitude=end.get("longitude"),
        zona_entrega=zona, entregador_id=dados.entregador_id,
        subtotal_centavos=t.subtotal_centavos, taxa_entrega_centavos=t.taxa_entrega_centavos,
        desconto_centavos=t.desconto_centavos, acrescimo_centavos=t.acrescimo_centavos,
        total_centavos=t.total_centavos, troco_para_centavos=dados.troco_para_centavos,
        cupom=cupom, cpf_nota="".join(ch for ch in dados.cpf_nota if ch.isdigit()),
        observacao=dados.observacao, atendente=usuario if usuario and not online else None,
        turno=caixa.turno_aberto(usuario, loja) if usuario and not online else None,
        dispositivo=dados.dispositivo, aceito_em=agora if status == S.RECEBIDO else None,
    )
    for l in linhas:
        p = l["produto"]
        item = ItemPedido.objects.create(
            pedido=pedido, produto=p, nome_produto=l["nome"][:120], variacao=l["variacao"],
            nome_variacao=l["variacao"].nome if l["variacao"] else "", quantidade=l["quantidade"],
            preco_unitario_centavos=l["preco_unit"], total_adicionais_centavos=l["total_adicionais"],
            total_centavos=l["total"], observacao=l["observacao"], setor=p.setor_efetivo,
        )
        ItemPedidoSabor.objects.bulk_create(
            [ItemPedidoSabor(item=item, produto=sp, nome=sp.nome, preco_unitario_centavos=pr) for sp, pr in l["sabores"]]
        )
        ItemPedidoAdicional.objects.bulk_create([
            ItemPedidoAdicional(item=item, adicional=a, nome=a.nome, quantidade=q, preco_unitario_centavos=a.preco_centavos)
            for a, q in l["adicionais"]
        ])
    HistoricoStatusPedido.objects.create(pedido=pedido, status_para=status, usuario=usuario)

    if cupom:
        from apps.marketing.models import Cupom, UsoCupom

        UsoCupom.objects.create(cupom=cupom, pedido=pedido, cliente=cliente, telefone=tel, desconto_centavos=desconto)
        Cupom.objects.filter(pk=cupom.pk).update(usos=F("usos") + 1)

    if dados.forma_pagamento_prevista:  # online: forma escolhida, paga na entrega/retirada
        Pagamento.objects.create(
            pedido=pedido, forma=FormaPagamento(dados.forma_pagamento_prevista), status=StatusPagamento.PENDENTE,
            valor_centavos=max(t.total_centavos, 1),
            valor_recebido_centavos=dados.troco_para_centavos,
        )

    if status == S.RECEBIDO and loja.momento_baixa_estoque == MomentoBaixaEstoque.ACEITE:
        estoque.baixar_pedido(pedido, usuario)
    if pedido.comanda_id:
        from apps.salao.services import recalcular

        recalcular(pedido.comanda)
    eventos.pedido_novo(pedido)
    return pedido


# =============================================================================
# Status
# =============================================================================
@transaction.atomic
def transicionar(pedido, para: StatusPedido, usuario=None, *, motivo: str = "", entregador_id=None,
                 origem_externa: bool = False) -> Pedido:
    p = Pedido.objects.select_for_update().select_related("loja").get(pk=pedido.pk)
    de = StatusPedido(p.status)
    if de == para:
        return p  # reenvio idempotente
    try:
        fluxo.validar_transicao(de, para, TipoAtendimento(p.tipo_atendimento))
    except fluxo.TransicaoInvalida as exc:
        raise ErroNegocio(f"não é possível mudar de {de.rotulo} para {para.rotulo}") from exc
    if para in (S.CANCELADO, S.RECUSADO):
        if not motivo:
            raise ErroNegocio("informe o motivo", "motivo")
        if de != S.PENDENTE and usuario is not None and not usuario.eh_gerente:
            raise ErroNegocio("cancelar pedido já aceito exige gerente")

    agora = timezone.now()
    p.status = para
    setattr(p, fluxo.CAMPO_TIMESTAMP[para], agora)
    if para in (S.CANCELADO, S.RECUSADO):
        p.motivo_cancelamento = motivo
    if entregador_id:
        p.entregador_id = entregador_id
    p.save()
    HistoricoStatusPedido.objects.create(pedido=p, status_de=de, status_para=para, usuario=usuario, observacao=motivo)

    momento = p.loja.momento_baixa_estoque
    if (para == S.RECEBIDO and momento == MomentoBaixaEstoque.ACEITE) or (
        para == S.CONCLUIDO and momento == MomentoBaixaEstoque.CONCLUSAO
    ):
        estoque.baixar_pedido(p, usuario)
    elif para == S.CONCLUIDO:
        estoque.baixar_pedido(p, usuario)  # garante a baixa mesmo se o aceite foi automático
    if para in (S.CANCELADO, S.RECUSADO):
        estoque.estornar_pedido(p, usuario)
        _estornar_pagamentos(p, usuario, motivo)
        if p.cupom_id:
            from apps.marketing.models import Cupom, UsoCupom

            UsoCupom.objects.filter(pedido=p).delete()
            Cupom.objects.filter(pk=p.cupom_id, usos__gt=0).update(usos=F("usos") - 1)
        if p.comanda_id:
            from apps.salao.services import recalcular

            recalcular(p.comanda)
    eventos.pedido_status(p)
    _ganchos_status(p, para, motivo, origem_externa)
    return p


def _ganchos_status(p, para, motivo, origem_externa):
    """Reflexos fora do sistema (sempre por tarefa, depois do commit)."""
    from apps.integracoes.models import Integracao
    from apps.integracoes.tarefas import enfileirar

    if p.canal == CanalVenda.MARKETPLACE and p.marketplace == "IFOOD" and not origem_externa:
        integ = Integracao.ativa(p.loja, "MARKETPLACE", "ifood")
        if integ:
            from apps.integracoes.provedores.ifood import acao_para_status

            if para in (S.CANCELADO, S.RECUSADO):
                enfileirar("ifood.acao", {"integracao_id": str(integ.id), "order_id": p.id_externo,
                                          "acao": "requestCancellation",
                                          "corpo": {"reason": motivo[:250], "cancellationCode": "501"}})
            elif acao := acao_para_status(para):
                if not (acao == "readyToPickup" and p.tipo_atendimento == TipoAtendimento.ENTREGA):
                    enfileirar("ifood.acao", {"integracao_id": str(integ.id), "order_id": p.id_externo, "acao": acao})
    from apps.integracoes.notificacoes import notificar_status

    notificar_status(p)
    if para == S.CONCLUIDO:
        from apps.fiscal.services import agendar_emissao_automatica

        agendar_emissao_automatica(p)


def concluir(pedido, usuario=None) -> Pedido:
    """Leva o pedido até CONCLUIDO pelo caminho válido (usado ao fechar comanda)."""
    p = pedido
    while StatusPedido(p.status) not in fluxo.FINAIS:
        atual = StatusPedido(p.status)
        proximo = S.RECEBIDO if atual == S.PENDENTE else S.PRONTO if atual in (S.RECEBIDO, S.EM_PREPARO) else S.CONCLUIDO
        p = transicionar(p, proximo, usuario)
    return p


def _estornar_pagamentos(pedido, usuario, motivo):
    for pg in pedido.pagamentos.select_for_update().filter(status=StatusPagamento.CONFIRMADO):
        if pg.turno_id:
            turno = caixa.turno_aberto(usuario, pedido.loja) if usuario else None
            if turno is None:
                raise ErroNegocio("abra o caixa para estornar o pagamento deste pedido")
            caixa.registrar_estorno(turno, pg, usuario, motivo)
        pg.status = StatusPagamento.ESTORNADO
        pg.save(update_fields=["status", "atualizado_em"])
    pedido.pagamentos.filter(status=StatusPagamento.PENDENTE).update(status=StatusPagamento.ESTORNADO)


# =============================================================================
# Pagamentos
# =============================================================================
def total_pago(*, pedido=None, comanda=None) -> int:
    qs = Pagamento.objects.filter(status=StatusPagamento.CONFIRMADO)
    qs = qs.filter(pedido=pedido) if pedido is not None else qs.filter(comanda=comanda)
    return qs.aggregate(s=Sum("valor_centavos"))["s"] or 0


def _taxa_e_previsao(loja, forma, bandeira, valor):
    from apps.financeiro.models import TaxaFormaPagamento

    cfg = (
        TaxaFormaPagamento.objects.filter(loja=loja, forma_pagamento=forma, bandeira=bandeira or "").first()
        or TaxaFormaPagamento.objects.filter(loja=loja, forma_pagamento=forma, bandeira="").first()
    )
    if cfg is None:
        return 0, timezone.localdate()
    taxa = int((Decimal(valor) * cfg.taxa_percentual / 100).quantize(Decimal("1"))) + cfg.taxa_fixa_centavos
    return min(taxa, valor), timezone.localdate() + timedelta(days=cfg.prazo_recebimento_dias)


@transaction.atomic
def registrar_pagamento(
    *, usuario, forma: FormaPagamento, valor_centavos: int, pedido=None, comanda=None,
    valor_recebido_centavos: int | None = None, bandeira: str = "", referencia_externa: str = "",
    pago_online: bool = False, id=None,
) -> Pagamento:
    """Pagamento CONFIRMADO. Entra no caixa do operador (exceto pago online /
    marketplace). Em dinheiro, calcula o troco."""
    if id and (existente := Pagamento.objects.filter(pk=id).first()):
        return existente
    if (pedido is None) == (comanda is None):
        raise ErroNegocio("informe o pedido OU a comanda")
    alvo = pedido or comanda
    loja = alvo.loja
    if pedido is not None:
        pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
        if pedido.status in (S.CANCELADO, S.RECUSADO):
            raise ErroNegocio("pedido cancelado não recebe pagamento")
        total = pedido.total_centavos
    else:
        from apps.salao.models import Comanda

        comanda = Comanda.objects.select_for_update().get(pk=comanda.pk)
        if comanda.status not in ("ABERTA", "FECHANDO"):
            raise ErroNegocio("comanda não está aberta")
        total = comanda.total_centavos
    if valor_centavos <= 0:
        raise ErroNegocio("valor deve ser positivo", "valor_centavos")
    restante = total - total_pago(pedido=pedido, comanda=comanda)
    if valor_centavos > restante:
        raise ErroNegocio(f"valor maior que o restante a pagar ({restante} centavos)", "valor_centavos")

    troco = 0
    if forma == FormaPagamento.DINHEIRO:
        recebido = valor_recebido_centavos if valor_recebido_centavos is not None else valor_centavos
        try:
            troco = calcular_troco(valor_centavos, recebido)
        except ValueError as exc:
            raise ErroNegocio("valor recebido menor que o pagamento", "valor_recebido_centavos") from exc
        valor_recebido_centavos = recebido

    turno = None
    if not pago_online and forma not in FORMAS_SEM_CAIXA:
        turno = caixa.exigir_turno(usuario, loja)
    taxa, previsao = _taxa_e_previsao(loja, forma, bandeira, valor_centavos)

    # Se havia um pagamento PENDENTE (forma escolhida no online), ele é substituído
    if pedido is not None:
        pedido.pagamentos.filter(status=StatusPagamento.PENDENTE).delete()
    pg = Pagamento.objects.create(
        **({"id": id} if id else {}), pedido=pedido, comanda=comanda, forma=forma,
        status=StatusPagamento.CONFIRMADO, valor_centavos=valor_centavos,
        valor_recebido_centavos=valor_recebido_centavos, troco_centavos=troco, pago_online=pago_online,
        referencia_externa=referencia_externa, bandeira=bandeira, taxa_centavos=taxa,
        previsao_recebimento=previsao, turno=turno, recebido_por=usuario, confirmado_em=timezone.now(),
    )
    if turno is not None:
        caixa.registrar_venda(turno, pg, usuario)
    return pg


# =============================================================================
# Marketplace e pagamentos online
# =============================================================================
@transaction.atomic
def importar_pedido_externo(loja, d: dict) -> Pedido:
    """Pedido vindo de marketplace (iFood...): preços e totais são os do app
    (o cliente já pagou o que viu lá). Produtos são casados pelo `codigo` (SKU)
    para baixar estoque e rotear para o setor de produção; o que não casar entra
    só como texto."""
    if existente := Pedido.objects.filter(loja=loja, marketplace=d["marketplace"], id_externo=d["id_externo"]).first():
        return existente
    codigos = {i["codigo"] for i in d["itens"] if i.get("codigo")}
    produtos = {p.codigo: p for p in Produto.objects.ativos().filter(loja=loja, codigo__in=codigos)} if codigos else {}
    end = d.get("endereco") or {}
    pedido = Pedido.objects.create(
        loja=loja, numero=SequenciaPedido.proximo(loja, timezone.localdate()), canal=CanalVenda.MARKETPLACE,
        marketplace=d["marketplace"], id_externo=d["id_externo"], codigo_externo=d.get("codigo_externo", ""),
        tipo_atendimento=d["tipo_atendimento"], status=S.RECEBIDO if loja.aceite_automatico else S.PENDENTE,
        nome_cliente=d.get("nome_cliente", "")[:120], telefone_cliente="".join(c for c in d.get("telefone_cliente", "") if c.isdigit())[:13],
        entrega_logradouro=end.get("logradouro", "") or "", entrega_numero=end.get("numero", "") or "",
        entrega_complemento=end.get("complemento", "") or "", entrega_bairro=end.get("bairro", "") or "",
        entrega_cidade=end.get("cidade", "") or "", entrega_cep=end.get("cep", "") or "",
        entrega_referencia=end.get("referencia", "") or "",
        subtotal_centavos=d["subtotal_centavos"], taxa_entrega_centavos=d.get("taxa_entrega_centavos", 0),
        desconto_centavos=d.get("desconto_centavos", 0), acrescimo_centavos=d.get("acrescimo_centavos", 0),
        total_centavos=d["total_centavos"], observacao=d.get("observacao", ""),
    )
    for it in d["itens"]:
        prod = produtos.get(it.get("codigo"))
        adic_unit = sum(a["unitario_centavos"] * a["quantidade"] for a in it.get("adicionais", []))
        item = ItemPedido.objects.create(
            pedido=pedido, produto=prod, nome_produto=it["nome"][:120], quantidade=it["quantidade"],
            preco_unitario_centavos=it["unitario_centavos"], total_adicionais_centavos=adic_unit,
            total_centavos=it["total_centavos"], observacao=it.get("observacao", "")[:255],
            setor=prod.setor_efetivo if prod else None,
        )
        ItemPedidoAdicional.objects.bulk_create([
            ItemPedidoAdicional(item=item, nome=a["nome"][:80], quantidade=a["quantidade"],
                                preco_unitario_centavos=a["unitario_centavos"]) for a in it.get("adicionais", [])
        ])
    for pg in d.get("pagamentos", []):
        if pg["valor_centavos"] <= 0:
            continue
        Pagamento.objects.create(
            pedido=pedido, forma=pg["forma"], valor_centavos=pg["valor_centavos"], pago_online=pg.get("pago", False),
            status=StatusPagamento.CONFIRMADO if pg.get("pago") else StatusPagamento.PENDENTE,
            confirmado_em=timezone.now() if pg.get("pago") else None,
            valor_recebido_centavos=pg.get("troco_para_centavos"),
        )
    HistoricoStatusPedido.objects.create(pedido=pedido, status_para=pedido.status, observacao=d["marketplace"])
    if pedido.status == S.RECEBIDO and loja.momento_baixa_estoque == MomentoBaixaEstoque.ACEITE:
        estoque.baixar_pedido(pedido)
    eventos.pedido_novo(pedido)
    return pedido


@transaction.atomic
def cobrar_pix(*, pedido=None, comanda=None, valor_centavos: int | None = None, email: str = "") -> Pagamento:
    """Gera cobrança Pix (QR) no gateway da loja. O pagamento fica PENDENTE até
    o webhook confirmar."""
    from django.conf import settings

    from apps.integracoes.models import Integracao
    from apps.integracoes.provedores.base import ErroProvedor
    from apps.integracoes.provedores.mercadopago import MercadoPago

    alvo = pedido or comanda
    integ = Integracao.ativa(alvo.loja, "PAGAMENTO", "mercadopago")
    if integ is None:
        raise ErroNegocio("Pix automático não configurado nesta loja")
    total = alvo.total_centavos
    restante = total - total_pago(pedido=pedido, comanda=comanda)
    valor = valor_centavos or restante
    if valor <= 0 or valor > restante:
        raise ErroNegocio("valor inválido para a cobrança Pix")
    if pedido is not None:
        pedido.pagamentos.filter(status=StatusPagamento.PENDENTE).delete()
    pg = Pagamento.objects.create(pedido=pedido, comanda=comanda, forma=FormaPagamento.PIX, valor_centavos=valor,
                                  status=StatusPagamento.PENDENTE, pago_online=True)
    url = settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/api/webhooks/mercadopago/{alvo.loja_id}/"
    try:
        cobranca = MercadoPago(integ.obter_credenciais()["access_token"]).criar_pix(
            valor_centavos=valor, descricao=f"{alvo.loja.nome} — {alvo}", email=email, referencia=str(pg.id),
            notification_url=url if url.startswith("https://") else "",
        )
    except (ErroProvedor, KeyError) as exc:
        integ.registrar_erro(str(exc))
        raise ErroNegocio(f"falha ao gerar o Pix: {exc}") from exc
    pg.referencia_externa = cobranca["id"]
    pg.dados_externos = {k: cobranca[k] for k in ("qr_code", "qr_code_base64", "ticket_url")}
    pg.save(update_fields=["referencia_externa", "dados_externos", "atualizado_em"])
    return pg


@transaction.atomic
def confirmar_pagamento_online(pagamento: Pagamento, *, valor_centavos: int | None = None) -> Pagamento:
    """Webhook do gateway confirmou: idempotente."""
    pg = Pagamento.objects.select_for_update().get(pk=pagamento.pk)
    if pg.status == StatusPagamento.CONFIRMADO:
        return pg
    if valor_centavos is not None and valor_centavos < pg.valor_centavos:
        raise ErroNegocio("valor pago menor que o cobrado")
    loja = (pg.pedido or pg.comanda).loja
    pg.taxa_centavos, pg.previsao_recebimento = _taxa_e_previsao(loja, pg.forma, pg.bandeira, pg.valor_centavos)
    pg.status, pg.pago_online, pg.confirmado_em = StatusPagamento.CONFIRMADO, True, timezone.now()
    pg.save()
    if pg.pedido_id:
        p = pg.pedido
        eventos.publicar(eventos.grupo_pdv(p.loja_id), "pagamento.confirmado",
                         {"pedido": str(p.id), "valor_centavos": pg.valor_centavos})
        eventos.publicar(eventos.grupo_pedido(p.token_rastreio), "pagamento.confirmado", {"pago": True})
    return pg
