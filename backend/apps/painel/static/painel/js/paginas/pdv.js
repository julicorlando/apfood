// PDV no navegador: balcão e delivery, com pagamento, cupom e via da cozinha.
import { get, lista, post, sessao } from "../api.js";
import { anexar, aviso, botaoAcao, centavos, dinheiro, erro, h, limpar, modal, opcoes, trocar, uuid } from "../ui.js";
import { imprimirLinhas, imprimirPedido, mostrarCupom, receber } from "./comum.js";
import { abrirCaixaModal } from "./operacao.js";

const C = () => window.ApCarrinho;

/** Monta o cardápio no mesmo formato do cardápio público (o ApCarrinho calcula os preços). */
export async function carregarCardapio() {
  const [cats, prods, grupos, promocoes] = await Promise.all([
    lista("/api/categorias/", { ativa: "true" }),
    lista("/api/produtos/", { tipo: "VENDA", ativo: "true" }),
    lista("/api/grupos-adicionais/"),
    get("/api/promocoes/agora/").catch(() => ({})),
  ]);
  const gruposPorId = Object.fromEntries(grupos.filter((g) => g.ativo).map((g) => [g.id, {
    id: g.id, nome: g.nome, min: g.min_selecao, max: g.max_selecao,
    opcoes: (g.adicionais || []).map((a) => ({ id: a.id, nome: a.nome, preco_centavos: a.preco_centavos, max_por_item: a.max_por_item })),
  }]));
  const conv = (p) => ({
    id: p.id, nome: p.nome, preco_centavos: p.preco_centavos, variacoes: p.variacoes || [], esgotado: !!p.pausado && (!p.pausado_ate || new Date(p.pausado_ate) > new Date()),
    codigo: p.codigo, imagem: p.imagem, grupos: (p.grupos_adicionais || []).map((id) => gruposPorId[id]).filter(Boolean),
  });
  const ordem = (a, b) => (a.ordem ?? 0) - (b.ordem ?? 0) || a.nome.localeCompare(b.nome);
  const categorias = cats.sort(ordem).map((c) => ({
    id: c.id, nome: c.nome, max_sabores: c.max_sabores, regra_preco_sabores: c.regra_preco_sabores,
    produtos: prods.filter((p) => p.categoria === c.id).sort(ordem).map(conv),
  }));
  const soltos = prods.filter((p) => !p.categoria || !cats.find((c) => c.id === p.categoria)).sort(ordem).map(conv);
  if (soltos.length) categorias.push({ id: "_", nome: "Outros", max_sabores: 1, produtos: soltos });
  const cardapio = { categorias: categorias.filter((c) => c.produtos.length) };
  const idx = C().indexar(cardapio);
  idx.promocoes = promocoes || {};
  aplicarPromocoes(idx, "BALCAO");
  return { cardapio, idx };
}

/** Promoções programadas valendo agora no canal (o servidor recalcula ao salvar). */
export function aplicarPromocoes(idx, canal) {
  const mapa = (idx.promocoes || {})[canal] || {};
  for (const p of Object.values(idx.produtos)) p.promocao = mapa[p.id] || null;
}

/** Preço para mostrar no botão do produto, já com a promoção. */
export function precoProduto(p) {
  const varia = p.variacoes.length;
  const base = varia ? Math.min(...p.variacoes.map((v) => v.preco_centavos)) : p.preco_centavos;
  const d = C().descontoPromocao(p.promocao, base);
  const texto = (varia ? "a partir de " : "") + dinheiro(base - d);
  return d ? h("span", { title: p.promocao.nome }, `🔥 ${texto}`) : texto;
}

