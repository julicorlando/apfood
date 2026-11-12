"""Nomes dos grupos do Channels (contrato de tempo real).

  loja_<uuid>_pdv     — todos os PDVs da loja: pedido.novo, pedido.status,
                        estoque.alerta, catalogo.alterado
  pedido_<token>      — link público do cliente: pedido.status
"""


def grupo_pdv(loja_id) -> str:
    return f"loja_{loja_id}_pdv".replace("-", "")


def grupo_pedido(token: str) -> str:
    return f"pedido_{token}"
