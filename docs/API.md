# API do ApFood

Base: `/api/`. Autenticação JWT: `POST /api/auth/token/ {username, password}` → `access` (header `Authorization: Bearer <access>`), renovar em `/api/auth/token/refresh/`.

**Loja ativa:** `?loja=<uuid>` ou header `X-Loja`. É opcional se o usuário só acessa uma loja. Loja de outra empresa → 403.
**Valores** em centavos. **Datas** ISO 8601. **Erros de regra de negócio** → 400 `{"detail": "..."}` ou `{"campo": ["..."]}`.
**Idempotência:** operações aceitam `id` (UUID gerado no cliente); reenviar não duplica.

## Sessão
| Método | Rota | |
|---|---|---|
| GET | `eu/` | usuário, papel, empresa, lojas permitidas, turno aberto |
| POST | `auth/pin/` | `{username, pin}` troca rápida de operador (mesma empresa) |

## Cadastros (todos leem; gerente+ altera; DELETE = soft delete)
`setores/`, `categorias/`, `produtos/`, `variacoes/`, `grupos-adicionais/`, `adicionais/`, `clientes/`, `enderecos/`, `zonas-entrega/`, `entregadores/`, `mesas/`, `fornecedores/`, `cupons/`, `categorias-despesa/`, `taxas-pagamento/`, `despesas/` (gerente+, `?em_aberto=1` = contas a pagar)

Extras: `produtos/{id}/grupos/` (PUT `{grupos: [ids]}`), `produtos/{id}/ficha/` (PUT `[{insumo, quantidade}]`), `clientes/por-telefone/?telefone=` (autopreenche o delivery), `POST taxa-entrega/ {bairro, latitude, longitude}`.

## Pedidos
| Método | Rota | |
|---|---|---|
| GET | `pedidos/?abertos=1&status=PENDENTE&canal=ONLINE&data=AAAA-MM-DD` | fila do PDV |
| POST | `pedidos/` | balcão, delivery, mesa, marketplace (ver exemplo) |
| POST | `pedidos/{id}/status/` | `{status, motivo?, entregador_id?}` |
| POST | `pedidos/{id}/pagamentos/` | `{forma, valor_centavos, valor_recebido_centavos?, bandeira?}` |
| GET | `cozinha/?setor=` | itens a preparar (KDS) |
| POST | `cozinha/{item}/avancar/` | AGUARDANDO → EM_PREPARO → PRONTO (pedido fica PRONTO quando todos ficam) |

```json
{
  "id": "uuid-opcional", "canal": "DELIVERY", "tipo_atendimento": "ENTREGA", "origem_contato": "WHATSAPP",
  "nome_cliente": "Ana", "telefone_cliente": "11987654321",
  "endereco": {"logradouro": "Rua A", "numero": "10", "bairro": "Centro"},
  "itens": [
    {"produto_id": "…", "quantidade": 2, "adicionais": [{"adicional_id": "…", "quantidade": 1}], "observacao": "sem cebola"},
    {"produto_id": "calabresa", "variacao_id": "grande", "sabores": ["calabresa", "portuguesa"]}
  ],
  "cupom_codigo": "BEMVINDO10", "troco_para_centavos": 10000, "entregador_id": "…"
}
```
Os preços vêm sempre do banco. A taxa de entrega é calculada por bairro ou raio, mas o atendente pode informá-la (`taxa_entrega_centavos`).

## Caixa
| Método | Rota | |
|---|---|---|
| POST | `turnos/abrir/` | `{valor_abertura_centavos}` |
| GET | `turnos/atual/` | turno + resumo (operador não vê o esperado: conferência cega) |
| POST | `turnos/{id}/movimentos/` | `{tipo: SANGRIA\|SUPRIMENTO, valor_centavos, motivo}` |
| POST | `turnos/{id}/despesas/` | despesa paga com dinheiro da gaveta |
| POST | `turnos/{id}/fechar/` | `{informado: {"DINHEIRO": 15000, "PIX": 3000}, tipo_conferencia}` → quebra/sobra por forma |

## Salão
`comandas/` (POST abre; `?abertas=1`), `comandas/{id}/pedidos/`, `pedir-conta/`, `reabrir/`, `ajustar/` (taxa de serviço, desconto, couvert), `divisao/?pessoas=3`, `pagamentos/`, `fechar/`, `transferir/ {mesa}`, `juntar/ {origem}`. Para lançar uma rodada, use `POST pedidos/` com `canal: MESA` e `comanda: <id>`.

## Estoque e compras (gerente+)
`estoque/` (kardex, `?produto=`), `estoque/abaixo-do-minimo/`, `POST estoque/operacao/ {produto, operacao: ENTRADA|PERDA|INVENTARIO, quantidade, custo_unitario_centavos?, motivo}`, `compras/` (CRUD em rascunho com `itens`), `compras/{id}/lancar/` (estoque + custo médio + conta a pagar), `compras/{id}/cancelar/`.

## Relatórios (gerente+) — `?periodo=dia|semana|mes` ou `?inicio=&fim=`
`relatorios/vendas/` (faturamento, ticket médio, por dia/canal/forma com taxas), `relatorios/curva-abc/`, `relatorios/fechamentos/?usuario=`, `relatorios/fluxo-caixa/` (entradas líquidas × saídas, a receber, a pagar), `plataforma/resumo/` (só MASTER: todas as empresas).

## Sincronização do PDV
- `GET sync/pull/?entidades=produtos,clientes&desde=<iso>` → `{entidades: {produtos: {registros, cursor, mais}}}` (inclui excluídos)
- `POST sync/push/ {operacoes: [{id, operacao, payload}]}` → resultado por operação. Operações: `caixa.abrir`, `caixa.movimento`, `caixa.despesa`, `caixa.fechar`, `pedido.criar`, `pedido.status`, `pedido.pagamento`, `comanda.abrir`, `comanda.pagamento`, `comanda.fechar`.

## Público (sem login, com limite de requisições)
`GET publico/lojas/{slug}/` (cardápio), `POST publico/lojas/{slug}/taxa-entrega/`, `POST publico/lojas/{slug}/pedidos/`, `GET publico/pedidos/{token}/` (acompanhamento).

## Tempo real (WebSocket)
- `ws/pdv/{loja_id}/` (autenticado): `pedido.novo`, `pedido.status`, `estoque.alerta`, `catalogo.alterado`
- `ws/pedido/{token}/` (cliente): `pedido.status`
