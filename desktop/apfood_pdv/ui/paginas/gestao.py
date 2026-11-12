"""Caixa, cozinha (KDS), estoque, relatórios e configurações."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QTabWidget, QTableWidget, QVBoxLayout, QWidget,
)

from ...api import SemConexao
from ...impressao import para_texto
from ..dialogos import DialogoEscolha, DialogoFechamento, DialogoTexto, DialogoValor
from ..util import CANAIS, FORMAS, botao, dado_selecionado, erro, preencher_tabela, reais, seguro


def _titulo(texto: str) -> QLabel:
    t = QLabel(texto)
    t.setProperty("papel", "titulo")
    return t


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
        for i, b in enumerate((self.btn_abrir, self.btn_sangria, self.btn_suprimento, self.btn_despesa,
                               self.btn_fechar, self.btn_relatorio)):
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
        self.inicio, self.fim = QDateEdit(date.today() - timedelta(days=7)), QDateEdit(date.today())
        for d_ in (self.inicio, self.fim):
            d_.setCalendarPopup(True)
            d_.setDisplayFormat("dd/MM/yyyy")
        topo.addWidget(self.periodo)
        topo.addWidget(self.inicio)
        topo.addWidget(self.fim)
        topo.addWidget(botao("Gerar", self.atualizar, "primario"))
        lay.addLayout(topo)
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

    def _params(self) -> dict:
        if self.periodo.currentData():
            return {"periodo": self.periodo.currentData()}
        return {"inicio": self.inicio.date().toString("yyyy-MM-dd"), "fim": self.fim.date().toString("yyyy-MM-dd")}

    def atualizar(self):
        p = self._params()
        api = self.ctx.api
        v = seguro(self, api.get, "/api/relatorios/vendas/", **p)
        if not v:
            return
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
class PaginaConfig(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        cfg = ctx.cfg
        lay = QVBoxLayout(self)
        lay.addWidget(_titulo("Configurações deste computador"))
        f = QFormLayout()
        self.terminal = QLineEdit(cfg.nome_terminal)
        self.imp_caixa = QLineEdit(cfg.impressora_caixa)
        self.imp_caixa.setPlaceholderText('ex.: 192.168.0.50:9100  |  EPSON TM-T20  |  arquivo:C:/cupons')
        self.imp_cozinha = QLineEdit(cfg.impressora_cozinha_padrao)
        self.imp_cozinha.setPlaceholderText("vazio = usa a do setor ou a do caixa")
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
        f.addRow("Bobina", self.bobina)
        f.addRow(self.auto_cozinha)
        f.addRow(self.som)
        f.addRow("Sincronizar a cada (s)", self.sync)
        f.addRow("Servidor", QLabel(cfg.api_url))
        lay.addLayout(f)
        h = QHBoxLayout()
        h.addWidget(botao("Salvar", self.salvar, "primario"))
        h.addWidget(botao("Imprimir teste", self.teste))
        h.addWidget(botao("Sincronizar cardápio agora", self.sincronizar))
        h.addWidget(botao("Operações recusadas pelo servidor", self.rejeitadas))
        h.addStretch()
        lay.addLayout(h)
        lay.addStretch()

    def ao_mostrar(self):
        pass

    def salvar(self):
        c = self.ctx.cfg
        c.nome_terminal, c.impressora_caixa = self.terminal.text().strip() or "Caixa 1", self.imp_caixa.text().strip()
        c.impressora_cozinha_padrao, c.largura_bobina = self.imp_cozinha.text().strip(), self.bobina.currentData()
        c.imprimir_cozinha_automatico, c.som_novo_pedido = self.auto_cozinha.isChecked(), self.som.isChecked()
        c.intervalo_sync_s = self.sync.value()
        c.salvar()
        self.ctx.status("Configurações salvas")

    def teste(self):
        from apfood_core.cupom import Linha

        self.salvar()
        linhas = [Linha("APFOOD - TESTE DE IMPRESSAO", negrito=True, alinhamento="centro"),
                  Linha("Acentuação: ação, café, pão, maçã"), Linha("-" * self.bobina.currentData()),
                  Linha("Texto grande", grande=True), Linha("https://apfood.app", qrcode=True), Linha(corte=True)]
        seguro(self, self.ctx.imprimir, linhas)

    def sincronizar(self):
        r = seguro(self, self.ctx.sincronizador.ciclo)
        if r is not None:
            self.ctx.status(f"Sincronizado: {r['enviados']} enviados, {r['recebidos']} recebidos")

    def rejeitadas(self):
        rej = self.ctx.banco.rejeitadas()
        texto = "\n\n".join(f"{r.get('rejeitada_em', '')}  {r['operacao']}\n  motivo: {r.get('ultimo_erro', '')}" for r in rej) \
            or "Nenhuma operação recusada."
        DialogoTexto("Operações recusadas", texto, self).exec()
