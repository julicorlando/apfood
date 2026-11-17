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

function imprimirNoNavegador(linhas) {
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

// Ponte de impressão: com o ApFood PDV aberto neste computador, o cupom sai
// direto na térmica configurada nele (sem a janela de impressão do navegador).
const PONTE = "http://127.0.0.1:17777";
const estadoPonte = { ok: null, quando: 0 };

function ponteLigada() {
  try { return localStorage.getItem("apfood.impressao") !== "navegador"; } catch { return true; }
}

export async function ponteDisponivel(forcar = false) {
  if (!ponteLigada()) return false;
  const agora = Date.now();
  const validade = estadoPonte.ok ? 5 * 60000 : 60000;
  if (!forcar && estadoPonte.ok !== null && agora - estadoPonte.quando < validade) return estadoPonte.ok;
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 1500);
  try {
    const r = await fetch(`${PONTE}/status`, { signal: ctl.signal, cache: "no-store" });
    estadoPonte.ok = r.ok;
    estadoPonte.info = r.ok ? await r.json() : null;
  } catch { estadoPonte.ok = false; estadoPonte.info = null; }
  clearTimeout(t);
  estadoPonte.quando = agora;
  return estadoPonte.ok;
}
export const infoPonte = () => estadoPonte.info;

async function imprimirNaPonte(linhas, { destino = "caixa", impressora = "", gaveta = false } = {}) {
  try {
    const r = await fetch(`${PONTE}/imprimir`, {
      method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
      body: JSON.stringify({ linhas, destino, impressora, abrir_gaveta: gaveta }),
    });
    if (r.ok) return true;
    const e = await r.json().catch(() => ({}));
    aviso(`PDV: ${e.erro || `erro ${r.status}`}. Abrindo a impressão do navegador.`);
  } catch {
    estadoPonte.ok = false;
  }
  return false;
}

