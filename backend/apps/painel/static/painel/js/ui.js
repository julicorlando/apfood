// Blocos de interface do painel. Nada de innerHTML com dados: tudo vira nó de texto.

const PROPRIEDADES = new Set(["value", "checked", "selected", "disabled", "multiple", "hidden", "required", "readOnly"]);

export function h(tag, attrs, ...filhos) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (PROPRIEDADES.has(k)) el[k] = v;
      else el.setAttribute(k, v === true ? "" : String(v));
    }
  }
  anexar(el, filhos);
  return el;
}

export function anexar(el, filhos) {
  for (const f of filhos.flat(Infinity)) {
    if (f === null || f === undefined || f === false) continue;
    el.append(f instanceof Node ? f : document.createTextNode(String(f)));
  }
  return el;
}

export function limpar(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

// Limpa e preenche (aceita listas aninhadas, ao contrário do append nativo).
export function trocar(el, ...filhos) {
  return anexar(limpar(el), filhos);
}

// ---------------------------------------------------------------- formatação
const FMT_BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
export const dinheiro = (c) => FMT_BRL.format((Number(c) || 0) / 100);

export function centavos(texto) {
  if (typeof texto === "number") return Math.round(texto * 100);
  const limpo = String(texto ?? "").replace(/[^\d,.-]/g, "");
  if (!limpo) return 0;
  // "1.234,56" → 1234.56 ; "12.5" → 12.5
  const normal = limpo.includes(",") ? limpo.replace(/\./g, "").replace(",", ".") : limpo;
  const n = Number(normal);
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

export const reais = (c) => ((Number(c) || 0) / 100).toFixed(2).replace(".", ",");

export function data(iso) {
  if (!iso) return "";
  const [a, m, d] = String(iso).slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

export function dataHora(iso) {
  if (!iso) return "";
  const dt = new Date(iso);
  return dt.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function hora(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function hojeISO(deslocDias = 0) {
  const d = new Date();
  d.setDate(d.getDate() + deslocDias);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function minutosDesde(iso) {
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
}

export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16));
}

// ---------------------------------------------------------------- rótulos
let ROTULOS = {};
export function definirRotulos(enums) { ROTULOS = enums || {}; }
export function opcoes(enumNome) { return ROTULOS[enumNome] || []; }
export function rotulo(enumNome, valor) {
  const o = (ROTULOS[enumNome] || []).find((x) => x.valor === valor);
  return o ? o.rotulo : (valor ?? "");
}

const COR_STATUS = {
  PENDENTE: "e-alerta", RECEBIDO: "e-info", EM_PREPARO: "e-info", PRONTO: "e-ok", SAIU_PARA_ENTREGA: "e-cor",
  CONCLUIDO: "e-ok", CANCELADO: "e-erro", RECUSADO: "e-erro", ABERTO: "e-ok", FECHADO: "", ABERTA: "e-ok",
  FECHANDO: "e-alerta", FECHADA: "", CANCELADA: "e-erro", AUTORIZADA: "e-ok", REJEITADA: "e-erro",
  PROCESSANDO: "e-alerta", RASCUNHO: "e-alerta", LANCADA: "e-ok", PAGA: "e-ok", VENCIDA: "e-erro",
  CONFIRMADO: "e-ok", ESTORNADO: "e-erro", TRIAL: "e-info", ATIVA: "e-ok", INADIMPLENTE: "e-erro",
};
export function etiqueta(texto, classe = "") { return h("span", { class: `etiqueta ${classe}` }, texto); }
export function etiquetaStatus(enumNome, valor) { return etiqueta(rotulo(enumNome, valor), COR_STATUS[valor] || ""); }
export const simNao = (v) => (v ? etiqueta("Sim", "e-ok") : etiqueta("Não"));

// ---------------------------------------------------------------- avisos
export function aviso(msg, tipo = "") {
  const caixa = document.getElementById("avisos");
  if (!caixa) return;
  const el = h("div", { class: `aviso ${tipo}`, role: tipo === "erro" ? "alert" : "status" }, msg);
  caixa.append(el);
  setTimeout(() => el.remove(), tipo === "erro" ? 7000 : 3500);
}

export function erro(e) {
  console.error(e);
  aviso(e?.mensagem || e?.message || "Algo deu errado.", "erro");
}

// ---------------------------------------------------------------- modal
export function modal({ titulo, corpo, rodape, tamanho = "", aoFechar } = {}) {
  const anterior = document.activeElement;
  const fundo = h("div", { class: "modal-fundo" });
  const fecharBtn = h("button", { type: "button", class: "botao-icone", "aria-label": "Fechar" }, "✕");
  const caixa = h("div", { class: `modal ${tamanho}`, role: "dialog", "aria-modal": "true", "aria-label": titulo },
    h("div", { class: "modal-topo" }, h("h2", null, titulo), fecharBtn),
    h("div", { class: "modal-corpo" }, corpo),
    rodape ? h("div", { class: "modal-rodape" }, rodape) : null);
  fundo.append(caixa);
  let fechado = false;
  const fechar = () => {
    if (fechado) return;
    fechado = true;
    fundo.remove();
    document.removeEventListener("keydown", esc);
    anterior?.focus?.();
    aoFechar?.();
  };
  const esc = (ev) => { if (ev.key === "Escape") fechar(); };
  fecharBtn.addEventListener("click", fechar);
  fundo.addEventListener("mousedown", (ev) => { if (ev.target === fundo) fechar(); });
  document.addEventListener("keydown", esc);
  document.body.append(fundo);
  const foco = caixa.querySelector("input:not([type=hidden]), select, textarea, button.botao-primario");
  (foco || fecharBtn).focus();
  return { fechar, el: caixa, corpo: caixa.querySelector(".modal-corpo") };
}

export function confirmar(mensagem, { titulo = "Confirmar", ok = "Confirmar", perigo = false } = {}) {
  return new Promise((resolve) => {
    let resposta = false;
    const sim = h("button", { class: `botao ${perigo ? "botao-perigo" : "botao-primario"}`, type: "button" }, ok);
    const nao = h("button", { class: "botao", type: "button" }, "Cancelar");
    const m = modal({ titulo, corpo: h("p", null, mensagem), rodape: [nao, sim], tamanho: "modal-pequeno",
      aoFechar: () => resolve(resposta) });
    sim.addEventListener("click", () => { resposta = true; m.fechar(); });
    nao.addEventListener("click", () => m.fechar());
    sim.focus();
  });
}

export function pedirTexto(titulo, { rotulo: rot = "", valor = "", obrigatorio = true, ok = "Confirmar", tipo = "text", minimo = 0 } = {}) {
  return new Promise((resolve) => {
    let resposta = null;
    const campo = h("input", { type: tipo, value: valor });
    const erroEl = h("div", { class: "erro" });
    const form = h("form", { class: "grade" }, h("label", { class: "campo" }, h("span", null, rot), campo, erroEl));
    const btn = h("button", { class: "botao botao-primario", type: "submit" }, ok);
    const m = modal({ titulo, corpo: form, rodape: [btn], tamanho: "modal-pequeno", aoFechar: () => resolve(resposta) });
    const enviar = (ev) => {
      ev.preventDefault();
      const v = campo.value.trim();
      if (obrigatorio && v.length < Math.max(1, minimo)) {
        erroEl.textContent = minimo ? `Informe pelo menos ${minimo} caracteres.` : "Campo obrigatório.";
        return;
      }
      resposta = v;
      m.fechar();
    };
    form.addEventListener("submit", enviar);
    btn.addEventListener("click", enviar);
    campo.focus();
  });
}

// ---------------------------------------------------------------- tabela
export function tabela(colunas, linhas, { aoClicar, vazio = "Nada por aqui ainda." } = {}) {
  if (!linhas.length) return h("div", { class: "cartao vazio" }, vazio);
  return h("div", { class: "tabela-caixa" },
    h("table", { class: "tabela" },
      h("thead", null, h("tr", null, colunas.map((c) => h("th", { class: c.classe || "" }, c.rotulo)))),
      h("tbody", null, linhas.map((l) => {
        const tr = h("tr", { class: aoClicar ? "clicavel" : "" },
          colunas.map((c) => h("td", { class: c.classe || "" }, c.valor ? c.valor(l) : l[c.campo])));
        if (aoClicar) tr.addEventListener("click", (ev) => { if (!ev.target.closest("button,a,input")) aoClicar(l); });
        return tr;
      }))));
}

export function kpi(rot, valor, detalhe) {
  return h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, rot), h("div", { class: "kpi-valor" }, valor),
    detalhe ? h("div", { class: "kpi-detalhe" }, detalhe) : null);
}

export function barras(pontos, { rotulo: rot = (p) => p.rotulo, valor = (p) => p.valor, dica = null } = {}) {
  const max = Math.max(1, ...pontos.map(valor));
  return h("div", null,
    h("div", { class: "barras" }, pontos.map((p) => h("div", {
      class: "barra", style: { height: `${(valor(p) / max) * 100}%` }, title: dica ? dica(p) : String(valor(p)),
    }))),
    h("div", { class: "barras-rotulos" }, pontos.map((p) => h("span", null, rot(p)))));
}

export function abas(itens, aoTrocar, inicial = 0) {
  const barra = h("div", { class: "abas", role: "tablist" });
  const botoes = itens.map((it, i) => h("button", {
    type: "button", role: "tab", class: i === inicial ? "ativa" : "",
    onclick: () => { botoes.forEach((b) => b.classList.remove("ativa")); botoes[i].classList.add("ativa"); aoTrocar(it, i); },
  }, it.rotulo));
  anexar(barra, botoes);
  return barra;
}

export function carregando(texto = "Carregando…") { return h("div", { class: "carregando" }, texto); }

// botão que se desabilita enquanto a ação roda
export function botaoAcao(texto, acao, classe = "botao") {
  const b = h("button", { type: "button", class: classe }, texto);
  b.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    if (b.disabled) return;
    b.disabled = true;
    try { await acao(ev); } catch (e) { erro(e); } finally { b.disabled = false; }
  });
  return b;
}
