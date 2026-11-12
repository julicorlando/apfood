"""Testes da interface do PDV (PySide6 em modo offscreen, servidor falso).
Pulados automaticamente se o PySide6 não estiver instalado."""

import json
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from apfood_pdv.api import ApiClient, SemConexao  # noqa: E402
from apfood_pdv.config import Config  # noqa: E402
from apfood_pdv.local_db import BancoLocal  # noqa: E402

LOJA = {"id": "11111111-1111-1111-1111-111111111111", "nome": "Burger Demo", "slug": "burger"}
USUARIO = {"id": "u1", "username": "caixa1", "nome": "Caixa 1", "papel": "GERENTE", "lojas": [LOJA]}
CARDAPIO = {
    "setores": [{"id": "s1", "nome": "Chapa", "impressora": "", "atualizado_em": "2026-01-01T00:00:00Z"}],
    "categorias": [{"id": "c1", "nome": "Lanches", "ativa": True, "ordem": 0, "setor": "s1", "max_sabores": 1,
                    "atualizado_em": "2026-01-01T00:00:00Z"}],
    "produtos": [
        {"id": "p1", "nome": "Refrigerante", "tipo": "VENDA", "ativo": True, "categoria": "c1", "preco_centavos": 700,
         "grupos_adicionais": [], "controla_estoque": True, "estoque_atual": "10", "unidade": "UN",
         "atualizado_em": "2026-01-01T00:00:00Z"},
        {"id": "p2", "nome": "X-Burger", "tipo": "VENDA", "ativo": True, "categoria": "c1", "preco_centavos": 3000,
         "grupos_adicionais": ["g1"], "atualizado_em": "2026-01-01T00:00:00Z"},
    ],
    "variacoes": [],
    "grupos_adicionais": [{"id": "g1", "nome": "Ponto", "min_selecao": 1, "max_selecao": 1, "ativo": True,
                           "atualizado_em": "2026-01-01T00:00:00Z"}],
    "adicionais": [{"id": "a1", "grupo": "g1", "nome": "Ao ponto", "preco_centavos": 0, "max_por_item": 1, "ativo": True,
                    "atualizado_em": "2026-01-01T00:00:00Z"},
                   {"id": "a2", "grupo": "g1", "nome": "Bem passado", "preco_centavos": 0, "max_por_item": 1,
                    "ativo": True, "atualizado_em": "2026-01-01T00:00:00Z"}],
    "mesas": [{"id": "m1", "nome": "Mesa 01", "ativa": True, "atualizado_em": "2026-01-01T00:00:00Z"}],
    "entregadores": [],
}


