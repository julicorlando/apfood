// Cadastros da loja (cardápio, clientes, entrega, financeiro).
import { del, ehGerente, get, lista, patch, post, put } from "../api.js";
import { paginaCadastro } from "../crud.js";
import { formulario } from "../form.js";
import {
  aviso, botaoAcao, centavos, data, dinheiro, erro, etiqueta, h, modal, rotulo, simNao, tabela, trocar,
} from "../ui.js";

const ativoCol = (campo = "ativo") => ({ rotulo: "Ativo", valor: (l) => simNao(l[campo]) });
const porOrdem = (a, b) => (a.ordem ?? 0) - (b.ordem ?? 0) || String(a.nome).localeCompare(String(b.nome));
const excluirGerente = () => ehGerente();

// ---------------------------------------------------------------- cardápio
const camposProduto = (tipo) => [
  { nome: "nome", rotulo: "Nome", obrigatorio: true },
  ...(tipo === "VENDA" ? [
    { nome: "categoria", rotulo: "Categoria", tipo: "fk", url: "/api/categorias/" },
    { nome: "preco_centavos", rotulo: "Preço (R$)", tipo: "dinheiro", ajuda: "Produtos com tamanhos usam o preço de cada variação." },
    { nome: "descricao", rotulo: "Descrição (aparece no cardápio)", tipo: "textarea" },
    { nome: "imagem", rotulo: "Foto", tipo: "imagem", largo: true },
    { nome: "ativo", rotulo: "Ativo", tipo: "bool", padrao: true },
    { nome: "disponivel_online", rotulo: "Aparece no cardápio online", tipo: "bool", padrao: true },
    { nome: "pausado", rotulo: "Esgotado agora (pausar)", tipo: "bool" },
    { nome: "setor", rotulo: "Setor de produção", tipo: "fk", url: "/api/setores/", ajuda: "Vazio = usa o da categoria." },
    { nome: "ordem", rotulo: "Ordem", tipo: "numero" },
  ] : [
    { nome: "unidade", rotulo: "Unidade", tipo: "select", enum: "UnidadeMedida", obrigatorio: true },
    { nome: "ativo", rotulo: "Ativo", tipo: "bool", padrao: true },
  ]),
  { secao: "Código e estoque" },
  { nome: "codigo", rotulo: "Código / SKU" },
  { nome: "gtin", rotulo: "Código de barras (EAN)" },
  ...(tipo === "VENDA" ? [{ nome: "unidade", rotulo: "Unidade", tipo: "select", enum: "UnidadeMedida", obrigatorio: true }] : []),
  { nome: "controla_estoque", rotulo: "Controla estoque deste item", tipo: "bool", padrao: tipo !== "VENDA" },
  { nome: "estoque_minimo", rotulo: "Estoque mínimo", tipo: "decimal", mostrarSe: (v) => v.controla_estoque },
  ...(tipo === "VENDA" ? [{ nome: "baixar_insumos", rotulo: "Baixar insumos da ficha técnica na venda", tipo: "bool" }] : []),
  ...(tipo === "VENDA" ? [
    { secao: "Dados fiscais (NFC-e)" },
    { nome: "ncm", rotulo: "NCM", max: 8 },
    { nome: "cfop", rotulo: "CFOP", max: 4 },
    { nome: "cst_csosn", rotulo: "CST/CSOSN" },
    { nome: "cest", rotulo: "CEST" },
    { nome: "origem", rotulo: "Origem (0 = nacional)", tipo: "numero" },
  ] : []),
];

function secaoVariacoes(produto, recarregar) {
  const caixa = h("div");
  const desenhar = async () => {
    const itens = await lista("/api/variacoes/", { produto: produto.id });
    trocar(caixa, 
      h("h3", null, "Tamanhos / variações"),
      h("p", { class: "muted" }, "Ex.: Média e Grande, cada uma com seu preço. Deixe vazio se o produto tem preço único."),
      itens.length ? tabela([
        { rotulo: "Nome", campo: "nome" },
        { rotulo: "Preço", classe: "num", valor: (v) => dinheiro(v.preco_centavos) },
        { rotulo: "", classe: "acoes-linha", valor: (v) => botaoAcao("Remover", async () => {
          await del(`/api/variacoes/${v.id}/`); desenhar(); recarregar();
        }, "botao botao-pequeno botao-perigo") },
      ], itens) : null,
      novaLinha());
  };
  const novaLinha = () => {
    const nome = h("input", { type: "text", placeholder: "Nome (ex.: Grande)" });
    const preco = h("input", { type: "text", placeholder: "Preço", inputmode: "decimal", style: { maxWidth: "120px" } });
    return h("div", { class: "acoes", style: { marginTop: "8px" } }, nome, preco, botaoAcao("Adicionar", async () => {
      if (!nome.value.trim()) return;
      await post("/api/variacoes/", { produto: produto.id, nome: nome.value.trim(), preco_centavos: centavos(preco.value) });
      desenhar(); recarregar();
    }));
  };
  desenhar().catch(erro);
  return caixa;
}

