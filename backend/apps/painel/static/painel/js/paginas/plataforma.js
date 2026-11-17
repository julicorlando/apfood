// Área do MASTER: empresas clientes, planos e faturas da plataforma.
import { ErroApi, get, post, put } from "../api.js";
import { recarregarSessao } from "../app.js";
import { paginaCadastro } from "../crud.js";
import { formulario } from "../form.js";
import { aviso, botaoAcao, confirmar, data, dinheiro, erro, etiquetaStatus, h, kpi, modal, simNao, tabela, trocar } from "../ui.js";

export function visaoGeral() {
  return {
    titulo: "Visão geral da plataforma",
    async render(raiz) {
      const sel = h("select", null, [["dia", "Hoje"], ["semana", "Esta semana"], ["mes", "Este mês"]].map(([v, r]) => h("option", { value: v, selected: v === "mes" }, r)));
      const area = h("div");
      trocar(raiz, h("div", { class: "barra-ferramentas" }, sel), area);
      const carregar = async () => {
        const r = await get(`/api/plataforma/resumo/?periodo=${sel.value}`, { semLoja: true });
        const ativas = r.empresas.filter((e) => e.ativa);
        trocar(area, 
          h("div", { class: "grade grade-kpi" },
            kpi("Empresas", String(r.empresas.length), `${ativas.length} ativas`),
            kpi("Lojas", String(r.empresas.reduce((s, e) => s + e.lojas, 0))),
            kpi("Faturamento das lojas", dinheiro(r.total_faturamento_centavos)),
            kpi("Pedidos", String(r.empresas.reduce((s, e) => s + e.pedidos, 0)))),
          h("div", { style: { marginTop: "16px" } }, tabela([
            { rotulo: "Empresa", campo: "nome" },
            { rotulo: "Plano", valor: (e) => e.plano || "—" },
            { rotulo: "Assinatura", valor: (e) => etiquetaStatus("StatusAssinatura", e.status_assinatura) },
            { rotulo: "Lojas", classe: "num", campo: "lojas" },
            { rotulo: "Pedidos", classe: "num", campo: "pedidos" },
            { rotulo: "Faturamento", classe: "num", valor: (e) => dinheiro(e.faturamento_centavos) },
            { rotulo: "Ativa", valor: (e) => simNao(e.ativa) },
          ], r.empresas, { vazio: "Nenhuma empresa cadastrada.", aoClicar: () => { location.hash = "#/empresas"; } })));
      };
      sel.addEventListener("change", carregar);
      await carregar();
    },
  };
}

function novaEmpresa(recarregar) {
  const f = formulario([
    { secao: "Empresa" },
    { nome: "empresa_nome", rotulo: "Nome fantasia", obrigatorio: true },
    { nome: "empresa_cnpj", rotulo: "CNPJ/CPF" },
    { nome: "empresa_email", rotulo: "E-mail", tipo: "email" },
    { nome: "empresa_telefone", rotulo: "Telefone", tipo: "tel" },
    { nome: "empresa_plano", rotulo: "Plano", tipo: "fk", url: "/api/planos/" },
    { nome: "empresa_status_assinatura", rotulo: "Assinatura", tipo: "select", enum: "StatusAssinatura", obrigatorio: true },
    { secao: "Primeira loja" },
    { nome: "loja_nome", rotulo: "Nome da loja", obrigatorio: true },
    { nome: "loja_slug", rotulo: "Endereço do cardápio", obrigatorio: true, ajuda: "Ex.: burger-centro" },
    { secao: "Administrador da empresa" },
    { nome: "admin_first_name", rotulo: "Nome" },
    { nome: "admin_email", rotulo: "E-mail", tipo: "email" },
    { nome: "admin_username", rotulo: "Login", obrigatorio: true },
    { nome: "admin_password", rotulo: "Senha inicial", tipo: "senha", obrigatorio: true },
  ], { empresa_status_assinatura: "TRIAL" });
  const m = modal({ titulo: "Nova empresa", corpo: f.el, tamanho: "modal-grande", rodape: [botaoAcao("Cadastrar empresa", async () => {
    const d = f.ler();
    const parte = (pref) => Object.fromEntries(Object.entries(d).filter(([k]) => k.startsWith(pref)).map(([k, v]) => [k.slice(pref.length), v]));
    const corpo = { empresa: parte("empresa_"), loja: { ...parte("loja_"), slug: String(d.loja_slug || "").toLowerCase() }, admin: parte("admin_") };
    if (!corpo.empresa.cnpj) corpo.empresa.cnpj = null;
    try {
      await post("/api/empresas/onboarding/", corpo, { semLoja: true });
      aviso("Empresa, loja e administrador criados.", "ok");
      m.fechar();
      await recarregarSessao();
      recarregar();
    } catch (e) {
      if (e instanceof ErroApi && e.status === 400 && typeof e.dados === "object") {
        const plano = {};
        for (const [grupo, erros] of Object.entries(e.dados)) {
          if (typeof erros === "object" && !Array.isArray(erros)) for (const [k, v] of Object.entries(erros)) plano[`${grupo}_${k}`] = v;
          else plano[grupo] = erros;
        }
        f.mostrarErros(plano);
      } else throw e;
    }
  }, "botao botao-primario")] });
}

