// Configurações: loja, horários, fiscal, integrações, usuários, lojas e empresa.
import { ehAdmin, ehMaster, ErroApi, get, lista, patch, post, put, sessao } from "../api.js";
import { recarregarSessao } from "../app.js";
import { paginaCadastro } from "../crud.js";
import { formulario } from "../form.js";
import { aviso, botaoAcao, dataHora, erro, etiqueta, h, limpar, modal, rotulo, simNao, trocar } from "../ui.js";

const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

function editorHorarios(valor) {
  const linhas = [];
  const caixa = h("div", { class: "grade", style: { gap: "8px" } });
  const lista_ = h("div", { class: "grade", style: { gap: "6px" } });
  const adicionar = (hr = { dia_semana: 0, abre: "18:00", fecha: "23:00" }) => {
    const dia = h("select", null, DIAS.map((d, i) => h("option", { value: i, selected: Number(hr.dia_semana) === i }, d)));
    const abre = h("input", { type: "time", value: hr.abre });
    const fecha = h("input", { type: "time", value: hr.fecha });
    const linha = { dia, abre, fecha };
    const el = h("div", { class: "horarios-grade" }, dia, abre, fecha,
      h("button", { type: "button", class: "botao botao-pequeno botao-perigo", onclick: () => { linhas.splice(linhas.indexOf(linha), 1); el.remove(); } }, "Tirar"));
    linhas.push(linha);
    lista_.append(el);
  };
  (valor || []).forEach(adicionar);
  caixa.append(
    h("div", { class: "horarios-grade muted" }, h("small", null, "Dia"), h("small", null, "Abre"), h("small", null, "Fecha"), h("span")),
    lista_,
    h("div", { class: "acoes" },
      h("button", { type: "button", class: "botao botao-pequeno", onclick: () => adicionar() }, "+ Horário"),
      h("button", { type: "button", class: "botao botao-pequeno", onclick: () => {
        const base = linhas[0] ? { abre: linhas[0].abre.value, fecha: linhas[0].fecha.value } : { abre: "18:00", fecha: "23:00" };
        while (linhas.length) { linhas.pop(); }
        limpar(lista_);
        for (let d = 0; d < 7; d++) adicionar({ dia_semana: d, ...base });
      } }, "Todos os dias iguais")),
    h("small", { class: "muted" }, "Sem horários = vale só o botão \"Aberta para pedidos\". Se fecha depois da meia-noite, use o horário (ex.: 02:00)."));
  return { el: caixa, ler: () => linhas.map((l) => ({ dia_semana: Number(l.dia.value), abre: l.abre.value, fecha: l.fecha.value })) };
}

const CAMPOS_LOJA = [
  { secao: "Identificação" },
  { nome: "nome", rotulo: "Nome da loja", obrigatorio: true },
  { nome: "slug", rotulo: "Endereço do cardápio", obrigatorio: true, ajuda: "Letras minúsculas e hífen. Fica: seu-site/endereco/" },
  { nome: "cnpj", rotulo: "CNPJ" },
  { nome: "telefone", rotulo: "Telefone", tipo: "tel" },
  { nome: "whatsapp", rotulo: "WhatsApp", tipo: "tel" },
  { nome: "cor_primaria", rotulo: "Cor do cardápio", tipo: "cor" },
  { nome: "logo", rotulo: "Logo", tipo: "imagem", largo: true },
  { secao: "Endereço (usado na entrega por raio)" },
  { nome: "cep", rotulo: "CEP" },
  { nome: "logradouro", rotulo: "Rua", largo: true },
  { nome: "numero", rotulo: "Número" },
  { nome: "bairro", rotulo: "Bairro" },
  { nome: "cidade", rotulo: "Cidade" },
  { nome: "uf", rotulo: "UF", max: 2 },
  { nome: "latitude", rotulo: "Latitude", tipo: "decimal", passo: "0.0000001" },
  { nome: "longitude", rotulo: "Longitude", tipo: "decimal", passo: "0.0000001" },
  { secao: "Pedidos e operação" },
  { nome: "aberta_para_pedidos", rotulo: "Aberta para pedidos online", tipo: "bool" },
  { nome: "aceite_automatico", rotulo: "Aceitar pedidos online automaticamente", tipo: "bool" },
  { nome: "pedido_minimo_centavos", rotulo: "Pedido mínimo online (R$)", tipo: "dinheiro" },
  { nome: "tempo_preparo_min", rotulo: "Tempo de preparo (min)", tipo: "numero" },
  { nome: "taxa_servico_percentual", rotulo: "Taxa de serviço das mesas (%)", tipo: "decimal", passo: "0.01" },
  { nome: "momento_baixa_estoque", rotulo: "Baixar estoque no", tipo: "select", enum: "MomentoBaixaEstoque", obrigatorio: true },
  { secao: "Fidelidade" },
  { nome: "cashback_percentual", rotulo: "Cashback (%)", tipo: "decimal", passo: "0.01",
    ajuda: "Parte do valor de cada pedido concluído que volta como saldo para o cliente (identificado pelo telefone). 0 = desligado." },
  { nome: "ativa", rotulo: "Loja ativa", tipo: "bool" },
];

