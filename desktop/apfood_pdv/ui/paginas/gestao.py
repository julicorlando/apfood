"""Caixa, cozinha (KDS), estoque, relatórios e configurações."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget, QTableWidget, QVBoxLayout, QWidget,
)

from ...api import SemConexao
from ...impressao import para_texto
from ..dialogos import DialogoEscolha, DialogoFechamento, DialogoTexto, DialogoValor
from ..util import CANAIS, FORMAS, botao, dado_selecionado, erro, preencher_tabela, reais, seguro


def _titulo(texto: str) -> QLabel:
    t = QLabel(texto)
    t.setProperty("papel", "titulo")
    return t


def _data(d: date) -> QDateEdit:
    e = QDateEdit(QDate(d.year, d.month, d.day))
    e.setCalendarPopup(True)
    e.setDisplayFormat("dd/MM/yyyy")
    return e


def mostrar_e_imprimir(parent, ctx, titulo: str, linhas: list) -> None:
    """Prévia do cupom com o botão Imprimir (térmica do caixa ou impressora do Windows configurada)."""
    DialogoTexto(titulo, para_texto(linhas, ctx.cfg.largura_bobina), parent,
                 acoes=[("Imprimir", lambda: seguro(parent, ctx.imprimir, linhas) is not None and ctx.status("Enviado para a impressora"))]).exec()


class DialogoFechamentos(QDialog):
    """Imprimir fechamento de caixa por dia. Operador: os próprios. Gerente/administrador: de um operador
    ou de todos de uma vez (um cupom atrás do outro)."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Imprimir fechamento de caixa")
        lay = QFormLayout(self)
        self.dia = _data(date.today())
        lay.addRow("Dia (DD/MM/AAAA)", self.dia)
        self.operador = QComboBox()
        self.operador.addItem("Todos os operadores", "")
        if ctx.eh_gerente:
            lay.addRow("Operador", self.operador)
            self.dia.dateChanged.connect(lambda *_: self._operadores())
            self._operadores()
        self.info = QLabel("")
        self.info.setWordWrap(True)
        lay.addRow(self.info)
        h = QHBoxLayout()
        h.addWidget(botao("Visualizar / imprimir", self.imprimir, "primario"))
        h.addWidget(botao("Fechar", self.reject))
        lay.addRow(h)

    def _params(self, **extra) -> dict:
        p = {"data": self.dia.date().toString("dd/MM/yyyy"), "largura": self.ctx.cfg.largura_bobina, **extra}
        if self.operador.currentData():
            p["usuario"] = self.operador.currentData()
        return p

    def _operadores(self):
        try:
            r = self.ctx.api.get("/api/turnos/fechamentos/", **self._params())
        except Exception:  # noqa: BLE001
            return
        atual = self.operador.currentData()
        if self.operador.count() == 1:
            for o in r.get("operadores", []):
                self.operador.addItem(o["nome"], o["id"])
            i = self.operador.findData(atual)
            self.operador.setCurrentIndex(max(0, i))
        n = len(r.get("turnos", []))
        self.info.setText(f"{n} caixa(s) fechado(s) nesse dia." if n else "Nenhum caixa fechado nesse dia.")

    def imprimir(self):
        try:
            r = self.ctx.api.get("/api/turnos/fechamentos/", **self._params(cupom=1))
        except Exception as e:  # noqa: BLE001
            erro(self, e)
            return
        quem = self.operador.currentText() if self.ctx.eh_gerente else self.ctx.usuario.get("nome", "")
        mostrar_e_imprimir(self, self.ctx, f"Fechamento(s) — {self.dia.date().toString('dd/MM/yyyy')} — {quem}", r["linhas"])


