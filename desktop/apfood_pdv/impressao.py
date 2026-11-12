"""Impressão térmica ESC/POS sem dependências.

Destino (texto configurado):
    "192.168.0.50:9100"      → impressora de rede (porta RAW 9100)
    "EPSON TM-T20"           → impressora instalada no Windows (spooler RAW, requer pywin32)
    "arquivo:C:/cupons"      → grava .txt (sem impressora / testes)
"""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

ESC, GS = b"\x1b", b"\x1d"
INICIAR = ESC + b"@"
CODEPAGE_PT = ESC + b"t\x03"  # PC860 (português) — o mais comum nas térmicas nacionais
ALINHA = {"esquerda": ESC + b"a\x00", "centro": ESC + b"a\x01", "direita": ESC + b"a\x02"}
NEGRITO = (ESC + b"E\x00", ESC + b"E\x01")
TAMANHO = (GS + b"!\x00", GS + b"!\x11")  # normal | altura+largura duplas
AVANCA_E_CORTA = ESC + b"d\x04" + GS + b"V\x42\x00"
GAVETA = ESC + b"p\x00\x19\xfa"  # pulso no pino 2: abre a gaveta de dinheiro


def _linha(l) -> dict:
    return l if isinstance(l, dict) else {"texto": l.texto, "negrito": l.negrito, "grande": l.grande,
                                         "alinhamento": l.alinhamento, "corte": l.corte}


def para_escpos(linhas, *, abrir_gaveta: bool = False, codificacao: str = "cp860") -> bytes:
    """`linhas`: Linha do apfood_core.cupom ou dicts vindos da API."""
    out = bytearray(INICIAR + CODEPAGE_PT)
    if abrir_gaveta:
        out += GAVETA
    for l in map(_linha, linhas):
        if l.get("corte"):
            out += AVANCA_E_CORTA
            continue
        out += ALINHA.get(l.get("alinhamento", "esquerda"), ALINHA["esquerda"])
        out += NEGRITO[bool(l.get("negrito"))] + TAMANHO[bool(l.get("grande"))]
        out += (l.get("texto") or "").encode(codificacao, errors="replace") + b"\n"
    out += NEGRITO[0] + TAMANHO[0] + ALINHA["esquerda"]
    return bytes(out)


def para_texto(linhas, largura: int = 48) -> str:
    saida = []
    for l in map(_linha, linhas):
        if l.get("corte"):
            continue
        t = l.get("texto") or ""
        saida.append(t.center(largura).rstrip() if l.get("alinhamento") == "centro" else t)
    return "\n".join(saida)


class ErroImpressao(Exception):
    pass


def enviar(destino: str, dados: bytes, *, texto: str = "") -> str:
    """Envia bytes ESC/POS ao destino. Devolve uma descrição do que foi feito."""
    destino = (destino or "").strip()
    if not destino:
        raise ErroImpressao("nenhuma impressora configurada")
    if destino.startswith("arquivo:"):
        pasta = Path(destino.removeprefix("arquivo:"))
        pasta.mkdir(parents=True, exist_ok=True)
        arq = pasta / f"cupom-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.txt"
        arq.write_text(texto or dados.decode("cp860", errors="replace"), encoding="utf-8")
        return str(arq)
    host, _, porta = destino.rpartition(":")
    if host and porta.isdigit():
        try:
            with socket.create_connection((host, int(porta)), timeout=5) as s:
                s.sendall(dados)
        except OSError as e:
            raise ErroImpressao(f"impressora {destino} não respondeu: {e}") from e
        return destino
    if sys.platform == "win32":
        try:
            import win32print  # type: ignore[import-not-found]
        except ImportError as e:
            raise ErroImpressao("instale o pywin32 para imprimir em impressora do Windows") from e
        h = win32print.OpenPrinter(destino)
        try:
            win32print.StartDocPrinter(h, 1, ("ApFood", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, dados)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        return destino
    raise ErroImpressao(f"destino de impressão inválido: {destino}")


def imprimir(destino: str, linhas, *, largura: int = 48, abrir_gaveta: bool = False) -> str:
    return enviar(destino, para_escpos(linhas, abrir_gaveta=abrir_gaveta), texto=para_texto(linhas, largura))
