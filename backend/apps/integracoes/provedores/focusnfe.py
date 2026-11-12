"""Focus NFe — emissão de NFC-e (modelo 65).

API: POST /v2/nfce?ref=REF · GET /v2/nfce/REF · DELETE /v2/nfce/REF
Auth: HTTP Basic (token como usuário, senha vazia).
Hosts: homologacao.focusnfe.com.br | api.focusnfe.com.br

Credenciais da Integracao (tipo FISCAL, provedor "focusnfe"): {"token": "..."}.
Configuração: {"cnpj_emitente": "...", "pis_cst": "07", "cofins_cst": "07"}.
⚠ Validar o leiaute com o contador e em homologação antes de produção
(CST/CSOSN, NCM e CFOP de cada produto vêm do cadastro).
"""

from decimal import Decimal

from apfood_core.enums import AmbienteFiscal, FormaPagamento

from .base import checar, cliente

HOSTS = {AmbienteFiscal.HOMOLOGACAO: "https://homologacao.focusnfe.com.br",
         AmbienteFiscal.PRODUCAO: "https://api.focusnfe.com.br"}

#: Tabela de meios de pagamento da NFC-e (tPag)
TPAG = {
    FormaPagamento.DINHEIRO: "01", FormaPagamento.CARTAO_CREDITO: "03", FormaPagamento.CARTAO_DEBITO: "04",
    FormaPagamento.VOUCHER: "11", FormaPagamento.PIX: "17", FormaPagamento.MARKETPLACE: "99",
    FormaPagamento.OUTRO: "99",
}


def _reais(c: int) -> str:
    return f"{Decimal(c) / 100:.2f}"


def ratear(total: int, pesos: list[int]) -> list[int]:
    """Distribui `total` centavos proporcionalmente aos pesos, sem perder centavo."""
    soma = sum(pesos)
    if not total or not soma:
        return [0] * len(pesos)
    partes = [total * p // soma for p in pesos]
    partes[-1] += total - sum(partes)
    return partes


class FocusNFe:
    def __init__(self, token: str, ambiente: str = AmbienteFiscal.HOMOLOGACAO):
        self.http = cliente(HOSTS[AmbienteFiscal(ambiente)], auth=(token, ""))

    def emitir_nfce(self, referencia: str, dados: dict) -> dict:
        return checar(self.http.post("/v2/nfce", params={"ref": referencia}, json=dados), "Focus NFe emitir")

    def consultar_nfce(self, referencia: str) -> dict:
        return checar(self.http.get(f"/v2/nfce/{referencia}"), "Focus NFe consultar")

    def cancelar_nfce(self, referencia: str, justificativa: str) -> dict:
        return checar(self.http.request("DELETE", f"/v2/nfce/{referencia}", json={"justificativa": justificativa}),
                      "Focus NFe cancelar")


def montar_nfce(*, itens: list[dict], pagamentos: list[dict], desconto_centavos: int, outras_centavos: int,
                cnpj_emitente: str, cpf: str = "", entrega: bool = False, config: dict | None = None,
                data_emissao: str) -> dict:
    """`itens`: [{codigo, descricao, ncm, cfop, cest, origem, cst_csosn, quantidade, unitario_centavos,
    total_centavos}]. Desconto e acréscimos (taxa de entrega/serviço) são rateados pelos itens."""
    config = config or {}
    totais = [i["total_centavos"] for i in itens]
    descontos, outras = ratear(desconto_centavos, totais), ratear(outras_centavos, totais)
    nfce_itens = []
    for n, (i, d, o) in enumerate(zip(itens, descontos, outras, strict=True), start=1):
        qtd = Decimal(i["quantidade"])
        item = {
            "numero_item": n, "codigo_produto": i["codigo"][:60], "descricao": i["descricao"][:120],
            "codigo_ncm": i.get("ncm") or "21069090", "cfop": i.get("cfop") or "5102",
            "unidade_comercial": "UN", "quantidade_comercial": f"{qtd:.4f}",
            "valor_unitario_comercial": _reais(i["unitario_centavos"]), "valor_bruto": _reais(i["total_centavos"]),
            "unidade_tributavel": "UN", "quantidade_tributavel": f"{qtd:.4f}",
            "valor_unitario_tributavel": _reais(i["unitario_centavos"]),
            "icms_origem": str(i.get("origem") or 0), "icms_situacao_tributaria": i.get("cst_csosn") or "102",
            "pis_situacao_tributaria": config.get("pis_cst", "07"),
            "cofins_situacao_tributaria": config.get("cofins_cst", "07"),
        }
        if i.get("cest"):
            item["cest"] = i["cest"]
        if d:
            item["valor_desconto"] = _reais(d)
        if o:
            item["valor_outras_despesas"] = _reais(o)
        nfce_itens.append(item)
    dados = {
        "cnpj_emitente": cnpj_emitente, "data_emissao": data_emissao,
        "presenca_comprador": "4" if entrega else "1", "modalidade_frete": "9", "local_destino": "1",
        "items": nfce_itens,
        "formas_pagamento": [{"forma_pagamento": TPAG.get(FormaPagamento(p["forma"]), "99"),
                              "valor_pagamento": _reais(p["valor_centavos"])} for p in pagamentos],
    }
    if cpf:
        dados["cpf_destinatario"] = cpf
    return dados
