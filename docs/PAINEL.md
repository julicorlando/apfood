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

**Quem acessa o quê:** o MASTER (dono da plataforma) administra empresas, lojas, usuários, planos e faturas, mas **não opera as lojas dos clientes**: não vê nem altera cardápio, pedidos, caixa, estoque, clientes ou relatórios de loja. Cada empresa (ADMIN) acessa só as suas lojas; GERENTE e OPERADOR, só as lojas vinculadas a eles.

O seletor no topo troca a loja ativa, para quem tem acesso a mais de uma.

## Páginas públicas

| Endereço | O que é |
|---|---|
| `/planos/` | Planos e **cadastro self-service**: o restaurante cria a conta sozinho, em teste grátis (empresa + loja + administrador), e entra direto no painel. Só aparecem os planos marcados como "públicos". |
| `/painel/senha/esqueci/` | **Esqueci minha senha**: link por e-mail que vale 2 horas (precisa do `EMAIL_URL`, ver DEPLOY.md). |
| `/termos/` e `/privacidade/` | **Termos de uso** e **Política de privacidade (LGPD)**. Os dados da empresa vêm das variáveis `APFOOD_LEGAL_*` (ver DEPLOY.md). Enquanto faltar alguma, a página mostra o aviso "Rascunho". Os links aparecem no cadastro, no login e na página inicial. |
| `/entrega/<link>/` | **Tela do entregador**, no celular: as entregas dele, mapa, botão de ligar, quanto cobrar e "Entregue". O link é gerado em Clientes e entrega → Entregadores → **Link do celular** (gerar outro desativa o anterior). |

## Cashback

Em **Dados da loja → Fidelidade**, defina o percentual. Cada pedido **concluído** de um cliente identificado pelo telefone gera saldo (sem contar a taxa de entrega). No PDV, ao buscar o telefone, aparece **"Usar cashback"**, que vira desconto. Se o pedido for cancelado, o saldo usado volta para o cliente. O saldo aparece na lista de Clientes. O PDV para Windows também usa: informe o telefone no balcão (ou busque o cliente no delivery) e marque **"Usar cashback"**.

## LGPD: anonimizar cliente

Em **Clientes**, o botão **Anonimizar** (gerente+) apaga nome, telefone, e-mail, CPF, nascimento, observações e endereços do cliente, desliga o marketing e zera o cashback. Os pedidos dele perdem nome, telefone e endereço, mas os valores continuam nos relatórios. Notas fiscais já emitidas são mantidas, porque a lei obriga. Não tem como desfazer. Na API: `POST /api/clientes/<id>/anonimizar/`.

## Assinatura (cobrança da plataforma)

- **Rotina diária** (serviço `cobranca`): gera a fatura do mês, cria o Pix no Mercado Pago da plataforma (`APFOOD_MP_TOKEN_PLATAFORMA`) e marca inadimplência. Depois de `APFOOD_DIAS_TOLERANCIA` dias de atraso, bloqueia a empresa. O pagamento confirmado pelo webhook libera o acesso sozinho.
- **E-mails** para o e-mail da empresa e dos administradores: fatura nova (com o link do Pix), lembrete 3 dias antes do vencimento, fatura vencida, acesso suspenso, pagamento confirmado e fim do teste grátis em 3 dias. Precisa do `EMAIL_URL`.
- **Login bloqueado por falta de pagamento** mostra a fatura e o botão **Pagar com Pix**.
- **Recebimentos (MASTER):** em **Plataforma → Recebimentos**, cole o access token de produção do Mercado Pago (conferido e guardado cifrado) e escolha como o cliente paga: **página do Mercado Pago** (Pix, cartão em até 12x e boleto) ou **só Pix**. A tela mostra o recebido no mês, o que está a vencer e o vencido, e o endereço do webhook para cadastrar no Mercado Pago. Em **Faturas**: gerar o link, copiar e **marcar paga** (baixa manual, libera a empresa bloqueada).
- **Painel:** uma faixa no topo avisa o ADMIN sobre fatura em aberto, fatura vencida ou fim do teste (7 dias antes). Em **Minha empresa**, o ADMIN vê as faturas e **troca de plano**. A troca vale a partir da próxima fatura e respeita o limite de lojas e usuários do plano. Na API: `GET/POST /api/assinatura/`.

## Promoções programadas

Em **Clientes e entrega → Promoções** (gerente+): desconto automático por dia da semana e horário, por exemplo "Terça do hambúrguer: 20% off das 18h às 23h".
- **Tipos:** % de desconto, R$ de desconto por item ou preço fixo (ex.: lata por R$ 5,00).
- **Para quais produtos:** produtos e/ou categorias escolhidos. Sem nenhum marcado, vale o cardápio todo.
- **Onde vale:** cardápio online, balcão, delivery ou mesas. Nenhum marcado = todos. Pedidos do iFood nunca entram.
- **Quando:** dias da semana, horário (pode passar da meia-noite: 18:00–02:00 vale pela noite em que começou) e período opcional (começa/termina em).
- Se duas promoções valerem para o mesmo item, fica a de maior desconto. O desconto é no preço do produto, não nos adicionais.
- **Onde aparece:** o cardápio online mostra o preço riscado, um selo e a faixa "Promoções de hoje". O PDV web e o PDV do computador mostram 🔥 no botão do produto. O servidor sempre recalcula, e o item do pedido guarda qual promoção foi aplicada.

## Mesas: pagamento parcial

Na comanda, **Receber (total ou parte)** aceita só uma parte da conta: o cliente 1 paga a parte dele e vai embora, e a mesa continua aberta para quem ficou pedir mais e pagar depois.
- Tem botões para dividir o que falta por 2, 3, 4 ou 5 e um campo **Quem está pagando** ("Cliente 1", "João"), que aparece na conta.
- Mesmo depois de pedir a conta, dá para reabrir a mesa e lançar mais itens: os pagamentos já feitos continuam abatidos.
- A mesa só é liberada em **Fechar comanda**, quando não falta nada.
- No PDV do computador funciona igual: Mesas → Receber (total ou parte).

## Número do pedido no balcão

Pedido de balcão sem senha informada ganha o número do pedido do dia com 4 dígitos (ex.: **0124**), impresso no cupom e mostrado no PDV para chamar o cliente. Sem internet, o PDV do computador numera sozinho (sequência do dia naquele caixa). No PDV do computador, sem itens no pedido aparece **CAIXA LIVRE** (ou **CAIXA FECHADO**, se o caixa não foi aberto) com o último número chamado.

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
- **Impressão direta:** com o **ApFood PDV (0.3.5+)** aberto no mesmo computador, o cupom sai direto na térmica configurada no PDV, sem a janela de impressão. A via da cozinha vai para a impressora de cada setor. O PDV abre uma "ponte" em `http://127.0.0.1:17777`, que só aceita chamadas vindas do endereço do servidor configurado nele. No Chrome, permita o acesso a "apps e serviços deste dispositivo" quando ele pedir. Para ver o estado, testar ou desligar: **Configurações → Impressão**. A porta muda em `porta_ponte` no `config.json` do PDV (0 desliga).
- **Sem o PDV:** sai pela janela de impressão do navegador, em papel de 80 mm. O QR Code (NFC-e e Pix) é gerado pelo servidor em `/painel/qrcode.svg`.

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
