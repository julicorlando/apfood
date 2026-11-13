// Estoque, compras, financeiro e relatórios.
import { ehGerente, get, lista, patch, post } from "../api.js";
import { paginaCadastro } from "../crud.js";
import {
  abas, aviso, barras, botaoAcao, centavos, data, dataHora, dinheiro, erro, etiqueta, etiquetaStatus, h, hojeISO, kpi, modal, pedirTexto, rotulo, tabela, trocar,
} from "../ui.js";
import { imprimirLinhas, mostrarCupom } from "./comum.js";

// ---------------------------------------------------------------- período
function seletorPeriodo(aoMudar) {
  const sel = h("select", { "aria-label": "Período" },
    [["dia", "Hoje"], ["ontem", "Ontem"], ["semana", "Esta semana"], ["7d", "Últimos 7 dias"], ["mes", "Este mês"], ["30d", "Últimos 30 dias"], ["custom", "Escolher datas…"]]
      .map(([v, r]) => h("option", { value: v }, r)));
  const ini = h("input", { type: "date", value: hojeISO(-6), hidden: true, style: { maxWidth: "160px" } });
  const fim = h("input", { type: "date", value: hojeISO(), hidden: true, style: { maxWidth: "160px" } });
  const params = () => {
    const v = sel.value;
    if (v === "ontem") return `inicio=${hojeISO(-1)}&fim=${hojeISO(-1)}`;
    if (v === "7d") return `inicio=${hojeISO(-6)}&fim=${hojeISO()}`;
    if (v === "30d") return `inicio=${hojeISO(-29)}&fim=${hojeISO()}`;
    if (v === "custom") return `inicio=${ini.value}&fim=${fim.value}`;
    return `periodo=${v}`;
  };
  sel.addEventListener("change", () => { ini.hidden = fim.hidden = sel.value !== "custom"; aoMudar(); });
  ini.addEventListener("change", aoMudar);
  fim.addEventListener("change", aoMudar);
  return { el: [sel, ini, fim], params };
}

function paginaRelatorio(titulo, desenhar) {
  return {
    titulo,
    async render(raiz) {
      const area = h("div");
      const p = seletorPeriodo(() => carregar());
      const imprimir = h("button", { type: "button", class: "botao", onclick: () => window.print() }, "Imprimir");
      trocar(raiz, h("div", { class: "barra-ferramentas" }, p.el, h("span", { class: "espaco" }), imprimir), area);
      async function carregar() {
        trocar(area, h("div", { class: "carregando" }, "Carregando…"));
        try { await desenhar(area, p.params()); } catch (e) { trocar(area, h("div", { class: "alerta alerta-erro" }, e.mensagem || String(e))); }
      }
      await carregar();
    },
  };
}

// ---------------------------------------------------------------- relatórios
export function vendas() {
  return paginaRelatorio("Vendas", async (area, q) => {
    const r = await get(`/api/relatorios/vendas/?${q}`);
    trocar(area, 
      h("p", { class: "muted" }, `De ${data(r.inicio)} a ${data(r.fim)} · somente pedidos concluídos`),
      h("div", { class: "grade grade-kpi" },
        kpi("Faturamento", dinheiro(r.faturamento_centavos)), kpi("Pedidos", String(r.pedidos)),
        kpi("Ticket médio", dinheiro(r.ticket_medio_centavos)), kpi("Taxas de entrega", dinheiro(r.taxas_entrega_centavos)),
        kpi("Descontos", dinheiro(r.descontos_centavos)), kpi("Cancelados", String(r.cancelados))),
      r.por_dia.length > 1 ? h("div", { class: "cartao", style: { marginTop: "16px" } }, h("h2", null, "Por dia"),
        barras(r.por_dia.map((d) => ({ rotulo: data(d.data).slice(0, 5), valor: d.faturamento_centavos, n: d.pedidos })), { dica: (p) => `${dinheiro(p.valor)} · ${p.n} pedidos` })) : null,
      h("div", { class: "grade grade-2", style: { marginTop: "16px" } },
        h("div", null, h("h2", null, "Por canal"), tabela([
          { rotulo: "Canal", valor: (c) => rotulo("CanalVenda", c.canal) },
          { rotulo: "Pedidos", classe: "num", campo: "pedidos" },
          { rotulo: "Faturamento", classe: "num", valor: (c) => dinheiro(c.faturamento_centavos) },
          { rotulo: "%", classe: "num", valor: (c) => `${c.percentual}%` },
        ], r.por_canal, { vazio: "Sem vendas no período." })),
        h("div", null, h("h2", null, "Por forma de pagamento"), tabela([
          { rotulo: "Forma", valor: (f) => rotulo("FormaPagamento", f.forma) },
          { rotulo: "Qtd", classe: "num", campo: "quantidade" },
          { rotulo: "Bruto", classe: "num", valor: (f) => dinheiro(f.bruto_centavos) },
          { rotulo: "Taxas", classe: "num", valor: (f) => dinheiro(f.taxas_centavos) },
          { rotulo: "Líquido", classe: "num", valor: (f) => dinheiro(f.liquido_centavos) },
        ], r.por_forma_pagamento, { vazio: "Sem pagamentos no período." }))));
  });
}

