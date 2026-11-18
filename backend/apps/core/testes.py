"""Ajudantes dos testes."""


def quitar(pedido, forma: str = "PIX"):
    """Registra o pagamento do que falta (pedido só é concluído depois de pago)."""
    from django.utils import timezone

    from apps.pedidos.models import Pagamento
    from apps.pedidos.services import total_pago

    falta = pedido.total_centavos - total_pago(pedido=pedido)
    if falta > 0:
        pedido.pagamentos.filter(status="PENDENTE", cobrado_em__isnull=True).delete()  # a forma "prevista" vira o pagamento
        Pagamento.objects.create(pedido=pedido, forma=forma, valor_centavos=falta, status="CONFIRMADO",
                                 confirmado_em=timezone.now(), pago_online=forma != "DINHEIRO")
    return pedido
