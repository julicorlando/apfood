// Peças compartilhadas da operação: cupom (prévia e impressão), detalhe do pedido e pagamento.
import { ehGerente, get, lista, post, sessao } from "../api.js";
import {
  aviso, botaoAcao, centavos, dataHora, dinheiro, erro, etiquetaStatus, h, modal, opcoes, pedirTexto, reais, rotulo, trocar, uuid,
} from "../ui.js";

// ---------------------------------------------------------------- cupom
const CLASSE_ALINHAMENTO = { centro: "centro", direita: "direita" };

function linhaCupom(doc, l) {
  if (l.qrcode) {
    const img = doc.createElement("img");
    img.alt = "QR Code";
    img.src = `/painel/qrcode.svg?t=${encodeURIComponent(l.texto)}`;
    return img;
  }
  const div = doc.createElement("div");
  div.className = [l.negrito ? "negrito" : "", l.grande ? "grande" : "", CLASSE_ALINHAMENTO[l.alinhamento] || ""].join(" ");
  div.textContent = l.texto || " ";
  if (l.corte) {
    const corte = doc.createElement("div");
    corte.className = "corte";
    const caixa = doc.createElement("div");
    caixa.append(div, corte);
    return caixa;
  }
  return div;
}

export function cupomEl(linhas) {
  const caixa = h("div", { class: "cupom" });
  for (const l of linhas) caixa.append(linhaCupom(document, l));
  return caixa;
}

const CSS_IMPRESSAO = `
@page { size: 80mm auto; margin: 2mm; }
body { margin: 0; font-family: "Courier New", monospace; font-size: 11px; color: #000; }
.cupom > div, body > div { white-space: pre; }
.negrito { font-weight: bold; } .grande { font-size: 17px; font-weight: bold; }
.centro { text-align: center; } .direita { text-align: right; }
.corte { border-bottom: 1px dashed #000; margin: 4mm 0; page-break-after: always; }
img { display: block; margin: 2mm auto; width: 34mm; height: 34mm; }`;

export function imprimirLinhas(linhas) {
  const iframe = document.createElement("iframe");
  Object.assign(iframe.style, { position: "fixed", right: "0", bottom: "0", width: "0", height: "0", border: "0" });
  document.body.append(iframe);
  const doc = iframe.contentDocument;
  doc.open();
  doc.write("<!doctype html><html><head><meta charset='utf-8'><title>Cupom</title></head><body></body></html>");
  doc.close();
  const style = doc.createElement("style");
  style.textContent = CSS_IMPRESSAO;
  doc.head.append(style);
  for (const l of linhas) doc.body.append(linhaCupom(doc, l));
  const imgs = [...doc.images];
  const pronto = Promise.all(imgs.map((i) => (i.complete ? null : new Promise((r) => { i.onload = r; i.onerror = r; }))));
  pronto.then(() => {
    iframe.contentWindow.focus();
    iframe.contentWindow.print();
    setTimeout(() => iframe.remove(), 60000);
  });
}

export function mostrarCupom(linhas, { titulo = "Cupom", aviso: av = "" } = {}) {
  modal({
    titulo, tamanho: "modal-pequeno",
    corpo: [av ? h("div", { class: "alerta alerta-aviso", style: { marginBottom: "12px" } }, av) : null, cupomEl(linhas)],
    rodape: [h("button", { class: "botao botao-primario", type: "button", onclick: () => imprimirLinhas(linhas) }, "Imprimir")],
  });
}

export async function imprimirPedido(pedidoId, tipo = "venda") {
  const r = await get(`/api/pedidos/${pedidoId}/cupom/?tipo=${tipo}`);
  if (tipo === "cozinha") {
    const vias = r.vias || [];
    if (!vias.length) { aviso("Nenhum item para a cozinha."); return; }
    const linhas = vias.flatMap((v) => (Array.isArray(v) ? v : v.linhas || []));
    imprimirLinhas(linhas);
  } else imprimirLinhas(r.linhas);
}