export function loja() {
  return {
    titulo: "Dados da loja",
    async render(raiz) {
      const l = await get(`/api/lojas/${sessao.loja.id}/`);
      const f = formulario(CAMPOS_LOJA, l);
      const horarios = editorHorarios(l.horarios);
      const salvar = botaoAcao("Salvar", async () => {
        let dados;
        try { dados = f.ler(); } catch (e) { f.mostrarErros(e.message); return; }
        const logo = dados.logo;
        delete dados.logo;
        dados.horarios = horarios.ler();
        try {
          await patch(`/api/lojas/${l.id}/`, dados);
          if (logo instanceof File) { const fd = new FormData(); fd.append("logo", logo); await patch(`/api/lojas/${l.id}/`, fd); }
          aviso("Loja atualizada.", "ok");
          await recarregarSessao();
        } catch (e) { if (e instanceof ErroApi && e.status === 400) f.mostrarErros(e.dados); else throw e; }
      }, "botao botao-primario");
      trocar(raiz, 
        h("div", { class: "cartao" }, f.el),
        h("div", { class: "cartao" }, h("h2", null, "Horário de funcionamento"), horarios.el),
        h("div", { class: "acoes acoes-fim", style: { marginTop: "16px" } },
          h("a", { class: "botao", href: `/${l.slug}/`, target: "_blank", rel: "noopener" }, "Ver cardápio online"), salvar));
    },
  };
}

// ---------------------------------------------------------------- fiscal
export function fiscal() {
  return {
    titulo: "Fiscal",
    async render(raiz) {
      const cfg = await get("/api/fiscal/configuracao/");
      const emissores = await lista("/api/integracoes/", { tipo: "FISCAL" });
      const f = formulario([
        { nome: "ativa", rotulo: "Emitir documentos fiscais nesta loja", tipo: "bool", largo: true },
        { nome: "modelo_padrao", rotulo: "Documento padrão", tipo: "select", obrigatorio: true,
          opcoes: [{ valor: "NFCE", rotulo: "NFC-e (modelo 65)" }, { valor: "NFE", rotulo: "NF-e (modelo 55)" }] },
        { nome: "ambiente", rotulo: "Ambiente", tipo: "select", enum: "AmbienteFiscal", obrigatorio: true, ajuda: "Use Homologação para testar; Produção vale de verdade." },
        { nome: "serie", rotulo: "Série", tipo: "numero" },
        { nome: "regime_tributario", rotulo: "Regime tributário", tipo: "select", enum: "RegimeTributario", obrigatorio: true },
        { nome: "inscricao_estadual", rotulo: "Inscrição estadual" },
        { nome: "inscricao_municipal", rotulo: "Inscrição municipal" },
        { nome: "cnae", rotulo: "CNAE" },
        { nome: "emitir_automaticamente", rotulo: "Emitir automaticamente ao concluir o pedido", tipo: "bool", largo: true },
        { nome: "informacoes_complementares", rotulo: "Informações complementares (rodapé da nota)", tipo: "textarea" },
      ], cfg);
      const salvar = botaoAcao("Salvar", async () => {
        try { await put("/api/fiscal/configuracao/", f.ler()); aviso("Configuração fiscal salva.", "ok"); }
        catch (e) { if (e instanceof ErroApi && e.status === 400) f.mostrarErros(e.dados); else throw e; }
      }, "botao botao-primario");
      const emissorAtivo = emissores.find((i) => i.ativo);
      trocar(raiz, 
        h("div", { class: `alerta ${emissorAtivo ? "alerta-ok" : "alerta-aviso"}`, style: { marginBottom: "16px" } },
          emissorAtivo ? `Emissor configurado: ${emissorAtivo.provedor}.`
            : "Nenhum emissor fiscal ativo: as vendas saem com comprovante NÃO fiscal. Para emitir NFC-e, cadastre o Focus NFe em Integrações (o certificado A1 e o CSC ficam no painel do Focus NFe).",
          " ", h("a", { href: "#/integracoes" }, "Abrir integrações")),
        h("div", { class: "cartao" }, f.el, h("div", { class: "acoes acoes-fim", style: { marginTop: "16px" } }, salvar)));
    },
  };
}

