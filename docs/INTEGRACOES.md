# Integrações e rotinas do servidor

Cadastre em **Admin → Integrações** (por loja). As credenciais são **cifradas** (Fernet) com a chave `APFOOD_CHAVE_CRIPTO`: gere com `python manage.py gerar_chave_cripto` e guarde no `.env`. Elas nunca aparecem na API nem no admin.

| Tipo | Provedor | Credenciais | Configuração |
|---|---|---|---|
| FISCAL | `focusnfe` | `{"token": "..."}` | `{"cnpj_emitente": "...", "csc_id"?: "..."}` + **Configuração fiscal** da loja (regime, ambiente, série, emitir automático) |
| PAGAMENTO | `mercadopago` | `{"access_token": "...", "webhook_secret": "..."}` | webhook: `https://SEU_SERVIDOR/api/webhooks/mercadopago/<loja_id>/` |
| WHATSAPP | `zapi` | `{"instancia": "...", "token": "...", "client_token": "..."}` | avisa o cliente a cada etapa do pedido |
| MARKETPLACE | `ifood` | `{"client_id": "...", "client_secret": "..."}` | `{"merchant_id": "..."}`. No catálogo do iFood, use o **código externo = id ou código do produto** no ApFood |

O certificado A1 e o CSC ficam cadastrados **no painel da Focus NFe**: o ApFood não guarda certificado. Comece em **HOMOLOGAÇÃO** e valide os campos fiscais (NCM, CFOP, CST/CSOSN) com o contador antes de ir para produção.

## Rotinas (rodar como serviço/cron no servidor)
| Comando | Frequência | O que faz |
|---|---|---|
| `python manage.py processar_tarefas --loop` | contínuo | fila de tarefas: WhatsApp, consulta de NFC-e em processamento, ações no iFood, emissão automática, com retentativa |
| `python manage.py ifood_polling --loop` | contínuo (30 s) | busca pedidos novos e cancelamentos no iFood |
| `python manage.py cobranca_diaria` | 1×/dia | gera as faturas mensais das empresas, marca inadimplência, **bloqueia** após a tolerância e reativa ao pagar |

## Limitações conhecidas
- As integrações foram testadas com **respostas simuladas**, seguindo a documentação pública de cada provedor. Valide cada uma no ambiente de homologação/sandbox antes de usar com clientes.
- SAT (SP) e NF-e modelo 55 têm modelo de dados pronto, mas só a **NFC-e via Focus NFe** está implementada.
- Taxa de entrega por **bairro** e por **raio a partir das coordenadas**. Não há geocodificação automática de endereço: o raio só vale quando o pedido traz latitude/longitude.
