import type { StatusPedido } from './enums';

/**
 * Contrato dos eventos em tempo real (Socket.IO). Salas:
 *   loja:{lojaId}            → desktops/PDVs da loja (pedidos, estoque, caixa)
 *   pedido:{tokenRastreio}   → página pública de acompanhamento do cliente
 */

export interface PedidoResumoEvento {
  id: string;
  numero: number | null;
  canal: 'ONLINE' | 'BALCAO' | 'DELIVERY';
  status: StatusPedido;
  nomeCliente: string | null;
  totalCentavos: number;
  createdAt: string;
}

export interface ServerToClientEvents {
  'pedido:novo': (p: PedidoResumoEvento) => void;
  'pedido:atualizado': (p: PedidoResumoEvento) => void;
  'pedido:status': (p: { id: string; status: StatusPedido; em: string }) => void;
  'estoque:alerta-minimo': (p: { produtoId: string; nome: string; saldo: string }) => void;
  'catalogo:alterado': (p: { entidade: string; ids: string[] }) => void;
  'sync:recomendado': () => void; // força pull após reconexão
}

export interface ClientToServerEvents {
  'loja:entrar': (p: { lojaId: string }, ack: (ok: boolean) => void) => void;
  'pedido:acompanhar': (p: { tokenRastreio: string }, ack: (ok: boolean) => void) => void;
}