// ---------------------------------------------------------------- integrações
const PROVEDORES = {
  "FISCAL:focusnfe": { titulo: "Focus NFe (NFC-e e NF-e)", cred: [["token", "Token da API"]] },
  "PAGAMENTO:mercadopago": { titulo: "Mercado Pago (Pix com QR Code)", cred: [["access_token", "Access token (APP_USR-…)"]] },
  "WHATSAPP:zapi": { titulo: "Z-API (WhatsApp do status do pedido)", cred: [["instance", "ID da instância"], ["token", "Token"], ["client_token", "Client token (segurança)"]] },
  "MARKETPLACE:ifood": { titulo: "iFood", cred: [["client_id", "Client ID (vazio = app da plataforma)"], ["client_secret", "Client secret"]], conf: [["merchant_id", "Merchant ID da loja no iFood"]] },
  "MAPAS:google": { titulo: "Google Maps (distância e geocodificação)", cred: [["api_key", "API key"]] },
};

export function integracoes() {
  return {
    titulo: "Integrações",
    async render(raiz) {
      const area = h("div");
      trocar(raiz, h("p", { class: "muted" }, "Os segredos ficam cifrados no servidor e nunca são exibidos de volta. Deixe em branco para manter os atuais."), area);
      async function carregar() {
        const atuais = await lista("/api/integracoes/");
        trocar(area, h("div", { class: "grade grade-2" }, Object.entries(PROVEDORES).map(([chave, p]) => {
          const [tipo, provedor] = chave.split(":");
          const i = atuais.find((x) => x.tipo === tipo && x.provedor === provedor);
          return h("div", { class: "cartao" },
            h("div", { class: "acoes" }, h("h3", { style: { flex: 1, margin: 0 } }, p.titulo),
              i ? etiqueta(i.ativo ? "Ativa" : "Desligada", i.ativo ? "e-ok" : "") : etiqueta("Não configurada")),
            h("p", { class: "muted" }, rotulo("TipoIntegracao", tipo)),
            i?.ultimo_erro ? h("div", { class: "alerta alerta-erro" }, `Último erro: ${i.ultimo_erro.slice(0, 200)}`) : null,
            i?.ultimo_sucesso_em ? h("p", { class: "muted" }, `Funcionou pela última vez em ${dataHora(i.ultimo_sucesso_em)}`) : null,
            h("button", { type: "button", class: "botao", onclick: () => editar(tipo, provedor, p, i) }, i ? "Configurar" : "Ativar"));
        })));
      }
      function editar(tipo, provedor, p, i) {
        const campos = [
          { nome: "ativo", rotulo: "Ativa", tipo: "bool", largo: true },
          ...(p.conf || []).map(([k, r]) => ({ nome: `conf_${k}`, rotulo: r })),
          ...p.cred.map(([k, r]) => ({ nome: `cred_${k}`, rotulo: r, tipo: "senha", ajuda: i?.tem_credenciais ? "Já salvo — preencha só para trocar." : "" })),
        ];
        const valores = { ativo: i ? i.ativo : true };
        for (const [k] of p.conf || []) valores[`conf_${k}`] = i?.configuracao?.[k] || "";
        const f = formulario(campos, valores);
        const m = modal({ titulo: p.titulo, corpo: f.el, rodape: [botaoAcao("Salvar", async () => {
          const d = f.ler();
          const corpo = { tipo, provedor, ativo: d.ativo, configuracao: { ...(i?.configuracao || {}) }, credenciais: {} };
          for (const [k] of p.conf || []) corpo.configuracao[k] = d[`conf_${k}`] || "";
          for (const [k] of p.cred) if (d[`cred_${k}`]) corpo.credenciais[k] = d[`cred_${k}`];
          if (!Object.keys(corpo.credenciais).length) delete corpo.credenciais;
          try {
            if (i) await patch(`/api/integracoes/${i.id}/`, corpo); else await post("/api/integracoes/", corpo);
            aviso("Integração salva.", "ok"); m.fechar(); carregar();
          } catch (e) { if (e instanceof ErroApi && e.status === 400) f.mostrarErros(e.dados); else throw e; }
        }, "botao botao-primario")] });
      }
      await carregar();
    },
  };
}

