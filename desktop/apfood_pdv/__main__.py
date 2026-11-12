"""python -m apfood_pdv  (ou ApFoodPDV.exe) — abre o PDV."""

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from .api import ApiClient, SemConexao
from .config import Config, pasta_dados
from .local_db import BancoLocal
from .ui.contexto import Contexto
from .ui.estilo import QSS


def main():
    logging.basicConfig(filename=str(pasta_dados() / "pdv.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName("ApFood PDV")
    app.setStyleSheet(QSS)
    from .ui.janela import DialogoLogin, JanelaPrincipal

    cfg = Config.carregar()
    ctx = Contexto(cfg, ApiClient(cfg.api_url), BancoLocal(cfg.caminho_db))
    if not ctx.restaurar_sessao():
        if not DialogoLogin(ctx).exec():
            return 0
    # primeira carga do cardápio (se o cache está vazio)
    if not ctx.banco.listar("produtos"):
        try:
            ctx.sincronizador.pull()
        except SemConexao:
            QMessageBox.warning(None, "ApFood", "Sem internet e sem cardápio salvo neste computador.\n"
                                                "Conecte-se ao menos uma vez para baixar o cardápio.")
        except Exception as e:  # noqa: BLE001
            logging.exception("pull inicial")
            QMessageBox.warning(None, "ApFood", f"Não foi possível baixar o cardápio: {e}")
    janela = JanelaPrincipal(ctx)
    janela.iniciar_servicos()
    janela.showMaximized()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
