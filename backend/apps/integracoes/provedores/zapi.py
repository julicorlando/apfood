"""Z-API — envio de mensagens de WhatsApp.

POST https://api.z-api.io/instances/{instance}/token/{token}/send-text  {phone, message}
Header Client-Token. Credenciais: {"instance": "...", "token": "...", "client_token": "..."}.
"""

from .base import checar, cliente


class ZApi:
    def __init__(self, instance: str, token: str, client_token: str = ""):
        headers = {"Client-Token": client_token} if client_token else {}
        self.http = cliente(f"https://api.z-api.io/instances/{instance}/token/{token}", headers=headers)

    def enviar_texto(self, telefone: str, mensagem: str) -> dict:
        digitos = "".join(c for c in telefone if c.isdigit())
        if len(digitos) in (10, 11):
            digitos = "55" + digitos  # DDI Brasil
        return checar(self.http.post("/send-text", json={"phone": digitos, "message": mensagem}), "Z-API")