function secaoGrupos(produto) {
  const caixa = h("div", { style: { marginTop: "20px" } });
  (async () => {
    const [grupos, marcados] = await Promise.all([lista("/api/grupos-adicionais/"), get(`/api/produtos/${produto.id}/grupos/`)]);
    const sel = new Set(marcados.map(String));
    const chips = h("div", { class: "chips" }, grupos.map((g) => {
      const b = h("button", { type: "button", class: `chip ${sel.has(g.id) ? "marcado" : ""}` }, g.nome);
      b.addEventListener("click", () => { sel.has(g.id) ? sel.delete(g.id) : sel.add(g.id); b.classList.toggle("marcado"); });
      return b;
    }));
    trocar(caixa, h("h3", null, "Grupos de adicionais oferecidos"),
      grupos.length ? chips : h("p", { class: "muted" }, "Cadastre grupos em Cardápio → Adicionais."),
      grupos.length ? h("div", { style: { marginTop: "8px" } }, botaoAcao("Salvar grupos", async () => {
        await put(`/api/produtos/${produto.id}/grupos/`, { grupos: [...sel] });
        aviso("Grupos salvos.", "ok");
      })) : null);
  })().catch(erro);
  return caixa;
}

function secaoFicha(produto) {
  const caixa = h("div", { style: { marginTop: "20px" } });
  (async () => {
    const [insumos, linhas] = await Promise.all([
      lista("/api/produtos/", { tipo: "INSUMO" }), get(`/api/produtos/${produto.id}/ficha/`),
    ]);
    const nomeInsumo = (id) => insumos.find((i) => i.id === String(id));
    let atuais = linhas.map((l) => ({ insumo: String(l.insumo), quantidade: l.quantidade }));
    const lista_ = h("div");
    const redesenhar = () => {
      trocar(lista_, atuais.length ? h("ul", { class: "lista-simples" }, atuais.map((l, i) => {
        const ins = nomeInsumo(l.insumo);
        return h("li", null, h("span", null, `${ins?.nome || "?"} — ${l.quantidade} ${ins?.unidade || ""}`),
          h("button", { type: "button", class: "botao botao-pequeno botao-perigo", onclick: () => { atuais.splice(i, 1); redesenhar(); } }, "Remover"));
      })) : h("p", { class: "muted" }, "Sem insumos na ficha."));
    };
    const sel = h("select", null, h("option", { value: "" }, "Insumo…"), insumos.map((i) => h("option", { value: i.id }, `${i.nome} (${i.unidade})`)));
    const qtd = h("input", { type: "number", step: "0.001", placeholder: "Qtd", style: { maxWidth: "110px" } });
    redesenhar();
    trocar(caixa, h("h3", null, "Ficha técnica"),
      h("p", { class: "muted" }, "Quanto de cada insumo sai do estoque a cada unidade vendida (com \"Baixar insumos\" marcado)."),
      lista_,
      h("div", { class: "acoes", style: { marginTop: "8px" } }, sel, qtd,
        h("button", { type: "button", class: "botao", onclick: () => {
          if (!sel.value || !qtd.value) return;
          atuais.push({ insumo: sel.value, quantidade: qtd.value }); redesenhar();
        } }, "Incluir"),
        botaoAcao("Salvar ficha", async () => {
          await put(`/api/produtos/${produto.id}/ficha/`, atuais);
          aviso("Ficha técnica salva.", "ok");
        }, "botao botao-primario")));
  })().catch(erro);
  return caixa;
}

export function produtos() {
  return paginaCadastro({
    titulo: "Produtos", singular: "Produto", url: "/api/produtos/", params: { tipo: "VENDA" }, modalGrande: true,
    busca: ["nome", "codigo"], ordenar: porOrdem,
    novo: { tipo: "VENDA", ativo: true, disponivel_online: true, unidade: "UN", cfop: "5102" },
    filtros: [{ nome: "categoria", rotulo: "Todas as categorias", url: "/api/categorias/" }],
    colunas: [
      { rotulo: "", valor: (p) => p.imagem ? h("img", { src: p.imagem, alt: "", class: "foto-previa", style: { width: "44px", height: "44px" } }) : "" },
      { rotulo: "Produto", valor: (p) => h("div", null, h("div", { class: "negrito" }, p.nome),
        p.variacoes?.length ? h("small", { class: "muted" }, p.variacoes.map((v) => `${v.nome} ${dinheiro(v.preco_centavos)}`).join(" · ")) : null) },
      { rotulo: "Preço", classe: "num", valor: (p) => (p.variacoes?.length ? "—" : dinheiro(p.preco_centavos)) },
      { rotulo: "Situação", valor: (p) => !p.ativo ? etiqueta("Inativo") : p.pausado ? etiqueta("Esgotado", "e-alerta") : etiqueta("À venda", "e-ok") },
      { rotulo: "Estoque", classe: "num", valor: (p) => p.controla_estoque ? h("span", { class: p.abaixo_do_minimo ? "etiqueta e-erro" : "" }, `${Number(p.estoque_atual)} ${p.unidade}`) : "—" },
    ],
    campos: () => camposProduto("VENDA"),
    antesDeSalvar: (d) => ({ ...d, tipo: "VENDA" }),
    podeExcluir: excluirGerente,
    acoes: (p, recarregar) => ehGerente() ? botaoAcao(p.pausado ? "Reativar" : "Esgotar", async () => {
      await patch(`/api/produtos/${p.id}/`, { pausado: !p.pausado }); recarregar();
    }, "botao botao-pequeno") : null,
    extras: (p, recarregar) => [secaoVariacoes(p, recarregar), secaoGrupos(p), secaoFicha(p)],
  });
}

