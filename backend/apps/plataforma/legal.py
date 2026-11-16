"""Termos de uso e Política de privacidade (páginas públicas)."""

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.cache import cache_control

PENDENTE = "[preencher em APFOOD_LEGAL_*]"


def _contexto():
    d = {k.lower(): (v or PENDENTE) for k, v in settings.APFOOD_LEGAL.items()}
    d["completo"] = all(settings.APFOOD_LEGAL[k] for k in ("RAZAO_SOCIAL", "CNPJ", "EMAIL", "CIDADE_FORO"))
    d["site"] = settings.APFOOD["URL_PUBLICA"].rstrip("/")
    return d


@cache_control(max_age=3600, public=True)
def termos(request):
    return render(request, "plataforma/legal/termos.html", _contexto())


@cache_control(max_age=3600, public=True)
def privacidade(request):
    return render(request, "plataforma/legal/privacidade.html", _contexto())
