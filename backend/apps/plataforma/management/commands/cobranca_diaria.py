from django.core.management.base import BaseCommand

from apps.plataforma.cobranca import rotina_diaria


class Command(BaseCommand):
    help = "Gera faturas do mês, cria o Pix e atualiza inadimplência/bloqueio (rodar 1x por dia no cron)"

    def handle(self, *args, **opts):
        self.stdout.write(str(rotina_diaria()))
