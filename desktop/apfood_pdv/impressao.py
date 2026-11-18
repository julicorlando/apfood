"""Impressão térmica ESC/POS sem dependências.

Destino (texto configurado):
    "192.168.0.50:9100"      → impressora de rede (porta RAW 9100)
    "EPSON TM-T20"           → térmica instalada no Windows (spooler RAW, ESC/POS; requer pywin32)
    "windows:HP LaserJet"    → qualquer impressora instalada, pelo driver (impressao_qt.py)
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


# Logo da loja (baixada do servidor e guardada no PDV): {largura: {"escpos": bytes, "png": bytes}}
LOGO: dict[int, dict] = {}


def definir_logo(largura: int, escpos: bytes | None, png: bytes | None) -> None:
    if escpos or png:
        LOGO[32 if largura == 32 else 48] = {"escpos": escpos or b"", "png": png or b""}
    else:
        LOGO.pop(32 if largura == 32 else 48, None)


def logo(largura: int = 48) -> dict | None:
    return LOGO.get(32 if largura == 32 else 48) or LOGO.get(48) or LOGO.get(32)


def _linha(l) -> dict:
    return l if isinstance(l, dict) else {"texto": l.texto, "negrito": l.negrito, "grande": l.grande,
                                         "alinhamento": l.alinhamento, "corte": l.corte,
                                         "qrcode": getattr(l, "qrcode", False), "logo": getattr(l, "logo", False)}


def qrcode_escpos(conteudo: str, tamanho: int = 6) -> bytes:
    """QR Code nativo da impressora (GS ( k, modelo 2) — Epson, Elgin, Bematech, Daruma."""
    dados = conteudo.encode("ascii", errors="ignore")
    n = len(dados) + 3
    return (GS + b"(k\x04\x00\x31\x41\x32\x00"          # modelo 2
            + GS + b"(k\x03\x001C" + bytes([tamanho])     # tamanho do módulo
            + GS + b"(k\x03\x001E0"                      # correção de erro L
            + GS + b"(k" + bytes([n % 256, n // 256]) + b"1P0" + dados  # armazena
            + GS + b"(k\x03\x001Q0")                     # imprime


def para_escpos(linhas, *, abrir_gaveta: bool = False, codificacao: str = "cp860", largura: int = 48) -> bytes:
    """`linhas`: Linha do apfood_core.cupom ou dicts vindos da API. Linha de logo → a logo guardada da loja."""
    out = bytearray(INICIAR + CODEPAGE_PT)
    lg = logo(largura)
    if abrir_gaveta:
        out += GAVETA
    for l in map(_linha, linhas):
        if l.get("corte"):
            out += AVANCA_E_CORTA
            continue
        if l.get("logo"):
            if lg and lg.get("escpos"):
                out += ALINHA["centro"] + lg["escpos"] + b"\n"
            continue
        out += ALINHA.get(l.get("alinhamento", "esquerda"), ALINHA["esquerda"])
        if l.get("qrcode"):
            out += ALINHA["centro"] + qrcode_escpos(l.get("texto") or "") + b"\n"
            continue
        out += NEGRITO[bool(l.get("negrito"))] + TAMANHO[bool(l.get("grande"))]
        out += (l.get("texto") or "").encode(codificacao, errors="replace") + b"\n"
    out += NEGRITO[0] + TAMANHO[0] + ALINHA["esquerda"]
    return bytes(out)


def para_texto(linhas, largura: int = 48) -> str:
    saida = []
    for l in map(_linha, linhas):
        if l.get("corte") or l.get("logo"):
            continue
        t = ("[QR Code] " if l.get("qrcode") else "") + (l.get("texto") or "")
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
    destino = (destino or "").strip()
    if destino.startswith("windows:"):
        from .impressao_qt import imprimir_driver

        return imprimir_driver(destino.removeprefix("windows:").strip(), linhas, largura)
    return enviar(destino, para_escpos(linhas, abrir_gaveta=abrir_gaveta, largura=largura), texto=para_texto(linhas, largura))


def descrever(destino: str) -> str:
    """Texto amigável do destino configurado."""
    destino = (destino or "").strip()
    if not destino:
        return "nenhuma"
    if destino.startswith("windows:"):
        return f"{destino[8:]} (driver do Windows)"
    if destino.startswith("arquivo:"):
        return f"arquivo em {destino[8:]}"
    host, _, porta = destino.rpartition(":")
    return f"rede {destino}" if host and porta.isdigit() else f"{destino} (térmica ESC/POS)"
