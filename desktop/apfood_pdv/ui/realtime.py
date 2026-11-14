"""WebSocket do PDV: recebe pedido.novo / pedido.status / estoque.alerta em
tempo real, com reconexão automática. Se cair, o polling da fila cobre."""

import json

from PySide6.QtCore import QObject, QTimer, QUrl, Signal


class ClienteTempoReal(QObject):
    evento = Signal(dict)
    conectado = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ws = None
        self.url = ""
        self.ligado = False
        self.reconectar = QTimer(self)
        self.reconectar.setInterval(5000)
        self.reconectar.timeout.connect(self._abrir)

    def iniciar(self, ws_base: str, loja_id: str, token_fn):
        self.ws_base, self.loja_id, self.token_fn = ws_base.rstrip("/"), loja_id, token_fn
        try:
            from PySide6.QtWebSockets import QWebSocket
        except ImportError:
            return
        self.ws = QWebSocket()
        self.ws.connected.connect(lambda: self._estado(True))
        self.ws.disconnected.connect(lambda: self._estado(False))
        self.ws.textMessageReceived.connect(self._mensagem)
        self._abrir()

    def _abrir(self):
        if self.ws is None or self.ligado:
            return
        from PySide6.QtNetwork import QNetworkRequest

        from ..api import user_agent

        req = QNetworkRequest(QUrl(f"{self.ws_base}/ws/pdv/{self.loja_id}/?token={self.token_fn()}"))
        req.setRawHeader(b"User-Agent", user_agent().encode())
        self.ws.open(req)

    def _estado(self, ok: bool):
        self.ligado = ok
        self.conectado.emit(ok)
        if ok:
            self.reconectar.stop()
        elif not self.reconectar.isActive():
            self.reconectar.start()

    def _mensagem(self, texto: str):
        try:
            self.evento.emit(json.loads(texto))
        except ValueError:
            pass

    def parar(self):
        self.reconectar.stop()
        if self.ws is not None:
            self.ws.close()
