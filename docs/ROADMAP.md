# Roadmap

## ✅ Passo 1 — Arquitetura, banco e estrutura
- Stack 100% Python: Django + DRF + Channels, PySide6 no desktop, pacote `apfood_core` compartilhado
- Models de todo o domínio com constraints no banco
- Multiempresa: MASTER da plataforma, empresas com limite de lojas e bloqueio, isolamento na retaguarda e no WebSocket
- Esqueleto do WebSocket, do cardápio público e do PDV (SQLite local + outbox)
- Comando `seed_demo`
- Testes das regras de caixa, totais, status e fila offline

## Passo 2 — API e tempo real
- Autenticação JWT + permissões por papel (MASTER / ADMIN / GERENTE / OPERADOR) e mixin de escopo multiempresa em todos os endpoints
- Painel do MASTER: empresas, bloqueio, limites, visão consolidada
- `services.py` por app: criar pedido (validação de adicionais, totais, numeração), transição de status, pagamentos, abertura/sangria/suprimento/fechamento de caixa, baixa e estorno de estoque
- Endpoints REST (cardápio, clientes por telefone, zonas/taxa, pedidos, caixa, estoque, relatórios)
- `POST /api/sync/push/` (idempotente por UUID) e `GET /api/sync/pull/`
- Eventos Channels com `transaction.on_commit`
- Testes com pytest-django

## Passo 3 — PDV desktop (PySide6)
- Login por usuário/PIN, pareamento do dispositivo
- Fila de pedidos online com alerta sonoro/visual, aceitar/recusar, cupom de cozinha ESC/POS
- Balcão (nome/senha/mesa) e Delivery (busca por telefone, endereço, taxa, motoboy)
- Abertura, sangria, suprimento e fechamento (cego ou detalhado) com relatório de quebra/sobra
- Estoque: entradas, ajustes, alertas de mínimo, kardex
- Relatórios e dashboard
- Instalador Windows (PyInstaller + Inno Setup)

## Passo 4 — Cardápio digital
- Cardápio mobile-first por slug, carrinho, adicionais com mín/máx
- Endereço com cálculo de taxa, retirada, forma de pagamento e troco
- Acompanhamento em tempo real pelo link do pedido
