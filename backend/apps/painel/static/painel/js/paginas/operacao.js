// Operação do dia: início, pedidos em tempo real, mesas, cozinha e caixa.
import { ehGerente, ehMaster, get, lista, post, sessao, put } from "../api.js";
import { aoMudarConexao, bipe, ouvir } from "../realtime.js";
import {
  aviso, barras, botaoAcao, centavos, confirmar, dataHora, dinheiro, erro, etiqueta, etiquetaStatus, h, hojeISO, hora, kpi, limpar, minutosDesde, modal, pedirTexto, reais, rotulo, tabela, trocar, uuid,
} from "../ui.js";
import { abrirPedido, cartaoDelivery, imprimirLinhas, imprimirPedido, itensTexto, mostrarCupom, pago, receber } from "./comum.js";
import { aplicarPromocoes, carregarCardapio, montarItem, precoProduto } from "./pdv.js";

function atualizarAoVivo(fn, ms = 20000) {
  let fila = null;
  const agendar = () => { clearTimeout(fila); fila = setTimeout(fn, 400); };
  const parar = ouvir((ev) => { if (ev.tipo?.startsWith("pedido.")) agendar(); });
  const intervalo = setInterval(fn, ms);
  return () => { parar(); clearInterval(intervalo); clearTimeout(fila); };
}

function indicadorAoVivo() {
  const el = h("span", { class: "status-ao-vivo" }, "ao vivo");
  const parar = aoMudarConexao((on) => { el.classList.toggle("on", on); el.textContent = on ? "ao vivo" : "reconectando…"; });
  return { el, parar };
}

// =============================================================================
// Início
// =============================================================================
export function inicio() {
  return {
    titulo: "Início",
    async render(raiz) {
      const loja = sessao.loja;
      if (!loja) {
        trocar(raiz, h("div", { class: "cartao vazio" },
          ehMaster() ? h("div", null, h("p", null, "Nenhuma loja cadastrada ainda."), h("a", { class: "botao botao-primario", href: "#/empresas" }, "Cadastrar a primeira empresa"))
            : "Você ainda não tem acesso a nenhuma loja. Fale com o administrador."));
        return;
      }
      const corpo = h("div", { class: "grade" });
      trocar(raiz, corpo);
      const lojaInfo = (await get(`/api/lojas/${loja.id}/`).catch(() => null)) || loja;
      const urlCardapio = `${location.origin}/${lojaInfo.slug}/`;

      const abertura = h("div", { class: "cartao acoes" },
        h("div", { style: { flex: 1, minWidth: "220px" } },
          h("div", { class: "negrito" }, lojaInfo.nome),
          h("div", { class: "muted" }, "Cardápio online: ", h("a", { href: urlCardapio, target: "_blank", rel: "noopener" }, urlCardapio))),
        etiqueta(lojaInfo.aberta_para_pedidos ? "Recebendo pedidos online" : "Pedidos online fechados", lojaInfo.aberta_para_pedidos ? "e-ok" : "e-erro"),
        ehGerente() ? botaoAcao(lojaInfo.aberta_para_pedidos ? "Fechar pedidos online" : "Abrir pedidos online", async () => {
          await post(`/api/lojas/${loja.id}/pedidos-online/`, { aberta: !lojaInfo.aberta_para_pedidos });
          aviso("Pronto.", "ok");
          window.dispatchEvent(new HashChangeEvent("hashchange"));
        }, lojaInfo.aberta_para_pedidos ? "botao" : "botao botao-primario") : null,
        h("a", { class: "botao botao-primario", href: "#/pdv" }, "Abrir PDV"));
      corpo.append(abertura);

      const [abertos, turno] = await Promise.all([
        lista("/api/pedidos/", { abertos: 1 }),
        get("/api/turnos/atual/").catch(() => null),
      ]);
      const conta = (sts) => abertos.filter((p) => sts.includes(p.status)).length;
      const kpisOperacao = h("div", { class: "grade grade-kpi" },
        h("a", { href: "#/pedidos", style: { textDecoration: "none", color: "inherit" } }, kpi("Aguardando aceite", String(conta(["PENDENTE"])), "pedidos online")),
        kpi("Em preparo", String(conta(["RECEBIDO", "EM_PREPARO"]))),
        kpi("Prontos / em entrega", String(conta(["PRONTO", "SAIU_PARA_ENTREGA"]))),
        kpi("Seu caixa", turno && turno.loja === loja.id ? "Aberto" : "Fechado", turno && turno.loja === loja.id ? `desde ${hora(turno.aberto_em)}` : "abra em Caixa"));
      corpo.append(kpisOperacao);

      if (ehGerente()) {
        const [hoje, semana, baixos] = await Promise.all([
          get("/api/relatorios/vendas/?periodo=dia"),
          get(`/api/relatorios/vendas/?inicio=${hojeISO(-6)}&fim=${hojeISO()}`),
          get("/api/estoque/abaixo-do-minimo/").catch(() => []),
        ]);
        corpo.append(h("div", { class: "grade grade-kpi" },
          kpi("Faturamento hoje", dinheiro(hoje.faturamento_centavos), `${hoje.pedidos} pedidos concluídos`),
          kpi("Ticket médio hoje", dinheiro(hoje.ticket_medio_centavos)),
          kpi("Últimos 7 dias", dinheiro(semana.faturamento_centavos), `${semana.pedidos} pedidos`),
          kpi("Cancelados hoje", String(hoje.cancelados))));
        const dias = [];
        for (let i = 6; i >= 0; i--) {
          const d = hojeISO(-i);
          const achado = semana.por_dia.find((x) => String(x.data).slice(0, 10) === d);
          dias.push({ rotulo: `${d.slice(8, 10)}/${d.slice(5, 7)}`, valor: achado?.faturamento_centavos || 0, pedidos: achado?.pedidos || 0 });
        }
        corpo.append(h("div", { class: "grade grade-2" },
          h("div", { class: "cartao" }, h("h2", null, "Vendas da semana"),
            barras(dias, { dica: (p) => `${dinheiro(p.valor)} · ${p.pedidos} pedidos` })),
          h("div", { class: "cartao" }, h("h2", null, "Hoje por canal"),
            hoje.por_canal.length ? h("ul", { class: "lista-simples" }, hoje.por_canal.map((c) => h("li", null,
              h("div", { style: { flex: 1 } }, rotulo("CanalVenda", c.canal), h("div", { class: "linha-pct" }, h("i", { style: { width: `${c.percentual}%` } }))),
              h("span", { class: "num" }, dinheiro(c.faturamento_centavos))))) : h("p", { class: "muted" }, "Nenhuma venda concluída hoje."))));
        if (baixos.length) {
          corpo.append(h("div", { class: "cartao" }, h("h2", null, "⚠️ Estoque abaixo do mínimo"),
            h("ul", { class: "lista-simples" }, baixos.map((p) => h("li", null, p.nome,
              h("span", { class: "etiqueta e-erro" }, `${Number(p.estoque_atual)} / mín. ${Number(p.estoque_minimo)} ${p.unidade}`)))),
            h("a", { href: "#/estoque", class: "botao", style: { marginTop: "8px" } }, "Ver estoque")));
        }
      }
    },
  };
}

