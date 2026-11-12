import { z } from 'zod';

/** Schemas de entrada compartilhados (validação na API e nos formulários). */

const uuid = z.string().uuid();
const centavos = z.number().int().nonnegative();

export const itemPedidoInput = z.object({
  produtoId: uuid,
  quantidade: z.number().int().positive().max(99),
  observacao: z.string().max(200).optional(),
  adicionais: z
    .array(z.object({ adicionalId: uuid, quantidade: z.number().int().positive().max(10) }))
    .default([]),
});

export const enderecoEntregaInput = z.object({
  logradouro: z.string().min(2),
  numero: z.string().min(1),
  complemento: z.string().optional(),
  bairro: z.string().min(2),
  cidade: z.string().min(2),
  cep: z.string().optional(),
  referencia: z.string().optional(),
  latitude: z.number().optional(),
  longitude: z.number().optional(),
});

export const pagamentoInput = z.object({
  forma: z.enum(['DINHEIRO', 'PIX', 'CARTAO_CREDITO', 'CARTAO_DEBITO', 'VOUCHER', 'OUTRO']),
  valorCentavos: centavos.positive(),
  valorRecebidoCentavos: centavos.optional(),
});

/** Pedido do cardápio digital. Preços NUNCA vêm do cliente — a API recalcula. */
export const criarPedidoOnlineInput = z
  .object({
    nomeCliente: z.string().min(2).max(80),
    telefoneCliente: z.string().regex(/^\d{10,11}$/, 'Telefone com DDD, só números'),
    tipoAtendimento: z.enum(['RETIRADA', 'ENTREGA']),
    endereco: enderecoEntregaInput.optional(),
    itens: z.array(itemPedidoInput).min(1),
    formaPagamento: pagamentoInput.shape.forma,
    trocoParaCentavos: centavos.optional(),
    observacao: z.string().max(300).optional(),
  })
  .refine((p) => p.tipoAtendimento !== 'ENTREGA' || !!p.endereco, {
    message: 'Endereço obrigatório para entrega',
    path: ['endereco'],
  });

/** Pedido lançado no PDV (balcão ou delivery por telefone). Aceita id do cliente (offline). */
export const criarPedidoPdvInput = z.object({
  id: uuid, // gerado no desktop → idempotência
  canal: z.enum(['BALCAO', 'DELIVERY']),
  origemContato: z.enum(['TELEFONE', 'WHATSAPP', 'PRESENCIAL']).optional(),
  tipoAtendimento: z.enum(['CONSUMO_LOCAL', 'RETIRADA', 'ENTREGA']),
  clienteId: uuid.optional(),
  nomeCliente: z.string().max(80).optional(),
  telefoneCliente: z.string().optional(),
  mesa: z.string().max(10).optional(),
  senha: z.string().max(10).optional(),
  endereco: enderecoEntregaInput.optional(),
  entregadorId: uuid.optional(),
  taxaEntregaCentavos: centavos.default(0),
  descontoCentavos: centavos.default(0),
  itens: z.array(itemPedidoInput).min(1),
  pagamentos: z.array(pagamentoInput).default([]),
  observacao: z.string().max(300).optional(),
  criadoEm: z.string().datetime(), // horário real do lançamento (pode ser offline)
});

export const abrirTurnoInput = z.object({ id: uuid, valorAberturaCentavos: centavos });

export const movimentacaoCaixaInput = z.object({
  id: uuid,
  tipo: z.enum(['SUPRIMENTO', 'SANGRIA']),
  valorCentavos: centavos.positive(),
  motivo: z.string().max(200).optional(),
});

export const fecharTurnoInput = z.object({
  tipoConferencia: z.enum(['CEGA', 'DETALHADA']),
  informado: z.record(z.string(), centavos),
  observacao: z.string().max(500).optional(),
});

export type CriarPedidoOnlineInput = z.infer<typeof criarPedidoOnlineInput>;
export type CriarPedidoPdvInput = z.infer<typeof criarPedidoPdvInput>;
export type AbrirTurnoInput = z.infer<typeof abrirTurnoInput>;
export type MovimentacaoCaixaInput = z.infer<typeof movimentacaoCaixaInput>;
export type FecharTurnoInput = z.infer<typeof fecharTurnoInput>;
