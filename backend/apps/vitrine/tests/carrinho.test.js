// node --test backend/apps/vitrine/tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const C = require("../static/vitrine/carrinho.js");

const CARDAPIO = {
  categorias: [
    { id: "lanches", max_sabores: 1, produtos: [
      { id: "x", nome: "X-Burger", preco_centavos: 3000, variacoes: [], esgotado: false, grupos: [
        { id: "ponto", nome: "Ponto", min: 1, max: 1, opcoes: [{ id: "ao", nome: "Ao ponto", preco_centavos: 0, max_por_item: 1 }] },
        { id: "extras", nome: "Extras", min: 0, max: 3, opcoes: [{ id: "bacon", nome: "Bacon", preco_centavos: 500, max_por_item: 2 }] },
      ] },
      { id: "fora", nome: "Esgotado", preco_centavos: 100, variacoes: [], esgotado: true, grupos: [] },
    ] },
    { id: "pizzas", max_sabores: 2, regra_preco_sabores: "MAIOR", produtos: [
      { id: "cal", nome: "Calabresa", preco_centavos: 4000, grupos: [], variacoes: [
        { id: "cal-m", nome: "Média", preco_centavos: 4000 }, { id: "cal-g", nome: "Grande", preco_centavos: 5000 }] },
      { id: "por", nome: "Portuguesa", preco_centavos: 4500, grupos: [], variacoes: [
        { id: "por-m", nome: "Média", preco_centavos: 4500 }, { id: "por-g", nome: "Grande", preco_centavos: 6000 }] },
      { id: "doce", nome: "Chocolate", preco_centavos: 4200, grupos: [], variacoes: [{ id: "d-m", nome: "Média", preco_centavos: 4200 }] },
    ] },
  ],
};
const idx = C.indexar(CARDAPIO);

test("preço com adicionais e quantidade (igual ao servidor)", () => {
  const item = { produto_id: "x", quantidade: 2, adicionais: [{ adicional_id: "ao", quantidade: 1 }, { adicional_id: "bacon", quantidade: 2 }] };
  assert.deepEqual(C.precificar(idx, item), { unitario: 3000, adicionais_por_unidade: 1000, total: 8000 });
  assert.deepEqual(C.validar(idx, item), []);
});

test("grupo obrigatório e limites", () => {
  assert.match(C.validar(idx, { produto_id: "x", adicionais: [] })[0], /Ponto/);
  const erros = C.validar(idx, { produto_id: "x", adicionais: [{ adicional_id: "ao" }, { adicional_id: "bacon", quantidade: 3 }] });
  assert.ok(erros.some((e) => /Bacon: até 2/.test(e)));
  assert.match(C.validar(idx, { produto_id: "fora" })[0], /esgotado/);
});

test("pizza meio a meio cobra o sabor mais caro no tamanho escolhido", () => {
  const item = { produto_id: "cal", variacao_id: "cal-g", sabores: ["cal", "por"], quantidade: 1 };
  assert.equal(C.precificar(idx, item).total, 6000);
  assert.equal(C.descrever(idx, item).titulo, "1/2 Calabresa + 1/2 Portuguesa (Grande)");
  // sabor sem o tamanho Grande não é oferecido
  assert.deepEqual(C.saboresCompativeis(idx, idx.produtos.cal, "Grande").map((p) => p.id), ["por"]);
  assert.match(C.validar(idx, { produto_id: "cal" })[0], /tamanho/);
});

test("regra MEDIA arredonda como o servidor", () => {
  const cat = CARDAPIO.categorias[1];
  cat.regra_preco_sabores = "MEDIA";
  assert.equal(C.precificar(idx, { produto_id: "cal", variacao_id: "cal-m", sabores: ["cal", "por"] }).total, 4250);
  cat.regra_preco_sabores = "MAIOR";
});

test("totais, dinheiro e telefone", () => {
  const t = C.totais(idx, [{ produto_id: "x", adicionais: [{ adicional_id: "ao" }] }], 500, 99999);
  assert.deepEqual(t, { subtotal: 3000, taxa: 500, desconto: 3500, total: 0 });
  assert.equal(C.reais(123456), "R$ 1.234,56");
  assert.equal(C.paraCentavos("50"), 5000);
  assert.equal(C.paraCentavos("1.234,5"), 123450);
  assert.ok(C.telefoneValido("(11) 98765-4321") && !C.telefoneValido("9876"));
  assert.equal(C.mascaraTelefone("11987654321"), "(11) 98765-4321");
});

test("carrinho persistido e saneado", () => {
  const mem = { d: {}, getItem(k) { return this.d[k] || null; }, setItem(k, v) { this.d[k] = v; } };
  const c = new C.Carrinho("burger", mem);
  c.adicionar({ produto_id: "x", quantidade: 1, adicionais: [{ adicional_id: "ao" }] });
  c.adicionar({ produto_id: "sumiu", quantidade: 1 });
  assert.equal(new C.Carrinho("burger", mem).itens.length, 2);
  assert.equal(c.sanear(idx), 1);
  c.quantidade(0, 2);
  assert.equal(c.contagem(), 3);
  c.quantidade(0, -3);
  assert.equal(c.itens.length, 0);
});