export function curvaAbc() {
  return paginaRelatorio("Curva ABC", async (area, q) => {
    const r = await get(`/api/relatorios/curva-abc/?${q}`);
    const cor = { A: "e-ok", B: "e-alerta", C: "" };
    trocar(area, 
      h("p", { class: "muted" }, "Classe A: produtos que somam 80% do faturamento; B: os próximos 15%; C: o restante."),
      tabela([
        { rotulo: "Classe", valor: (l) => etiqueta(l.classe, cor[l.classe]) },
        { rotulo: "Produto", campo: "nome" },
        { rotulo: "Qtd", classe: "num", campo: "quantidade" },
        { rotulo: "Faturamento", classe: "num", valor: (l) => dinheiro(l.faturamento_centavos) },
        { rotulo: "%", classe: "num", valor: (l) => `${Number(l.percentual).toFixed(1)}%` },
        { rotulo: "Acumulado", classe: "num", valor: (l) => `${Number(l.acumulado).toFixed(1)}%` },
      ], r.itens, { vazio: "Sem vendas no período." }));
  });
}

export function fechamentos() {
  return paginaRelatorio("Fechamentos de caixa", async (area, q) => {
    const r = await get(`/api/relatorios/fechamentos/?${q}`);
    const dif = (v) => h("span", { class: v ? (v > 0 ? "etiqueta e-info" : "etiqueta e-erro") : "etiqueta e-ok" }, v ? dinheiro(v) : "ok");
    trocar(area, 
      h("h2", null, "Por operador"),
      tabela([
        { rotulo: "Operador", campo: "operador" },
        { rotulo: "Caixas", classe: "num", campo: "turnos" },
        { rotulo: "Diferença acumulada", classe: "num", valor: (o) => dif(o.diferenca_centavos) },
      ], r.por_operador, { vazio: "Nenhum caixa fechado no período." }),
      h("h2", { style: { marginTop: "20px" } }, "Caixas fechados"),
      tabela([
        { rotulo: "Fechado em", valor: (t) => dataHora(t.fechado_em) },
        { rotulo: "Operador", campo: "operador" },
        { rotulo: "Esperado", classe: "num", valor: (t) => dinheiro(t.total_esperado_centavos) },
        { rotulo: "Informado", classe: "num", valor: (t) => dinheiro(t.total_informado_centavos) },
        { rotulo: "Diferença", classe: "num", valor: (t) => dif(t.diferenca_centavos) },
        { rotulo: "", classe: "acoes-linha", valor: (t) => botaoAcao("Cupom", async () => {
          const c = await get(`/api/turnos/${t.id}/cupom/`);
          mostrarCupom(c.linhas, { titulo: "Fechamento de caixa" });
        }, "botao botao-pequeno") },
      ], r.turnos, { vazio: "Nenhum caixa fechado no período." }));
  });
}

