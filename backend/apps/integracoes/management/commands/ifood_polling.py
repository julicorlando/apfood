import time

from django.core.management.base import BaseCommand

from apps.integracoes.models import Integracao
from apps.integracoes.provedores.ifood import sincronizar


class Command(BaseCommand):
    help = "Busca pedidos do iFood de todas as lojas com a integração ativa (loop a cada 30 s)"

    def add_arguments(self, parser):
        parser.add_argument("--uma-vez", action="store_true")

    def handle(self, *args, uma_vez, **opts):
        while True:
            for integ in Integracao.objects.filter(tipo="MARKETPLACE", provedor="ifood", ativo=True).select_related("loja"):
                try:
                    n = sincronizar(integ)
                    if n:
                        self.stdout.write(f"{integ.loja}: {n} pedido(s) importado(s)")
                except Exception as exc:  # noqa: BLE001
                    integ.registrar_erro(str(exc))
                    self.stderr.write(f"{integ.loja}: {exc}")
            if uma_vez:
                return
            time.sleep(30)
