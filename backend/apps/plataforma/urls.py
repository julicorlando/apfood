from django.urls import path

from . import cadastro

app_name = "cadastro"

urlpatterns = [
    path("", cadastro.planos, name="planos"),
]
