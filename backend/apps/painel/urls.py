from django.urls import path

from . import views

app_name = "painel"

urlpatterns = [
    path("entrar/", views.Entrar.as_view(), name="entrar"),
    path("sair/", views.Sair.as_view(), name="sair"),
    path("qrcode.svg", views.qrcode, name="qrcode"),
    path("", views.app, name="app"),
]
