"""Loja de demonstração."""

from rest_framework.test import APIClient

from apps.cardapio.models import Produto
from apps.contas.models import Usuario
from apps.pedidos.models import Pedido
from apps.plataforma import demonstracao


def test_preenche_sem_duplicar(loja, gerente):
    Usuario.objects.create_user("dono", password="x", papel="ADMIN", empresa=loja.empresa)
    r = demonstracao.preencher(loja, dias=3)
    assert r["produtos"] == len(demonstracao.CARDAPIO) and r["pedidos_historico"] >= 24
    loja.refresh_from_db()
    assert loja.fidelidade_selos == 8 and loja.horarios and loja.aberta_para_pedidos
    concluidos = Pedido.objects.filter(loja=loja, status="CONCLUIDO")
    assert concluidos.count() >= 20
    assert concluidos.filter(tipo_atendimento="ENTREGA", entregador__isnull=False).exists()
    assert Pedido.objects.filter(loja=loja, status="EM_PREPARO").exists()  # movimento de hoje
    assert Pedido.objects.filter(loja=loja, comanda__isnull=False).exists()  # mesa aberta
    ovo = Produto.objects.get(loja=loja, nome="Ovo", tipo="INSUMO")
    assert ovo.abaixo_do_minimo
    # rodar de novo não duplica cardápio nem histórico
    total = Pedido.objects.filter(loja=loja).count()
    produtos = Produto.objects.filter(loja=loja).count()
    assert demonstracao.preencher(loja, dias=3)["pedidos_historico"] in (0, r["pedidos_historico"])
    assert Produto.objects.filter(loja=loja).count() == produtos
    # CMV tem números
    api = APIClient()
    api.force_authenticate(gerente)
    from datetime import timedelta

    from django.utils import timezone

    hoje = timezone.localdate()
    cmv = api.get(f"/api/relatorios/cmv/?loja={loja.id}&inicio={hoje - timedelta(days=5)}&fim={hoje}").data
    assert cmv["custo_centavos"] > 0 and cmv["cmv_percentual"] is not None
    assert total <= Pedido.objects.filter(loja=loja).count()


def test_endpoint_so_master(loja, gerente, django_capture_on_commit_callbacks):
    from apps.integracoes.models import Tarefa

    api = APIClient()
    api.force_authenticate(gerente)
    assert api.post(f"/api/empresas/{loja.empresa_id}/demonstracao/").status_code in (403, 404)
    master = Usuario.objects.create_superuser("chefe", password="x")
    api.force_authenticate(master)
    with django_capture_on_commit_callbacks(execute=True):
        r = api.post(f"/api/empresas/{loja.empresa_id}/demonstracao/")
    assert r.status_code == 202 and Tarefa.objects.filter(tipo="plataforma.demonstracao").count() == 1


def test_mais_movimento_vem_antes(loja):
    from django.db.models import Min

    Usuario.objects.create_user("dono", password="x", papel="ADMIN", empresa=loja.empresa)
    demonstracao.preencher(loja, dias=2)
    antes = Pedido.objects.filter(loja=loja).aggregate(m=Min("data_referencia"))["m"]
    r = demonstracao.preencher(loja, dias=2, mais=True)
    assert r["pedidos_historico"] > 0 and r["ate"] < str(antes)
    assert Pedido.objects.filter(loja=loja, canal="ONLINE", status="CONCLUIDO").exists()
    assert Pedido.objects.filter(loja=loja, canal="MESA", status="CONCLUIDO").exists()
    assert Pedido.objects.filter(loja=loja, status="SAIU_PARA_ENTREGA").exists()