export function empresas() {
  return paginaCadastro({
    titulo: "Empresas", singular: "Empresa", url: "/api/empresas/", busca: ["nome", "cnpj", "email", "responsavel"],
    textoNovo: "Nova empresa", podeCriar: () => false, podeEditar: () => true,
    topo: (recarregar) => h("button", { type: "button", class: "botao botao-primario", onclick: () => novaEmpresa(recarregar) }, "+ Nova empresa"),
    colunas: [
      { rotulo: "Empresa", valor: (e) => h("div", null, h("div", { class: "negrito" }, e.nome), h("small", { class: "muted" }, e.cnpj || "")) },
      { rotulo: "Plano", valor: (e) => e.plano_nome || "—" },
      { rotulo: "Assinatura", valor: (e) => etiquetaStatus("StatusAssinatura", e.status_assinatura) },
      { rotulo: "Lojas", classe: "num", valor: (e) => `${e.qtd_lojas}${e.limite_lojas ? ` / ${e.limite_lojas}` : ""}` },
      { rotulo: "Ativa", valor: (e) => simNao(e.ativa) },
    ],
    campos: [
      { nome: "nome", rotulo: "Nome fantasia", obrigatorio: true },
      { nome: "razao_social", rotulo: "Razão social" },
      { nome: "cnpj", rotulo: "CNPJ/CPF" },
      { nome: "responsavel", rotulo: "Responsável" },
      { nome: "email", rotulo: "E-mail", tipo: "email" },
      { nome: "telefone", rotulo: "Telefone", tipo: "tel" },
      { secao: "Assinatura e limites" },
      { nome: "plano", rotulo: "Plano", tipo: "fk", url: "/api/planos/" },
      { nome: "status_assinatura", rotulo: "Assinatura", tipo: "select", enum: "StatusAssinatura", obrigatorio: true },
      { nome: "trial_ate", rotulo: "Teste grátis até", tipo: "data" },
      { nome: "dia_vencimento", rotulo: "Dia do vencimento", tipo: "numero" },
      { nome: "limite_lojas", rotulo: "Limite de lojas (vazio = do plano)", tipo: "numero", nulo: true },
      { nome: "limite_usuarios", rotulo: "Limite de usuários (vazio = do plano)", tipo: "numero", nulo: true },
      { nome: "ativa", rotulo: "Ativa (desmarcar bloqueia todos os usuários)", tipo: "bool", largo: true },
      { nome: "motivo_bloqueio", rotulo: "Motivo do bloqueio", mostrarSe: (v) => !v.ativa },
      { nome: "observacoes", rotulo: "Observações internas", tipo: "textarea" },
    ],
    antesDeSalvar: (d) => ({ ...d, cnpj: d.cnpj || null }),
    acoes: (e) => botaoAcao("Demonstração", async () => {
      if (!(await confirmar(`Preencher a loja de "${e.nome}" com dados de demonstração? Cria cardápio, estoque, mesas, `
        + "clientes, promoções e um mês de pedidos de exemplo. Não apaga nada que já existe.", { ok: "Preencher" }))) return;
      try {
        const r = await post(`/api/empresas/${e.id}/demonstracao/`, {});
        aviso(`Preenchendo "${r.loja}"… leva cerca de 1 a 2 minutos.`, "ok");
      } catch (err) { erro(err); }
    }, "botao botao-pequeno"),
  });
}

