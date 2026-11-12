import os
from dataclasses import dataclass
from pathlib import Path


def pasta_dados() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    pasta = base / "ApFood"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


@dataclass(frozen=True)
class Config:
    api_url: str = os.environ.get("APFOOD_API_URL", "http://localhost:8000")
    ws_url: str = os.environ.get("APFOOD_WS_URL", "ws://localhost:8000")
    intervalo_sync_s: int = int(os.environ.get("APFOOD_SYNC_S", "5"))
    caminho_db: Path = pasta_dados() / "pdv.sqlite3"
