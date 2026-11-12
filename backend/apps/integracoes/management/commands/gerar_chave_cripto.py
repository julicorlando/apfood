from django.core.management.base import BaseCommand

from apps.integracoes.cripto import gerar_chave


class Command(BaseCommand):
    help = "Gera uma chave para APFOOD_CHAVE_CRIPTO (guarde no .env do servidor)"

    def handle(self, *args, **opts):
        self.stdout.write(gerar_chave())