export function insumos() {
  return paginaCadastro({
    titulo: "Insumos", singular: "Insumo", url: "/api/produtos/", params: { tipo: "INSUMO" },
    intro: "Matérias-primas e embalagens: entram pelas compras e saem pela ficha técnica dos produtos.",
    busca: ["nome", "codigo"], novo: { tipo: "INSUMO", ativo: true, controla_estoque: true, unidade: "UN" },
    colunas: [
      { rotulo: "Insumo", campo: "nome" },
      { rotulo: "Saldo", classe: "num", valor: (p) => h("span", { class: p.abaixo_do_minimo ? "etiqueta e-erro" : "" }, `${Number(p.estoque_atual)} ${p.unidade}`) },
      { rotulo: "Mínimo", classe: "num", valor: (p) => (p.estoque_minimo != null ? `${Number(p.estoque_minimo)} ${p.unidade}` : "—") },
      { rotulo: "Custo médio", classe: "num", valor: (p) => dinheiro(p.custo_centavos) },
    ],
    campos: () => camposProduto("INSUMO"),
    antesDeSalvar: (d) => ({ ...d, tipo: "INSUMO" }),
    podeExcluir: excluirGerente,
  });
}

export function categorias() {
  return paginaCadastro({
    titulo: "Categorias", singular: "Categoria", url: "/api/categorias/", busca: ["nome"], ordenar: porOrdem,
    novo: { ativa: true, max_sabores: 1, regra_preco_sabores: "MAIOR" },
    colunas: [
      { rotulo: "Ordem", campo: "ordem", classe: "num" },
      { rotulo: "Categoria", campo: "nome" },
      { rotulo: "Sabores", classe: "num", valor: (c) => (c.max_sabores > 1 ? `até ${c.max_sabores}` : "—") },
      ativoCol("ativa"),
    ],
    campos: [
      { nome: "nome", rotulo: "Nome", obrigatorio: true },
      { nome: "descricao", rotulo: "Descrição" },
      { nome: "ordem", rotulo: "Ordem no cardápio", tipo: "numero" },
      { nome: "setor", rotulo: "Setor de produção", tipo: "fk", url: "/api/setores/" },
      { nome: "ativa", rotulo: "Ativa", tipo: "bool" },
      { secao: "Pizzas e meio a meio" },
      { nome: "max_sabores", rotulo: "Máximo de sabores por item", tipo: "numero" },
      { nome: "regra_preco_sabores", rotulo: "Preço com vários sabores", tipo: "select", enum: "RegraPrecoSabores", obrigatorio: true },
      { nome: "disponibilidade", rotulo: "Disponibilidade por horário (avançado)", tipo: "json", padraoJson: [],
        ajuda: 'Vazio = sempre. Ex.: [{"dia_semana": 0, "inicio": "11:00", "fim": "15:00"}] (0 = segunda)' },
    ],
    podeExcluir: excluirGerente,
  });
}

function secaoAdicionais(grupo, recarregar) {
  const caixa = h("div");
  const desenhar = async () => {
    const itens = await lista("/api/adicionais/", { grupo: grupo.id });
    const ativos = itens.filter((a) => !a.excluido_em);
    trocar(caixa, h("h3", null, "Opções deste grupo"),
      ativos.length ? tabela([
        { rotulo: "Opção", campo: "nome" },
        { rotulo: "Preço", classe: "num", valor: (a) => dinheiro(a.preco_centavos) },
        { rotulo: "Máx. por item", classe: "num", campo: "max_por_item" },
        { rotulo: "", classe: "acoes-linha", valor: (a) => botaoAcao("Remover", async () => {
          await del(`/api/adicionais/${a.id}/`); desenhar(); recarregar();
        }, "botao botao-pequeno botao-perigo") },
      ], ativos) : h("p", { class: "muted" }, "Nenhuma opção ainda."),
      novaLinha());
  };
  const novaLinha = () => {
    const nome = h("input", { type: "text", placeholder: "Opção (ex.: Bacon)" });
    const preco = h("input", { type: "text", placeholder: "Preço", inputmode: "decimal", style: { maxWidth: "110px" } });
    const max = h("input", { type: "number", value: "1", min: "1", style: { maxWidth: "80px" }, title: "Máximo por item" });
    return h("div", { class: "acoes", style: { marginTop: "8px" } }, nome, preco, max, botaoAcao("Adicionar", async () => {
      if (!nome.value.trim()) return;
      await post("/api/adicionais/", { grupo: grupo.id, nome: nome.value.trim(), preco_centavos: centavos(preco.value),
        max_por_item: parseInt(max.value, 10) || 1, ativo: true });
      desenhar(); recarregar();
    }));
  };
  desenhar().catch(erro);
  return caixa;
}

