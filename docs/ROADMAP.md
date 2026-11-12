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

## ✅ Passo 2b — Integrações e plataforma
- NFC-e via Focus NFe (emissão, consulta, cancelamento, DANFE na térmica com QR Code); sem emissor → cupom não fiscal
- Pix dinâmico (Mercado Pago) com webhook; WhatsApp (Z-API) a cada etapa; iFood (polling, importação, ações)
- Credenciais cifradas, fila de tarefas com retentativa, WebSocket por JWT
- Cobrança das empresas: faturas, inadimplência, bloqueio e reativação automáticos

## ✅ Passo 3 — PDV desktop (PySide6)
- Login, escolha de loja, sessão salva e troca de operador por PIN
- Fila em tempo real com alerta sonoro, balcão, delivery por telefone, mesas/comandas, caixa com fechamento cego, KDS, estoque, relatórios
- Impressão ESC/POS (rede, Windows, arquivo) por setor; DANFE NFC-e ou cupom não fiscal
- Funciona offline (fila local + cupom não fiscal local)
- `ApFoodPDV.exe` gerado pela CI

### Próximas melhorias
- Geocodificação de endereço (Google/OSM) para taxa por raio sem coordenadas
- SAT/CF-e (SP) e NF-e modelo 55
- Instalador com atualização automática (hoje: baixar o novo `.exe`)
- Painel web de retaguarda próprio (hoje: Django admin)

## Passo 4 — Cardápio digital
- Cardápio mobile-first por slug, carrinho, adicionais com mín/máx
- Endereço com cálculo de taxa, retirada, forma de pagamento e troco
- Acompanhamento em tempo real pelo link do pedido
