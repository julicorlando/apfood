# ApFood

Sistema de gestão e PDV para restaurantes e hamburguerias, com cardápio digital e sincronização em tempo real. Feito em **Python**.

| Pasta | O que é | Stack |
|---|---|---|
| `backend/` | API REST, WebSocket, cardápio digital público e admin | Django 5.2 + DRF + Channels + PostgreSQL + Redis |
| `desktop/` | PDV Windows: pedidos online, balcão, delivery, caixa, estoque, relatórios | PySide6 + SQLite local |
| `core/` | Regras compartilhadas: caixa, totais, status do pedido, dinheiro, enums | Python puro |

📐 [Arquitetura](docs/ARQUITETURA.md) · 🗄️ [Banco de dados](docs/BANCO_DE_DADOS.md) · 🗺️ [Roadmap](docs/ROADMAP.md)

## Rodando localmente

Requisitos: Python 3.12+ e Docker.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
cp .env.example .env               # ajuste DJANGO_SECRET_KEY

docker compose up -d               # PostgreSQL + Redis

cd backend
pip install -r requirements/dev.txt
python manage.py makemigrations    # primeira vez: gera as migrations iniciais
python manage.py migrate
python manage.py seed_demo         # loja "burger-demo" + admin/gerente/caixa1 (senha apfood123, PIN 1234)
python manage.py runserver         # http://localhost:8000/admin  e  http://localhost:8000/burger-demo/
```

PDV desktop (outro terminal, mesmo venv):

```bash
cd desktop
pip install -r requirements.txt
python -m apfood_pdv
```

Testes (na raiz do repositório):

```bash
pip install pytest
pytest core/tests desktop/tests
```

## Status

- [x] **Passo 1** — arquitetura, modelagem do banco, estrutura do projeto
- [ ] **Passo 2** — API e sincronização em tempo real
- [ ] **Passo 3** — App PC (PDV)
- [ ] **Passo 4** — Cardápio digital