// =============================================================================
// Pedidos (quadro em tempo real)
// =============================================================================
const COLUNAS = [
  ["Novos (aceitar)", ["PENDENTE"]],
  ["Em preparo", ["RECEBIDO", "EM_PREPARO"]],
  ["Prontos", ["PRONTO"]],
  ["Em entrega", ["SAIU_PARA_ENTREGA"]],
];

export function pedidos() {
  return {
    titulo: "Pedidos",
    async render(raiz) {
      let vista = "quadro";
      let novos = new Set();
      let conhecidos = null;
      const area = h("div");
      const ao = indicadorAoVivo();
      const dataSel = h("input", { type: "date", value: hojeISO(), style: { maxWidth: "170px" } });
      const botoesVista = [["quadro", "Em andamento"], ["dia", "Todos do dia"]].map(([v, r]) => h("button", {
        type: "button", class: `botao ${v === vista ? "botao-primario" : ""}`,
        onclick: () => { vista = v; botoesVista.forEach((b, i) => b.classList.toggle("botao-primario", ["quadro", "dia"][i] === v)); dataSel.hidden = v !== "dia"; carregar(); },
      }, r));
      dataSel.hidden = true;
      dataSel.addEventListener("change", carregar);
      trocar(raiz, h("div", { class: "barra-ferramentas" }, botoesVista, dataSel, h("span", { class: "espaco" }), ao.el,
        h("a", { href: "#/pdv", class: "botao botao-primario" }, "+ Novo pedido")), area);

      async function carregar() {
        try {
          if (vista === "quadro") {
            const ps = await lista("/api/pedidos/", { abertos: 1 });
            const ids = new Set(ps.map((p) => p.id));
            if (conhecidos) for (const id of ids) if (!conhecidos.has(id)) novos.add(id);
            conhecidos = ids;
            desenharQuadro(ps);
          } else {
            const ps = await lista("/api/pedidos/", { data: dataSel.value });
            desenharDia(ps);
          }
        } catch (e) { erro(e); }
      }

      function cartao(p) {
        const min = minutosDesde(p.criado_em);
        const falta = p.total_centavos - pago(p);
        const c = h("div", { class: `pedido-cartao ${novos.has(p.id) || p.status === "PENDENTE" ? "novo" : ""}`, tabindex: 0, role: "button" },
          h("div", { class: "pedido-topo" },
            h("span", { class: "pedido-numero" }, `#${p.numero}`),
            h("span", { class: min > 40 ? "etiqueta e-erro" : min > 20 ? "etiqueta e-alerta" : "etiqueta" }, `${min} min`)),
          h("div", null, p.nome_cliente || p.mesa && `Mesa ${p.mesa}` || rotulo("TipoAtendimento", p.tipo_atendimento)),
          p.agendado_para ? h("div", { class: "etiqueta e-info", style: { justifySelf: "start" } }, `📅 Agendado ${dataHora(p.agendado_para)}`) : null,
          h("div", { class: "pedido-itens" }, itensTexto(p)),
          h("div", { class: "acoes" },
            h("span", { class: "etiqueta" }, p.marketplace ? rotulo("Marketplace", p.marketplace) : rotulo("CanalVenda", p.canal)),
            p.tipo_atendimento === "ENTREGA" ? h("span", { class: "etiqueta e-cor" }, "Entrega") : null,
            h("span", { class: "espaco", style: { flex: 1 } }),
            h("strong", null, dinheiro(p.total_centavos)),
            falta > 0 ? h("span", { class: "etiqueta e-alerta" }, "a receber") : null));
        const abrir = () => { novos.delete(p.id); abrirPedido(p.id, { aoMudar: carregar }).catch(erro); };
        c.addEventListener("click", abrir);
        c.addEventListener("keydown", (ev) => { if (ev.key === "Enter") abrir(); });
        return c;
      }

      function desenharQuadro(ps) {
        trocar(area, h("div", { class: "quadro" }, COLUNAS.map(([titulo, sts]) => {
          const dela = ps.filter((p) => sts.includes(p.status)).sort((a, b) => a.criado_em.localeCompare(b.criado_em));
          return h("div", { class: "coluna" }, h("h3", null, titulo, h("span", { class: "etiqueta" }, String(dela.length))),
            dela.length ? dela.map(cartao) : h("div", { class: "muted", style: { padding: "8px" } }, "—"));
        })));
      }

      function desenharDia(ps) {
        const concluidos = ps.filter((p) => p.status === "CONCLUIDO");
        trocar(area, 
          h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
            kpi("Pedidos", String(ps.length)), kpi("Concluídos", String(concluidos.length)),
            kpi("Faturado", dinheiro(concluidos.reduce((s, p) => s + p.total_centavos, 0)))),
          tabela([
            { rotulo: "Nº", valor: (p) => h("strong", null, `#${p.numero}`) },
            { rotulo: "Hora", valor: (p) => hora(p.criado_em) },
            { rotulo: "Cliente", valor: (p) => p.nome_cliente || (p.mesa ? `Mesa ${p.mesa}` : "—") },
            { rotulo: "Canal", valor: (p) => rotulo("CanalVenda", p.canal) },
            { rotulo: "Itens", valor: (p) => itensTexto(p) },
            { rotulo: "Total", classe: "num", valor: (p) => dinheiro(p.total_centavos) },
            { rotulo: "Status", valor: (p) => etiquetaStatus("StatusPedido", p.status) },
          ], [...ps].sort((a, b) => b.criado_em.localeCompare(a.criado_em)), { aoClicar: (p) => abrirPedido(p.id, { aoMudar: carregar }).catch(erro), vazio: "Nenhum pedido nesta data." }));
      }

      await carregar();
      const parar = atualizarAoVivo(carregar);
      return () => { parar(); ao.parar(); };
    },
  };
}