export function planos() {
  return paginaCadastro({
    titulo: "Planos", singular: "Plano", url: "/api/planos/", busca: ["nome"], podeCriar: () => true, podeEditar: () => true,
    novo: { ativo: true, publico: true, dias_trial: 14, recursos: [] },
    colunas: [
      { rotulo: "Plano", campo: "nome" },
      { rotulo: "Mensal", classe: "num", valor: (p) => dinheiro(p.preco_mensal_centavos) },
      { rotulo: "Lojas", classe: "num", valor: (p) => p.limite_lojas ?? "∞" },
      { rotulo: "Usuários", classe: "num", valor: (p) => p.limite_usuarios ?? "∞" },
      { rotulo: "Recursos", valor: (p) => (p.recursos || []).join(", ") || "—" },
      { rotulo: "Ativo", valor: (p) => simNao(p.ativo) },
    ],
    campos: [
      { nome: "nome", rotulo: "Nome", obrigatorio: true },
      { nome: "preco_mensal_centavos", rotulo: "Preço mensal (R$)", tipo: "dinheiro", obrigatorio: true },
      { nome: "descricao", rotulo: "Descrição", tipo: "textarea" },
      { nome: "limite_lojas", rotulo: "Limite de lojas (vazio = ilimitado)", tipo: "numero", nulo: true },
      { nome: "limite_usuarios", rotulo: "Limite de usuários (vazio = ilimitado)", tipo: "numero", nulo: true },
      { nome: "dias_trial", rotulo: "Dias de teste grátis", tipo: "numero" },
      { nome: "recursos", rotulo: "Recursos incluídos", tipo: "multi",
        opcoes: ["fiscal", "mesas", "marketplace", "pix", "whatsapp", "multiloja", "kds"].map((r) => ({ valor: r, rotulo: r })) },
      { nome: "ordem", rotulo: "Ordem", tipo: "numero" },
      { nome: "publico", rotulo: "Aparece na página de planos", tipo: "bool" },
      { nome: "ativo", rotulo: "Ativo", tipo: "bool" },
    ],
    podeExcluir: (p) => p.ativo, textoExcluir: "Desativar",
  });
}

export function faturas() {
  return paginaCadastro({
    titulo: "Faturas", singular: "Fatura", url: "/api/faturas/", busca: ["empresa_nome"], podeCriar: () => true, podeEditar: () => true,
    nomeDe: (f) => `${f.empresa_nome} ${String(f.competencia).slice(5, 7)}/${String(f.competencia).slice(0, 4)}`,
    filtros: [{ nome: "status", rotulo: "Todas", opcoes: ["ABERTA", "PAGA", "VENCIDA", "CANCELADA"].map((s) => ({ valor: s, rotulo: s.charAt(0) + s.slice(1).toLowerCase() })) }],
    colunas: [
      { rotulo: "Empresa", campo: "empresa_nome" },
      { rotulo: "Competência", valor: (f) => `${String(f.competencia).slice(5, 7)}/${String(f.competencia).slice(0, 4)}` },
      { rotulo: "Valor", classe: "num", valor: (f) => dinheiro(f.valor_centavos) },
      { rotulo: "Vencimento", valor: (f) => data(f.vencimento) },
      { rotulo: "Situação", valor: (f) => etiquetaStatus("StatusFatura", f.status) },
    ],
    campos: [
      { nome: "empresa", rotulo: "Empresa", tipo: "fk", url: "/api/empresas/", obrigatorio: true },
      { nome: "plano", rotulo: "Plano", tipo: "fk", url: "/api/planos/" },
      { nome: "competencia", rotulo: "Competência (1º dia do mês)", tipo: "data", obrigatorio: true },
      { nome: "valor_centavos", rotulo: "Valor (R$)", tipo: "dinheiro", obrigatorio: true },
      { nome: "vencimento", rotulo: "Vencimento", tipo: "data", obrigatorio: true },
      { nome: "status", rotulo: "Situação", tipo: "select", enum: "StatusFatura", obrigatorio: true },
      { nome: "forma_pagamento", rotulo: "Pago com", tipo: "select", enum: "FormaPagamento" },
      { nome: "pago_em", rotulo: "Pago em", tipo: "datahora" },
      { nome: "link_pagamento", rotulo: "Link de pagamento" },
    ],
    novo: { status: "ABERTA" },
    antesDeSalvar: (d) => ({ ...d, forma_pagamento: d.forma_pagamento || "" }),
    acoes: (f, recarregar) => (f.status === "ABERTA" ? [
      f.link_pagamento ? h("a", { class: "botao botao-pequeno", href: f.link_pagamento, target: "_blank", rel: "noopener" }, "Abrir link") : null,
      f.link_pagamento ? botaoAcao("Copiar link", async () => {
        try { await navigator.clipboard.writeText(f.link_pagamento); aviso("Link copiado.", "ok"); } catch { aviso(f.link_pagamento); }
      }, "botao botao-pequeno") : null,
      botaoAcao(f.link_pagamento ? "Gerar de novo" : "Gerar cobrança", async () => {
        try { await post(`/api/faturas/${f.id}/cobrar/`, {}); aviso("Link de pagamento gerado.", "ok"); recarregar(); } catch (e) { erro(e); }
      }, "botao botao-pequeno"),
      botaoAcao("Marcar paga", async () => {
        if (!(await confirmar(`Dar baixa manual na fatura de ${f.empresa_nome} (${dinheiro(f.valor_centavos)})? Use quando recebeu por fora do Mercado Pago.`, { ok: "Marcar paga" }))) return;
        try { await post(`/api/faturas/${f.id}/marcar-paga/`, { forma: "PIX" }); aviso("Fatura paga. Empresa liberada.", "ok"); recarregar(); } catch (e) { erro(e); }
      }, "botao botao-pequeno"),
    ] : null),
  });
}