// ---------------------------------------------------------------- pagamento
export const FORMAS_PDV = ["DINHEIRO", "PIX", "CARTAO_DEBITO", "CARTAO_CREDITO", "VOUCHER", "OUTRO"];

/** Abre o modal de pagamento. alvo = {tipo: "pedido"|"comanda", id, restante}. Resolve true quando quitado. */
export function receber(alvo) {
  return new Promise((resolve) => {
    let quitou = false;
    let forma = "DINHEIRO";
    const valor = h("input", { type: "text", inputmode: "decimal", value: reais(alvo.restante) });
    const recebido = h("input", { type: "text", inputmode: "decimal", placeholder: "Valor entregue pelo cliente" });
    const troco = h("div", { class: "muted" });
    const bandeira = h("input", { type: "text", placeholder: "Visa, Master, Elo…" });
    const blocoDinheiro = h("label", { class: "campo" }, h("span", null, "Recebido em dinheiro (para troco)"), recebido, troco);
    const blocoCartao = h("label", { class: "campo", hidden: true }, h("span", null, "Bandeira (opcional)"), bandeira);
    const atualizar = () => {
      const t = centavos(recebido.value) - centavos(valor.value);
      troco.textContent = recebido.value && t >= 0 ? `Troco: ${dinheiro(t)}` : "";
      blocoDinheiro.hidden = forma !== "DINHEIRO";
      blocoCartao.hidden = !forma.startsWith("CARTAO");
    };
    recebido.addEventListener("input", atualizar);
    valor.addEventListener("input", atualizar);
    const botoes = FORMAS_PDV.map((f) => {
      const b = h("button", { type: "button", class: f === forma ? "ativa" : "" }, rotulo("FormaPagamento", f));
      b.addEventListener("click", () => { forma = f; botoes.forEach((x) => x.classList.toggle("ativa", x === b)); atualizar(); });
      return b;
    });
    const msg = h("div", { class: "alerta alerta-erro", hidden: true });
    const pixBtn = botaoAcao("Gerar Pix (QR Code)", async () => {
      const r = await post(`/api/${alvo.tipo === "comanda" ? "comandas" : "pedidos"}/${alvo.id}/pix/`, { valor_centavos: centavos(valor.value) });
      mostrarPix(r);
    });
    const corpo = h("div", { class: "grade" },
      h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Falta pagar"), h("div", { class: "kpi-valor" }, dinheiro(alvo.restante))),
      msg,
      h("div", { class: "formas" }, botoes),
      h("label", { class: "campo" }, h("span", null, "Valor deste pagamento"), valor),
      blocoDinheiro, blocoCartao,
      h("small", { class: "muted" }, "Pix pela integração Mercado Pago gera o QR Code e confirma sozinho. Sem integração, receba e registre como Pix."),
    );
    const ok = botaoAcao("Confirmar pagamento", async () => {
      msg.hidden = true;
      const v = centavos(valor.value);
      if (v <= 0) { msg.textContent = "Informe o valor."; msg.hidden = false; return; }
      const corpoReq = { id: uuid(), forma, valor_centavos: v, bandeira: bandeira.value.trim() };
      if (forma === "DINHEIRO" && recebido.value) corpoReq.valor_recebido_centavos = centavos(recebido.value);
      try {
        const pg = await post(`/api/${alvo.tipo === "comanda" ? "comandas" : "pedidos"}/${alvo.id}/pagamentos/`, corpoReq);
        if (pg.troco_centavos) aviso(`Troco: ${dinheiro(pg.troco_centavos)}`, "ok");
        alvo.restante -= v;
        quitou = alvo.restante <= 0;
        m.fechar();
      } catch (e) {
        msg.textContent = e.mensagem || String(e);
        msg.hidden = false;
      }
    }, "botao botao-primario botao-grande");
    const m = modal({ titulo: "Receber pagamento", corpo, rodape: [pixBtn, ok], aoFechar: () => resolve(quitou) });
    atualizar();
    valor.select();
  });
}

