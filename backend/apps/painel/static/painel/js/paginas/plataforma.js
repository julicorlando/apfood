// Área do MASTER: empresas clientes, planos e faturas da plataforma.
import { ErroApi, get, post } from "../api.js";
import { recarregarSessao } from "../app.js";
import { paginaCadastro } from "../crud.js";
import { formulario } from "../form.js";
import { aviso, botaoAcao, data, dinheiro, etiquetaStatus, h, kpi, modal, simNao, tabela, trocar } from "../ui.js";

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
  });
}
