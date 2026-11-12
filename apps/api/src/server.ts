import Fastify from 'fastify';
import cors from '@fastify/cors';
import { prisma } from '@apfood/database';
import { env, corsOrigins } from './env';
import { criarRealtime } from './realtime';

const app = Fastify({ logger: { level: env.NODE_ENV === 'production' ? 'info' : 'debug' } });

await app.register(cors, { origin: corsOrigins });

app.get('/health', async () => {
  await prisma.$queryRaw`SELECT 1`;
  return { ok: true, servico: 'apfood-api', em: new Date().toISOString() };
});

// Passo 2: registrar módulos em src/modules/* (auth, catalogo, pedidos, caixa,
// estoque, clientes, entrega, relatorios, sync, publico).

const io = criarRealtime(app);
app.decorate('io', io);

await app.listen({ port: env.API_PORT, host: '0.0.0.0' });