export function fluxoCaixa() {
  return paginaRelatorio("Fluxo de caixa", async (area, q) => {
    const r = await get(`/api/relatorios/fluxo-caixa/?${q}`);
    trocar(area, 
      h("div", { class: "grade grade-kpi" },
        kpi("Entradas (líquidas)", dinheiro(r.total_entradas_liquidas_centavos)),
        kpi("Saídas", dinheiro(r.total_saidas_centavos)),
        kpi("Saldo do período", dinheiro(r.total_entradas_liquidas_centavos - r.total_saidas_centavos)),
        kpi("A receber (cartões)", dinheiro(r.a_receber_centavos)),
        kpi("Contas a pagar em aberto", dinheiro(r.a_pagar_centavos))),
      h("div", { style: { marginTop: "16px" } }, tabela([
        { rotulo: "Dia", valor: (d) => data(d.data) },
        { rotulo: "Entradas", classe: "num", valor: (d) => dinheiro(d.entradas_brutas_centavos) },
        { rotulo: "Taxas", classe: "num", valor: (d) => dinheiro(d.taxas_centavos) },
        { rotulo: "Saídas", classe: "num", valor: (d) => dinheiro(d.saidas_centavos) },
        { rotulo: "Saldo", classe: "num", valor: (d) => h("span", { class: d.saldo_centavos < 0 ? "etiqueta e-erro" : "" }, dinheiro(d.saldo_centavos)) },
      ], r.dias.filter((d) => d.entradas_brutas_centavos || d.saidas_centavos), { vazio: "Sem movimento no período." })));
  });
}

// ---------------------------------------------------------------- notas fiscais
export function notas() {
  return {
    titulo: "Notas fiscais",
    async render(raiz) {
      const area = h("div");
      const st = h("select", { "aria-label": "Situação" }, h("option", { value: "" }, "Todas"),
        ["AUTORIZADA", "PROCESSANDO", "REJEITADA", "CANCELADA"].map((s) => h("option", { value: s }, rotulo("StatusNotaFiscal", s))));
      st.addEventListener("change", carregar);
      trocar(raiz, h("div", { class: "barra-ferramentas" }, st), area);
      async function carregar() {
        const ns = await lista("/api/notas-fiscais/", { status: st.value });
        trocar(area, tabela([
          { rotulo: "Emissão", valor: (n) => dataHora(n.autorizada_em || n.criado_em) },
          { rotulo: "Modelo", valor: (n) => rotulo("ModeloDocumentoFiscal", n.modelo) },
          { rotulo: "Número", valor: (n) => n.numero ? `${n.numero} / série ${n.serie}` : "—" },
          { rotulo: "Valor", classe: "num", valor: (n) => (n.valor_total_centavos != null ? dinheiro(n.valor_total_centavos) : "—") },
          { rotulo: "Situação", valor: (n) => etiquetaStatus("StatusNotaFiscal", n.status) },
          { rotulo: "Mensagem", valor: (n) => h("small", { class: "muted" }, n.mensagem_retorno || "") },
          { rotulo: "", classe: "acoes-linha", valor: (n) => h("div", { class: "acoes acoes-fim" },
            n.status === "AUTORIZADA" ? botaoAcao("DANFE", async () => {
              const r = await get(`/api/notas-fiscais/${n.id}/danfe/`);
              if (r.url_danfe && !r.linhas?.length) window.open(r.url_danfe, "_blank", "noopener");
              else imprimirLinhas(r.linhas);
            }, "botao botao-pequeno") : null,
            n.status === "REJEITADA" ? botaoAcao("Reemitir", async () => { await post(`/api/notas-fiscais/${n.id}/reemitir/`); aviso("Reenviada.", "ok"); carregar(); }, "botao botao-pequeno") : null,
            n.status === "AUTORIZADA" && ehGerente() ? botaoAcao("Cancelar", async () => {
              const j = await pedirTexto("Cancelar nota", { rotulo: "Justificativa (mínimo 15 caracteres)", minimo: 15, ok: "Cancelar nota" });
              if (!j) return;
              await post(`/api/notas-fiscais/${n.id}/cancelar/`, { justificativa: j });
              aviso("Cancelamento enviado.", "ok"); carregar();
            }, "botao botao-pequeno botao-perigo") : null) },
        ], ns, { vazio: "Nenhuma nota emitida. Sem emissor configurado, o sistema imprime comprovante não fiscal." }));
      }
      await carregar();
    },
  };
}

