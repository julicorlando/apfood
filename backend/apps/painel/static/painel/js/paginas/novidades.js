// Combos, importar cardápio (foto/PDF/texto), lista de compras pelo estoque mínimo e tempo por etapa.
import { del, get, lista, post, put } from "../api.js";
import {
  aviso, barras, botaoAcao, centavos, confirmar, dinheiro, erro, h, kpi, modal, reais, tabela, trocar,
} from "../ui.js";
import { paginaRelatorio } from "./gestao.js";

// =============================================================================== combos
export function combos() {
  return {
    titulo: "Combos",
    async render(raiz) {
      const area = h("div");
      trocar(raiz,
        h("div", { class: "barra-ferramentas" },
          h("p", { class: "muted", style: { margin: 0 } }, "Combo com preço fechado: o cardápio mostra “de R$ X por R$ Y” e sugere o combo quando o cliente escolhe um dos itens. O estoque baixa cada item do combo."),
          h("span", { class: "espaco" }),
          botaoAcao("+ Novo combo", () => editar(null, carregar), "botao botao-primario")),
        area);
      async function carregar() {
        const cs = await get("/api/combos/");
        trocar(area, cs.length ? h("div", { class: "grade grade-cards" }, cs.map((c) => h("div", { class: "cartao" },
          h("div", { class: "pedido-topo" }, h("strong", null, c.nome), c.economia_centavos
            ? h("span", { class: "etiqueta e-ok" }, `economia ${dinheiro(c.economia_centavos)}`) : null),
          h("div", { class: "muted", style: { margin: "6px 0" } }, c.itens.map((i) => `${i.quantidade}x ${i.nome}`).join(" + ")),
          h("div", null, c.de_centavos > c.preco_centavos ? h("s", { class: "muted" }, dinheiro(c.de_centavos)) : null, " ",
            h("strong", { style: { fontSize: "18px" } }, dinheiro(c.preco_centavos))),
          h("div", { class: "muted" }, c.categoria),
          h("div", { class: "acoes", style: { marginTop: "10px" } },
            botaoAcao("Editar", () => editar(c, carregar), "botao botao-pequeno"),
            botaoAcao("Tirar do cardápio", async () => {
              if (!(await confirmar(`Tirar o combo “${c.nome}” do cardápio?`))) return;
              await del(`/api/combos/${c.id}/`); aviso("Combo removido.", "ok"); carregar();
            }, "botao botao-pequeno botao-perigo")))))
          : h("div", { class: "cartao vazio" }, "Nenhum combo ainda. Crie o primeiro: por exemplo, lanche + batata + refrigerante por um preço menor que separado."));
      }
      await carregar();
    },
  };
}