// =============================================================================
// Mesas e comandas
// =============================================================================
export function mesas() {
  return {
    titulo: "Mesas e comandas",
    async render(raiz) {
      const area = h("div");
      trocar(raiz, h("div", { class: "barra-ferramentas" },
        h("span", { class: "muted" }, "Toque numa mesa livre para abrir a comanda."), h("span", { class: "espaco" }),
        botaoAcao("+ Comanda avulsa", async () => {
          const numero = await pedirTexto("Comanda avulsa", { rotulo: "Número ou nome da comanda", ok: "Abrir" });
          if (!numero) return;
          const c = await post("/api/comandas/", { id: uuid(), numero, nome_cliente: numero, pessoas: 1 });
          await carregar();
          abrirComanda(c.id, carregar);
        }, "botao")), area);

      async function carregar() {
        const [ms, cs] = await Promise.all([lista("/api/mesas/", { ativa: "true" }), lista("/api/comandas/", { abertas: 1 })]);
        const porMesa = new Map(cs.filter((c) => c.mesa).map((c) => [c.mesa, c]));
        const avulsas = cs.filter((c) => !c.mesa);
        trocar(area, 
          ms.length ? h("div", { class: "mesas" }, ms.sort((a, b) => (a.ordem ?? 0) - (b.ordem ?? 0) || a.nome.localeCompare(b.nome)).map((m) => {
            const c = porMesa.get(m.id);
            const el = h("button", { type: "button", class: `mesa ${c ? (c.status === "FECHANDO" ? "fechando" : "ocupada") : ""}` },
              h("div", { class: "num-mesa" }, m.nome.replace(/^Mesa\s*/i, "")),
              h("div", { class: "muted" }, m.area || ""),
              c ? h("div", { class: "negrito" }, dinheiro(c.total_centavos)) : h("div", { class: "muted" }, "livre"),
              c?.status === "FECHANDO" ? h("div", null, etiqueta("conta pedida", "e-alerta")) : null);
            el.addEventListener("click", async () => {
              try {
                if (c) abrirComanda(c.id, carregar);
                else {
                  const pessoas = await pedirTexto(`Abrir ${m.nome}`, { rotulo: "Pessoas na mesa", valor: "2", tipo: "number", ok: "Abrir comanda" });
                  if (!pessoas) return;
                  const nova = await post("/api/comandas/", { id: uuid(), mesa: m.id, pessoas: parseInt(pessoas, 10) || 1 });
                  await carregar();
                  abrirComanda(nova.id, carregar);
                }
              } catch (e) { erro(e); }
            });
            return el;
          })) : h("div", { class: "cartao vazio" }, "Nenhuma mesa cadastrada. ", h("a", { href: "#/mesas-cadastro" }, "Cadastrar mesas")),
          avulsas.length ? h("div", { class: "cartao", style: { marginTop: "16px" } }, h("h2", null, "Comandas avulsas"),
            tabela([
              { rotulo: "Comanda", valor: (c) => c.numero || c.nome_cliente || "—" },
              { rotulo: "Aberta", valor: (c) => dataHora(c.criado_em) },
              { rotulo: "Total", classe: "num", valor: (c) => dinheiro(c.total_centavos) },
              { rotulo: "Situação", valor: (c) => etiquetaStatus("StatusComanda", c.status) },
            ], avulsas, { aoClicar: (c) => abrirComanda(c.id, carregar) })) : null);
      }
      await carregar();
      const parar = atualizarAoVivo(() => carregar().catch(() => {}), 30000);
      return parar;
    },
  };
}