export function adicionais() {
  return paginaCadastro({
    titulo: "Adicionais", singular: "Grupo de adicionais", textoNovo: "Novo grupo", url: "/api/grupos-adicionais/",
    intro: "Grupos como \"Ponto da carne\" (obrigatório, escolhe 1) ou \"Extras\" (opcional, até 3). Depois, marque os grupos em cada produto.",
    busca: ["nome"], ordenar: porOrdem, novo: { min_selecao: 0, max_selecao: 1, ativo: true }, modalGrande: true,
    colunas: [
      { rotulo: "Grupo", campo: "nome" },
      { rotulo: "Escolha", valor: (g) => (g.min_selecao ? `obrigatório, ${g.min_selecao} a ${g.max_selecao}` : `opcional, até ${g.max_selecao}`) },
      { rotulo: "Opções", valor: (g) => (g.adicionais || []).map((a) => a.nome).join(", ") || "—" },
    ],
    campos: [
      { nome: "nome", rotulo: "Nome do grupo", obrigatorio: true },
      { nome: "min_selecao", rotulo: "Mínimo de escolhas (0 = opcional)", tipo: "numero" },
      { nome: "max_selecao", rotulo: "Máximo de escolhas", tipo: "numero" },
      { nome: "ordem", rotulo: "Ordem", tipo: "numero" },
      { nome: "ativo", rotulo: "Ativo", tipo: "bool" },
    ],
    podeExcluir: excluirGerente,
    extras: (g, recarregar) => secaoAdicionais(g, recarregar),
  });
}

export function setores() {
  return paginaCadastro({
    titulo: "Setores de produção", singular: "Setor", url: "/api/setores/", ordenar: porOrdem,
    intro: "Onde cada item é preparado (Chapa, Bar, Pizzaria). Cada setor tem sua fila na tela da cozinha e sua via impressa.",
    novo: { ativo: true },
    colunas: [{ rotulo: "Setor", campo: "nome" }, { rotulo: "Impressora (PDV desktop)", campo: "impressora" }, ativoCol()],
    campos: [
      { nome: "nome", rotulo: "Nome", obrigatorio: true },
      { nome: "impressora", rotulo: "Impressora", ajuda: 'Usada pelo PDV desktop: nome no Windows ou "ip:porta".' },
      { nome: "ordem", rotulo: "Ordem", tipo: "numero" },
      { nome: "ativo", rotulo: "Ativo", tipo: "bool" },
    ],
    podeExcluir: excluirGerente,
  });
}

// ---------------------------------------------------------------- clientes e entrega
function secaoEnderecos(cliente) {
  const caixa = h("div");
  const desenhar = async () => {
    const itens = await lista("/api/enderecos/", { cliente: cliente.id });
    trocar(caixa, h("h3", null, "Endereços"),
      itens.length ? h("ul", { class: "lista-simples" }, itens.map((e) => h("li", null,
        h("span", null, `${e.apelido ? `${e.apelido}: ` : ""}${e.logradouro}, ${e.numero}${e.complemento ? ` ${e.complemento}` : ""} — ${e.bairro}, ${e.cidade}`),
        botaoAcao("Remover", async () => { await del(`/api/enderecos/${e.id}/`); desenhar(); }, "botao botao-pequeno botao-perigo"))))
        : h("p", { class: "muted" }, "Nenhum endereço."),
      h("div", { style: { marginTop: "8px" } }, h("button", { type: "button", class: "botao", onclick: novo }, "+ Endereço")));
  };
  const novo = () => {
    const f = formulario([
      { nome: "apelido", rotulo: "Apelido (Casa, Trabalho)" },
      { nome: "cep", rotulo: "CEP" },
      { nome: "logradouro", rotulo: "Rua", obrigatorio: true, largo: true },
      { nome: "numero", rotulo: "Número", obrigatorio: true },
      { nome: "complemento", rotulo: "Complemento" },
      { nome: "bairro", rotulo: "Bairro", obrigatorio: true },
      { nome: "cidade", rotulo: "Cidade", obrigatorio: true },
      { nome: "uf", rotulo: "UF", max: 2 },
      { nome: "referencia", rotulo: "Referência", largo: true },
    ]);
    const m = modal({ titulo: "Novo endereço", corpo: f.el, rodape: [botaoAcao("Salvar", async () => {
      try {
        await post("/api/enderecos/", { ...f.ler(), cliente: cliente.id });
        m.fechar(); desenhar();
      } catch (e) { if (e.status === 400) f.mostrarErros(e.dados); else throw e; }
    }, "botao botao-primario")] });
  };
  desenhar().catch(erro);
  return caixa;
}