// ---------------------------------------------------------------- estoque
export function estoque() {
  return {
    titulo: "Estoque",
    async render(raiz) {
      const area = h("div");
      let aba = 0;
      const barra = abas([{ rotulo: "Saldos" }, { rotulo: "Abaixo do mínimo" }, { rotulo: "Movimentações" }], (_, i) => { aba = i; carregar(); });
      trocar(raiz, h("div", { class: "barra-ferramentas" }, h("span", { class: "espaco" }),
        h("button", { type: "button", class: "botao botao-primario", onclick: () => operacao(null, carregar) }, "+ Entrada / perda / inventário")), barra, area);

      async function carregar() {
        trocar(area, h("div", { class: "carregando" }, "Carregando…"));
        if (aba === 0) {
          const ps = (await lista("/api/produtos/", { controla_estoque: "true" })).sort((a, b) => a.nome.localeCompare(b.nome));
          trocar(area, tabela([
            { rotulo: "Item", campo: "nome" },
            { rotulo: "Tipo", valor: (p) => rotulo("TipoProduto", p.tipo) },
            { rotulo: "Saldo", classe: "num", valor: (p) => h("span", { class: p.abaixo_do_minimo ? "etiqueta e-erro" : "" }, `${Number(p.estoque_atual)} ${p.unidade}`) },
            { rotulo: "Mínimo", classe: "num", valor: (p) => (p.estoque_minimo != null ? `${Number(p.estoque_minimo)}` : "—") },
            { rotulo: "Custo médio", classe: "num", valor: (p) => dinheiro(p.custo_centavos) },
            { rotulo: "", classe: "acoes-linha", valor: (p) => h("div", { class: "acoes acoes-fim" },
              h("button", { type: "button", class: "botao botao-pequeno", onclick: () => operacao(p, carregar) }, "Movimentar"),
              h("button", { type: "button", class: "botao botao-pequeno", onclick: () => kardex(p) }, "Histórico")) },
          ], ps, { vazio: "Nenhum item controla estoque. Marque \"Controla estoque\" no cadastro do produto ou insumo." }));
        } else if (aba === 1) {
          const ps = await get("/api/estoque/abaixo-do-minimo/");
          trocar(area, tabela([
            { rotulo: "Item", campo: "nome" },
            { rotulo: "Saldo", classe: "num", valor: (p) => h("span", { class: "etiqueta e-erro" }, `${Number(p.estoque_atual)} ${p.unidade}`) },
            { rotulo: "Mínimo", classe: "num", valor: (p) => `${Number(p.estoque_minimo)} ${p.unidade}` },
          ], ps, { vazio: "Tudo acima do mínimo. 👍" }));
        } else {
          const ms = await get("/api/estoque/?limit=200");
          const itens = ms.results || ms;
          trocar(area, tabelaMovs(itens));
        }
      }
      await carregar();
    },
  };
}

function tabelaMovs(itens) {
  return tabela([
    { rotulo: "Quando", valor: (m) => dataHora(m.criado_em) },
    { rotulo: "Item", campo: "produto_nome" },
    { rotulo: "Movimento", valor: (m) => rotulo("TipoMovimentacaoEstoque", m.tipo) },
    { rotulo: "Quantidade", classe: "num", valor: (m) => h("span", { class: Number(m.quantidade) < 0 ? "etiqueta e-erro" : "etiqueta e-ok" }, String(Number(m.quantidade))) },
    { rotulo: "Saldo depois", classe: "num", valor: (m) => String(Number(m.saldo_posterior)) },
    { rotulo: "Motivo", campo: "motivo" },
  ], itens, { vazio: "Sem movimentações." });
}

async function kardex(p) {
  const ms = await get(`/api/estoque/?produto=${p.id}&limit=200`);
  modal({ titulo: `Histórico — ${p.nome}`, corpo: tabelaMovs(ms.results || ms), tamanho: "modal-grande" });
}