/** Imprime as linhas do cupom: na térmica (via PDV) ou pela janela do navegador. */
export async function imprimirLinhas(linhas, opcoes = {}) {
  if (await ponteDisponivel() && await imprimirNaPonte(linhas, opcoes)) {
    aviso("Enviado para a impressora.", "ok");
    return true;
  }
  imprimirNoNavegador(linhas);
  return false;
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
    const vias = (r.vias || []).map((v) => (Array.isArray(v) ? { linhas: v } : v));
    if (!vias.length) { aviso("Nenhum item para a cozinha."); return; }
    if (await ponteDisponivel()) {
      const falhou = [];
      for (const v of vias) {
        if (!(await imprimirNaPonte(v.linhas || [], { destino: "cozinha", impressora: v.impressora || "" }))) falhou.push(v);
      }
      if (!falhou.length) { aviso(vias.length > 1 ? `${vias.length} vias enviadas para a cozinha.` : "Via enviada para a cozinha.", "ok"); return; }
      imprimirNoNavegador(falhou.flatMap((v) => v.linhas || []));
      return;
    }
    imprimirNoNavegador(vias.flatMap((v) => v.linhas || []));
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
    // Mesa: recebe só a parte de um cliente (a conta continua aberta)
    const pagador = h("input", { type: "text", maxlength: 60, placeholder: "Ex.: Cliente 1, João (opcional)" });
    const dividir = alvo.parcial ? h("div", { class: "acoes" }, h("span", { class: "muted" }, "Dividir o que falta por:"),
      ...[2, 3, 4, 5].map((n) => h("button", { type: "button", class: "botao botao-pequeno", onclick: () => {
        valor.value = reais(Math.ceil(alvo.restante / n)); atualizar();
      } }, `${n}`))) : null;
    const corpo = h("div", { class: "grade" },
      h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Falta pagar"), h("div", { class: "kpi-valor" }, dinheiro(alvo.restante))),
      msg,
      h("div", { class: "formas" }, botoes),
      h("label", { class: "campo" }, h("span", null, alvo.parcial ? "Valor deste pagamento (pode ser só uma parte)" : "Valor deste pagamento"), valor),
      dividir,
      alvo.parcial ? h("label", { class: "campo" }, h("span", null, "Quem está pagando"), pagador) : null,
      blocoDinheiro, blocoCartao,
      h("small", { class: "muted" }, "Pix pela integração Mercado Pago gera o QR Code e confirma sozinho. Sem integração, receba e registre como Pix."),
    );
    const ok = botaoAcao("Confirmar pagamento", async () => {
      msg.hidden = true;
      const v = centavos(valor.value);
      if (v <= 0) { msg.textContent = "Informe o valor."; msg.hidden = false; return; }
      if (v > alvo.restante) { msg.textContent = `O valor passa do que falta (${dinheiro(alvo.restante)}).`; msg.hidden = false; return; }
      const corpoReq = { id: uuid(), forma, valor_centavos: v, bandeira: bandeira.value.trim(), pagador: pagador.value.trim() };
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

export function pago(p) {  // inclui o dinheiro já cobrado pelo entregador (aguardando o repasse)
  return (p.pagamentos || []).filter((x) => x.status === "CONFIRMADO" || (x.status === "PENDENTE" && x.cobrado_em))
    .reduce((s, x) => s + x.valor_centavos, 0);
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
        h("span", { class: "muted" }, dataHora(p.criado_em)),
        p.agendado_para ? h("span", { class: "etiqueta e-info" }, `📅 Agendado para ${dataHora(p.agendado_para)}`) : null),
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
          p.tipo_atendimento === "ENTREGA" ? blocoEntrega() : null,
          p.observacao ? h("div", { class: "alerta alerta-aviso" }, `Obs.: ${p.observacao}`) : null,
          p.motivo_cancelamento ? h("div", { class: "alerta alerta-erro" }, `Motivo: ${p.motivo_cancelamento}`) : null,
          h("h3", { style: { marginTop: "16px" } }, "Pagamento"),
          p.forma_pagamento_prevista ? h("p", { class: "muted" }, `Previsto: ${rotulo("FormaPagamento", p.forma_pagamento_prevista)}${p.troco_para_centavos ? ` (troco para ${dinheiro(p.troco_para_centavos)})` : ""}`) : null,
          h("ul", { class: "lista-simples" }, (p.pagamentos || []).map((pg) => h("li", null,
            h("span", null, rotulo("FormaPagamento", pg.forma), " ",
              pg.status === "PENDENTE" && pg.cobrado_em ? h("span", { class: "etiqueta" }, "com o entregador") : etiquetaStatus("StatusPagamento", pg.status),
              pg.cobrado_em && pg.forma === "DINHEIRO" && pg.valor_recebido_centavos ? h("span", { class: "muted" }, ` · recebeu ${dinheiro(pg.valor_recebido_centavos)}, troco ${dinheiro(pg.troco_centavos || 0)}`) : null),
            h("span", { class: "num" }, dinheiro(pg.valor_centavos))))),
          falta > 0 && !FINAIS.includes(p.status) ? h("div", { class: "alerta alerta-aviso", style: { marginTop: "8px" } }, `Falta receber ${dinheiro(falta)}`)
            : totalPago >= p.total_centavos ? h("div", { class: "alerta alerta-ok", style: { marginTop: "8px" } }, "Pago") : null,
          h("h3", { style: { marginTop: "16px" } }, "Histórico"),
          h("ul", { class: "lista-simples" }, (p.historico || []).map((x) => h("li", null,
            h("span", null, rotulo("StatusPedido", x.status_para), x.observacao ? h("span", { class: "muted" }, ` — ${x.observacao}`) : null),
            h("span", { class: "muted" }, dataHora(x.criado_em))))))),
    );

    const acoes = [];
    if (podeChamar() && !(chamada && chamada.status === "PROCURANDO")) {
      acoes.push(botaoAcao("🛵 Chamar entregador", chamar, "botao botao-primario"));
    }
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

  // ---- entrega pelo app ApFood Entregador: chamada em fila e códigos
  let chamada = null;
  let disponiveis = null;
  let juntar = [];
  let espera = null;
  const ativo = () => document.body.contains(m.el);
  const podeChamar = () => p.tipo_atendimento === "ENTREGA" && !p.entregador && ["RECEBIDO", "EM_PREPARO", "PRONTO"].includes(p.status);
  const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  function blocoEntrega() {
    const linhas = [h("h3", { style: { marginTop: "16px" } }, "Entrega")];
    if (p.entregador_nome) linhas.push(h("p", null, "🛵 Entregador: ", h("b", null, p.entregador_nome)));
    if (!FINAIS.includes(p.status) && p.status !== "SAIU_PARA_ENTREGA" && p.entregador) {
      linhas.push(h("div", { class: "alerta alerta-info codigo-retirada" },
        h("span", null, "Código de retirada"), h("b", null, p.codigo_retirada),
        h("small", null, "Informe ao entregador: ele digita no app ao pegar o pedido.")));
    }
    if (p.foto_entrega) {
      linhas.push(h("div", null, h("div", { class: "muted" }, "📷 Entregue com foto (cliente ausente):"),
        h("a", { href: p.foto_entrega, target: "_blank", rel: "noopener" }, h("img", { class: "foto-entrega-painel", src: p.foto_entrega, alt: "Foto da entrega" }))));
    }
    if (chamada) linhas.push(blocoChamada());
    else if (podeChamar()) linhas.push(h("p", { class: "muted" }, "Sem entregador. Use “Chamar entregador” para oferecer aos entregadores do app."));
    return h("div", null, linhas);
  }

  function blocoChamada() {
    const c = chamada;
    if (c.status === "PROCURANDO") {
      return h("div", { class: "alerta alerta-aviso chamada" },
        h("div", { class: "negrito" }, "Procurando entregador…"),
        c.juntos?.length ? h("div", null, `📦 Na mesma viagem: #${c.juntos.join(", #")}`) : null,
        c.entregador_atual ? h("div", null, `Oferecendo para ${c.entregador_atual} · ${c.segundos_oferta}s para aceitar`)
          : h("div", null, disponiveis ? "Passando para o próximo…" : "Nenhum entregador disponível no app agora — esperando alguém ficar online."),
        h("div", { class: "muted" }, `Tentativas: ${c.tentativas}${c.recusas ? ` · recusas: ${c.recusas}` : ""} · tempo restante ${mmss(c.segundos_total)}`),
        h("div", { class: "acoes", style: { marginTop: "6px" } },
          botaoAcao("Cancelar chamada", async () => { await post(`/api/pedidos/${p.id}/chamada/cancelar/`); await atualizarChamada(); }, "botao botao-pequeno")));
    }
    if (c.status === "ACEITA") return h("div", { class: "alerta alerta-ok" }, `✓ ${c.aceita_por} aceitou a entrega${c.juntos?.length ? ` (junto com #${c.juntos.join(", #")})` : ""}.`);
    if (c.status === "SEM_RESPOSTA" && podeChamar()) {
      return h("div", { class: "alerta alerta-erro chamada" },
        h("div", { class: "negrito" }, "Ninguém aceitou."),
        h("div", null, disponiveis ? `${disponiveis} entregador(es) online não responderam em 2 minutos.` : "Nenhum entregador estava disponível no app."),
        h("div", { class: "acoes", style: { marginTop: "6px" } },
          botaoAcao("Chamar novamente", chamar, "botao botao-primario botao-pequeno"),
          botaoAcao("Outra forma de entrega", outraForma, "botao botao-pequeno")));
    }
    return h("span");
  }

  async function chamar() {
    let extras = [];
    if (juntar.length) {
      extras = await escolherJuntos();
      if (extras === null) return;
    }
    const r = await post(`/api/pedidos/${p.id}/chamada/`, { juntar: extras });
    chamada = r.chamada; disponiveis = r.disponiveis;
    desenhar();
    acompanhar();
  }

  // Mais de uma entrega por viagem: outros pedidos sem entregador, do destino mais perto ao mais longe
  function escolherJuntos() {
    return new Promise((resolve) => {
      const marcados = new Set();
      let resposta = null;
      const linhas = juntar.map((o) => {
        const cx = h("input", { type: "checkbox", onchange: () => { if (cx.checked) marcados.add(o.id); else marcados.delete(o.id); } });
        if (o.mesmo_bairro || (o.distancia_km !== null && o.distancia_km <= 2)) { cx.checked = true; marcados.add(o.id); }
        return h("label", { class: "check" }, cx, h("span", null, h("b", null, `#${o.numero}`), ` · ${o.bairro || "—"}`,
          o.distancia_km !== null ? h("span", { class: "muted" }, ` · ${String(o.distancia_km).replace(".", ",")} km deste`) : null,
          o.mesmo_bairro ? h("span", { class: "etiqueta e-ok", style: { marginLeft: "6px" } }, "mesmo bairro") : null,
          h("span", { class: "muted" }, ` · ${rotulo("StatusPedido", o.status)}`)));
      });
      const mm = modal({
        titulo: "Levar outros pedidos na mesma viagem?", tamanho: "modal-pequeno",
        corpo: h("div", { class: "grade" }, h("p", { class: "muted" }, "Um entregador leva todos: a chamada mostra as entregas juntas e o app dele ordena as paradas."), ...linhas),
        rodape: [
          botaoAcao("Chamar só este", () => { resposta = []; mm.fechar(); }),
          botaoAcao("Chamar com os marcados", () => { resposta = [...marcados]; mm.fechar(); }, "botao botao-primario")],
        aoFechar: () => resolve(resposta),
      });
    });
  }

  async function outraForma() {
    const ents = await lista("/api/entregadores/", { ativo: "true" });
    const ops = ents.map((e) => ({ valor: e.id, rotulo: `${e.nome}${e.online_agora ? " · online" : ""}` }));
    const escolhido = await escolher("Quem vai entregar?", [...ops, { valor: "__proprio", rotulo: "Entrega própria / sem entregador cadastrado" }]);
    if (!escolhido) return;
    await post(`/api/pedidos/${p.id}/entregador/`, { entregador_id: escolhido === "__proprio" ? null : escolhido });
    chamada = null;
    await recarregar();
    aviso(escolhido === "__proprio" ? "Ok: marque “Saiu para entrega” quando sair." : "Entregador definido.", "ok");
  }

  async function atualizarChamada() {
    const r = await get(`/api/pedidos/${p.id}/chamada/`);
    const antes = chamada?.status;
    chamada = r.chamada; disponiveis = r.disponiveis; juntar = r.juntar || [];
    if (chamada?.status === "ACEITA" && antes === "PROCURANDO") { aviso(`${chamada.aceita_por} aceitou o pedido #${p.numero}.`, "ok"); await recarregar(); return; }
    desenhar();
  }

  function acompanhar() {
    clearTimeout(espera);
    if (!ativo() || chamada?.status !== "PROCURANDO") return;
    espera = setTimeout(async () => { try { await atualizarChamada(); } catch (e) { /* tenta de novo */ } acompanhar(); }, 2000);
  }

  desenhar();
  if (p.tipo_atendimento === "ENTREGA" && !FINAIS.includes(p.status)) {
    atualizarChamada().then(acompanhar).catch(() => {});
  }
  return m;
}

// Delivery no fechamento de caixa (gerente/administrador): pago online × na entrega × a receber, por entregador
export function cartaoDelivery(d, titulo = "Delivery no período") {
  if (!d || !d.pedidos) return h("div", { class: "cartao" }, h("h2", null, titulo), h("p", { class: "muted" }, "Nenhuma entrega concluída no período."));
  const linhas = (obj) => Object.entries(obj).map(([f, v]) => h("li", null, rotulo("FormaPagamento", f), h("span", { class: "num" }, dinheiro(v))));
  return h("div", { class: "cartao" }, h("h2", null, `🛵 ${titulo}`),
    h("div", { class: "grade grade-kpi", style: { marginBottom: "12px" } },
      h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Entregas"), h("div", { class: "kpi-valor" }, String(d.pedidos)),
        h("div", { class: "kpi-detalhe" }, `${dinheiro(d.total_centavos)} · taxas ${dinheiro(d.taxas_centavos)}`)),
      h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Pago online"), h("div", { class: "kpi-valor" }, dinheiro(d.online_centavos))),
      h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Recebido na entrega"), h("div", { class: "kpi-valor" }, dinheiro(d.na_entrega_centavos))),
      h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "A receber"),
        h("div", { class: "kpi-valor", style: { color: d.a_receber_centavos ? "var(--erro)" : "" } }, dinheiro(d.a_receber_centavos)),
        h("div", { class: "kpi-detalhe" }, "entregue sem pagamento registrado")),
      d.com_entregadores_centavos ? h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Com os entregadores"),
        h("div", { class: "kpi-valor" }, dinheiro(d.com_entregadores_centavos)),
        h("div", { class: "kpi-detalhe" }, "dinheiro cobrado, aguardando o repasse")) : null),
    h("div", { class: "grade grade-2" },
      h("div", null, h("h3", null, "Por forma de pagamento"),
        h("ul", { class: "lista-simples" }, ...linhas(d.online).map((li) => { li.firstChild.textContent = `Online · ${li.firstChild.textContent}`; return li; }),
          ...linhas(d.na_entrega).map((li) => { li.firstChild.textContent = `Na entrega · ${li.firstChild.textContent}`; return li; }))),
      h("div", null, h("h3", null, "Por entregador"),
        h("ul", { class: "lista-simples" }, d.por_entregador.map((e) => h("li", null,
          h("span", null, `${e.entregador} (${e.entregas})`, e.dinheiro_centavos ? h("span", { class: "muted" }, ` · dinheiro ${dinheiro(e.dinheiro_centavos)}`) : null,
            e.a_receber_centavos ? h("span", { class: "etiqueta e-erro", style: { marginLeft: "6px" } }, `falta ${dinheiro(e.a_receber_centavos)}`) : null),
          h("span", { class: "num" }, dinheiro(e.total_centavos))))))));
}

export { opcoes, sessao };
