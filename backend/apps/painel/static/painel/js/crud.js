// Página de cadastro genérica: lista + busca + formulário em modal.
import { del, ehGerente, ErroApi, lista, patch, post } from "./api.js";
import { formulario, limparCacheFk } from "./form.js";
import { aviso, botaoAcao, carregando, confirmar, erro, h, modal, tabela, trocar } from "./ui.js";

/**
 * cfg = {
 *   titulo, singular, url, params, colunas, campos, busca: ["nome", ...],
 *   podeCriar(), podeEditar(l), podeExcluir(l), novo: {...},
 *   antesDeSalvar(dados, obj), depoisDeSalvar(obj, ehNovo), acoes(l, recarregar), extras(obj, recarregar),
 *   filtros: [{nome, rotulo, opcoes:[{valor, rotulo}]}], ordenar(a, b), textoExcluir, topo(recarregar)
 * }
 */
export function paginaCadastro(cfg) {
  return {
    titulo: cfg.titulo,
    async render(raiz) {
      const podeCriar = cfg.podeCriar ? cfg.podeCriar() : ehGerente();
      const filtrosAtivos = {};
      let termo = "";
      let itens = [];
      const corpo = h("div", null, carregando());
      const busca = cfg.busca ? h("input", { type: "search", placeholder: "Buscar…", "aria-label": "Buscar" }) : null;
      busca?.addEventListener("input", () => { termo = busca.value.trim().toLowerCase(); desenhar(); });
      const filtros = (cfg.filtros || []).map((f) => {
        const sel = h("select", { "aria-label": f.rotulo },
          h("option", { value: "" }, f.rotulo), (f.opcoes || []).map((o) => h("option", { value: o.valor }, o.rotulo)));
        if (f.url) lista(f.url).then((xs) => xs.forEach((x) => sel.append(h("option", { value: x.id }, x.nome)))).catch(() => {});
        if (f.padrao !== undefined) { sel.value = f.padrao; filtrosAtivos[f.nome] = f.padrao; }
        sel.addEventListener("change", () => { filtrosAtivos[f.nome] = sel.value; carregar(); });
        return sel;
      });
      const barra = h("div", { class: "barra-ferramentas" }, busca, filtros, cfg.topo ? cfg.topo(carregar) : null,
        h("span", { class: "espaco" }),
        podeCriar ? h("button", { class: "botao botao-primario", type: "button", onclick: () => abrir(null) },
          `+ ${cfg.textoNovo || "Novo"}`) : null);
      trocar(raiz, cfg.intro ? h("p", { class: "muted" }, cfg.intro) : null, barra, corpo);

      function filtrados() {
        let r = itens;
        if (termo && cfg.busca) {
          r = r.filter((l) => cfg.busca.some((c) => String(typeof c === "function" ? c(l) : l[c] ?? "").toLowerCase().includes(termo)));
        }
        if (cfg.filtroLocal) r = r.filter((l) => cfg.filtroLocal(l, filtrosAtivos));
        return cfg.ordenar ? [...r].sort(cfg.ordenar) : r;
      }

      function desenhar() {
        const colunas = [...cfg.colunas];
        if (cfg.acoes || cfg.podeExcluir) {
          colunas.push({
            rotulo: "", classe: "acoes-linha", valor: (l) => h("div", { class: "acoes acoes-fim" },
              cfg.acoes ? cfg.acoes(l, carregar) : null,
              cfg.podeExcluir && cfg.podeExcluir(l)
                ? botaoAcao(cfg.textoExcluir || "Excluir", () => excluir(l), "botao botao-pequeno botao-perigo") : null),
          });
        }
        trocar(corpo, tabela(colunas, filtrados(), {
          aoClicar: (l) => abrir(l),
          vazio: termo ? "Nada encontrado." : cfg.vazio || "Nenhum cadastro ainda.",
        }));
      }

      async function carregar() {
        try {
          const params = { ...(cfg.params || {}) };
          for (const [k, v] of Object.entries(filtrosAtivos)) if (v !== "" && !(cfg.filtros || []).find((f) => f.nome === k)?.local) params[k] = v;
          itens = await lista(cfg.url, params);
          desenhar();
        } catch (e) { trocar(corpo, h("div", { class: "alerta alerta-erro" }, e.mensagem || String(e))); }
      }

      async function excluir(l) {
        const nome = l.nome || l.descricao || l.codigo || l.username || "este item";
        if (!(await confirmar(`Excluir "${nome}"?`, { ok: cfg.textoExcluir || "Excluir", perigo: true }))) return;
        await del(`${cfg.url}${l.id}/`);
        limparCacheFk();
        aviso("Excluído.", "ok");
        carregar();
      }

      function abrir(obj) {
        const editavel = obj ? (cfg.podeEditar ? cfg.podeEditar(obj) : ehGerente()) : true;
        const valores = obj ? { ...obj } : { ...(cfg.novo || {}) };
        const campos = (typeof cfg.campos === "function" ? cfg.campos(obj) : cfg.campos)
          .filter((c) => !(obj && c.somenteNovo) && !(!obj && c.somenteEdicao));
        let m;
        const f = formulario(campos, valores, { aoEnviar: () => salvarBtn.click() });
        if (!editavel) f.el.querySelectorAll("input,select,textarea,button").forEach((x) => { x.disabled = true; });
        const salvarBtn = botaoAcao("Salvar", async () => {
          let dados;
          try { dados = f.ler(); } catch (e) { f.mostrarErros(e.message); return; }
          const imagens = {};
          for (const c of campos) if (c.tipo === "imagem" && dados[c.nome] instanceof File) { imagens[c.nome] = dados[c.nome]; delete dados[c.nome]; }
          if (cfg.antesDeSalvar) dados = await cfg.antesDeSalvar(dados, obj);
          try {
            let salvo = obj ? await patch(`${cfg.url}${obj.id}/`, dados) : await post(cfg.url, dados);
            if (Object.keys(imagens).length) {
              const fd = new FormData();
              for (const [k, v] of Object.entries(imagens)) fd.append(k, v);
              salvo = await patch(`${cfg.url}${salvo.id}/`, fd);
            }
            limparCacheFk();
            await cfg.depoisDeSalvar?.(salvo, !obj);
            aviso(obj ? "Alterações salvas." : `${cfg.singular || "Cadastro"} criado.`, "ok");
            m.fechar();
            carregar();
            if (!obj && cfg.extras) abrir(salvo); // continua editando (ex.: variações do produto)
          } catch (e) {
            if (e instanceof ErroApi && e.status === 400) f.mostrarErros(e.dados);
            else erro(e);
          }
        }, "botao botao-primario");
        const extras = obj && cfg.extras ? h("div", { style: { marginTop: "20px" } }, cfg.extras(obj, carregar)) : null;
        m = modal({
          titulo: obj ? `${cfg.singular || "Cadastro"}: ${cfg.nomeDe ? cfg.nomeDe(obj) : obj.nome || obj.username || obj.descricao || ""}` : `Novo ${(cfg.singular || "cadastro").toLowerCase()}`,
          corpo: [f.el, extras],
          rodape: editavel ? [h("button", { class: "botao", type: "button", onclick: () => m.fechar() }, "Cancelar"), salvarBtn]
            : [h("span", { class: "muted" }, "Somente leitura para o seu perfil.")],
          tamanho: cfg.modalGrande ? "modal-grande" : "",
        });
      }

      await carregar();
      if (cfg.abrirNovo) abrir(null);
    },
  };
}