export function clientes() {
  return paginaCadastro({
    titulo: "Clientes", singular: "Cliente", url: "/api/clientes/", busca: ["nome", "telefone", "email"],
    podeCriar: () => true, podeEditar: () => true,
    colunas: [
      { rotulo: "Nome", campo: "nome" },
      { rotulo: "Telefone", campo: "telefone" },
      { rotulo: "Bairro", valor: (c) => c.enderecos?.[0]?.bairro || "—" },
      { rotulo: "Cashback", classe: "num", valor: (c) => (c.saldo_cashback_centavos ? dinheiro(c.saldo_cashback_centavos) : "—") },
      { rotulo: "Marketing", valor: (c) => simNao(c.aceita_marketing) },
    ],
    campos: [
      { nome: "nome", rotulo: "Nome", obrigatorio: true },
      { nome: "telefone", rotulo: "Telefone (só números, com DDD)", tipo: "tel", obrigatorio: true },
      { nome: "email", rotulo: "E-mail", tipo: "email" },
      { nome: "cpf", rotulo: "CPF (para nota)", max: 11 },
      { nome: "data_nascimento", rotulo: "Nascimento", tipo: "data" },
      { nome: "aceita_marketing", rotulo: "Aceita receber promoções", tipo: "bool" },
      { nome: "observacoes", rotulo: "Observações", tipo: "textarea" },
    ],
    antesDeSalvar: (d) => ({ ...d, telefone: String(d.telefone || "").replace(/\D/g, ""), cpf: String(d.cpf || "").replace(/\D/g, "") }),
    podeExcluir: excluirGerente,
    extras: (c) => secaoEnderecos(c),
  });
}

export function entregadores() {
  return paginaCadastro({
    titulo: "Entregadores", singular: "Entregador", url: "/api/entregadores/", busca: ["nome"], novo: { ativo: true },
    colunas: [{ rotulo: "Nome", campo: "nome" }, { rotulo: "Telefone", campo: "telefone" }, ativoCol()],
    campos: [
      { nome: "nome", rotulo: "Nome", obrigatorio: true },
      { nome: "telefone", rotulo: "Telefone", tipo: "tel" },
      { nome: "ativo", rotulo: "Ativo", tipo: "bool" },
    ],
    antesDeSalvar: (d) => ({ ...d, telefone: String(d.telefone || "").replace(/\D/g, "") }),
    podeExcluir: excluirGerente,
    intro: "Cada entregador recebe um link para abrir no celular: vê as entregas dele, o mapa, quanto cobrar e marca como entregue.",
    acoes: (e) => ehGerente() && e.ativo ? botaoAcao("Link do celular", () => linkEntregador(e), "botao botao-pequeno") : null,
  });
}

async function linkEntregador(e) {
  const r = await post(`/api/entregadores/${e.id}/link/`);
  const texto = `Olá, ${e.nome}! Suas entregas ficam neste link (guarde no celular): ${r.url}`;
  const wa = e.telefone ? `https://wa.me/55${e.telefone}?text=${encodeURIComponent(texto)}` : null;
  modal({
    titulo: `Link do entregador — ${e.nome}`, tamanho: "modal-pequeno",
    corpo: h("div", { class: "grade", style: { textAlign: "center" } },
      h("img", { src: `/painel/qrcode.svg?t=${encodeURIComponent(r.url)}`, alt: "QR Code do link", style: { width: "200px", margin: "0 auto" } }),
      h("textarea", { readonly: true, rows: 3, onclick: (ev) => ev.target.select() }, r.url),
      h("small", { class: "muted" }, "Gerar de novo desativa o link anterior.")),
    rodape: [
      h("button", { type: "button", class: "botao", onclick: () => navigator.clipboard?.writeText(r.url).then(() => aviso("Link copiado.", "ok")) }, "Copiar"),
      wa ? h("a", { class: "botao botao-primario", href: wa, target: "_blank", rel: "noopener" }, "Enviar no WhatsApp") : null,
    ],
  });
}

export function zonas() {
  return paginaCadastro({
    titulo: "Zonas de entrega", singular: "Zona", url: "/api/zonas-entrega/", busca: ["nome"],
    intro: "Taxa por bairro ou por distância (raio em km a partir da loja — precisa de latitude/longitude em Dados da loja).",
    novo: { tipo: "BAIRRO", ativa: true },
    colunas: [
      { rotulo: "Zona", campo: "nome" },
      { rotulo: "Tipo", valor: (z) => rotulo("TipoZonaEntrega", z.tipo) + (z.tipo === "RAIO_KM" ? ` até ${z.raio_max_km} km` : "") },
      { rotulo: "Taxa", classe: "num", valor: (z) => dinheiro(z.taxa_centavos) },
      { rotulo: "Tempo", valor: (z) => (z.tempo_estimado_min ? `${z.tempo_estimado_min} min` : "—") },
      ativoCol("ativa"),
    ],
    campos: [
      { nome: "tipo", rotulo: "Tipo", tipo: "select", enum: "TipoZonaEntrega", obrigatorio: true },
      { nome: "nome", rotulo: "Bairro / nome da faixa", obrigatorio: true },
      { nome: "raio_max_km", rotulo: "Raio máximo (km)", tipo: "decimal", passo: "0.1", mostrarSe: (v) => v.tipo === "RAIO_KM" },
      { nome: "taxa_centavos", rotulo: "Taxa (R$)", tipo: "dinheiro" },
      { nome: "tempo_estimado_min", rotulo: "Tempo estimado (min)", tipo: "numero", nulo: true },
      { nome: "ativa", rotulo: "Ativa", tipo: "bool" },
    ],
    podeExcluir: excluirGerente,
  });
}