async function operacao(produto, recarregar) {
  const ps = produto ? [produto] : (await lista("/api/produtos/", { controla_estoque: "true" })).sort((a, b) => a.nome.localeCompare(b.nome));
  const sel = h("select", null, ps.map((p) => h("option", { value: p.id }, `${p.nome} (${p.unidade})`)));
  const op = h("select", null, [["ENTRADA", "Entrada (compra avulsa)"], ["PERDA", "Perda / quebra"], ["INVENTARIO", "Inventário (saldo contado)"]].map(([v, r]) => h("option", { value: v }, r)));
  const qtd = h("input", { type: "number", step: "0.001" });
  const custo = h("input", { type: "text", inputmode: "decimal", placeholder: "Opcional" });
  const motivo = h("input", { type: "text" });
  const blocoCusto = h("label", { class: "campo" }, h("span", null, "Custo unitário (R$)"), custo);
  const rotQtd = h("span", null, "Quantidade");
  op.addEventListener("change", () => { blocoCusto.hidden = op.value !== "ENTRADA"; rotQtd.textContent = op.value === "INVENTARIO" ? "Saldo contado" : "Quantidade"; });
  if (!ps.length) { aviso("Nenhum item controla estoque.", "erro"); return; }
  const m = modal({
    titulo: "Movimentar estoque", tamanho: "modal-pequeno",
    corpo: h("div", { class: "grade" },
      h("label", { class: "campo" }, h("span", null, "Item"), sel), h("label", { class: "campo" }, h("span", null, "Operação"), op),
      h("label", { class: "campo" }, rotQtd, qtd), blocoCusto, h("label", { class: "campo" }, h("span", null, "Motivo"), motivo)),
    rodape: [botaoAcao("Registrar", async () => {
      if (!qtd.value) { aviso("Informe a quantidade.", "erro"); return; }
      const r = await post("/api/estoque/operacao/", {
        produto: sel.value, operacao: op.value, quantidade: qtd.value, motivo: motivo.value.trim(),
        custo_unitario_centavos: op.value === "ENTRADA" && custo.value ? centavos(custo.value) : null,
      });
      aviso(r.detail || "Estoque atualizado.", "ok");
      m.fechar(); recarregar();
    }, "botao botao-primario")],
  });
}

// ---------------------------------------------------------------- compras
export function compras() {
  return paginaCadastro({
    titulo: "Compras", singular: "Compra", textoNovo: "Nova compra", url: "/api/compras/",
    intro: "Lance a nota do fornecedor: ao confirmar, os itens entram no estoque (com custo médio) e a conta a pagar é criada.",
    podeCriar: () => ehGerente(), podeEditar: (c) => c.status === "RASCUNHO",
    nomeDe: (c) => c.numero_nota ? `NF ${c.numero_nota}` : data(c.data_entrada),
    filtros: [{ nome: "status", rotulo: "Todas", opcoes: [{ valor: "RASCUNHO", rotulo: "Rascunho" }, { valor: "LANCADA", rotulo: "Lançada" }, { valor: "CANCELADA", rotulo: "Cancelada" }] }],
    novo: { data_entrada: hojeISO(), itens: [] },
    colunas: [
      { rotulo: "Entrada", valor: (c) => data(c.data_entrada) },
      { rotulo: "Nota", valor: (c) => c.numero_nota || "—" },
      { rotulo: "Itens", classe: "num", valor: (c) => String(c.itens?.length || 0) },
      { rotulo: "Total", classe: "num", valor: (c) => dinheiro(c.total_centavos) },
      { rotulo: "Vencimento", valor: (c) => data(c.vencimento) || "—" },
      { rotulo: "Situação", valor: (c) => etiquetaStatus("StatusCompra", c.status) },
    ],
    campos: [
      { nome: "fornecedor", rotulo: "Fornecedor", tipo: "fk", url: "/api/fornecedores/" },
      { nome: "data_entrada", rotulo: "Data de entrada", tipo: "data", obrigatorio: true },
      { nome: "numero_nota", rotulo: "Número da nota" },
      { nome: "data_emissao", rotulo: "Emissão da nota", tipo: "data" },
      { nome: "vencimento", rotulo: "Vencimento (gera conta a pagar)", tipo: "data" },
      { nome: "frete_centavos", rotulo: "Frete (R$)", tipo: "dinheiro" },
      { nome: "desconto_centavos", rotulo: "Desconto (R$)", tipo: "dinheiro" },
      { nome: "observacao", rotulo: "Observação", tipo: "textarea" },
    ],
    antesDeSalvar: (d, obj) => ({ ...d, itens: (obj?.itens || []).map(({ id, ...i }) => i) }),
    acoes: (c, recarregar) => h("div", { class: "acoes" },
      c.status === "RASCUNHO" ? botaoAcao("Itens", () => itensCompra(c, recarregar), "botao botao-pequeno") : null,
      c.status === "RASCUNHO" && c.itens?.length ? botaoAcao("Lançar no estoque", async () => {
        await post(`/api/compras/${c.id}/lancar/`);
        aviso("Compra lançada: estoque e conta a pagar atualizados.", "ok"); recarregar();
      }, "botao botao-pequeno botao-ok") : null,
      c.status !== "CANCELADA" ? botaoAcao("Cancelar", async () => {
        const motivo = await pedirTexto("Cancelar compra", { rotulo: "Motivo", ok: "Cancelar compra" });
        if (!motivo) return;
        await post(`/api/compras/${c.id}/cancelar/`, { motivo });
        recarregar();
      }, "botao botao-pequeno botao-perigo") : null),
    depoisDeSalvar: (c, novo) => { if (novo) setTimeout(() => itensCompra(c, () => window.dispatchEvent(new HashChangeEvent("hashchange"))), 50); },
  });
}

