// Painel ApFood: roteamento por hash, menu por perfil e seletor de loja.
import { definirLoja, ehAdmin, ehGerente, ehMaster, get, lojaSalva, sessao } from "./api.js";
import { bipe, conectar, ouvir } from "./realtime.js";
import { aviso, data, definirRotulos, dinheiro, erro, h, limpar, trocar } from "./ui.js";

const temLoja = () => !!sessao.loja;

// [rota, título, ícone, grupo, permissão, módulo, função]
const ROTAS = [
  ["/", "Início", "📊", "Operação", () => !ehMaster(), "operacao", "inicio"],
  ["/pdv", "PDV (vender)", "🧾", "Operação", temLoja, "pdv", "pdv"],
  ["/pedidos", "Pedidos", "🛎️", "Operação", temLoja, "operacao", "pedidos"],
  ["/mesas", "Mesas e comandas", "🍽️", "Operação", temLoja, "operacao", "mesas"],
  ["/cozinha", "Cozinha", "👨‍🍳", "Operação", temLoja, "operacao", "cozinha"],
  ["/caixa", "Caixa", "💵", "Operação", temLoja, "operacao", "caixa"],

  ["/produtos", "Produtos", "🍔", "Cardápio", temLoja, "cadastros", "produtos"],
  ["/categorias", "Categorias", "🗂️", "Cardápio", temLoja, "cadastros", "categorias"],
  ["/adicionais", "Adicionais", "➕", "Cardápio", temLoja, "cadastros", "adicionais"],
  ["/setores", "Setores de produção", "🔥", "Cardápio", temLoja, "cadastros", "setores"],
  ["/insumos", "Insumos", "🥬", "Cardápio", temLoja, "cadastros", "insumos"],

  ["/clientes", "Clientes", "👥", "Clientes e entrega", temLoja, "cadastros", "clientes"],
  ["/entregadores", "Entregadores", "🛵", "Clientes e entrega", temLoja, "cadastros", "entregadores"],
  ["/zonas", "Zonas de entrega", "📍", "Clientes e entrega", temLoja, "cadastros", "zonas"],
  ["/cupons", "Cupons", "🏷️", "Clientes e entrega", temLoja, "cadastros", "cupons"],
  ["/campanhas", "Campanhas WhatsApp", "📣", "Clientes e entrega", () => temLoja() && ehGerente(), "cadastros", "campanhas"],
  ["/mesas-cadastro", "Cadastro de mesas", "🪑", "Clientes e entrega", temLoja, "cadastros", "mesasCadastro"],

  ["/estoque", "Estoque", "📦", "Estoque e compras", () => temLoja() && ehGerente(), "gestao", "estoque"],
  ["/compras", "Compras", "🛒", "Estoque e compras", () => temLoja() && ehGerente(), "gestao", "compras"],
  ["/fornecedores", "Fornecedores", "🚚", "Estoque e compras", temLoja, "cadastros", "fornecedores"],

  ["/contas-a-pagar", "Contas a pagar", "📄", "Financeiro", () => temLoja() && ehGerente(), "cadastros", "despesas"],
  ["/fluxo-de-caixa", "Fluxo de caixa", "📈", "Financeiro", () => temLoja() && ehGerente(), "gestao", "fluxoCaixa"],
  ["/categorias-despesa", "Categorias de despesa", "🧮", "Financeiro", () => temLoja() && ehGerente(), "cadastros", "categoriasDespesa"],
  ["/taxas", "Taxas de pagamento", "💳", "Financeiro", () => temLoja() && ehGerente(), "cadastros", "taxas"],

  ["/relatorios", "Vendas", "📊", "Relatórios", () => temLoja() && ehGerente(), "gestao", "vendas"],
  ["/curva-abc", "Curva ABC", "🔤", "Relatórios", () => temLoja() && ehGerente(), "gestao", "curvaAbc"],
  ["/fechamentos", "Fechamentos de caixa", "🔐", "Relatórios", () => temLoja() && ehGerente(), "gestao", "fechamentos"],
  ["/notas", "Notas fiscais", "🧾", "Relatórios", temLoja, "gestao", "notas"],

  ["/loja", "Dados da loja", "🏪", "Configurações", () => temLoja() && ehAdmin(), "config", "loja"],
  ["/fiscal", "Fiscal", "🏛️", "Configurações", () => temLoja() && ehAdmin(), "config", "fiscal"],
  ["/integracoes", "Integrações", "🔌", "Configurações", () => temLoja() && ehAdmin(), "config", "integracoes"],
  ["/impressao", "Impressão", "🖨️", "Configurações", () => !ehMaster(), "config", "impressao"],
  ["/usuarios", "Usuários", "🔑", "Configurações", ehGerente, "config", "usuarios"],
  ["/lojas", "Lojas", "🏬", "Configurações", ehAdmin, "config", "lojas"],
  ["/empresa", "Minha empresa", "🏢", "Configurações", () => ehAdmin() && !ehMaster(), "config", "minhaEmpresa"],

  ["/plataforma", "Visão geral", "🌐", "Plataforma", ehMaster, "plataforma", "visaoGeral"],
  ["/empresas", "Empresas", "🏢", "Plataforma", ehMaster, "plataforma", "empresas"],
  ["/planos", "Planos", "📋", "Plataforma", ehMaster, "plataforma", "planos"],
  ["/faturas", "Faturas", "💰", "Plataforma", ehMaster, "plataforma", "faturas"],
];

