# ApFood

Sistema de gestão e PDV para restaurantes e hamburguerias, com cardápio digital e sincronização em tempo real.

| App | Descrição | Stack |
|---|---|---|
| `apps/web` | Cardápio digital mobile-first e acompanhamento do pedido | Next.js + React |
| `apps/desktop` | PDV Windows: pedidos online, balcão, delivery, caixa, estoque, relatórios | Electron + React + SQLite local |
| `apps/api` | API REST + tempo real | Fastify + Socket.IO + Prisma |
| `packages/database` | Schema, migrations e seed | Prisma + PostgreSQL |
| `packages/shared` | Enums, validação (zod), cálculo de caixa e totais, contrato de eventos | TypeScript |

📐 [Arquitetura](docs/ARQUITETURA.md) · 🗄️ [Banco de dados](docs/BANCO_DE_DADOS.md) · 🗺️ [Roadmap](docs/ROADMAP.md)

## Rodando localmente

Requisitos: Node 22+, pnpm 10+, Docker.

```bash
pnpm install
cp .env.example .env
cp .env packages/database/.env   # o Prisma lê o .env da pasta do schema

pnpm db:up          # sobe o PostgreSQL no Docker
pnpm db:migrate     # cria as tabelas (nomeie a migration: "inicial")
pnpm db:extras      # índices parciais e CHECKs
pnpm db:seed        # loja demo "burger-demo" + usuários admin/gerente/caixa1 (senha: apfood123)

pnpm dev:api        # http://localhost:3333/health
pnpm dev:web        # http://localhost:3000/burger-demo
pnpm dev:desktop    # abre o PDV
```

Testes das regras compartilhadas (caixa, totais, status):

```bash
pnpm --filter @apfood/shared test
```

## Status

- [x] **Passo 1** — arquitetura, modelagem do banco, estrutura do monorepo
- [ ] **Passo 2** — API e sincronização em tempo real
- [ ] **Passo 3** — App PC (PDV)
- [ ] **Passo 4** — Cardápio digital
