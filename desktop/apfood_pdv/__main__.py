"""python -m apfood_pdv — abre o PDV."""

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from . import __version__
from .config import Config
from .local_db import BancoLocal


class JanelaPrincipal(QMainWindow):
    def __init__(self, banco: BancoLocal):
        super().__init__()
        self.banco = banco
        self.setWindowTitle(f"ApFood PDV {__version__}")
        self.resize(1280, 800)
        # Passo 3: abas Pedidos online | Balcão | Delivery | Caixa | Estoque | Relatórios
        self.setCentralWidget(QLabel("ApFood PDV — em construção (Passo 3)"))
        self.statusBar().showMessage(f"Pendentes de sincronização: {banco.total_pendentes()}")


def main():
    cfg = Config()
    app = QApplication(sys.argv)
    janela = JanelaPrincipal(BancoLocal(cfg.caminho_db))
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
