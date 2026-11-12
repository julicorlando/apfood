# Módulos da API (implementação no Passo 2)

Cada módulo segue `routes.ts` (HTTP + validação zod) → `service.ts` (regra de negócio, transações Prisma) → eventos Socket.IO.

| Módulo | Rotas principais | Observações |
|---|---|---|
| `auth` | `POST /auth/login`, `/auth/pin`, `/auth/refresh` | JWT curto + refresh; PIN para troca rápida de operador no PDV |
| `catalogo` | CRUD categorias, produtos, grupos de adicionais, ficha técnica | Emite `catalogo:alterado` |
| `publico` | `GET /p/:slug/cardapio`, `POST /p/:slug/pedidos`, `GET /p/pedido/:token` | Sem login, com rate limit; preço recalculado no servidor |
| `pedidos` | criar (PDV), aceitar/recusar, mudar status, cancelar | Máquina de estados em `@apfood/shared`; emite `pedido:*` |
| `caixa` | abrir turno, suprimento, sangria, fechar (cega/detalhada) | Esperado calculado com `calcularEsperado` |
| `estoque` | entradas, ajustes, perdas, kardex, alertas | Baixa automática dentro da mesma transação do pedido |
| `clientes` | busca por telefone, endereços | Auto-preenchimento no delivery |
| `entrega` | zonas, cálculo de taxa (bairro/raio), entregadores | |
| `relatorios` | faturamento, ticket médio, curva ABC, canais, fechamentos, fluxo de caixa | Consultas SQL agregadas |
| `sync` | `POST /sync/push`, `GET /sync/pull?desde=` | Upsert idempotente por UUID; cursor por `updatedAt` |