export function mostrarPix(r) {
  const codigo = r.qr_code || r.copia_e_cola || r.emv || "";
  modal({
    titulo: `Pix — ${dinheiro(r.valor_centavos)}`, tamanho: "modal-pequeno",
    corpo: h("div", { class: "grade", style: { textAlign: "center" } },
      codigo ? h("img", { src: `/painel/qrcode.svg?t=${encodeURIComponent(codigo)}`, alt: "QR Code Pix", style: { width: "240px", margin: "0 auto" } }) : null,
      codigo ? h("textarea", { readonly: true, rows: 3, onclick: (ev) => ev.target.select() }, codigo) : h("p", null, "QR Code indisponível."),
      h("p", { class: "muted" }, "O pagamento é confirmado automaticamente quando o cliente pagar.")),
    rodape: codigo ? [h("button", { class: "botao", type: "button", onclick: () => navigator.clipboard?.writeText(codigo).then(() => aviso("Código copiado.", "ok")) }, "Copiar código")] : null,
  });
}

// ---------------------------------------------------------------- detalhe do pedido
const PROXIMO = {
  PENDENTE: [["RECEBIDO", "Aceitar", "botao-ok"]],
  RECEBIDO: [["EM_PREPARO", "Iniciar preparo", ""], ["PRONTO", "Marcar pronto", "botao-ok"]],
  EM_PREPARO: [["PRONTO", "Marcar pronto", "botao-ok"]],
  PRONTO: [["SAIU_PARA_ENTREGA", "Saiu para entrega", ""], ["CONCLUIDO", "Concluir", "botao-ok"]],
  SAIU_PARA_ENTREGA: [["CONCLUIDO", "Entregue (concluir)", "botao-ok"]],
};
const FINAIS = ["CONCLUIDO", "CANCELADO", "RECUSADO"];

export function pago(p) {
  return (p.pagamentos || []).filter((x) => x.status === "CONFIRMADO").reduce((s, x) => s + x.valor_centavos, 0);
}

export async function mudarStatus(p, para) {
  const corpo = { status: para };
  if (para === "CANCELADO" || para === "RECUSADO") {
    const motivo = await pedirTexto(para === "RECUSADO" ? "Recusar pedido" : "Cancelar pedido", { rotulo: "Motivo", ok: para === "RECUSADO" ? "Recusar" : "Cancelar pedido" });
    if (!motivo) return null;
    corpo.motivo = motivo;
  }
  if (para === "SAIU_PARA_ENTREGA") {
    const entregadores = await lista("/api/entregadores/", { ativo: "true" });
    if (entregadores.length) {
      const escolhido = await escolher("Quem vai entregar?", entregadores.map((e) => ({ valor: e.id, rotulo: e.nome })), { opcional: true });
      if (escolhido === undefined) return null;
      if (escolhido) corpo.entregador_id = escolhido;
    }
  }
  return post(`/api/pedidos/${p.id}/status/`, corpo);
}

export function escolher(titulo, ops, { opcional = false } = {}) {
  return new Promise((resolve) => {
    let r;
    const lista_ = h("div", { class: "opcoes-lista" }, ops.map((o) => h("button", {
      type: "button", class: "opcao", onclick: () => { r = o.valor; m.fechar(); },
    }, o.rotulo)));
    const m = modal({
      titulo, corpo: lista_, tamanho: "modal-pequeno",
      rodape: opcional ? [h("button", { type: "button", class: "botao", onclick: () => { r = null; m.fechar(); } }, "Pular")] : null,
      aoFechar: () => resolve(r),
    });
  });
}

function enderecoTexto(p) {
  if (!p.entrega_logradouro) return "";
  return `${p.entrega_logradouro}, ${p.entrega_numero}${p.entrega_complemento ? ` ${p.entrega_complemento}` : ""} — ${p.entrega_bairro}${p.entrega_cidade ? `, ${p.entrega_cidade}` : ""}${p.entrega_referencia ? ` (ref.: ${p.entrega_referencia})` : ""}`;
}