class ServidorFalso:
    def __init__(self):
        self.online = True
        self.chamadas = []
        self.pedidos = []
        self.rotas = [
            ("GET", r"/api/eu/", lambda c, m: (200, USUARIO)),
            ("GET", r"/api/pedidos/", lambda c, m: (200, {"results": self.pedidos, "next": None})),
            ("POST", r"/api/pedidos/", self._criar),
            ("POST", r"/api/pedidos/([^/]+)/pagamentos/", lambda c, m: (201, {"id": "pg", "troco_centavos": 0})),
            ("POST", r"/api/pedidos/([^/]+)/status/", lambda c, m: (200, {"id": m[1], "status": c["status"]})),
            ("POST", r"/api/pedidos/([^/]+)/documento/",
             lambda c, m: (200, {"tipo": "NAO_FISCAL", "linhas": [{"texto": "CUPOM SERVIDOR"}, {"corte": True}]})),
            ("GET", r"/api/pedidos/([^/]+)/cupom/", lambda c, m: (200, {"vias": []})),
            ("GET", r"/api/turnos/atual/", lambda c, m: (404, {"detail": "nenhum caixa aberto"})),
            ("POST", r"/api/turnos/abrir/", lambda c, m: (201, {"id": "t1", **c})),
            ("GET", r"/api/comandas/", lambda c, m: (200, {"results": [], "next": None})),
            ("GET", r"/api/cozinha/", lambda c, m: (200, [])),
            ("GET", r"/api/estoque/abaixo-do-minimo/", lambda c, m: (200, [])),
            ("GET", r"/api/estoque/", lambda c, m: (200, {"results": [], "next": None})),
            ("GET", r"/api/produtos/", lambda c, m: (200, {"results": CARDAPIO["produtos"], "next": None})),
            ("GET", r"/api/relatorios/vendas/", lambda c, m: (200, {
                "faturamento_centavos": 0, "pedidos": 0, "ticket_medio_centavos": 0, "cancelados": 0, "por_dia": [],
                "por_canal": [], "por_forma_pagamento": []})),
            ("GET", r"/api/relatorios/curva-abc/", lambda c, m: (200, {"itens": []})),
            ("GET", r"/api/relatorios/fechamentos/", lambda c, m: (200, {"turnos": [], "por_operador": []})),
            ("GET", r"/api/relatorios/fluxo-caixa/", lambda c, m: (200, {"dias": [], "a_receber_centavos": 0,
                                                                         "a_pagar_centavos": 0})),
        ]

    def _criar(self, corpo, m):
        total = sum(700 if i["produto_id"] == "p1" else 3000 for i in corpo["itens"])
        p = {**corpo, "numero": len(self.pedidos) + 1, "status": "RECEBIDO", "subtotal_centavos": total,
             "taxa_entrega_centavos": 0, "desconto_centavos": 0, "total_centavos": total}
        return 201, p

    def __call__(self, metodo, url, headers, corpo, timeout):
        if not self.online:
            raise SemConexao("offline")
        caminho = "/" + url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        dados = json.loads(corpo) if corpo else None
        self.chamadas.append((metodo, caminho, dados))
        for met, padrao, fn in self.rotas:
            if met == metodo and (m := re.fullmatch(padrao, caminho)):
                status, resp = fn(dados, m)
                return status, json.dumps(resp).encode()
        return 404, b'{"detail": "nao encontrado"}'


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def avisos(monkeypatch):
    registro = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: registro.append(a[2] if len(a) > 2 else a))
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", lambda *a, **k: QtWidgets.QMessageBox.Yes)
    return registro


@pytest.fixture
def ctx(app, tmp_path, monkeypatch, avisos):
    monkeypatch.setenv("APFOOD_PASTA", str(tmp_path))
    from apfood_pdv.ui.contexto import Contexto

    servidor = ServidorFalso()
    cfg = Config(api_url="http://servidor", impressora_caixa=f"arquivo:{tmp_path / 'cupons'}",
                 impressora_cozinha_padrao=f"arquivo:{tmp_path / 'cozinha'}")
    banco = BancoLocal(":memory:")
    for entidade, regs in CARDAPIO.items():
        banco.aplicar_pull(entidade, regs)
    c = Contexto(cfg, ApiClient(cfg.api_url, transporte=servidor), banco)
    c.definir_usuario(USUARIO)
    c.definir_loja(LOJA)
    c.servidor, c.pasta = servidor, tmp_path
    return c


def test_janela_abre_todas_as_telas(ctx):
    from apfood_pdv.ui.janela import JanelaPrincipal

    j = JanelaPrincipal(ctx)
    for linha in range(len(JanelaPrincipal.MENU) - 1):  # menos "Trocar operador"
        j.menu.setCurrentRow(linha)
        assert j.pilha.currentWidget() is j.paginas[linha]
    j.p_venda.novo_delivery()
    assert j.p_venda.modo == "DELIVERY"


