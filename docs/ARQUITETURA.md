# Arquitetura do ApFood (Python / Django)

## Visão geral

```
                    ┌──────────────────────────────────────────────┐
                    │        SERVIDOR (nuvem) — backend/           │
  Cliente (celular) │  Django 5.2 + DRF + Channels (ASGI/Daphne)   │
  ───────────────►  │                                              │
  apfood.app/<slug> │  apps.vitrine  → cardápio digital (HTMX)     │
  WS ws/pedido/<tk> │  /api/...      → API REST p/ o PDV (JWT)     │
                    │  ws/pdv/<loja> → fila de pedidos em tempo real│
                    │  /admin/       → retaguarda / cadastros       │
                    └──────────┬───────────────────┬───────────────┘
                               │                   │
                        PostgreSQL 17         Redis 7 (channel layer)
                               ▲
                               │ HTTPS (push/pull) + WebSocket
                    ┌──────────┴───────────────────────────────────┐
                    │      PDV WINDOWS — desktop/ (PySide6)        │
                    │  UI Qt nativa · alerta sonoro · impressão    │
                    │  térmica ESC/POS · SQLite local (cache +     │
                    │  outbox) · SyncWorker em background          │
                    └──────────────────────────────────────────────┘

        core/ (apfood_core) — regras puras em Python, usadas pelos dois lados
```

## Stack

| Camada | Escolha | Por quê |
|---|---|---|
| Backend / API | **Django 5.2 LTS** + Django REST Framework + SimpleJWT | ORM maduro, migrations, admin pronto para a retaguarda, suporte LTS até 2028 |
| Tempo real | **Django Channels 4** + Redis | WebSocket nativo no mesmo projeto Django; `group_send` a partir de qualquer view/serviço |
| Banco central | **PostgreSQL 17** | Constraints parciais (1 turno aberto por operador), `select_for_update` para estoque e numeração de pedidos. Roda local (Docker) ou gerenciado (Supabase, Neon, RDS) |
| Cardápio digital | **Templates Django + HTMX + Alpine.js** | Mesmo projeto, sem build de front-end; mobile-first e leve em 3G |
| PDV desktop | **PySide6 (Qt 6)** empacotado com **PyInstaller** | Python de ponta a ponta, UI nativa e rápida no Windows, `QSoundEffect` para alerta, `python-escpos` para impressora térmica |
| Offline do PDV | **SQLite** (biblioteca padrão) | Cache dos cadastros + fila *outbox* de operações |
| Regras compartilhadas | **apfood_core** (Python puro) | Cálculo de caixa, totais, máquina de status e enums iguais no servidor e no PDV — instalado com `pip install -e core` |

## Estrutura de pastas

```
apfood/
├── core/                    # pacote apfood_core (sem dependências)
│   ├── apfood_core/         # enums, dinheiro, caixa, pedido_status, totais
│   └── tests/
├── backend/                 # projeto Django
│   ├── config/              # settings (base/dev/prod), urls, asgi, wsgi
│   ├── apps/
│   │   ├── core/            # ModeloBase (UUID, timestamps), soft delete, mixin de loja
│   │   ├── lojas/           # Loja, SequenciaPedido, Dispositivo, comando seed_demo
│   │   ├── contas/          # Usuario (papéis), LogAuditoria
│   │   ├── cardapio/        # Categoria, Produto/Insumo, FichaTecnica, Adicionais
│   │   ├── clientes/        # Cliente, Endereço, ZonaEntrega, Entregador
│   │   ├── caixa/           # TurnoCaixa, MovimentacaoCaixa, ConferenciaCaixa
│   │   ├── pedidos/         # Pedido, Itens, Adicionais do item, Pagamento, Histórico
│   │   ├── estoque/         # MovimentacaoEstoque (kardex)
│   │   ├── financeiro/      # CategoriaDespesa, Despesa
│   │   ├── realtime/        # consumers WebSocket e nomes de grupos
│   │   └── vitrine/         # cardápio digital público
│   └── requirements/
├── desktop/                 # PDV PySide6
│   └── apfood_pdv/          # janela, banco local, sync
└── docs/
```

Cada app Django segue o mesmo padrão a partir do Passo 2: `models.py`, `services.py` (regras que mexem em mais de um model, sempre em `transaction.atomic`), `serializers.py`, `views.py`, `urls.py`, `tests/`.

## Decisões importantes

**Multi-loja desde o início.** Todo model operacional tem `loja`. A API sempre filtra pela loja do usuário autenticado (Passo 2: mixin de queryset).

**UUID gerado no cliente.** O PDV cria o UUID do pedido/pagamento/movimentação offline; o servidor faz *upsert* pelo id. Reenviar uma operação depois de uma queda de rede não duplica nada.

**Dinheiro em centavos (`int`).** Nada de `float`. Formatação e conversão em `apfood_core.dinheiro`.

**Snapshots no pedido.** Nome e preço do produto/adicional e o endereço de entrega são copiados para o pedido. Alterar o cardápio ou o cadastro do cliente não muda pedidos antigos nem os relatórios.

**Número do pedido pelo servidor.** `SequenciaPedido.proximo()` usa `select_for_update` por loja/dia. Pedido criado offline mostra um `codigo_local` (ex.: `C1-0042`) até sincronizar.

**Caixa como livro-razão.** Cada venda, sangria, suprimento, despesa ou estorno é uma `MovimentacaoCaixa` com valor positivo e tipo. O esperado por forma de pagamento é calculado por `apfood_core.caixa.calcular_esperado`, e o fechamento grava uma `ConferenciaCaixa` por forma (esperado × informado × diferença). Conferência **cega** esconde o esperado do operador até ele confirmar.

**Estoque opcional por produto.** `controla_estoque` (o próprio item tem saldo) e/ou `baixar_insumos` (baixa a ficha técnica). Adicionais também podem consumir insumo. A baixa acontece no aceite ou na conclusão (configurável por loja) e é idempotente (`Pedido.estoque_baixado`). Cancelamento estorna.

## Tempo real

| Grupo (Channels) | Quem escuta | Eventos |
|---|---|---|
| `loja_<id>_pdv` | Todos os PDVs da loja | `pedido.novo` (toca o alerta), `pedido.status`, `estoque.alerta`, `catalogo.alterado` |
| `pedido_<token>` | Página de acompanhamento do cliente | `pedido.status` |

Eventos são disparados com `transaction.on_commit` para nunca anunciar algo que sofreu rollback.

## Resiliência do PDV (offline)

1. Toda ação do operador grava primeiro no SQLite local (`outbox`), depois a UI segue.
2. O `SyncWorker` envia a fila em ordem (`POST /api/sync/push/`) e busca alterações de cadastros (`GET /api/sync/pull/?desde=<cursor>`), usando `atualizado_em` como cursor.
3. O WebSocket entrega pedidos online na hora. Se cair, o pull periódico cobre o intervalo, então nenhum pedido se perde.
4. A barra de status mostra online/offline e quantas operações faltam sincronizar.

Limite conhecido: pedidos **online** dependem do servidor. Se a internet da loja cair, os pedidos continuam chegando no servidor e aparecem no PDV quando a conexão voltar.

## Segurança

- Senhas e PINs com Argon2.
- JWT para o PDV (12 h de acesso, refresh de 30 dias com rotação); sessão para o admin.
- Cada PC é cadastrado como `Dispositivo` com token próprio (só o hash fica no banco).
- `LogAuditoria` para cancelamentos, reabertura de caixa, ajustes de estoque e alteração de preço.
