# Roadmap

## ✅ Passo 1 — Arquitetura, banco e estrutura
- Stack 100% Python: Django + DRF + Channels, PySide6 no desktop, pacote `apfood_core` compartilhado
- Models de todo o domínio com constraints no banco
- Multiempresa: MASTER da plataforma, empresas com limite de lojas e bloqueio, isolamento na retaguarda e no WebSocket
- Esqueleto do WebSocket, do cardápio público e do PDV (SQLite local + outbox)
- Comando `seed_demo`
- Testes das regras de caixa, totais, status e fila offline

## ✅ Passo 1b — Modelagem ampliada
- Fiscal (NFC-e/SAT/NF-e via provedor), mesas e comandas, variações (P/M/G), pizza meio a meio, combos
- Setores de produção (impressora por setor) e status de produção por item (KDS)
- Fornecedores e compras (custo médio, conta a pagar), contas a pagar, taxas de maquininha
- Cupons, LGPD no cliente, planos/faturas das empresas, integrações e webhooks

## ✅ Passo 2 — Regras de negócio, API e tempo real
- Serviços: pedidos (montagem, totais, taxa, cupom, status, estoque, pagamentos), caixa, estoque, comandas, compras
- API REST com escopo multiempresa, cozinha (KDS), relatórios e resumo do MASTER
- Sincronização do PDV (pull por cursor, push idempotente) e cardápio público
- CI no GitHub Actions com PostgreSQL

### Pendências do Passo 2 (entram junto com os passos 3/4)
- Integrações reais: emissor fiscal, Pix com webhook, iFood/99Food, WhatsApp, geocodificação
- Criptografia das credenciais de integração
- Cobrança automática das faturas das empresas e bloqueio por inadimplência
- WebSocket: autenticação por JWT (hoje usa sessão)

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
