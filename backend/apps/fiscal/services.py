"""Documento da venda: NFC-e quando a loja tem emissor fiscal configurado;
senão, COMPROVANTE NÃO FISCAL (cupom) para impressão.

    documento_da_venda(pedido)  → {"tipo": "NFCE", "nota": ...} | {"tipo": "NAO_FISCAL", "linhas": [...]}
"""

import logging

from apfood_core import cupom
from apfood_core.enums import ModeloDocumentoFiscal, StatusNotaFiscal, StatusPagamento
from django.db import transaction
from django.utils import timezone

from apps.core.excecoes import ErroNegocio
from apps.integracoes.tarefas import enfileirar, executor

from .models import ConfiguracaoFiscal, NotaFiscal

log = logging.getLogger(__name__)


# --- dados para os layouts de impressão ---------------------------------------
def dados_loja(loja) -> dict:
    end = ", ".join(x for x in (loja.logradouro, loja.numero) if x)
    if loja.bairro:
        end += f" - {loja.bairro}"
    if loja.cidade:
        end += f" - {loja.cidade}/{loja.uf}"
    return {"nome": loja.nome, "razao_social": loja.empresa.razao_social, "cnpj": loja.cnpj or loja.empresa.cnpj or "",
            "endereco": end.strip(" -"), "telefone": loja.telefone}


def dados_pedido(pedido) -> dict:
    from django.conf import settings

    itens = []
    for i in pedido.itens.prefetch_related("adicionais", "sabores"):
        itens.append({
            "quantidade": i.quantidade, "nome": i.nome_produto, "variacao": i.nome_variacao,
            "total_centavos": i.total_centavos, "observacao": i.observacao,
            "sabores": [s.nome for s in i.sabores.all()] if i.sabores.count() > 1 else [],
            "adicionais": [{"nome": a.nome, "quantidade": a.quantidade, "preco_unitario_centavos": a.preco_unitario_centavos}
                           for a in i.adicionais.all()],
            "setor": i.setor.nome if i.setor_id else "",
        })
    endereco = ""
    if pedido.entrega_logradouro:
        endereco = f"{pedido.entrega_logradouro}, {pedido.entrega_numero}"
        for parte in (pedido.entrega_complemento, pedido.entrega_bairro, pedido.entrega_referencia):
            if parte:
                endereco += f" - {parte}"
    return {
        "numero": pedido.numero, "codigo_local": pedido.codigo_local, "data": timezone.localtime(pedido.criado_em),
        "tipo_atendimento": pedido.tipo_atendimento, "mesa": pedido.mesa or (pedido.comanda.mesa.nome if pedido.comanda_id and pedido.comanda.mesa_id else ""),
        "senha": pedido.senha, "nome_cliente": pedido.nome_cliente, "telefone_cliente": pedido.telefone_cliente,
        "atendente": str(pedido.atendente) if pedido.atendente_id else "", "itens": itens,
        "subtotal_centavos": pedido.subtotal_centavos, "taxa_entrega_centavos": pedido.taxa_entrega_centavos,
        "desconto_centavos": pedido.desconto_centavos, "acrescimo_centavos": pedido.acrescimo_centavos,
        "total_centavos": pedido.total_centavos, "troco_para_centavos": pedido.troco_para_centavos,
        "pagamentos": [{"forma": p.forma, "valor_centavos": p.valor_centavos, "troco_centavos": p.troco_centavos}
                       for p in pedido.pagamentos.filter(status=StatusPagamento.CONFIRMADO)],
        "endereco": endereco, "observacao": pedido.observacao,
        "link_acompanhamento": settings.APFOOD["URL_PUBLICA"].rstrip("/") + f"/pedido/{pedido.token_rastreio}/"
        if pedido.canal in ("ONLINE", "DELIVERY") else "",
    }


def linhas_para_json(linhas) -> list[dict]:
    return [{"texto": l.texto, "negrito": l.negrito, "grande": l.grande, "alinhamento": l.alinhamento,
             "corte": l.corte} for l in linhas]


