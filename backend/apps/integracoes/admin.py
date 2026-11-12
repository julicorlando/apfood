import json

from django import forms
from django.contrib import admin

from apps.core.admin import EscopoAdmin

from .models import Integracao, Tarefa, WebhookRecebido

AJUDA = {
    "focusnfe": '{"token": "..."}', "mercadopago": '{"access_token": "APP_USR-..."}',
    "zapi": '{"instance": "...", "token": "...", "client_token": "..."}',
    "ifood": '{"client_id": "...", "client_secret": "..."} (ou vazio para usar o app da plataforma)',
}


class IntegracaoForm(forms.ModelForm):
    novas_credenciais = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="JSON com os segredos. Fica cifrado e nunca é exibido. Vazio = manter as atuais. "
                  + " | ".join(f"{k}: {v}" for k, v in AJUDA.items()),
    )

    class Meta:
        model = Integracao
        fields = ["loja", "tipo", "provedor", "ativo", "configuracao"]

    def clean_novas_credenciais(self):
        bruto = self.cleaned_data["novas_credenciais"].strip()
        if not bruto:
            return None
        try:
            dados = json.loads(bruto)
        except ValueError as exc:
            raise forms.ValidationError("JSON inválido") from exc
        if not isinstance(dados, dict):
            raise forms.ValidationError("informe um objeto JSON")
        return dados

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("novas_credenciais") is not None:
            obj.definir_credenciais(self.cleaned_data["novas_credenciais"])
        if commit:
            obj.save()
        return obj


@admin.register(Integracao)
class IntegracaoAdmin(EscopoAdmin):
    form = IntegracaoForm
    caminho_loja = "loja"
    edicao_minima = "admin"
    list_display = ["loja", "tipo", "provedor", "ativo", "tem_credenciais", "ultimo_sucesso_em", "ultimo_erro"]
    list_filter = ["tipo", "provedor", "ativo"]
    readonly_fields = ["ultimo_sucesso_em", "ultimo_erro"]

    @admin.display(boolean=True, description="credenciais")
    def tem_credenciais(self, obj):
        return bool(obj.credenciais_cifradas)


@admin.register(Tarefa)
class TarefaAdmin(EscopoAdmin):
    somente_master = True
    list_display = ["criado_em", "tipo", "status", "tentativas", "executar_em", "erro"]
    list_filter = ["status", "tipo"]
    actions = ["reprocessar"]

    @admin.action(description="Reprocessar agora")
    def reprocessar(self, request, queryset):
        from django.utils import timezone

        queryset.update(status=Tarefa.PENDENTE, executar_em=timezone.now(), tentativas=0)


@admin.register(WebhookRecebido)
class WebhookRecebidoAdmin(EscopoAdmin):
    somente_master = True
    list_display = ["criado_em", "provedor", "evento", "loja", "processado_em"]
    list_filter = ["provedor", "evento"]
    readonly_fields = [f.name for f in WebhookRecebido._meta.fields]

    def has_add_permission(self, request):
        return False