const modulos = {
  operacao: () => import("./paginas/operacao.js"),
  pdv: () => import("./paginas/pdv.js"),
  cadastros: () => import("./paginas/cadastros.js"),
  gestao: () => import("./paginas/gestao.js"),
  config: () => import("./paginas/config.js"),
  plataforma: () => import("./paginas/plataforma.js"),
};

const $ = (id) => document.getElementById(id);
let limpeza = null;
let navegacao = 0;

function rotaAtual() {
  const bruto = location.hash.replace(/^#/, "") || "/";
  const [caminho, query] = bruto.split("?");
  return { caminho, params: new URLSearchParams(query || "") };
}

function montarMenu() {
  const nav = limpar($("nav"));
  let grupo = null;
  for (const [rota, titulo, icone, g, pode] of ROTAS) {
    if (!pode()) continue;
    if (g !== grupo) { nav.append(h("div", { class: "menu-grupo" }, g)); grupo = g; }
    nav.append(h("a", { href: `#${rota}`, class: "item", dataset: { rota } }, h("span", { class: "icone", "aria-hidden": "true" }, icone), titulo));
  }
}

function marcarMenu(caminho) {
  document.querySelectorAll(".menu a.item").forEach((a) => a.classList.toggle("ativo", a.dataset.rota === caminho));
}

async function navegar() {
  const { caminho, params } = rotaAtual();
  const minha = ++navegacao;
  // MASTER administra a plataforma (não opera lojas): a tela inicial dele é a Visão geral
  const inicial = ehMaster() ? ROTAS.find((r) => r[0] === "/plataforma") : ROTAS[0];
  const def = ROTAS.find((r) => r[0] === caminho && r[4]()) || inicial;
  const [, titulo, , , , mod, fn] = def;
  if (limpeza) { try { limpeza(); } catch (e) { console.error(e); } limpeza = null; }
  $("app").classList.remove("menu-aberto");
  marcarMenu(def[0]);
  $("titulo").textContent = titulo;
  document.title = `${titulo} — ApFood`;
  const raiz = limpar($("conteudo"));
  raiz.append(h("div", { class: "carregando" }, "Carregando…"));
  try {
    const m = await modulos[mod]();
    if (minha !== navegacao) return;
    const pagina = m[fn]();
    if (pagina.titulo && pagina.titulo !== titulo) $("titulo").textContent = pagina.titulo;
    const r = await pagina.render(raiz, params);
    if (minha !== navegacao) { if (typeof r === "function") r(); return; }
    if (typeof r === "function") limpeza = r;
    raiz.focus({ preventScroll: true });
  } catch (e) {
    erro(e);
    trocar(raiz, h("div", { class: "alerta alerta-erro" }, e.mensagem || e.message || "Não foi possível abrir esta tela."));
  }
}

function montarSeletorLoja() {
  const sel = limpar($("seletor-loja"));
  sel.hidden = sessao.lojas.length <= 1;
  for (const l of sessao.lojas) sel.append(h("option", { value: l.id, selected: l.id === sessao.loja?.id }, l.nome));
  sel.onchange = () => {
    definirLoja(sel.value);
    conectar();
    montarMenu();
    navegar();
  };
}

export async function recarregarSessao() {
  const eu = await get("/api/eu/", { semLoja: true });
  sessao.usuario = eu;
  sessao.lojas = eu.lojas || [];
  definirLoja(sessao.loja?.id || lojaSalva());
  montarSeletorLoja();
  montarMenu();
  return eu;
}

// Faixa no topo: fim do teste grátis ou fatura em aberto (só ADMIN da empresa).
export async function mostrarAssinatura() {
  document.getElementById("faixa-assinatura")?.remove();
  const a = await get("/api/assinatura/", { semLoja: true });
  const f = a.fatura_aberta;
  let texto = null;
  let classe = "faixa";
  if (f && f.vencida) {
    classe += " faixa-perigo";
    texto = `Fatura ${f.competencia.slice(5, 7)}/${f.competencia.slice(0, 4)} (${dinheiro(f.valor_centavos)}) venceu em ${data(f.vencimento)}. `
      + `O acesso é suspenso ${a.tolerancia_dias} dias após o vencimento.`;
  } else if (f) {
    texto = `Fatura ${f.competencia.slice(5, 7)}/${f.competencia.slice(0, 4)} de ${dinheiro(f.valor_centavos)} vence em ${data(f.vencimento)}.`;
  } else if (a.dias_de_teste !== null && a.dias_de_teste <= 7) {
    texto = a.dias_de_teste > 0
      ? `Seu teste grátis termina em ${a.dias_de_teste} dia${a.dias_de_teste === 1 ? "" : "s"} (${data(a.trial_ate)}).`
      : "Seu teste grátis termina hoje.";
  }
  if (!texto) return;
  const faixa = h("div", { class: classe, id: "faixa-assinatura", role: "status" }, h("span", null, texto),
    f?.link_pagamento ? h("a", { class: "botao botao-pequeno botao-primario", href: f.link_pagamento, target: "_blank", rel: "noopener" }, "Pagar com Pix") : null,
    h("a", { class: "botao botao-pequeno", href: "#/empresa" }, f ? "Ver faturas" : "Ver planos"));
  $("conteudo").before(faixa);
}

async function iniciar() {
  $("abrir-menu").addEventListener("click", () => $("app").classList.add("menu-aberto"));
  $("fechar-menu").addEventListener("click", () => $("app").classList.remove("menu-aberto"));
  $("fundo-menu").addEventListener("click", () => $("app").classList.remove("menu-aberto"));
  try {
    const [, enums] = await Promise.all([recarregarSessao(), get("/api/enums/", { semLoja: true })]);
    definirRotulos(enums);
  } catch (e) {
    erro(e);
    return;
  }
  const u = sessao.usuario;
  $("usuario").textContent = `${u.nome} · ${u.empresa?.nome || "Plataforma"}`;
  if (ehAdmin() && !ehMaster()) mostrarAssinatura().catch(() => {});
  conectar();
  ouvir((ev) => {
    if (ev.tipo === "pedido.novo") {
      bipe();
      aviso(`Novo pedido #${ev.pedido?.numero ?? ""}${ev.pedido?.nome_cliente ? ` — ${ev.pedido.nome_cliente}` : ""}`, "ok");
    }
    if (ev.tipo === "estoque.alerta") aviso(`Estoque baixo: ${ev.produto?.nome ?? ""}`);
  });
  window.addEventListener("hashchange", navegar);
  navegar();
}

iniciar();
