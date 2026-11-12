import { test } from 'node:test';
import assert from 'node:assert/strict';
import { calcularEsperado, conferirCaixa } from '../src/caixa';
import { parseReaisParaCentavos, totaisPedido } from '../src/dinheiro';
import { podeTransicionar } from '../src/pedido-status';

test('esperado do caixa considera fundo, vendas, suprimento e sangria', () => {
  const esperado = calcularEsperado(10000, [
    { tipo: 'VENDA', formaPagamento: 'DINHEIRO', valorCentavos: 4590 },
    { tipo: 'VENDA', formaPagamento: 'PIX', valorCentavos: 3200 },
    { tipo: 'SUPRIMENTO', formaPagamento: 'DINHEIRO', valorCentavos: 5000 },
    { tipo: 'SANGRIA', formaPagamento: 'DINHEIRO', valorCentavos: 8000 },
  ]);
  assert.equal(esperado.DINHEIRO, 11590);
  assert.equal(esperado.PIX, 3200);
});

test('conferência aponta quebra por forma de pagamento', () => {
  const r = conferirCaixa(
    { DINHEIRO: 11590, PIX: 3200, CARTAO_CREDITO: 0, CARTAO_DEBITO: 0, VOUCHER: 0, OUTRO: 0 },
    { DINHEIRO: 11500, PIX: 3200 },
  );
  assert.equal(r.diferenca, -90);
  assert.equal(r.linhas.find((l) => l.formaPagamento === 'DINHEIRO')?.diferencaCentavos, -90);
  assert.equal(r.linhas.length, 2);
});

test('parse de valores em reais', () => {
  assert.equal(parseReaisParaCentavos('R$ 1.234,56'), 123456);
  assert.equal(parseReaisParaCentavos('12.5'), 1250);
  assert.equal(parseReaisParaCentavos('abc'), null);
});

test('totais do pedido com adicionais, taxa e desconto', () => {
  const t = totaisPedido({
    itens: [{ quantidade: 2, precoUnitarioCentavos: 2890, adicionais: [{ quantidade: 1, precoUnitarioCentavos: 500 }] }],
    taxaEntregaCentavos: 500,
    descontoCentavos: 300,
  });
  assert.deepEqual(t, { subtotalCentavos: 6780, totalCentavos: 6980 });
});

test('retirada não pode ir para "saiu para entrega"', () => {
  assert.equal(podeTransicionar('EM_PREPARO', 'SAIU_PARA_ENTREGA', 'RETIRADA'), false);
  assert.equal(podeTransicionar('EM_PREPARO', 'SAIU_PARA_ENTREGA', 'ENTREGA'), true);
  assert.equal(podeTransicionar('CONCLUIDO', 'CANCELADO', 'ENTREGA'), false);
});
