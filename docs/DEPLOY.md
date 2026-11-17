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
O serviço **backup** do compose faz uma cópia do banco (`pg_dump`) e das fotos (volume `media`) ao subir e todo dia às 04h, no volume `backups`, e apaga as cópias com mais de 14 dias. Variáveis opcionais: `BACKUP_HORA` (padrão `04`) e `BACKUP_DIAS` (padrão `14`).

- **Ver as cópias:** Coolify → ApFood → **Terminal** → container `backup` → `ls -lh /backups`.
- **Restaurar** (no terminal do container `backup`):
  ```sh
  pg_restore --clean --if-exists --no-owner -d apfood /backups/apfood-AAAAMMDD-HHMM.dump
  ```
  Depois, faça **Restart** do recurso.
- **Fotos:** `tar -xzf /backups/media-AAAAMMDD-HHMM.tar.gz -C /media` (no mesmo terminal).
- O volume `backups` fica no mesmo servidor. Para ter uma cópia fora dele, ative também os **Backups S3** do Coolify ou copie `/backups` para outro lugar.

## 5. E-mail (senha, cobrança e alertas)
Defina `EMAIL_URL` no Coolify, por exemplo `smtp+tls://usuario:senha@smtp.gmail.com:587` (no Gmail, use uma *senha de app*), e `DEFAULT_FROM_EMAIL` (ex.: `ApFood <nao-responda@seudominio.com.br>`). Sem `EMAIL_URL`, os e-mails só aparecem no log do container e o administrador redefine a senha pelo painel (Configurações → Usuários).

O mesmo e-mail é usado nos avisos de cobrança da assinatura e nos alertas de erro.

## 6. Monitoramento de erros
- **Por e-mail:** `DJANGO_ADMINS="Seu Nome <voce@exemplo.com>, outro@exemplo.com"`. Cada erro 500 chega por e-mail com o detalhe (precisa do `EMAIL_URL`).
- **Sentry (recomendado):** crie um projeto Django em sentry.io (o plano gratuito atende) e defina `SENTRY_DSN`. Os erros chegam agrupados, com o contexto, e sem dados de clientes (`send_default_pii=False`). Opcional: `SENTRY_AMBIENTE` (padrão `producao`) e `SENTRY_TRACES` (ex.: `0.1` para medir desempenho).
- Os logs continuam no Coolify (aba Logs de cada serviço).

## 7. Termos de uso e privacidade
Defina no Coolify:

| Variável | Exemplo |
|---|---|
| `APFOOD_LEGAL_RAZAO_SOCIAL` | `Axion Web Digital LTDA` |
| `APFOOD_LEGAL_CNPJ` | `00.000.000/0001-00` |
| `APFOOD_LEGAL_EMAIL` | `privacidade@seudominio.com.br` (encarregado/LGPD) |
| `APFOOD_LEGAL_CIDADE_FORO` | `Recife/PE` |

Enquanto faltar alguma, `/termos/` e `/privacidade/` mostram o aviso "Rascunho". O texto é um modelo: **revise com um advogado** antes de vender.

## 8. WhatsApp (servidor próprio)
O `docker-compose.prod.yml` sobe o serviço **whatsapp** (Evolution API, código aberto), só na rede interna. Ele guarda as sessões no volume `whatsapp` e os dados no mesmo Postgres, no schema `evolution_api`. A chave entre o web e esse serviço é a `SERVICE_PASSWORD_EVOLUTION`, que o Coolify gera sozinho na próxima implantação. Cada loja conecta o próprio número em Configurações → WhatsApp, lendo o QR Code; não há nada para configurar por loja.