export function cupons() {
  return paginaCadastro({
    titulo: "Cupons", singular: "Cupom", url: "/api/cupons/", busca: ["codigo", "descricao"],
    novo: { tipo: "PERCENTUAL", ativo: true, canais: [] },
    nomeDe: (c) => c.codigo,
    colunas: [
      { rotulo: "Código", valor: (c) => h("strong", null, c.codigo) },
      { rotulo: "Desconto", valor: (c) => (c.tipo === "PERCENTUAL" ? `${Number(c.valor)}%` : c.tipo === "VALOR_FIXO" ? dinheiro(c.valor) : "Frete grátis") },
      { rotulo: "Usos", classe: "num", valor: (c) => `${c.usos}${c.usos_maximos ? ` / ${c.usos_maximos}` : ""}` },
      { rotulo: "Validade", valor: (c) => (c.valido_ate ? `até ${data(c.valido_ate)}` : "—") },
      ativoCol(),
    ],
    campos: [
      { nome: "codigo", rotulo: "Código", obrigatorio: true, exemplo: "BEMVINDO10" },
      { nome: "descricao", rotulo: "Descrição" },
      { nome: "tipo", rotulo: "Tipo", tipo: "select", enum: "TipoCupom", obrigatorio: true },
      { nome: "valor", rotulo: "Valor", tipo: "decimal", passo: "0.01", ajuda: "Percentual: 10 = 10%. Valor fixo: em centavos (500 = R$ 5,00).",
        mostrarSe: (v) => v.tipo !== "FRETE_GRATIS" },
      { nome: "pedido_minimo_centavos", rotulo: "Pedido mínimo (R$)", tipo: "dinheiro" },
      { nome: "desconto_maximo_centavos", rotulo: "Desconto máximo (R$)", tipo: "dinheiro", nulo: true },
      { nome: "valido_de", rotulo: "Válido de", tipo: "datahora" },
      { nome: "valido_ate", rotulo: "Válido até", tipo: "datahora" },
      { nome: "usos_maximos", rotulo: "Limite de usos (vazio = ilimitado)", tipo: "numero", nulo: true },
      { nome: "usos_por_cliente", rotulo: "Usos por cliente", tipo: "numero", nulo: true },
      { nome: "somente_primeira_compra", rotulo: "Só na primeira compra", tipo: "bool" },
      { nome: "canais", rotulo: "Canais (nenhum marcado = todos)", tipo: "multi", enum: "CanalVenda" },
      { nome: "ativo", rotulo: "Ativo", tipo: "bool" },
    ],
    antesDeSalvar: (d) => ({ ...d, codigo: String(d.codigo || "").toUpperCase().replace(/\s/g, ""), valor: d.valor ?? 0 }),
    podeExcluir: excluirGerente,
  });
}

export function mesasCadastro() {
  return paginaCadastro({
    titulo: "Cadastro de mesas", singular: "Mesa", url: "/api/mesas/", busca: ["nome", "area"], ordenar: porOrdem,
    novo: { capacidade: 4, ativa: true },
    colunas: [{ rotulo: "Mesa", campo: "nome" }, { rotulo: "Área", campo: "area" },
      { rotulo: "Lugares", classe: "num", campo: "capacidade" }, ativoCol("ativa")],
    campos: [
      { nome: "nome", rotulo: "Nome", obrigatorio: true, exemplo: "Mesa 05" },
      { nome: "area", rotulo: "Área", exemplo: "Salão, Varanda" },
      { nome: "capacidade", rotulo: "Lugares", tipo: "numero" },
      { nome: "ordem", rotulo: "Ordem", tipo: "numero" },
      { nome: "ativa", rotulo: "Ativa", tipo: "bool" },
    ],
    podeExcluir: excluirGerente,
    topo: () => ehGerente() ? h("button", { type: "button", class: "botao", onclick: () => criarVarias() }, "Criar várias") : null,
  });
}

function criarVarias() {
  const f = formulario([
    { nome: "de", rotulo: "Da mesa nº", tipo: "numero", padrao: 1 },
    { nome: "ate", rotulo: "Até a mesa nº", tipo: "numero", padrao: 10 },
    { nome: "area", rotulo: "Área" },
    { nome: "capacidade", rotulo: "Lugares", tipo: "numero", padrao: 4 },
  ]);
  const m = modal({ titulo: "Criar várias mesas", corpo: f.el, tamanho: "modal-pequeno", rodape: [botaoAcao("Criar", async () => {
    const d = f.ler();
    if (d.ate < d.de || d.ate - d.de > 200) { f.mostrarErros("Intervalo inválido (máximo 200 mesas)."); return; }
    for (let n = d.de; n <= d.ate; n++) {
      await post("/api/mesas/", { nome: `Mesa ${String(n).padStart(2, "0")}`, area: d.area, capacidade: d.capacidade, ordem: n, ativa: true });
    }
    aviso("Mesas criadas.", "ok");
    m.fechar();
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }, "botao botao-primario")] });
}