async function abrirComanda(id, aoMudar) {
  const corpo = h("div");
  const rodape = h("div", { class: "acoes", style: { width: "100%" } });
  const m = modal({ titulo: "Comanda", corpo, rodape, tamanho: "modal-grande" });
  let c;
  let cardapio = null;

  async function recarregar() {
    const [cc, ps] = await Promise.all([get(`/api/comandas/${id}/`), get(`/api/comandas/${id}/pedidos/`)]);
    c = cc;
    m.el.querySelector(".modal-topo h2").textContent = c.numero ? `Comanda ${c.numero}` : "Comanda";
    const ativos = ps.filter((p) => !["CANCELADO", "RECUSADO"].includes(p.status));
    const pagoTotal = (c.pagamentos || []).filter((x) => x.status === "CONFIRMADO").reduce((s, x) => s + x.valor_centavos, 0);
    const falta = Math.max(0, c.total_centavos - pagoTotal);
    trocar(corpo, 
      h("div", { class: "acoes", style: { marginBottom: "12px" } }, etiquetaStatus("StatusComanda", c.status),
        h("span", { class: "muted" }, `${c.pessoas} pessoa(s) · aberta ${dataHora(c.criado_em)}`)),
      h("div", { class: "grade grade-2" },
        h("div", null, h("h3", null, "Consumo"),
          ativos.length ? h("ul", { class: "lista-simples" }, ativos.flatMap((p) => (p.itens || []).map((i) => h("li", null,
            h("span", null, `${i.quantidade}× ${i.nome_produto}${i.nome_variacao ? ` (${i.nome_variacao})` : ""}`,
              i.adicionais?.length ? h("span", { class: "muted" }, ` + ${i.adicionais.map((a) => a.nome).join(", ")}`) : null),
            h("span", { class: "num" }, dinheiro(i.total_centavos)))))) : h("p", { class: "muted" }, "Nada lançado ainda.")),
        h("div", null, h("h3", null, "Conta"),
          h("ul", { class: "lista-simples" },
            h("li", null, "Consumo", h("span", { class: "num" }, dinheiro(c.subtotal_centavos))),
            c.cobrar_taxa_servico ? h("li", null, `Serviço (${Number(c.taxa_servico_percentual)}%)`, h("span", { class: "num" }, dinheiro(c.taxa_servico_centavos))) : null,
            c.couvert_centavos ? h("li", null, "Couvert", h("span", { class: "num" }, dinheiro(c.couvert_centavos))) : null,
            c.desconto_centavos ? h("li", null, "Desconto", h("span", { class: "num" }, `− ${dinheiro(c.desconto_centavos)}`)) : null,
            h("li", { class: "negrito" }, "Total", h("span", { class: "num" }, dinheiro(c.total_centavos))),
            ...(c.pagamentos || []).filter((x) => x.status === "CONFIRMADO").map((x) => h("li", { class: "muted" },
              `Pago${x.pagador ? ` por ${x.pagador}` : ""} · ${rotulo("FormaPagamento", x.forma)}`,
              h("span", { class: "num" }, `− ${dinheiro(x.valor_centavos)}`))),
            h("li", { class: "negrito" }, "Falta", h("span", { class: "num" }, dinheiro(falta)))),
          pagoTotal && falta > 0 ? h("p", { class: "muted", style: { marginTop: "8px" } },
            "Pagamento parcial: a mesa continua aberta para quem ficou consumir e pagar depois.") : null)));

    const aberta = ["ABERTA", "FECHANDO"].includes(c.status);
    trocar(rodape, 
      aberta ? botaoAcao("+ Lançar itens", lancarItens, "botao botao-primario") : null,
      aberta && c.status === "ABERTA" ? botaoAcao("Pedir a conta", async () => { await post(`/api/comandas/${id}/pedir-conta/`); await recarregar(); aoMudar(); }) : null,
      c.status === "FECHANDO" ? botaoAcao("Reabrir", async () => { await post(`/api/comandas/${id}/reabrir/`); await recarregar(); aoMudar(); }) : null,
      botaoAcao("Imprimir conta", async () => { const { qsLargura } = await import("./comum.js"); const r = await get(`/api/comandas/${id}/cupom/?${qsLargura()}`); imprimirLinhas(r.linhas); }),
      aberta ? botaoAcao("Dividir", async () => {
        const n = await pedirTexto("Dividir a conta", { rotulo: "Em quantas pessoas?", valor: String(c.pessoas), tipo: "number" });
        if (!n) return;
        const r = await get(`/api/comandas/${id}/divisao/?pessoas=${parseInt(n, 10) || 1}`);
        modal({ titulo: "Divisão sugerida", tamanho: "modal-pequeno", corpo: h("ul", { class: "lista-simples" },
          r.partes_centavos.map((v, i) => h("li", null, `Pessoa ${i + 1}`, h("span", { class: "num" }, dinheiro(v))))) });
      }) : null,
      aberta && ehGerente() ? botaoAcao("Ajustes", ajustes) : null,
      aberta ? botaoAcao("Transferir", transferir) : null,
      aberta && falta > 0 ? botaoAcao("Receber (total ou parte)", async () => {
        const quitou = await receber({ tipo: "comanda", id, restante: falta, parcial: true, pessoas: c.pessoas });
        await recarregar(); aoMudar();
        if (!quitou && c.status !== "FECHADA") aviso("Parte recebida. A mesa continua aberta.", "ok");
      }, "botao botao-ok") : null,
      aberta && falta === 0 && c.total_centavos > 0 ? botaoAcao("Fechar comanda", async () => {
        await post(`/api/comandas/${id}/fechar/`);
        aviso("Comanda fechada.", "ok");
        m.fechar(); aoMudar();
      }, "botao botao-ok") : null);
  }

  async function lancarItens() {
    if (c.status === "FECHANDO") {  // conta pedida: reabre para quem ficou continuar pedindo
      if (!(await confirmar("A conta já foi pedida. Reabrir a mesa para lançar mais itens? Os pagamentos feitos continuam abatidos."))) return;
      await post(`/api/comandas/${id}/reabrir/`);
      await recarregar(); aoMudar();
    }
    cardapio = cardapio || await carregarCardapio();
    aplicarPromocoes(cardapio.idx, "MESA");
    const itens = [];
    const listaEl = h("ul", { class: "lista-simples" });
    const grade = h("div", { class: "pdv-produtos", style: { maxHeight: "50vh", overflowY: "auto" } });
    const busca = h("input", { type: "search", placeholder: "Buscar produto…" });
    const desenhar = () => {
      const termo = busca.value.trim().toLowerCase();
      const prods = cardapio.cardapio.categorias.flatMap((x) => x.produtos).filter((p) => !termo || p.nome.toLowerCase().includes(termo));
      trocar(grade, prods.map((p) => h("button", { type: "button", class: "pdv-produto", disabled: p.esgotado, onclick: async () => {
        const simples = !p.variacoes.length && !p.grupos.length && (cardapio.idx.categoriaDe[p.id]?.max_sabores || 1) < 2;
        const it = simples ? { produto_id: p.id, quantidade: 1, adicionais: [], sabores: [], observacao: "" } : await montarItem(cardapio.idx, p);
        if (!it) return;
        itens.push(it);
        trocar(listaEl, itens.map((x, n) => h("li", null, `${x.quantidade}× ${window.ApCarrinho.descrever(cardapio.idx, x).titulo}`,
          h("button", { type: "button", class: "botao botao-pequeno botao-perigo", onclick: (ev) => { itens.splice(n, 1); ev.target.closest("li").remove(); } }, "Tirar"))));
      } }, h("span", { class: "nome" }, p.nome), h("span", { class: "preco" }, precoProduto(p)))));
    };
    busca.addEventListener("input", desenhar);
    desenhar();
    const cozinha = h("input", { type: "checkbox", checked: true });
    const mm = modal({
      titulo: "Lançar na comanda", tamanho: "modal-grande",
      corpo: h("div", { class: "grade grade-2" }, h("div", null, busca, h("div", { style: { marginTop: "10px" } }, grade)),
        h("div", null, h("h3", null, "Itens a lançar"), listaEl, h("label", { class: "check", style: { marginTop: "10px" } }, cozinha, h("span", null, "Imprimir via da cozinha")))),
      rodape: [botaoAcao("Enviar pedido", async () => {
        if (!itens.length) { aviso("Escolha os itens.", "erro"); return; }
        const mesaNome = c.mesa ? (await get(`/api/mesas/${c.mesa}/`).catch(() => null))?.nome || "" : "";
        const p = await post("/api/pedidos/", {
          id: uuid(), canal: "MESA", tipo_atendimento: "CONSUMO_LOCAL", comanda: id,
          mesa: mesaNome.replace(/^Mesa\s*/i, "").slice(0, 10), nome_cliente: c.nome_cliente || "",
          itens: itens.map((i) => ({ produto_id: i.produto_id, quantidade: i.quantidade, variacao_id: i.variacao_id || null,
            sabores: i.sabores || [], adicionais: i.adicionais || [], observacao: i.observacao || "" })),
        });
        if (cozinha.checked) {
          await imprimirPedido(p.id, "cozinha").catch(erro);
        }
        aviso(`Pedido #${p.numero} enviado.`, "ok");
        mm.fechar();
        await recarregar();
        aoMudar();
      }, "botao botao-primario botao-grande")],
    });
  }

  function ajustes() {
    const servico = h("input", { type: "checkbox", checked: c.cobrar_taxa_servico });
    const desconto = h("input", { type: "text", inputmode: "decimal", value: reais(c.desconto_centavos) });
    const couvert = h("input", { type: "text", inputmode: "decimal", value: reais(c.couvert_centavos) });
    const mm = modal({
      titulo: "Ajustes da conta", tamanho: "modal-pequeno",
      corpo: h("div", { class: "grade" }, h("label", { class: "check" }, servico, h("span", null, "Cobrar taxa de serviço")),
        h("label", { class: "campo" }, h("span", null, "Desconto (R$)"), desconto),
        h("label", { class: "campo" }, h("span", null, "Couvert (R$)"), couvert)),
      rodape: [botaoAcao("Aplicar", async () => {
        await post(`/api/comandas/${id}/ajustar/`, { cobrar_taxa_servico: servico.checked, desconto_centavos: centavos(desconto.value), couvert_centavos: centavos(couvert.value) });
        mm.fechar(); await recarregar(); aoMudar();
      }, "botao botao-primario")],
    });
  }

  async function transferir() {
    const ms = await lista("/api/mesas/", { ativa: "true" });
    const ocupadas = new Set((await lista("/api/comandas/", { abertas: 1 })).map((x) => x.mesa).filter(Boolean));
    const livres = ms.filter((x) => !ocupadas.has(x.id));
    if (!livres.length) { aviso("Nenhuma mesa livre.", "erro"); return; }
    const mm = modal({
      titulo: "Transferir para a mesa", tamanho: "modal-pequeno",
      corpo: h("div", { class: "mesas" }, livres.map((x) => h("button", { type: "button", class: "mesa", onclick: async () => {
        try { await post(`/api/comandas/${id}/transferir/`, { mesa: x.id }); mm.fechar(); await recarregar(); aoMudar(); } catch (e) { erro(e); }
      } }, h("div", { class: "num-mesa" }, x.nome.replace(/^Mesa\s*/i, ""))))),
    });
  }

  try { await recarregar(); } catch (e) { erro(e); m.fechar(); }
}

