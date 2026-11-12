# Integrações e rotinas do servidor

Cadastre em **Admin → Integrações** (por loja). As credenciais são **cifradas** (Fernet) com a chave `APFOOD_CHAVE_CRIPTO`: gere com `python manage.py gerar_chave_cripto` e guarde no `.env`. Elas nunca aparecem na API nem no admin.

| Tipo | Provedor | Credenciais | Configuração |
|---|---|---|---|
| FISCAL | `focusnfe` | `{"token": "..."}` | `{"cnpj_emitente": "...", "csc_id"?: "..."}` + **Configuração fiscal** da loja (regime, ambiente, série, emitir automático) |
| PAGAMENTO | `mercadopago` | `{"access_token": "...", "webhook_secret": "..."}` | webhook: `https://SEU_SERVIDOR/api/webhooks/mercadopago/<loja_id>/` |
| WHATSAPP | `zapi` | `{"instance": "...", "token": "...", "client_token": "..."}` | avisa o cliente a cada etapa do pedido |
| MAPAS | `google` ou `nominatim` | Google: `{"api_key": "..."}` · Nominatim: nenhuma | Nominatim: `{"email": "contato@loja.com"}` (exigência do OpenStreetMap). Transforma o endereço digitado em coordenadas para a **taxa por raio**; cache de 30 dias |
| MARKETPLACE | `ifood` | `{"client_id": "...", "client_secret": "..."}` | `{"merchant_id": "..."}`. No catálogo do iFood, use o **código externo = id ou código do produto** no ApFood |

**Documentos fiscais:** NFC-e (modelo 65) no balcão/delivery para consumidor; **NF-e (modelo 55)** para venda a empresa (`POST /api/pedidos/{id}/nfe/` com o destinatário: CNPJ/CPF, IE, endereço). A NF-e é assíncrona (a fila consulta até autorizar) e o DANFE é A4 (PDF do provedor). **CF-e SAT não é suportado:** a emissão está vedada em SP desde 01/01/2026 (Portaria SRE 79/2024), e a NFC-e o substitui.

O certificado A1 e o CSC ficam cadastrados **no painel da Focus NFe**: o ApFood não guarda certificado. Comece em **HOMOLOGAÇÃO** e valide os campos fiscais (NCM, CFOP, CST/CSOSN) com o contador antes de ir para produção.

## Rotinas (rodar como serviço/cron no servidor)
| Comando | Frequência | O que faz |
|---|---|---|
| `python manage.py processar_tarefas` | contínuo (`--uma-vez` para cron) | fila de tarefas: WhatsApp, consulta de NFC-e em processamento, ações no iFood, emissão automática, com retentativa |
| `python manage.py ifood_polling` | contínuo (`--uma-vez` para cron) | busca pedidos novos e cancelamentos no iFood |
| `python manage.py cobranca_diaria` | 1×/dia | gera as faturas mensais das empresas, marca inadimplência, **bloqueia** após a tolerância e reativa ao pagar |

## Limitações conhecidas
- As integrações foram testadas com **respostas simuladas**, seguindo a documentação pública de cada provedor. Valide cada uma no ambiente de homologação/sandbox antes de usar com clientes.
- Só a Focus NFe está implementada como emissor (NFC-e e NF-e).
- Taxa de entrega: bairro cadastrado → raio pelas coordenadas recebidas → raio por geocodificação (se a integração MAPAS estiver ativa). Sem MAPAS, endereço fora dos bairros cadastrados e sem coordenadas fica "fora da área" no site; no PDV, o atendente informa a taxa.

## Atualização automática do PDV
Cada push na `main` gera o `ApFoodPDV.exe` e, se a versão em `desktop/apfood_pdv/__init__.py` for nova, cria a release `pdv-vX.Y.Z` com o SHA-256 nas notas. Copie os três valores das notas para o `.env` do servidor:

```
APFOOD_PDV_VERSAO=0.2.0
APFOOD_PDV_URL=https://github.com/julicorlando/apfood/releases/download/pdv-v0.2.0/ApFoodPDV.exe
APFOOD_PDV_SHA256=...
APFOOD_PDV_OBRIGATORIA_ATE=   # opcional: versões abaixo desta são forçadas a atualizar
```

Ao abrir, o PDV compara a versão, baixa, **confere o SHA-256** e troca o executável ao fechar, guardando o anterior como `ApFoodPDV.exe.old`. Se o repositório for **privado**, o link da release não abre sem login: hospede o `.exe` em um endereço público (seu servidor, S3) e aponte `APFOOD_PDV_URL` para ele.
