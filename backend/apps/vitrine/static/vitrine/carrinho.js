/* ApFood — regras do carrinho do cardápio digital (puras, testáveis no Node).
 * Espelham apfood_core (totais.py / precos.py). O servidor sempre recalcula:
 * aqui é só para mostrar o preço certo enquanto o cliente monta o pedido. */
(function (raiz, fabrica) {
  if (typeof module === "object" && module.exports) module.exports = fabrica();
  else raiz.ApCarrinho = fabrica();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function reais(c) {
    const v = (c || 0) / 100;
    return "R$ " + v.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function paraCentavos(texto) {
    if (texto === null || texto === undefined || texto === "") return 0;
    let t = String(texto).replace(/[R$\s]/g, "");
    if (t.indexOf(",") >= 0) t = t.replace(/\./g, "").replace(",", ".");
    const n = Number(t);
    if (!isFinite(n) || n < 0) return NaN;
    return Math.round(n * 100);
  }

  /** Índices auxiliares a partir do JSON de /api/publico/lojas/<slug>/ */
  function indexar(cardapio) {
    const produtos = {}, categoriaDe = {};
    (cardapio.categorias || []).forEach(function (c) {
      c.produtos.forEach(function (p) { produtos[p.id] = p; categoriaDe[p.id] = c; });
    });
    return { produtos: produtos, categoriaDe: categoriaDe };
  }

  /** Preço unitário (sem adicionais) de um produto, num tamanho opcional. */
  function precoBase(produto, nomeVariacao) {
    if (nomeVariacao) {
      const v = (produto.variacoes || []).find(function (x) { return x.nome === nomeVariacao; });
      if (v) return v.preco_centavos;
    }
    return produto.preco_centavos;
  }

  /**
   * item = {produto_id, variacao_id?, sabores?: [ids, inclui o principal], adicionais: [{adicional_id, quantidade}], quantidade}
   * Devolve {unitario, adicionais_por_unidade, total}.
   */
  function precificar(idx, item) {
    const p = idx.produtos[item.produto_id];
    if (!p) return { unitario: 0, adicionais_por_unidade: 0, total: 0 };
    const variacao = item.variacao_id ? (p.variacoes || []).find(function (v) { return v.id === item.variacao_id; }) : null;
    const nomeVar = variacao ? variacao.nome : null;
    let unitario = variacao ? variacao.preco_centavos : p.preco_centavos;
    const sabores = item.sabores || [];
    if (sabores.length > 1) {
      const cat = idx.categoriaDe[p.id] || {};
      const precos = sabores.map(function (sid) { const sp = idx.produtos[sid]; return sp ? precoBase(sp, nomeVar) : 0; });
      unitario = cat.regra_preco_sabores === "MEDIA"
        ? Math.round(precos.reduce(function (a, b) { return a + b; }, 0) / precos.length)
        : Math.max.apply(null, precos);
    }
    const opcoes = {};
    (p.grupos || []).forEach(function (g) { g.opcoes.forEach(function (o) { opcoes[o.id] = o; }); });
    const ad = (item.adicionais || []).reduce(function (s, a) {
      const o = opcoes[a.adicional_id];
      return s + (o ? o.preco_centavos * (a.quantidade || 1) : 0);
    }, 0);
    const qtd = Math.max(1, item.quantidade || 1);
    return { unitario: unitario, adicionais_por_unidade: ad, total: (unitario + ad) * qtd };
  }

  /** Erros de montagem do item (mesmas regras do servidor). [] = válido. */
  function validar(idx, item) {
    const p = idx.produtos[item.produto_id];
    if (!p) return ["Produto indisponível"];
    const erros = [];
    if (p.esgotado) erros.push(p.nome + " está esgotado");
    if ((p.variacoes || []).length && !item.variacao_id) erros.push("Escolha o tamanho");
    const cat = idx.categoriaDe[p.id] || {};
    const sabores = item.sabores || [];
    if (sabores.length > Math.max(1, cat.max_sabores || 1)) erros.push("Máximo de " + cat.max_sabores + " sabores");
    const porGrupo = {};
    (item.adicionais || []).forEach(function (a) {
      (p.grupos || []).forEach(function (g) {
        const o = g.opcoes.find(function (x) { return x.id === a.adicional_id; });
        if (o) {
          porGrupo[g.id] = (porGrupo[g.id] || 0) + (a.quantidade || 1);
          if ((a.quantidade || 1) > (o.max_por_item || 1)) erros.push(o.nome + ": até " + (o.max_por_item || 1));
        }
      });
    });
    (p.grupos || []).forEach(function (g) {
      const n = porGrupo[g.id] || 0;
      if (n < g.min) erros.push(g.nome + ": escolha " + (g.min === 1 ? "uma opção" : "ao menos " + g.min));
      if (n > g.max) erros.push(g.nome + ": no máximo " + g.max);
    });
    return erros;
  }

  /** Descrição curta para o carrinho. */
  function descrever(idx, item) {
    const p = idx.produtos[item.produto_id] || { nome: "?" };
    let nome = p.nome;
    const sabores = item.sabores || [];
    if (sabores.length > 1) {
      nome = sabores.map(function (s) { return "1/" + sabores.length + " " + ((idx.produtos[s] || {}).nome || "?"); }).join(" + ");
    }
    if (item.variacao_id) {
      const v = (p.variacoes || []).find(function (x) { return x.id === item.variacao_id; });
      if (v) nome += " (" + v.nome + ")";
    }
    const nomes = {};
    (p.grupos || []).forEach(function (g) { g.opcoes.forEach(function (o) { nomes[o.id] = o.nome; }); });
    const extras = (item.adicionais || []).map(function (a) {
      return (a.quantidade > 1 ? a.quantidade + "x " : "") + (nomes[a.adicional_id] || "");
    }).filter(Boolean);
    return { titulo: nome, detalhe: extras.join(", ") };
  }

  /** Sabores que podem acompanhar `produto` (mesma categoria e mesmo tamanho disponível). */
  function saboresCompativeis(idx, produto, nomeVariacao) {
    const cat = idx.categoriaDe[produto.id];
    if (!cat || (cat.max_sabores || 1) < 2) return [];
    return cat.produtos.filter(function (p) {
      if (p.id === produto.id || p.esgotado) return false;
      if (!nomeVariacao) return !(p.variacoes || []).length;
      return (p.variacoes || []).some(function (v) { return v.nome === nomeVariacao; });
    });
  }

  function totais(idx, itens, taxa, desconto) {
    const subtotal = itens.reduce(function (s, i) { return s + precificar(idx, i).total; }, 0);
    const t = taxa || 0, d = Math.min(desconto || 0, subtotal + t);
    return { subtotal: subtotal, taxa: t, desconto: d, total: Math.max(0, subtotal + t - d) };
  }

  /** Carrinho salvo no navegador, por loja. */
  function Carrinho(slug, armazenamento) {
    this.chave = "apfood_carrinho_" + slug;
    this.store = armazenamento || (typeof localStorage !== "undefined" ? localStorage : null);
    this.itens = [];
    try { this.itens = JSON.parse((this.store && this.store.getItem(this.chave)) || "[]"); } catch (e) { this.itens = []; }
  }
  Carrinho.prototype.salvar = function () {
    try { if (this.store) this.store.setItem(this.chave, JSON.stringify(this.itens)); } catch (e) { /* modo privado */ }
  };
  Carrinho.prototype.adicionar = function (item) { this.itens.push(item); this.salvar(); };
  Carrinho.prototype.quantidade = function (i, delta) {
    const it = this.itens[i];
    if (!it) return;
    it.quantidade = (it.quantidade || 1) + delta;
    if (it.quantidade <= 0) this.itens.splice(i, 1);
    this.salvar();
  };
  Carrinho.prototype.limpar = function () { this.itens = []; this.salvar(); };
  Carrinho.prototype.contagem = function () {
    return this.itens.reduce(function (s, i) { return s + (i.quantidade || 1); }, 0);
  };
  /** Remove itens que sumiram do cardápio (produto/opção excluídos desde a última visita). */
  Carrinho.prototype.sanear = function (idx) {
    const antes = this.itens.length;
    this.itens = this.itens.filter(function (i) { return idx.produtos[i.produto_id] && validar(idx, i).length === 0; });
    if (this.itens.length !== antes) this.salvar();
    return antes - this.itens.length;
  };

  function telefoneValido(t) {
    const d = String(t || "").replace(/\D/g, "");
    return d.length === 10 || d.length === 11;
  }

  function mascaraTelefone(t) {
    const d = String(t || "").replace(/\D/g, "").slice(0, 11);
    if (d.length <= 2) return d;
    if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    if (d.length <= 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
    return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
  }

  return {
    reais: reais, paraCentavos: paraCentavos, indexar: indexar, precificar: precificar, validar: validar,
    descrever: descrever, saboresCompativeis: saboresCompativeis, totais: totais, Carrinho: Carrinho,
    telefoneValido: telefoneValido, mascaraTelefone: mascaraTelefone,
  };
});