/** Modal de montagem do item (tamanho, sabores, adicionais, observação). Resolve o item ou null. */
export function montarItem(idx, produto) {
  return new Promise((resolve) => {
    let resultado = null;
    const item = { produto_id: produto.id, quantidade: 1, adicionais: [], sabores: [], observacao: "" };
    const cat = idx.categoriaDe[produto.id] || {};
    const corpo = h("div", { class: "grade" });
    const precoEl = h("strong");
    const erroEl = h("div", { class: "alerta alerta-erro", hidden: true });
    let extrasSabores = [];

    const atualizarPreco = () => {
      item.sabores = extrasSabores.length ? [produto.id, ...extrasSabores] : [];
      precoEl.textContent = dinheiro(C().precificar(idx, item).total);
    };

    const blocoVariacoes = produto.variacoes.length ? h("div", null, h("h3", null, "Tamanho"),
      h("div", { class: "opcoes-lista" }, produto.variacoes.map((v) => {
        const b = h("button", { type: "button", class: "opcao" }, h("span", null, v.nome), h("span", null, dinheiro(v.preco_centavos)));
        b.addEventListener("click", () => {
          item.variacao_id = v.id;
          b.parentElement.querySelectorAll(".opcao").forEach((x) => x.classList.toggle("marcada", x === b));
          extrasSabores = [];
          desenharSabores();
          atualizarPreco();
        });
        return b;
      }))) : null;

    const blocoSabores = h("div");
    function desenharSabores() {
      limpar(blocoSabores);
      const max = Math.max(1, cat.max_sabores || 1);
      if (max < 2) return;
      const nomeVar = produto.variacoes.find((v) => v.id === item.variacao_id)?.nome || null;
      if (produto.variacoes.length && !nomeVar) return;
      const compat = C().saboresCompativeis(idx, produto, nomeVar);
      if (!compat.length) return;
      blocoSabores.append(h("h3", null, `Outros sabores (até ${max - 1})`),
        h("div", { class: "chips" }, compat.map((s) => {
          const b = h("button", { type: "button", class: "chip" }, s.nome);
          b.addEventListener("click", () => {
            const i = extrasSabores.indexOf(s.id);
            if (i >= 0) extrasSabores.splice(i, 1);
            else if (extrasSabores.length < max - 1) extrasSabores.push(s.id);
            b.classList.toggle("marcado", extrasSabores.includes(s.id));
            atualizarPreco();
          });
          return b;
        })));
    }

    const blocoGrupos = produto.grupos.map((g) => {
      const doGrupo = (a) => g.opcoes.some((x) => x.id === a.adicional_id);
      const ui = new Map();
      const pintar = () => {
        for (const o of g.opcoes) {
          const q = item.adicionais.find((a) => a.adicional_id === o.id)?.quantidade || 0;
          ui.get(o.id).qtdEl.textContent = String(q);
          ui.get(o.id).linha.classList.toggle("marcada", q > 0);
        }
      };
      const mudar = (o, d) => {
        const atual = item.adicionais.find((a) => a.adicional_id === o.id)?.quantidade || 0;
        const noGrupo = item.adicionais.filter(doGrupo).reduce((s, a) => s + a.quantidade, 0);
        let q = atual + d;
        if (q < 0 || q > (o.max_por_item || 1)) return;
        if (d > 0 && noGrupo >= g.max) {
          if (g.max !== 1) return;
          item.adicionais = item.adicionais.filter((a) => !doGrupo(a)); // escolha única: troca
          q = 1;
        }
        item.adicionais = item.adicionais.filter((a) => a.adicional_id !== o.id);
        if (q > 0) item.adicionais.push({ adicional_id: o.id, quantidade: q });
        pintar();
        atualizarPreco();
      };
      const listaEl = h("div", { class: "opcoes-lista" }, g.opcoes.map((o) => {
        const qtdEl = h("span", { class: "negrito" }, "0");
        const linha = h("div", { class: "opcao" },
          h("span", { style: { flex: 1, cursor: "pointer" }, onclick: () => mudar(o, 1) },
            o.nome, o.preco_centavos ? h("span", { class: "muted" }, ` + ${dinheiro(o.preco_centavos)}`) : null),
          h("span", { class: "qtd" },
            h("button", { type: "button", onclick: () => mudar(o, -1), "aria-label": `Menos ${o.nome}` }, "−"), qtdEl,
            h("button", { type: "button", onclick: () => mudar(o, 1), "aria-label": `Mais ${o.nome}` }, "+")));
        ui.set(o.id, { qtdEl, linha });
        return linha;
      }));
      return h("div", null,
        h("h3", null, g.nome, h("span", { class: "muted", style: { fontWeight: 400 } },
          g.min ? ` — obrigatório (${g.min === g.max ? g.min : `${g.min} a ${g.max}`})` : ` — opcional, até ${g.max}`)),
        listaEl);
    });

    const obs = h("input", { type: "text", placeholder: "Ex.: sem cebola", maxlength: 255 });
    obs.addEventListener("input", () => { item.observacao = obs.value; });
    const qtd = h("input", { type: "number", min: 1, value: 1, style: { maxWidth: "90px" } });
    qtd.addEventListener("input", () => { item.quantidade = Math.max(1, parseInt(qtd.value, 10) || 1); atualizarPreco(); });

    anexar(corpo, [erroEl, blocoVariacoes, blocoSabores, ...blocoGrupos,
      h("label", { class: "campo" }, h("span", null, "Observação"), obs),
      h("label", { class: "campo" }, h("span", null, "Quantidade"), qtd)]);
    desenharSabores();
    atualizarPreco();

    const ok = h("button", { type: "button", class: "botao botao-primario botao-grande" }, "Adicionar ", precoEl);
    ok.addEventListener("click", () => {
      atualizarPreco();
      const erros = C().validar(idx, item);
      if (erros.length) { erroEl.textContent = erros.join(" · "); erroEl.hidden = false; return; }
      resultado = { ...item, sabores: [...item.sabores], adicionais: item.adicionais.map((a) => ({ ...a })) };
      m.fechar();
    });
    const m = modal({ titulo: produto.nome, corpo, rodape: [ok], aoFechar: () => resolve(resultado) });
  });
}