async function editar(c, recarregar) {
  const [produtos, categorias] = await Promise.all([lista("/api/produtos/", { tipo: "VENDA" }), lista("/api/categorias/")]);
  const vendaveis = produtos.filter((p) => p.ativo && (!c || p.id !== c.id));
  const nome = h("input", { type: "text", value: c?.nome || "", placeholder: "Ex.: Combo Smash" });
  const desc = h("input", { type: "text", value: c?.descricao || "", placeholder: "Opcional" });
  const preco = h("input", { type: "text", inputmode: "decimal", value: c ? reais(c.preco_centavos) : "", placeholder: "0,00" });
  const cat = h("select", null, h("option", { value: "" }, "Categoria “Combos” (cria se não existir)"),
    categorias.map((x) => h("option", { value: x.id, selected: c?.categoria_id === x.id }, x.nome)));
  const itens = (c?.itens || []).map((i) => ({ produto_id: i.produto_id, quantidade: i.quantidade }));
  const listaEl = h("div", { class: "grade", style: { gap: "6px" } });
  const resumo = h("div", { class: "alerta" });
  const precoDe = (pid) => (vendaveis.find((p) => p.id === pid) || {}).preco_centavos || 0;
  function desenhar() {
    trocar(listaEl, itens.length ? itens.map((it, i) => {
      const sel = h("select", null, vendaveis.map((p) => h("option", { value: p.id, selected: p.id === it.produto_id }, `${p.nome} — ${dinheiro(p.preco_centavos)}`)));
      sel.addEventListener("change", () => { it.produto_id = sel.value; atualizar(); });
      const qtd = h("input", { type: "number", min: "1", step: "1", value: it.quantidade, style: { width: "70px" } });
      qtd.addEventListener("input", () => { it.quantidade = Math.max(1, parseInt(qtd.value, 10) || 1); atualizar(); });
      return h("div", { class: "horarios-grade", style: { gridTemplateColumns: "1fr 80px auto" } }, sel, qtd,
        h("button", { type: "button", class: "botao botao-pequeno botao-perigo", onclick: () => { itens.splice(i, 1); desenhar(); } }, "Tirar"));
    }) : h("p", { class: "muted" }, "Adicione os itens que vêm no combo."));
    atualizar();
  }
  function atualizar() {
    const de = itens.reduce((s, it) => s + precoDe(it.produto_id) * it.quantidade, 0);
    const por = centavos(preco.value) || 0;
    trocar(resumo, itens.length < 2 ? "Escolha pelo menos 2 itens."
      : h("span", null, `Separado: ${dinheiro(de)} · No combo: ${dinheiro(por)} · `,
        h("strong", { style: { color: de - por > 0 ? "var(--ok)" : "var(--erro)" } }, de - por > 0 ? `cliente economiza ${dinheiro(de - por)}` : "sem economia")));
  }
  preco.addEventListener("input", atualizar);
  desenhar();
  const m = modal({
    titulo: c ? `Editar ${c.nome}` : "Novo combo",
    corpo: h("div", { class: "grade" },
      h("label", { class: "campo" }, h("span", null, "Nome *"), nome),
      h("label", { class: "campo" }, h("span", null, "Descrição"), desc),
      h("div", { class: "grade grade-2" },
        h("label", { class: "campo" }, h("span", null, "Preço do combo (R$) *"), preco),
        h("label", { class: "campo" }, h("span", null, "Categoria"), cat)),
      h("div", { class: "campo" }, h("span", null, "Itens do combo"), listaEl,
        h("div", { class: "acoes" }, h("button", { type: "button", class: "botao botao-pequeno", onclick: () => {
          if (!vendaveis.length) { erro("Cadastre produtos antes."); return; }
          itens.push({ produto_id: vendaveis[0].id, quantidade: 1 }); desenhar();
        } }, "+ Item"))),
      resumo,
      h("small", { class: "muted" }, "Foto e opções (ex.: escolher a bebida) ficam em Cardápio → Produtos, como em qualquer produto.")),
    rodape: [botaoAcao("Salvar combo", async () => {
      const corpo = { nome: nome.value, descricao: desc.value, preco_centavos: centavos(preco.value), categoria_id: cat.value || null, itens };
      if (c) await put(`/api/combos/${c.id}/`, corpo); else await post("/api/combos/", corpo);
      m.fechar(); aviso("Combo salvo.", "ok"); recarregar();
    }, "botao botao-primario")],
  });
}