// ---------------------------------------------------------------- recebimentos (Mercado Pago da plataforma)
export function recebimentos() {
  return {
    titulo: "Recebimentos",
    async render(raiz) {
      const desenhar = async (d) => {
        d = d || await get("/api/plataforma/recebimentos/", { semLoja: true });
        const token = h("input", { type: "password", autocomplete: "off", placeholder: d.configurado ? "•••••• (salvo) — cole outro para trocar" : "APP_USR-…" });
        const metodo = h("select", null, d.metodos.map((m) => h("option", { value: m.valor, selected: m.valor === d.metodo }, m.rotulo)));
        const msg = h("div", { class: "alerta alerta-erro", hidden: true });
        const salvar = async (corpo) => {
          msg.hidden = true;
          try { await desenhar(await put("/api/plataforma/recebimentos/", corpo, { semLoja: true })); aviso("Salvo.", "ok"); }
          catch (e) { msg.textContent = e.mensagem || String(e); msg.hidden = false; }
        };
        const situacao = d.configurado
          ? h("div", { class: "alerta alerta-ok" }, `Recebendo pelo Mercado Pago${d.conta ? ` (conta ${d.conta})` : ""}`
            + (d.origem === "ambiente" ? " — token da variável APFOOD_MP_TOKEN_PLATAFORMA." : "."))
          : h("div", { class: "alerta alerta-aviso" }, "Mercado Pago não configurado: as faturas são geradas, mas sem link de pagamento.");
        trocar(raiz,
          h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
            kpi("Recebido no mês", dinheiro(d.recebido_mes.valor_centavos), `${d.recebido_mes.quantidade} fatura(s)`),
            kpi("Últimos 30 dias", dinheiro(d.recebido_30d.valor_centavos), `${d.recebido_30d.quantidade} fatura(s)`),
            kpi("A vencer", dinheiro(d.em_aberto.valor_centavos), `${d.em_aberto.quantidade} fatura(s)`),
            kpi("Vencido", dinheiro(d.vencido.valor_centavos), `${d.vencido.quantidade} fatura(s)`)),
          h("div", { class: "cartao" },
            h("h2", null, "Conta que recebe as assinaturas"),
            situacao, msg,
            h("div", { class: "grade grade-2", style: { marginTop: "12px" } },
              h("label", { class: "campo" }, h("span", null, "Access token de produção do Mercado Pago"), token,
                h("small", { class: "muted" }, "Mercado Pago → Seu negócio → Configurações → Credenciais de produção. Fica guardado cifrado.")),
              h("label", { class: "campo" }, h("span", null, "Como o cliente paga"), metodo)),
            h("div", { class: "acoes", style: { marginTop: "12px" } },
              botaoAcao("Salvar e conferir", () => salvar({ ...(token.value.trim() ? { token: token.value.trim() } : {}), metodo: metodo.value }), "botao botao-primario"),
              d.origem === "painel" ? botaoAcao("Remover token", async () => {
                if (await confirmar("Remover o token salvo? As cobranças novas ficam sem link.", { perigo: true, ok: "Remover" })) salvar({ token: "" });
              }) : null),
            h("p", { class: "suave", style: { marginTop: "14px" } }, "Notificações de pagamento (webhook) — cadastre no Mercado Pago, evento \"Pagamentos\":"),
            h("code", { style: { display: "block", padding: "8px", background: "var(--fundo)", borderRadius: "8px", wordBreak: "break-all" } }, d.webhook_url),
            h("p", { class: "suave", style: { marginTop: "8px" } }, "Quando o pagamento é aprovado, a fatura vira paga sozinha e a empresa bloqueada é liberada.")),
          h("div", { class: "cartao" },
            h("h2", null, "Faturas sem link de pagamento"),
            h("p", null, d.sem_link ? `${d.sem_link} fatura(s) em aberto ainda sem link.` : "Todas as faturas em aberto já têm link."),
            h("div", { class: "acoes" },
              d.sem_link && d.configurado ? botaoAcao("Gerar links agora", async () => {
                try {
                  const r = await post("/api/plataforma/recebimentos/", {}, { semLoja: true });
                  aviso(`${r.gerados} link(s) gerado(s).` + (r.falhas.length ? ` Falhas: ${r.falhas.join("; ")}` : ""), r.falhas.length ? "" : "ok");
                  desenhar(r);
                } catch (e) { erro(e); }
              }, "botao botao-primario") : null,
              h("a", { class: "botao", href: "#/faturas" }, "Ver faturas"))));
      };
      await desenhar();
    },
  };
}
