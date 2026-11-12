/** Todos os valores monetários do sistema trafegam em centavos (inteiros). */

const BRL = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

export function formatarCentavos(centavos: number): string {
  return BRL.format(centavos / 100);
}

/** Converte "12,50" | "12.50" | "R$ 1.234,56" em centavos. Retorna null se inválido. */
export function parseReaisParaCentavos(texto: string): number | null {
  const limpo = texto.replace(/[^\d,.-]/g, '').trim();
  if (!limpo) return null;
  // Se tem vírgula, ela é o separador decimal (padrão BR) e pontos são milhar.
  const normalizado = limpo.includes(',') ? limpo.replace(/\./g, '').replace(',', '.') : limpo;
  const valor = Number(normalizado);
  if (!Number.isFinite(valor)) return null;
  return Math.round(valor * 100);
}

export interface ItemCalculavel {
  quantidade: number;
  precoUnitarioCentavos: number;
  adicionais?: { quantidade: number; precoUnitarioCentavos: number }[];
}

export function totalItem(item: ItemCalculavel): number {
  const adicionais = (item.adicionais ?? []).reduce(
    (s, a) => s + a.quantidade * a.precoUnitarioCentavos,
    0,
  );
  return (item.precoUnitarioCentavos + adicionais) * item.quantidade;
}

export function totaisPedido(p: {
  itens: ItemCalculavel[];
  taxaEntregaCentavos?: number;
  descontoCentavos?: number;
  acrescimoCentavos?: number;
}) {
  const subtotalCentavos = p.itens.reduce((s, i) => s + totalItem(i), 0);
  const totalCentavos = Math.max(
    0,
    subtotalCentavos + (p.taxaEntregaCentavos ?? 0) + (p.acrescimoCentavos ?? 0) - (p.descontoCentavos ?? 0),
  );
  return { subtotalCentavos, totalCentavos };
}