export function fornecedores() {
  return paginaCadastro({
    titulo: "Fornecedores", singular: "Fornecedor", url: "/api/fornecedores/", busca: ["nome", "cnpj", "contato"],
    colunas: [{ rotulo: "Fornecedor", campo: "nome" }, { rotulo: "CNPJ/CPF", campo: "cnpj" },
      { rotulo: "Contato", campo: "contato" }, { rotulo: "Telefone", campo: "telefone" }],
    campos: [
      { nome: "nome", rotulo: "Nome", obrigatorio: true },
      { nome: "cnpj", rotulo: "CNPJ/CPF (só números)", max: 14 },
      { nome: "contato", rotulo: "Pessoa de contato" },
      { nome: "telefone", rotulo: "Telefone", tipo: "tel" },
      { nome: "email", rotulo: "E-mail", tipo: "email" },
      { nome: "observacoes", rotulo: "Observações", tipo: "textarea" },
    ],
    antesDeSalvar: (d) => ({ ...d, cnpj: String(d.cnpj || "").replace(/\D/g, "") }),
    podeExcluir: excluirGerente,
  });
}

// ---------------------------------------------------------------- financeiro
export function despesas() {
  return paginaCadastro({
    titulo: "Contas a pagar", singular: "Despesa", textoNovo: "Nova despesa", url: "/api/despesas/",
    busca: ["descricao"],
    filtros: [{ nome: "em_aberto", rotulo: "Todas", opcoes: [{ valor: "1", rotulo: "Só em aberto" }], padrao: "1" }],
    novo: { data_competencia: new Date().toISOString().slice(0, 10) },
    nomeDe: (d) => d.descricao,
    colunas: [
      { rotulo: "Descrição", campo: "descricao" },
      { rotulo: "Valor", classe: "num", valor: (d) => dinheiro(d.valor_centavos) },
      { rotulo: "Vencimento", valor: (d) => data(d.data_vencimento) || "—" },
      { rotulo: "Situação", valor: (d) => d.data_pagamento ? etiqueta(`Paga ${data(d.data_pagamento)}`, "e-ok")
        : d.data_vencimento && d.data_vencimento < new Date().toISOString().slice(0, 10) ? etiqueta("Vencida", "e-erro") : etiqueta("Em aberto", "e-alerta") },
    ],
    campos: [
      { nome: "descricao", rotulo: "Descrição", obrigatorio: true, largo: true },
      { nome: "valor_centavos", rotulo: "Valor (R$)", tipo: "dinheiro", obrigatorio: true },
      { nome: "categoria", rotulo: "Categoria", tipo: "fk", url: "/api/categorias-despesa/" },
      { nome: "fornecedor", rotulo: "Fornecedor", tipo: "fk", url: "/api/fornecedores/" },
      { nome: "data_competencia", rotulo: "Competência", tipo: "data", obrigatorio: true },
      { nome: "data_vencimento", rotulo: "Vencimento", tipo: "data" },
      { nome: "data_pagamento", rotulo: "Pago em (vazio = em aberto)", tipo: "data" },
      { nome: "forma_pagamento", rotulo: "Forma de pagamento", tipo: "select", enum: "FormaPagamento" },
    ],
    antesDeSalvar: (d) => ({ ...d, forma_pagamento: d.forma_pagamento || "" }),
    acoes: (d, recarregar) => !d.data_pagamento ? botaoAcao("Marcar como paga", async () => {
      await patch(`/api/despesas/${d.id}/`, { data_pagamento: new Date().toISOString().slice(0, 10) });
      recarregar();
    }, "botao botao-pequeno") : null,
    podeExcluir: excluirGerente,
  });
}

export function categoriasDespesa() {
  return paginaCadastro({
    titulo: "Categorias de despesa", singular: "Categoria", url: "/api/categorias-despesa/", busca: ["nome"], novo: { ativa: true },
    colunas: [{ rotulo: "Categoria", campo: "nome" }, ativoCol("ativa")],
    campos: [{ nome: "nome", rotulo: "Nome", obrigatorio: true }, { nome: "ativa", rotulo: "Ativa", tipo: "bool" }],
    podeExcluir: excluirGerente,
  });
}

