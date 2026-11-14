"""Configuração local do PDV (arquivo config.json na pasta de dados)."""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


SERVIDOR_PADRAO = "https://apfood.axionwebdigital.com.br"


def recurso(nome: str) -> Path:
    """Arquivos que vão junto com o app (logo, ícone). Funciona no .exe do PyInstaller."""
    return Path(__file__).resolve().parent / "recursos" / nome


def pasta_dados() -> Path:
    """%LOCALAPPDATA%\\ApFood no Windows; APFOOD_PASTA sobrescreve (testes)."""
    if os.environ.get("APFOOD_PASTA"):
        pasta = Path(os.environ["APFOOD_PASTA"])
    else:
        pasta = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "ApFood"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


@dataclass
class Config:
    api_url: str = os.environ.get("APFOOD_API_URL", SERVIDOR_PADRAO)
    ultimo_usuario: str = ""
    loja_id: str = ""
    intervalo_sync_s: int = 5
    impressora_caixa: str = ""  # "192.168.0.50:9100" | nome da impressora no Windows | "arquivo:C:/cupons"
    impressora_cozinha_padrao: str = ""  # usada quando o setor não define impressora
    largura_bobina: int = 48  # 48 = 80 mm | 32 = 58 mm
    imprimir_cozinha_automatico: bool = True
    som_novo_pedido: bool = True
    nome_terminal: str = "Caixa 1"
    extras: dict = field(default_factory=dict)

    @property
    def ws_url(self) -> str:
        return self.api_url.replace("https://", "wss://").replace("http://", "ws://")

    @property
    def caminho_db(self) -> Path:
        return pasta_dados() / "pdv.sqlite3"

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "Config":
        caminho = caminho or pasta_dados() / "config.json"
        if caminho.exists():
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            campos = {k: v for k, v in dados.items() if k in cls.__dataclass_fields__}
            cfg = cls(**campos)
            # versões antigas salvavam vazio ou localhost: volta para o servidor de produção
            if not (cfg.api_url or "").strip() or cfg.api_url.rstrip("/") == "http://localhost:8000":
                cfg.api_url = os.environ.get("APFOOD_API_URL", SERVIDOR_PADRAO)
            return cfg
        return cls()

    def salvar(self, caminho: Path | None = None) -> None:
        caminho = caminho or pasta_dados() / "config.json"
        caminho.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


def normalizar_servidor(texto: str) -> str:
    """Aceita "apfood.exemplo.com.br", "https://.../painel/" etc. e devolve só a origem."""
    from urllib.parse import urlsplit

    t = (texto or "").strip()
    if not t:
        return t
    if "://" not in t:
        t = ("http://" if t.startswith(("localhost", "127.", "192.168.", "10.")) else "https://") + t
    p = urlsplit(t)
    return f"{p.scheme}://{p.netloc}"
