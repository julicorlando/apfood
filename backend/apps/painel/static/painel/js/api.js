// Cliente da API REST (/api/) autenticado pela sessão do navegador.

export const sessao = { usuario: null, loja: null, lojas: [] };

const CHAVE_LOJA = "apfood.loja";

export class ErroApi extends Error {
  constructor(status, dados) {
    super(mensagemDeErro(dados) || `Erro ${status}`);
    this.status = status;
    this.dados = dados;
    this.mensagem = this.message;
  }
}

// Achata o formato de erro do DRF: {"campo": ["msg"]} → "Campo: msg"
export function mensagemDeErro(dados) {
  if (!dados) return "";
  if (typeof dados === "string") return dados.length > 300 ? "" : dados;
  if (Array.isArray(dados)) return dados.map(mensagemDeErro).filter(Boolean).join(" ");
  if (dados.detail) return mensagemDeErro(dados.detail);
  return Object.entries(dados).map(([k, v]) => {
    const m = mensagemDeErro(v);
    return k === "non_field_errors" || k === "__all__" ? m : `${k.replace(/_/g, " ")}: ${m}`;
  }).join(" · ");
}

function csrf() {
  const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export function definirLoja(id) {
  sessao.loja = sessao.lojas.find((l) => l.id === id) || sessao.lojas[0] || null;
  try { if (sessao.loja) localStorage.setItem(CHAVE_LOJA, sessao.loja.id); } catch { /* modo privado */ }
}

export function lojaSalva() {
  try { return localStorage.getItem(CHAVE_LOJA); } catch { return null; }
}

export function comLoja(url) {
  if (!sessao.loja) return url;
  const u = new URL(url, location.origin);
  if (!u.searchParams.has("loja")) u.searchParams.set("loja", sessao.loja.id);
  return u.pathname + u.search;
}

export async function req(metodo, url, corpo, { semLoja = false } = {}) {
  const opcoes = { method: metodo, credentials: "same-origin", headers: { Accept: "application/json" } };
  if (metodo !== "GET" && metodo !== "HEAD") opcoes.headers["X-CSRFToken"] = csrf();
  if (corpo instanceof FormData) opcoes.body = corpo;
  else if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  const r = await fetch(semLoja ? url : comLoja(url), opcoes);
  if (r.status === 401 || (r.status === 403 && !(r.headers.get("content-type") || "").includes("json"))) {
    location.href = "/painel/entrar/?next=" + encodeURIComponent(location.pathname + location.hash);
    throw new ErroApi(r.status, "Sessão expirada.");
  }
  const tipo = r.headers.get("content-type") || "";
  const dados = r.status === 204 ? null : tipo.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new ErroApi(r.status, dados);
  return dados;
}

export const get = (url, op) => req("GET", url, undefined, op);
export const post = (url, corpo, op) => req("POST", url, corpo ?? {}, op);
export const put = (url, corpo, op) => req("PUT", url, corpo, op);
export const patch = (url, corpo, op) => req("PATCH", url, corpo, op);
export const del = (url, op) => req("DELETE", url, undefined, op);

// Lista completa (segue a paginação limit/offset do DRF).
export async function lista(url, params = {}, op) {
  const u = new URL(url, location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.searchParams.append(k, x));
    else u.searchParams.set(k, v);
  }
  if (!u.searchParams.has("limit")) u.searchParams.set("limit", "500");
  let proxima = u.pathname + u.search;
  const tudo = [];
  for (let i = 0; proxima && i < 20; i++) {
    const dados = await get(proxima, op);
    if (Array.isArray(dados)) return dados;
    tudo.push(...(dados.results || []));
    proxima = dados.next ? new URL(dados.next, location.origin).pathname + new URL(dados.next, location.origin).search : null;
  }
  return tudo;
}

// Papéis
export const papel = () => sessao.usuario?.papel;
export const ehMaster = () => papel() === "MASTER";
export const ehAdmin = () => ["MASTER", "ADMIN"].includes(papel());
export const ehGerente = () => ["MASTER", "ADMIN", "GERENTE"].includes(papel());
