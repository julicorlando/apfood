// Estoque, compras, financeiro e relatórios.
import { ehGerente, get, lista, patch, post } from "../api.js";
import { paginaCadastro } from "../crud.js";
import {
  abas, aviso, barras, botaoAcao, centavos, confirmar, data, dataHora, dinheiro, erro, etiqueta, etiquetaStatus, h, hojeISO, kpi, modal, pedirTexto, reais, rotulo, tabela, trocar,
} from "../ui.js";
import { cartaoDelivery, imprimirLinhas, mostrarCupom } from "./comum.js";

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

export function cmv() {
  return paginaRelatorio("CMV e margem", async (area, q) => {
    const r = await get(`/api/relatorios/cmv/?${q}`);
    const pct = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)}%`);
    const corMargem = (m) => (m === null || m === undefined ? "" : m >= 60 ? "e-ok" : m >= 40 ? "e-alerta" : "e-erro");
    const semCusto = r.cardapio.filter((p) => p.custo_centavos === null).length;
    trocar(area,
      h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
        kpi("Faturamento", dinheiro(r.faturamento_centavos), "pedidos concluídos"),
        kpi("Custo (CMV)", dinheiro(r.custo_centavos), "pela ficha técnica"),
        kpi("CMV %", pct(r.cmv_percentual), "ideal: abaixo de 35%"),
        kpi("Lucro bruto", dinheiro(r.lucro_bruto_centavos), "faturamento − custo")),
      r.faturamento_sem_custo_centavos ? h("div", { class: "alerta alerta-aviso", style: { marginBottom: "12px" } },
        `${dinheiro(r.faturamento_sem_custo_centavos)} vendidos em produtos sem custo cadastrado (ficha técnica ou custo das compras) ficaram fora do CMV.`) : null,
      h("h2", null, "Vendas do período"),
      tabela([
        { rotulo: "Produto", campo: "nome" },
        { rotulo: "Qtd", classe: "num", campo: "quantidade" },
        { rotulo: "Faturamento", classe: "num", valor: (l) => dinheiro(l.faturamento_centavos) },
        { rotulo: "Custo", classe: "num", valor: (l) => (l.sem_custo ? "sem custo" : dinheiro(l.custo_centavos)) },
        { rotulo: "CMV", classe: "num", valor: (l) => pct(l.cmv_percentual) },
        { rotulo: "Margem", valor: (l) => (l.margem_percentual === null ? "—" : etiqueta(pct(l.margem_percentual), corMargem(l.margem_percentual))) },
      ], r.itens, { vazio: "Sem vendas concluídas no período." }),
      h("h2", { style: { marginTop: "20px" } }, "Cardápio: preço × custo"),
      semCusto ? h("p", { class: "muted" }, `${semCusto} item(ns) sem custo: cadastre a ficha técnica (Cardápio → Produtos) e lance as compras dos insumos.`) : null,
      tabela([
        { rotulo: "Produto", campo: "nome" },
        { rotulo: "Preço", classe: "num", valor: (l) => dinheiro(l.preco_centavos) },
        { rotulo: "Custo", classe: "num", valor: (l) => (l.custo_centavos === null ? "—" : dinheiro(l.custo_centavos)) },
        { rotulo: "Margem", valor: (l) => (l.margem_percentual === null ? "—" : etiqueta(pct(l.margem_percentual), corMargem(l.margem_percentual))) },
      ], r.cardapio, { vazio: "Nenhum produto." }));
  });
}

export function operadores() {
  return paginaRelatorio("Faturamento por operador", async (area, q) => {
    const r = await get(`/api/relatorios/operadores/?${q}`);
    const formas = (o) => Object.entries(o.por_forma || {}).map(([f, v]) => `${rotulo("FormaPagamento", f)} ${dinheiro(v)}`).join(" · ") || "—";
    trocar(area,
      h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
        kpi("Recebido pelos operadores", dinheiro(r.total_recebido_centavos), "pagamentos confirmados no caixa"),
        kpi("Pedidos efetivados", dinheiro(r.total_pedidos_centavos), "lançados por eles e concluídos"),
        kpi("Operadores", String(r.operadores.length), "com movimento no período")),
      h("p", { class: "muted" }, "Pedidos efetivados: lançados pelo operador (PDV, mesa ou telefone) e concluídos. "
        + "Recebido: pagamentos que o operador registrou no caixa (pedidos pagos online pelo cliente não entram)."),
      tabela([
        { rotulo: "Operador", valor: (o) => h("strong", null, o.operador) },
        { rotulo: "Pedidos", classe: "num", campo: "pedidos" },
        { rotulo: "Valor dos pedidos", classe: "num", valor: (o) => dinheiro(o.pedidos_centavos) },
        { rotulo: "Ticket médio", classe: "num", valor: (o) => dinheiro(o.ticket_medio_centavos) },
        { rotulo: "Cancelados", classe: "num", campo: "cancelados" },
        { rotulo: "Recebido", classe: "num", valor: (o) => h("strong", null, dinheiro(o.recebido_centavos)) },
        { rotulo: "Por forma", valor: formas },
      ], r.operadores, { vazio: "Nenhum operador com movimento no período." }));
  });
}

export function acertoEntregadores() {
  return {
    titulo: "Acerto de entregadores",
    async render(raiz) {
      const area = h("div");
      trocar(raiz, h("p", { class: "muted" }, "Entregas concluídas ainda não acertadas. Ganhos seguem a regra do cadastro de cada entregador "
        + "(taxa de entrega ou valor fixo); “em mãos” é o dinheiro que ele cobrou dos clientes na entrega. "
        + "Saldo positivo: a loja paga; negativo: o entregador devolve."), area);
      async function carregar() {
        const r = await get("/api/acertos-entregador/");
        const totais = r.pendentes.reduce((t, x) => ({ ent: t.ent + x.entregas, saldo: t.saldo + x.saldo_centavos }), { ent: 0, saldo: 0 });
        trocar(area,
          h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
            kpi("Entregas a acertar", String(totais.ent)), kpi("Saldo total", dinheiro(totais.saldo), "a pagar aos entregadores")),
          h("div", { class: "cartao", style: { marginBottom: "16px" } }, h("h2", null, "A acertar"),
            tabela([
              { rotulo: "Entregador", valor: (x) => h("div", null, h("strong", null, x.entregador), h("div", { class: "muted" }, x.regra)) },
              { rotulo: "Período", valor: (x) => `${data(x.desde)} a ${data(x.ate)}` },
              { rotulo: "Entregas", classe: "num", campo: "entregas" },
              { rotulo: "Ganhos", classe: "num", valor: (x) => dinheiro(x.ganhos_centavos) },
              { rotulo: "Em mãos", classe: "num", valor: (x) => dinheiro(x.em_maos_centavos) },
              { rotulo: "Saldo", classe: "num", valor: (x) => h("strong", { style: { color: x.saldo_centavos < 0 ? "var(--erro)" : "" } }, dinheiro(x.saldo_centavos)) },
              { rotulo: "", classe: "acoes-linha", valor: (x) => ehGerente() ? botaoAcao("Registrar acerto", () => registrar(x), "botao botao-primario botao-pequeno") : null },
            ], r.pendentes, { vazio: "Nenhuma entrega pendente de acerto." })),
          h("div", { class: "cartao" }, h("h2", null, "Acertos feitos"),
            tabela([
              { rotulo: "Quando", valor: (a) => dataHora(a.em) },
              { rotulo: "Entregador", campo: "entregador" },
              { rotulo: "Período", valor: (a) => `${data(a.inicio)} a ${data(a.fim)}` },
              { rotulo: "Entregas", classe: "num", campo: "entregas" },
              { rotulo: "Pago", classe: "num", valor: (a) => dinheiro(a.pago_centavos) },
              { rotulo: "", classe: "acoes-linha", valor: (a) => botaoAcao("Recibo", async () => {
                const rr = await get(`/api/acertos-entregador/${a.id}/recibo/`);
                mostrarCupom(rr.linhas, { titulo: "Recibo de acerto" });
              }, "botao botao-pequeno") },
            ], r.acertos, { vazio: "Nenhum acerto registrado." })));
      }
      function registrar(x) {
        const valor = h("input", { type: "text", inputmode: "decimal", value: reais(Math.max(0, x.saldo_centavos)) });
        const obs = h("input", { type: "text", placeholder: "Ex.: pago no Pix" });
        const despesa = h("input", { type: "checkbox", checked: true });
        const m = modal({
          titulo: `Acerto — ${x.entregador}`, tamanho: "modal-pequeno",
          corpo: h("div", { class: "grade" },
            h("ul", { class: "lista-simples" },
              h("li", null, `${x.entregas} entrega(s)`, h("span", { class: "num" }, `${data(x.desde)} a ${data(x.ate)}`)),
              h("li", null, "Ganhos", h("span", { class: "num" }, dinheiro(x.ganhos_centavos))),
              h("li", null, "Dinheiro em mãos", h("span", { class: "num" }, `− ${dinheiro(x.em_maos_centavos)}`)),
              h("li", { class: "negrito" }, "Saldo", h("span", { class: "num" }, dinheiro(x.saldo_centavos)))),
            h("label", { class: "campo" }, h("span", null, "Valor pago agora (R$)"), valor),
            h("label", { class: "campo" }, h("span", null, "Observação"), obs),
            h("label", { class: "check" }, despesa, h("span", null, "Lançar em Contas a pagar como paga"))),
          rodape: [botaoAcao("Registrar e emitir recibo", async () => {
            const r = await post("/api/acertos-entregador/", { entregador_id: x.entregador_id, pago_centavos: centavos(valor.value) || 0,
              observacao: obs.value, gerar_despesa: despesa.checked });
            m.fechar();
            aviso("Acerto registrado.", "ok");
            mostrarCupom(r.linhas, { titulo: "Recibo de acerto" });
            carregar();
          }, "botao botao-primario")],
        });
      }
      await carregar();
    },
  };
}

export function garcons() {
  return paginaRelatorio("Taxa de serviço por garçom", async (area, q) => {
    const r = await get(`/api/relatorios/garcons/?${q}`);
    trocar(area,
      h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
        kpi("Taxa de serviço no período", dinheiro(r.total_taxa_centavos), `${r.comandas} comanda(s) fechada(s)`)),
      h("p", { class: "muted" }, "A taxa de cada comanda é dividida entre quem lançou os pedidos, na proporção do valor que cada um lançou. "
        + "Pedidos feitos pelo QR da mesa ficam em “Autoatendimento”."),
      tabela([
        { rotulo: "Garçom", valor: (g) => h("strong", null, g.garcom) },
        { rotulo: "Comandas", classe: "num", campo: "comandas" },
        { rotulo: "Vendas lançadas", classe: "num", valor: (g) => dinheiro(g.vendas_centavos) },
        { rotulo: "Taxa de serviço", classe: "num", valor: (g) => h("strong", null, dinheiro(g.taxa_centavos)) },
      ], r.garcons, { vazio: "Nenhuma comanda fechada no período." }));
  });
}

export function rede() {
  return paginaRelatorio("Visão da rede", async (area, q) => {
    const r = await get(`/api/rede/?${q}`, { semLoja: true });
    const t = r.total;
    trocar(area,
      h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
        kpi("Faturamento da rede", dinheiro(t.faturamento_centavos), `${r.lojas.length} loja(s)`),
        kpi("Pedidos", String(t.pedidos)), kpi("Ticket médio", dinheiro(t.ticket_medio_centavos)), kpi("Cancelados", String(t.cancelados))),
      h("div", { class: "cartao", style: { marginBottom: "16px" } }, h("h2", null, "Por loja"),
        tabela([
          { rotulo: "Loja", valor: (l) => h("div", null, h("strong", null, l.loja), l.cidade ? h("div", { class: "muted" }, l.cidade) : null) },
          { rotulo: "Faturamento", classe: "num", valor: (l) => h("strong", null, dinheiro(l.faturamento_centavos)) },
          { rotulo: "% da rede", classe: "num", valor: (l) => h("div", { class: "barra-rede" },
            h("div", { class: "cheio", style: { width: `${l.participacao}%` } }), h("span", null, `${String(l.participacao).replace(".", ",")}%`)) },
          { rotulo: "Pedidos", classe: "num", campo: "pedidos" },
          { rotulo: "Ticket", classe: "num", valor: (l) => dinheiro(l.ticket_medio_centavos) },
          { rotulo: "Entregas", classe: "num", campo: "entregas" },
          { rotulo: "Online", classe: "num", campo: "online" },
          { rotulo: "Cancelados", classe: "num", campo: "cancelados" },
          { rotulo: "Nota", classe: "num", valor: (l) => (l.nota_media ? `${String(l.nota_media).replace(".", ",")} ★` : "—") },
        ], r.lojas, { vazio: "Nenhuma loja." })),
      r.lojas.length > 1 ? cartaoReplicar(r.lojas) : h("p", { class: "muted" }, "Cadastre mais lojas em Configurações → Lojas para comparar e replicar o cardápio."));
  });
}

function cartaoReplicar(lojas) {
  const origem = h("select", null, lojas.map((l) => h("option", { value: l.loja_id }, l.loja)));
  const destinos = h("div", { class: "grade", style: { gap: "6px" } });
  const somente = h("input", { type: "checkbox" });
  const desenhar = () => trocar(destinos, lojas.filter((l) => l.loja_id !== origem.value).map((l) =>
    h("label", { class: "check" }, h("input", { type: "checkbox", value: l.loja_id, checked: true }), h("span", null, l.loja))));
  origem.addEventListener("change", desenhar);
  desenhar();
  return h("div", { class: "cartao" }, h("h2", null, "Replicar cardápio entre lojas"),
    h("p", { class: "muted" }, "Copia categorias, produtos, tamanhos e adicionais da loja de origem (casando pelo nome). "
      + "Produtos que já existem no destino têm o preço atualizado. Ficha técnica e estoque não são copiados."),
    h("div", { class: "form-grade" },
      h("label", { class: "campo" }, h("span", null, "Loja de origem"), origem),
      h("div", { class: "campo" }, h("span", null, "Para as lojas"), destinos),
      h("label", { class: "check largo" }, somente, h("span", null, "Só atualizar preços (não criar itens novos)"))),
    h("div", { class: "acoes", style: { marginTop: "12px" } }, botaoAcao("Replicar", async () => {
      const ids = [...destinos.querySelectorAll("input:checked")].map((i) => i.value);
      if (!ids.length) { aviso("Escolha pelo menos uma loja de destino.", "erro"); return; }
      if (!(await confirmar(`Replicar o cardápio de ${origem.selectedOptions[0].textContent} para ${ids.length} loja(s)?`))) return;
      const r = await post("/api/rede/replicar/", { origem: origem.value, destinos: ids, somente_precos: somente.checked }, { semLoja: true });
      modal({ titulo: "Cardápio replicado", tamanho: "modal-pequeno", corpo: h("ul", { class: "lista-simples" },
        Object.entries(r.resultado).map(([loja, c]) => h("li", null, h("strong", null, loja),
          h("span", { class: "muted" }, `${c.produtos_novos} novo(s), ${c.produtos_atualizados} atualizado(s), ${c.categorias} categoria(s)`)))) });
    }, "botao botao-primario")));
}

export function avaliacoes() {
  return paginaRelatorio("Avaliações dos clientes", async (area, q) => {
    const r = await get(`/api/relatorios/avaliacoes/?${q}`);
    const estrelas = (n) => h("span", { class: "estrelas", "aria-label": `${n} de 5` }, "★".repeat(n) + "☆".repeat(5 - n));
    const maior = Math.max(1, ...Object.values(r.distribuicao));
    trocar(area,
      h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
        kpi("Nota média", r.media ? r.media.toFixed(1).replace(".", ",") + " ★" : "—", `${r.quantidade} avaliação(ões)`),
        kpi("Clientes que avaliaram", r.taxa_resposta != null ? `${String(r.taxa_resposta).replace(".", ",")}%` : "—", "dos pedidos concluídos")),
      h("div", { class: "cartao", style: { marginBottom: "16px" } },
        h("h2", null, "Distribuição"),
        h("div", { class: "barras-notas" }, [5, 4, 3, 2, 1].map((n) => h("div", { class: "barra-nota" },
          h("span", null, `${n} ★`),
          h("div", { class: "trilho" }, h("div", { class: "cheio", style: { width: `${(100 * r.distribuicao[n]) / maior}%` } })),
          h("span", { class: "num" }, String(r.distribuicao[n])))))),
      h("p", { class: "muted" }, "A avaliação é opcional: o cliente vê o pedido de avaliação na tela de acompanhamento e na mensagem de WhatsApp de pedido entregue."),
      tabela([
        { rotulo: "Quando", valor: (a) => dataHora(a.em) },
        { rotulo: "Pedido", valor: (a) => `#${a.pedido}` },
        { rotulo: "Cliente", campo: "cliente" },
        { rotulo: "Nota", valor: (a) => estrelas(a.nota) },
        { rotulo: "Comentário", valor: (a) => a.comentario || h("span", { class: "muted" }, "—") },
      ], r.avaliacoes, { vazio: "Nenhuma avaliação no período." }));
  });
}

export function fechamentos() {
  return paginaRelatorio("Fechamentos de caixa", async (area, q) => {
    const r = await get(`/api/relatorios/fechamentos/?${q}`);
    const dif = (v) => h("span", { class: v ? (v > 0 ? "etiqueta e-info" : "etiqueta e-erro") : "etiqueta e-ok" }, v ? dinheiro(v) : "ok");
    trocar(area, 
      cartaoDelivery(r.delivery),
      h("h2", { style: { marginTop: "16px" } }, "Por operador"),
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