def cupom_venda(pedido, largura=48):
    return cupom.comprovante_venda(dados_pedido(pedido), dados_loja(pedido.loja), largura)


def cupons_cozinha(pedido, largura=48) -> list[dict]:
    """Uma via por setor de produção (cada setor na sua impressora)."""
    dados = dados_pedido(pedido)
    por_setor: dict[str, list] = {}
    for item in dados["itens"]:
        por_setor.setdefault(item["setor"] or "", []).append(item)
    from apps.cardapio.models import SetorProducao

    impressoras = {s.nome: s.impressora for s in SetorProducao.objects.filter(loja=pedido.loja)}
    return [{"setor": setor, "impressora": impressoras.get(setor, ""),
             "linhas": linhas_para_json(cupom.cupom_cozinha({**dados, "itens": itens}, setor or "Cozinha", largura))}
            for setor, itens in por_setor.items()]


def cupom_comanda(comanda, largura=48):
    """Conta da mesa (pré-conta) — também não fiscal."""
    from apps.pedidos.models import ItemPedido

    itens = [{"quantidade": i.quantidade, "nome": i.nome_produto, "variacao": i.nome_variacao,
              "total_centavos": i.total_centavos, "adicionais": []}
             for i in ItemPedido.objects.filter(pedido__comanda=comanda).exclude(
                 pedido__status__in=["CANCELADO", "RECUSADO"]).order_by("criado_em")]
    dados = {"numero": comanda.numero or (comanda.mesa.nome if comanda.mesa_id else ""), "data": timezone.localtime(),
             "mesa": comanda.mesa.nome if comanda.mesa_id else "", "nome_cliente": comanda.nome_cliente, "itens": itens,
             "subtotal_centavos": comanda.subtotal_centavos, "taxa_servico_centavos": comanda.taxa_servico_centavos,
             "desconto_centavos": comanda.desconto_centavos, "acrescimo_centavos": comanda.couvert_centavos,
             "total_centavos": comanda.total_centavos,
             "pagamentos": [{"forma": p.forma, "valor_centavos": p.valor_centavos, "troco_centavos": p.troco_centavos}
                            for p in comanda.pagamentos.filter(status=StatusPagamento.CONFIRMADO)]}
    return cupom.comprovante_venda(dados, dados_loja(comanda.loja), largura)


def cupom_fechamento(turno, largura=48):
    from apps.caixa.services import resumo

    r = resumo(turno, mostrar_esperado=True)
    dados = {"operador": str(turno.usuario), "aberto_em": timezone.localtime(turno.aberto_em),
             "fechado_em": timezone.localtime(turno.fechado_em) if turno.fechado_em else None,
             "valor_abertura_centavos": turno.valor_abertura_centavos, "totais_por_tipo": r["totais_por_tipo"],
             "quantidade_vendas": r["quantidade_vendas"],
             "conferencia": [{"forma": c.forma_pagamento, "esperado_centavos": c.valor_esperado_centavos,
                              "informado_centavos": c.valor_informado_centavos, "diferenca_centavos": c.diferenca_centavos}
                             for c in turno.conferencias.all()]}
    return cupom.fechamento_caixa(dados, dados_loja(turno.loja), largura)


# --- emissão fiscal -----------------------------------------------------------
def emissor_da_loja(loja):
    """(ConfiguracaoFiscal, Integracao) se a loja emite nota; senão None."""
    from apps.integracoes.models import Integracao

    cfg = ConfiguracaoFiscal.objects.filter(loja=loja, ativa=True).first()
    if cfg is None or not loja.empresa.tem_recurso("fiscal"):
        return None
    integ = Integracao.ativa(loja, "FISCAL")
    return (cfg, integ) if integ else None


