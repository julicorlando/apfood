"""Rotinas automáticas das lojas (rodar de hora em hora; cada uma só age uma vez por dia/cliente)."""

from django.core.management.base import BaseCommand

from apps.lojas.models import Loja
from apps.marketing import reconquista


class Command(BaseCommand):
    help = "Reconquista e aniversário por WhatsApp (10h às 20h)."

    def handle(self, *args, **opts):
        total = {"reconquista": 0, "aniversario": 0}
        for loja in Loja.objects.filter(ativa=True, empresa__ativa=True).select_related("empresa"):
            if not (loja.reconquista_ativa or loja.aniversario_ativo):
                continue
            r = reconquista.rodar(loja)
            for k in total:
                total[k] += r[k]
        self.stdout.write(f"rotinas: {total}")
