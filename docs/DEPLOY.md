# Publicar no Coolify com domínio no Cloudflare

Resultado: **https://apfood.axionwebdigital.com.br**, com o cardápio em `/<slug-da-loja>/`, o admin em `/admin/` e a API em `/api/`. O PDV usa esse endereço como servidor.

## 1. Cloudflare (DNS)
Em **axionwebdigital.com.br → DNS → Records → Add record**:

| Tipo | Nome | Conteúdo | Proxy |
|---|---|---|---|
| A | `apfood` | IP público do servidor do Coolify | **Proxied** (nuvem laranja) |

Depois, em **SSL/TLS → Overview**, use o modo **Full (strict)**. O Coolify (Traefik) emite o certificado Let's Encrypt, e o Cloudflare repassa o WebSocket sem configuração extra.

> Se o certificado não sair na primeira vez, deixe o registro como **DNS only** (nuvem cinza), faça o deploy, espere o certificado e volte para **Proxied**.

## 2. Coolify
1. **Projects → (seu projeto) → + New → Private Repository (GitHub App)** ou **Public Repository**: `julicorlando/apfood`.
2. **Branch:** `main` (depois de mesclar o PR) ou `passo-1-django`.
3. **Build Pack:** **Docker Compose**. **Docker Compose Location:** `/docker-compose.prod.yml`.
4. Em **Domains** do serviço **web**: `https://apfood.axionwebdigital.com.br:8000`. O `:8000` diz ao Coolify a porta interna; o site abre normalmente na 443.
5. Em **Environment Variables**:
   - Gerados sozinhos pelo Coolify: `SERVICE_PASSWORD_POSTGRES`, `SERVICE_BASE64_64_DJANGO` (secret do Django) e `SERVICE_PASSWORD_MASTER` (senha do usuário `master`). Anote a senha do master.
   - `APFOOD_CHAVE_CRIPTO`: gere com `docker compose exec web python manage.py gerar_chave_cripto` (ou em qualquer máquina com o projeto) e cole aqui **antes** de cadastrar integrações. Não troque depois: as credenciais salvas deixam de abrir.
   - Opcionais: `APFOOD_MP_TOKEN_PLATAFORMA`, `APFOOD_IFOOD_CLIENT_ID/SECRET`, `APFOOD_PDV_*` (atualização do PDV, ver INTEGRACOES.md).
6. **Deploy.** O container `web` roda as migrations e cria o usuário **master** sozinho. Os containers `tarefas`, `ifood` e `cobranca` são os workers (fila, polling do iFood e cobrança diária).

## 3. Primeiro acesso
- `https://apfood.axionwebdigital.com.br/admin/`: entre com `master` e a senha gerada.
- Para ver um exemplo funcionando: **Terminal** do container web no Coolify → `python manage.py seed_demo` → `https://apfood.axionwebdigital.com.br/burger-demo/`.
- No PDV: em **Servidor**, informe `https://apfood.axionwebdigital.com.br`.
- Webhook do Mercado Pago: `https://apfood.axionwebdigital.com.br/api/webhooks/mercadopago/<id-da-loja>/`.

## 4. Backup
O banco fica no volume `pgdata`. Ative **Backups** no recurso no Coolify, ou agende um `pg_dump` diário, e guarde também o volume `media` (fotos dos produtos).
