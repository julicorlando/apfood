import pytest


@pytest.fixture(autouse=True)
def _db_liberado(db):
    """Todos os testes do backend podem usar o banco."""
