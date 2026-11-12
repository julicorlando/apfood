"""Ponto de entrada para o PyInstaller (gera ApFoodPDV.exe)."""

import sys

from apfood_pdv.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
