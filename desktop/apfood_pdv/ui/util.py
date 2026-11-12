from __future__ import annotations

from collections.abc import Callable

from apfood_core.dinheiro import formatar, reais_para_centavos
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QWidget

from ..api import ErroApi, SemConexao

STATUS = {"PENDENTE": "Aguardando aceite", "RECEBIDO": "Recebido", "EM_PREPARO": "Em preparo", "PRONTO": "Pronto",
          "SAIU_PARA_ENTREGA": "Saiu p/ entrega", "CONCLUIDO": "Concluído", "CANCELADO": "Cancelado",
          "RECUSADO": "Recusado"}
CANAIS = {"ONLINE": "Online", "BALCAO": "Balcão", "DELIVERY": "Delivery", "MESA": "Mesa", "MARKETPLACE": "iFood"}
FORMAS = {"DINHEIRO": "Dinheiro", "PIX": "Pix", "CARTAO_CREDITO": "Crédito", "CARTAO_DEBITO": "Débito",
          "VOUCHER": "Vale-refeição", "MARKETPLACE": "Pago no app", "OUTRO": "Outro"}


def reais(c: int | None) -> str:
    return formatar(c or 0)


def centavos(texto: str) -> int:
    texto = (texto or "").strip()
    return reais_para_centavos(texto) if texto else 0


def botao(texto: str, ao_clicar: Callable | None = None, papel: str = "", atalho: str = "") -> QPushButton:
    b = QPushButton(texto)
    if papel:
        b.setProperty("papel", papel)
    if ao_clicar:
        b.clicked.connect(lambda *_: ao_clicar())
    if atalho:
        b.setShortcut(atalho)
        b.setToolTip(atalho)
    b.setCursor(Qt.PointingHandCursor)
    return b


def erro(parent: QWidget | None, exc: Exception | str) -> None:
    if isinstance(exc, SemConexao):
        msg = "Sem conexão com o servidor. A operação não pôde ser feita agora."
    elif isinstance(exc, ErroApi):
        msg = exc.mensagem
    else:
        msg = str(exc)
    QMessageBox.warning(parent, "ApFood", msg)


def confirmar(parent: QWidget, pergunta: str) -> bool:
    return QMessageBox.question(parent, "ApFood", pergunta) == QMessageBox.Yes


def seguro(parent: QWidget, fn: Callable, *a, **kw):
    """Executa uma ação mostrando o erro de forma amigável. Devolve None se falhar."""
    QGuiApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        return fn(*a, **kw)
    except Exception as exc:  # noqa: BLE001
        QGuiApplication.restoreOverrideCursor()
        erro(parent, exc)
        return None
    finally:
        if QGuiApplication.overrideCursor():
            QGuiApplication.restoreOverrideCursor()


def preencher_tabela(tabela: QTableWidget, cabecalho: list[str], linhas: list[list], dados: list | None = None) -> None:
    tabela.clear()
    tabela.setColumnCount(len(cabecalho))
    tabela.setHorizontalHeaderLabels(cabecalho)
    tabela.setRowCount(len(linhas))
    for r, linha in enumerate(linhas):
        for c, valor in enumerate(linha):
            item = QTableWidgetItem("" if valor is None else str(valor))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if dados is not None and c == 0:
                item.setData(Qt.UserRole, dados[r])
            tabela.setItem(r, c, item)
    tabela.resizeColumnsToContents()
    tabela.horizontalHeader().setStretchLastSection(True)


def dado_selecionado(tabela: QTableWidget):
    linha = tabela.currentRow()
    if linha < 0 or tabela.item(linha, 0) is None:
        return None
    return tabela.item(linha, 0).data(Qt.UserRole)
