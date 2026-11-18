"""Testes da interface do PDV (PySide6 em modo offscreen, servidor falso).
Pulados automaticamente se o PySide6 não estiver instalado."""

import json
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APFOOD_SEM_SOM", "1")
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
            ("POST", r"/api/auth/token/", lambda c, m: (200, {"access": "a", "refresh": "r"}) if c["password"] == "certa"
             else (401, {"detail": "credenciais"})),
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
            ("GET", r"/api/clientes/por-telefone/", lambda c, m: (200, [
                {"id": "cl1", "nome": "Ana", "telefone": "11999990000", "saldo_cashback_centavos": 500, "enderecos": []}])),
            ("GET", r"/api/relatorios/vendas/", lambda c, m: (200, {
                "faturamento_centavos": 0, "pedidos": 0, "ticket_medio_centavos": 0, "cancelados": 0, "por_dia": [],
                "por_canal": [], "por_forma_pagamento": []})),
            ("GET", r"/api/relatorios/curva-abc/", lambda c, m: (200, {"itens": []})),
            ("GET", r"/api/relatorios/fechamentos/", lambda c, m: (200, {"turnos": [], "por_operador": []})),
            ("GET", r"/api/relatorios/fluxo-caixa/", lambda c, m: (200, {"dias": [], "a_receber_centavos": 0,
                                                                         "a_pagar_centavos": 0})),
            ("GET", r"/api/relatorios/faturamento/", lambda c, m: (200, {
                "linhas": [{"texto": "RELATORIO DE FATURAMENTO"}, {"corte": True}],
                "operadores": [{"id": "u1", "nome": "Caixa 1"}, {"id": "u2", "nome": "Caixa 2"}]})),
            ("GET", r"/api/turnos/fechamentos/", lambda c, m: (200, {
                "turnos": [{"id": "t1"}, {"id": "t2"}], "operadores": [{"id": "u1", "nome": "Caixa 1"}],
                "linhas": [{"texto": "FECHAMENTO CAIXA 1"}, {"corte": True}, {"texto": "FECHAMENTO CAIXA 2"}, {"corte": True}]})),
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
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield a
    # desmonta tudo antes do fim do processo (evita segfault do Qt no encerramento)
    from PySide6.QtCore import QTimer

    for w in a.topLevelWidgets():
        for t in w.findChildren(QTimer):
            t.stop()
        w.close()
        w.deleteLater()
    a.processEvents()
    a.sendPostedEvents(None, 0)


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
        if JanelaPrincipal.MENU[linha][0] == "Painel web":
            continue  # abre o navegador
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


def test_venda_balcao_usa_cashback_do_cliente(ctx):
    from apfood_pdv.ui.paginas.venda import PaginaVenda

    v = PaginaVenda(ctx)
    v.ao_mostrar()
    v.adicionar_produto(CARDAPIO["produtos"][0])  # 700
    assert v.usar_cashback.isHidden()
    v.telefone_balcao.setText("11999990000")
    v.buscar_cliente_balcao()
    assert not v.usar_cashback.isHidden() and "5,00" in v.usar_cashback.text()
    v.usar_cashback.setChecked(True)
    assert "2,00" in v.total.text()
    dados = v.montar_dados()
    assert dados["usar_cashback_centavos"] == 500 and dados["telefone_cliente"] == "11999990000"
    v.limpar()
    assert v.usar_cashback.isHidden() and v.cliente is None


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


def test_login_tema_claro_lembra_usuario_e_mostra_erro(ctx):
    from apfood_pdv.ui.janela import DialogoLogin

    d = DialogoLogin(ctx)
    assert not d.box_servidor.isVisible() and "servidor" in d.lbl_servidor.text()
    if pasta := os.environ.get("APFOOD_PRINTS"):  # a CI guarda o print da tela
        from apfood_pdv.__main__ import tema_claro
        from apfood_pdv.ui.estilo import QSS

        app = QtWidgets.QApplication.instance()
        tema_claro(app)
        app.setStyleSheet(QSS)
        d.usuario.setText("caixa1")
        d.show()
        app.processEvents()
        os.makedirs(pasta, exist_ok=True)
        d.grab().save(os.path.join(pasta, "login.png"))
        d.usuario.clear()
    d.entrar()
    assert "Informe usuário" in d.msg.text()
    d.usuario.setText("caixa1")
    d.senha.setText("errada")
    d.entrar()
    assert "incorretos" in d.msg.text() and d.btn_entrar.isEnabled()
    d.senha.setText("certa")
    d.entrar()
    assert d.result() == 1 and ctx.cfg.ultimo_usuario == "caixa1"
    d2 = DialogoLogin(ctx)
    assert d2.usuario.text() == "caixa1"


