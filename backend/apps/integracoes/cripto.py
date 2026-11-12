"""Criptografia simétrica (Fernet/AES) das credenciais de integração.

Chave: variável APFOOD_CHAVE_CRIPTO (gere com `python manage.py gerar_chave_cripto`).
Sem ela, deriva da SECRET_KEY — funciona, mas trocar a SECRET_KEY invalida
as credenciais salvas. Em produção, defina APFOOD_CHAVE_CRIPTO.
"""

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    chave = getattr(settings, "APFOOD_CHAVE_CRIPTO", "") or ""
    if not chave:
        chave = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(chave.encode())


def cifrar(dados: dict) -> str:
    return _fernet().encrypt(json.dumps(dados).encode()).decode()


def decifrar(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken as exc:
        raise ValueError("não foi possível decifrar as credenciais (chave mudou?)") from exc


def gerar_chave() -> str:
    return Fernet.generate_key().decode()
