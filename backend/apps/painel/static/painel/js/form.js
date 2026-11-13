// Formulários gerados a partir de uma descrição de campos.
import { lista } from "./api.js";
import { centavos, h, opcoes as opcoesEnum, reais } from "./ui.js";

const cacheFk = new Map();

export function limparCacheFk() { cacheFk.clear(); }

async function opcoesFk(campo) {
  const chave = campo.url + JSON.stringify(campo.params || {});
  if (!cacheFk.has(chave)) cacheFk.set(chave, lista(campo.url, campo.params || {}));
  const itens = await cacheFk.get(chave);
  const rot = campo.rotuloFk || ((x) => x.nome ?? x.username ?? x.id);
  return itens.map((x) => ({ valor: String(x.id), rotulo: rot(x) }));
}

function paraDataHoraLocal(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function criarEntrada(c, valor) {
  switch (c.tipo) {
    case "bool":
      return h("input", { type: "checkbox", checked: !!valor });
    case "textarea":
      return h("textarea", { rows: c.linhas || 3 }, valor ?? "");
    case "json":
      return h("textarea", { rows: c.linhas || 4, spellcheck: "false", style: { fontFamily: "monospace" } },
        valor === undefined || valor === null || valor === "" ? "" : JSON.stringify(valor, null, 2));
    case "dinheiro":
      return h("input", { type: "text", inputmode: "decimal", placeholder: "0,00",
        value: valor === null || valor === undefined || valor === "" ? "" : reais(valor) });
    case "numero":
      return h("input", { type: "number", step: "1", value: valor ?? "" });
    case "decimal":
      return h("input", { type: "number", step: c.passo || "0.001", value: valor ?? "" });
    case "data":
      return h("input", { type: "date", value: valor ? String(valor).slice(0, 10) : "" });
    case "datahora":
      return h("input", { type: "datetime-local", value: paraDataHoraLocal(valor) });
    case "hora":
      return h("input", { type: "time", value: valor ? String(valor).slice(0, 5) : "" });
    case "cor":
      return h("input", { type: "color", value: valor || "#e4572e", style: { height: "40px", padding: "2px" } });
    case "senha":
      return h("input", { type: "password", autocomplete: "new-password", value: "" });
    case "imagem": {
      const prev = h("img", { class: "foto-previa", alt: "", src: valor || "", hidden: !valor });
      const inp = h("input", { type: "file", accept: "image/*" });
      inp.addEventListener("change", () => {
        const f = inp.files[0];
        if (f) { prev.src = URL.createObjectURL(f); prev.hidden = false; }
      });
      return h("div", { class: "acoes" }, prev, inp);
    }
    case "select":
    case "fk": {
      const sel = h("select", null, c.obrigatorio ? null : h("option", { value: "" }, c.vazio || "—"));
      const preencher = (ops) => {
        for (const o of ops) sel.append(h("option", { value: o.valor, selected: String(valor ?? "") === String(o.valor) }, o.rotulo));
        if (valor !== undefined && valor !== null) sel.value = String(valor);
      };
      if (c.tipo === "fk") opcoesFk(c).then(preencher);
      else preencher(c.enum ? opcoesEnum(c.enum) : c.opcoes || []);
      return sel;
    }
    case "multi": {
      const marcados = new Set((valor || []).map(String));
      const caixa = h("div", { class: "chips" });
      caixa._marcados = marcados;
      const fonte = c.url ? opcoesFk(c) : Promise.resolve(c.enum ? opcoesEnum(c.enum) : c.opcoes || []);
      fonte.then((ops) => {
        if (!ops.length) caixa.append(h("span", { class: "muted" }, "Nenhuma opção."));
        for (const o of ops) {
          const chip = h("button", { type: "button", class: `chip ${marcados.has(o.valor) ? "marcado" : ""}` }, o.rotulo);
          chip.addEventListener("click", () => {
            if (marcados.has(o.valor)) marcados.delete(o.valor); else marcados.add(o.valor);
            chip.classList.toggle("marcado");
          });
          caixa.append(chip);
        }
      });
      return caixa;
    }
    default:
      return h("input", { type: c.tipo === "email" ? "email" : c.tipo === "tel" ? "tel" : "text", value: valor ?? "",
        maxlength: c.max || null, placeholder: c.exemplo || null, autocomplete: "off" });
  }
}

function lerEntrada(c, el) {
  switch (c.tipo) {
    case "bool": return el.checked;
    case "dinheiro": return el.value.trim() === "" ? (c.nulo ? null : 0) : centavos(el.value);
    case "numero": return el.value === "" ? (c.nulo ? null : 0) : parseInt(el.value, 10);
    case "decimal": return el.value === "" ? null : el.value;
    case "json": {
      const t = el.value.trim();
      if (!t) return c.padraoJson ?? {};
      try { return JSON.parse(t); } catch { throw new Error(`${c.rotulo}: JSON inválido`); }
    }
    case "data": case "hora": return el.value || null;
    case "datahora": return el.value ? new Date(el.value).toISOString() : null;
    case "imagem": return el.querySelector("input[type=file]").files[0] || undefined;
    case "multi": return [...el._marcados];
    case "fk": case "select": return el.value === "" ? null : el.value;
    case "senha": return el.value;
    default: return el.value.trim();
  }
}

/**
 * campos: [{nome, rotulo, tipo, ajuda, largo, obrigatorio, enum|opcoes|url, secao, mostrarSe(valores)}]
 * Retorna {el, ler() → dados, mostrarErros(dadosDeErro)}.
 */
export function formulario(campos, valores = {}, { aoEnviar } = {}) {
  const grade = h("div", { class: "form-grade" });
  const alerta = h("div", { class: "alerta alerta-erro largo", hidden: true, role: "alert" });
  grade.append(alerta);
  const entradas = {};
  const blocos = {};
  for (const c of campos) {
    if (c.secao) { grade.append(h("div", { class: "form-secao" }, c.secao)); continue; }
    const entrada = criarEntrada(c, valores[c.nome] ?? c.padrao);
    const erroEl = h("div", { class: "erro" });
    let bloco;
    if (c.tipo === "bool") {
      bloco = h("div", { class: `campo ${c.largo ? "largo" : ""}` },
        h("label", { class: "check" }, entrada, h("span", null, c.rotulo)),
        c.ajuda ? h("small", null, c.ajuda) : null, erroEl);
    } else {
      bloco = h("label", { class: `campo ${c.largo || ["textarea", "json", "multi"].includes(c.tipo) ? "largo" : ""}` },
        h("span", null, c.rotulo, c.obrigatorio ? " *" : ""), entrada, c.ajuda ? h("small", null, c.ajuda) : null, erroEl);
    }
    bloco._erro = erroEl;
    entradas[c.nome] = entrada;
    blocos[c.nome] = bloco;
    grade.append(bloco);
  }
  const form = h("form", { novalidate: true }, grade);
  const atualizarVisiveis = () => {
    let vals;
    try { vals = ler(true); } catch { return; }
    for (const c of campos) if (c.mostrarSe && blocos[c.nome]) blocos[c.nome].hidden = !c.mostrarSe(vals);
  };
  form.addEventListener("change", atualizarVisiveis);
  form.addEventListener("submit", (ev) => { ev.preventDefault(); aoEnviar?.(); });

  function ler(silencioso = false) {
    const dados = {};
    for (const c of campos) {
      if (c.secao || !entradas[c.nome]) continue;
      if (!silencioso && blocos[c.nome].hidden) continue;
      const v = lerEntrada(c, entradas[c.nome]);
      if (c.tipo === "senha" && !v) continue;
      if (c.tipo === "imagem" && v === undefined) continue;
      dados[c.nome] = v;
    }
    return dados;
  }

  function mostrarErros(erros) {
    alerta.hidden = true;
    for (const b of Object.values(blocos)) b._erro.textContent = "";
    if (!erros) return;
    if (typeof erros === "string") { alerta.textContent = erros; alerta.hidden = false; return; }
    const soltos = [];
    for (const [k, v] of Object.entries(erros)) {
      const msg = Array.isArray(v) ? v.join(" ") : typeof v === "object" ? JSON.stringify(v) : String(v);
      if (blocos[k] && !blocos[k].hidden) blocos[k]._erro.textContent = msg;
      else soltos.push(k === "detail" || k === "non_field_errors" ? msg : `${k}: ${msg}`);
    }
    if (soltos.length) { alerta.textContent = soltos.join(" · "); alerta.hidden = false; }
    form.querySelector(".erro:not(:empty), .alerta:not([hidden])")?.scrollIntoView({ block: "nearest" });
  }

  atualizarVisiveis();
  return { el: form, ler, mostrarErros, entradas };
}
