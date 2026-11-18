"""Layouts de impressão térmica (80 mm = 48 colunas, 58 mm = 32 colunas).

Gera uma lista de `Linha` com estilo; quem imprime (PDV) converte para
ESC/POS. Sem dependências — o mesmo layout serve para a tela de pré-visualização,
para PDF e para a impressora.

    comprovante_venda  → cupom NÃO FISCAL (quando a loja não tem emissor fiscal)
    cupom_cozinha      → via de produção por setor (letra grande, sem preços)
    fechamento_caixa   → conferência do turno
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .dinheiro import formatar
from .enums import CanalVenda, FormaPagamento


@dataclass(frozen=True, slots=True)
class Linha:
    texto: str = ""
    negrito: bool = False
    grande: bool = False  # altura e largura duplas
    alinhamento: str = "esquerda"  # esquerda | centro | direita
    corte: bool = False  # cortar o papel depois desta linha
    qrcode: bool = False  # imprime `texto` como QR Code


def _r(c: int) -> str:
    return formatar(c, simbolo=False)


def _quebrar(texto: str, largura: int) -> list[str]:
    palavras, linhas, atual = (texto or "").split(), [], ""
    for p in palavras:
        while len(p) > largura:
            if atual:
                linhas.append(atual)
                atual = ""
            linhas.append(p[:largura])
            p = p[largura:]
        if not atual:
            atual = p
        elif len(atual) + 1 + len(p) <= largura:
            atual += " " + p
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas or [""]


def _dupla(esq: str, dir: str, largura: int) -> str:
    """'X-Burger ........ 29,90' — texto à esquerda, valor à direita."""
    espaco = largura - len(dir) - 1
    esq = esq[:espaco] if len(esq) > espaco else esq
    return esq + " " * (largura - len(esq) - len(dir)) + dir


def _sep(largura: int, c: str = "-") -> Linha:
    return Linha(c * largura)


def _cabecalho_loja(loja: dict, largura: int) -> list[Linha]:
    out = [Linha(loja.get("nome", "").upper(), negrito=True, alinhamento="centro")]
    for campo in ("razao_social", "endereco"):
        if loja.get(campo):
            out += [Linha(t, alinhamento="centro") for t in _quebrar(loja[campo], largura)]
    if loja.get("cnpj"):
        out.append(Linha(f"CNPJ {loja['cnpj']}", alinhamento="centro"))
    if loja.get("telefone"):
        out.append(Linha(f"Tel. {loja['telefone']}", alinhamento="centro"))
    return out


def _itens(itens: list[dict], largura: int, *, precos: bool) -> list[Linha]:
    out = []
    for it in itens:
        nome = it["nome"] + (f" ({it['variacao']})" if it.get("variacao") else "")
        cab = f"{it['quantidade']}x {nome}"
        if precos:
            linhas = _quebrar(cab, largura - 12)
            out.append(Linha(_dupla(linhas[0], _r(it["total_centavos"]), largura)))
            out += [Linha("   " + l) for l in linhas[1:]]
        else:
            out += [Linha(l, negrito=True, grande=True) for l in _quebrar(cab, largura // 2)]
        for s in it.get("sabores", []):
            out.append(Linha(f"   1/{len(it['sabores'])} {s}"))
        for a in it.get("adicionais", []):
            txt = f"   + {a.get('quantidade', 1)}x {a['nome']}"
            if precos and a.get("preco_unitario_centavos"):
                out.append(Linha(_dupla(txt, _r(a["preco_unitario_centavos"] * a.get("quantidade", 1)), largura)))
            else:
                out.append(Linha(txt, negrito=not precos))
        if it.get("observacao"):
            for l in _quebrar(f"OBS: {it['observacao']}", largura - 3):
                out.append(Linha("   " + l, negrito=True))
    return out


def comprovante_venda(pedido: dict, loja: dict, largura: int = 48) -> list[Linha]:
    """`pedido`: numero, data (datetime), canal, tipo_atendimento, atendente, nome_cliente,
    telefone_cliente, mesa, senha, itens[], subtotal/taxa_entrega/desconto/acrescimo/
    taxa_servico/total_centavos, pagamentos[{forma, valor_centavos, troco_centavos}],
    endereco (str), observacao, link_acompanhamento."""
    L = largura
    out = _cabecalho_loja(loja, L)
    out += [_sep(L, "="), Linha("COMPROVANTE DE VENDA", negrito=True, alinhamento="centro"),
            Linha("NAO E DOCUMENTO FISCAL", negrito=True, alinhamento="centro"), _sep(L, "=")]
    data: datetime = pedido.get("data") or datetime.now()
    out.append(Linha(_dupla(f"Pedido #{pedido.get('numero') or pedido.get('codigo_local', '')}",
                            data.strftime("%d/%m/%Y %H:%M"), L), negrito=True))
    if pedido.get("tipo_atendimento"):
        out.append(Linha(pedido["tipo_atendimento"].replace("_", " ").title()))
    for rotulo, campo in (("Mesa", "mesa"), ("Senha", "senha"), ("Cliente", "nome_cliente"),
                          ("Telefone", "telefone_cliente"), ("Atendente", "atendente")):
        if pedido.get(campo):
            out.append(Linha(f"{rotulo}: {pedido[campo]}"))
    out.append(_sep(L))
    out += _itens(pedido.get("itens", []), L, precos=True)
    out.append(_sep(L))
    out.append(Linha(_dupla("Subtotal", _r(pedido.get("subtotal_centavos", 0)), L)))
    for rotulo, campo, sinal in (("Taxa de entrega", "taxa_entrega_centavos", ""),
                                 ("Taxa de servico", "taxa_servico_centavos", ""),
                                 ("Acrescimo", "acrescimo_centavos", ""), ("Desconto", "desconto_centavos", "-")):
        if pedido.get(campo):
            out.append(Linha(_dupla(rotulo, sinal + _r(pedido[campo]), L)))
    out.append(Linha(_dupla("TOTAL R$", _r(pedido.get("total_centavos", 0)), L // 2), negrito=True, grande=True))
    if pedido.get("pagamentos"):
        out.append(_sep(L))
        for pg in pedido["pagamentos"]:
            out.append(Linha(_dupla(pg["forma"].replace("_", " ").title(), _r(pg["valor_centavos"]), L)))
            if pg.get("troco_centavos"):
                out.append(Linha(_dupla("  Troco", _r(pg["troco_centavos"]), L)))
    elif pedido.get("troco_para_centavos"):
        out.append(Linha(_dupla("Troco para", _r(pedido["troco_para_centavos"]), L)))
    if pedido.get("endereco"):
        out += [_sep(L), Linha("ENTREGA", negrito=True)] + [Linha(l) for l in _quebrar(pedido["endereco"], L)]
    if pedido.get("observacao"):
        out += [_sep(L)] + [Linha(l) for l in _quebrar(f"Obs: {pedido['observacao']}", L)]
    out.append(_sep(L, "="))
    if pedido.get("link_acompanhamento"):
        out += [Linha("Acompanhe seu pedido:", alinhamento="centro"),
                Linha(pedido["link_acompanhamento"], alinhamento="centro")]
    out += [Linha("Obrigado pela preferencia!", alinhamento="centro"), Linha(), Linha(corte=True)]
    return out


def danfe_nfce(pedido: dict, loja: dict, nota: dict, largura: int = 48) -> list[Linha]:
    """DANFE NFC-e simplificado para a térmica (NFC-e AUTORIZADA).

    `nota`: numero, serie, chave, protocolo, autorizada_em (datetime|str),
    url_consulta, qrcode (conteúdo do QR da SEFAZ), ambiente, cpf_cnpj_consumidor.
    Mesmo corpo do comprovante; muda o título e o rodapé fiscal (chave + QR Code).
    """
    L = largura
    corpo = comprovante_venda(pedido, loja, largura)
    # troca o título "COMPROVANTE / NAO E DOCUMENTO FISCAL" pelo do DANFE
    titulo = [Linha("DANFE NFC-e - Documento Auxiliar da", negrito=True, alinhamento="centro"),
              Linha("Nota Fiscal de Consumidor Eletronica", negrito=True, alinhamento="centro")]
    i = next(n for n, l in enumerate(corpo) if l.texto == "COMPROVANTE DE VENDA")
    corpo = corpo[:i] + titulo + corpo[i + 2:]
    # rodapé fiscal antes do agradecimento
    fim = next(n for n, l in enumerate(corpo) if l.texto == "Obrigado pela preferencia!")
    chave = nota.get("chave") or ""
    autorizada = nota.get("autorizada_em")
    if isinstance(autorizada, datetime):
        autorizada = autorizada.strftime("%d/%m/%Y %H:%M:%S")
    elif isinstance(autorizada, str) and len(autorizada) >= 19:
        autorizada = f"{autorizada[8:10]}/{autorizada[5:7]}/{autorizada[:4]} {autorizada[11:19]}"
    doc = nota.get("cpf_cnpj_consumidor") or ""
    fiscal = [
        Linha(f"NFC-e n {nota.get('numero') or ''}  Serie {nota.get('serie') or ''}", negrito=True,
              alinhamento="centro"),
        Linha(f"Emissao {autorizada or ''}", alinhamento="centro"),
        Linha(f"CONSUMIDOR CPF/CNPJ {doc}" if doc else "CONSUMIDOR NAO IDENTIFICADO", alinhamento="centro"),
        Linha("Consulte pela chave de acesso em", alinhamento="centro"),
    ]
    if nota.get("url_consulta"):
        fiscal += [Linha(t, alinhamento="centro") for t in _quebrar(nota["url_consulta"], L)]
    fiscal += [Linha(" ".join(chave[n:n + 4] for n in range(0, len(chave), 4))[:L], alinhamento="centro")]
    if len(" ".join(chave[n:n + 4] for n in range(0, len(chave), 4))) > L:
        resto = " ".join(chave[n:n + 4] for n in range(0, len(chave), 4))[L:].strip()
        fiscal.append(Linha(resto, alinhamento="centro"))
    if nota.get("protocolo"):
        fiscal.append(Linha(f"Protocolo de autorizacao {nota['protocolo']}", alinhamento="centro"))
    if nota.get("qrcode"):
        fiscal.append(Linha(nota["qrcode"], qrcode=True, alinhamento="centro"))
    if nota.get("ambiente") == "HOMOLOGACAO":
        fiscal.append(Linha("EMITIDA EM HOMOLOGACAO - SEM VALOR FISCAL", negrito=True, alinhamento="centro"))
    fiscal.append(_sep(L, "="))
    return corpo[:fim] + fiscal + corpo[fim:]


def cupom_cozinha(pedido: dict, setor: str = "", largura: int = 48) -> list[Linha]:
    """Via de produção: número grande, itens grandes, observações em destaque, sem preços."""
    L = largura
    destino = pedido.get("mesa") and f"MESA {pedido['mesa']}" or (pedido.get("tipo_atendimento") or "").replace("_", " ")
    out = [
        Linha(setor.upper() or "COZINHA", negrito=True, alinhamento="centro"),
        Linha(f"#{pedido.get('numero') or pedido.get('codigo_local', '')}", negrito=True, grande=True, alinhamento="centro"),
        Linha(destino.upper(), negrito=True, grande=True, alinhamento="centro"),
    ]
    if pedido.get("nome_cliente"):
        out.append(Linha(pedido["nome_cliente"], alinhamento="centro"))
    data: datetime = pedido.get("data") or datetime.now()
    out += [Linha(data.strftime("%d/%m %H:%M"), alinhamento="centro"), _sep(L)]
    out += _itens(pedido.get("itens", []), L, precos=False)
    if pedido.get("observacao"):
        out += [_sep(L)] + [Linha(l, negrito=True) for l in _quebrar(f"OBS DO PEDIDO: {pedido['observacao']}", L)]
    out += [_sep(L), Linha(), Linha(corte=True)]
    return out


def fechamento_caixa(dados: dict, loja: dict, largura: int = 48) -> list[Linha]:
    """`dados`: operador, aberto_em, fechado_em (datetime), valor_abertura_centavos,
    conferencia[{forma, esperado_centavos, informado_centavos, diferenca_centavos}],
    totais_por_tipo{SANGRIA, SUPRIMENTO, DESPESA, VENDA}, quantidade_vendas, situacao."""
    L = largura
    out = _cabecalho_loja(loja, L) + [_sep(L, "="), Linha("FECHAMENTO DE CAIXA", negrito=True, alinhamento="centro"),
                                      _sep(L, "=")]
    out.append(Linha(f"Operador: {dados.get('operador', '')}"))
    for rotulo, campo in (("Abertura", "aberto_em"), ("Fechamento", "fechado_em")):
        if dados.get(campo):
            out.append(Linha(f"{rotulo}: {dados[campo]:%d/%m/%Y %H:%M}"))
    out.append(Linha(_dupla("Fundo de troco", _r(dados.get("valor_abertura_centavos", 0)), L)))
    tipos = dados.get("totais_por_tipo", {})
    for rotulo, chave in (("Vendas", "VENDA"), ("Suprimentos", "SUPRIMENTO"), ("Sangrias", "SANGRIA"),
                          ("Despesas", "DESPESA"), ("Estornos", "ESTORNO_VENDA")):
        if tipos.get(chave):
            out.append(Linha(_dupla(rotulo, _r(tipos[chave]), L)))
    out.append(Linha(f"Quantidade de vendas: {dados.get('quantidade_vendas', 0)}"))
    out += [_sep(L), Linha(f"{'Forma':<16}{'Esperado':>10}{'Contado':>11}{'Dif.':>11}"[:L], negrito=True)]
    for c in dados.get("conferencia", []):
        forma = c["forma"].replace("CARTAO_", "").replace("_", " ").title()[:15]
        out.append(Linha(f"{forma:<16}{_r(c['esperado_centavos']):>10}{_r(c['informado_centavos']):>11}"
                         f"{_r(c['diferenca_centavos']):>11}"[:L]))
    total = sum(c["diferenca_centavos"] for c in dados.get("conferencia", []))
    situacao = dados.get("situacao") or ("SOBRA" if total > 0 else "QUEBRA" if total < 0 else "OK")
    out += [_sep(L), Linha(_dupla(f"RESULTADO: {situacao}", _r(total), L), negrito=True),
            Linha(), Linha("_" * min(30, L), alinhamento="centro"), Linha("Assinatura do operador", alinhamento="centro"),
            Linha(), Linha(corte=True)]
    return out


def _rotulo(enum, valor: str) -> str:
    try:
        return enum(valor).rotulo
    except ValueError:
        return valor


def relatorio_faturamento(dados: dict, loja: dict, largura: int = 48) -> list[Linha]:
    """Relatório de faturamento do período (térmica). `dados` = resposta de /api/relatorios/faturamento/."""
    L = largura
    out = _cabecalho_loja(loja, L) + [_sep(L, "="), Linha("RELATÓRIO DE FATURAMENTO", negrito=True, alinhamento="centro"),
                                      _sep(L, "=")]
    ini, fim = dados["inicio"], dados["fim"]
    out.append(Linha(f"Período: {ini:%d/%m/%Y}" + (f" a {fim:%d/%m/%Y}" if fim != ini else "")))
    if dados.get("operador"):
        out.append(Linha(f"Operador: {dados['operador']}"))
    out.append(Linha(f"Emitido em: {dados['emitido_em']:%d/%m/%Y %H:%M}"))
    r = dados["resumo"]
    out += [_sep(L), Linha(_dupla("FATURAMENTO", formatar(r["faturamento_centavos"]), L), negrito=True)]
    for rot, k in (("Pedidos concluídos", "pedidos"),):
        out.append(Linha(_dupla(rot, str(r[k]), L)))
    for rot, k in (("Ticket médio", "ticket_medio_centavos"), ("Subtotal dos itens", "subtotal_centavos"),
                   ("Taxas de entrega", "taxas_entrega_centavos"), ("Acréscimos/serviço", "acrescimos_centavos"),
                   ("Descontos", "descontos_centavos")):
        if r.get(k) or k == "ticket_medio_centavos":
            out.append(Linha(_dupla(rot, ("-" if k == "descontos_centavos" else "") + _r(r[k]), L)))
    if r.get("cancelados"):
        out.append(Linha(_dupla(f"Cancelados ({r['cancelados']})", _r(r["cancelados_centavos"]), L)))
    formas = dados.get("por_forma") or []
    if formas:
        out += [_sep(L), Linha("RECEBIMENTOS POR FORMA", negrito=True)]
        for f in formas:
            out.append(Linha(_dupla(f"{_rotulo(FormaPagamento, f['forma'])} ({f['quantidade']})", _r(f["bruto_centavos"]), L)))
        tot = dados["recebido"]
        out.append(Linha(_dupla("Total recebido", formatar(tot["bruto_centavos"]), L), negrito=True))
        if tot.get("taxas_centavos"):
            out += [Linha(_dupla("Taxas (cartão/online)", "-" + _r(tot["taxas_centavos"]), L)),
                    Linha(_dupla("Líquido", formatar(tot["liquido_centavos"]), L), negrito=True)]
    canais = dados.get("por_canal") or []
    if canais:
        out += [_sep(L), Linha("VENDAS POR CANAL", negrito=True)]
        for c in canais:
            out.append(Linha(_dupla(f"{_rotulo(CanalVenda, c['canal'])} ({c['pedidos']})", _r(c["faturamento_centavos"]), L)))
    ops = dados.get("por_operador") or []
    if ops and not dados.get("operador"):
        out += [_sep(L), Linha("RECEBIDO POR OPERADOR", negrito=True)]
        for o in ops:
            out.append(Linha(_dupla(f"{o['operador'][:L - 14]} ({o['quantidade']})", _r(o["bruto_centavos"]), L)))
    dias = dados.get("por_dia") or []
    if len(dias) > 1:
        out += [_sep(L), Linha("POR DIA", negrito=True)]
        for d in dias:
            out.append(Linha(_dupla(f"{d['data']:%d/%m} ({d['pedidos']} ped.)", _r(d["faturamento_centavos"]), L)))
    out += [_sep(L, "="), Linha(), Linha("_" * min(30, L), alinhamento="centro"), Linha("Responsável", alinhamento="centro"),
            Linha(), Linha(corte=True)]
    return out


def para_texto(linhas: list[Linha], largura: int = 48) -> str:
    """Versão texto (pré-visualização, e-mail, log)."""
    saida = []
    for l in linhas:
        if l.corte:
            continue
        t = l.texto
        if l.alinhamento == "centro":
            t = t.center(largura).rstrip()
        elif l.alinhamento == "direita":
            t = t.rjust(largura)
        saida.append(t)
    return "\n".join(saida)