// ---------------------------------------------------------------- usuários
export function usuarios() {
  const papeisPermitidos = () => ehMaster() ? ["MASTER", "ADMIN", "GERENTE", "OPERADOR"]
    : ehAdmin() ? ["ADMIN", "GERENTE", "OPERADOR"] : ["OPERADOR"];
  return paginaCadastro({
    titulo: "Usuários", singular: "Usuário", url: "/api/usuarios/", busca: ["username", "nome", "email", "empresa_nome"],
    intro: "Operadores usam o PDV e o próprio caixa; gerentes veem relatórios e fecham caixas; administradores configuram a empresa.",
    podeCriar: () => true, podeEditar: () => true,
    novo: { papel: "OPERADOR", is_active: true, lojas: sessao.loja ? [sessao.loja.id] : [] },
    nomeDe: (u) => u.nome,
    colunas: [
      { rotulo: "Nome", valor: (u) => h("div", null, h("div", { class: "negrito" }, u.nome), h("small", { class: "muted" }, u.username)) },
      { rotulo: "Perfil", valor: (u) => rotulo("PapelUsuario", u.papel) },
      ...(ehMaster() ? [{ rotulo: "Empresa", valor: (u) => u.empresa_nome || "—" }] : []),
      { rotulo: "PIN", valor: (u) => simNao(u.tem_pin) },
      { rotulo: "Último acesso", valor: (u) => dataHora(u.last_login) || "—" },
      { rotulo: "Ativo", valor: (u) => simNao(u.is_active) },
    ],
    campos: (u) => [
      { nome: "username", rotulo: "Login", obrigatorio: true, ajuda: "Usado para entrar. Sem espaços." },
      { nome: "first_name", rotulo: "Nome" },
      { nome: "last_name", rotulo: "Sobrenome" },
      { nome: "email", rotulo: "E-mail", tipo: "email", ajuda: "Usado no \"Esqueci minha senha\"." },
      { nome: "password", rotulo: u ? "Nova senha (vazio = manter)" : "Senha", tipo: "senha", obrigatorio: !u, ajuda: "Mínimo de 6 caracteres." },
      { nome: "pin", rotulo: "PIN do PDV (4 a 6 dígitos)", tipo: "senha", ajuda: u?.tem_pin ? "Já definido — preencha só para trocar." : "Para troca rápida de operador no PDV desktop." },
      ...(u && u.id === sessao.usuario?.id ? [] : [
        { nome: "papel", rotulo: "Perfil", tipo: "select", obrigatorio: true, opcoes: papeisPermitidos().map((p) => ({ valor: p, rotulo: rotulo("PapelUsuario", p) })) },
        ...(ehMaster() ? [{ nome: "empresa", rotulo: "Empresa", tipo: "fk", url: "/api/empresas/", mostrarSe: (v) => v.papel !== "MASTER" }] : []),
        { nome: "lojas", rotulo: "Lojas que acessa", tipo: "multi", url: "/api/lojas/", mostrarSe: (v) => ["GERENTE", "OPERADOR"].includes(v.papel),
          ajuda: "Administradores acessam todas as lojas da empresa." },
        { nome: "is_active", rotulo: "Ativo (pode entrar)", tipo: "bool" },
      ]),
    ],
    antesDeSalvar: (d) => {
      const r = { ...d };
      if (!r.pin) delete r.pin;
      if (r.papel === "MASTER") r.empresa = null;
      return r;
    },
    podeExcluir: (u) => u.is_active && u.id !== sessao.usuario?.id, textoExcluir: "Desativar",
  });
}

