"""Impressão pelo driver do Windows (qualquer impressora instalada no PC):
laser, jato de tinta ou térmica que só tem driver. Desenha o mesmo cupom
(negrito, tamanho grande, alinhamento e QR Code) com o Qt.

Destino "windows:<nome da impressora>". As térmicas ESC/POS continuam no modo
RAW (impressao.py), que é mais rápido e corta o papel/abre a gaveta."""

from __future__ import annotations

from .impressao import ErroImpressao, _linha


def impressoras_instaladas() -> list[str]:
    try:
        from PySide6.QtPrintSupport import QPrinterInfo

        nomes = list(QPrinterInfo.availablePrinterNames())
        if nomes:
            return sorted(nomes, key=str.lower)
    except Exception:  # noqa: BLE001 - sem QtPrintSupport: tenta o spooler
        pass
    try:
        import win32print  # type: ignore[import-not-found]

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return sorted({p[2] for p in win32print.EnumPrinters(flags)}, key=str.lower)
    except Exception:  # noqa: BLE001
        return []


def impressora_padrao() -> str:
    try:
        from PySide6.QtPrintSupport import QPrinterInfo

        return QPrinterInfo.defaultPrinterName() or ""
    except Exception:  # noqa: BLE001
        return ""


def _qr(texto: str):
    """QImage do QR Code (segno, se disponível)."""
    from PySide6.QtGui import QImage

    try:
        import io

        import segno

        buf = io.BytesIO()
        segno.make(texto, error="m").save(buf, kind="png", scale=8, border=2)
        img = QImage()
        img.loadFromData(buf.getvalue(), "PNG")
        return img if not img.isNull() else None
    except Exception:  # noqa: BLE001
        return None


def _desenhar(nome: str, linhas, largura: int) -> str:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QFont, QFontMetricsF, QPainter
    from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

    info = QPrinterInfo.printerInfo(nome)
    if info.isNull():
        raise ErroImpressao(f"a impressora “{nome}” não está instalada neste computador")
    pr = QPrinter(info, QPrinter.PrinterMode.HighResolution)
    pr.setDocName("ApFood")
    p = QPainter()
    if not p.begin(pr):
        raise ErroImpressao(f"não foi possível usar a impressora “{nome}” (está ligada e com papel?)")
    try:
        area = pr.pageLayout().paintRectPixels(pr.resolution())
        larg_px, alt_px = area.width(), area.height()
        base = QFont("Consolas")
        base.setStyleHint(QFont.StyleHint.Monospace)
        base.setPointSizeF(10)
        medida = QFontMetricsF(base, pr).horizontalAdvance("M" * max(20, largura))
        base.setPointSizeF(max(5.0, min(12.0, 10 * larg_px / max(1.0, medida) * 0.97)))
        alinhar = {"centro": Qt.AlignmentFlag.AlignHCenter, "direita": Qt.AlignmentFlag.AlignRight}
        y = 0.0
        pendente_pagina = False
        for l in map(_linha, linhas):
            if l.get("corte"):
                pendente_pagina = y > 0  # várias vias no mesmo envio: cada uma na sua página
                continue
            if pendente_pagina:
                pr.newPage()
                y, pendente_pagina = 0.0, False
            if l.get("qrcode"):
                img = _qr(l.get("texto") or "")
                if img is None:
                    continue
                lado = min(larg_px * 0.45, alt_px * 0.3)
                if y + lado > alt_px:
                    pr.newPage()
                    y = 0.0
                p.drawImage(QRectF((larg_px - lado) / 2, y, lado, lado), img)
                y += lado + QFontMetricsF(base, pr).lineSpacing() * 0.5
                continue
            f = QFont(base)
            f.setBold(bool(l.get("negrito")))
            if l.get("grande"):
                f.setPointSizeF(base.pointSizeF() * 2)
            p.setFont(f)
            alt = QFontMetricsF(f, pr).lineSpacing()
            if y + alt > alt_px:
                pr.newPage()
                y = 0.0
            flag = alinhar.get(l.get("alinhamento", "esquerda"), Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter
            p.drawText(QRectF(0, y, larg_px, alt), flag, l.get("texto") or "")
            y += alt
    finally:
        p.end()
    return f"windows:{nome}"


def imprimir_driver(nome: str, linhas, largura: int = 48) -> str:
    """Imprime pelo driver. Chamado de outra thread (ponte com o painel web), executa na thread da tela."""
    from PySide6.QtCore import QCoreApplication, QThread

    linhas = list(linhas)
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() == app.thread():
        return _desenhar(nome, linhas, largura)
    return _na_tela(lambda: _desenhar(nome, linhas, largura))


_executor = None


def _na_tela(fn):
    from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal, Slot

    global _executor
    if _executor is None:
        class Executor(QObject):
            pedido = Signal(object)

            def __init__(self):
                super().__init__()
                self.pedido.connect(self._rodar, Qt.ConnectionType.BlockingQueuedConnection)

            @Slot(object)
            def _rodar(self, caixa):
                try:
                    caixa["r"] = caixa["fn"]()
                except Exception as e:  # noqa: BLE001
                    caixa["e"] = e

        _executor = Executor()
        _executor.moveToThread(QCoreApplication.instance().thread())
    caixa = {"fn": fn}
    _executor.pedido.emit(caixa)
    if "e" in caixa:
        raise caixa["e"]
    return caixa.get("r", "")