export function taxas() {
  return paginaCadastro({
    titulo: "Taxas de pagamento", singular: "Taxa", url: "/api/taxas-pagamento/",
    intro: "Taxa da maquininha/app por forma de pagamento: entra no fluxo de caixa como líquido a receber.",
    nomeDe: (t) => rotulo("FormaPagamento", t.forma_pagamento),
    colunas: [
      { rotulo: "Forma", valor: (t) => rotulo("FormaPagamento", t.forma_pagamento) },
      { rotulo: "Bandeira", valor: (t) => t.bandeira || "Todas" },
      { rotulo: "Taxa", classe: "num", valor: (t) => `${Number(t.taxa_percentual)}%${t.taxa_fixa_centavos ? ` + ${dinheiro(t.taxa_fixa_centavos)}` : ""}` },
      { rotulo: "Recebe em", valor: (t) => (t.prazo_recebimento_dias ? `D+${t.prazo_recebimento_dias}` : "Na hora") },
    ],
    campos: [
      { nome: "forma_pagamento", rotulo: "Forma de pagamento", tipo: "select", enum: "FormaPagamento", obrigatorio: true },
      { nome: "bandeira", rotulo: "Bandeira (vazio = todas)" },
      { nome: "taxa_percentual", rotulo: "Taxa (%)", tipo: "decimal", passo: "0.01" },
      { nome: "taxa_fixa_centavos", rotulo: "Taxa fixa (R$)", tipo: "dinheiro" },
      { nome: "prazo_recebimento_dias", rotulo: "Prazo de recebimento (dias)", tipo: "numero" },
    ],
    podeExcluir: excluirGerente,
  });
}

// ---------------------------------------------------------------- campanhas
const PUBLICOS = [
  { valor: "MARKETING", rotulo: "Todos que aceitam promoções" },
  { valor: "CASHBACK", rotulo: "Quem tem saldo de cashback" },
  { valor: "INATIVOS", rotulo: "Quem não compra há X dias" },
];

export function campanhas() {
  return paginaCadastro({
    titulo: "Campanhas WhatsApp", singular: "Campanha", textoNovo: "Nova campanha", url: "/api/campanhas/",
    intro: "Mensagens pelo WhatsApp (integração Z-API) só para clientes que aceitaram receber promoções. "
      + "As mensagens saem aos poucos (uma a cada 8 segundos) para o número não ser bloqueado.",
    busca: ["nome"], podeEditar: (c) => c.status === "RASCUNHO",
    novo: { publico: "MARKETING", dias_inativo: 30,
      mensagem: "Oi, {nome}! Hoje tem promoção na {loja} 🍔\nPeça pelo link: {link}" },
    colunas: [
      { rotulo: "Campanha", campo: "nome" },
      { rotulo: "Público", valor: (c) => PUBLICOS.find((p) => p.valor === c.publico)?.rotulo || c.publico },
      { rotulo: "Situação", valor: (c) => etiqueta(c.status === "RASCUNHO" ? "Rascunho" : c.status === "ENVIANDO" ? "Enviando" : "Concluída",
        c.status === "CONCLUIDA" ? "e-ok" : c.status === "ENVIANDO" ? "e-info" : "e-alerta") },
      { rotulo: "Envios", classe: "num", valor: (c) => (c.total ? `${c.enviados}/${c.total}${c.falhas ? ` · ${c.falhas} falha(s)` : ""}` : "—") },
    ],
    campos: [
      { nome: "nome", rotulo: "Nome (só para você)", obrigatorio: true },
      { nome: "publico", rotulo: "Para quem", tipo: "select", opcoes: PUBLICOS, obrigatorio: true },
      { nome: "dias_inativo", rotulo: "Sem comprar há quantos dias", tipo: "numero", mostrarSe: (v) => v.publico === "INATIVOS" },
      { nome: "mensagem", rotulo: "Mensagem", tipo: "textarea", linhas: 5, obrigatorio: true,
        ajuda: "Troca automática: {nome} (primeiro nome), {loja}, {cashback} (saldo do cliente) e {link} (seu cardápio)." },
    ],
    podeExcluir: (c) => c.status !== "ENVIANDO",
    acoes: (c, recarregar) => c.status === "RASCUNHO" ? botaoAcao("Revisar e enviar", () => revisarCampanha(c, recarregar), "botao botao-pequeno botao-primario") : null,
  });
}

async function revisarCampanha(c, recarregar) {
  const r = await get(`/api/campanhas/${c.id}/previa/`);
  const m = modal({
    titulo: `Enviar "${c.nome}"`, tamanho: "modal-pequeno",
    corpo: h("div", { class: "grade" },
      h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Clientes que vão receber"), h("div", { class: "kpi-valor" }, String(r.total))),
      r.total ? h("div", null, h("small", { class: "muted" }, "Exemplo de mensagem:"),
        h("div", { class: "cartao", style: { whiteSpace: "pre-wrap", background: "#e9fbe5" } }, r.exemplo)) : h("div", { class: "alerta alerta-aviso" },
        "Nenhum cliente neste público aceitou receber promoções. Marque \"Aceita receber promoções\" no cadastro do cliente."),
      r.total ? h("small", { class: "muted" }, `Tempo estimado: ~${Math.ceil((r.total * 8) / 60)} min. Depois de enviada, a campanha não pode ser alterada.`) : null),
    rodape: r.total ? [botaoAcao("Enviar agora", async () => {
      await post(`/api/campanhas/${c.id}/enviar/`);
      aviso("Campanha em envio.", "ok"); m.fechar(); recarregar();
    }, "botao botao-primario")] : null,
  });
}
