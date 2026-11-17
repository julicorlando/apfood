"""Alerta sonoro de novo pedido: toca em loop até alguém aceitar/recusar."""

import math
import os
import struct
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtWidgets import QApplication

from ..config import pasta_dados


def gerar_som(caminho: Path) -> Path:
    """Três toques fortes (988, 1319 e 1760 Hz, onda quase quadrada no volume máximo), duas vezes —
    gerado na primeira execução, sem arquivo de áudio no instalador. Bem audível numa cozinha barulhenta."""
    if caminho.exists():
        return caminho
    taxa, quadros = 22050, bytearray()
    padrao = [(988, 0.16), (0, 0.04), (1319, 0.16), (0, 0.04), (1760, 0.24), (0, 0.25)] * 2
    for freq, dur in padrao:
        n = int(taxa * dur)
        for i in range(n):
            if not freq:
                quadros += struct.pack("<h", 0)
                continue
            s = math.sin(2 * math.pi * freq * i / taxa)
            onda = math.tanh(4 * s) / math.tanh(4)  # senoide "achatada": quase quadrada, mais alta e sem estalo
            env = min(1.0, i / (taxa * 0.005), (n - i) / (taxa * 0.005))  # 5 ms de entrada/saída
            quadros += struct.pack("<h", int(31000 * onda * env))
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
            if os.environ.get("APFOOD_SEM_SOM"):  # testes/CI: sem backend de áudio
                raise RuntimeError("som desativado")
            from PySide6.QtMultimedia import QSoundEffect

            self.efeito = QSoundEffect(self)
            self.efeito.setSource(QUrl.fromLocalFile(str(gerar_som(pasta_dados() / "novo_pedido_forte.wav"))))
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
