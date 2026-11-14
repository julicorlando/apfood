"""Atualização automática do PDV (Windows, executável PyInstaller).

1. Ao abrir, pergunta ao servidor a versão publicada (GET /api/pdv/versao/).
2. Se for maior que a instalada: baixa o .exe para a pasta de dados e confere o
   SHA-256 (arquivo corrompido ou adulterado é descartado).
3. Ao confirmar, grava um .cmd que espera o PDV fechar, troca o executável
   (guardando o anterior como .old para voltar atrás) e abre a versão nova.

Rodando pelo código-fonte (não "congelado"), só avisa que há versão nova.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .config import pasta_dados


def versao_tupla(v: str) -> tuple[int, ...]:
    """'1.10.2' → (1, 10, 2). Partes não numéricas (ex.: '-beta') são ignoradas."""
    partes = []
    for p in (v or "0").lstrip("vV").split("."):
        dig = "".join(c for c in p if c.isdigit())
        partes.append(int(dig) if dig else 0)
    while len(partes) > 1 and partes[-1] == 0:
        partes.pop()
    return tuple(partes)


def mais_nova(publicada: str, instalada: str = __version__) -> bool:
    return bool(publicada) and versao_tupla(publicada) > versao_tupla(instalada)


@dataclass
class Atualizacao:
    versao: str
    url: str
    sha256: str
    obrigatoria: bool


def verificar(api, instalada: str = __version__) -> Atualizacao | None:
    """None se não há versão nova (ou o servidor não publicou nenhuma)."""
    info = api.get("/api/pdv/versao/")
    if not info.get("url") or not mais_nova(info.get("versao", ""), instalada):
        return None
    obrig = bool(info.get("obrigatoria_ate")) and versao_tupla(instalada) < versao_tupla(info["obrigatoria_ate"])
    return Atualizacao(info["versao"], info["url"], (info.get("sha256") or "").lower(), obrig)


class ErroAtualizacao(Exception):
    pass


Baixador = Callable[[str], bytes]


def _baixar_urllib(url: str) -> bytes:
    from .api import user_agent

    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — URL vem do nosso servidor
        return r.read()


def baixar(at: Atualizacao, *, destino: Path | None = None, baixador: Baixador | None = None) -> Path:
    if not at.sha256:
        raise ErroAtualizacao("o servidor não informou o SHA-256 do instalador — atualização recusada")
    dados = (baixador or _baixar_urllib)(at.url)
    if hashlib.sha256(dados).hexdigest() != at.sha256:
        raise ErroAtualizacao("arquivo baixado não confere (SHA-256 diferente) — descartado")
    destino = destino or pasta_dados() / f"ApFoodPDV-{at.versao}.exe"
    destino.write_bytes(dados)
    return destino


def executavel_atual() -> Path | None:
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def script_troca(novo: Path, atual: Path, pid: int) -> str:
    """Script do Windows que espera o PDV fechar, troca o .exe e reabre."""
    return "\r\n".join([
        "@echo off",
        "setlocal",
        ":espera",
        f'tasklist /FI "PID eq {pid}" 2>NUL | find "{pid}" >NUL',
        "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto espera)",
        f'if exist "{atual}.old" del /f /q "{atual}.old"',
        f'move /y "{atual}" "{atual}.old" >NUL',
        f'move /y "{novo}" "{atual}" >NUL || (move /y "{atual}.old" "{atual}" >NUL & exit /b 1)',
        f'start "" "{atual}"',
        'del /f /q "%~f0"',
        "",
    ])


def aplicar(novo: Path) -> bool:
    """Agenda a troca e devolve True (o chamador deve fechar o PDV em seguida).
    False quando não está rodando como .exe (desenvolvimento)."""
    atual = executavel_atual()
    if atual is None or sys.platform != "win32":
        return False
    script = pasta_dados() / "atualizar.cmd"
    script.write_text(script_troca(novo, atual, os.getpid()), encoding="ascii", errors="replace")
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                     | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0), close_fds=True)
    return True