// =============================================================================
// Cozinha (KDS)
// =============================================================================
export function cozinha() {
  return {
    titulo: "Cozinha",
    async render(raiz) {
      const [setores, lojaInfo] = await Promise.all([lista("/api/setores/"), get(`/api/lojas/${sessao.loja.id}/`).catch(() => ({}))]);
      const meta = Number(lojaInfo.tempo_preparo_min) || 30;
      let setorSalvo = "";
      try { setorSalvo = localStorage.getItem("apfood_kds_setor") || ""; } catch { /* ok */ }
      const sel = h("select", { "aria-label": "Setor" }, h("option", { value: "" }, "Todos os setores"), setores.map((s) => h("option", { value: s.id, selected: s.id === setorSalvo }, s.nome)));
      const area = h("div");
      const ao = indicadorAoVivo();
      const resumo = h("span", { class: "muted" });
      const tv = h("button", { type: "button", class: "botao", onclick: alternarTv }, "📺 Modo TV");
      sel.addEventListener("change", () => { try { localStorage.setItem("apfood_kds_setor", sel.value); } catch { /* ok */ } carregar(); });
      trocar(raiz, h("div", { class: "barra-ferramentas kds-barra" }, sel, resumo, h("span", { class: "espaco" }), ao.el, tv), area);
      let conhecidos = null;
      let itensAtuais = [];

      function alternarTv() {
        const ligado = document.body.classList.toggle("kds-tv");
        tv.textContent = ligado ? "Sair do modo TV" : "📺 Modo TV";
        try { if (ligado) document.documentElement.requestFullscreen?.(); else if (document.fullscreenElement) document.exitFullscreen(); } catch { /* ok */ }
      }
      const sairTela = () => { if (!document.fullscreenElement && document.body.classList.contains("kds-tv")) alternarTv(); };
      document.addEventListener("fullscreenchange", sairTela);

      function cor(min) { return min >= meta ? "atrasado" : min >= meta * 0.7 ? "atencao" : "no-prazo"; }
      function tipoTxt(p) {
        if (p.mesa) return `🍽️ Mesa ${p.mesa}`;
        return { ENTREGA: "🛵 Entrega", RETIRADA: "🛍️ Retirada", CONSUMO_LOCAL: "🍽️ Balcão" }[p.tipo_atendimento] || "";
      }
      function desenhar() {
        const porPedido = new Map();
        for (const i of itensAtuais) {
          if (!porPedido.has(i.pedido.id)) porPedido.set(i.pedido.id, { pedido: i.pedido, itens: [] });
          porPedido.get(i.pedido.id).itens.push(i);
        }
        const pedidos = [...porPedido.values()];
        resumo.textContent = pedidos.length ? `${pedidos.length} pedido(s) na fila · meta ${meta} min` : "";
        trocar(area, pedidos.length ? h("div", { class: "kds" }, pedidos.map(({ pedido: p, itens }) => {
          const min = minutosDesde(p.aceito_em || p.criado_em);
          const emPreparo = itens.some((i) => i.status_producao === "EM_PREPARO");
          return h("div", { class: `kds-comanda ${cor(min)}` },
            h("div", { class: "kds-cab" },
              h("span", { class: "kds-num" }, `#${p.numero ?? ""}${p.senha ? ` · senha ${p.senha}` : ""}`),
              h("span", { class: "kds-tempo" }, `${min} min`)),
            h("div", { class: "kds-tipo" }, tipoTxt(p), p.nome_cliente ? ` · ${p.nome_cliente}` : ""),
            p.observacao ? h("div", { class: "kds-obs" }, `⚠️ ${p.observacao}`) : null,
            h("ul", { class: "kds-itens" }, itens.map((i) => h("li", { class: i.status_producao },
              h("button", { type: "button", class: "kds-item-btn", title: i.status_producao === "AGUARDANDO" ? "Começar este item" : "Item pronto",
                onclick: async () => { await post(`/api/cozinha/${i.id}/avancar/`); carregar(); } },
                h("span", { class: "kds-qtd" }, `${i.quantidade}×`),
                h("span", null, h("strong", null, `${i.nome_produto}${i.nome_variacao ? ` (${i.nome_variacao})` : ""}`),
                  i.sabores?.length ? h("div", null, i.sabores.map((s) => s.nome).join(" / ")) : null,
                  i.adicionais?.length ? h("div", { class: "kds-ad" }, i.adicionais.map((a) => `+ ${a.quantidade > 1 ? `${a.quantidade}× ` : ""}${a.nome}`).join(", ")) : null,
                  i.observacao ? h("div", { class: "kds-obs-item" }, i.observacao) : null),
                h("span", { class: "kds-st" }, i.status_producao === "EM_PREPARO" ? "🔥" : ""))))),
            h("div", { class: "kds-acoes" },
              emPreparo ? null : botaoAcao("Começar", async () => {
                for (const i of itens.filter((x) => x.status_producao === "AGUARDANDO")) await post(`/api/cozinha/${i.id}/avancar/`);
                carregar();
              }, "botao"),
              botaoAcao("✓ Pronto", async () => {
                await post(`/api/cozinha/pedido/${p.id}/pronto/`, { setor: sel.value || null });
                carregar();
              }, "botao botao-ok")));
        })) : h("div", { class: "cartao vazio kds-vazio" }, "Nenhum pedido na fila. 🎉"));
      }
      async function carregar() {
        try {
          itensAtuais = await get(`/api/cozinha/${sel.value ? `?setor=${sel.value}` : ""}`);
          const ids = new Set(itensAtuais.map((i) => i.pedido.id));
          if (conhecidos && [...ids].some((id) => !conhecidos.has(id))) bipe();  // chegou pedido novo na fila
          conhecidos = ids;
          desenhar();
        } catch (e) { erro(e); }
      }
      await carregar();
      const parar = atualizarAoVivo(carregar, 10000);
      const relogio = setInterval(desenhar, 30000);  // os minutos andam mesmo sem mudança
      return () => {
        parar(); ao.parar(); clearInterval(relogio);
        document.removeEventListener("fullscreenchange", sairTela);
        document.body.classList.remove("kds-tv");
      };
    },
  };
}

// =============================================================================
// Caixa
// =============================================================================
export function abrirCaixaModal() {
  return new Promise((resolve) => {
    let r = null;
    const valor = h("input", { type: "text", inputmode: "decimal", placeholder: "0,00" });
    const mm = modal({
      titulo: "Abrir caixa", tamanho: "modal-pequeno",
      corpo: h("label", { class: "campo" }, h("span", null, "Dinheiro na gaveta (troco inicial)"), valor),
      rodape: [botaoAcao("Abrir caixa", async () => {
        r = await post("/api/turnos/abrir/", { id: uuid(), valor_abertura_centavos: centavos(valor.value) });
        aviso("Caixa aberto.", "ok");
        mm.fechar();
      }, "botao botao-primario")],
      aoFechar: () => resolve(r),
    });
  });
}

const FORMAS_CONFERENCIA = ["DINHEIRO", "PIX", "CARTAO_DEBITO", "CARTAO_CREDITO", "VOUCHER", "OUTRO"];

export function caixa() {
  return {
    titulo: "Caixa",
    async render(raiz) {
      const area = h("div");
      trocar(raiz, area);

      async function carregar() {
        let t = null;
        try { t = await get("/api/turnos/atual/"); } catch { t = null; }
        if (t && t.loja !== sessao.loja?.id) t = null;
        limpar(area);
        if (!t) {
          area.append(h("div", { class: "cartao", style: { maxWidth: "520px" } },
            h("h2", null, "Seu caixa está fechado"),
            h("p", { class: "muted" }, "Abra o caixa para receber pagamentos no PDV e nas mesas."),
            botaoAcao("Abrir caixa", async () => { if (await abrirCaixaModal()) carregar(); }, "botao botao-primario botao-grande")));
        } else {
          area.append(painelTurno(t, carregar, true));
        }
        const rep = await get("/api/repasses-entregador/").catch(() => null);
        if (rep) area.append(cartaoRepasses(rep, !!t, carregar));
        area.append(await cartaoImprimirFechamento());
        if (ehGerente()) {
          const abertos = (await lista("/api/turnos/", { status: "ABERTO" })).filter((x) => x.loja === sessao.loja?.id && x.id !== t?.id);
          if (abertos.length) {
            area.append(h("div", { class: "cartao" }, h("h2", null, "Outros caixas abertos nesta loja"),
              tabela([
                { rotulo: "Aberto em", valor: (x) => dataHora(x.aberto_em) },
                { rotulo: "Abertura", classe: "num", valor: (x) => dinheiro(x.valor_abertura_centavos) },
              ], abertos, { aoClicar: async (x) => {
                const res = await get(`/api/turnos/${x.id}/resumo/`);
                const mm = modal({ titulo: `Caixa de ${res.operador}`, corpo: painelTurno({ ...x, resumo: res }, () => { mm.fechar(); carregar(); }, false), tamanho: "modal-grande" });
              } })));
          }
        }
      }
      await carregar();
    },
  };
}