def test_venda_balcao_online_recebe_e_imprime(ctx, avisos):
    from apfood_pdv.ui.paginas.venda import PaginaVenda

    v = PaginaVenda(ctx)
    v.ao_mostrar()
    v.adicionar_produto(CARDAPIO["produtos"][0])  # sem opções: entra direto
    v.adicionar_produto(CARDAPIO["produtos"][0])
    assert v.subtotal() == 1400
    resp = v.finalizar(pagamentos=[{"forma": "DINHEIRO", "valor_centavos": 1400, "recebido_centavos": 2000}])
    assert resp and not resp["offline"] and resp["numero"] == 1
    metodos = [(m, c) for m, c, _ in ctx.servidor.chamadas]
    assert ("POST", "/api/pedidos/") in metodos
    assert any(c.endswith("/pagamentos/") for m, c in metodos)
    assert any(c.endswith("/documento/") for m, c in metodos)
    cupons = list((ctx.pasta / "cupons").glob("*.txt"))
    assert cupons and "CUPOM SERVIDOR" in cupons[0].read_text(encoding="utf-8")
    assert v.carrinho == [] and not avisos


def test_venda_offline_vai_para_fila_e_imprime_nao_fiscal_local(ctx):
    from apfood_pdv.ui.paginas.venda import PaginaVenda

    ctx.servidor.online = False
    v = PaginaVenda(ctx)
    v.ao_mostrar()
    v.adicionar_produto(CARDAPIO["produtos"][0])
    v.nome_balcao.setText("João")
    resp = v.finalizar(pagamentos=[{"forma": "PIX", "valor_centavos": 700}])
    assert resp["offline"] and resp["codigo_local"]
    ops = [o.operacao for o in ctx.banco.pendentes()]
    assert ops == ["pedido.criar", "pedido.pagamento"]
    texto = "".join(f.read_text(encoding="utf-8") for f in (ctx.pasta / "cupons").glob("*.txt"))
    assert "NAO E DOCUMENTO FISCAL" in texto and "Refrigerante" in texto and "João" in texto
    cozinha = "".join(f.read_text(encoding="utf-8") for f in (ctx.pasta / "cozinha").glob("*.txt"))
    assert "Refrigerante" in cozinha  # via de cozinha local por setor


def test_dialogo_item_exige_grupo_obrigatorio(ctx):
    from apfood_pdv.ui.dialogos import DialogoItem

    d = DialogoItem(ctx.pdv, CARDAPIO["produtos"][1])
    assert d._erros()  # "Ponto" é obrigatório
    _, _, spin = d.spins[0]
    spin.setValue(1)
    assert not d._erros()
    item = d.item()
    assert item["adicionais"] == [{"adicional_id": "a1", "quantidade": 1}] and item["quantidade"] == 1


def test_fila_destaca_pedido_online_pendente(ctx):
    from apfood_pdv.ui.paginas.pedidos import PaginaPedidos

    ctx.servidor.pedidos = [{
        "id": "x1", "numero": 9, "codigo_local": "", "canal": "ONLINE", "status": "PENDENTE",
        "tipo_atendimento": "ENTREGA", "nome_cliente": "Ana", "criado_em": "2026-11-12T20:00:00-03:00",
        "total_centavos": 3500, "subtotal_centavos": 3000, "taxa_entrega_centavos": 500, "pagamentos": [],
        "itens": [{"quantidade": 1, "nome_produto": "X-Burger", "total_centavos": 3000, "adicionais": [], "sabores": []}],
        "entrega_logradouro": "Rua A", "entrega_numero": "1", "entrega_bairro": "Centro",
    }]
    p = PaginaPedidos(ctx)
    contagem = []
    p.pendentes_mudou.connect(contagem.append)
    p.atualizar()
    assert contagem == [1] and p.tabela.rowCount() == 1
    p.tabela.selectRow(0)
    assert p.btn_aceitar.isEnabled() and "X-Burger" in p.detalhe.toPlainText()
    p.aceitar()
    assert ("POST", "/api/pedidos/x1/status/") in [(m, c) for m, c, _ in ctx.servidor.chamadas]


def test_caixa_fechado_permite_abrir(ctx):
    from apfood_pdv.ui.paginas.gestao import PaginaCaixa

    c = PaginaCaixa(ctx)
    c.atualizar()
    assert c.btn_abrir.isEnabled() and not c.btn_fechar.isEnabled()