# =============================================================================
class PaginaCaixa(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.turno: dict | None = None
        lay = QVBoxLayout(self)
        lay.addWidget(_titulo("Caixa"))
        self.estado = QLabel()
        self.estado.setProperty("papel", "aviso")
        self.estado.setWordWrap(True)
        lay.addWidget(self.estado)
        g = QGridLayout()
        self.btn_abrir = botao("Abrir caixa", self.abrir, "primario")
        self.btn_sangria = botao("Sangria (retirada)", lambda: self.movimento("SANGRIA"))
        self.btn_suprimento = botao("Suprimento (reforço)", lambda: self.movimento("SUPRIMENTO"))
        self.btn_despesa = botao("Pagar despesa com a gaveta", self.despesa)
        self.btn_fechar = botao("Fechar caixa", self.fechar, "perigo")
        self.btn_relatorio = botao("Imprimir parcial (gerente)", self.parcial)
        self.btn_reimprimir = botao("Imprimir fechamento (por dia)", lambda: DialogoFechamentos(self.ctx, self).exec())
        for i, b in enumerate((self.btn_abrir, self.btn_sangria, self.btn_suprimento, self.btn_despesa,
                               self.btn_fechar, self.btn_relatorio, self.btn_reimprimir)):
            b.setMinimumHeight(54)
            g.addWidget(b, i // 3, i % 3)
        lay.addLayout(g)
        self.resumo = QTableWidget()
        lay.addWidget(self.resumo, 1)

    def ao_mostrar(self):
        self.atualizar()

    def atualizar(self):
        try:
            self.turno = self.ctx.pdv.turno_atual()
        except Exception as e:  # noqa: BLE001
            self.estado.setText(f"Erro ao consultar o caixa: {e}")
            return
        aberto = self.turno is not None
        for b in (self.btn_sangria, self.btn_suprimento, self.btn_despesa, self.btn_fechar):
            b.setEnabled(aberto)
        self.btn_abrir.setEnabled(not aberto)
        self.btn_relatorio.setEnabled(aberto and self.ctx.eh_gerente and not self.turno.get("offline"))
        if not aberto:
            self.estado.setText("Caixa FECHADO. Abra o caixa informando o fundo de troco para começar a vender.")
            preencher_tabela(self.resumo, ["", ""], [])
            return
        if self.turno.get("offline"):
            self.estado.setText("Caixa ABERTO (sem internet: o resumo aparece quando a conexão voltar).")
            return
        r = self.turno.get("resumo", {})
        self.estado.setText(f"Caixa ABERTO por {r.get('operador', '')} desde {self.turno['aberto_em'][11:16]} — "
                            f"fundo de troco {reais(self.turno['valor_abertura_centavos'])} — "
                            f"{r.get('quantidade_vendas', 0)} venda(s).")
        linhas = [[k.replace("_", " ").title(), reais(v)] for k, v in (r.get("totais_por_tipo") or {}).items()]
        if "esperado" in r:
            linhas += [["— esperado " + FORMAS.get(k, k), reais(v)] for k, v in r["esperado"].items()]
        d = r.get("delivery")  # gerente/administrador: delivery do período deste caixa
        if d and d.get("pedidos"):
            linhas += [["", ""], [f"🛵 DELIVERY — {d['pedidos']} entrega(s)", reais(d["total_centavos"])],
                       ["— taxas de entrega", reais(d["taxas_centavos"])],
                       ["— pago online", reais(d["online_centavos"])],
                       ["— recebido na entrega", reais(d["na_entrega_centavos"])]]
            linhas += [[f"     na entrega · {FORMAS.get(k, k)}", reais(v)] for k, v in d.get("na_entrega", {}).items()]
            if d.get("a_receber_centavos"):
                linhas.append(["— A RECEBER (entregue sem pagamento)", reais(d["a_receber_centavos"])])
            linhas += [[f"     {e['entregador']} ({e['entregas']})", reais(e["total_centavos"])] for e in d.get("por_entregador", [])]
        preencher_tabela(self.resumo, ["Movimento", "Valor"], linhas)

    def abrir(self):
        d = DialogoValor("Abrir caixa", "Fundo de troco (R$)", parent=self)
        d.valor.setText("0,00")
        if d.exec():
            if seguro(self, self.ctx.pdv.abrir_caixa, d.centavos()) is not None:
                self.ctx.status("Caixa aberto")
        self.atualizar()

    def movimento(self, tipo: str):
        nome = "Sangria" if tipo == "SANGRIA" else "Suprimento"
        d = DialogoValor(nome, texto="ex.: depósito no cofre" if tipo == "SANGRIA" else "ex.: troco extra", parent=self)
        if d.exec():
            if tipo == "SANGRIA" and not d.motivo():
                erro(self, "Informe o motivo da sangria.")
                return
            if seguro(self, self.ctx.pdv.movimento_caixa, self.turno["id"], tipo, d.centavos(), d.motivo()) is not None:
                self.ctx.status(f"{nome} de {reais(d.centavos())} registrada")
                try:
                    from apfood_core.cupom import Linha

                    self.ctx.imprimir([Linha(nome.upper(), negrito=True, alinhamento="centro"),
                                       Linha(f"Valor: {reais(d.centavos())}"), Linha(f"Motivo: {d.motivo()}"),
                                       Linha(f"Operador: {self.ctx.usuario.get('nome', '')}"), Linha(),
                                       Linha("_" * 30, alinhamento="centro"), Linha("Assinatura", alinhamento="centro"),
                                       Linha(corte=True)], gaveta=True)
                except Exception:  # noqa: BLE001
                    pass
        self.atualizar()

    def despesa(self):
        d = DialogoValor("Despesa paga com dinheiro do caixa", texto="descrição (ex.: gás, gelo)", parent=self)
        if d.exec():
            if not d.motivo():
                erro(self, "Descreva a despesa.")
                return
            seguro(self, self.ctx.pdv.despesa_caixa, self.turno["id"], d.motivo(), d.centavos())
        self.atualizar()

    def fechar(self):
        esperado = (self.turno.get("resumo") or {}).get("esperado")  # só gerente recebe
        d = DialogoFechamento(esperado if self.ctx.eh_gerente else None, self)
        if not d.exec():
            return
        r = seguro(self, self.ctx.pdv.fechar_caixa, self.turno["id"], d.informado(),
                   "DETALHADA" if esperado and self.ctx.eh_gerente else "CEGA", d.obs.toPlainText().strip())
        if r is None:
            return
        if r.get("offline"):
            self.ctx.status("Fechamento registrado offline — o resultado sai quando a internet voltar")
        else:
            dif = r.get("diferenca_centavos") or 0
            self.ctx.status(f"Caixa fechado: {r.get('situacao')} {reais(dif)}")
            try:
                linhas = self.ctx.api.get(f"/api/turnos/{self.turno['id']}/cupom/", largura=self.ctx.cfg.largura_bobina)["linhas"]
                self.ctx.imprimir(linhas)
                DialogoTexto("Fechamento de caixa", para_texto(linhas, self.ctx.cfg.largura_bobina), self).exec()
            except Exception as e:  # noqa: BLE001
                self.ctx.status(f"Impressão: {e}")
        self.atualizar()

    def parcial(self):
        try:
            linhas = self.ctx.api.get(f"/api/turnos/{self.turno['id']}/cupom/", largura=self.ctx.cfg.largura_bobina)["linhas"]
            DialogoTexto("Parcial do caixa", para_texto(linhas, self.ctx.cfg.largura_bobina), self,
                         acoes=[("Imprimir", lambda: seguro(self, self.ctx.imprimir, linhas))]).exec()
        except Exception as e:  # noqa: BLE001
            erro(self, e)


# =============================================================================
class PaginaCozinha(QWidget):
    """Tela da cozinha (KDS) por setor: toque no item para avançar."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        topo.addWidget(_titulo("Cozinha"))
        topo.addStretch()
        self.setor = QComboBox()
        self.setor.currentIndexChanged.connect(lambda *_: self.atualizar())
        topo.addWidget(QLabel("Setor"))
        topo.addWidget(self.setor)
        lay.addLayout(topo)
        self.grade_w = QWidget()
        self.grade = QGridLayout(self.grade_w)
        self.grade.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self.grade_w, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(10000)
        self.timer.timeout.connect(self.atualizar)

    def ao_mostrar(self):
        atual = self.setor.currentData()
        self.setor.blockSignals(True)
        self.setor.clear()
        self.setor.addItem("Todos", None)
        for s in self.ctx.banco.listar("setores"):
            self.setor.addItem(s["nome"], s["id"])
        i = self.setor.findData(atual)
        self.setor.setCurrentIndex(max(i, 0))
        self.setor.blockSignals(False)
        self.atualizar()
        self.timer.start()

    def atualizar(self):
        try:
            itens = self.ctx.api.get("/api/cozinha/", setor=self.setor.currentData())
        except SemConexao:
            return
        except Exception as e:  # noqa: BLE001
            self.ctx.status(f"Cozinha: {e}")
            return
        while self.grade.count():
            w = self.grade.takeAt(0).widget()
            if w:
                w.deleteLater()
        for n, i in enumerate(itens):
            p = i["pedido"]
            destino = f"Mesa {p['mesa']}" if p.get("mesa") else (p.get("nome_cliente") or p["tipo_atendimento"].title())
            extras = "\n".join(f"+ {a['quantidade']}x {a['nome']}" for a in i.get("adicionais", []))
            obs = f"\n*** {i['observacao']} ***" if i.get("observacao") else ""
            em_preparo = i["status_producao"] == "EM_PREPARO"
            b = QPushButton(f"#{p['numero']}  {destino}\n{i['quantidade']}x {i['nome_produto']}"
                            f"{' (' + i['nome_variacao'] + ')' if i.get('nome_variacao') else ''}\n{extras}{obs}\n"
                            f"[{'EM PREPARO → toque p/ PRONTO' if em_preparo else 'toque p/ INICIAR'}]")
            b.setMinimumSize(220, 130)
            b.setStyleSheet(f"text-align:left; padding:8px; font-size:15px; background:{'#FFF3E0' if em_preparo else 'white'};")
            b.clicked.connect(lambda _=False, item=i: self.avancar(item))
            self.grade.addWidget(b, n // 4, n % 4)
        if not itens:
            self.grade.addWidget(QLabel("Nada para preparar 🎉"), 0, 0)

    def avancar(self, item):
        seguro(self, self.ctx.api.post, f"/api/cozinha/{item['id']}/avancar/")
        self.atualizar()


# =============================================================================
class PaginaEstoque(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        topo.addWidget(_titulo("Estoque"))
        topo.addStretch()
        for rot, op in (("Entrada", "ENTRADA"), ("Perda / quebra", "PERDA"), ("Inventário (contagem)", "INVENTARIO")):
            topo.addWidget(botao(rot, lambda o=op: self.operacao(o)))
        topo.addWidget(botao("Atualizar", self.atualizar))
        lay.addLayout(topo)
        abas = QTabWidget()
        self.baixo = QTableWidget()
        self.todos = QTableWidget()
        self.kardex = QTableWidget()
        for t in (self.baixo, self.todos, self.kardex):
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
        abas.addTab(self.baixo, "Abaixo do mínimo")
        abas.addTab(self.todos, "Saldos")
        abas.addTab(self.kardex, "Movimentações")
        lay.addWidget(abas, 1)

    def ao_mostrar(self):
        self.atualizar()

    def _controlados(self):
        return sorted((p for p in self.ctx.banco.listar("produtos") if p.get("controla_estoque")), key=lambda p: p["nome"])

    def atualizar(self):
        if not self.ctx.eh_gerente:
            preencher_tabela(self.baixo, ["Aviso"], [["Estoque é restrito a gerentes."]])
            return
        try:
            baixo = self.ctx.api.get("/api/estoque/abaixo-do-minimo/")
            preencher_tabela(self.baixo, ["Produto", "Saldo", "Mínimo", "Unidade"],
                             [[p["nome"], p["estoque_atual"], p["estoque_minimo"], p["unidade"]] for p in baixo])
            mov = self.ctx.api.get("/api/estoque/", limit=200)
            mov = mov["results"] if isinstance(mov, dict) else mov
            preencher_tabela(self.kardex, ["Data", "Produto", "Tipo", "Qtd", "Saldo", "Motivo"],
                             [[m["criado_em"][:16].replace("T", " "), m["produto_nome"], m["tipo"], m["quantidade"],
                               m["saldo_posterior"], m.get("motivo", "")] for m in mov])
            prods = self.ctx.api.lista("/api/produtos/", controla_estoque="true")
        except SemConexao:
            prods = self._controlados()
        except Exception as e:  # noqa: BLE001
            erro(self, e)
            return
        preencher_tabela(self.todos, ["Produto", "Tipo", "Saldo", "Mínimo", "Unidade", "Custo médio"],
                         [[p["nome"], p["tipo"], p["estoque_atual"], p.get("estoque_minimo") or "", p["unidade"],
                           reais(p.get("custo_centavos")) if p.get("custo_centavos") else ""] for p in prods], prods)

    def operacao(self, op: str):
        produtos = [(f"{p['nome']} (saldo {p['estoque_atual']} {p['unidade']})", p) for p in self._controlados()]
        d = DialogoEscolha({"ENTRADA": "Entrada de", "PERDA": "Perda de", "INVENTARIO": "Contagem de"}[op], produtos, self)
        if not d.exec() or not d.valor():
            return
        p = d.valor()
        f = QWidget()
        from PySide6.QtWidgets import QDialog, QDialogButtonBox

        dlg = QDialog(self)
        dlg.setWindowTitle(p["nome"])
        form = QFormLayout(dlg)
        qtd = QLineEdit()
        qtd.setPlaceholderText("quantidade" if op != "INVENTARIO" else "saldo contado")
        custo = QLineEdit()
        custo.setPlaceholderText("custo unitário (R$)")
        motivo = QLineEdit()
        form.addRow("Quantidade" if op != "INVENTARIO" else "Saldo contado", qtd)
        if op == "ENTRADA":
            form.addRow("Custo unitário", custo)
        form.addRow("Motivo", motivo)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        del f
        if not dlg.exec():
            return
        from ..util import centavos

        corpo = {"produto": p["id"], "operacao": op, "quantidade": qtd.text().replace(",", "."),
                 "motivo": motivo.text().strip()}
        if op == "ENTRADA" and custo.text().strip():
            corpo["custo_unitario_centavos"] = centavos(custo.text())
        if seguro(self, self.ctx.api.post, "/api/estoque/operacao/", corpo) is not None:
            self.ctx.status("Estoque atualizado")
        self.atualizar()


# =============================================================================
class PaginaRelatorios(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        topo.addWidget(_titulo("Relatórios"))
        topo.addStretch()
        self.periodo = QComboBox()
        for rot, v in (("Hoje", "dia"), ("Esta semana", "semana"), ("Este mês", "mes"), ("Personalizado", "")):
            self.periodo.addItem(rot, v)
        self.inicio, self.fim = _data(date.today() - timedelta(days=7)), _data(date.today())
        self._ajustando = False
        self.periodo.currentIndexChanged.connect(self._ajustar_datas)
        for d_ in (self.inicio, self.fim):
            d_.dateChanged.connect(self._personalizado)
        self.operador = QComboBox()
        self.operador.addItem("Todos os operadores", "")
        topo.addWidget(self.periodo)
        topo.addWidget(QLabel("De"))
        topo.addWidget(self.inicio)
        topo.addWidget(QLabel("até"))
        topo.addWidget(self.fim)
        topo.addWidget(self.operador)
        topo.addWidget(botao("Gerar", self.atualizar, "primario"))
        lay.addLayout(topo)
        self._ajustar_datas()
        impr = QHBoxLayout()
        impr.addStretch()
        impr.addWidget(botao("🖨 Imprimir relatório de faturamento", self.imprimir_faturamento, "primario"))
        impr.addWidget(botao("🖨 Imprimir fechamentos de caixa", lambda: DialogoFechamentos(self.ctx, self).exec()))
        lay.addLayout(impr)
        self.cards = QHBoxLayout()
        self.lbl = {k: QLabel("—") for k in ("fat", "ped", "ticket", "canc")}
        for k, rot in (("fat", "Faturamento"), ("ped", "Pedidos"), ("ticket", "Ticket médio"), ("canc", "Cancelados")):
            box = QGroupBox(rot)
            v = QVBoxLayout(box)
            self.lbl[k].setProperty("papel", "total")
            v.addWidget(self.lbl[k])
            self.cards.addWidget(box)
        lay.addLayout(self.cards)
        abas = QTabWidget()
        self.t_dia, self.t_canal, self.t_forma = QTableWidget(), QTableWidget(), QTableWidget()
        self.t_abc, self.t_fech, self.t_fluxo = QTableWidget(), QTableWidget(), QTableWidget()
        for t, rot in ((self.t_dia, "Por dia"), (self.t_canal, "Canais"), (self.t_forma, "Formas de pagamento"),
                       (self.t_abc, "Curva ABC"), (self.t_fech, "Fechamentos de caixa"), (self.t_fluxo, "Fluxo de caixa")):
            abas.addTab(t, rot)
        lay.addWidget(abas, 1)

    def ao_mostrar(self):
        if self.ctx.eh_gerente:
            self.atualizar()
        else:
            self.lbl["fat"].setText("restrito a gerentes")

    def _personalizado(self, *_):
        if not self._ajustando and self.periodo.currentData():
            self.periodo.blockSignals(True)
            self.periodo.setCurrentIndex(self.periodo.findData(""))
            self.periodo.blockSignals(False)

    def _ajustar_datas(self, *_):
        """Escolher Hoje/Semana/Mês já preenche as datas (DD/MM/AAAA); mexer nas datas vira Personalizado."""
        hoje = date.today()
        v = self.periodo.currentData()
        ini = {"dia": hoje, "semana": hoje - timedelta(days=hoje.weekday()), "mes": hoje.replace(day=1)}.get(v)
        if ini:
            self._ajustando = True
            self.inicio.setDate(QDate(ini.year, ini.month, ini.day))
            self.fim.setDate(QDate(hoje.year, hoje.month, hoje.day))
            self._ajustando = False

    def _params(self) -> dict:
        if self.periodo.currentData():
            return {"periodo": self.periodo.currentData()}
        return {"inicio": self.inicio.date().toString("yyyy-MM-dd"), "fim": self.fim.date().toString("yyyy-MM-dd")}

    def imprimir_faturamento(self):
        """Relatório de faturamento do período (DD/MM/AAAA), de todos ou de um operador, na impressora do caixa."""
        if not self.ctx.eh_gerente:
            erro(self, "O relatório de faturamento é para gerente/administrador.")
            return
        p = {"inicio": self.inicio.date().toString("dd/MM/yyyy"), "fim": self.fim.date().toString("dd/MM/yyyy"),
             "largura": self.ctx.cfg.largura_bobina}
        if self.operador.currentData():
            p["operador"] = self.operador.currentData()
        r = seguro(self, self.ctx.api.get, "/api/relatorios/faturamento/", **p)
        if r:
            self._preencher_operadores(r.get("operadores", []))
            mostrar_e_imprimir(self, self.ctx, f"Faturamento {p['inicio']} a {p['fim']}", r["linhas"])

    def _preencher_operadores(self, ops):
        if self.operador.count() > 1:
            return
        for o in ops:
            self.operador.addItem(o["nome"], o["id"])

    def atualizar(self):
        p = self._params()
        api = self.ctx.api
        v = seguro(self, api.get, "/api/relatorios/vendas/", **p)
        if not v:
            return
        if self.operador.count() == 1:
            try:
                self._preencher_operadores(api.get("/api/turnos/fechamentos/", **p).get("operadores", []))
            except Exception:  # noqa: BLE001
                pass
        self.lbl["fat"].setText(reais(v["faturamento_centavos"]))
        self.lbl["ped"].setText(str(v["pedidos"]))
        self.lbl["ticket"].setText(reais(v["ticket_medio_centavos"]))
        self.lbl["canc"].setText(str(v["cancelados"]))
        preencher_tabela(self.t_dia, ["Data", "Faturamento", "Pedidos", "Ticket médio"],
                         [[d["data"], reais(d["faturamento_centavos"]), d["pedidos"], reais(d["ticket_medio_centavos"])]
                          for d in v["por_dia"]])
        preencher_tabela(self.t_canal, ["Canal", "Faturamento", "Pedidos", "%"],
                         [[CANAIS.get(c["canal"], c["canal"]), reais(c["faturamento_centavos"]), c["pedidos"],
                           f"{c['percentual']}%"] for c in v["por_canal"]])
        preencher_tabela(self.t_forma, ["Forma", "Bruto", "Taxas", "Líquido", "Qtd"],
                         [[FORMAS.get(f["forma"], f["forma"]), reais(f["bruto_centavos"]), reais(f["taxas_centavos"]),
                           reais(f["liquido_centavos"]), f["quantidade"]] for f in v["por_forma_pagamento"]])
        if abc := seguro(self, api.get, "/api/relatorios/curva-abc/", **p):
            preencher_tabela(self.t_abc, ["Classe", "Produto", "Qtd", "Faturamento", "%", "Acumulado"],
                             [[i["classe"], i["nome"], i["quantidade"], reais(i["faturamento_centavos"]),
                               f"{i['percentual']}%", f"{i['acumulado']}%"] for i in abc["itens"]])
        if f := seguro(self, api.get, "/api/relatorios/fechamentos/", **p):
            preencher_tabela(self.t_fech, ["Fechado em", "Operador", "Esperado", "Informado", "Diferença", "Situação"],
                             [[t["fechado_em"][:16].replace("T", " "), t["operador"], reais(t["total_esperado_centavos"]),
                               reais(t["total_informado_centavos"]), reais(t["diferenca_centavos"]),
                               "SOBRA" if (t["diferenca_centavos"] or 0) > 0 else "QUEBRA" if (t["diferenca_centavos"] or 0) < 0
                               else "OK"] for t in f["turnos"]])
        if fl := seguro(self, api.get, "/api/relatorios/fluxo-caixa/", **p):
            preencher_tabela(self.t_fluxo, ["Data", "Entradas brutas", "Taxas", "Entradas líquidas", "Saídas", "Saldo"],
                             [[d["data"], reais(d["entradas_brutas_centavos"]), reais(d["taxas_centavos"]),
                               reais(d["entradas_liquidas_centavos"]), reais(d["saidas_centavos"]), reais(d["saldo_centavos"])]
                              for d in fl["dias"]]
                             + [["A receber", "", "", reais(fl["a_receber_centavos"]), "", ""],
                                ["A pagar", "", "", "", reais(fl["a_pagar_centavos"]), ""]])


# =============================================================================
class SeletorImpressora(QWidget):
    """Impressora instalada no PC (lista) ou digitada (IP:porta, arquivo:...), e o modo:
    térmica ESC/POS (RAW: corta o papel e abre a gaveta) ou comum (driver do Windows: qualquer impressora)."""

    MODOS = [("Térmica (ESC/POS)", "raw"), ("Comum (driver do Windows)", "driver")]

    def __init__(self, valor: str, vazio: str = "", parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QComboBox, QHBoxLayout

        from ...impressao_qt import impressoras_instaladas

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.nome = QComboBox()
        self.nome.setEditable(True)
        self.nome.setMinimumWidth(320)
        self.nome.addItem("")
        self.nome.addItems(impressoras_instaladas())
        self.nome.lineEdit().setPlaceholderText(vazio or "escolha na lista, ou digite 192.168.0.50:9100 / arquivo:C:/cupons")
        self.modo = QComboBox()
        for rot, v in self.MODOS:
            self.modo.addItem(rot, v)
        valor = (valor or "").strip()
        driver = valor.startswith("windows:")
        self.nome.setCurrentText(valor.removeprefix("windows:"))
        self.modo.setCurrentIndex(1 if driver else 0)
        self.nome.currentTextChanged.connect(self._ajustar)
        h.addWidget(self.nome, 1)
        h.addWidget(self.modo)
        self._ajustar()

    @staticmethod
    def _rede_ou_arquivo(t: str) -> bool:
        host, _, porta = t.rpartition(":")
        return t.startswith("arquivo:") or bool(host and porta.isdigit())

    def _ajustar(self, *_):
        self.modo.setEnabled(bool(self.nome.currentText().strip()) and not self._rede_ou_arquivo(self.nome.currentText().strip()))

    def valor(self) -> str:
        t = self.nome.currentText().strip()
        if not t or self._rede_ou_arquivo(t) or self.modo.currentData() == "raw":
            return t
        return f"windows:{t}"


class PaginaConfig(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        cfg = ctx.cfg
        lay = QVBoxLayout(self)
        lay.addWidget(_titulo("Configurações deste computador"))
        f = QFormLayout()
        self.terminal = QLineEdit(cfg.nome_terminal)
        self.imp_caixa = SeletorImpressora(cfg.impressora_caixa)
        self.imp_cozinha = SeletorImpressora(cfg.impressora_cozinha_padrao, "vazio = usa a do setor ou a do caixa")
        self.bobina = QComboBox()
        self.bobina.addItem("80 mm (48 colunas)", 48)
        self.bobina.addItem("58 mm (32 colunas)", 32)
        self.bobina.setCurrentIndex(0 if cfg.largura_bobina == 48 else 1)
        self.auto_cozinha = QCheckBox("Imprimir via da cozinha ao lançar/aceitar pedido")
        self.auto_cozinha.setChecked(cfg.imprimir_cozinha_automatico)
        self.som = QCheckBox("Alerta sonoro para pedido online")
        self.som.setChecked(cfg.som_novo_pedido)
        self.sync = QSpinBox()
        self.sync.setRange(2, 120)
        self.sync.setValue(cfg.intervalo_sync_s)
        f.addRow("Nome do terminal", self.terminal)
        f.addRow("Impressora do caixa", self.imp_caixa)
        f.addRow("Impressora da cozinha", self.imp_cozinha)
        dica = QLabel("Térmica (ESC/POS): corta o papel e abre a gaveta. Comum: qualquer impressora instalada no "
                      "Windows (laser, jato de tinta ou térmica só com driver).")
        dica.setWordWrap(True)
        dica.setStyleSheet("color:#66666d")
        f.addRow("", dica)
        f.addRow("Bobina", self.bobina)
        f.addRow(self.auto_cozinha)
        f.addRow(self.som)
        f.addRow("Sincronizar a cada (s)", self.sync)
        f.addRow("Servidor", QLabel(cfg.api_url))
        lay.addLayout(f)
        h = QHBoxLayout()
        h.addWidget(botao("Salvar", self.salvar, "primario"))
        h.addWidget(botao("Testar impressora do caixa", self.teste))
        h.addWidget(botao("Testar da cozinha", lambda: self.teste(cozinha=True)))
        h.addWidget(botao("Sincronizar cardápio agora", self.sincronizar))
        h.addWidget(botao("Operações recusadas pelo servidor", self.rejeitadas))
        h.addStretch()
        lay.addLayout(h)
        lay.addStretch()

    def ao_mostrar(self):
        pass

    def salvar(self):
        c = self.ctx.cfg
        c.nome_terminal, c.impressora_caixa = self.terminal.text().strip() or "Caixa 1", self.imp_caixa.valor()
        c.impressora_cozinha_padrao, c.largura_bobina = self.imp_cozinha.valor(), self.bobina.currentData()
        c.imprimir_cozinha_automatico, c.som_novo_pedido = self.auto_cozinha.isChecked(), self.som.isChecked()
        c.intervalo_sync_s = self.sync.value()
        c.salvar()
        self.ctx.status("Configurações salvas")

    def teste(self, cozinha: bool = False):
        from apfood_core.cupom import Linha

        from ...impressao import descrever

        self.salvar()
        destino = (self.ctx.cfg.impressora_cozinha_padrao or self.ctx.cfg.impressora_caixa) if cozinha else self.ctx.cfg.impressora_caixa
        linhas = [Linha("APFOOD - TESTE DE IMPRESSAO", negrito=True, alinhamento="centro"),
                  Linha(f"Impressora: {descrever(destino)}"[: self.bobina.currentData()]),
                  Linha("Acentuação: ação, café, pão, maçã"), Linha("-" * self.bobina.currentData()),
                  Linha("Texto grande", grande=True), Linha("https://apfood.app", qrcode=True), Linha(corte=True)]
        if seguro(self, self.ctx.imprimir, linhas, destino) is not None:
            self.ctx.status(f"Teste enviado para {descrever(destino)}")

    def sincronizar(self):
        r = seguro(self, self.ctx.sincronizador.ciclo)
        if r is not None:
            self.ctx.status(f"Sincronizado: {r['enviados']} enviados, {r['recebidos']} recebidos")

    def rejeitadas(self):
        rej = self.ctx.banco.rejeitadas()
        texto = "\n\n".join(f"{r.get('rejeitada_em', '')}  {r['operacao']}\n  motivo: {r.get('ultimo_erro', '')}" for r in rej) \
            or "Nenhuma operação recusada."
        DialogoTexto("Operações recusadas", texto, self).exec()