// Imprimir fechamento: cada operador o(s) seu(s) do dia; o administrador escolhe um operador ou todos de uma vez
async function cartaoImprimirFechamento() {
  const { campoData } = await import("./novidades.js");
  const { imprimirLinhas, qsLargura, app, configurarImpressoraApp } = await import("./comum.js");
  const dia = campoData();
  const op = h("select", { "aria-label": "Operador" }, h("option", { value: "" }, "Todos os operadores"));
  const listaEl = h("div");
  const gerente = ehGerente();
  async function buscar(extra = "") {
    if (!dia.valida()) { erro("Digite a data no formato DD/MM/AAAA."); return null; }
    const q = new URLSearchParams({ data: dia.value });
    if (gerente && op.value) q.set("usuario", op.value);
    return get(`/api/turnos/fechamentos/?${q}${extra}&${qsLargura()}`);
  }
  async function listar() {
    const r = await buscar();
    if (!r) return;
    if (gerente && op.options.length === 1) r.operadores.forEach((o) => op.append(h("option", { value: o.id }, o.nome)));
    trocar(listaEl, r.turnos.length ? tabela([
      { rotulo: "Operador", campo: "operador" },
      { rotulo: "Aberto", valor: (x) => dataHora(x.aberto_em) },
      { rotulo: "Fechado", valor: (x) => dataHora(x.fechado_em) },
      { rotulo: "", classe: "acoes-linha", valor: (x) => botaoAcao("🖨️ Imprimir", async () => {
        const c = await get(`/api/turnos/${x.id}/cupom/?${qsLargura()}`);
        imprimirLinhas(c.linhas);
      }, "botao botao-pequeno") },
    ], r.turnos) : h("p", { class: "muted" }, gerente ? "Nenhum caixa fechado nesse dia." : "Você não fechou caixa nesse dia."));
  }
  dia.addEventListener("change", listar);
  op.addEventListener("change", listar);
  const imprimirTodos = botaoAcao(gerente ? "🖨️ Imprimir de uma vez" : "🖨️ Imprimir meus fechamentos", async () => {
    const r = await buscar("&cupom=1");
    if (r) imprimirLinhas(r.linhas);
  }, "botao botao-primario");
  const cartao = h("div", { class: "cartao", style: { marginTop: "16px" } },
    h("div", { class: "pedido-topo" }, h("h2", { style: { margin: 0 } }, "🖨️ Imprimir fechamento de caixa"),
      app.bridge() ? botaoAcao("⚙️ Impressora", () => configurarImpressoraApp(), "botao botao-pequeno") : null),
    h("p", { class: "muted" }, gerente ? "Escolha o dia e o operador (ou todos os operadores, um cupom atrás do outro)."
      : "Escolha o dia para reimprimir o seu fechamento."),
    h("div", { class: "barra-ferramentas", style: { flexWrap: "wrap" } },
      h("label", { class: "campo", style: { maxWidth: "150px" } }, h("span", null, "Dia"), dia),
      gerente ? h("label", { class: "campo", style: { minWidth: "200px" } }, h("span", null, "Operador"), op) : null,
      h("button", { type: "button", class: "botao", onclick: listar }, "Ver"), imprimirTodos),
    listaEl,
    gerente ? h("p", { style: { marginTop: "10px" } }, h("a", { href: "#/faturamento" }, "📊 Relatório de faturamento por período (imprimir) →")) : null);
  listar().catch(() => {});
  return cartao;
}

// Dinheiro que os entregadores cobraram na porta: o entregador informa o repasse, a loja confere digitando o que recebeu
function cartaoRepasses(r, caixaAberto, recarregar) {
  if (!r.aguardando.length && !r.com_entregadores.length && !r.recebidos.length) return h("span");
  const receber = (alvo) => {
    const esperado = alvo.esperado_centavos ?? alvo.em_maos_centavos;
    const valor = h("input", { type: "text", inputmode: "decimal", placeholder: "0,00" });
    const obs = h("input", { type: "text", placeholder: "Opcional" });
    const m = modal({
      titulo: `Receber de ${alvo.entregador}`, tamanho: "modal-pequeno",
      corpo: h("div", { class: "grade" },
        h("ul", { class: "lista-simples" },
          h("li", null, "Cobrado nas entregas", h("span", { class: "num" }, dinheiro(esperado))),
          alvo.informado_entregador_centavos != null
            ? h("li", null, "O entregador informou", h("span", { class: "num" }, dinheiro(alvo.informado_entregador_centavos)))
            : h("li", { class: "muted" }, "O entregador ainda não informou o repasse no app.")),
        h("label", { class: "campo" }, h("span", null, "Quanto você recebeu (conte o dinheiro) R$"), valor),
        h("label", { class: "campo" }, h("span", null, "Observação"), obs),
        h("p", { class: "muted" }, "O valor entra no seu caixa aberto. Se for diferente, a diferença fica registrada e entra no acerto do entregador.")),
      rodape: [botaoAcao("Confirmar recebimento", async () => {
        const v = centavos(valor.value);
        if (!valor.value.trim()) { erro("Digite o valor recebido."); return; }
        const res = await post("/api/repasses-entregador/", { repasse_id: alvo.id && alvo.esperado_centavos != null ? alvo.id : null,
          entregador_id: alvo.entregador_id, valor_centavos: v, observacao: obs.value.trim() });
        m.fechar();
        aviso(res.diferenca_centavos ? `Recebido com diferença de ${dinheiro(res.diferenca_centavos)}.` : "Repasse recebido. Confere!", res.diferenca_centavos ? "erro" : "ok");
        recarregar();
      }, "botao botao-primario")],
    });
    setTimeout(() => valor.focus(), 50);
  };
  const botao = (x) => (caixaAberto ? botaoAcao("Receber", () => receber(x), "botao botao-primario botao-pequeno")
    : h("span", { class: "muted" }, "abra o caixa"));
  return h("div", { class: "cartao", style: { marginTop: "16px" } }, h("h2", null, "💵 Dinheiro dos entregadores"),
    h("p", { class: "muted" }, "Dinheiro que os entregadores cobraram na entrega. Eles informam o repasse no app; aqui você confere digitando quanto recebeu."),
    r.aguardando.length ? h("div", null, h("h3", null, "Repasses para conferir"), tabela([
      { rotulo: "Entregador", valor: (x) => h("strong", null, x.entregador) },
      { rotulo: "Informado em", valor: (x) => dataHora(x.informado_em) },
      { rotulo: "Entregas", classe: "num", campo: "entregas" },
      { rotulo: "Cobrado", classe: "num", valor: (x) => dinheiro(x.esperado_centavos) },
      { rotulo: "Entregador diz", classe: "num", valor: (x) => h("strong", { style: { color: x.informado_entregador_centavos !== x.esperado_centavos ? "var(--erro)" : "" } }, dinheiro(x.informado_entregador_centavos)) },
      { rotulo: "", classe: "acoes-linha", valor: botao },
    ], r.aguardando)) : null,
    r.com_entregadores.length ? h("div", null, h("h3", null, "Ainda com o entregador"), tabela([
      { rotulo: "Entregador", valor: (x) => h("strong", null, x.entregador) },
      { rotulo: "Entregas", classe: "num", campo: "entregas" },
      { rotulo: "Em mãos", classe: "num", valor: (x) => dinheiro(x.em_maos_centavos) },
      { rotulo: "", classe: "acoes-linha", valor: botao },
    ], r.com_entregadores)) : null,
    r.recebidos.length ? h("details", null, h("summary", null, "Últimos recebidos"), tabela([
      { rotulo: "Quando", valor: (x) => dataHora(x.recebido_em) },
      { rotulo: "Entregador", campo: "entregador" },
      { rotulo: "Cobrado", classe: "num", valor: (x) => dinheiro(x.esperado_centavos) },
      { rotulo: "Entregador disse", classe: "num", valor: (x) => (x.informado_entregador_centavos == null ? "—" : dinheiro(x.informado_entregador_centavos)) },
      { rotulo: "Loja recebeu", classe: "num", valor: (x) => dinheiro(x.recebido_loja_centavos) },
      { rotulo: "Situação", valor: (x) => h("span", { style: { color: x.status === "DIVERGENTE" ? "var(--erro)" : "" } },
        x.status_rotulo + (x.diferenca_centavos ? ` (${x.diferenca_centavos > 0 ? "+" : ""}${dinheiro(x.diferenca_centavos)})` : "")) },
      { rotulo: "Por", campo: "recebido_por" },
    ], r.recebidos)) : null);
}