// =============================================================================== importar cardápio
export function importarCardapio() {
  return {
    titulo: "Importar cardápio",
    async render(raiz) {
      const info = await get("/api/cardapio/importar/").catch(() => ({ ia: false }));
      const arquivo = h("input", { type: "file", accept: "image/*,application/pdf" });
      const texto = h("textarea", { rows: 8, placeholder: "LANCHES\nX-Burger 24,90\nPão, carne e queijo\nX-Bacon 28,90\n\nBEBIDAS\nRefrigerante lata 6,00" });
      const area = h("div");
      trocar(raiz,
        h("div", { class: "cartao", style: { marginBottom: "16px" } },
          h("h2", null, "1. Envie o cardápio"),
          h("p", { class: "muted" }, info.ia
            ? "Mande uma foto nítida ou o PDF do cardápio: a IA lê categorias, produtos, descrições e preços. Você confere tudo antes de salvar."
            : "Mande o PDF do cardápio (com texto) ou cole o texto abaixo. Para ler fotos, peça para ligar a leitura por IA (APFOOD_ANTHROPIC_KEY no servidor)."),
          h("div", { class: "grade grade-2" },
            h("label", { class: "campo" }, h("span", null, info.ia ? "Foto ou PDF" : "PDF"), arquivo,
              botaoAcao("Ler arquivo", async () => {
                const f = arquivo.files[0];
                if (!f) { erro("Escolha o arquivo."); return; }
                const fd = new FormData(); fd.append("arquivo", f);
                trocar(area, h("div", { class: "carregando" }, "Lendo o cardápio… (pode levar até 1 minuto)"));
                try { previa(await post("/api/cardapio/importar/", fd)); } catch (e) { trocar(area); throw e; }
              }, "botao botao-primario")),
            h("label", { class: "campo" }, h("span", null, "Ou cole o texto (um produto com preço por linha)"), texto,
              botaoAcao("Ler texto", async () => previa(await post("/api/cardapio/importar/", { texto: texto.value })), "botao")))),
        area);

      function previa(r) {
        const cats = r.categorias.map((c) => ({ ...c, marcada: true, produtos: c.produtos.map((p) => ({ ...p, marcado: true })) }));
        const total = () => cats.reduce((s, c) => s + (c.marcada ? c.produtos.filter((p) => p.marcado).length : 0), 0);
        const contador = h("strong");
        const atualizarContador = () => { contador.textContent = `${total()} produto(s) para importar`; };
        trocar(area, h("div", { class: "cartao" },
          h("h2", null, "2. Confira e ajuste"),
          h("p", { class: "muted" }, "Corrija nomes e preços, desmarque o que não quer. Produto com o mesmo nome na mesma categoria não é duplicado."),
          ...cats.map((c) => {
            const marcaCat = h("input", { type: "checkbox", checked: true, onchange: () => { c.marcada = marcaCat.checked; atualizarContador(); } });
            const nomeCat = h("input", { type: "text", value: c.nome, oninput: () => { c.nome = nomeCat.value; } });
            return h("div", { style: { margin: "14px 0" } },
              h("div", { class: "acoes" }, marcaCat, nomeCat),
              tabela([
                { rotulo: "", valor: (p) => h("input", { type: "checkbox", checked: p.marcado, onchange: (ev) => { p.marcado = ev.target.checked; atualizarContador(); } }) },
                { rotulo: "Produto", valor: (p) => h("input", { type: "text", value: p.nome, oninput: (ev) => { p.nome = ev.target.value; } }) },
                { rotulo: "Descrição", valor: (p) => h("input", { type: "text", value: p.descricao, oninput: (ev) => { p.descricao = ev.target.value; } }) },
                { rotulo: "Preço (R$)", classe: "num", valor: (p) => h("input", { type: "text", inputmode: "decimal", value: reais(p.preco_centavos), style: { width: "100px" },
                  oninput: (ev) => { p.preco_centavos = centavos(ev.target.value) || 0; } }) },
              ], c.produtos));
          }),
          h("div", { class: "acoes" }, contador, h("span", { class: "espaco" }),
            botaoAcao("Importar para o cardápio", async () => {
              const corpo = cats.filter((c) => c.marcada).map((c) => ({ nome: c.nome, produtos: c.produtos.filter((p) => p.marcado) }))
                .filter((c) => c.produtos.length);
              const res = await post("/api/cardapio/importar/confirmar/", { categorias: corpo });
              aviso(`Pronto: ${res.produtos} produto(s) e ${res.categorias} categoria(s) novas. Adicione fotos em Cardápio → Produtos.`, "ok");
              trocar(area);
            }, "botao botao-primario"))));
        atualizarContador();
      }
    },
  };
}

// =============================================================================== lista de compras
export function listaCompras() {
  return {
    titulo: "Lista de compras",
    async render(raiz) {
      const area = h("div");
      trocar(raiz, h("p", { class: "muted" }, "Itens com estoque no mínimo ou abaixo (e os que estão quase lá), com a quantidade para voltar ao dobro do mínimo. "
        + "Agrupados pelo último fornecedor de cada item. Defina o estoque mínimo em Cardápio → Insumos / Produtos."), area);
      async function carregar() {
        const r = await get("/api/estoque/lista-compras/");
        if (!r.itens) { trocar(area, h("div", { class: "cartao vazio" }, "✅ Nada para comprar: todo o estoque está acima do mínimo.")); return; }
        trocar(area, ...r.grupos.map((g) => {
          const qtds = {};
          g.itens.forEach((i) => { qtds[i.produto_id] = i.sugerido; });
          const texto = () => `Pedido de compra — ${g.fornecedor}\n` + g.itens.map((i) => `• ${i.nome}: ${qtds[i.produto_id]} ${i.unidade}`).join("\n");
          const tel = (g.telefone || "").replace(/\D/g, "");
          return h("div", { class: "cartao", style: { marginBottom: "16px" } },
            h("div", { class: "pedido-topo" }, h("h2", { style: { margin: 0 } }, `🚚 ${g.fornecedor}`),
              h("span", { class: "muted" }, `≈ ${dinheiro(g.total_estimado_centavos)}`)),
            tabela([
              { rotulo: "Item", valor: (i) => h("strong", null, i.nome) },
              { rotulo: "Situação", valor: (i) => h("span", { class: `etiqueta ${i.situacao === "quase" ? "e-alerta" : "e-erro"}` },
                i.situacao === "acabou" ? "Acabou" : i.situacao === "abaixo" ? "Abaixo do mínimo" : "Quase no mínimo") },
              { rotulo: "Tem", classe: "num", valor: (i) => `${i.estoque_atual} ${i.unidade}` },
              { rotulo: "Mínimo", classe: "num", valor: (i) => `${i.estoque_minimo} ${i.unidade}` },
              { rotulo: "Comprar", classe: "num", valor: (i) => h("input", { type: "number", min: "0", step: "any", value: i.sugerido, style: { width: "90px" },
                oninput: (ev) => { qtds[i.produto_id] = ev.target.value; } }) },
            ], g.itens),
            h("div", { class: "acoes", style: { marginTop: "10px" } },
              botaoAcao("📋 Copiar lista", async () => { await navigator.clipboard.writeText(texto()); aviso("Lista copiada.", "ok"); }, "botao"),
              tel ? h("a", { class: "botao", target: "_blank", rel: "noopener", href: `https://wa.me/${tel.length <= 11 ? "55" + tel : tel}?text=${encodeURIComponent(texto())}`,
                onclick: (ev) => { ev.currentTarget.href = `https://wa.me/${tel.length <= 11 ? "55" + tel : tel}?text=${encodeURIComponent(texto())}`; } }, "💬 Mandar no WhatsApp") : null,
              h("span", { class: "espaco" }),
              botaoAcao("Criar compra (rascunho)", async () => {
                const itens = g.itens.map((i) => ({ produto_id: i.produto_id, quantidade: qtds[i.produto_id] })).filter((i) => Number(i.quantidade) > 0);
                await post("/api/estoque/lista-compras/", { fornecedor_id: g.fornecedor_id, itens });
                aviso("Compra criada em rascunho. Confira e lance quando a mercadoria chegar (Estoque e compras → Compras).", "ok");
              }, "botao botao-primario")));
        }));
      }
      await carregar();
    },
  };
}

