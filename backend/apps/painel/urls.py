from django.urls import path

from . import views

app_name = "painel"

urlpatterns = [
    path("entrar/", views.Entrar.as_view(), name="entrar"),
    path("sair/", views.Sair.as_view(), name="sair"),
    path("qrcode.svg", views.qrcode, name="qrcode"),
    path("senha/esqueci/", views.EsqueciSenha.as_view(), name="esqueci"),
    path("senha/enviado/", views.SenhaEnviada.as_view(), name="senha_enviada"),
    path("senha/nova/<uidb64>/<token>/", views.NovaSenha.as_view(), name="nova_senha"),
    path("senha/pronta/", views.SenhaPronta.as_view(), name="senha_pronta"),
    path("", views.app, name="app"),
]