function painelTurno(t, recarregar, meu) {
  const r = t.resumo || {};
  const tot = r.totais_por_tipo || {};
  const caixaEl = h("div", { class: "grade" },
    h("div", { class: "grade grade-kpi" },
      kpi("Aberto desde", dataHora(t.aberto_em), r.operador),
      kpi("Troco inicial", dinheiro(t.valor_abertura_centavos)),
      kpi("Vendas", String(r.quantidade_vendas ?? 0), dinheiro(tot.VENDA || 0)),
      kpi("Sangrias / suprimentos", `${dinheiro(tot.SANGRIA || 0)}`, `+ ${dinheiro(tot.SUPRIMENTO || 0)} suprimento`)),
    r.esperado ? h("div", { class: "cartao" }, h("h2", null, "Esperado em caixa"),
      h("ul", { class: "lista-simples" }, Object.entries(r.esperado).map(([f, v]) => h("li", null, rotulo("FormaPagamento", f), h("span", { class: "num" }, dinheiro(v))))))
      : h("p", { class: "muted" }, "Conferência cega: os valores esperados aparecem depois do fechamento."),
    r.delivery ? cartaoDelivery(r.delivery, "Delivery neste caixa") : null,
    h("div", { class: "acoes" },
      botaoAcao("Sangria (retirada)", () => movimento(t, "SANGRIA", recarregar)),
      botaoAcao("Suprimento (reforço)", () => movimento(t, "SUPRIMENTO", recarregar)),
      botaoAcao("Despesa paga do caixa", () => despesaCaixa(t, recarregar)),
      h("span", { style: { flex: 1 } }),
      botaoAcao(meu ? "Fechar meu caixa" : "Fechar este caixa", () => fechar(t, recarregar), "botao botao-primario")));
  return caixaEl;
}

async function movimento(t, tipo, recarregar) {
  const valor = h("input", { type: "text", inputmode: "decimal", placeholder: "0,00" });
  const motivo = h("input", { type: "text", placeholder: "Motivo" });
  const mm = modal({
    titulo: tipo === "SANGRIA" ? "Sangria" : "Suprimento", tamanho: "modal-pequeno",
    corpo: h("div", { class: "grade" }, h("label", { class: "campo" }, h("span", null, "Valor (R$)"), valor), h("label", { class: "campo" }, h("span", null, "Motivo"), motivo)),
    rodape: [botaoAcao("Registrar", async () => {
      await post(`/api/turnos/${t.id}/movimentos/`, { id: uuid(), tipo, valor_centavos: centavos(valor.value), motivo: motivo.value.trim() });
      aviso("Registrado.", "ok"); mm.fechar(); recarregar();
    }, "botao botao-primario")],
  });
}

async function despesaCaixa(t, recarregar) {
  const cats = await lista("/api/categorias-despesa/").catch(() => []);
  const descricao = h("input", { type: "text", placeholder: "Ex.: gás, gelo, motoboy" });
  const valor = h("input", { type: "text", inputmode: "decimal", placeholder: "0,00" });
  const cat = h("select", null, h("option", { value: "" }, "Sem categoria"), cats.map((c) => h("option", { value: c.id }, c.nome)));
  const mm = modal({
    titulo: "Despesa paga com dinheiro do caixa", tamanho: "modal-pequeno",
    corpo: h("div", { class: "grade" }, h("label", { class: "campo" }, h("span", null, "Descrição"), descricao),
      h("label", { class: "campo" }, h("span", null, "Valor (R$)"), valor), h("label", { class: "campo" }, h("span", null, "Categoria"), cat)),
    rodape: [botaoAcao("Registrar", async () => {
      await post(`/api/turnos/${t.id}/despesas/`, { id: uuid(), descricao: descricao.value.trim(), valor_centavos: centavos(valor.value), categoria: cat.value || null });
      aviso("Despesa registrada.", "ok"); mm.fechar(); recarregar();
    }, "botao botao-primario")],
  });
}

