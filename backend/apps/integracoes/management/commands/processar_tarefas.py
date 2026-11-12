import time

from django.core.management.base import BaseCommand

from apps.integracoes.tarefas import processar_lote


class Command(BaseCommand):
    help = "Executa a fila de tarefas (emissão fiscal, WhatsApp, iFood, cobrança). Use --uma-vez no cron."

    def add_arguments(self, parser):
        parser.add_argument("--uma-vez", action="store_true")
        parser.add_argument("--intervalo", type=float, default=2.0)

    def handle(self, *args, uma_vez, intervalo, **opts):
        while True:
            n = processar_lote()
            if uma_vez:
                self.stdout.write(f"{n} tarefa(s) processada(s)")
                return
            if not n:
                time.sleep(intervalo)