def _itens_fiscais(pedido) -> list[dict]:
    out = []
    for i in pedido.itens.select_related("produto"):
        p = i.produto
        unit = i.total_centavos // i.quantidade if i.quantidade else i.total_centavos
        out.append({"codigo": (p.codigo or str(p.id)[:8]) if p else "AVULSO", "descricao": i.nome_produto,
                    "ncm": p.ncm if p else "", "cfop": p.cfop if p else "5102", "cest": p.cest if p else "",
                    "origem": p.origem if p else 0, "cst_csosn": p.cst_csosn if p else "",
                    "quantidade": i.quantidade, "unitario_centavos": unit, "total_centavos": unit * i.quantidade})
    # diferença de arredondamento (unitário × qtd) vai no último item
    if out:
        dif = sum(i.total_centavos for i in pedido.itens.all()) - sum(i["total_centavos"] for i in out)
        out[-1]["total_centavos"] += dif
    return out


@transaction.atomic
def emitir_nfce(pedido, *, cpf: str = "") -> NotaFiscal:
    from apps.integracoes.provedores.base import ErroProvedor
    from apps.integracoes.provedores.focusnfe import FocusNFe, montar_nfce

    par = emissor_da_loja(pedido.loja)
    if par is None:
        raise ErroNegocio("loja sem emissor fiscal configurado")
    cfg, integ = par
    if integ.provedor != "focusnfe":
        raise ErroNegocio(f"provedor fiscal '{integ.provedor}' ainda não suportado")
    if pedido.status in ("CANCELADO", "RECUSADO"):
        raise ErroNegocio("pedido cancelado não gera nota")
    if existente := pedido.notas_fiscais.filter(status__in=[StatusNotaFiscal.AUTORIZADA, StatusNotaFiscal.PROCESSANDO]).first():
        return existente
    pagos = list(pedido.pagamentos.filter(status=StatusPagamento.CONFIRMADO))
    if sum(p.valor_centavos for p in pagos) < pedido.total_centavos:
        raise ErroNegocio("registre o pagamento completo antes de emitir a nota")
    cpf = "".join(c for c in (cpf or pedido.cpf_nota) if c.isdigit())
    nota = NotaFiscal.objects.create(
        loja=pedido.loja, pedido=pedido, modelo=ModeloDocumentoFiscal.NFCE, ambiente=cfg.ambiente,
        status=StatusNotaFiscal.PROCESSANDO, valor_total_centavos=pedido.total_centavos, cpf_cnpj_consumidor=cpf,
        provedor="focusnfe", referencia_provedor=f"apf-{str(pedido.id)[:8]}-{pedido.notas_fiscais.count() + 1}",
        serie=cfg.serie,
    )
    dados = montar_nfce(
        itens=_itens_fiscais(pedido), pagamentos=[{"forma": p.forma, "valor_centavos": p.valor_centavos} for p in pagos],
        desconto_centavos=pedido.desconto_centavos,
        outras_centavos=pedido.taxa_entrega_centavos + pedido.acrescimo_centavos,
        cnpj_emitente="".join(c for c in (integ.configuracao.get("cnpj_emitente") or pedido.loja.cnpj or "") if c.isdigit()),
        cpf=cpf if len(cpf) == 11 else "", entrega=pedido.tipo_atendimento == "ENTREGA", config=integ.configuracao,
        data_emissao=timezone.localtime().isoformat(timespec="seconds"),
    )
    try:
        resp = FocusNFe(integ.obter_credenciais()["token"], cfg.ambiente).emitir_nfce(nota.referencia_provedor, dados)
        aplicar_retorno(nota, resp)
        integ.registrar_sucesso()
    except ErroProvedor as exc:
        nota.status, nota.mensagem_retorno = StatusNotaFiscal.REJEITADA, str(exc)
        nota.tentativas += 1
        nota.save()
        integ.registrar_erro(str(exc))
    return nota