export function itensTexto(p) {
  return (p.itens || []).map((i) => `${i.quantidade}× ${i.nome_produto}${i.nome_variacao ? ` ${i.nome_variacao}` : ""}`).join(", ");
}

export async function abrirPedido(id, { aoMudar } = {}) {
  let p = await get(`/api/pedidos/${id}/`);
  const corpo = h("div");
  const rodape = h("div", { class: "acoes", style: { width: "100%" } });
  const m = modal({ titulo: `Pedido #${p.numero}`, corpo, rodape, tamanho: "modal-grande" });
  const recarregar = async () => { p = await get(`/api/pedidos/${id}/`); desenhar(); aoMudar?.(p); };

  function desenhar() {
    const totalPago = pago(p);
    const falta = Math.max(0, p.total_centavos - totalPago);
    trocar(corpo, 
      h("div", { class: "acoes", style: { marginBottom: "12px" } },
        etiquetaStatus("StatusPedido", p.status), h("span", { class: "etiqueta" }, rotulo("CanalVenda", p.canal)),
        h("span", { class: "etiqueta" }, rotulo("TipoAtendimento", p.tipo_atendimento)),
        p.marketplace ? h("span", { class: "etiqueta e-cor" }, rotulo("Marketplace", p.marketplace)) : null,
        h("span", { class: "muted" }, dataHora(p.criado_em))),
      h("div", { class: "grade grade-2" },
        h("div", null,
          h("h3", null, "Itens"),
          h("ul", { class: "lista-simples" }, (p.itens || []).map((i) => h("li", null,
            h("div", null,
              h("div", { class: "negrito" }, `${i.quantidade}× ${i.nome_produto}${i.nome_variacao ? ` (${i.nome_variacao})` : ""}`),
              i.sabores?.length ? h("div", { class: "muted" }, `Sabores: ${i.sabores.map((s) => s.nome).join(" / ")}`) : null,
              i.adicionais?.length ? h("div", { class: "muted" }, i.adicionais.map((a) => `+ ${a.quantidade > 1 ? `${a.quantidade}× ` : ""}${a.nome}`).join(", ")) : null,
              i.observacao ? h("div", { class: "muted" }, `Obs.: ${i.observacao}`) : null),
            h("span", { class: "num" }, dinheiro(i.total_centavos))))),
          h("ul", { class: "lista-simples", style: { marginTop: "8px" } },
            h("li", null, "Subtotal", h("span", { class: "num" }, dinheiro(p.subtotal_centavos))),
            p.taxa_entrega_centavos ? h("li", null, "Entrega", h("span", { class: "num" }, dinheiro(p.taxa_entrega_centavos))) : null,
            p.desconto_centavos ? h("li", null, "Desconto", h("span", { class: "num" }, `− ${dinheiro(p.desconto_centavos)}`)) : null,
            p.acrescimo_centavos ? h("li", null, "Acréscimo", h("span", { class: "num" }, dinheiro(p.acrescimo_centavos))) : null,
            p.cashback_usado_centavos ? h("li", null, "Cashback usado (já no desconto)", h("span", { class: "num" }, dinheiro(p.cashback_usado_centavos))) : null,
            p.cashback_gerado_centavos ? h("li", null, "Cashback gerado para o cliente", h("span", { class: "num" }, dinheiro(p.cashback_gerado_centavos))) : null,
            h("li", { class: "negrito" }, "Total", h("span", { class: "num" }, dinheiro(p.total_centavos))))),
        h("div", null,
          h("h3", null, "Cliente"),
          h("p", null, p.nome_cliente || "—", p.telefone_cliente ? h("span", { class: "muted" }, ` · ${p.telefone_cliente}`) : null),
          p.mesa ? h("p", null, `Mesa: ${p.mesa}`) : null,
          enderecoTexto(p) ? h("p", null, "📍 ", enderecoTexto(p)) : null,
          p.observacao ? h("div", { class: "alerta alerta-aviso" }, `Obs.: ${p.observacao}`) : null,
          p.motivo_cancelamento ? h("div", { class: "alerta alerta-erro" }, `Motivo: ${p.motivo_cancelamento}`) : null,
          h("h3", { style: { marginTop: "16px" } }, "Pagamento"),
          p.forma_pagamento_prevista ? h("p", { class: "muted" }, `Previsto: ${rotulo("FormaPagamento", p.forma_pagamento_prevista)}${p.troco_para_centavos ? ` (troco para ${dinheiro(p.troco_para_centavos)})` : ""}`) : null,
          h("ul", { class: "lista-simples" }, (p.pagamentos || []).map((pg) => h("li", null,
            h("span", null, rotulo("FormaPagamento", pg.forma), " ", etiquetaStatus("StatusPagamento", pg.status)),
            h("span", { class: "num" }, dinheiro(pg.valor_centavos))))),
          falta > 0 && !FINAIS.includes(p.status) ? h("div", { class: "alerta alerta-aviso", style: { marginTop: "8px" } }, `Falta receber ${dinheiro(falta)}`)
            : totalPago >= p.total_centavos ? h("div", { class: "alerta alerta-ok", style: { marginTop: "8px" } }, "Pago") : null,
          h("h3", { style: { marginTop: "16px" } }, "Histórico"),
          h("ul", { class: "lista-simples" }, (p.historico || []).map((x) => h("li", null,
            h("span", null, rotulo("StatusPedido", x.status_para), x.observacao ? h("span", { class: "muted" }, ` — ${x.observacao}`) : null),
            h("span", { class: "muted" }, dataHora(x.criado_em))))))),
    );

    const acoes = [];
    for (const [para, texto, cls] of PROXIMO[p.status] || []) {
      if (para === "SAIU_PARA_ENTREGA" && p.tipo_atendimento !== "ENTREGA") continue;
      acoes.push(botaoAcao(texto, async () => { if (await mudarStatus(p, para)) await recarregar(); }, `botao ${cls}`));
    }
    if (falta > 0 && !FINAIS.includes(p.status)) {
      acoes.push(botaoAcao(`Receber ${dinheiro(falta)}`, async () => {
        await receber({ tipo: "pedido", id: p.id, restante: falta });
        await recarregar();
      }, "botao botao-primario"));
    }
    acoes.push(botaoAcao("Imprimir cupom", () => imprimirPedido(p.id, "venda")));
    acoes.push(botaoAcao("Via da cozinha", () => imprimirPedido(p.id, "cozinha")));
    if (p.status === "CONCLUIDO" || totalPago >= p.total_centavos) {
      acoes.push(botaoAcao("Nota / comprovante", async () => {
        const r = await post(`/api/pedidos/${p.id}/documento/`, { cpf: p.cpf_nota || "" });
        mostrarCupom(r.linhas, { titulo: r.tipo === "NFCE" ? "NFC-e" : "Comprovante (não fiscal)", aviso: r.aviso || "" });
      }));
    }
    if (p.status === "PENDENTE") acoes.push(botaoAcao("Recusar", async () => { if (await mudarStatus(p, "RECUSADO")) await recarregar(); }, "botao botao-perigo"));
    else if (!FINAIS.includes(p.status) && ehGerente()) {
      acoes.push(botaoAcao("Cancelar pedido", async () => { if (await mudarStatus(p, "CANCELADO")) await recarregar(); }, "botao botao-perigo"));
    }
    if (p.token_rastreio && (p.canal === "ONLINE" || p.canal === "DELIVERY")) {
      acoes.push(h("a", { class: "botao", href: `/pedido/${p.token_rastreio}/`, target: "_blank", rel: "noopener" }, "Link do cliente"));
    }
    trocar(rodape, acoes);
  }
  desenhar();
  return m;
}

export { opcoes, sessao };
