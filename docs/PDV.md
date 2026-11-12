# PDV desktop (Windows)

## Instalação
1. Baixe o `ApFoodPDV.exe` em **GitHub → Actions → última execução verde → Artifacts → ApFoodPDV-windows**.
2. Execute. Na primeira vez, informe o **endereço do servidor**, o usuário e a senha, e escolha a loja deste computador.
3. Vá em **Configurações** e defina a impressora do caixa, a da cozinha e a bobina (80 ou 58 mm). Use **Imprimir teste**.

Os dados locais ficam em `%LOCALAPPDATA%\ApFood`: cache do cardápio, fila offline, `config.json` e `pdv.log`.

### Impressoras
| Configuração | Quando usar |
|---|---|
| `192.168.0.50:9100` | impressora térmica de rede (Epson, Elgin, Bematech, Daruma), porta RAW 9100 |
| `EPSON TM-T20` | impressora USB instalada no Windows (nome exato do Painel de Controle) |
| `arquivo:C:/cupons` | sem impressora: grava cada cupom em `.txt` |

Cada **setor de produção** (cadastrado no painel) pode ter a própria impressora: Chapa, Bar, Forno etc. A via da cozinha sai separada por setor, sem preços e em letra grande.

## Telas e atalhos
| Tecla | Tela | O que faz |
|---|---|---|
| F1 | Pedidos | fila em tempo real. O pedido online **toca alerta até ser aceito**. Aceitar (A), recusar, avançar (Espaço), saiu para entrega com motoboy, concluir, receber, cancelar, reimprimir cupom/DANFE e via de cozinha |
| F3 | Novo pedido | balcão: consumo no local ou retirada, com nome, senha ou mesa |
| F4 | Delivery | telefone/WhatsApp: busca o cliente pelo telefone, preenche o endereço, calcula a taxa, escolhe o motoboy e o troco |
| F6 | Mesas | mapa do salão: abrir, lançar rodada, conta, pedir conta, dividir, receber, fechar, transferir, juntar, taxa de serviço |
| F8 | Caixa | abrir com fundo de troco, sangria, suprimento, despesa paga com a gaveta, fechamento **cego** e comprovante |
| F9 | Cozinha | tela da cozinha (KDS) por setor: toque para iniciar e marcar pronto |
| — | Estoque | abaixo do mínimo, saldos, kardex, entrada, perda e inventário (gerente) |
| — | Relatórios | faturamento, ticket médio, canais, formas de pagamento, curva ABC, fechamentos e fluxo de caixa (gerente) |
| Ctrl+T | Trocar operador | troca rápida por usuário e PIN |
| F12 | — | finalizar o pedido · F2 = buscar produto · F5 = atualizar |

## Documento da venda: fiscal ou não fiscal
Ao receber o pagamento, o PDV pede ao servidor o **documento da venda**:

- **Loja com emissor fiscal ativo** (Configuração fiscal + integração Focus NFe): emite a **NFC-e** e imprime o **DANFE NFC-e** na térmica, com chave de acesso, protocolo e QR Code.
- **Loja sem emissor**, ou **NFC-e rejeitada**: imprime o **cupom NÃO FISCAL** ("NÃO É DOCUMENTO FISCAL"). Na rejeição, a nota fica para reemissão em *Notas fiscais*.
- **Sem internet**: o PDV imprime o cupom **não fiscal** sozinho, com o mesmo layout. A nota pode ser emitida depois, quando a venda sincronizar.

## Sem internet
- Vendas de balcão e delivery, pagamentos, sangrias, suprimentos e fechamento continuam funcionando. Tudo vai para a **fila local** e é enviado na ordem quando a conexão volta. O servidor não duplica nada.
- O pedido offline recebe um código local (`CAIXA1-0007`) até ganhar o número oficial.
- A barra de status mostra **● ONLINE/OFFLINE** e quantas operações aguardam envio.
- Se o servidor recusar uma operação ao sincronizar (por exemplo, um produto excluído no meio do caminho), o PDV avisa. A lista fica em *Configurações → Operações recusadas*.
- O que **precisa** de internet: pedidos online e do iFood (eles chegam ao servidor e aparecem quando a conexão voltar), mesas, cozinha, relatórios, Pix dinâmico e NFC-e.

## Atualizações
Ao abrir, o PDV pergunta ao servidor se há versão nova. Ele baixa, confere a assinatura (SHA-256) e reinicia já atualizado. A versão anterior fica guardada como `ApFoodPDV.exe.old`. Atualizações marcadas como obrigatórias não podem ser adiadas. A configuração no servidor está em [INTEGRACOES.md](INTEGRACOES.md#atualização-automática-do-pdv).

## Desenvolvimento
```bash
pip install -e core -e desktop
python -m apfood_pdv                      # abre o PDV
QT_QPA_PLATFORM=offscreen pytest desktop/tests
```