export function pdv() {
  return {
    titulo: "PDV",
    async render(raiz) {
      const { idx, cardapio } = await carregarCardapio();
      let turno = null;
      try {
        turno = await get("/api/turnos/atual/");
        if (turno.loja !== sessao.loja?.id) turno = null;
      } catch { turno = null; }

      const estado = {
        itens: [], modo: "LOCAL", categoria: cardapio.categorias[0]?.id, busca: "",
        cliente: { nome: "", telefone: "" }, endereco: null, taxa: 0, desconto: 0, cupom: "", observacao: "", cpf: "",
        senha: "", origem: "TELEFONE", previsto: "DINHEIRO", trocoPara: "",
        saldoCashback: 0, usarCashback: false, mesa: null,
      };
      let mesasPdv = null;  // { mesas, comandas } — carregado ao escolher o modo Mesa

      const avisoCaixa = h("div");
      const desenharAvisoCaixa = () => {
        limpar(avisoCaixa);
        if (!turno) {
          avisoCaixa.append(h("div", { class: "alerta alerta-aviso acoes pdv-caixa-fechado", style: { marginBottom: "12px" } },
            h("span", { style: { flex: 1 } }, "Seu caixa está fechado: abra para receber pagamentos."),
            botaoAcao("Abrir caixa", async () => {
              const t = await abrirCaixaModal();
              if (t) { turno = t; desenharAvisoCaixa(); }
            }, "botao botao-primario botao-pequeno")));
        }
      };
      desenharAvisoCaixa();

      // ---------- catálogo
      const busca = h("input", { type: "search", placeholder: "Buscar produto ou código…", "aria-label": "Buscar produto" });
      const cats = h("div", { class: "pdv-categorias" });
      const grade = h("div", { class: "pdv-produtos" });
      const desenharCatalogo = () => {
        trocar(cats, cardapio.categorias.map((c) => h("button", {
          type: "button", class: !estado.busca && c.id === estado.categoria ? "ativa" : "",
          onclick: () => { estado.categoria = c.id; estado.busca = ""; busca.value = ""; desenharCatalogo(); },
        }, c.nome)));
        const termo = estado.busca.toLowerCase();
        const produtos = termo
          ? cardapio.categorias.flatMap((c) => c.produtos).filter((p) => p.nome.toLowerCase().includes(termo) || (p.codigo || "").toLowerCase() === termo)
          : cardapio.categorias.find((c) => c.id === estado.categoria)?.produtos || [];
        trocar(grade, produtos.length ? produtos.map((p) => h("button", {
          type: "button", class: "pdv-produto", disabled: p.esgotado, onclick: () => escolher(p),
        }, h("span", { class: "nome" }, p.nome),
        p.esgotado ? h("span", { class: "etiqueta e-alerta" }, "Esgotado") : null,
        h("span", { class: "preco" }, precoProduto(p))))
          : h("div", { class: "vazio" }, cardapio.categorias.length ? "Nenhum produto." : "Cadastre produtos em Cardápio → Produtos."));
      };
      busca.addEventListener("input", () => { estado.busca = busca.value.trim(); desenharCatalogo(); });
      busca.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter") return;
        const termo = busca.value.trim().toLowerCase();
        const exato = cardapio.categorias.flatMap((c) => c.produtos).find((p) => (p.codigo || "").toLowerCase() === termo);
        if (exato) { escolher(exato); busca.value = ""; estado.busca = ""; desenharCatalogo(); }
      });

      async function escolher(p) {
        const simples = !p.variacoes.length && !p.grupos.length && (idx.categoriaDe[p.id]?.max_sabores || 1) < 2;
        const item = simples ? { produto_id: p.id, quantidade: 1, adicionais: [], sabores: [], observacao: "" } : await montarItem(idx, p);
        if (!item) return;
        const igual = simples && estado.itens.find((i) => i.produto_id === p.id && !i.adicionais.length && !i.variacao_id && !i.observacao);
        if (igual) igual.quantidade += 1; else estado.itens.push(item);
        desenharCarrinho();
      }

      // ---------- carrinho
      const carrinho = h("div", { class: "cartao pdv-carrinho" });
      const modos = [["LOCAL", "Comer aqui"], ["MESA", "Mesa"], ["RETIRADA", "Para viagem"], ["DELIVERY", "Delivery"]];
      const estreita = () => matchMedia("(max-width: 1000px)").matches;
      const fundoCarrinho = h("div", { class: "pdv-fundo", onclick: () => fecharCarrinho() });
      function abrirCarrinho() {
        if (!estreita()) { carrinho.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
        carrinho.classList.add("aberto"); fundoCarrinho.classList.add("aberto");
      }
      function fecharCarrinho() { carrinho.classList.remove("aberto"); fundoCarrinho.classList.remove("aberto"); }
      const irCarrinho = h("button", { type: "button", class: "pdv-ir-carrinho", onclick: abrirCarrinho });
      const canalPromo = (m) => (m === "DELIVERY" ? "DELIVERY" : m === "MESA" ? "MESA" : "BALCAO");

      function totais() {
        const taxa = estado.modo === "DELIVERY" ? estado.taxa : 0;
        const base = C().totais(idx, estado.itens, taxa, estado.desconto);
        const cashback = estado.usarCashback ? Math.min(estado.saldoCashback, base.total) : 0;
        const t = C().totais(idx, estado.itens, taxa, estado.desconto + cashback);
        t.cashback = cashback;
        return t;
      }

      async function buscarCliente(telefone) {
        const achados = await get(`/api/clientes/por-telefone/?telefone=${encodeURIComponent(telefone.replace(/\D/g, ""))}`);
        const c = achados[0];
        estado.saldoCashback = c?.saldo_cashback_centavos || 0;
        estado.usarCashback = false;
        return c;
      }

      function blocoCashback() {
        if (!estado.saldoCashback) return null;
        const marca = h("input", { type: "checkbox", checked: estado.usarCashback });
        marca.addEventListener("change", () => { estado.usarCashback = marca.checked; desenharCarrinho(); });
        return h("label", { class: "check alerta alerta-ok", style: { margin: "6px 0" } }, marca,
          h("span", null, `Usar cashback do cliente (saldo ${dinheiro(estado.saldoCashback)})`));
      }

      function desenharCarrinho() {
        const t = totais();
        const blocoModo = h("div", { class: "abas", style: { marginBottom: "8px" } }, modos.map(([v, r]) => h("button", {
          type: "button", class: estado.modo === v ? "ativa" : "", onclick: () => {
            estado.modo = v;
            aplicarPromocoes(idx, canalPromo(v));
            if (v === "MESA" && !mesasPdv) carregarMesas().catch(erro);
            desenharCarrinho();
            desenharCatalogo();
          },
        }, r)));
        const itens = h("div", { class: "pdv-itens" }, estado.itens.length ? estado.itens.map((i, n) => {
          const d = C().descrever(idx, i);
          const preco = C().precificar(idx, i);
          return h("div", { class: "pdv-item" },
            h("div", { class: "info" }, h("div", { class: "negrito" }, d.titulo),
              d.detalhe ? h("div", { class: "detalhe" }, d.detalhe) : null,
              i.observacao ? h("div", { class: "detalhe" }, `Obs.: ${i.observacao}`) : null,
              h("div", { class: "qtd", style: { marginTop: "4px" } },
                h("button", { type: "button", "aria-label": "Menos", onclick: () => { i.quantidade -= 1; if (i.quantidade <= 0) estado.itens.splice(n, 1); desenharCarrinho(); } }, "−"),
                h("span", null, String(i.quantidade)),
                h("button", { type: "button", "aria-label": "Mais", onclick: () => { i.quantidade += 1; desenharCarrinho(); } }, "+"))),
            h("div", { class: "num negrito" }, dinheiro(preco.total)));
        }) : h("div", { class: "vazio" }, "Toque nos produtos para adicionar."));

        const cliente = blocoCliente();
        trocar(carrinho, 
          h("div", { class: "pdv-carrinho-topo" }, h("h2", null, "Pedido"),
            h("button", { type: "button", class: "botao botao-pequeno", "aria-label": "Fechar", onclick: fecharCarrinho }, "Continuar vendendo")),
          blocoModo, cliente, itens,
          h("ul", { class: "lista-simples" },
            h("li", null, "Subtotal", h("span", { class: "num" }, dinheiro(t.subtotal))),
            estado.modo === "DELIVERY" ? h("li", null, "Entrega", h("span", { class: "num" }, dinheiro(t.taxa))) : null,
            t.desconto ? h("li", null, t.cashback ? "Desconto (inclui cashback)" : "Desconto", h("span", { class: "num" }, `− ${dinheiro(t.desconto)}`)) : null),
          h("div", { class: "pdv-total" }, h("span", null, "Total"), h("span", null, dinheiro(t.total))),
          h("div", { class: "acoes" },
            h("button", { type: "button", class: "botao botao-pequeno", onclick: ajustes }, "Desconto, cupom, obs."),
            estado.itens.length ? h("button", { type: "button", class: "botao botao-pequeno botao-perigo", onclick: () => { estado.itens = []; desenharCarrinho(); } }, "Limpar") : null),
          h("div", { style: { marginTop: "10px" } }, botaoAcao(estado.modo === "MESA" ? "Enviar para a mesa" : "Finalizar venda", finalizar, "botao botao-primario botao-grande botao-bloco")),
        );
        const qtd = estado.itens.reduce((n, i) => n + i.quantidade, 0);
        if (qtd) irCarrinho.removeAttribute("data-vazio"); else { irCarrinho.setAttribute("data-vazio", ""); fecharCarrinho(); }
        trocar(irCarrinho, h("span", null, `Ver pedido · ${qtd} ${qtd === 1 ? "item" : "itens"}`), h("span", null, dinheiro(t.total)));
      }

      // ---------- mesa: o pedido entra na conta (comanda) da mesa
      async function carregarMesas() {
        const [ms, cs] = await Promise.all([lista("/api/mesas/", { ativa: "true" }), lista("/api/comandas/", { abertas: 1 })]);
        mesasPdv = { mesas: ms.sort((a, b) => (a.ordem ?? 0) - (b.ordem ?? 0) || a.nome.localeCompare(b.nome)), comandas: cs };
        if (estado.mesa?.comandaId && !cs.find((c) => c.id === estado.mesa.comandaId)) estado.mesa = null;
        desenharCarrinho();
      }

      function blocoMesa() {
        if (!mesasPdv) return h("div", { class: "muted", style: { margin: "6px 0 10px" } }, "Carregando mesas…");
        const porMesa = new Map(mesasPdv.comandas.filter((c) => c.mesa).map((c) => [c.mesa, c]));
        const atual = estado.mesa ? (estado.mesa.comandaId && !estado.mesa.mesaId ? `c:${estado.mesa.comandaId}` : `m:${estado.mesa.mesaId}`) : "";
        const sel = h("select", { "aria-label": "Mesa ou comanda" },
          h("option", { value: "" }, "Escolha a mesa…"),
          mesasPdv.mesas.map((m) => {
            const c = porMesa.get(m.id);
            return h("option", { value: `m:${m.id}`, selected: atual === `m:${m.id}` },
              `${m.nome}${c ? ` — ocupada · ${dinheiro(c.total_centavos)}${c.status === "FECHANDO" ? " · conta pedida" : ""}` : " — livre"}`);
          }),
          mesasPdv.comandas.filter((c) => !c.mesa).map((c) => h("option", { value: `c:${c.id}`, selected: atual === `c:${c.id}` },
            `Comanda ${c.numero || c.nome_cliente} · ${dinheiro(c.total_centavos)}`)));
        sel.addEventListener("change", () => {
          const [tipo, id] = sel.value.split(":");
          if (!id) { estado.mesa = null; return; }
          if (tipo === "c") { const c = mesasPdv.comandas.find((x) => x.id === id); estado.mesa = { comandaId: id, mesaId: null, nome: `Comanda ${c?.numero || ""}`.trim() }; return; }
          const m = mesasPdv.mesas.find((x) => x.id === id);
          estado.mesa = { mesaId: id, comandaId: porMesa.get(id)?.id || null, nome: m?.nome || "" };
        });
        const nome = h("input", { type: "text", placeholder: "Nome do cliente (opcional)", value: estado.cliente.nome });
        nome.addEventListener("input", () => { estado.cliente.nome = nome.value; });
        return h("div", { class: "grade", style: { gap: "6px", marginBottom: "8px" } },
          h("div", { class: "acoes" }, h("div", { style: { flex: 1, minWidth: "0" } }, sel),
            h("button", { type: "button", class: "botao botao-pequeno", title: "Atualizar mesas", onclick: () => carregarMesas().catch(erro) }, "↻")),
          nome,
          mesasPdv.mesas.length ? null : h("div", { class: "muted" }, "Nenhuma mesa cadastrada — peça ao gerente para cadastrar."));
      }

      async function lancarNaMesa() {
        if (!estado.mesa) { aviso("Escolha a mesa.", "erro"); return; }
        const cozinha = await new Promise((resolve) => {
          let r = null;
          const marca = h("input", { type: "checkbox", checked: true });
          const m = modal({
            titulo: `Enviar para ${estado.mesa.nome}`, tamanho: "modal-pequeno",
            corpo: h("div", { class: "grade" },
              h("p", { style: { margin: 0 } }, "Os itens entram na conta da mesa. O pagamento é feito ao fechar (ou em partes) em Mesas."),
              h("label", { class: "check" }, marca, h("span", null, "Imprimir via da cozinha"))),
            rodape: [h("button", { type: "button", class: "botao botao-primario botao-grande", onclick: () => { r = { cozinha: marca.checked }; m.fechar(); } }, "Enviar")],
            aoFechar: () => resolve(r),
          });
        });
        if (!cozinha) return;
        let comanda = estado.mesa.comandaId;
        try {
          if (!comanda) {
            const pessoas = 1;
            comanda = (await post("/api/comandas/", { id: uuid(), mesa: estado.mesa.mesaId, pessoas, nome_cliente: estado.cliente.nome.trim() })).id;
          }
          const p = await post("/api/pedidos/", {
            id: uuid(), canal: "MESA", tipo_atendimento: "CONSUMO_LOCAL", comanda,
            mesa: estado.mesa.nome.replace(/^Mesa\s*/i, "").slice(0, 10), nome_cliente: estado.cliente.nome.trim(),
            observacao: estado.observacao,
            itens: estado.itens.map((i) => ({ produto_id: i.produto_id, quantidade: i.quantidade, variacao_id: i.variacao_id || null,
              sabores: i.sabores || [], adicionais: i.adicionais || [], observacao: i.observacao || "" })),
          });
          if (cozinha.cozinha) imprimirPedido(p.id, "cozinha").catch(erro);
          aviso(`Pedido #${p.numero} enviado para ${estado.mesa.nome}.`, "ok");
        } catch (e) { erro(e); return; }
        estado.itens = []; estado.observacao = ""; estado.cliente = { nome: "", telefone: "" }; estado.mesa = null;
        await carregarMesas().catch(erro);
      }

      function blocoCliente() {
        if (estado.modo === "MESA") return blocoMesa();
        if (estado.modo !== "DELIVERY") {
          const nome = h("input", { type: "text", placeholder: "Nome do cliente (opcional)", value: estado.cliente.nome });
          nome.addEventListener("input", () => { estado.cliente.nome = nome.value; });
          const senha = h("input", { type: "text", placeholder: "Nº auto", value: estado.senha, style: { maxWidth: "96px" } });
          senha.addEventListener("input", () => { estado.senha = senha.value; });
          const tel = h("input", { type: "tel", placeholder: "Telefone (cashback)", value: estado.cliente.telefone });
          tel.addEventListener("input", () => { estado.cliente.telefone = tel.value; });
          const buscar = botaoAcao("Buscar", async () => {
            const c = await buscarCliente(tel.value);
            if (c) { estado.cliente = { nome: c.nome, telefone: c.telefone }; } else aviso("Cliente novo: o cashback começa a contar a partir desta compra.");
            desenharCarrinho();
          }, "botao botao-pequeno");
          return h("div", { class: "grade", style: { gap: "6px", marginBottom: "6px" } },
            h("div", { class: "acoes" }, nome, senha), h("div", { class: "acoes" }, tel, buscar), blocoCashback());
        }
        const tel = h("input", { type: "tel", placeholder: "Telefone do cliente", value: estado.cliente.telefone });
        const nome = h("input", { type: "text", placeholder: "Nome", value: estado.cliente.nome });
        nome.addEventListener("input", () => { estado.cliente.nome = nome.value; });
        tel.addEventListener("input", () => { estado.cliente.telefone = tel.value; });
        const buscar = botaoAcao("Buscar", async () => {
          const c = await buscarCliente(tel.value);
          if (!c) { aviso("Cliente novo: preencha nome e endereço."); desenharCarrinho(); return; }
          estado.cliente = { nome: c.nome, telefone: c.telefone };
          const e = c.enderecos?.find((x) => x.principal) || c.enderecos?.[0];
          if (e) { estado.endereco = { logradouro: e.logradouro, numero: e.numero, complemento: e.complemento, bairro: e.bairro, cidade: e.cidade, cep: e.cep, referencia: e.referencia }; await calcularTaxa(); }
          desenharCarrinho();
        }, "botao botao-pequeno");
        const end = estado.endereco;
        return h("div", { class: "grade", style: { gap: "6px", marginBottom: "6px" } },
          h("div", { class: "acoes" }, tel, buscar), nome,
          h("button", { type: "button", class: "botao botao-pequeno", onclick: editarEndereco },
            end ? `📍 ${end.logradouro}, ${end.numero} — ${end.bairro}` : "Informar endereço de entrega"),
          blocoCashback());
      }

      async function calcularTaxa() {
        if (!estado.endereco?.bairro) return;
        try {
          const r = await post("/api/taxa-entrega/", estado.endereco);
          estado.taxa = r.taxa_centavos;
        } catch (e) { aviso(`Taxa de entrega: ${e.mensagem || e}`, "erro"); estado.taxa = 0; }
      }

      function editarEndereco() {
        const e = estado.endereco || {};
        const campos = [["cep", "CEP"], ["logradouro", "Rua"], ["numero", "Número"], ["complemento", "Complemento"], ["bairro", "Bairro"], ["cidade", "Cidade"], ["referencia", "Referência"]];
        const entradas = Object.fromEntries(campos.map(([k]) => [k, h("input", { type: "text", value: e[k] || "" })]));
        entradas.cep.setAttribute("inputmode", "numeric");
        entradas.cep.setAttribute("placeholder", "00000-000 (preenche o endereço)");
        // bairros com taxa cadastrada: sugestões no campo (dá para digitar outro)
        const listaBairros = h("datalist", { id: "pdv-bairros" });
        entradas.bairro.setAttribute("list", "pdv-bairros");
        lista("/api/zonas/", { ativa: "true" }).then((zs) => trocar(listaBairros,
          [...new Set(zs.filter((z) => z.tipo === "BAIRRO").map((z) => z.nome))].sort().map((n) => h("option", { value: n })))).catch(() => {});
        const dicaCep = h("small", { class: "muted" });
        let ultimoCep = (e.cep || "").replace(/\D/g, "");
        const semAcento = (t) => (t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
        const buscarCep = async () => {
          const cep = entradas.cep.value.replace(/\D/g, "");
          if (cep.length === 8) entradas.cep.value = `${cep.slice(0, 5)}-${cep.slice(5)}`;
          if (cep.length !== 8 || cep === ultimoCep) return;
          ultimoCep = cep;
          dicaCep.textContent = "Buscando…";
          try {
            const d = await (await fetch(`https://viacep.com.br/ws/${cep}/json/`)).json();
            if (d.erro) { dicaCep.textContent = "CEP não encontrado."; return; }
            const cadastrado = [...listaBairros.options].map((o) => o.value).find((b) => semAcento(b) === semAcento(d.bairro));
            if (d.logradouro) entradas.logradouro.value = d.logradouro;
            entradas.bairro.value = cadastrado || d.bairro || entradas.bairro.value;
            entradas.cidade.value = d.localidade || entradas.cidade.value;
            dicaCep.textContent = `✓ ${d.localidade || ""}${d.uf ? ` - ${d.uf}` : ""} · confira o bairro (pode trocar pela lista)`;
            entradas.numero.focus();
          } catch { dicaCep.textContent = "Não deu para buscar o CEP agora."; }
        };
        entradas.cep.addEventListener("input", buscarCep);
        entradas.cep.addEventListener("blur", buscarCep);
        const taxa = h("input", { type: "text", inputmode: "decimal", placeholder: "Automática pela zona", value: "" });
        const m = modal({
          titulo: "Endereço de entrega",
          corpo: h("div", { class: "form-grade" }, campos.map(([k, r]) => h("label", { class: `campo ${k === "logradouro" ? "largo" : ""}` }, h("span", null, r), entradas[k],
            k === "cep" ? dicaCep : null)), listaBairros,
            h("label", { class: "campo" }, h("span", null, "Taxa manual (opcional)"), taxa)),
          rodape: [botaoAcao("Usar este endereço", async () => {
            const d = Object.fromEntries(campos.map(([k]) => [k, entradas[k].value.trim()]));
            if (!d.logradouro || !d.numero || !d.bairro) { aviso("Preencha rua, número e bairro.", "erro"); return; }
            estado.endereco = d;
            if (taxa.value.trim()) estado.taxa = centavos(taxa.value); else await calcularTaxa();
            m.fechar();
            desenharCarrinho();
          }, "botao botao-primario")],
        });
      }

      function ajustes() {
        const desc = h("input", { type: "text", inputmode: "decimal", placeholder: "0,00", value: estado.desconto ? (estado.desconto / 100).toFixed(2).replace(".", ",") : "" });
        const cupom = h("input", { type: "text", value: estado.cupom, placeholder: "Código do cupom" });
        const obs = h("textarea", { rows: 2 }, estado.observacao);
        const cpf = h("input", { type: "text", value: estado.cpf, placeholder: "Somente números" });
        const m = modal({
          titulo: "Ajustes da venda", tamanho: "modal-pequeno",
          corpo: h("div", { class: "grade" },
            h("label", { class: "campo" }, h("span", null, "Desconto (R$)"), desc),
            h("label", { class: "campo" }, h("span", null, "Cupom"), cupom),
            h("label", { class: "campo" }, h("span", null, "CPF/CNPJ na nota"), cpf),
            h("label", { class: "campo" }, h("span", null, "Observação do pedido"), obs)),
          rodape: [h("button", { type: "button", class: "botao botao-primario", onclick: () => {
            estado.desconto = centavos(desc.value);
            estado.cupom = cupom.value.trim().toUpperCase();
            estado.cpf = cpf.value.replace(/\D/g, "");
            estado.observacao = obs.value.trim();
            m.fechar();
            desenharCarrinho();
          } }, "Aplicar")],
        });
      }

      function corpoPedido() {
        const delivery = estado.modo === "DELIVERY";
        return {
          id: uuid(),
          canal: delivery ? "DELIVERY" : "BALCAO",
          tipo_atendimento: delivery ? "ENTREGA" : estado.modo === "RETIRADA" ? "RETIRADA" : "CONSUMO_LOCAL",
          origem_contato: delivery ? estado.origem : "PRESENCIAL",
          itens: estado.itens.map((i) => ({
            produto_id: i.produto_id, quantidade: i.quantidade, variacao_id: i.variacao_id || null,
            sabores: i.sabores || [], adicionais: i.adicionais || [], observacao: i.observacao || "",
          })),
          nome_cliente: estado.cliente.nome.trim(),
          telefone_cliente: estado.cliente.telefone.replace(/\D/g, ""),
          senha: estado.senha.trim(),
          endereco: delivery ? estado.endereco : null,
          taxa_entrega_centavos: delivery ? estado.taxa : null,
          desconto_centavos: estado.desconto,
          cupom_codigo: estado.cupom,
          observacao: estado.observacao,
          cpf_nota: estado.cpf,
          usar_cashback_centavos: estado.usarCashback ? estado.saldoCashback : 0,
          forma_pagamento_prevista: delivery ? estado.previsto : "",
          troco_para_centavos: delivery && estado.previsto === "DINHEIRO" && estado.trocoPara ? centavos(estado.trocoPara) : null,
        };
      }

      async function finalizar() {
        if (!estado.itens.length) { aviso("Adicione produtos à venda.", "erro"); return; }
        if (estado.modo === "MESA") { await lancarNaMesa(); return; }
        const delivery = estado.modo === "DELIVERY";
        if (delivery && (!estado.endereco || !estado.cliente.telefone)) { aviso("Delivery: informe telefone e endereço.", "erro"); return; }
        const escolha = await escolherFinalizacao(delivery);
        if (!escolha) return;
        let pedido;
        try {
          pedido = await post("/api/pedidos/", corpoPedido());
        } catch (e) { erro(e); return; }
        aviso(`Pedido #${pedido.numero} lançado.`, "ok");
        if (escolha.cozinha) imprimirPedido(pedido.id, "cozinha").catch(erro);
        let quitado = false;
        if (escolha.receber) quitado = await receber({ tipo: "pedido", id: pedido.id, restante: pedido.total_centavos });
        if (quitado || !escolha.receber) {
          try {
            if (quitado) {
              const doc = await post(`/api/pedidos/${pedido.id}/documento/`, { cpf: estado.cpf });
              if (escolha.imprimir) imprimirLinhas(doc.linhas); else mostrarCupom(doc.linhas, { titulo: doc.tipo === "NFCE" ? "NFC-e" : "Comprovante", aviso: doc.aviso || "" });
              if (doc.aviso) aviso(doc.aviso);
            } else if (escolha.imprimir) await imprimirPedido(pedido.id, "venda");
          } catch (e) { erro(e); }
        }
        estado.itens = [];
        estado.desconto = 0; estado.cupom = ""; estado.observacao = ""; estado.cpf = ""; estado.senha = "";
        estado.cliente = { nome: "", telefone: "" }; estado.endereco = null; estado.taxa = 0; estado.trocoPara = "";
        estado.saldoCashback = 0; estado.usarCashback = false;
        desenharCarrinho();
      }

      function escolherFinalizacao(delivery) {
        return new Promise((resolve) => {
          let r = null;
          const receberAgora = h("input", { type: "checkbox", checked: !delivery });
          const imprimir = h("input", { type: "checkbox", checked: true });
          const cozinha = h("input", { type: "checkbox", checked: false });
          const previsto = h("select", null, opcoes("FormaPagamento").filter((o) => o.valor !== "MARKETPLACE").map((o) => h("option", { value: o.valor, selected: o.valor === estado.previsto }, o.rotulo)));
          const troco = h("input", { type: "text", inputmode: "decimal", placeholder: "Troco para quanto?", value: estado.trocoPara });
          const origem = h("select", null, opcoes("OrigemContato").filter((o) => o.valor !== "SITE").map((o) => h("option", { value: o.valor, selected: o.valor === estado.origem }, o.rotulo)));
          const t = totais();
          const m = modal({
            titulo: "Finalizar venda", tamanho: "modal-pequeno",
            corpo: h("div", { class: "grade" },
              h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Total"), h("div", { class: "kpi-valor" }, dinheiro(t.total))),
              h("label", { class: "check" }, receberAgora, h("span", null, "Receber o pagamento agora")),
              delivery ? h("div", { class: "grade" },
                h("label", { class: "campo" }, h("span", null, "Pedido recebido por"), origem),
                h("label", { class: "campo" }, h("span", null, "Cliente vai pagar com"), previsto),
                h("label", { class: "campo" }, h("span", null, "Troco para (dinheiro)"), troco)) : null,
              h("label", { class: "check" }, imprimir, h("span", null, "Imprimir cupom")),
              h("label", { class: "check" }, cozinha, h("span", null, "Imprimir via da cozinha"))),
            rodape: [h("button", { type: "button", class: "botao botao-primario botao-grande", onclick: () => {
              estado.previsto = previsto.value; estado.trocoPara = troco.value; estado.origem = origem.value;
              r = { receber: receberAgora.checked, imprimir: imprimir.checked, cozinha: cozinha.checked };
              m.fechar();
            } }, "Lançar pedido")],
            aoFechar: () => resolve(r),
          });
        });
      }

      trocar(raiz, avisoCaixa, h("div", { class: "pdv" },
        h("div", null, h("div", { class: "pdv-cabeca" }, h("div", { class: "barra-ferramentas" }, busca), cats), grade, irCarrinho),
        carrinho, fundoCarrinho));
      desenharCatalogo();
      desenharCarrinho();
      if (!matchMedia("(pointer: coarse)").matches) busca.focus();  // no celular não abre o teclado sozinho
    },
  };
}
