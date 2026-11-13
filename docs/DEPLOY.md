# Publicar no Coolify com domínio no Cloudflare

Resultado: **https://apfood.axionwebdigital.com.br**, com o painel em `/painel/`, o cardápio em `/<slug-da-loja>/` e a API em `/api/`. O PDV usa esse endereço como servidor.

## 1. Cloudflare (Tunnel)
O servidor publica os apps pelo **Cloudflare Tunnel `fluxomonitor`**, não por IP público. Em **Zero Trust → Networks → Tunnels → fluxomonitor → Routes → Add route → Published application**:

| Campo | Valor |
|---|---|
| Subdomain / Domain | `apfood` / `axionwebdigital.com.br` |
| Service URL | `https://localhost:443` (o proxy Traefik do Coolify) |
| HTTP → HTTP Host Header | `apfood.axionwebdigital.com.br` |
| TLS → Origin Server Name | `apfood.axionwebdigital.com.br` |
| TLS → Disable TLS certificate verification | ligado |

O Cloudflare cria sozinho o CNAME `apfood` → `<id-do-túnel>.cfargotunnel.com`. São os mesmos ajustes da rota do `appdv`. O WebSocket passa pelo túnel sem configuração extra.

## 2. Coolify
1. **Projects → ApFood → production → Add Resource → Public Git Repository**: `https://github.com/julicorlando/apfood`.
2. **Branch:** `main`.
3. **Build Pack:** **Docker Compose**. **Compose file:** `/docker-compose.prod.yml`.
4. Em **Domains → Add Domain**: serviço **web**, protocolo `https`, domínio `apfood.axionwebdigital.com.br`, porta `8000` (porta interna; o site abre na 443). Apague a variante `www.` que o Coolify sugere, porque o túnel só tem a rota sem `www`.
5. Em **Environment Variables**:
   - Gerados sozinhos pelo Coolify: `SERVICE_PASSWORD_POSTGRES`, `SERVICE_BASE64_64_DJANGO` (secret do Django) e `SERVICE_PASSWORD_MASTER` (senha do usuário `master`). Anote a senha do master.
   - `APFOOD_CHAVE_CRIPTO`: gere com `docker compose exec web python manage.py gerar_chave_cripto` (ou em qualquer máquina com o projeto) e cole aqui **antes** de cadastrar integrações. Não troque depois: as credenciais salvas deixam de abrir.
   - Opcionais: `APFOOD_MP_TOKEN_PLATAFORMA`, `APFOOD_IFOOD_CLIENT_ID/SECRET`, `APFOOD_PDV_*` (atualização do PDV, ver INTEGRACOES.md).
6. **Deploy.** O container `web` roda as migrations e cria o usuário **master** sozinho. Os containers `tarefas`, `ifood` e `cobranca` são os workers (fila, polling do iFood e cobrança diária).

## 3. Primeiro acesso
- `https://apfood.axionwebdigital.com.br/painel/`: entre com `master` e a senha gerada. Em **Plataforma → Empresas → Nova empresa**, cadastre o cliente com a primeira loja e o administrador dele.
- Para ver um exemplo funcionando: **Terminal** do container web no Coolify → `python manage.py seed_demo` → `https://apfood.axionwebdigital.com.br/burger-demo/`.
- No PDV: em **Servidor**, informe `https://apfood.axionwebdigital.com.br`.
- Webhook do Mercado Pago: `https://apfood.axionwebdigital.com.br/api/webhooks/mercadopago/<id-da-loja>/`.

## 4. Backup
O banco fica no volume `pgdata`. Ative **Backups** no recurso no Coolify, ou agende um `pg_dump` diário, e guarde também o volume `media` (fotos dos produtos).
