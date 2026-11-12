import { FormaPagamento, TipoMovimentacaoCaixa } from './enums';

/**
 * Cálculo do fechamento de caixa — função pura, usada pela API (fonte da
 * verdade) e pelo desktop (pré-visualização offline).
 *
 * Esperado por forma:
 *   DINHEIRO = fundo de troco + vendas + suprimentos − sangrias − despesas − estornos
 *   demais   = vendas − estornos
 */

export interface MovimentacaoParaFechamento {
  tipo: TipoMovimentacaoCaixa;
  formaPagamento: FormaPagamento;
  valorCentavos: number; // sempre positivo
}

const SINAL: Record<TipoMovimentacaoCaixa, 1 | -1> = {
  VENDA: 1,
  SUPRIMENTO: 1,
  ESTORNO_VENDA: -1,
  SANGRIA: -1,
  DESPESA: -1,
};

export type TotaisPorForma = Record<FormaPagamento, number>;

function zerado(): TotaisPorForma {
  return { DINHEIRO: 0, PIX: 0, CARTAO_CREDITO: 0, CARTAO_DEBITO: 0, VOUCHER: 0, OUTRO: 0 };
}

export function calcularEsperado(
  valorAberturaCentavos: number,
  movimentacoes: MovimentacaoParaFechamento[],
): TotaisPorForma {
  const t = zerado();
  t.DINHEIRO = valorAberturaCentavos;
  for (const m of movimentacoes) {
    if (m.valorCentavos <= 0) throw new Error('Movimentação com valor não positivo');
    t[m.formaPagamento] += SINAL[m.tipo] * m.valorCentavos;
  }
  return t;
}

export interface LinhaConferencia {
  formaPagamento: FormaPagamento;
  valorEsperadoCentavos: number;
  valorInformadoCentavos: number;
  diferencaCentavos: number; // > 0 sobra, < 0 quebra
}

export function conferirCaixa(
  esperado: TotaisPorForma,
  informado: Partial<TotaisPorForma>,
): { linhas: LinhaConferencia[]; totalEsperado: number; totalInformado: number; diferenca: number } {
  const linhas: LinhaConferencia[] = [];
  for (const forma of Object.keys(esperado) as FormaPagamento[]) {
    const valorEsperadoCentavos = esperado[forma];
    const valorInformadoCentavos = informado[forma] ?? 0;
    if (valorEsperadoCentavos === 0 && valorInformadoCentavos === 0) continue;
    linhas.push({
      formaPagamento: forma,
      valorEsperadoCentavos,
      valorInformadoCentavos,
      diferencaCentavos: valorInformadoCentavos - valorEsperadoCentavos,
    });
  }
  const totalEsperado = linhas.reduce((s, l) => s + l.valorEsperadoCentavos, 0);
  const totalInformado = linhas.reduce((s, l) => s + l.valorInformadoCentavos, 0);
  return { linhas, totalEsperado, totalInformado, diferenca: totalInformado - totalEsperado };
}
