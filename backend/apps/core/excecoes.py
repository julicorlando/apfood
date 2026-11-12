from rest_framework.exceptions import ValidationError


class ErroNegocio(ValidationError):
    """Violação de regra de negócio. A API devolve 400 com {"detail": "..."}.

    Os services lançam esta exceção; views e o sync apenas a repassam."""

    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__({campo: [mensagem]} if campo else {"detail": mensagem})
        self.mensagem = mensagem