def aplicar_retorno(nota, resp: dict) -> None:
    from apps.integracoes.provedores.focusnfe import HOSTS

    st = resp.get("status")
    nota.tentativas += 1
    nota.mensagem_retorno = resp.get("mensagem_sefaz") or resp.get("mensagem") or ""
    if st == "autorizado":
        host = HOSTS[nota.ambiente]
        nota.status, nota.autorizada_em = StatusNotaFiscal.AUTORIZADA, timezone.now()
        nota.chave = (resp.get("chave_nfe") or "").removeprefix("NFe") or None
        nota.numero = int(resp["numero"]) if resp.get("numero") else None
        nota.serie = int(resp["serie"]) if resp.get("serie") else nota.serie
        nota.protocolo = resp.get("protocolo", "")
        for campo, chave in (("url_xml", "caminho_xml_nota_fiscal"), ("url_danfe", "caminho_danfe")):
            if resp.get(chave):
                setattr(nota, campo, resp[chave] if resp[chave].startswith("http") else host + resp[chave])
    elif st == "processando_autorizacao":
        nota.status = StatusNotaFiscal.PROCESSANDO
        enfileirar("fiscal.consultar", {"nota_id": str(nota.id)}, chave=f"nf-{nota.id}", atraso_s=10)
    elif st == "cancelado":
        nota.status, nota.cancelada_em = StatusNotaFiscal.CANCELADA, timezone.now()
    else:
        nota.status = StatusNotaFiscal.REJEITADA
    nota.save()


def documento_da_venda(pedido, *, cpf: str = "", largura: int = 48) -> dict:
    """O que imprimir ao finalizar a venda."""
    if emissor_da_loja(pedido.loja):
        nota = emitir_nfce(pedido, cpf=cpf)
        if nota.status in (StatusNotaFiscal.AUTORIZADA, StatusNotaFiscal.PROCESSANDO):
            return {"tipo": "NFCE", "nota": {"id": str(nota.id), "status": nota.status, "numero": nota.numero,
                                             "chave": nota.chave, "url_danfe": nota.url_danfe}}
        # rejeitada: entrega o comprovante para o cliente não ficar sem nada
        return {"tipo": "NAO_FISCAL", "aviso": f"NFC-e rejeitada: {nota.mensagem_retorno}",
                "linhas": linhas_para_json(cupom_venda(pedido, largura))}
    return {"tipo": "NAO_FISCAL", "linhas": linhas_para_json(cupom_venda(pedido, largura))}


def agendar_emissao_automatica(pedido) -> None:
    cfg = ConfiguracaoFiscal.objects.filter(loja=pedido.loja, ativa=True, emitir_automaticamente=True).first()
    if cfg and emissor_da_loja(pedido.loja):
        enfileirar("fiscal.emitir", {"pedido_id": str(pedido.id)}, chave=f"nf-pedido-{pedido.id}")


@transaction.atomic
def cancelar_nota(nota, justificativa: str) -> NotaFiscal:
    from apps.integracoes.provedores.focusnfe import FocusNFe

    if nota.status != StatusNotaFiscal.AUTORIZADA:
        raise ErroNegocio("só notas autorizadas podem ser canceladas")
    if len(justificativa) < 15:
        raise ErroNegocio("a justificativa precisa ter ao menos 15 caracteres", "justificativa")
    _, integ = emissor_da_loja(nota.loja) or (None, None)
    if integ is None:
        raise ErroNegocio("emissor fiscal indisponível")
    resp = FocusNFe(integ.obter_credenciais()["token"], nota.ambiente).cancelar_nfce(nota.referencia_provedor, justificativa)
    nota.motivo_cancelamento = justificativa
    aplicar_retorno(nota, resp)
    return nota


@executor("fiscal.emitir")
def _tarefa_emitir(pedido_id: str):
    from apps.pedidos.models import Pedido

    nota = emitir_nfce(Pedido.objects.get(pk=pedido_id))
    if nota.status == StatusNotaFiscal.REJEITADA:
        raise RuntimeError(nota.mensagem_retorno)


@executor("fiscal.consultar")
def _tarefa_consultar(nota_id: str):
    from apps.integracoes.provedores.focusnfe import FocusNFe

    nota = NotaFiscal.objects.get(pk=nota_id)
    if nota.status != StatusNotaFiscal.PROCESSANDO:
        return
    _, integ = emissor_da_loja(nota.loja)
    aplicar_retorno(nota, FocusNFe(integ.obter_credenciais()["token"], nota.ambiente).consultar_nfce(nota.referencia_provedor))
    if nota.status == StatusNotaFiscal.PROCESSANDO:
        raise RuntimeError("ainda processando")
