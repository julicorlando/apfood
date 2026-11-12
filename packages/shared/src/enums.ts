/**
 * Enums espelhados do schema Prisma como objetos `const`, para que web e
 * desktop (renderer) usem os mesmos valores sem depender do @prisma/client.
 * Mantenha em sincronia com packages/database/prisma/schema.prisma.
 */

export const PapelUsuario = { ADMIN: 'ADMIN', GERENTE: 'GERENTE', OPERADOR: 'OPERADOR' } as const;
export type PapelUsuario = (typeof PapelUsuario)[keyof typeof PapelUsuario];

export const CanalVenda = { ONLINE: 'ONLINE', BALCAO: 'BALCAO', DELIVERY: 'DELIVERY' } as const;
export type CanalVenda = (typeof CanalVenda)[keyof typeof CanalVenda];

export const TipoAtendimento = {
  CONSUMO_LOCAL: 'CONSUMO_LOCAL',
  RETIRADA: 'RETIRADA',
  ENTREGA: 'ENTREGA',
} as const;
export type TipoAtendimento = (typeof TipoAtendimento)[keyof typeof TipoAtendimento];

export const StatusPedido = {
  PENDENTE: 'PENDENTE',
  RECEBIDO: 'RECEBIDO',
  EM_PREPARO: 'EM_PREPARO',
  PRONTO: 'PRONTO',
  SAIU_PARA_ENTREGA: 'SAIU_PARA_ENTREGA',
  CONCLUIDO: 'CONCLUIDO',
  CANCELADO: 'CANCELADO',
  RECUSADO: 'RECUSADO',
} as const;
export type StatusPedido = (typeof StatusPedido)[keyof typeof StatusPedido];

export const FormaPagamento = {
  DINHEIRO: 'DINHEIRO',
  PIX: 'PIX',
  CARTAO_CREDITO: 'CARTAO_CREDITO',
  CARTAO_DEBITO: 'CARTAO_DEBITO',
  VOUCHER: 'VOUCHER',
  OUTRO: 'OUTRO',
} as const;
export type FormaPagamento = (typeof FormaPagamento)[keyof typeof FormaPagamento];

export const TipoMovimentacaoCaixa = {
  VENDA: 'VENDA',
  ESTORNO_VENDA: 'ESTORNO_VENDA',
  SUPRIMENTO: 'SUPRIMENTO',
  SANGRIA: 'SANGRIA',
  DESPESA: 'DESPESA',
} as const;
export type TipoMovimentacaoCaixa = (typeof TipoMovimentacaoCaixa)[keyof typeof TipoMovimentacaoCaixa];

export const ROTULO_STATUS: Record<StatusPedido, string> = {
  PENDENTE: 'Aguardando confirmação',
  RECEBIDO: 'Recebido',
  EM_PREPARO: 'Em preparo',
  PRONTO: 'Pronto',
  SAIU_PARA_ENTREGA: 'Saiu para entrega',
  CONCLUIDO: 'Concluído',
  CANCELADO: 'Cancelado',
  RECUSADO: 'Recusado',
};

export const ROTULO_FORMA_PAGAMENTO: Record<FormaPagamento, string> = {
  DINHEIRO: 'Dinheiro',
  PIX: 'Pix',
  CARTAO_CREDITO: 'Cartão de crédito',
  CARTAO_DEBITO: 'Cartão de débito',
  VOUCHER: 'Vale-refeição',
  OUTRO: 'Outro',
};
