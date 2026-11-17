"""Painel: combos, lista de compras pelo estoque mínimo, importar cardápio por foto/PDF/texto,
resumo do dia e tempo por etapa dos pedidos."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, time, timedelta
from decimal import ROUND_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cardapio.models import Categoria, ComboItem, Produto
from apps.core.api import EhGerente, loja_da_requisicao
from apps.core.excecoes import ErroNegocio


def _int(v, campo: str, minimo: int = 0) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ErroNegocio("valor inválido", campo) from None
    if n < minimo:
        raise ErroNegocio("valor inválido", campo)
    return n


# ============================================================================= combos
def _combo_out(p: Produto, request=None) -> dict:
    itens = list(p.componentes.select_related("produto"))
    de = sum(ci.produto.preco_centavos * ci.quantidade for ci in itens)
    return {"id": str(p.id), "nome": p.nome, "descricao": p.descricao, "preco_centavos": p.preco_centavos,
            "categoria_id": str(p.categoria_id) if p.categoria_id else None,
            "categoria": p.categoria.nome if p.categoria_id else "", "ativo": p.ativo, "pausado": p.pausado,
            "imagem": request.build_absolute_uri(p.imagem.url) if request and p.imagem else None,
            "itens": [{"produto_id": str(ci.produto_id), "nome": ci.produto.nome, "quantidade": ci.quantidade,
                       "preco_centavos": ci.produto.preco_centavos} for ci in itens],
            "de_centavos": de, "economia_centavos": max(0, de - p.preco_centavos)}


def _salvar_combo(loja, dados, combo: Produto | None = None) -> Produto:
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        raise ErroNegocio("dê um nome ao combo", "nome")
    preco = _int(dados.get("preco_centavos"), "preco_centavos", 1)
    itens = dados.get("itens") or []
    if not isinstance(itens, list) or len(itens) < 2:
        raise ErroNegocio("escolha pelo menos 2 itens para o combo", "itens")
    ids = [str(i.get("produto_id")) for i in itens]
    produtos = {str(p.id): p for p in Produto.objects.ativos().filter(loja=loja, pk__in=ids, tipo="VENDA")}
    if len(produtos) != len(set(ids)):
        raise ErroNegocio("algum item do combo não foi encontrado", "itens")
    cat_id = dados.get("categoria_id")
    categoria = Categoria.objects.ativos().filter(loja=loja, pk=cat_id).first() if cat_id else None
    if categoria is None:
        categoria = (Categoria.objects.ativos().filter(loja=loja, nome__iexact="Combos").first()
                     or Categoria.objects.create(loja=loja, nome="Combos", ordem=0))
    if combo is not None and str(combo.id) in produtos:
        raise ErroNegocio("o combo não pode conter ele mesmo", "itens")
    with transaction.atomic():
        if combo is None:
            combo = Produto(loja=loja, tipo="VENDA")
        combo.nome, combo.descricao = nome[:120], str(dados.get("descricao") or "").strip()
        combo.preco_centavos, combo.categoria = preco, categoria
        if "ativo" in dados:
            combo.ativo = bool(dados.get("ativo"))
        combo.save()
        combo.componentes.all().delete()
        vistos = set()
        for ordem, i in enumerate(itens):
            pid = str(i.get("produto_id"))
            if pid in vistos:
                continue
            vistos.add(pid)
            ComboItem.objects.create(combo=combo, produto=produtos[pid], quantidade=_int(i.get("quantidade") or 1, "quantidade", 1),
                                     ordem=ordem)
    return combo


class CombosView(APIView):
    """GET: combos da loja. POST {nome, descricao, preco_centavos, categoria_id?, itens:[{produto_id, quantidade}]}."""

    permission_classes = [EhGerente]

    def get(self, request):
        loja = loja_da_requisicao(request)
        combos = (Produto.objects.ativos().filter(loja=loja, componentes__isnull=False).distinct()
                  .select_related("categoria").order_by("nome"))
        return Response([_combo_out(p, request) for p in combos])

    def post(self, request):
        return Response(_combo_out(_salvar_combo(loja_da_requisicao(request), request.data), request), status=201)


class ComboView(APIView):
    permission_classes = [EhGerente]

    def _combo(self, request, pk):
        p = Produto.objects.ativos().filter(loja=loja_da_requisicao(request), pk=pk).first()
        if p is None:
            raise ErroNegocio("combo não encontrado")
        return p

    def put(self, request, pk):
        p = self._combo(request, pk)
        return Response(_combo_out(_salvar_combo(p.loja, request.data, p), request))

    def delete(self, request, pk):
        """Tira do cardápio (o histórico de vendas continua)."""
        p = self._combo(request, pk)
        p.excluir()
        return Response(status=204)


# ============================================================================= lista de compras
def _ultimo_fornecedor(produto_id):
    from apps.compras.models import ItemCompra

    ic = (ItemCompra.objects.filter(produto_id=produto_id, compra__fornecedor__isnull=False)
          .exclude(compra__status="CANCELADA").select_related("compra__fornecedor").order_by("-compra__data_entrada").first())
    return (ic.compra.fornecedor, ic.custo_unitario_centavos, ic.fator_conversao) if ic else (None, None, Decimal("1"))


def lista_compras(loja) -> dict:
    """O que está no estoque mínimo ou abaixo (e o que está quase lá), com a quantidade sugerida para
    voltar ao dobro do mínimo, agrupado pelo último fornecedor de cada item."""
    grupos: dict = {}
    for p in (Produto.objects.ativos().filter(loja=loja, controla_estoque=True, estoque_minimo__isnull=False,
                                              estoque_minimo__gt=0).order_by("nome")):
        quase = p.estoque_minimo * Decimal("1.2")
        if p.estoque_atual > quase:
            continue
        sugerido = (p.estoque_minimo * 2 - p.estoque_atual).quantize(Decimal("1"), rounding=ROUND_UP)
        forn, custo, fator = _ultimo_fornecedor(p.id)
        chave = str(forn.id) if forn else ""
        g = grupos.setdefault(chave, {"fornecedor_id": chave or None, "fornecedor": forn.nome if forn else "Sem fornecedor",
                                      "telefone": getattr(forn, "telefone", "") if forn else "", "itens": [],
                                      "total_estimado_centavos": 0})
        unit = custo if custo is not None else (p.custo_centavos or 0)
        g["itens"].append({"produto_id": str(p.id), "nome": p.nome, "unidade": p.unidade,
                           "estoque_atual": str(p.estoque_atual.normalize()), "estoque_minimo": str(p.estoque_minimo.normalize()),
                           "situacao": "acabou" if p.estoque_atual <= 0 else "abaixo" if p.estoque_atual <= p.estoque_minimo else "quase",
                           "sugerido": str(max(sugerido, Decimal("1"))), "custo_unitario_centavos": unit,
                           "fator_conversao": str(fator.normalize())})
        g["total_estimado_centavos"] += int(unit * max(sugerido, Decimal("1")) / (fator or 1))
    lista = sorted(grupos.values(), key=lambda g: (g["fornecedor_id"] is None, g["fornecedor"]))
    return {"grupos": lista, "itens": sum(len(g["itens"]) for g in lista)}


class ListaComprasView(APIView):
    """GET: lista sugerida. POST {fornecedor_id?, itens:[{produto_id, quantidade}]}: cria a compra em rascunho."""

    permission_classes = [EhGerente]

    def get(self, request):
        return Response(lista_compras(loja_da_requisicao(request)))

    def post(self, request):
        from apps.compras.models import Compra, Fornecedor, ItemCompra

        loja = loja_da_requisicao(request)
        forn = None
        if fid := request.data.get("fornecedor_id"):
            forn = Fornecedor.objects.ativos().filter(loja=loja, pk=fid).first()
        itens = request.data.get("itens") or []
        if not itens:
            raise ErroNegocio("escolha os itens da compra", "itens")
        with transaction.atomic():
            c = Compra.objects.create(loja=loja, fornecedor=forn, data_entrada=timezone.localdate(),
                                      observacao="Gerada pela lista de compras (estoque mínimo)")
            total = 0
            for i in itens:
                p = Produto.objects.ativos().filter(loja=loja, pk=i.get("produto_id")).first()
                if p is None:
                    continue
                try:
                    qtd = Decimal(str(i.get("quantidade")).replace(",", "."))
                except Exception:  # noqa: BLE001
                    qtd = Decimal("0")
                if qtd <= 0:
                    continue
                _, custo, fator = _ultimo_fornecedor(p.id)
                unit = int(custo if custo is not None else (p.custo_centavos or 0))
                sub = int((Decimal(unit) * qtd).quantize(Decimal("1")))
                ItemCompra.objects.create(compra=c, produto=p, quantidade=qtd, fator_conversao=fator or Decimal("1"),
                                          custo_unitario_centavos=unit, total_centavos=sub)
                total += sub
            if not c.itens.exists():
                raise ErroNegocio("nenhum item válido", "itens")
            c.total_centavos = total
            c.save(update_fields=["total_centavos", "atualizado_em"])
        return Response({"id": str(c.id), "total_centavos": total}, status=201)


# ============================================================================= importar cardápio
PRECO = re.compile(r"(?:R\$\s*)?(\d{1,4}(?:\.\d{3})*,\d{2}|\d{1,4}\.\d{2})(?!\d)")
INSTRUCAO_IA = (
    "Você recebe a foto ou o PDF do cardápio de um restaurante brasileiro. Extraia as categorias e os produtos "
    "com o preço em reais. Responda SÓ com JSON, sem texto antes ou depois, no formato: "
    '{"categorias":[{"nome":"Lanches","produtos":[{"nome":"X-Burger","descricao":"pão, carne e queijo",'
    '"preco":"24,90"}]}]}. Use o nome como está no cardápio; descrição vazia se não houver; se um item tiver '
    "vários tamanhos, crie um produto por tamanho (ex.: \"Pizza Calabresa (G)\"). Ignore telefones, endereços e horários."
)


def _centavos(txt) -> int:
    t = str(txt or "").strip().replace("R$", "").strip()
    if not t:
        return 0
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return max(0, int((Decimal(t) * 100).quantize(Decimal("1"))))
    except Exception:  # noqa: BLE001
        return 0


def _normalizar(dados) -> list[dict]:
    out = []
    for c in (dados or {}).get("categorias") or []:
        produtos = []
        for p in c.get("produtos") or []:
            nome = str(p.get("nome") or "").strip()[:120]
            if not nome:
                continue
            preco = p.get("preco_centavos")
            preco = int(preco) if isinstance(preco, int) else _centavos(p.get("preco"))
            produtos.append({"nome": nome, "descricao": str(p.get("descricao") or "").strip()[:500], "preco_centavos": preco})
        if produtos:
            out.append({"nome": (str(c.get("nome") or "").strip() or "Cardápio")[:80], "produtos": produtos})
    return out


def ler_texto(texto: str) -> list[dict]:
    """Sem IA: cada linha com preço vira produto; linha curta sem preço vira categoria;
    linha longa logo depois de um produto vira a descrição dele."""
    categorias: list[dict] = []
    atual = None
    ultimo = None
    for bruta in (texto or "").splitlines():
        linha = re.sub(r"\s+", " ", bruta).strip(" .-–—•*\t")
        if not linha:
            continue
        m = list(PRECO.finditer(linha))
        if m:
            nome = linha[:m[0].start()].strip(" .-–—:|R$")
            if not nome:
                continue
            if atual is None:
                atual = {"nome": "Cardápio", "produtos": []}
                categorias.append(atual)
            ultimo = {"nome": nome[:120], "descricao": "", "preco_centavos": _centavos(m[0].group(1))}
            atual["produtos"].append(ultimo)
        elif ultimo is not None and (len(linha) > 28 or linha[:1].islower() or "," in linha):
            ultimo["descricao"] = (ultimo["descricao"] + " " + linha).strip()[:500]
        elif len(linha) <= 40:
            atual = {"nome": linha.title() if linha.isupper() else linha, "produtos": []}
            categorias.append(atual)
            ultimo = None
    return [c for c in categorias if c["produtos"]]


def _texto_pdf(conteudo: bytes) -> str:
    import io

    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        return "\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(conteudo)).pages[:20])
    except Exception:  # noqa: BLE001
        return ""


def ler_com_ia(conteudo: bytes, tipo: str) -> list[dict]:
    import httpx

    chave = settings.APFOOD.get("IA_CHAVE")
    if not chave:
        raise ErroNegocio("a leitura por foto ainda não está ligada: cole o texto do cardápio ou envie um PDF com texto")
    dados = base64.b64encode(conteudo).decode()
    bloco = ({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": dados}}
             if tipo == "application/pdf" else
             {"type": "image", "source": {"type": "base64", "media_type": tipo, "data": dados}})
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
            "x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": settings.APFOOD.get("IA_MODELO") or "claude-sonnet-5-5", "max_tokens": 8000,
                  "messages": [{"role": "user", "content": [bloco, {"type": "text", "text": INSTRUCAO_IA}]}]})
    except httpx.HTTPError as exc:
        raise ErroNegocio("não consegui falar com a IA agora: tente de novo") from exc
    if r.status_code != 200:
        raise ErroNegocio(f"a IA não conseguiu ler o arquivo (erro {r.status_code})")
    texto = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    ini, fim = texto.find("{"), texto.rfind("}")
    try:
        return _normalizar(json.loads(texto[ini:fim + 1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ErroNegocio("a IA não devolveu um cardápio legível: tente uma foto mais nítida") from exc


class ImportarCardapioView(APIView):
    """POST multipart {arquivo: foto (jpg/png/webp) ou PDF} ou JSON {texto}: devolve a prévia
    {categorias:[{nome, produtos:[{nome, descricao, preco_centavos}]}]} para conferir antes de salvar."""

    permission_classes = [EhGerente]
    TIPOS = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}

    def get(self, request):
        return Response({"ia": bool(settings.APFOOD.get("IA_CHAVE"))})

    def post(self, request):
        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            cats = ler_texto(str(request.data.get("texto") or ""))
            if not cats:
                raise ErroNegocio("não encontrei produtos com preço no texto (ex.: \"X-Burger 24,90\")", "texto")
            return Response({"categorias": cats, "origem": "texto"})
        if arquivo.size > 15 * 1024 * 1024:
            raise ErroNegocio("arquivo muito grande (máximo 15 MB)", "arquivo")
        tipo = (arquivo.content_type or "").lower()
        if tipo == "image/jpg":
            tipo = "image/jpeg"
        if tipo not in self.TIPOS:
            raise ErroNegocio("envie uma foto (JPG/PNG) ou um PDF", "arquivo")
        conteudo = arquivo.read()
        if tipo == "application/pdf" and not settings.APFOOD.get("IA_CHAVE"):
            cats = ler_texto(_texto_pdf(conteudo))
            if not cats:
                raise ErroNegocio("este PDF não tem texto legível (é uma imagem): cole o texto do cardápio")
            return Response({"categorias": cats, "origem": "pdf"})
        return Response({"categorias": ler_com_ia(conteudo, tipo), "origem": "ia"})


class ImportarConfirmarView(APIView):
    """POST {categorias:[...]} (a prévia conferida): cria categorias e produtos. Produto com o mesmo
    nome na mesma categoria não é duplicado."""

    permission_classes = [EhGerente]

    def post(self, request):
        loja = loja_da_requisicao(request)
        cats = _normalizar({"categorias": request.data.get("categorias") or []})
        if not cats:
            raise ErroNegocio("nada para importar")
        criadas = produtos = 0
        with transaction.atomic():
            base = Categoria.objects.ativos().filter(loja=loja).count()
            for i, c in enumerate(cats):
                cat = Categoria.objects.ativos().filter(loja=loja, nome__iexact=c["nome"]).first()
                if cat is None:
                    cat = Categoria.objects.create(loja=loja, nome=c["nome"], ordem=base + i)
                    criadas += 1
                for j, p in enumerate(c["produtos"]):
                    if Produto.objects.ativos().filter(loja=loja, categoria=cat, nome__iexact=p["nome"]).exists():
                        continue
                    Produto.objects.create(loja=loja, categoria=cat, tipo="VENDA", nome=p["nome"], descricao=p["descricao"],
                                           preco_centavos=p["preco_centavos"], ordem=j)
                    produtos += 1
        return Response({"categorias": criadas, "produtos": produtos}, status=201)


# ============================================================================= resumo do dia
class ResumoDiarioView(APIView):
    """GET: prévia do resumo de hoje. POST: envia agora (teste)."""

    permission_classes = [EhGerente]

    def get(self, request):
        from apps.lojas import resumo_diario

        loja = loja_da_requisicao(request)
        r = resumo_diario.calcular(loja)
        return Response({"resumo": r, "texto": resumo_diario.texto(loja, r), "numeros": resumo_diario.numeros(loja)})

    def post(self, request):
        from apps.lojas import resumo_diario

        loja = loja_da_requisicao(request)
        return Response(resumo_diario.enviar(loja, chave_extra=f"-teste-{timezone.now():%H%M%S}"))


# ============================================================================= tempo por etapa
ETAPAS = [("aceite", "Aceitar o pedido"), ("preparo", "Preparo"), ("espera_entregador", "Esperando o entregador"),
          ("entrega", "Entrega (trajeto)"), ("retirada", "Cliente retirar")]


def _min(a, b):
    if a is None or b is None or b < a:
        return None
    return (b - a).total_seconds() / 60


def tempos(loja, inicio, fim) -> dict:
    from apps.pedidos.models import Pedido

    ini = timezone.make_aware(datetime.combine(inicio, time.min))
    ate = timezone.make_aware(datetime.combine(fim, time.min)) + timedelta(days=1)
    ps = list(Pedido.objects.filter(loja=loja, status="CONCLUIDO", criado_em__gte=ini, criado_em__lt=ate,
                                    agendado_para__isnull=True)
              .only("id", "numero", "tipo_atendimento", "criado_em", "aceito_em", "em_preparo_em", "pronto_em",
                    "saiu_entrega_em", "concluido_em").order_by("criado_em")[:5000])
    valores: dict[str, list[float]] = {k: [] for k, _ in ETAPAS}
    totais, por_hora, lentos = [], {}, []
    for p in ps:
        e = {"aceite": _min(p.criado_em, p.aceito_em), "preparo": _min(p.aceito_em or p.criado_em, p.pronto_em)}
        if p.tipo_atendimento == "ENTREGA":
            e["espera_entregador"] = _min(p.pronto_em, p.saiu_entrega_em)
            e["entrega"] = _min(p.saiu_entrega_em, p.concluido_em)
        elif p.tipo_atendimento == "RETIRADA":
            e["retirada"] = _min(p.pronto_em, p.concluido_em)
        for k, v in e.items():
            if v is not None and v < 600:
                valores[k].append(v)
        total = _min(p.criado_em, p.concluido_em)
        if total is not None and total < 600:
            totais.append(total)
            h = timezone.localtime(p.criado_em).hour
            por_hora.setdefault(h, []).append(total)
            lentos.append({"numero": p.numero, "id": str(p.id), "tipo": p.tipo_atendimento, "total_min": round(total),
                           "etapas": {k: round(v) for k, v in e.items() if v is not None},
                           "criado_em": p.criado_em})

    def resumo(vs):
        if not vs:
            return None
        s = sorted(vs)
        return {"media_min": round(sum(s) / len(s), 1), "p90_min": round(s[min(len(s) - 1, int(len(s) * 0.9))], 1),
                "pedidos": len(s)}

    etapas = [{"etapa": k, "rotulo": r, **(resumo(valores[k]) or {"media_min": None, "p90_min": None, "pedidos": 0})}
              for k, r in ETAPAS]
    com_media = [x for x in etapas if x["media_min"] is not None and x["etapa"] in ("aceite", "preparo", "espera_entregador", "entrega")]
    gargalo = max(com_media, key=lambda x: x["media_min"])["etapa"] if com_media else None
    return {"pedidos": len(totais), "total": resumo(totais), "etapas": etapas, "gargalo": gargalo,
            "meta_preparo_min": loja.tempo_preparo_min,
            "por_hora": [{"hora": h, "media_min": round(sum(v) / len(v), 1), "pedidos": len(v)} for h, v in sorted(por_hora.items())],
            "mais_lentos": sorted(lentos, key=lambda x: -x["total_min"])[:10]}


class TemposView(APIView):
    permission_classes = [EhGerente]

    def get(self, request):
        from .relatorios import periodo

        inicio, fim = periodo(request)
        return Response(tempos(loja_da_requisicao(request), inicio, fim))
