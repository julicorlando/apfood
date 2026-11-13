"""Ponto de entrada para o PyInstaller (gera ApFoodPDV.exe).

`ApFoodPDV.exe --autoteste` só importa todos os módulos e sai (código 0 = ok):
a CI roda isso para garantir que o executável não sai sem nenhum pacote.
"""

import sys


def autoteste() -> int:
    import importlib
    import pkgutil

    import apfood_core
    import apfood_pdv

    for pacote in (apfood_core, apfood_pdv):
        for m in pkgutil.walk_packages(pacote.__path__, pacote.__name__ + "."):
            importlib.import_module(m.name)
    from apfood_pdv.config import recurso

    for nome in ("logo.png", "icone.png", "apfood.ico"):
        if not recurso(nome).exists():
            return 2  # faltou empacotar a logo
    import PySide6.QtMultimedia  # noqa: F401
    import PySide6.QtWebSockets  # noqa: F401

    return 0


if __name__ == "__main__":
    if "--autoteste" in sys.argv:
        sys.exit(autoteste())
    from apfood_pdv.__main__ import main

    sys.exit(main())