async function itensCompra(compra, recarregar) {
  const produtos = (await lista("/api/produtos/", { controla_estoque: "true" })).sort((a, b) => a.nome.localeCompare(b.nome));
  const itens = (compra.itens || []).map(({ id, ...i }) => ({ ...i, produto: String(i.produto) }));
  const listaEl = h("div");
  const total = h("strong");
  const nome = (id) => produtos.find((p) => p.id === id)?.nome || "?";
  const desenhar = () => {
    trocar(listaEl, tabela([
      { rotulo: "Item", valor: (i) => nome(i.produto) },
      { rotulo: "Qtd", classe: "num", valor: (i) => `${Number(i.quantidade)}${Number(i.fator_conversao) !== 1 ? ` × ${Number(i.fator_conversao)}` : ""}` },
      { rotulo: "Custo un.", classe: "num", valor: (i) => dinheiro(i.custo_unitario_centavos) },
      { rotulo: "Total", classe: "num", valor: (i) => dinheiro(i.total_centavos) },
      { rotulo: "", classe: "acoes-linha", valor: (i) => h("button", { type: "button", class: "botao botao-pequeno botao-perigo", onclick: () => { itens.splice(itens.indexOf(i), 1); desenhar(); } }, "Tirar") },
    ], itens, { vazio: "Nenhum item." }));
    total.textContent = dinheiro(itens.reduce((s, i) => s + i.total_centavos, 0));
  };
  const sel = h("select", null, produtos.map((p) => h("option", { value: p.id }, `${p.nome} (${p.unidade})`)));
  const qtd = h("input", { type: "number", step: "0.001", placeholder: "Qtd", style: { maxWidth: "100px" } });
  const fator = h("input", { type: "number", step: "0.001", value: "1", title: "Unidades de estoque por unidade comprada (caixa com 12 = 12)", style: { maxWidth: "90px" } });
  const custo = h("input", { type: "text", inputmode: "decimal", placeholder: "Custo un.", style: { maxWidth: "120px" } });
  desenhar();
  const m = modal({
    titulo: "Itens da compra", tamanho: "modal-grande",
    corpo: h("div", { class: "grade" },
      produtos.length ? null : h("div", { class: "alerta alerta-aviso" }, "Marque \"Controla estoque\" nos insumos/produtos que você compra."),
      h("div", { class: "acoes" }, sel, qtd, h("span", { class: "muted" }, "×"), fator, custo,
        h("button", { type: "button", class: "botao", onclick: () => {
          const q = Number(qtd.value);
          const c = centavos(custo.value);
          if (!sel.value || !q) return;
          itens.push({ produto: sel.value, quantidade: qtd.value, fator_conversao: fator.value || "1", custo_unitario_centavos: c, total_centavos: Math.round(q * c), descricao_nota: "" });
          qtd.value = ""; custo.value = ""; desenhar();
        } }, "Incluir")),
      h("small", { class: "muted" }, "Quantidade na unidade de compra; o fator converte para a unidade de estoque (ex.: 2 caixas × 12 = 24 un)."),
      listaEl, h("div", { class: "direita" }, "Total dos itens: ", total)),
    rodape: [botaoAcao("Salvar itens", async () => {
      await patch(`/api/compras/${compra.id}/`, { itens });
      aviso("Itens salvos.", "ok"); m.fechar(); recarregar();
    }, "botao botao-primario")],
  });
}