// ---------------------------------------------------------------- lojas e empresa
export function lojas() {
  return paginaCadastro({
    titulo: "Lojas", singular: "Loja", url: "/api/lojas/", busca: ["nome", "slug", "empresa_nome"],
    podeCriar: () => ehAdmin(), podeEditar: () => ehAdmin(),
    novo: { ativa: true, momento_baixa_estoque: "CONCLUSAO", tempo_preparo_min: 30, taxa_servico_percentual: "10" },
    colunas: [
      { rotulo: "Loja", campo: "nome" },
      ...(ehMaster() ? [{ rotulo: "Empresa", campo: "empresa_nome" }] : []),
      { rotulo: "Cardápio", valor: (l) => h("a", { href: `/${l.slug}/`, target: "_blank", rel: "noopener" }, `/${l.slug}/`) },
      { rotulo: "Cidade", campo: "cidade" },
      { rotulo: "Pedidos online", valor: (l) => l.aberta_para_pedidos ? etiqueta("Abertos", "e-ok") : etiqueta("Fechados") },
      { rotulo: "Ativa", valor: (l) => simNao(l.ativa) },
    ],
    campos: (l) => [
      ...(ehMaster() && !l ? [{ nome: "empresa", rotulo: "Empresa", tipo: "fk", url: "/api/empresas/", obrigatorio: true }] : []),
      ...CAMPOS_LOJA,
    ],
    antesDeSalvar: (d) => ({ ...d, slug: String(d.slug || "").toLowerCase().trim() }),
    depoisDeSalvar: () => recarregarSessao(),
  });
}

export function minhaEmpresa() {
  return {
    titulo: "Minha empresa",
    async render(raiz) {
      const e = await get(`/api/empresas/${sessao.usuario.empresa.id}/`);
      const f = formulario([
        { nome: "nome", rotulo: "Nome fantasia", obrigatorio: true },
        { nome: "razao_social", rotulo: "Razão social" },
        { nome: "cnpj", rotulo: "CNPJ/CPF" },
        { nome: "responsavel", rotulo: "Responsável" },
        { nome: "email", rotulo: "E-mail", tipo: "email" },
        { nome: "telefone", rotulo: "Telefone", tipo: "tel" },
      ], e);
      const faturas = await lista("/api/faturas/").catch(() => []);
      trocar(raiz, 
        h("div", { class: "grade grade-kpi", style: { marginBottom: "16px" } },
          h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Plano"), h("div", { class: "kpi-valor" }, e.plano_nome || "—")),
          h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Assinatura"), h("div", { class: "kpi-valor", style: { fontSize: "20px" } }, rotulo("StatusAssinatura", e.status_assinatura))),
          h("div", { class: "kpi" }, h("div", { class: "kpi-rotulo" }, "Lojas"), h("div", { class: "kpi-valor" }, `${e.qtd_lojas}${e.limite_lojas ? ` / ${e.limite_lojas}` : ""}`))),
        h("div", { class: "cartao" }, f.el, h("div", { class: "acoes acoes-fim", style: { marginTop: "16px" } }, botaoAcao("Salvar", async () => {
          try { await patch(`/api/empresas/${e.id}/`, f.ler()); aviso("Dados salvos.", "ok"); }
          catch (er) { if (er instanceof ErroApi && er.status === 400) f.mostrarErros(er.dados); else erro(er); }
        }, "botao botao-primario"))),
        faturas.length ? h("div", { class: "cartao" }, h("h2", null, "Faturas"), h("ul", { class: "lista-simples" }, faturas.map((ft) => h("li", null,
          h("span", null, `${String(ft.competencia).slice(5, 7)}/${String(ft.competencia).slice(0, 4)} — vence ${String(ft.vencimento).split("-").reverse().join("/")}`),
          h("span", { class: "acoes" }, rotulo("StatusFatura", ft.status),
            ft.link_pagamento && ft.status !== "PAGA" ? h("a", { class: "botao botao-pequeno", href: ft.link_pagamento, target: "_blank", rel: "noopener" }, "Pagar") : null))))) : null);
    },
  };
}
