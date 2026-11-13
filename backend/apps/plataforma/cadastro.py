"""Página pública de planos e cadastro self-service do restaurante.

O restaurante escolhe o plano e já sai usando: cria a empresa em teste grátis
(TRIAL), a primeira loja e o usuário ADMIN, e entra direto no painel.
"""

from datetime import timedelta

from apfood_core.enums import PapelUsuario, StatusAssinatura
from django import forms
from django.contrib.auth import login
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.cache import never_cache

from apps.contas.models import Usuario
from apps.lojas.models import Empresa, Loja

from .models import Plano

DIAS_TRIAL_PADRAO = 14
MAX_CADASTROS_POR_IP_HORA = 5
RESERVADOS = {"admin", "api", "painel", "static", "media", "health", "pedido", "ws", "planos", "cadastro", "entrega"}


class FormCadastro(forms.Form):
    restaurante = forms.CharField(label="Nome do restaurante", max_length=120)
    cidade = forms.CharField(label="Cidade", max_length=80)
    nome = forms.CharField(label="Seu nome", max_length=150)
    email = forms.EmailField(label="E-mail (vai ser seu login)")
    telefone = forms.CharField(label="WhatsApp", max_length=20)
    senha = forms.CharField(label="Senha", widget=forms.PasswordInput, min_length=6)
    plano = forms.ModelChoiceField(queryset=Plano.objects.none(), required=False, empty_label=None)
    aceite = forms.BooleanField(label="Li e aceito os termos de uso")
    site = forms.CharField(required=False)  # armadilha para robôs (fica escondido)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plano"].queryset = Plano.objects.filter(ativo=True, publico=True)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Usuario.objects.filter(username__iexact=email).exists() or Usuario.objects.filter(email__iexact=email).exists():
            raise ValidationError("Este e-mail já tem cadastro. Use \"Esqueci minha senha\" no login.")
        return email

    def clean_telefone(self):
        digitos = "".join(c for c in self.cleaned_data["telefone"] if c.isdigit())
        if len(digitos) not in (10, 11):
            raise ValidationError("Informe o telefone com DDD.")
        return digitos

    def clean(self):
        dados = super().clean()
        if dados.get("site"):
            raise ValidationError("Não foi possível concluir o cadastro.")
        if dados.get("senha"):
            try:
                validate_password(dados["senha"], Usuario(username=dados.get("email", ""), email=dados.get("email", "")))
            except ValidationError as exc:
                self.add_error("senha", exc)
        return dados


def slug_unico(nome: str) -> str:
    base = slugify(nome)[:40] or "loja"
    if base in RESERVADOS:
        base = f"{base}-loja"
    slug, n = base, 2
    while Loja.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


@transaction.atomic
def criar_conta(d: dict) -> Usuario:
    plano = d.get("plano")
    dias = plano.dias_trial if plano else DIAS_TRIAL_PADRAO
    empresa = Empresa.objects.create(
        nome=d["restaurante"], email=d["email"], telefone=d["telefone"], responsavel=d["nome"], plano=plano,
        status_assinatura=StatusAssinatura.TRIAL, trial_ate=timezone.localdate() + timedelta(days=dias),
    )
    Loja.objects.create(empresa=empresa, nome=d["restaurante"], slug=slug_unico(d["restaurante"]),
                        cidade=d["cidade"], whatsapp=d["telefone"], telefone=d["telefone"])
    nome, _, sobrenome = d["nome"].strip().partition(" ")
    u = Usuario(username=d["email"], email=d["email"], first_name=nome[:150], last_name=sobrenome[:150],
                papel=PapelUsuario.ADMIN, empresa=empresa)
    u.set_password(d["senha"])
    u.save()
    return u


def _ip(request) -> str:
    return (request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR") or "").split(",")[0].strip()


@never_cache
def planos(request):
    planos_publicos = list(Plano.objects.filter(ativo=True, publico=True))
    if request.method == "POST":
        form = FormCadastro(request.POST)
        chave = f"cadastro-ip-{_ip(request)}"
        if cache.get(chave, 0) >= MAX_CADASTROS_POR_IP_HORA:
            form.add_error(None, "Muitos cadastros a partir desta rede. Tente de novo mais tarde.")
        elif form.is_valid():
            cache.set(chave, cache.get(chave, 0) + 1, 60 * 60)
            u = criar_conta(form.cleaned_data)
            login(request, u, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("/painel/#/loja")
    else:
        form = FormCadastro(initial={"plano": planos_publicos[0].pk if planos_publicos else None})
    return render(request, "plataforma/planos.html", {"form": form, "planos": planos_publicos,
                                                      "dias_trial": DIAS_TRIAL_PADRAO})
