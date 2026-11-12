from apfood_pdv.local_db import BancoLocal


def test_outbox_idempotente_e_ordenada():
    db = BancoLocal()
    a = db.enfileirar("caixa.abrir", {"valor_abertura_centavos": 10000})
    db.enfileirar("pedido.criar", {"total_centavos": 3490}, op_id="fixo")
    db.enfileirar("pedido.criar", {"total_centavos": 3490}, op_id="fixo")  # repetida
    ops = db.pendentes()
    assert [o.operacao for o in ops] == ["caixa.abrir", "pedido.criar"]
    db.marcar_falha(a, "timeout")
    assert db.pendentes()[0].tentativas == 1
    db.marcar_enviado(a)
    assert db.total_pendentes() == 1


def test_pull_atualiza_cache_e_cursor():
    db = BancoLocal()
    db.aplicar_pull("produtos", [
        {"id": "p1", "nome": "X-Burger", "atualizado_em": "2026-11-12T10:00:00Z"},
        {"id": "p2", "nome": "X-Bacon", "atualizado_em": "2026-11-12T11:00:00Z"},
    ])
    db.aplicar_pull("produtos", [
        {"id": "p1", "nome": "X-Burger", "atualizado_em": "2026-11-12T12:00:00Z",
         "excluido_em": "2026-11-12T12:00:00Z"},
    ])
    assert [p["id"] for p in db.listar("produtos")] == ["p2"]
    assert db.cursor("produtos") == "2026-11-12T12:00:00Z"
