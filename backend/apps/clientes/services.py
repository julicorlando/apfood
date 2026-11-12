from apfood_core.entrega import Zona, distancia_km, encontrar_zona
from apfood_core.enums import TipoZonaEntrega
from django.db import transaction

from apps.core.excecoes import ErroNegocio

from .models import Cliente, EnderecoCliente, ZonaEntrega, so_digitos


def calcular_taxa_entrega(loja, *, bairro: str | None = None, latitude=None, longitude=None):
    """Devolve (ZonaEntrega, distancia_km | None) ou lança ErroNegocio se fora da área."""
    zonas_db = list(ZonaEntrega.objects.ativos().filter(loja=loja, ativa=True))
    distancia = None
    if latitude is not None and longitude is not None and loja.latitude is not None and loja.longitude is not None:
        distancia = distancia_km(float(loja.latitude), float(loja.longitude), float(latitude), float(longitude))
    zonas = [
        Zona(str(z.id), TipoZonaEntrega(z.tipo), z.nome, z.taxa_centavos, z.raio_max_km, z.tempo_estimado_min)
        for z in zonas_db
    ]
    achada = encontrar_zona(zonas, bairro=bairro, distancia=distancia)
    if achada is None:
        raise ErroNegocio("endereço fora da área de entrega")
    return next(z for z in zonas_db if str(z.id) == achada.id), distancia


def buscar_por_telefone(loja, telefone: str):
    """Busca exata; com 8+ dígitos também tenta pelo final (cliente sem DDD)."""
    digitos = so_digitos(telefone)
    qs = Cliente.objects.ativos().filter(loja=loja)
    exato = qs.filter(telefone=digitos).first()
    if exato or len(digitos) < 8:
        return [exato] if exato else []
    return list(qs.filter(telefone__endswith=digitos[-8:])[:10])


@transaction.atomic
def salvar_cliente_do_pedido(loja, *, nome: str, telefone: str, endereco: dict | None = None):
    """Cria/atualiza o cliente pelo telefone e guarda o endereço usado, para o
    próximo pedido por telefone já vir preenchido."""
    digitos = so_digitos(telefone)
    if len(digitos) < 10:
        return None
    cliente, _ = Cliente.objects.get_or_create(loja=loja, telefone=digitos, defaults={"nome": nome or "Cliente"})
    if nome and cliente.nome != nome:
        cliente.nome = nome
        cliente.save(update_fields=["nome", "atualizado_em"])
    if endereco and endereco.get("logradouro"):
        chave = {k: endereco.get(k, "") or "" for k in ("logradouro", "numero", "bairro")}
        existente = cliente.enderecos.ativos().filter(**chave).first()
        if existente is None:
            tem_principal = cliente.enderecos.ativos().filter(principal=True).exists()
            EnderecoCliente.objects.create(
                cliente=cliente, principal=not tem_principal,
                cidade=endereco.get("cidade") or loja.cidade or "",
                **chave,
                **{k: endereco.get(k) or "" for k in ("complemento", "cep", "referencia")},
                latitude=endereco.get("latitude"), longitude=endereco.get("longitude"),
            )
    return cliente
