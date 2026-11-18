"""Converte as linhas de impressão (apfood_core.cupom.Linha ou dicts da API) em bytes ESC/POS.
Usado pelo servidor para o app Android imprimir direto na térmica (rede ou Bluetooth)."""

from __future__ import annotations

ESC, GS = b"\x1b", b"\x1d"
INICIAR = ESC + b"@"
CODEPAGE_PT = ESC + b"t\x03"  # PC860 (português)
ALINHA = {"esquerda": ESC + b"a\x00", "centro": ESC + b"a\x01", "direita": ESC + b"a\x02"}
NEGRITO = (ESC + b"E\x00", ESC + b"E\x01")
TAMANHO = (GS + b"!\x00", GS + b"!\x11")
AVANCA_E_CORTA = ESC + b"d\x04" + GS + b"V\x42\x00"
GAVETA = ESC + b"p\x00\x19\xfa"


def _linha(l) -> dict:
    return l if isinstance(l, dict) else {"texto": l.texto, "negrito": l.negrito, "grande": l.grande,
                                         "alinhamento": l.alinhamento, "corte": l.corte, "qrcode": getattr(l, "qrcode", False),
                                         "logo": getattr(l, "logo", False)}


def raster(largura_px: int, altura_px: int, bits: bytes) -> bytes:
    """Imagem em bits (1 = preto, linha a linha, largura múltipla de 8) → comando GS v 0."""
    x = largura_px // 8
    return GS + b"v0\x00" + bytes([x % 256, x // 256, altura_px % 256, altura_px // 256]) + bits


def qrcode(conteudo: str, tamanho: int = 6) -> bytes:
    dados = conteudo.encode("ascii", errors="ignore")
    n = len(dados) + 3
    return (GS + b"(k\x04\x00\x31\x41\x32\x00" + GS + b"(k\x03\x001C" + bytes([tamanho]) + GS + b"(k\x03\x001E0"
            + GS + b"(k" + bytes([n % 256, n // 256]) + b"1P0" + dados + GS + b"(k\x03\x001Q0")


def para_escpos(linhas, *, abrir_gaveta: bool = False, codificacao: str = "cp860", logo: bytes | None = None) -> bytes:
    """`logo`: o comando raster (GS v 0) da logo da loja, impresso no lugar das linhas de logo."""
    out = bytearray(INICIAR + CODEPAGE_PT)
    if abrir_gaveta:
        out += GAVETA
    for l in map(_linha, linhas):
        if l.get("corte"):
            out += AVANCA_E_CORTA
            continue
        if l.get("logo"):
            if logo:
                out += ALINHA["centro"] + logo + b"\n"
            continue
        out += ALINHA.get(l.get("alinhamento", "esquerda"), ALINHA["esquerda"])
        if l.get("qrcode"):
            out += ALINHA["centro"] + qrcode(l.get("texto") or "") + b"\n"
            continue
        out += NEGRITO[bool(l.get("negrito"))] + TAMANHO[bool(l.get("grande"))]
        out += (l.get("texto") or "").encode(codificacao, errors="replace") + b"\n"
    out += NEGRITO[0] + TAMANHO[0] + ALINHA["esquerda"]
    return bytes(out)
