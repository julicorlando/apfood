import type { FastifyInstance } from 'fastify';
import { Server } from 'socket.io';
import type { ClientToServerEvents, ServerToClientEvents } from '@apfood/shared';
import { corsOrigins } from './env';

export type RealtimeServer = Server<ClientToServerEvents, ServerToClientEvents>;

declare module 'fastify' {
  interface FastifyInstance {
    io: RealtimeServer;
  }
}

/**
 * Socket.IO acoplado ao servidor HTTP do Fastify.
 * Passo 2: autenticar o handshake do desktop (JWT) antes de permitir 'loja:entrar'
 * e validar o tokenRastreio no banco antes de 'pedido:acompanhar'.
 */
export function criarRealtime(app: FastifyInstance): RealtimeServer {
  const io: RealtimeServer = new Server(app.server, {
    cors: { origin: corsOrigins },
    connectionStateRecovery: { maxDisconnectionDuration: 2 * 60 * 1000 },
  });

  io.on('connection', (socket) => {
    socket.on('loja:entrar', ({ lojaId }, ack) => {
      void socket.join(`loja:${lojaId}`);
      ack(true);
    });
    socket.on('pedido:acompanhar', ({ tokenRastreio }, ack) => {
      void socket.join(`pedido:${tokenRastreio}`);
      ack(true);
    });
  });

  return io;
}
