"""Logo da loja para a impressão dos cupons: preto e branco (pontilhado), no tamanho da bobina.

    80 mm (48 colunas) → até 320 × 160 pontos      58 mm (32 colunas) → até 224 × 112 pontos

Gera o comando ESC/POS (GS v 0) para as térmicas e um PNG monocromático para quem desenha o cupom
(impressora do Windows no PDV). Fica em cache até a logo mudar."""

from __future__ import annotations

import base64
import hashlib
import io

from django.conf import settings
from django.core.cache import cache

TAMANHOS = {48: (320, 160), 32: (224, 112)}


def url(loja) -> str:
    """Endereço público da logo (vai nas linhas do cupom); vazio sem logo."""
    if not loja.logo:
        return ""
    return settings.APFOOD["URL_PUBLICA"].rstrip("/") + loja.logo.url


def versao(loja) -> str:
    return hashlib.sha1(f"{loja.logo.name}".encode()).hexdigest()[:12] if loja.logo else ""


def _bits(loja, largura: int):
    from PIL import Image, ImageOps

    lw, lh = TAMANHOS[32 if largura == 32 else 48]
    with loja.logo.open("rb") as f:
        img = Image.open(f)
        img.load()
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fundo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        fundo.alpha_composite(img)
        img = fundo
    img = img.convert("L")
    # recorta a borda branca para a logo aproveitar o espaço
    caixa = ImageOps.invert(img).point(lambda v: 255 if v > 24 else 0).getbbox()
    if caixa:
        img = img.crop(caixa)
    img.thumbnail((lw, lh), Image.LANCZOS)
    w = (img.width + 7) // 8 * 8
    tela = Image.new("L", (w, img.height), 255)
    tela.paste(img, ((w - img.width) // 2, 0))
    mono = ImageOps.autocontrast(tela).convert("1")  # pontilhado (Floyd–Steinberg)
    return mono


def dados(loja, largura: int = 48) -> dict | None:
    """{"escpos": bytes (GS v 0), "png": bytes, "versao": str} ou None se a loja não tiver logo legível."""
    if not loja.logo:
        return None
    largura = 32 if largura == 32 else 48
    chave = f"logo-impressao:{loja.id}:{versao(loja)}:{largura}"
    if (c := cache.get(chave)) is not None:
        return c or None
    from apfood_core.escpos import raster

    try:
        mono = _bits(loja, largura)
    except Exception:  # noqa: BLE001 — arquivo sumiu/corrompido: imprime sem logo
        cache.set(chave, {}, 600)
        return None
    bits = bytes(b ^ 0xFF for b in mono.tobytes())  # no PIL 1 = branco; na térmica 1 = preto
    png = io.BytesIO()
    mono.save(png, "PNG")
    r = {"escpos": raster(mono.width, mono.height, bits), "png": png.getvalue(), "versao": versao(loja),
         "largura_px": mono.width, "altura_px": mono.height}
    cache.set(chave, r, 7 * 24 * 3600)
    return r


def para_api(loja, largura: int = 48) -> dict:
    d = dados(loja, largura)
    if not d:
        return {"tem_logo": False, "versao": ""}
    return {"tem_logo": True, "versao": d["versao"], "url": url(loja), "largura_px": d["largura_px"], "altura_px": d["altura_px"],
            "escpos_base64": base64.b64encode(d["escpos"]).decode(), "png_base64": base64.b64encode(d["png"]).decode()}