function fechar(t, recarregar) {
  const entradas = Object.fromEntries(FORMAS_CONFERENCIA.map((f) => [f, h("input", { type: "text", inputmode: "decimal", placeholder: "0,00" })]));
  const obs = h("textarea", { rows: 2 });
  const mm = modal({
    titulo: "Fechar caixa",
    corpo: h("div", { class: "grade" },
      h("p", { class: "muted" }, "Conte a gaveta e os comprovantes e informe o total de cada forma de pagamento."),
      h("div", { class: "form-grade" }, FORMAS_CONFERENCIA.map((f) => h("label", { class: "campo" }, h("span", null, rotulo("FormaPagamento", f)), entradas[f]))),
      h("label", { class: "campo" }, h("span", null, "Observação"), obs)),
    rodape: [botaoAcao("Fechar caixa", async () => {
      if (!(await confirmar("Fechar o caixa agora? Depois não dá para lançar mais vendas nele."))) return;
      const informado = Object.fromEntries(FORMAS_CONFERENCIA.map((f) => [f, centavos(entradas[f].value)]));
      const r = await post(`/api/turnos/${t.id}/fechar/`, { informado, tipo_conferencia: "CEGA", observacao: obs.value.trim() });
      mm.fechar();
      const resultado = modal({
        titulo: "Caixa fechado",
        corpo: h("div", { class: "grade" },
          h("div", { class: `alerta ${r.diferenca_centavos === 0 ? "alerta-ok" : r.diferenca_centavos > 0 ? "alerta-info" : "alerta-erro"}` },
            r.diferenca_centavos === 0 ? "Caixa conferido: bateu certinho." : r.diferenca_centavos > 0 ? `Sobra de ${dinheiro(r.diferenca_centavos)}` : `Falta de ${dinheiro(-r.diferenca_centavos)}`),
          tabela([
            { rotulo: "Forma", valor: (l) => rotulo("FormaPagamento", l.forma_pagamento) },
            { rotulo: "Esperado", classe: "num", valor: (l) => dinheiro(l.valor_esperado_centavos) },
            { rotulo: "Informado", classe: "num", valor: (l) => dinheiro(l.valor_informado_centavos) },
            { rotulo: "Diferença", classe: "num", valor: (l) => h("span", { class: l.diferenca_centavos ? "etiqueta e-erro" : "" }, dinheiro(l.diferenca_centavos)) },
          ], r.conferencia || [])),
        rodape: [botaoAcao("Imprimir fechamento", async () => {
          const { qsLargura } = await import("./comum.js"); const c = await get(`/api/turnos/${t.id}/cupom/?${qsLargura()}`);
          imprimirLinhas(c.linhas);
        }), botaoAcao("Ver cupom", async () => { const c = await get(`/api/turnos/${t.id}/cupom/`); mostrarCupom(c.linhas, { titulo: "Fechamento de caixa" }); })],
        aoFechar: recarregar,
      });
      return resultado;
    }, "botao botao-primario")],
  });
}


// =============================================================================
// Reservas de mesa
// =============================================================================
export function reservas() {
  return {
    titulo: "Reservas",
    async render(raiz) {
      const dataSel = h("input", { type: "date", value: hojeISO() });
      const area = h("div");
      trocar(raiz, h("div", { class: "barra-ferramentas" }, dataSel,
        h("span", { class: "espaco" }), botaoAcao("+ Nova reserva", nova, "botao botao-primario")), area);
      dataSel.addEventListener("change", carregar);
      const COR = { PENDENTE: "e-alerta", CONFIRMADA: "e-ok", CANCELADA: "e-erro", CHEGOU: "e-info", NAO_VEIO: "e-erro" };
      async function carregar() {
        const rs = await lista("/api/reservas/", { data: dataSel.value });
        const pessoas = rs.filter((r) => ["PENDENTE", "CONFIRMADA", "CHEGOU"].includes(r.status)).reduce((s, r) => s + r.pessoas, 0);
        trocar(area,
          h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
            kpi("Reservas no dia", String(rs.filter((r) => r.status !== "CANCELADA").length)),
            kpi("Pessoas esperadas", String(pessoas)),
            kpi("Aguardando confirmação", String(rs.filter((r) => r.status === "PENDENTE").length))),
          rs.length ? h("div", { class: "grade", style: { gap: "10px" } }, rs.map(cartao))
            : h("div", { class: "cartao vazio" }, "Nenhuma reserva neste dia."));
      }
      function cartao(r) {
        const st = async (status) => { await post(`/api/reservas/${r.id}/status/`, { status }); aviso("Reserva atualizada.", "ok"); carregar(); };
        return h("div", { class: "cartao" },
          h("div", { class: "acoes" }, h("strong", { style: { fontSize: "18px" } }, hora(r.data_hora)),
            h("span", { class: `etiqueta ${COR[r.status] || ""}` }, r.status_rotulo), h("span", { class: "espaco", style: { flex: 1 } }),
            h("span", { class: "muted" }, r.origem === "SITE" ? "pelo site" : "no painel")),
          h("div", { style: { margin: "6px 0" } }, h("strong", null, r.nome), ` · ${r.pessoas} pessoa(s) · `,
            h("a", { href: `https://wa.me/55${r.telefone}`, target: "_blank", rel: "noopener" }, r.telefone),
            r.mesa_nome ? ` · ${r.mesa_nome}` : ""),
          r.observacao ? h("div", { class: "muted" }, `Obs.: ${r.observacao}`) : null,
          h("div", { class: "acoes", style: { marginTop: "8px" } },
            r.status === "PENDENTE" ? botaoAcao("Confirmar", () => st("CONFIRMADA"), "botao botao-ok botao-pequeno") : null,
            ["PENDENTE", "CONFIRMADA"].includes(r.status) ? botaoAcao("Mesa", () => escolherMesa(r), "botao botao-pequeno") : null,
            ["PENDENTE", "CONFIRMADA"].includes(r.status) ? botaoAcao("Chegou", () => st("CHEGOU"), "botao botao-primario botao-pequeno") : null,
            r.status === "CONFIRMADA" ? botaoAcao("Não veio", () => st("NAO_VEIO"), "botao botao-pequeno") : null,
            ["PENDENTE", "CONFIRMADA"].includes(r.status) ? botaoAcao("Cancelar", () => st("CANCELADA"), "botao botao-perigo botao-pequeno") : null));
      }
      async function escolherMesa(r) {
        const ms = await lista("/api/mesas/", { ativa: "true" });
        const sel = h("select", null, h("option", { value: "" }, "Sem mesa"), ms.map((m) => h("option", { value: m.id, selected: m.id === r.mesa }, m.nome)));
        const m = modal({ titulo: `Mesa para ${r.nome}`, tamanho: "modal-pequeno", corpo: h("label", { class: "campo" }, h("span", null, "Mesa"), sel),
          rodape: [botaoAcao("Salvar", async () => { await put(`/api/reservas/${r.id}/`, { ...r, mesa: sel.value || null }); m.fechar(); carregar(); }, "botao botao-primario")] });
      }
      function nova() {
        const f = { nome: h("input", { type: "text" }), telefone: h("input", { type: "tel" }), pessoas: h("input", { type: "number", min: 1, value: 2 }),
          dia: h("input", { type: "date", value: dataSel.value }), hora: h("input", { type: "time", value: "20:00", step: 900 }), obs: h("input", { type: "text" }) };
        const m = modal({ titulo: "Nova reserva", tamanho: "modal-pequeno",
          corpo: h("div", { class: "grade" }, ...[["Nome", f.nome], ["Celular com DDD", f.telefone], ["Pessoas", f.pessoas], ["Dia", f.dia], ["Horário", f.hora], ["Observação", f.obs]]
            .map(([r, i]) => h("label", { class: "campo" }, h("span", null, r), i))),
          rodape: [botaoAcao("Salvar", async () => {
            await post("/api/reservas/", { nome: f.nome.value, telefone: f.telefone.value, pessoas: parseInt(f.pessoas.value, 10) || 1,
              data_hora: new Date(`${f.dia.value}T${f.hora.value}:00`).toISOString(), observacao: f.obs.value });
            m.fechar(); dataSel.value = f.dia.value; carregar();
          }, "botao botao-primario")] });
      }
      await carregar();
    },
  };
}
