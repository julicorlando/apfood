"""Dinheiro sempre em CENTAVOS (int). Nunca use float para valores monetários."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def reais_para_centavos(valor: str | int | Decimal) -> int:
    """Converte "12,50", "12.50", "1.234,56", Decimal("12.5") ou 12 em centavos.

    Inteiros são interpretados como REAIS (12 -> 1200).
    """
    if isinstance(valor, bool):
        raise TypeError("valor booleano não é dinheiro")
    if isinstance(valor, int):
        return valor * 100
    if isinstance(valor, str):
        texto = valor.strip().replace("R$", "").replace(" ", "")
        if "," in texto:  # formato brasileiro: 1.234,56
            texto = texto.replace(".", "").replace(",", ".")
        try:
            valor = Decimal(texto)
        except InvalidOperation as exc:
            raise ValueError(f"valor monetário inválido: {valor!r}") from exc
    if not isinstance(valor, Decimal):
        raise TypeError(f"tipo não suportado: {type(valor).__name__}")
    return int((valor * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def centavos_para_decimal(centavos: int) -> Decimal:
    return (Decimal(centavos) / 100).quantize(Decimal("0.01"))


def formatar(centavos: int, simbolo: bool = True) -> str:
    """1234567 -> 'R$ 12.345,67'; -150 -> '-R$ 1,50'."""
    sinal = "-" if centavos < 0 else ""
    inteiro, resto = divmod(abs(centavos), 100)
    corpo = f"{inteiro:,}".replace(",", ".") + f",{resto:02d}"
    return f"{sinal}{'R$ ' if simbolo else ''}{corpo}"


def calcular_troco(total_centavos: int, recebido_centavos: int) -> int:
    if recebido_centavos < total_centavos:
        raise ValueError("valor recebido menor que o total")
    return recebido_centavos - total_centavos
