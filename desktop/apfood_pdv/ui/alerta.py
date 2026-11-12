"""Alerta sonoro de novo pedido: toca em loop até alguém aceitar/recusar."""

import math
import struct
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtWidgets import QApplication

from ..config import pasta_dados


def gerar_som(caminho: Path) -> Path:
    """Dois bipes (880 Hz e 1320 Hz) — gerado na primeira execução, sem arquivo de áudio no instalador."""
    if caminho.exists():
        return caminho
    taxa, quadros = 22050, bytearray()
    for freq, dur in ((880, 0.18), (0, 0.07), (1320, 0.25)):
        for i in range(int(taxa * dur)):
            v = int(12000 * math.sin(2 * math.pi * freq * i / taxa)) if freq else 0
            quadros += struct.pack("<h", v)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(bytes(quadros))
    return caminho


class AlertaSonoro(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.efeito = None
        try:
            from PySide6.QtMultimedia import QSoundEffect

            self.efeito = QSoundEffect(self)
            self.efeito.setSource(QUrl.fromLocalFile(str(gerar_som(pasta_dados() / "novo_pedido.wav"))))
            self.efeito.setVolume(1.0)
        except Exception:  # noqa: BLE001 — sem backend de áudio: usa o bipe do sistema
            self.efeito = None
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self._tocar)
        self.ativo = True

    def _tocar(self):
        if self.efeito is not None:
            self.efeito.play()
        else:
            QApplication.beep()

    def iniciar(self):
        if self.ativo and not self.timer.isActive():
            self._tocar()
            self.timer.start()

    def parar(self):
        self.timer.stop()
