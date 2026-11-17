"""Notificações push (Firebase Cloud Messaging, API v1) para os apps ApFood
Empresa e ApFood Entregador — chegam mesmo com o app fechado.

Liga quando o servidor tem APFOOD_FCM_CREDENCIAIS (JSON da conta de serviço do
Firebase em base64). Sem isso, nada é enviado (os apps seguem com o alerta em
primeiro plano e o WhatsApp)."""

from __future__ import annotations

import base64
import json
import logging
import time

import httpx
from django.conf import settings
from django.core.cache import cache

from apps.integracoes.tarefas import enfileirar, executor

log = logging.getLogger(__name__)
ESCOPO = "https://www.googleapis.com/auth/firebase.messaging"


def credenciais() -> dict | None:
    bruto = settings.APFOOD.get("FCM_CREDENCIAIS") or ""
    if not bruto:
        return None
    try:
        return json.loads(base64.b64decode(bruto))
    except (ValueError, TypeError):
        log.error("APFOOD_FCM_CREDENCIAIS inválido (esperado JSON da conta de serviço em base64)")
        return None


def ativo() -> bool:
    return credenciais() is not None


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _token_acesso(cred: dict) -> str:
    """OAuth2 da conta de serviço (JWT RS256) — guardado por 50 min."""
    chave = f"fcm-token-{cred['client_email']}"
    if tok := cache.get(chave):
        return tok
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    agora = int(time.time())
    cab = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    corpo = _b64(json.dumps({"iss": cred["client_email"], "scope": ESCOPO, "aud": cred["token_uri"],
                             "iat": agora, "exp": agora + 3600}).encode())
    privada = serialization.load_pem_private_key(cred["private_key"].encode(), password=None)
    assinatura = privada.sign(f"{cab}.{corpo}".encode(), padding.PKCS1v15(), hashes.SHA256())
    jwt = f"{cab}.{corpo}.{_b64(assinatura)}"
    r = httpx.post(cred["token_uri"], data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                            "assertion": jwt}, timeout=15)
    r.raise_for_status()
    tok = r.json()["access_token"]
    cache.set(chave, tok, 50 * 60)
    return tok


# ----------------------------------------------------------------------------- envio
def _enfileirar(tokens: list[str], titulo: str, corpo: str, dados: dict, chave: str, somente_dados: bool = False) -> None:
    if tokens and ativo():
        enfileirar("push.enviar", {"tokens": tokens, "titulo": titulo, "corpo": corpo, "dados": dados,
                                   "somente_dados": somente_dados}, chave=chave)


@executor("push.enviar")
def enviar(tokens: list[str], titulo: str, corpo: str, dados: dict | None = None, somente_dados: bool = False):
    """somente_dados: o app (serviço nativo do entregador) monta a notificação com Aceitar/Recusar
    e tela cheia por cima do bloqueio; sem isso, o Android mostra uma notificação simples."""
    from .models import DispositivoPush

    cred = credenciais()
    if cred is None:
        return
    url = f"https://fcm.googleapis.com/v1/projects/{cred['project_id']}/messages:send"
    cab = {"Authorization": f"Bearer {_token_acesso(cred)}"}
    for t in tokens:
        if somente_dados:
            msg = {"message": {
                "token": t,
                "data": {**{k: str(v) for k, v in (dados or {}).items()}, "titulo": titulo, "corpo": corpo},
                "android": {"priority": "high", "ttl": "30s"},
            }}
        else:
            msg = {"message": {
                "token": t,
                "notification": {"title": titulo, "body": corpo},
                "data": {k: str(v) for k, v in (dados or {}).items()},
                "android": {"priority": "high", "notification": {"sound": "default", "default_vibrate_timings": True,
                                                                 "channel_id": "pedidos"}},
            }}
        r = httpx.post(url, json=msg, headers=cab, timeout=15)
        invalido = "UNREGISTERED" in r.text or ("INVALID_ARGUMENT" in r.text and "token" in r.text)
        if r.status_code in (400, 404) and invalido:
            DispositivoPush.objects.filter(token=t).update(ativo=False)  # app desinstalado ou token velho
        elif r.status_code >= 400:
            log.warning("FCM %s: %s", r.status_code, r.text[:300])


def registrar(token: str, app: str, *, usuario=None, entregador=None) -> None:
    from .models import DispositivoPush

    token = (token or "").strip()[:255]
    if len(token) < 20:
        return
    DispositivoPush.objects.update_or_create(token=token, defaults={
        "app": app, "usuario": usuario, "entregador": entregador, "ativo": True})


# ----------------------------------------------------------------------------- gatilhos
def para_loja(loja, titulo: str, corpo: str, dados: dict, chave: str) -> None:
    """Todos os celulares com o app Empresa de quem trabalha nesta loja."""
    if not ativo():
        return
    from django.db.models import Q

    from .models import DispositivoPush

    tokens = list(DispositivoPush.objects.filter(app="empresa", ativo=True, usuario__is_active=True)
                  .filter(Q(usuario__lojas=loja) | Q(usuario__papel="ADMIN", usuario__empresa_id=loja.empresa_id))
                  .values_list("token", flat=True).distinct())
    _enfileirar(tokens, titulo, corpo, dados, chave)


def para_entregador(entregador, titulo: str, corpo: str, dados: dict, chave: str) -> None:
    if not ativo():
        return
    from apps.clientes.models import Entregador

    from .models import DispositivoPush

    # o mesmo celular pode estar cadastrado em várias lojas: manda para todos os cadastros do telefone
    ids = [entregador.id]
    if entregador.telefone:
        ids += list(Entregador.objects.filter(telefone=entregador.telefone).values_list("id", flat=True))
    tokens = list(DispositivoPush.objects.filter(app="entregador", ativo=True, entregador_id__in=ids)
                  .values_list("token", flat=True).distinct())
    _enfileirar(tokens, titulo, corpo, dados, chave, somente_dados=True)