def test_caixa_livre_e_numero_do_balcao(ctx):
    from apfood_pdv.ui.paginas.venda import PaginaVenda

    v = PaginaVenda(ctx)
    v.ao_mostrar()
    assert v.pilha_carrinho.currentWidget() is v.caixa_livre and "CAIXA FECHADO" in v.caixa_livre.text()
    ctx.banco.gravar("turno_atual", "T1")
    v.mostrar_caixa_livre()
    assert "CAIXA LIVRE" in v.caixa_livre.text()
    v.adicionar_produto(CARDAPIO["produtos"][0])
    assert v.pilha_carrinho.currentWidget() is v.tabela
    ctx.servidor.online = False
    resp = v.finalizar(pagamentos=[{"forma": "PIX", "valor_centavos": 700}])
    assert resp["senha"] == "0001" and v.ultimo_numero == "0001"
    assert v.pilha_carrinho.currentWidget() is v.caixa_livre and "0001" in v.caixa_livre.text()
    texto = "".join(f.read_text(encoding="utf-8") for f in (ctx.pasta / "cupons").glob("*.txt"))
    assert "0001" in texto


def test_dialogo_pagamento_parcial_da_mesa(ctx):
    from apfood_pdv.ui.dialogos import DialogoPagamento

    d = DialogoPagamento(3000, permitir_parcial=True)
    d._dividir(3)
    assert d.valor.text() == "10,00"
    d.pagador.setText("Cliente 1")
    d.forma_btn.button(1).setChecked(True)  # Pix
    d.accept()
    assert d.result() == 1 and d.restante == 2000
    assert d.pagamentos == [{"forma": "PIX", "valor_centavos": 1000, "recebido_centavos": None, "bandeira": "",
                             "pagador": "Cliente 1"}]
    # sem permitir parcial (balcão), continua exigindo o valor todo
    d2 = DialogoPagamento(3000)
    d2.valor.setText("10,00")
    d2.accept()
    assert d2.result() == 0



def test_seletor_de_impressora_e_modo_driver(ctx):
    from apfood_pdv.ui.paginas.gestao import SeletorImpressora

    s = SeletorImpressora("windows:HP LaserJet")
    assert s.nome.currentText() == "HP LaserJet" and s.modo.currentData() == "driver" and s.valor() == "windows:HP LaserJet"
    s.modo.setCurrentIndex(0)
    assert s.valor() == "HP LaserJet"  # térmica ESC/POS (RAW), como antes
    s.nome.setCurrentText("192.168.0.50:9100")
    assert s.valor() == "192.168.0.50:9100" and not s.modo.isEnabled()
    assert SeletorImpressora("").valor() == ""


def test_impressora_do_windows_inexistente(ctx):
    from apfood_pdv.impressao import ErroImpressao, descrever, imprimir

    with pytest.raises(ErroImpressao, match="não está instalada"):
        imprimir("windows:Impressora Que Nao Existe", ["teste"])
    assert "driver" in descrever("windows:X") and "rede" in descrever("10.0.0.1:9100")


def test_pedido_mostra_entregador_codigo_e_agendado(ctx):
    from apfood_pdv.ui.paginas.pedidos import PaginaPedidos

    pg = PaginaPedidos(ctx)
    p = {"id": "p1", "numero": 7, "status": "PRONTO", "tipo_atendimento": "ENTREGA", "canal": "DELIVERY",
         "entregador": "e1", "entregador_nome": "Rui", "codigo_retirada": "4821", "agendado_para": "2026-11-18T19:30:00-03:00",
         "criado_em": "2026-11-17T12:00:00-03:00", "itens": [], "pagamentos": [], "total_centavos": 0, "subtotal_centavos": 0,
         "taxa_entrega_centavos": 0, "desconto_centavos": 0, "nome_cliente": "Ana"}
    pg.pedidos = [p]
    from apfood_pdv.ui.util import preencher_tabela

    preencher_tabela(pg.tabela, ["Nº"], [["#7"]], [p])
    pg.tabela.selectRow(0)
    texto = pg.detalhe.toPlainText()
    assert "CÓDIGO DE RETIRADA: 4821" in texto and "Entregador: Rui" in texto and "AGENDADO PARA 18/11 às 19:30" in texto
    assert not pg.btn_chamar.isEnabled()  # já tem entregador


