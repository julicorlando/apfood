# Roadmap

## Passo 2 — API e tempo real
- Auth (login, PIN, refresh, guard por papel) e cadastro de dispositivos
- CRUD de catálogo (categorias, produtos, adicionais, ficha técnica, zonas, entregadores)
- Pedidos: criação PDV (idempotente), criação pública com recálculo de preço, máquina de estados, cancelamento com estorno
- Caixa: abrir, suprimento, sangria, fechamento cego/detalhado
- Estoque: baixa transacional, entradas/ajustes/perdas, kardex, alerta de mínimo
- Sync: `POST /sync/push` (outbox) e `GET /sync/pull?desde=`
- Socket.IO autenticado (salas `loja:` e `pedido:`)
- Testes de integração com PostgreSQL em container

## Passo 3 — PDV desktop
- Login/PIN, abertura de caixa obrigatória antes de vender
- Fila de pedidos online com som, aceitar/recusar, mudança de status
- Balcão (nome/senha/mesa) e Delivery (busca por telefone, endereço, taxa, motoboy)
- Impressão ESC/POS (cozinha e cupom)
- Worker de sync + indicador online/offline
- Estoque, fechamento de caixa, relatórios e dashboard
- Instalador Windows (NSIS) + auto-update

## Passo 4 — Cardápio digital
- Cardápio por categoria, modal de produto com grupos de adicionais (mín./máx.)
- Carrinho, checkout (retirada/entrega, taxa, pagamento, troco)
- Página de acompanhamento em tempo real
- Loja fechada / fora do horário / pedido mínimo
