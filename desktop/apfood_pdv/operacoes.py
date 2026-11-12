"""Operações do PDV com funcionamento OFFLINE.

Regra: tenta a API; se não houver conexão — ou se já houver operações na fila
(para não furar a ordem) — grava na outbox com UUID gerado aqui e segue.
O servidor aplica depois, na mesma ordem, de forma idempotente.

Leituras usam o cache local (cardápio, clientes, mesas) quando offline.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from apfood_core import totais
from apfood_core.enums import RegraPrecoSabores
from apfood_core.precos import preco_sabores

from .api import ApiClient, ErroApi, SemConexao
from .local_db import BancoLocal


def novo_id() -> str:
    return str(uuid.uuid4())


class PDV:
    def __init__(self, api: ApiClient, banco: BancoLocal, *, terminal: str = "C1"):
        self.api, self.banco, self.terminal = api, banco, terminal
        self.online = True
        self.ao_enfileirar: Callable[[], None] | None = None  # acorda o sync

    # --- infraestrutura ----------------------------------------------------
    def _executar(self, operacao: str, payload: dict, chamada: Callable[[], dict]) -> dict:
        """Online → chamada direta. Offline/fila pendente → outbox."""
        if self.banco.total_pendentes() == 0:
            try:
                r = chamada()
                self.online = True
                return {**(r or {}), "offline": False}
            except SemConexao:
                self.online = False
        self.banco.enfileirar(operacao, payload, op_id=novo_id())
        if self.ao_enfileirar:
            self.ao_enfileirar()
        return {**payload, "offline": True}

    def codigo_local(self) -> str:
        return f"{self.terminal}-{self.banco.proximo('seq_pedido_local'):04d}"

    # --- cardápio (cache) ----------------------------------------------------
    def categorias(self) -> list[dict]:
        return sorted((c for c in self.banco.listar("categorias") if c.get("ativa", True)),
                      key=lambda c: (c.get("ordem", 0), c["nome"]))

    def produtos(self, categoria_id: str | None = None) -> list[dict]:
        ps = [p for p in self.banco.listar("produtos")
              if p.get("tipo") == "VENDA" and p.get("ativo", True) and not p.get("pausado")]
        if categoria_id:
            ps = [p for p in ps if str(p.get("categoria")) == str(categoria_id)]
        return sorted(ps, key=lambda p: (p.get("ordem", 0), p["nome"]))

    def variacoes(self, produto_id: str) -> list[dict]:
        return sorted((v for v in self.banco.listar("variacoes") if str(v["produto"]) == str(produto_id)
                       and v.get("ativo", True)), key=lambda v: (v.get("ordem", 0), v["preco_centavos"]))

    def grupos_do_produto(self, produto: dict) -> list[dict]:
        ids = [str(g) for g in produto.get("grupos_adicionais", [])]
        grupos = {str(g["id"]): g for g in self.banco.listar("grupos_adicionais") if g.get("ativo", True)}
        adicionais = [a for a in self.banco.listar("adicionais") if a.get("ativo", True)]
        out = []
        for gid in ids:
            if g := grupos.get(gid):
                out.append({**g, "opcoes": sorted((a for a in adicionais if str(a["grupo"]) == gid),
                                                  key=lambda a: (a.get("ordem", 0), a["nome"]))})
        return out

    def precificar_item(self, item: dict) -> int:
        """Total do item calculado localmente (o servidor recalcula ao receber)."""
        p = self.banco.obter("produtos", item["produto_id"]) or {}
        var = self.banco.obter("variacoes", item["variacao_id"]) if item.get("variacao_id") else None
        preco = var["preco_centavos"] if var else p.get("preco_centavos", 0)
        sabores = item.get("sabores") or []
        if len(sabores) > 1:
            cat = self.banco.obter("categorias", p.get("categoria")) or {}
            precos = []
            for sid in sabores:
                sp = self.banco.obter("produtos", sid) or {}
                sv = next((v for v in self.variacoes(sid) if var and v["nome"] == var["nome"]), None)
                precos.append(sv["preco_centavos"] if sv else sp.get("preco_centavos", 0))
            preco = preco_sabores(precos, RegraPrecoSabores(cat.get("regra_preco_sabores", "MAIOR")))
        escolhidos = []
        for a in item.get("adicionais", []):
            ad = self.banco.obter("adicionais", a["adicional_id"]) or {}
            escolhidos.append(totais.AdicionalEscolhido(str(ad.get("grupo")), a["adicional_id"],
                                                        ad.get("preco_centavos", 0), a.get("quantidade", 1)))
        return totais.Item(preco, item.get("quantidade", 1), escolhidos).total_centavos

    # --- pedidos -------------------------------------------------------------
    def criar_pedido(self, dados: dict) -> dict:
        payload = {"id": novo_id(), "codigo_local": self.codigo_local(), **dados}
        r = self._executar("pedido.criar", payload, lambda: self.api.post("/api/pedidos/", payload))
        if r["offline"]:
            sub = sum(self.precificar_item(i) for i in dados["itens"])
            taxa = dados.get("taxa_entrega_centavos") or 0
            r.update(numero=None, status="RECEBIDO", subtotal_centavos=sub, taxa_entrega_centavos=taxa,
                     total_centavos=max(0, sub + taxa + dados.get("acrescimo_centavos", 0) - dados.get("desconto_centavos", 0)),
                     criado_em=datetime.now().isoformat())
        return r

    def mudar_status(self, pedido_id: str, status: str, motivo: str = "", entregador_id: str | None = None) -> dict:
        corpo = {"status": status, "motivo": motivo, "entregador_id": entregador_id}
        return self._executar("pedido.status", {"pedido": pedido_id, **corpo},
                              lambda: self.api.post(f"/api/pedidos/{pedido_id}/status/", corpo))

    def pagar(self, pedido_id: str, forma: str, valor_centavos: int, recebido_centavos: int | None = None,
              bandeira: str = "") -> dict:
        corpo = {"id": novo_id(), "forma": forma, "valor_centavos": valor_centavos,
                 "valor_recebido_centavos": recebido_centavos, "bandeira": bandeira}
        r = self._executar("pedido.pagamento", {"pedido": pedido_id, **corpo},
                           lambda: self.api.post(f"/api/pedidos/{pedido_id}/pagamentos/", corpo))
        if r["offline"] and forma == "DINHEIRO" and recebido_centavos:
            r["troco_centavos"] = max(0, recebido_centavos - valor_centavos)
        return r

    # --- caixa ---------------------------------------------------------------
    def abrir_caixa(self, valor_centavos: int) -> dict:
        corpo = {"id": novo_id(), "valor_abertura_centavos": valor_centavos}
        r = self._executar("caixa.abrir", corpo, lambda: self.api.post("/api/turnos/abrir/", corpo))
        self.banco.gravar("turno_atual", r.get("id") or corpo["id"])
        return r

    def turno_atual(self) -> dict | None:
        try:
            return self.api.get("/api/turnos/atual/")
        except SemConexao:
            tid = self.banco.ler("turno_atual")
            return {"id": tid, "offline": True, "resumo": {}} if tid else None
        except ErroApi as e:
            if e.status == 404:
                self.banco.gravar("turno_atual", None)
                return None
            raise

    def movimento_caixa(self, turno_id: str, tipo: str, valor_centavos: int, motivo: str = "") -> dict:
        corpo = {"id": novo_id(), "tipo": tipo, "valor_centavos": valor_centavos, "motivo": motivo}
        return self._executar("caixa.movimento", {"turno": turno_id, **corpo},
                              lambda: self.api.post(f"/api/turnos/{turno_id}/movimentos/", corpo))

    def despesa_caixa(self, turno_id: str, descricao: str, valor_centavos: int) -> dict:
        corpo = {"id": novo_id(), "descricao": descricao, "valor_centavos": valor_centavos}
        return self._executar("caixa.despesa", {"turno": turno_id, **corpo},
                              lambda: self.api.post(f"/api/turnos/{turno_id}/despesas/", corpo))

    def fechar_caixa(self, turno_id: str, informado: dict, tipo_conferencia: str = "CEGA", observacao: str = "") -> dict:
        corpo = {"informado": informado, "tipo_conferencia": tipo_conferencia, "observacao": observacao}
        r = self._executar("caixa.fechar", {"turno": turno_id, **corpo},
                           lambda: self.api.post(f"/api/turnos/{turno_id}/fechar/", corpo))
        self.banco.gravar("turno_atual", None)
        return r

    # --- clientes ------------------------------------------------------------
    def buscar_cliente(self, telefone: str) -> list[dict]:
        digitos = "".join(c for c in telefone if c.isdigit())
        try:
            return self.api.get("/api/clientes/por-telefone/", telefone=digitos)
        except SemConexao:
            achados = [c for c in self.banco.listar("clientes") if c.get("telefone", "").endswith(digitos[-8:])]
            enderecos = self.banco.listar("enderecos")
            for c in achados:
                c["enderecos"] = [e for e in enderecos if str(e["cliente"]) == str(c["id"])]
            return achados