class _DialogoQueImprime:
    """Substitui a prévia: aperta "Imprimir" na hora."""
    titulos = []

    def __init__(self, titulo, texto, parent=None, *, rodape="", acoes=None):
        _DialogoQueImprime.titulos.append((titulo, texto))
        self.acoes = acoes or []

    def exec(self):
        for rot, fn in self.acoes:
            if rot == "Imprimir":
                fn()


def _cupons(ctx):
    pasta = ctx.pasta / "cupons"
    return "\n".join(f.read_text(encoding="utf-8") for f in sorted(pasta.glob("*.txt"))) if pasta.exists() else ""


def test_relatorio_de_faturamento_por_data_e_operador_imprime(ctx, monkeypatch):
    from apfood_pdv.ui.paginas import gestao

    monkeypatch.setattr(gestao, "DialogoTexto", _DialogoQueImprime)
    p = gestao.PaginaRelatorios(ctx)
    p.atualizar()
    assert p.inicio.displayFormat() == "dd/MM/yyyy" and p.operador.count() == 2  # Todos + quem trabalhou
    p.imprimir_faturamento()
    assert p.operador.count() == 3  # completou com a lista do relatório
    assert "RELATORIO DE FATURAMENTO" in _cupons(ctx)
    assert _DialogoQueImprime.titulos[-1][0].startswith("Faturamento ")


def test_imprime_fechamento_de_um_ou_de_todos_os_operadores(ctx, monkeypatch):
    from apfood_pdv.ui.paginas import gestao

    monkeypatch.setattr(gestao, "DialogoTexto", _DialogoQueImprime)
    d = gestao.DialogoFechamentos(ctx)
    assert d.operador.itemText(0) == "Todos os operadores" and d.operador.count() == 2
    assert "2 caixa(s)" in d.info.text()
    assert d._params()["data"] == d.dia.date().toString("dd/MM/yyyy") and "usuario" not in d._params()
    d.imprimir()
    texto = _cupons(ctx)
    assert "FECHAMENTO CAIXA 1" in texto and "FECHAMENTO CAIXA 2" in texto
    d.operador.setCurrentIndex(1)
    assert d._params()["usuario"] == "u1"
    c = gestao.PaginaCaixa(ctx)
    assert c.btn_reimprimir.text().startswith("Imprimir fechamento")


def test_logo_da_loja_sai_em_todos_os_cupons_do_pc(ctx, monkeypatch):
    import base64

    from apfood_core import cupom

    from apfood_pdv import impressao

    raster = b"\x1dv0\x00" + bytes([2, 0, 2, 0]) + b"\xff" * 4
    ctx.servidor.rotas.insert(0, ("GET", r"/api/impressao/logo/", lambda c, m: (200, {
        "tem_logo": True, "versao": "v1", "escpos_base64": base64.b64encode(raster).decode(),
        "png_base64": base64.b64encode(b"png").decode()})))
    assert ctx.carregar_logo()
    loja = ctx.loja_para_cupom()
    assert loja["logo"] == "local"
    linhas = cupom.comprovante_venda({"itens": [], "total_centavos": 0, "pagamentos": []}, loja, 48)
    assert linhas[0].logo
    dados = impressao.para_escpos(linhas, largura=48)
    assert raster in dados and dados.index(raster) < dados.index(b"BURGER DEMO")
    assert "png" not in impressao.para_texto(linhas)

    # sem internet: usa a logo guardada
    impressao.definir_logo(48, None, None)
    ctx.servidor.online = False
    assert ctx.carregar_logo() and impressao.logo(48)["escpos"] == raster
    ctx.servidor.online = True
    impressao.definir_logo(48, None, None)
