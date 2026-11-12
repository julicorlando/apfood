import { StatusPedido, TipoAtendimento } from './enums';

/**
 * Máquina de estados do pedido. A API é a autoridade: qualquer transição
 * fora desta tabela é rejeitada (inclusive vindas do desktop via sync).
 */
const TRANSICOES: Record<StatusPedido, readonly StatusPedido[]> = {
  PENDENTE: ['RECEBIDO', 'RECUSADO', 'CANCELADO'],
  RECEBIDO: ['EM_PREPARO', 'CANCELADO'],
  EM_PREPARO: ['PRONTO', 'SAIU_PARA_ENTREGA', 'CANCELADO'],
  PRONTO: ['SAIU_PARA_ENTREGA', 'CONCLUIDO', 'CANCELADO'],
  SAIU_PARA_ENTREGA: ['CONCLUIDO', 'CANCELADO'],
  CONCLUIDO: [],
  CANCELADO: [],
  RECUSADO: [],
};

export function podeTransicionar(
  de: StatusPedido,
  para: StatusPedido,
  tipo: TipoAtendimento,
): boolean {
  if (!TRANSICOES[de].includes(para)) return false;
  // "Saiu para entrega" só existe para pedidos de entrega.
  if (para === 'SAIU_PARA_ENTREGA' && tipo !== 'ENTREGA') return false;
  return true;
}

export function statusFinal(s: StatusPedido): boolean {
  return TRANSICOES[s].length === 0;
}

/** Etapas exibidas ao cliente no link de acompanhamento. */
export function etapasCliente(tipo: TipoAtendimento): StatusPedido[] {
  return tipo === 'ENTREGA'
    ? [StatusPedido.RECEBIDO, StatusPedido.EM_PREPARO, StatusPedido.SAIU_PARA_ENTREGA, StatusPedido.CONCLUIDO]
    : [StatusPedido.RECEBIDO, StatusPedido.EM_PREPARO, StatusPedido.PRONTO, StatusPedido.CONCLUIDO];
}
