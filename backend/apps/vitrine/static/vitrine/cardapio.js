/* ApFood — cardápio digital: lista, montagem do item, carrinho e checkout.
 * Usa só a API pública (/api/publico/...) e ApCarrinho (carrinho.js). */
(function () {
  "use strict";
  const C = window.ApCarrinho;
  const DADOS = JSON.parse(document.getElementById("dados-cardapio").textContent);
  const LOJA = DADOS.loja;
  const API = "/api/publico/lojas/" + encodeURIComponent(LOJA.slug) + "/";
  const idx = C.indexar(DADOS);
  const MESA = DADOS.mesa || null;  // autoatendimento pelo QR Code da mesa
  const TOTEM = DADOS.totem || null;  // totem de autoatendimento no balcão
  const carrinho = new C.Carrinho(MESA ? LOJA.slug + ":mesa:" + MESA.token : TOTEM ? LOJA.slug + ":totem" : LOJA.slug);
  const estado = {
    tipo: LOJA.entrega ? "ENTREGA" : "RETIRADA", taxa: null, taxaErro: "", coords: null, cupom: null,
    pagamento: LOJA.pix_online ? "PIX" : "DINHEIRO", enviando: false,
    agendar: !LOJA.aberta && !!LOJA.agendamento, dia: "", hora: "",
  };

  // ------------------------------------------------------------- utilidades
  function el(tag, attrs, filhos) {
    const e = document.createElement(tag);
    Object.entries(attrs || {}).forEach(function ([k, v]) {
      if (v === null || v === undefined || v === false) return;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v === true) e.setAttribute(k, "");
      else e.setAttribute(k, v);
    });
    (Array.isArray(filhos) ? filhos : filhos !== undefined ? [filhos] : []).forEach(function (f) {
      if (f === null || f === undefined || f === false) return;
      e.appendChild(typeof f === "string" || typeof f === "number" ? document.createTextNode(String(f)) : f);
    });
    return e;
  }
  const $ = function (s) { return document.querySelector(s); };

  function mensagemErro(corpo) {
    if (!corpo) return "Não foi possível concluir. Tente de novo.";
    if (typeof corpo === "string") return corpo;
    if (corpo.detail) return Array.isArray(corpo.detail) ? corpo.detail.join(" ") : String(corpo.detail);
    return Object.entries(corpo).map(function ([campo, v]) {
      const t = Array.isArray(v) ? v.map(function (x) { return typeof x === "object" ? mensagemErro(x) : x; }).join(" ") : mensagemErro(v);
      return ["detail", "non_field_errors", "itens", "endereco"].includes(campo) ? t : t;
    }).join(" · ");
  }

  async function post(caminho, corpo) {
    const r = await fetch(API + caminho, {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(corpo),
    });
    let dados = null;
    try { dados = await r.json(); } catch (e) { dados = null; }
    if (r.status === 429) throw new Error("Muitas tentativas. Aguarde um minuto e tente de novo.");
    if (!r.ok) throw new Error(mensagemErro(dados));
    return dados;
  }

  function abrirFolha(titulo, corpo, rodape) {
    const jaAberta = !!$("#folha");
    fecharFolha(true); // troca de folha (carrinho → checkout) sem mexer no histórico
    const painel = el("div", { class: "painel", role: "dialog", "aria-modal": "true", "aria-label": titulo }, [
      el("div", { class: "cab" }, [el("h3", { text: titulo }), el("button", { class: "fechar", "aria-label": "Fechar", onclick: fecharFolha, text: "×" })]),
      corpo, rodape ? el("div", { class: "rodape" }, rodape) : null,
    ]);
    const folha = el("div", { class: "folha", id: "folha", onclick: function (ev) { if (ev.target.id === "folha") fecharFolha(); } }, painel);
    document.body.appendChild(folha);
    document.body.style.overflow = "hidden";
    if (!jaAberta) history.pushState({ folha: true }, ""); // "voltar" do celular fecha a folha
    return painel;
  }
  function fecharFolha(semHistorico) {
    const f = $("#folha");
    if (f) { f.remove(); document.body.style.overflow = ""; if (semHistorico !== true && history.state && history.state.folha) history.back(); }
  }
  window.addEventListener("popstate", function () { fecharFolha(true); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") fecharFolha(); });

  // ---------------------------------------------------------------- cabeçalho
  function renderTopo() {
    document.documentElement.style.setProperty("--cor", LOJA.cor_primaria || "#e4572e");
    const logo = LOJA.logo ? el("img", { class: "logo", src: LOJA.logo, alt: "" })
      : el("div", { class: "logo logo-letra", text: (LOJA.nome || "?").charAt(0) });
    const info = [];
    if (LOJA.tempo_preparo_min) info.push("⏱ " + LOJA.tempo_preparo_min + "–" + (LOJA.tempo_preparo_min + 15) + " min");
    if (LOJA.pedido_minimo_centavos) info.push("Pedido mínimo " + C.reais(LOJA.pedido_minimo_centavos));
    info.push(LOJA.entrega ? "Entrega e retirada" : "Somente retirada");
    $("#topo").replaceChildren(el("div", { class: "topo-linha" }, [logo, el("div", {}, [
      el("h1", { text: LOJA.nome }),
      el("div", { class: "info" }, [el("span", { class: "selo" + (LOJA.aberta ? "" : " fechada"), text: LOJA.aberta ? "Aberto agora" : "Fechado" }),
        " " + info.join(" · ")]),
      LOJA.endereco ? el("div", { class: "info", text: "📍 " + LOJA.endereco }) : null,
      LOJA.fidelidade ? el("div", { class: "info fid-topo", text: "⭐ Cartão fidelidade: a cada " + LOJA.fidelidade.selos +
        " pedidos você ganha " + (LOJA.fidelidade.premio || "um prêmio") + "." }) : null,
    ])]));
    let modoApp = false;
    try { modoApp = localStorage.getItem("apfood_modo_app") === "1"; } catch (e) { modoApp = false; }
    if (modoApp && !MESA && !TOTEM) $("#topo").prepend(el("a", { class: "voltar-app", href: window.Capacitor || /ApFoodCliente/.test(navigator.userAgent) ? "/app/" : "/", text: "← Restaurantes" }));
    if (LOJA.reservas && !MESA && !TOTEM) {
      $("#topo").appendChild(el("a", { class: "aviso", style: "display:block;text-decoration:none", href: "/" + LOJA.slug + "/reservar/", text: "📅 Reservar mesa" }));
    }
    if (!LOJA.aberta && !MESA && !TOTEM) {
      let quando = "";
      if (LOJA.proxima_abertura) {
        const d = new Date(LOJA.proxima_abertura);
        quando = " Abrimos " + d.toLocaleDateString("pt-BR", { weekday: "long" }) + " às " +
          d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) + ".";
      }
      $("#topo").appendChild(el("div", { class: "aviso", text: LOJA.agendamento
        ? "Estamos fechados agora, mas você já pode agendar seu pedido." + quando
        : "No momento não estamos recebendo pedidos." + quando + " Você pode olhar o cardápio à vontade." }));
    }
  }

  // ---------------------------------------------------------------- cardápio
  function precoExibicao(p) {
    const varia = (p.variacoes || []).length;
    const base = varia ? Math.min.apply(null, p.variacoes.map(function (v) { return v.preco_centavos; })) : p.preco_centavos;
    const desconto = C.descontoPromocao(p.promocao, base);
    const prefixo = varia ? "a partir de " : "";
    if (!desconto) return prefixo + C.reais(base);
    return el("span", { class: "preco-promo" }, [
      el("s", { text: C.reais(base) }), " ", el("b", { text: prefixo + C.reais(base - desconto) }),
      el("span", { class: "selo-promo", text: "🔥 " + p.promocao.nome + (p.promocao.ate ? " até " + p.promocao.ate : "") }),
    ]);
  }

  function faixaPromocoes() {
    const lista = DADOS.promocoes || [];
    if (!lista.length) return null;
    return el("div", { class: "faixa-promo" }, [el("strong", { text: "🔥 Promoções de hoje" })].concat(lista.map(function (pr) {
      return el("div", { text: pr.nome + " — " + pr.resumo + (pr.descricao ? " · " + pr.descricao : "") });
    })));
  }

  function renderCardapio(filtro) {
    const termo = (filtro || "").trim().toLowerCase();
    const main = $("#lista");
    main.replaceChildren();
    const faixa = !termo && faixaPromocoes();
    if (faixa) main.appendChild(faixa);
    const chips = [];
    let algum = false;
    DADOS.categorias.forEach(function (c) {
      const produtos = c.produtos.filter(function (p) {
        return !termo || p.nome.toLowerCase().includes(termo) || (p.descricao || "").toLowerCase().includes(termo);
      });
      if (!produtos.length) return;
      algum = true;
      const id = "cat-" + c.id;
      chips.push(el("button", { class: "chip", "data-alvo": id, text: c.nome, onclick: function () {
        document.getElementById(id).scrollIntoView({ behavior: "smooth" });
      } }));
      main.appendChild(el("section", { class: "secao" }, [
        el("h2", { id: id, text: c.nome }), c.descricao ? el("p", { class: "desc", text: c.descricao }) : null,
      ].concat(produtos.map(function (p) {
        return el("button", { class: "produto", disabled: p.esgotado, onclick: function () { abrirProduto(p); } }, [
          el("div", { class: "txt" }, [el("strong", { text: p.nome }), p.descricao ? el("div", { class: "d", text: p.descricao }) : null,
            p.esgotado ? el("span", { class: "etiqueta", text: "Esgotado" }) : el("span", { class: "preco" }, [precoExibicao(p)])]),
          p.imagem ? el("img", { src: p.imagem, alt: "", loading: "lazy" }) : null,
        ]);
      }))));
    });
    if (!algum) main.appendChild(el("p", { class: "vazio", text: termo ? "Nada encontrado para “" + filtro + "”." : "Cardápio vazio no momento." }));
    $("#trilho").replaceChildren.apply($("#trilho"), chips);
    observarCategorias();
  }

  let observador = null;
  function observarCategorias() {
    if (!("IntersectionObserver" in window)) return;
    if (observador) observador.disconnect();
    observador = new IntersectionObserver(function (entradas) {
      entradas.forEach(function (en) {
        if (!en.isIntersecting) return;
        document.querySelectorAll(".chip").forEach(function (ch) {
          const ativa = ch.dataset.alvo === en.target.id;
          ch.classList.toggle("ativa", ativa);
          if (ativa) ch.scrollIntoView({ block: "nearest", inline: "center" });
        });
      });
    }, { rootMargin: "-120px 0px -70% 0px" });
    document.querySelectorAll(".secao h2").forEach(function (h) { observador.observe(h); });
  }

  // ------------------------------------------------------- montagem do item
  function abrirProduto(p) {
    const cat = idx.categoriaDe[p.id] || {};
    const item = { produto_id: p.id, quantidade: 1, variacao_id: (p.variacoes || [])[0] ? p.variacoes[0].id : null,
                   sabores: [], adicionais: [], observacao: "" };
    const qtdAd = {}; // adicional_id → quantidade
    const corpo = el("div", { class: "corpo" });
    const btn = el("button", { class: "btn" });
    const erros = el("p", { class: "erros", role: "alert" });

    function nomeVar() {
      const v = (p.variacoes || []).find(function (x) { return x.id === item.variacao_id; });
      return v ? v.nome : null;
    }
    function sincronizar() {
      item.adicionais = Object.entries(qtdAd).filter(function ([, q]) { return q > 0; })
        .map(function ([id, q]) { return { adicional_id: id, quantidade: q }; });
      const preco = C.precificar(idx, item);
      btn.replaceChildren(el("span", { text: "Adicionar" }), el("span", { text: C.reais(preco.total) }));
    }

    function montar() {
      corpo.replaceChildren();
      if (p.imagem) corpo.appendChild(el("img", { class: "foto-grande", src: p.imagem, alt: "" }));
      if (p.descricao) corpo.appendChild(el("p", { class: "d", text: p.descricao }));
      // tamanho
      if ((p.variacoes || []).length) {
        corpo.appendChild(el("div", { class: "grupo" }, [
          el("div", { class: "grupo-cab" }, [el("b", { text: "Tamanho" }), el("span", { class: "obrig", text: "OBRIGATÓRIO" })]),
        ].concat(p.variacoes.map(function (v) {
          return el("div", { class: "opcao" }, el("label", {}, [
            el("input", { type: "radio", name: "tam", checked: item.variacao_id === v.id, onchange: function () {
              item.variacao_id = v.id;
              // sabores precisam ter o mesmo tamanho
              item.sabores = item.sabores.filter(function (s) {
                return s === p.id || C.saboresCompativeis(idx, p, v.nome).some(function (x) { return x.id === s; });
              });
              montar();
            } }), el("span", { text: v.nome }), el("span", { class: "p", text: C.reais(v.preco_centavos) })]));
        }))));
      }
      // sabores (meio a meio)
      const maxS = Math.max(1, cat.max_sabores || 1);
      const compat = C.saboresCompativeis(idx, p, nomeVar());
      if (maxS > 1 && compat.length) {
        const extras = item.sabores.filter(function (s) { return s !== p.id; });
        corpo.appendChild(el("div", { class: "grupo" }, [
          el("div", { class: "grupo-cab" }, [el("b", { text: "Quer dividir? Até " + maxS + " sabores" }),
            el("small", { text: cat.regra_preco_sabores === "MEDIA" ? "preço pela média" : "vale o preço do mais caro" })]),
        ].concat(compat.map(function (sp) {
          const marcado = extras.includes(sp.id);
          return el("div", { class: "opcao" }, el("label", {}, [
            el("input", { type: "checkbox", checked: marcado, disabled: !marcado && extras.length >= maxS - 1, onchange: function (ev) {
              let novos = extras.slice();
              if (ev.target.checked) novos.push(sp.id); else novos = novos.filter(function (x) { return x !== sp.id; });
              item.sabores = novos.length ? [p.id].concat(novos) : [];
              montar();
            } }), el("span", { text: sp.nome }), el("span", { class: "p", text: C.reais(C.precificar(idx, { produto_id: sp.id, variacao_id: (sp.variacoes || []).find(function (v) { return v.nome === nomeVar(); }) ? sp.variacoes.find(function (v) { return v.nome === nomeVar(); }).id : null }).total) })]));
        }))));
      }
      // adicionais
      (p.grupos || []).forEach(function (g) {
        const unico = g.max === 1;
        const soma = function () { return g.opcoes.reduce(function (s, o) { return s + (qtdAd[o.id] || 0); }, 0); };
        corpo.appendChild(el("div", { class: "grupo" }, [
          el("div", { class: "grupo-cab" }, [
            el("div", {}, [el("b", { text: g.nome }), el("br"), el("small", { text: g.min ? (g.min === g.max ? "Escolha " + g.min : "Escolha de " + g.min + " a " + g.max) : "Até " + g.max })]),
            g.min ? el("span", { class: "obrig", text: "OBRIGATÓRIO" }) : null]),
        ].concat(g.opcoes.map(function (o) {
          const preco = o.preco_centavos ? el("span", { class: "p", text: "+ " + C.reais(o.preco_centavos) }) : null;
          if (unico) {
            return el("div", { class: "opcao" }, el("label", {}, [
              el("input", { type: g.min === 1 ? "radio" : "checkbox", name: "g-" + g.id, checked: (qtdAd[o.id] || 0) > 0,
                onchange: function (ev) {
                  g.opcoes.forEach(function (x) { qtdAd[x.id] = 0; });
                  qtdAd[o.id] = ev.target.checked ? 1 : 0;
                  montar();
                } }), el("span", { text: o.nome }), preco]));
          }
          const q = qtdAd[o.id] || 0;
          const maxO = o.max_por_item || 1;
          return el("div", { class: "opcao" }, [el("label", {}, [el("span", { text: o.nome }), preco]),
            el("div", { class: "passo" }, [
              el("button", { type: "button", "aria-label": "menos " + o.nome, disabled: q === 0, text: "−", onclick: function () { qtdAd[o.id] = q - 1; montar(); } }),
              el("span", { text: q }),
              el("button", { type: "button", "aria-label": "mais " + o.nome, disabled: q >= maxO || soma() >= g.max, text: "+", onclick: function () { qtdAd[o.id] = q + 1; montar(); } }),
            ])]);
        }))));
      });
      // observação e quantidade
      const obs = el("textarea", { placeholder: "Alguma observação? Ex.: sem cebola, ponto da carne…", maxlength: "255" });
      obs.value = item.observacao;
      obs.addEventListener("input", function () { item.observacao = obs.value; });
      corpo.appendChild(el("label", { class: "campo" }, [el("span", { text: "Observação" }), obs]));
      sincronizar();
    }

    const passoQtd = el("div", { class: "passo" });
    function renderQtd() {
      passoQtd.replaceChildren(
        el("button", { type: "button", "aria-label": "diminuir", disabled: item.quantidade <= 1, text: "−", onclick: function () { item.quantidade--; renderQtd(); sincronizar(); } }),
        el("span", { text: item.quantidade }),
        el("button", { type: "button", "aria-label": "aumentar", disabled: item.quantidade >= 50, text: "+", onclick: function () { item.quantidade++; renderQtd(); sincronizar(); } }));
    }
    renderQtd();
    btn.addEventListener("click", function () {
      sincronizar();
      const e = C.validar(idx, item);
      if (e.length) { erros.textContent = e.join(" · "); return; }
      carrinho.adicionar(JSON.parse(JSON.stringify(item)));
      fecharFolha();
      renderBarra();
    });
    montar();
    abrirFolha(p.nome, corpo, [el("div", { class: "rodape-linha" }, [passoQtd, btn]), erros]);
  }

  // ---------------------------------------------------------------- carrinho
  function renderBarra() {
    const n = carrinho.contagem();
    const barra = $("#barra");
    barra.classList.toggle("oculto", n === 0);
    if (!n) return;
    const t = C.totais(idx, carrinho.itens, 0, 0);
    barra.replaceChildren(el("button", { class: "btn", onclick: abrirCarrinho }, [
      el("span", { class: "qtd", text: n }), el("span", { text: "Ver carrinho" }), el("span", { text: C.reais(t.subtotal) })]));
  }

  function abrirCarrinho() {
    const corpo = el("div", { class: "corpo" });
    function render() {
      corpo.replaceChildren();
      if (!carrinho.itens.length) { fecharFolha(); renderBarra(); return; }
      carrinho.itens.forEach(function (it, i) {
        const d = C.descrever(idx, it), pr = C.precificar(idx, it);
        corpo.appendChild(el("div", { class: "item-car" }, [
          el("div", { class: "txt" }, [el("b", { text: d.titulo }), d.detalhe ? el("small", { text: d.detalhe }) : null,
            it.observacao ? el("small", { text: "Obs.: " + it.observacao }) : null, el("div", { text: C.reais(pr.total) })]),
          el("div", { class: "passo" }, [
            el("button", { type: "button", "aria-label": "remover um", text: it.quantidade > 1 ? "−" : "🗑", onclick: function () { carrinho.quantidade(i, -1); render(); renderBarra(); } }),
            el("span", { text: it.quantidade }),
            el("button", { type: "button", "aria-label": "adicionar um", text: "+", onclick: function () { carrinho.quantidade(i, 1); render(); renderBarra(); } })]),
        ]));
      });
      const t = C.totais(idx, carrinho.itens, 0, 0);
      corpo.appendChild(el("div", { class: "resumo" }, [el("div", { class: "total" }, [el("span", { text: "Subtotal" }), el("span", { text: C.reais(t.subtotal) })])]));
      if (LOJA.pedido_minimo_centavos && t.subtotal < LOJA.pedido_minimo_centavos) {
        corpo.appendChild(el("p", { class: "erros", text: "Faltam " + C.reais(LOJA.pedido_minimo_centavos - t.subtotal) + " para o pedido mínimo." }));
      }
      corpo.appendChild(el("button", { class: "btn secundario", style: "margin-top:10px", text: "+ Adicionar mais itens", onclick: function () { fecharFolha(); } }));
    }
    render();
    const continuar = el("button", { class: "btn", onclick: abrirCheckout }, [el("span", { text: "Continuar" }), el("span", { text: "→" })]);
    if (!LOJA.aberta && !MESA && !TOTEM && !LOJA.agendamento) { continuar.disabled = true; continuar.replaceChildren(el("span", { text: "Loja fechada no momento" })); }
    else if (!LOJA.aberta && !MESA && !TOTEM) continuar.replaceChildren(el("span", { text: "Agendar pedido" }), el("span", { text: "→" }));
    abrirFolha("Seu pedido", corpo, continuar);
  }

  // ---------------------------------------------------------------- checkout
  const PERFIL = "apfood_cliente";
  function perfil() { try { return JSON.parse(localStorage.getItem(PERFIL) || "{}"); } catch (e) { return {}; } }

  // ------------------------------------------------------------ mesa (QR Code)
  function faixaMesa() {
    return el("div", { class: "faixa-mesa" }, [
      el("div", {}, [el("strong", { text: "🍽️ " + MESA.nome }), el("div", { text: "Seu pedido vai direto para a cozinha e entra na conta da mesa." })]),
      el("button", { type: "button", class: "btn secundario", text: "Ver minha conta", onclick: verContaMesa }),
    ]);
  }

  async function verContaMesa() {
    const corpo = el("div", { class: "corpo" }, [el("p", { text: "Carregando…" })]);
    abrirFolha("Conta — " + MESA.nome, corpo, el("button", { class: "btn", text: "Fechar", onclick: function () { fecharFolha(); } }));
    try {
      const r = await fetch(API + "mesa/" + encodeURIComponent(MESA.token) + "/", { headers: { Accept: "application/json" } });
      const d = await r.json();
      corpo.replaceChildren();
      if (!d.aberta || !d.itens.length) { corpo.appendChild(el("p", { text: "Nada pedido ainda nesta mesa." })); return; }
      d.itens.forEach(function (i) {
        corpo.appendChild(el("div", { class: "item-car" }, [el("div", { class: "txt" }, [el("b", { text: i.quantidade + "× " + i.nome })]),
          el("div", { text: C.reais(i.total_centavos) })]));
      });
      const linhas = [["Consumo", d.subtotal_centavos]];
      if (d.taxa_servico_centavos) linhas.push(["Serviço", d.taxa_servico_centavos]);
      if (d.pago_centavos) linhas.push(["Já pago", -d.pago_centavos]);
      corpo.appendChild(el("div", { class: "resumo" }, linhas.map(function ([a, v]) {
        return el("div", {}, [el("span", { text: a }), el("span", { text: (v < 0 ? "−" : "") + C.reais(Math.abs(v)) })]);
      }).concat([el("div", { class: "total" }, [el("span", { text: "Falta pagar" }), el("span", { text: C.reais(Math.max(0, d.total_centavos - d.pago_centavos)) })])])));
      corpo.appendChild(el("p", { class: "ok", text: "Para pagar, chame o garçom ou vá ao caixa." }));
    } catch (e) {
      corpo.replaceChildren(el("p", { class: "erros", text: "Não foi possível carregar a conta." }));
    }
  }

  function abrirCheckoutMesa() {
    const corpo = el("div", { class: "corpo" });
    const nome = el("input", { name: "nome", maxlength: "120", placeholder: "Opcional — para o garçom saber de quem é" });
    nome.value = perfil().nome || "";
    const obs = el("textarea", { placeholder: "Ex.: sem cebola, trazer junto (opcional)", maxlength: "500" });
    const erros = el("p", { class: "erros", role: "alert" });
    const enviar = el("button", { class: "btn" });
    const t = C.totais(idx, carrinho.itens, 0, 0);
    corpo.appendChild(el("p", { class: "ok", text: "Pedido para a " + MESA.nome + ". Você paga no fim, com o garçom ou no caixa." }));
    corpo.appendChild(el("label", { class: "campo" }, [el("span", { text: "Seu nome" }), nome]));
    corpo.appendChild(el("label", { class: "campo" }, [el("span", { text: "Observação" }), obs]));
    corpo.appendChild(el("div", { class: "resumo" }, [el("div", { class: "total" }, [el("span", { text: "Total deste pedido" }), el("span", { text: C.reais(t.total) })])]));
    let enviando = false;
    function rotulo() { enviar.replaceChildren(el("span", { text: enviando ? "Enviando…" : "Enviar para a cozinha" }), el("span", { text: C.reais(t.total) })); enviar.disabled = enviando; }
    enviar.addEventListener("click", async function () {
      erros.textContent = "";
      enviando = true; rotulo();
      try {
        const r = await post("mesa/" + encodeURIComponent(MESA.token) + "/pedidos/", {
          nome_cliente: nome.value.trim(), observacao: obs.value.trim(),
          itens: carrinho.itens.map(function (i) {
            return { produto_id: i.produto_id, quantidade: i.quantidade, variacao_id: i.variacao_id || null,
              sabores: i.sabores || [], adicionais: i.adicionais || [], observacao: i.observacao || "" };
          }),
        });
        carrinho.limpar();
        renderBarra();
        abrirFolha("Pedido enviado!", el("div", { class: "corpo" }, [
          el("p", { class: "ok", text: "Pedido #" + (r.numero || "") + " enviado para a cozinha. Quer mais alguma coisa? É só pedir de novo por aqui." }),
          el("a", { class: "btn secundario", href: r.acompanhar, text: "Acompanhar o preparo" }),
        ]), el("button", { class: "btn", text: "Voltar ao cardápio", onclick: function () { fecharFolha(); } }));
      } catch (e) {
        enviando = false; rotulo();
        erros.textContent = e.message;
      }
    });
    rotulo();
    abrirFolha("Enviar pedido", corpo, [enviar, erros]);
  }

  function fusoLoja() { return "-03:00"; }  // horários da loja: America/Sao_Paulo (sem horário de verão)

  function abrirCheckout() {
    if (MESA) return abrirCheckoutMesa();
    if (TOTEM) return abrirCheckoutTotem();
    const salvo = perfil();
    const f = {};
    function campo(nome, rotulo, attrs) {
      const inp = el("input", Object.assign({ name: nome, autocomplete: "on" }, attrs || {}));
      inp.value = salvo[nome] || "";
      f[nome] = inp;
      return el("label", { class: "campo" }, [el("span", { text: rotulo }), inp]);
    }
    const corpo = el("div", { class: "corpo" });
    const resumo = el("div", { class: "resumo" });
    const msgTaxa = el("p", { class: "ok" });
    const msgCupom = el("p", { class: "ok" });
    const erros = el("p", { class: "erros", role: "alert" });
    const enviar = el("button", { class: "btn" });

    const tel = campo("telefone", "WhatsApp / telefone *", { type: "tel", inputmode: "tel", placeholder: "(11) 98765-4321", autocomplete: "tel" });
    f.telefone.addEventListener("input", function () { f.telefone.value = C.mascaraTelefone(f.telefone.value); });
    corpo.appendChild(campo("nome", "Seu nome *", { autocomplete: "name", maxlength: "120" }));
    corpo.appendChild(tel);

    // retirada × entrega
    const escolhas = [["ENTREGA", "🛵 Entrega"], ["RETIRADA", "🏪 Retirar"]].filter(function ([v]) { return v === "RETIRADA" || LOJA.entrega; });
    corpo.appendChild(el("div", { class: "escolha" }, escolhas.map(function ([v, r]) {
      return el("label", {}, [el("input", { type: "radio", name: "tipo", value: v, checked: estado.tipo === v,
        onchange: function () { estado.tipo = v; endereco.classList.toggle("oculto", v !== "ENTREGA"); atualizar(); } }), r]);
    })));

    // bairros com entrega cadastrada: sugestões (o cliente pode escolher outro da lista ou digitar)
    const listaBairros = el("datalist", { id: "bairros-loja" }, (LOJA.bairros || []).map(function (b) { return el("option", { value: b }); }));
    const msgCep = el("small", { class: "dica-cep", text: "Digite o CEP para preencher o endereço." });
    const endereco = el("div", { class: estado.tipo === "ENTREGA" ? "" : "oculto" }, [
      el("div", { class: "linha-cep" }, [campo("cep", "CEP", { inputmode: "numeric", maxlength: "9", placeholder: "00000-000", autocomplete: "postal-code" }), msgCep]),
      el("div", { class: "linha2" }, [campo("logradouro", "Rua *", { autocomplete: "address-line1" }), campo("numero", "Número *", { inputmode: "numeric" })]),
      campo("bairro", "Bairro *", { list: "bairros-loja", placeholder: (LOJA.bairros || []).length ? "Escolha da lista ou digite" : "" }), listaBairros,
      campo("complemento", "Complemento", { placeholder: "Apto, bloco…" }), campo("referencia", "Ponto de referência", {}),
      msgTaxa,
    ]);
    corpo.appendChild(endereco);

    // CEP → endereço (ViaCEP): preenche ao completar os 8 números; o bairro continua editável
    const semAcento = function (t) { return (t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim(); };
    let ultimoCep = f.cep.value.replace(/\D/g, "");  // endereço salvo: só busca de novo se o CEP mudar
    async function buscarCep() {
      const cep = f.cep.value.replace(/\D/g, "");
      if (cep.length === 8) f.cep.value = cep.slice(0, 5) + "-" + cep.slice(5);
      if (cep.length !== 8 || cep === ultimoCep) return;
      ultimoCep = cep;
      msgCep.className = "dica-cep"; msgCep.textContent = "Buscando o endereço…";
      try {
        const r = await fetch("https://viacep.com.br/ws/" + cep + "/json/");
        const d = await r.json();
        if (d.erro) { msgCep.className = "dica-cep erro"; msgCep.textContent = "CEP não encontrado: preencha o endereço."; return; }
        if (d.logradouro) f.logradouro.value = d.logradouro;
        const cadastrado = (LOJA.bairros || []).find(function (b) { return semAcento(b) === semAcento(d.bairro); });
        f.bairro.value = cadastrado || d.bairro || f.bairro.value;
        f.cidade = { value: d.localidade || "" };
        msgCep.className = "dica-cep ok";
        msgCep.textContent = "✓ " + [d.localidade, d.uf].filter(Boolean).join(" - ") +
          ((LOJA.bairros || []).length && !cadastrado ? ". Confira o bairro: se quiser, escolha um da lista." : ". Se quiser, troque o bairro.");
        estado.taxa = null;
        calcularTaxa();
        atualizar();
        (f.logradouro.value ? f.numero : f.logradouro).focus();
      } catch (e) { msgCep.className = "dica-cep"; msgCep.textContent = "Não deu para buscar o CEP agora: preencha o endereço."; }
    }
    f.cep.addEventListener("input", buscarCep);
    f.cep.addEventListener("blur", buscarCep);
    let tTaxa = null;
    ["bairro", "numero", "logradouro"].forEach(function (n) {
      f[n].addEventListener("input", function () { estado.taxa = null; clearTimeout(tTaxa); tTaxa = setTimeout(calcularTaxa, 700); atualizar(); });
    });
    async function calcularTaxa() {
      if (estado.tipo !== "ENTREGA" || !f.bairro.value.trim()) return;
      msgTaxa.className = "ok";
      msgTaxa.textContent = "Calculando a taxa de entrega…";
      try {
        const r = await post("taxa-entrega/", { bairro: f.bairro.value.trim(), logradouro: f.logradouro.value.trim(),
          numero: f.numero.value.trim(), cep: f.cep.value, cidade: f.cidade ? f.cidade.value : "" });
        estado.taxa = r.taxa_centavos;
        estado.taxaErro = "";
        estado.coords = r.latitude ? { latitude: r.latitude, longitude: r.longitude } : null;
        msgTaxa.textContent = "Taxa de entrega: " + (r.taxa_centavos ? C.reais(r.taxa_centavos) : "grátis") +
          (r.tempo_estimado_min ? " · cerca de " + r.tempo_estimado_min + " min" : "");
      } catch (e) {
        estado.taxa = null;
        estado.taxaErro = e.message;
        msgTaxa.className = "erros";
        msgTaxa.textContent = e.message;
      }
      atualizar();
    }

    // quando: agora ou agendado (encomenda)
    if (LOJA.agendamento) {
      const dias = LOJA.agendamento.dias;
      if (!estado.dia || !dias.find(function (d) { return d.data === estado.dia; })) { estado.dia = dias[0].data; estado.hora = dias[0].horarios[0]; }
      const selDia = el("select", { "aria-label": "Dia" }, dias.map(function (d) { return el("option", { value: d.data, selected: d.data === estado.dia, text: d.rotulo }); }));
      const selHora = el("select", { "aria-label": "Horário" });
      const encherHoras = function () {
        const d = dias.find(function (x) { return x.data === estado.dia; }) || dias[0];
        if (d.horarios.indexOf(estado.hora) < 0) estado.hora = d.horarios[0];
        selHora.replaceChildren.apply(selHora, d.horarios.map(function (h) { return el("option", { value: h, selected: h === estado.hora, text: h }); }));
      };
      selDia.addEventListener("change", function () { estado.dia = selDia.value; encherHoras(); });
      selHora.addEventListener("change", function () { estado.hora = selHora.value; });
      encherHoras();
      const escolha = el("div", { class: "agendar-quando" + (estado.agendar ? "" : " oculto") }, [selDia, selHora]);
      const opcoesQuando = (LOJA.aberta ? [["agora", "O quanto antes"]] : []).concat([["agendar", "Agendar dia e horário"]]);
      corpo.appendChild(el("div", { class: "campo" }, [el("span", { text: "Quando?" }), el("div", { class: "formas" }, opcoesQuando.map(function ([v, r]) {
        return el("label", {}, [el("input", { type: "radio", name: "quando", value: v, checked: (v === "agendar") === estado.agendar,
          onchange: function () { estado.agendar = v === "agendar"; escolha.classList.toggle("oculto", !estado.agendar); } }), r]);
      })), escolha]));
    }

    // pagamento
    const formas = [["PIX", LOJA.pix_online ? "Pix agora (QR Code na próxima tela)" : "Pix na entrega/retirada"]]
      .concat(LOJA.pix_online ? [["CARTAO_ONLINE", "Cartão agora (crédito ou débito, pelo Mercado Pago)"]] : [])
      .concat([["DINHEIRO", "Dinheiro"], ["CARTAO_CREDITO", "Cartão de crédito na entrega"], ["CARTAO_DEBITO", "Cartão de débito na entrega"],
        ["VOUCHER", "Vale-refeição na entrega"]]);

    if (LOJA.pix_online) formas.splice(1, 0, ["CARTAO_ONLINE", "Cartão agora (crédito ou débito, pelo Mercado Pago)"]);
    const troco = campo("troco", "Troco para quanto? (deixe vazio se não precisar)", { inputmode: "decimal", placeholder: "R$ 50,00" });
    troco.classList.toggle("oculto", estado.pagamento !== "DINHEIRO");
    corpo.appendChild(el("div", { class: "campo" }, [el("span", { text: "Pagamento" }), el("div", { class: "formas" }, formas.map(function ([v, r]) {
      return el("label", {}, [el("input", { type: "radio", name: "pag", value: v, checked: estado.pagamento === v,
        onchange: function () { estado.pagamento = v; troco.classList.toggle("oculto", v !== "DINHEIRO"); } }), r]);
    }))]));
    corpo.appendChild(troco);

    // cupom
    const cupomInp = el("input", { placeholder: "Cupom de desconto", "aria-label": "cupom", maxlength: "30" });
    if (estado.cupom) cupomInp.value = estado.cupom.codigo;
    corpo.appendChild(el("div", { class: "campo" }, [el("div", { class: "cupom" }, [cupomInp,
      el("button", { type: "button", text: "Aplicar", onclick: async function () {
        const codigo = cupomInp.value.trim();
        if (!codigo) { estado.cupom = null; msgCupom.textContent = ""; atualizar(); return; }
        try {
          const t = C.totais(idx, carrinho.itens, estado.taxa || 0, 0);
          const r = await post("cupom/", { codigo: codigo, subtotal_centavos: t.subtotal, taxa_entrega_centavos: t.taxa,
            telefone: f.telefone.value });
          estado.cupom = { codigo: r.codigo, desconto: r.desconto_centavos };
          msgCupom.className = "ok";
          msgCupom.textContent = "Cupom " + r.codigo + ": −" + C.reais(r.desconto_centavos);
        } catch (e) {
          estado.cupom = null;
          msgCupom.className = "erros";
          msgCupom.textContent = e.message;
        }
        atualizar();
      } })]), msgCupom]));

    const obs = el("textarea", { placeholder: "Observação para a loja (opcional)", maxlength: "500" });
    corpo.appendChild(el("label", { class: "campo" }, [el("span", { text: "Observação" }), obs]));
    corpo.appendChild(campo("cpf", "CPF na nota (opcional)", { inputmode: "numeric", maxlength: "14" }));
    corpo.appendChild(resumo);

    function atualizar() {
      const taxa = estado.tipo === "ENTREGA" ? (estado.taxa || 0) : 0;
      const t = C.totais(idx, carrinho.itens, taxa, estado.cupom ? estado.cupom.desconto : 0);
      const linhas = [["Subtotal", C.reais(t.subtotal)]];
      if (estado.tipo === "ENTREGA") linhas.push(["Taxa de entrega", estado.taxa === null ? "—" : C.reais(taxa)]);
      if (t.desconto) linhas.push(["Desconto", "−" + C.reais(t.desconto)]);
      resumo.replaceChildren.apply(resumo, linhas.map(function ([a, b]) { return el("div", {}, [el("span", { text: a }), el("span", { text: b })]); })
        .concat([el("div", { class: "total" }, [el("span", { text: "Total" }), el("span", { text: C.reais(t.total) })])]));
      enviar.replaceChildren(el("span", { text: estado.enviando ? "Enviando…" : "Fazer pedido" }), el("span", { text: C.reais(t.total) }));
      enviar.disabled = estado.enviando;
    }

    enviar.addEventListener("click", async function () {
      erros.textContent = "";
      const problemas = [];
      if (!f.nome.value.trim()) problemas.push("Informe seu nome");
      if (!C.telefoneValido(f.telefone.value)) problemas.push("Informe um telefone com DDD");
      if (estado.tipo === "ENTREGA") {
        if (!f.logradouro.value.trim() || !f.numero.value.trim() || !f.bairro.value.trim()) problemas.push("Preencha rua, número e bairro");
        else if (estado.taxaErro) problemas.push(estado.taxaErro);
      }
      const trocoC = C.paraCentavos(f.troco.value);
      if (estado.pagamento === "DINHEIRO" && f.troco.value && isNaN(trocoC)) problemas.push("Valor de troco inválido");
      if (problemas.length) { erros.textContent = problemas.join(" · "); return; }
      try { localStorage.setItem(PERFIL, JSON.stringify(["nome", "telefone", "logradouro", "numero", "bairro", "cep", "complemento", "referencia"]
        .reduce(function (o, k) { o[k] = f[k].value; return o; }, {}))); } catch (e) { /* ok */ }
      estado.enviando = true;
      atualizar();
      const corpoPedido = {
        tipo_atendimento: estado.tipo, nome_cliente: f.nome.value.trim(), telefone_cliente: f.telefone.value,
        forma_pagamento_prevista: estado.pagamento === "CARTAO_ONLINE" ? "CARTAO_CREDITO" : estado.pagamento,
        pagar_pix_agora: estado.pagamento === "PIX" && LOJA.pix_online,
        pagar_cartao_agora: estado.pagamento === "CARTAO_ONLINE",
        agendado_para: LOJA.agendamento && estado.agendar ? estado.dia + "T" + estado.hora + ":00" + fusoLoja() : null,
        cupom_codigo: estado.cupom ? estado.cupom.codigo : "", observacao: obs.value.trim(), cpf_nota: f.cpf.value,
        troco_para_centavos: estado.pagamento === "DINHEIRO" && trocoC > 0 ? trocoC : null,
        itens: carrinho.itens.map(function (i) {
          return { produto_id: i.produto_id, quantidade: i.quantidade, variacao_id: i.variacao_id || null,
            sabores: i.sabores || [], adicionais: i.adicionais || [], observacao: i.observacao || "" };
        }),
      };
      if (estado.tipo === "ENTREGA") {
        corpoPedido.endereco = Object.assign({ logradouro: f.logradouro.value.trim(), numero: f.numero.value.trim(),
          bairro: f.bairro.value.trim(), complemento: f.complemento.value.trim(), referencia: f.referencia.value.trim(),
          cep: f.cep.value, cidade: f.cidade ? f.cidade.value : "" }, estado.coords || {});
      }
      try {
        const r = await post("pedidos/", corpoPedido);
        carrinho.limpar();
        try {
          const meus = JSON.parse(localStorage.getItem("apfood_pedidos") || "[]");
          meus.unshift({ token: r.token, numero: r.numero, loja: LOJA.nome, slug: LOJA.slug, em: new Date().toISOString() });
          localStorage.setItem("apfood_pedidos", JSON.stringify(meus.slice(0, 20)));
          if (r.pix) sessionStorage.setItem("apfood_pix_" + r.token, JSON.stringify(r.pix));
        } catch (e) { /* ok */ }
        window.location.href = r.cartao_url || "/pedido/" + encodeURIComponent(r.token) + "/";
      } catch (e) {
        estado.enviando = false;
        erros.textContent = e.message;
        atualizar();
      }
    });

    atualizar();
    abrirFolha("Finalizar pedido", corpo, [enviar, erros]);
    if (estado.tipo === "ENTREGA" && f.bairro.value) calcularTaxa();
  }

  // ------------------------------------------------------------- meus pedidos
  function renderMeusPedidos() {
    let meus = [];
    try { meus = JSON.parse(localStorage.getItem("apfood_pedidos") || "[]").filter(function (p) { return p.slug === LOJA.slug; }); } catch (e) { meus = []; }
    const recente = meus.find(function (p) { return Date.now() - new Date(p.em).getTime() < 6 * 3600 * 1000; });
    if (recente) {
      $("#topo").appendChild(el("a", { class: "aviso", style: "display:block;text-decoration:none", href: "/pedido/" + recente.token + "/",
        text: "Acompanhar seu pedido #" + (recente.numero || "") + " →" }));
    }
  }

  // ------------------------------------------------------------- totem (balcão)
  function iniciarTotem() {
    document.body.classList.add("modo-totem");
    const telaInicial = function () {
      const capa = el("div", { class: "totem-capa", role: "button", tabindex: "0", onclick: function () { capa.remove(); } }, [
        LOJA.logo ? el("img", { src: LOJA.logo, alt: "" }) : null,
        el("h1", { text: LOJA.nome }), el("p", { text: "Toque para fazer seu pedido" }), el("span", { class: "totem-dedo", text: "👆" })]);
      document.body.appendChild(capa);
    };
    telaInicial();
    // sem mexer por 2 minutos: limpa e volta para a tela inicial
    let ocioso = null;
    const reiniciarOcio = function () {
      clearTimeout(ocioso);
      ocioso = setTimeout(function () { carrinho.limpar(); location.reload(); }, 120000);
    };
    ["pointerdown", "keydown", "scroll"].forEach(function (ev) { document.addEventListener(ev, reiniciarOcio, { passive: true }); });
    reiniciarOcio();
  }

  function abrirCheckoutTotem() {
    const corpo = el("div", { class: "corpo totem-checkout" });
    const erros = el("p", { class: "erros", role: "alert" });
    const enviar = el("button", { class: "btn" });
    const t = C.totais(idx, carrinho.itens, 0, 0);
    let tipo = "", pagamento = LOJA.pix_online ? "" : "CAIXA";
    const nome = el("input", { maxlength: "60", placeholder: "Para chamarmos você (opcional)", autocomplete: "off" });
    function botoes(rotulo, ops, atual, aoEscolher) {
      return el("div", { class: "campo" }, [el("span", { text: rotulo }), el("div", { class: "totem-opcoes" }, ops.map(function ([v, r, ico]) {
        return el("button", { type: "button", class: "totem-opcao" + (atual() === v ? " marcada" : ""), onclick: function () { aoEscolher(v); desenhar(); } },
          [el("span", { class: "ico", text: ico }), el("span", { text: r })]);
      }))]);
    }
    function desenhar() {
      corpo.replaceChildren(
        botoes("Onde você vai comer?", [["CONSUMO_LOCAL", "Comer aqui", "🍽️"], ["RETIRADA", "Para levar", "🛍️"]], function () { return tipo; }, function (v) { tipo = v; }),
        LOJA.pix_online ? botoes("Como vai pagar?", [["CAIXA", "No caixa", "💵"], ["PIX", "Pix agora", "📱"]], function () { return pagamento; }, function (v) { pagamento = v; }) : null,
        el("label", { class: "campo" }, [el("span", { text: "Seu nome" }), nome]),
        el("div", { class: "resumo" }, [el("div", { class: "total" }, [el("span", { text: "Total" }), el("span", { text: C.reais(t.total) })])]));
      enviar.disabled = !tipo || !pagamento;
      enviar.replaceChildren(el("span", { text: "Confirmar pedido" }), el("span", { text: C.reais(t.total) }));
    }
    desenhar();
    let enviando = false;
    enviar.addEventListener("click", async function () {
      if (enviando || !tipo || !pagamento) return;
      enviando = true; enviar.disabled = true; erros.textContent = "";
      try {
        const r = await post("totem/" + encodeURIComponent(TOTEM.token) + "/pedidos/", {
          tipo_atendimento: tipo, nome_cliente: nome.value.trim(), pagar_pix: pagamento === "PIX",
          itens: carrinho.itens.map(function (i) {
            return { produto_id: i.produto_id, quantidade: i.quantidade, variacao_id: i.variacao_id || null,
              sabores: i.sabores || [], adicionais: i.adicionais || [], observacao: i.observacao || "" };
          }),
        });
        carrinho.limpar();
        fecharFolha();
        renderBarra();
        telaSenha(r, pagamento);
      } catch (e) { enviando = false; enviar.disabled = false; erros.textContent = e.message; }
    });
    abrirFolha("Finalizar pedido", corpo, [enviar, erros]);
  }

  function telaSenha(r, pagamento) {
    let s = r.pix ? 90 : 25;
    const cont = el("small");
    const tela = el("div", { class: "totem-senha", role: "dialog", "aria-label": "Pedido confirmado" }, [
      el("div", { class: "ok", text: "✅ Pedido confirmado!" }),
      el("small", { text: "Sua senha" }),
      el("div", { class: "numero", text: r.senha }),
      r.pix ? el("div", { class: "totem-pix" }, [
        el("b", { text: "Pague " + C.reais(r.pix.valor_centavos) + " no Pix" }),
        r.pix.qr_code_base64 ? el("img", { src: "data:image/png;base64," + r.pix.qr_code_base64, alt: "QR Code Pix" }) : null,
        el("small", { text: "Aponte a câmera do celular para o QR Code. Seu pedido já está na cozinha." })])
        : el("p", { text: pagamento === "CAIXA" ? "Vá ao caixa e informe a senha para pagar." : "Aguarde ser chamado pela senha." }),
      el("button", { class: "btn", type: "button", text: "Fazer outro pedido", onclick: function () { location.reload(); } }),
      cont]);
    document.body.appendChild(tela);
    const passo = function () { cont.textContent = "Voltando ao início em " + s + " s"; if (s-- <= 0) location.reload(); else setTimeout(passo, 1000); };
    passo();
  }

  // ------------------------------------------------------------------- início
  renderTopo();
  if (MESA) $("#topo").appendChild(faixaMesa()); else if (TOTEM) iniciarTotem(); else renderMeusPedidos();
  renderCardapio("");
  const removidos = carrinho.sanear(idx);
  renderBarra();
  if (removidos) $("#topo").appendChild(el("div", { class: "aviso", text: removidos + " item(ns) do seu carrinho saíram do cardápio e foram removidos." }));
  let tBusca = null;
  $("#busca").addEventListener("input", function (e) { clearTimeout(tBusca); tBusca = setTimeout(function () { renderCardapio(e.target.value); }, 150); });
})();
