"""Painel web: login próprio e a página única (SPA) que conversa com a API.

Toda regra de negócio continua nos services/API — o painel é só a tela, a
mesma que o PDV desktop usa, autenticada pela sessão do navegador.
"""

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache


class FormEntrar(AuthenticationForm):
    """Recusa quem está bloqueado (empresa inativa) já na tela de login."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.acesso().bloqueado:
            raise ValidationError("Acesso bloqueado. Fale com o administrador da plataforma.", code="bloqueado")


class Entrar(LoginView):
    template_name = "painel/entrar.html"
    authentication_form = FormEntrar
    redirect_authenticated_user = True


class Sair(LogoutView):
    next_page = "/painel/entrar/"


@never_cache
@login_required
def app(request):
    if request.user.acesso().bloqueado:
        logout(request)
        return redirect("painel:entrar")
    return render(request, "painel/app.html")


@login_required
def qrcode(request):
    """QR Code em SVG para o cupom impresso pelo navegador (NFC-e, Pix)."""
    import io

    import segno

    texto = request.GET.get("t", "")
    if not texto or len(texto) > 1000:
        return HttpResponseBadRequest("texto inválido")
    buf = io.BytesIO()
    segno.make(texto, error="m").save(buf, kind="svg", scale=4, border=1, xmldecl=False)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")
