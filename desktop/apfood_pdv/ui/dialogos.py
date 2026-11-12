"""Diálogos reutilizáveis do PDV."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .util import FORMAS, botao, centavos, reais


def _botoes(dialogo: QDialog, ok: str = "Confirmar") -> QDialogButtonBox:
    caixa = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    caixa.button(QDialogButtonBox.Ok).setText(ok)
    caixa.button(QDialogButtonBox.Ok).setProperty("papel", "primario")
    caixa.button(QDialogButtonBox.Cancel).setText("Cancelar")
    caixa.accepted.connect(dialogo.accept)
    caixa.rejected.connect(dialogo.reject)
    return caixa


# =============================================================================
class DialogoValor(QDialog):
    """Pede um valor em reais (e opcionalmente um texto)."""

    def __init__(self, titulo: str, rotulo: str = "Valor (R$)", *, texto: str | None = None, parent=None,
                 valor_inicial: int = 0):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        f = QFormLayout(self)
        self.valor = QLineEdit(reais(valor_inicial).replace("R$ ", "") if valor_inicial else "")
        self.valor.setPlaceholderText("0,00")
        f.addRow(rotulo, self.valor)
        self.texto = None
        if texto is not None:
            self.texto = QLineEdit()
            self.texto.setPlaceholderText(texto)
            f.addRow("Motivo", self.texto)
        f.addRow(_botoes(self))
        self.valor.setFocus()

    def accept(self):
        try:
            if self.centavos() <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "ApFood", "Informe um valor válido.")
            return
        super().accept()

    def centavos(self) -> int:
        return centavos(self.valor.text())

    def motivo(self) -> str:
        return self.texto.text().strip() if self.texto else ""


# =============================================================================
class DialogoItem(QDialog):
    """Monta o item: tamanho, sabores (meio a meio), adicionais, quantidade, observação."""

    def __init__(self, pdv, produto: dict, parent=None):
        super().__init__(parent)
        self.pdv, self.produto = pdv, produto
        self.setWindowTitle(produto["nome"])
        self.setMinimumWidth(460)
        raiz = QVBoxLayout(self)
        corpo = QWidget()
        lay = QVBoxLayout(corpo)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setWidget(corpo)
        raiz.addWidget(rolagem)

        # tamanho
        self.variacoes = pdv.variacoes(produto["id"])
        self.grupo_var = QButtonGroup(self)
        if self.variacoes:
            box = QGroupBox("Tamanho *")
            h = QHBoxLayout(box)
            for i, v in enumerate(self.variacoes):
                rb = QRadioButton(f"{v['nome']}  {reais(v['preco_centavos'])}")
                self.grupo_var.addButton(rb, i)
                h.addWidget(rb)
                rb.toggled.connect(self._atualizar)
            self.grupo_var.button(0).setChecked(True)
            lay.addWidget(box)

        # sabores
        cat = pdv.banco.obter("categorias", produto.get("categoria")) or {}
        self.max_sabores = int(cat.get("max_sabores") or 1)
        self.lista_sabores = None
        if self.max_sabores > 1:
            box = QGroupBox(f"Sabores (até {self.max_sabores}) — o primeiro é {produto['nome']}")
            v = QVBoxLayout(box)
            self.lista_sabores = QListWidget()
            for p in pdv.produtos(produto.get("categoria")):
                if p["id"] == produto["id"]:
                    continue
                it = QListWidgetItem(p["nome"])
                it.setData(Qt.UserRole, p["id"])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked)
                self.lista_sabores.addItem(it)
            self.lista_sabores.itemChanged.connect(self._limitar_sabores)
            self.lista_sabores.setMaximumHeight(140)
            v.addWidget(self.lista_sabores)
            lay.addWidget(box)

        # adicionais
        self.grupos = pdv.grupos_do_produto(produto)
        self.spins: list[tuple[dict, dict, QSpinBox]] = []
        for g in self.grupos:
            obrig = f" * (mín. {g['min_selecao']})" if g["min_selecao"] else ""
            box = QGroupBox(f"{g['nome']}{obrig} — até {g['max_selecao']}")
            grid = QGridLayout(box)
            for r, a in enumerate(g["opcoes"]):
                preco = f"  +{reais(a['preco_centavos'])}" if a.get("preco_centavos") else ""
                grid.addWidget(QLabel(a["nome"] + preco), r, 0)
                sp = QSpinBox()
                sp.setRange(0, int(a.get("max_por_item") or 1))
                sp.valueChanged.connect(self._atualizar)
                grid.addWidget(sp, r, 1)
                self.spins.append((g, a, sp))
            lay.addWidget(box)

        form = QFormLayout()
        self.qtd = QSpinBox()
        self.qtd.setRange(1, 99)
        self.qtd.valueChanged.connect(self._atualizar)
        form.addRow("Quantidade", self.qtd)
        self.obs = QLineEdit()
        self.obs.setPlaceholderText("ex.: sem cebola, bem passado")
        form.addRow("Observação", self.obs)
        lay.addLayout(form)

        self.total = QLabel()
        self.total.setProperty("papel", "total")
        raiz.addWidget(self.total, alignment=Qt.AlignRight)
        raiz.addWidget(_botoes(self, "Adicionar"))
        self._atualizar()

    def _limitar_sabores(self, _item=None):
        marcados = [self.lista_sabores.item(i) for i in range(self.lista_sabores.count())
                    if self.lista_sabores.item(i).checkState() == Qt.Checked]
        if len(marcados) + 1 > self.max_sabores:
            self.lista_sabores.blockSignals(True)
            marcados[-1].setCheckState(Qt.Unchecked)
            self.lista_sabores.blockSignals(False)
        self._atualizar()

    def item(self) -> dict:
        var = self.variacoes[self.grupo_var.checkedId()] if self.variacoes else None
        sabores = []
        if self.lista_sabores is not None:
            extras = [self.lista_sabores.item(i).data(Qt.UserRole) for i in range(self.lista_sabores.count())
                      if self.lista_sabores.item(i).checkState() == Qt.Checked]
            if extras:
                sabores = [self.produto["id"], *extras]
        adicionais = [{"adicional_id": a["id"], "quantidade": sp.value()} for _, a, sp in self.spins if sp.value()]
        return {"produto_id": self.produto["id"], "quantidade": self.qtd.value(),
                "variacao_id": var["id"] if var else None, "sabores": sabores, "adicionais": adicionais,
                "observacao": self.obs.text().strip()}

    def descricao(self) -> str:
        it, nome = self.item(), self.produto["nome"]
        if it["sabores"]:
            nomes = [(self.pdv.banco.obter("produtos", s) or {}).get("nome", "?") for s in it["sabores"]]
            nome = " / ".join(f"1/{len(nomes)} {n}" for n in nomes)
        if it["variacao_id"]:
            nome += f" ({self.variacoes[self.grupo_var.checkedId()]['nome']})"
        extras = [f"+{sp.value()}x {a['nome']}" for _, a, sp in self.spins if sp.value()]
        return " ".join([nome, *extras])

    def _erros(self) -> list[str]:
        erros = []
        for g in self.grupos:
            n = sum(sp.value() for gg, _, sp in self.spins if gg is g)
            if n < g["min_selecao"]:
                erros.append(f"{g['nome']}: escolha ao menos {g['min_selecao']}")
            if n > g["max_selecao"]:
                erros.append(f"{g['nome']}: no máximo {g['max_selecao']}")
        return erros

    def _atualizar(self, *_):
        self.total.setText(reais(self.pdv.precificar_item(self.item())))

    def accept(self):
        if erros := self._erros():
            QMessageBox.warning(self, "ApFood", "\n".join(erros))
            return
        super().accept()


# =============================================================================
class DialogoPagamento(QDialog):
    """Recebe um ou vários pagamentos (dividir em formas). Para dinheiro, calcula troco.

    Resultado: `self.pagamentos` = [{forma, valor_centavos, recebido_centavos, bandeira}].
    `pix_fn(valor)` opcional: gera cobrança Pix dinâmica e devolve {qr_code,...}.
    """

    FORMAS_PDV = ["DINHEIRO", "PIX", "CARTAO_DEBITO", "CARTAO_CREDITO", "VOUCHER", "OUTRO"]

    def __init__(self, total_centavos: int, *, ja_pago: int = 0, pix_fn=None, parent=None, permitir_pendente=False):
        super().__init__(parent)
        self.setWindowTitle("Receber pagamento")
        self.setMinimumWidth(420)
        self.total, self.pagamentos, self.pix_fn = total_centavos, [], pix_fn
        self.ja_pago = ja_pago
        self.pendente = False
        lay = QVBoxLayout(self)
        self.rotulo = QLabel()
        self.rotulo.setProperty("papel", "total")
        lay.addWidget(self.rotulo)
        grade = QGridLayout()
        self.forma_btn = QButtonGroup(self)
        for i, f in enumerate(self.FORMAS_PDV):
            b = QPushButton(FORMAS[f])
            b.setCheckable(True)
            b.setMinimumHeight(44)
            self.forma_btn.addButton(b, i)
            grade.addWidget(b, i // 3, i % 3)
        self.forma_btn.button(0).setChecked(True)
        self.forma_btn.idToggled.connect(lambda *_: self._forma())
        lay.addLayout(grade)
        f = QFormLayout()
        self.valor = QLineEdit()
        self.recebido = QLineEdit()
        self.recebido.setPlaceholderText("valor entregue pelo cliente")
        self.recebido.textChanged.connect(self._troco)
        self.bandeira = QComboBox()
        self.bandeira.addItems(["", "Visa", "Mastercard", "Elo", "Hipercard", "Amex", "Alelo", "Sodexo", "VR", "Ticket"])
        self.troco = QLabel()
        f.addRow("Valor (R$)", self.valor)
        f.addRow("Recebido (R$)", self.recebido)
        f.addRow("Bandeira", self.bandeira)
        f.addRow("Troco", self.troco)
        lay.addLayout(f)
        self.lista = QListWidget()
        self.lista.setMaximumHeight(100)
        lay.addWidget(self.lista)
        h = QHBoxLayout()
        h.addWidget(botao("Adicionar pagamento", self._adicionar))
        self.btn_pix = botao("Gerar Pix (QR)", self._pix)
        h.addWidget(self.btn_pix)
        if permitir_pendente:
            h.addWidget(botao("Pagar na entrega", self._na_entrega))
        lay.addLayout(h)
        lay.addWidget(_botoes(self, "Finalizar"))
        self._atualizar()
        self._forma()

    @property
    def restante(self) -> int:
        return self.total - self.ja_pago - sum(p["valor_centavos"] for p in self.pagamentos)

    def _forma_atual(self) -> str:
        return self.FORMAS_PDV[self.forma_btn.checkedId()]

    def _forma(self):
        dinheiro = self._forma_atual() == "DINHEIRO"
        self.recebido.setEnabled(dinheiro)
        self.bandeira.setEnabled(self._forma_atual() in ("CARTAO_DEBITO", "CARTAO_CREDITO", "VOUCHER"))
        self.btn_pix.setVisible(self._forma_atual() == "PIX" and self.pix_fn is not None)
        self._troco()

    def _troco(self):
        try:
            v, r = centavos(self.valor.text()), centavos(self.recebido.text())
        except ValueError:
            self.troco.setText("—")
            return
        self.troco.setText(reais(max(0, r - v)) if r else "—")

    def _atualizar(self):
        self.rotulo.setText(f"Falta: {reais(self.restante)}  (total {reais(self.total)})")
        self.valor.setText(reais(self.restante).replace("R$ ", "") if self.restante > 0 else "")
        self.lista.clear()
        for p in self.pagamentos:
            self.lista.addItem(f"{FORMAS[p['forma']]}  {reais(p['valor_centavos'])}")

    def _adicionar(self) -> bool:
        try:
            v = centavos(self.valor.text())
            r = centavos(self.recebido.text()) if self.recebido.isEnabled() and self.recebido.text() else None
        except ValueError:
            QMessageBox.warning(self, "ApFood", "Valor inválido.")
            return False
        if v <= 0 or v > self.restante:
            QMessageBox.warning(self, "ApFood", f"O valor deve ser entre R$ 0,01 e {reais(self.restante)}.")
            return False
        if r is not None and r < v:
            QMessageBox.warning(self, "ApFood", "O valor recebido é menor que o pagamento.")
            return False
        self.pagamentos.append({"forma": self._forma_atual(), "valor_centavos": v, "recebido_centavos": r,
                                "bandeira": self.bandeira.currentText() if self.bandeira.isEnabled() else ""})
        self.recebido.clear()
        self._atualizar()
        return True

    def _pix(self):
        try:
            v = centavos(self.valor.text())
            cob = self.pix_fn(v)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "ApFood", f"Não foi possível gerar o Pix: {exc}")
            return
        DialogoTexto("Pix copia e cola", cob.get("qr_code") or "", self,
                     rodape="Mostre o QR ao cliente. O pagamento é confirmado sozinho quando o banco avisar\n"
                            "(o pedido aparece como pago na fila).").exec()
        self.pix_gerado = cob
        self.pendente = True  # confirmação chega pelo webhook — não lançar Pix manual em duplicidade
        QDialog.accept(self)

    def _na_entrega(self):
        self.pendente = True
        super().accept()

    def accept(self):
        if self.restante > 0 and self.valor.text().strip():
            if not self._adicionar():
                return
        if self.restante > 0:
            QMessageBox.warning(self, "ApFood", f"Ainda falta {reais(self.restante)}.")
            return
        super().accept()

    def troco_total(self) -> int:
        return sum(max(0, (p["recebido_centavos"] or 0) - p["valor_centavos"]) for p in self.pagamentos
                   if p["forma"] == "DINHEIRO")


# =============================================================================
class DialogoFechamento(QDialog):
    """Contagem do caixa por forma de pagamento (conferência CEGA por padrão)."""

    FORMAS_CONTAGEM = ["DINHEIRO", "PIX", "CARTAO_CREDITO", "CARTAO_DEBITO", "VOUCHER"]

    def __init__(self, esperado: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fechar caixa")
        f = QFormLayout(self)
        if esperado is None:
            aviso = QLabel("Conte o dinheiro da gaveta e some os comprovantes de cada forma.\n"
                           "O valor esperado só aparece depois de confirmar (conferência cega).")
            aviso.setProperty("papel", "aviso")
            aviso.setWordWrap(True)
            f.addRow(aviso)
        self.campos = {}
        for forma in self.FORMAS_CONTAGEM:
            e = QLineEdit()
            e.setPlaceholderText("0,00")
            rot = FORMAS[forma] + (f"  (esperado {reais(esperado.get(forma, 0))})" if esperado else "")
            f.addRow(rot, e)
            self.campos[forma] = e
        self.obs = QPlainTextEdit()
        self.obs.setMaximumHeight(60)
        f.addRow("Observação", self.obs)
        f.addRow(_botoes(self, "Fechar caixa"))

    def informado(self) -> dict:
        return {forma: centavos(e.text()) for forma, e in self.campos.items()}

    def accept(self):
        try:
            self.informado()
        except ValueError:
            QMessageBox.warning(self, "ApFood", "Há valores inválidos.")
            return
        super().accept()


# =============================================================================
class DialogoTexto(QDialog):
    """Mostra um texto (prévia de cupom, Pix copia e cola...)."""

    def __init__(self, titulo: str, texto: str, parent=None, *, rodape: str = "", acoes: list | None = None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(460, 600)
        lay = QVBoxLayout(self)
        area = QPlainTextEdit(texto)
        area.setReadOnly(True)
        area.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        lay.addWidget(area)
        if rodape:
            lay.addWidget(QLabel(rodape))
        h = QHBoxLayout()
        for rotulo, fn in acoes or []:
            h.addWidget(botao(rotulo, fn))
        h.addStretch()
        h.addWidget(botao("Fechar", self.accept))
        lay.addLayout(h)


class DialogoEscolha(QDialog):
    """Escolher um item de uma lista (entregador, mesa, comanda...)."""

    def __init__(self, titulo: str, opcoes: list[tuple[str, object]], parent=None, *, motivo: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        lay = QVBoxLayout(self)
        self.lista = QListWidget()
        for rotulo, valor in opcoes:
            it = QListWidgetItem(rotulo)
            it.setData(Qt.UserRole, valor)
            self.lista.addItem(it)
        if opcoes:
            self.lista.setCurrentRow(0)
        self.lista.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.lista)
        self.motivo = None
        if motivo is not None:
            self.motivo = QLineEdit()
            self.motivo.setPlaceholderText(motivo)
            lay.addWidget(self.motivo)
        lay.addWidget(_botoes(self))

    def valor(self):
        it = self.lista.currentItem()
        return it.data(Qt.UserRole) if it else None


class DialogoConfirmarMotivo(QDialog):
    def __init__(self, titulo: str, pergunta: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(pergunta))
        self.motivo = QLineEdit()
        self.motivo.setPlaceholderText("motivo (obrigatório)")
        lay.addWidget(self.motivo)
        lay.addWidget(_botoes(self))

    def accept(self):
        if not self.motivo.text().strip():
            QMessageBox.warning(self, "ApFood", "Informe o motivo.")
            return
        super().accept()


class CampoCheck(QCheckBox):
    pass
