/* ApFood — acompanhamento do pedido em tempo real (WebSocket + consulta de reserva). */
(function () {
  "use strict";
  const C = window.ApCarrinho;
  const TOKEN = JSON.parse(document.getElementById("token-pedido").textContent);
  const API = "/api/publico/pedidos/" + encodeURIComponent(TOKEN) + "/";
  const FINAIS = ["CONCLUIDO", "CANCELADO", "RECUSADO"];
  const $ = function (s) { return document.querySelector(s); };
  let ultimo = null, ws = null, tentativas = 0, timer = null;

  function el(tag, attrs, filhos) {
    const e = document.createElement(tag);
    Object.entries(attrs || {}).forEach(function ([k, v]) {
      if (v === null || v === undefined || v === false) return;
      if (k === "class") e.className = v; else if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? "" : v);
    });
    (Array.isArray(filhos) ? filhos : filhos !== undefined ? [filhos] : []).forEach(function (f) {
      if (f) e.appendChild(typeof f === "string" || typeof f === "number" ? document.createTextNode(String(f)) : f);
    });
    return e;
  }

  function hora(iso) { return iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : ""; }

  function etapas(p) {
    const entrega = p.tipo_atendimento === "ENTREGA";
    const lista = [
      { st: ["PENDENTE"], rot: "Pedido enviado", sub: "aguardando a loja confirmar", t: p.criado_em },
      { st: ["RECEBIDO"], rot: "Pedido confirmado", t: p.aceito_em },
      { st: ["EM_PREPARO", "PRONTO"], rot: p.status === "PRONTO" && !entrega ? "Pronto para retirar!" : "Em preparo" },
    ];
    if (entrega) lista.push({ st: ["SAIU_PARA_ENTREGA"], rot: "Saiu para entrega", t: p.saiu_entrega_em });
    lista.push({ st: ["CONCLUIDO"], rot: entrega ? "Entregue" : "Retirado", t: p.concluido_em });
    const ordem = lista.findIndex(function (e) { return e.st.includes(p.status); });
    return el("ol", { class: "etapas" }, lista.map(function (e, i) {
      const cls = i < ordem ? "feita" : i === ordem ? (p.status === "CONCLUIDO" ? "feita" : "atual") : "";
      return el("li", { class: cls }, [e.rot, e.t ? el("small", { text: "  " + hora(e.t) }) : null,
        i === ordem && e.sub ? el("div", {}, el("small", { text: e.sub })) : null]);
    }));
  }

  function blocoPix(p) {
    let pix = p.pix;
    if (!pix) { try { pix = JSON.parse(sessionStorage.getItem("apfood_pix_" + TOKEN) || "null"); } catch (e) { pix = null; } }
    if (!pix || p.pago || FINAIS.includes(p.status)) return null;
    const copia = el("div", { class: "copia", text: pix.qr_code || "" });
    const btn = el("button", { class: "btn", style: "justify-content:center", text: "Copiar código Pix", onclick: async function () {
      try { await navigator.clipboard.writeText(pix.qr_code); btn.textContent = "Copiado ✓"; }
      catch (e) { const r = document.createRange(); r.selectNodeContents(copia); getSelection().removeAllRanges(); getSelection().addRange(r); }
    } });
    return el("div", { class: "cartao qr" }, [el("b", { text: "Pague com Pix: " + C.reais(pix.valor_centavos) }),
      pix.qr_code_base64 ? el("img", { src: "data:image/png;base64," + pix.qr_code_base64, alt: "QR Code Pix" }) : null,
      copia, btn, el("small", { text: "Assim que o banco confirmar, o pedido aparece como pago aqui." })]);
  }

  function render(p) {
    document.documentElement.style.setProperty("--cor", p.cor_primaria || "#e4572e");
    document.title = "Pedido #" + (p.numero || "") + " — " + p.loja;
    const cancelado = p.status === "CANCELADO" || p.status === "RECUSADO";
    const titulo = cancelado ? "Pedido cancelado" : p.status === "CONCLUIDO" ? "Pedido finalizado 🎉" : p.etapa;
    const tel = (p.whatsapp || "").replace(/\D/g, "");
    const zap = tel ? "https://wa.me/" + (tel.length <= 11 ? "55" + tel : tel) + "?text=" +
      encodeURIComponent("Olá! Sobre o meu pedido #" + (p.numero || "") + "…") : null;
    const itens = p.itens.map(function (i) {
      return el("div", { class: "item-car" }, [el("div", { class: "txt" }, [el("b", { text: i.quantidade + "x " + i.nome + (i.variacao ? " (" + i.variacao + ")" : "") }),
        (i.adicionais || []).length ? el("small", { text: i.adicionais.join(", ") }) : null,
        i.observacao ? el("small", { text: "Obs.: " + i.observacao }) : null]), el("span", { text: C.reais(i.total_centavos) })]);
    });
    const linhas = [["Subtotal", C.reais(p.subtotal_centavos)]];
    if (p.taxa_entrega_centavos) linhas.push(["Entrega", C.reais(p.taxa_entrega_centavos)]);
    if (p.desconto_centavos) linhas.push(["Desconto", "−" + C.reais(p.desconto_centavos)]);
    const FORMAS = { PIX: "Pix", DINHEIRO: "Dinheiro", CARTAO_CREDITO: "Cartão de crédito", CARTAO_DEBITO: "Cartão de débito", VOUCHER: "Vale-refeição" };
    $("#conteudo").replaceChildren(
      el("div", { class: "cartao" }, [el("small", { text: p.loja }), el("p", { class: "grande", text: titulo }),
        el("div", { text: "Pedido #" + (p.numero || "") }),
        cancelado && p.motivo_cancelamento ? el("p", { class: "erros", text: "Motivo: " + p.motivo_cancelamento }) : null,
        cancelado ? null : etapas(p)]),
      blocoPix(p),
      el("div", { class: "cartao" }, [el("b", { text: "Itens" })].concat(itens).concat([el("div", { class: "resumo" },
        linhas.map(function ([a, b]) { return el("div", {}, [el("span", { text: a }), el("span", { text: b })]); })
          .concat([el("div", { class: "total" }, [el("span", { text: "Total" }), el("span", { text: C.reais(p.total_centavos) })])]))])
        .concat([el("div", { style: "margin-top:8px" }, [p.pago ? el("span", { class: "ok", text: "✓ Pago" })
          : el("span", { text: "Pagamento: " + (FORMAS[p.forma_prevista] || "na entrega") + (p.troco_para_centavos ? " · troco para " + C.reais(p.troco_para_centavos) : "") })])])
        .concat(p.endereco ? [el("div", { style: "margin-top:6px" }, el("small", { text: "📍 " + p.endereco }))] : [])),
      el("div", { class: "cartao", style: "display:grid;gap:8px" }, [
        zap ? el("a", { class: "btn secundario", href: zap, target: "_blank", rel: "noopener", text: "Falar com a loja no WhatsApp" }) : null,
        el("a", { class: "btn secundario", href: "/" + p.loja_slug + "/", text: "Voltar ao cardápio" })]),
      el("p", { class: "status-ws", id: "status-ws" }),
    );
    indicador();
  }

  function indicador() {
    const s = $("#status-ws");
    if (s) s.textContent = ultimo && FINAIS.includes(ultimo.status) ? "" : ws && ws.readyState === 1 ? "● atualizando em tempo real" : "atualiza a cada 20 s";
  }

  async function carregar() {
    try {
      const r = await fetch(API, { headers: { Accept: "application/json" } });
      if (r.status === 404) { $("#conteudo").replaceChildren(el("div", { class: "cartao", text: "Pedido não encontrado." })); return; }
      const p = await r.json();
      const mudou = ultimo && ultimo.status !== p.status;
      ultimo = p;
      render(p);
      if (mudou && navigator.vibrate) navigator.vibrate(200);
      if (FINAIS.includes(p.status)) { clearInterval(timer); if (ws) ws.close(); }
    } catch (e) { /* sem rede: tenta de novo no próximo ciclo */ }
  }

  function conectar() {
    if (!("WebSocket" in window) || (ultimo && FINAIS.includes(ultimo.status))) return;
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/pedido/" + encodeURIComponent(TOKEN) + "/");
    ws.onopen = function () { tentativas = 0; indicador(); };
    ws.onmessage = function () { carregar(); };
    ws.onclose = function () { indicador(); if (!(ultimo && FINAIS.includes(ultimo.status))) setTimeout(conectar, Math.min(30000, 2000 * ++tentativas)); };
  }

  carregar().then(conectar);
  timer = setInterval(carregar, 20000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) carregar(); });
})();
