# Painel web

Endereço: **`/painel/`**. Pela página inicial do site, o botão **Entrar no painel** leva até ele.

Tudo o que o PDV para Windows faz também pode ser feito pelo navegador, no computador, tablet ou celular. Por isso o app desktop é opcional: ele só é necessário para quem quer **trabalhar offline** ou imprimir direto numa térmica ESC/POS sem a janela de impressão do navegador.

## Telas

| Área | Telas | Quem vê |
|---|---|---|
| Operação | Início (vendas do dia, pedidos, estoque baixo, abrir/fechar pedidos online), **PDV**, **Pedidos** (quadro em tempo real), **Mesas e comandas**, **Cozinha** (KDS), **Caixa** | todos |
| Cardápio | Produtos (com tamanhos, adicionais, ficha técnica e foto), Categorias, Adicionais, Setores de produção, Insumos | todos leem; gerente+ altera |
| Clientes e entrega | Clientes (com endereços), Entregadores, Zonas de entrega, Cupons, Cadastro de mesas | todos leem; gerente+ altera |
| Estoque e compras | Estoque (saldos, abaixo do mínimo, movimentações), Compras (entrada de nota), Fornecedores | gerente+ |
| Financeiro | Contas a pagar, Fluxo de caixa, Categorias de despesa, Taxas de pagamento | gerente+ |
| Relatórios | Vendas, Curva ABC, Fechamentos de caixa, Notas fiscais | gerente+ (notas: todos) |
| Configurações | Dados da loja e horários, Fiscal, Integrações, Usuários, Lojas, Minha empresa | admin+ (usuários: gerente+) |
| Plataforma | Visão geral, Empresas (cadastro com loja e admin num passo só), Planos, Faturas | só o MASTER |

O seletor no topo troca a loja ativa, para quem tem acesso a mais de uma.

## Páginas públicas

| Endereço | O que é |
|---|---|
| `/planos/` | Planos e **cadastro self-service**: o restaurante cria a conta sozinho, em teste grátis (empresa + loja + administrador), e entra direto no painel. Só aparecem os planos marcados como "públicos". |
| `/painel/senha/esqueci/` | **Esqueci minha senha**: link por e-mail que vale 2 horas (precisa do `EMAIL_URL`, ver DEPLOY.md). |
| `/entrega/<link>/` | **Tela do entregador**, no celular: as entregas dele, mapa, botão de ligar, quanto cobrar e "Entregue". O link é gerado em Clientes e entrega → Entregadores → **Link do celular** (gerar outro desativa o anterior). |

## Cashback

Em **Dados da loja → Fidelidade**, defina o percentual. Cada pedido **concluído** de um cliente identificado pelo telefone gera saldo (sem contar a taxa de entrega). No PDV, ao buscar o telefone, aparece **"Usar cashback"**, que vira desconto. Se o pedido for cancelado, o saldo usado volta para o cliente. O saldo aparece na lista de Clientes. O PDV para Windows também usa: informe o telefone no balcão (ou busque o cliente no delivery) e marque **"Usar cashback"**.

## Campanhas de WhatsApp

Em **Clientes e entrega → Campanhas WhatsApp** (gerente+), escreva a mensagem e escolha o público:
- todos que aceitam promoções;
- quem tem saldo de cashback;
- quem não compra há X dias.

A mensagem aceita `{nome}`, `{loja}`, `{cashback}` e `{link}` (o cardápio da loja). **Revisar e enviar** mostra quantos vão receber e um exemplo.

- **Quem recebe:** só clientes com "Aceita receber promoções" marcado (LGPD).
- **Envio:** pela integração **Z-API**, uma mensagem a cada 8 segundos, pela fila de tarefas, para o número não ser bloqueado. A lista mostra enviados e falhas.

## PDV no navegador

- **Comer aqui, Para viagem ou Delivery.** No delivery, buscar o telefone preenche o cliente e o endereço salvo, e a taxa vem da zona de entrega.
- **Montagem do item:** tamanho, meio a meio (pizza), adicionais com limite por grupo e observação. O preço segue as mesmas regras do cardápio online (`vitrine/carrinho.js`), e o servidor recalcula tudo ao salvar.
- **Ao finalizar:** receber agora (dinheiro com troco, Pix, cartão, vale) ou na entrega, imprimir o cupom e a via da cozinha.
- **Documento da venda:** com emissor fiscal ativo sai a NFC-e; sem emissor, o comprovante não fiscal.
- **Impressão:** pela janela de impressão do navegador, em papel de 80 mm. O QR Code (NFC-e e Pix) é gerado pelo servidor em `/painel/qrcode.svg`.

## Tempo real

O painel abre o mesmo WebSocket do PDV (`/ws/pdv/<loja>/`, autenticado pela sessão):

- pedido novo dá aviso sonoro e mensagem na tela;
- quadro de pedidos, mesas e cozinha se atualizam sozinhos;
- se a conexão cair, reconecta sozinho, e as telas também recarregam a cada 15 a 30 segundos.

## Como é feito

- **Login:** `/painel/entrar/` cria a sessão do Django. Usuário de empresa bloqueada não entra.
- **Telas:** `/painel/` é uma página única. O JavaScript (módulos ES, sem build) fica em `apps/painel/static/painel/js/`:
  - `api.js`: cliente da API, com CSRF e loja ativa;
  - `ui.js`: blocos de interface, sem `innerHTML` com dados;
  - `form.js` e `crud.js`: formulários e listas genéricas;
  - `paginas/*.js`: as telas.
- **Dados:** toda leitura e gravação passa pela **mesma API REST do PDV** (`/api/...`), com as mesmas permissões por perfil e o mesmo isolamento entre empresas. O que antes só existia no admin do Django ganhou endpoints próprios em `apps/api/gestao.py`:
  - `lojas`, `empresas` (com `onboarding`), `usuarios`, `integracoes` (credenciais cifradas que nunca voltam pela API);
  - `fiscal/configuracao`, `planos`, `faturas` e `enums` (os rótulos em português).
- O `/admin/` do Django continua disponível para suporte técnico.
