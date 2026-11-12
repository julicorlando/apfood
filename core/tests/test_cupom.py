from datetime import datetime

from apfood_core.cupom import comprovante_venda, cupom_cozinha, fechamento_caixa, para_texto

LOJA = {"nome": "Burger Demo", "cnpj": "12.345.678/0001-90", "endereco": "Rua A, 10 - Centro", "telefone": "1199999"}
PEDIDO = {
    "numero": 42, "data": datetime(2026, 11, 12, 20, 15), "tipo_atendimento": "ENTREGA",
    "nome_cliente": "Ana", "telefone_cliente": "11987654321", "atendente": "Caixa 1",
    "itens": [
        {"quantidade": 2, "nome": "X-Bacon com um nome bem comprido para quebrar a linha", "total_centavos": 7980,
         "adicionais": [{"nome": "Cheddar extra", "quantidade": 1, "preco_unitario_centavos": 400}],
         "observacao": "sem cebola"},
        {"quantidade": 1, "nome": "Pizza", "variacao": "Grande", "sabores": ["Calabresa", "Portuguesa"],
         "total_centavos": 6000},
    ],
    "subtotal_centavos": 13980, "taxa_entrega_centavos": 500, "desconto_centavos": 1000, "total_centavos": 13480,
    "pagamentos": [{"forma": "DINHEIRO", "valor_centavos": 13480, "troco_centavos": 1520}],
    "endereco": "Rua das Flores, 123 - Jardim - ap 12", "link_acompanhamento": "https://apfood.app/pedido/abc",
}


def test_comprovante_nao_fiscal():
    linhas = comprovante_venda(PEDIDO, LOJA)
    texto = para_texto(linhas)
    assert "NAO E DOCUMENTO FISCAL" in texto
    assert "Pedido #42" in texto and "12/11/2026 20:15" in texto
    assert "134,80" in texto and "Troco" in texto and "15,20" in texto
    assert "1/2 Calabresa" in texto and "OBS: sem cebola" in texto
    assert all(len(l.texto) <= 48 for l in linhas)
    assert linhas[-1].corte


def test_bobina_58mm():
    assert all(len(l.texto) <= 32 for l in comprovante_venda(PEDIDO, LOJA, largura=32))


def test_cozinha_sem_precos():
    texto = para_texto(cupom_cozinha({**PEDIDO, "mesa": "7"}, "Chapa"))
    assert "CHAPA" in texto and "MESA 7" in texto and "#42" in texto
    assert "79,80" not in texto and "OBS: sem cebola" in texto


def test_fechamento():
    dados = {"operador": "Caixa 1", "aberto_em": datetime(2026, 11, 12, 18), "fechado_em": datetime(2026, 11, 12, 23),
             "valor_abertura_centavos": 10000, "totais_por_tipo": {"VENDA": 50000, "SANGRIA": 20000},
             "quantidade_vendas": 12,
             "conferencia": [{"forma": "DINHEIRO", "esperado_centavos": 30000, "informado_centavos": 29500,
                              "diferenca_centavos": -500},
                             {"forma": "PIX", "esperado_centavos": 10000, "informado_centavos": 10000,
                              "diferenca_centavos": 0}]}
    texto = para_texto(fechamento_caixa(dados, LOJA))
    assert "FECHAMENTO DE CAIXA" in texto and "QUEBRA" in texto and "-5,00" in texto