// =============================================================================== tempo por etapa
const ROTULO_ETAPA = { aceite: "Aceitar", preparo: "Preparo", espera_entregador: "Esperando entregador", entrega: "Entrega", retirada: "Cliente retirar" };

export function tempos() {
  return paginaRelatorio("Tempo por etapa", async (area, q) => {
    const r = await get(`/api/relatorios/tempos/?${q}`);
    const min = (v) => (v === null || v === undefined ? "—" : `${String(v).replace(".", ",")} min`);
    if (!r.pedidos) { trocar(area, h("div", { class: "cartao vazio" }, "Nenhum pedido concluído no período.")); return; }
    const etapas = r.etapas.filter((e) => e.pedidos);
    const g = r.etapas.find((e) => e.etapa === r.gargalo);
    trocar(area,
      h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
        kpi("Tempo total médio", min(r.total?.media_min), `${r.pedidos} pedido(s) · 90% em até ${min(r.total?.p90_min)}`),
        ...etapas.map((e) => kpi(e.rotulo, min(e.media_min), `90% em até ${min(e.p90_min)}`))),
      g ? h("div", { class: `alerta ${g.etapa === "preparo" && g.media_min > r.meta_preparo_min ? "alerta-erro" : "alerta-aviso"}`, style: { marginBottom: "16px" } },
        `⏱️ Onde mais demora: ${g.rotulo.toLowerCase()} (${min(g.media_min)} em média).`,
        g.etapa === "aceite" ? " Dica: ligue o aceite automático em Dados da loja." : "",
        g.etapa === "preparo" ? ` A meta de preparo da loja é ${r.meta_preparo_min} min.` : "",
        g.etapa === "espera_entregador" ? " Dica: chame o entregador pelo app assim que começar o preparo." : "") : null,
      h("div", { class: "grade grade-2", style: { marginBottom: "16px" } },
        h("div", { class: "cartao" }, h("h2", null, "Tempo médio por etapa"),
          barras(etapas.map((e) => ({ rotulo: ROTULO_ETAPA[e.etapa], valor: e.media_min })), { dica: (p) => `${p.rotulo}: ${min(p.valor)}` })),
        h("div", { class: "cartao" }, h("h2", null, "Tempo total por horário do pedido"),
          barras(r.por_hora.map((x) => ({ rotulo: `${x.hora}h`, valor: x.media_min, n: x.pedidos })), { dica: (p) => `${p.rotulo}: ${min(p.valor)} (${p.n} pedidos)` }))),
      h("div", { class: "cartao" }, h("h2", null, "Pedidos mais demorados"),
        tabela([
          { rotulo: "Pedido", valor: (x) => h("strong", null, `#${x.numero}`) },
          { rotulo: "Tipo", valor: (x) => ({ ENTREGA: "Entrega", RETIRADA: "Retirada", CONSUMO_LOCAL: "Balcão/mesa" }[x.tipo] || x.tipo) },
          ...Object.keys(ROTULO_ETAPA).map((k) => ({ rotulo: ROTULO_ETAPA[k], classe: "num", valor: (x) => min(x.etapas[k]) })),
          { rotulo: "Total", classe: "num", valor: (x) => h("strong", null, min(x.total_min)) },
        ], r.mais_lentos)));
  });
}
