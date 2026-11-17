/* App do cliente: restaurantes da região (localização ou cidade) e "meus pedidos". */
(function () {
  "use strict";
  const C = window.ApCarrinho;
  const $ = (s) => document.querySelector(s);
  const LS_LOCAL = "apfood_app_local";
  try { localStorage.setItem("apfood_modo_app", "1"); } catch (e) { /* ok */ }
  // no APK do cliente não mostra o acesso das empresas (elas têm o app próprio)
  if (window.Capacitor || /ApFoodCliente/.test(navigator.userAgent)) { const le = document.getElementById("login-empresas"); if (le) le.remove(); }

  function el(tag, attrs, filhos) {
    const n = document.createElement(tag);
    Object.entries(attrs || {}).forEach(function ([k, v]) {
      if (v === null || v === undefined || v === false) return;
      if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    });
    [].concat(filhos || []).forEach(function (f) { if (f !== null && f !== undefined) n.append(f.nodeType ? f : String(f)); });
    return n;
  }

  let local = null;
  try { local = JSON.parse(localStorage.getItem(LS_LOCAL) || "null"); } catch (e) { local = null; }
  let aba = "lojas";
  let busca = "";
  let cidade = "";

  async function carregarLojas() {
    const lista = $("#lista");
    const p = new URLSearchParams();
    if (local) { p.set("lat", local.lat); p.set("lng", local.lng); }
    else if (cidade) p.set("cidade", cidade);
    if (busca) p.set("busca", busca);
    $("#onde").textContent = local ? "Até 25 km de você" : (cidade ? "Em " + cidade : "Toque em “Perto de mim” para ver os mais próximos");
    try {
      const r = await fetch("/api/publico/lojas/?" + p.toString(), { headers: { Accept: "application/json" } });
      const d = await r.json();
      lista.replaceChildren();
      if (!local && d.cidades && d.cidades.length > 1) {
        const sel = el("select", { "aria-label": "Cidade", onchange: function (ev) { cidade = ev.target.value; carregarLojas(); } },
          [el("option", { value: "", text: "Todas as cidades" })].concat(d.cidades.map(function (c) {
            return el("option", { value: c, text: c, selected: c === cidade });
          })));
        lista.appendChild(el("div", { class: "app-cidade" }, sel));
      }
      if (!d.lojas.length) {
        lista.appendChild(el("div", { class: "cartao", text: local ? "Nenhum restaurante perto de você ainda. Tente buscar pela cidade." : "Nenhum restaurante encontrado." }));
        if (local) lista.appendChild(el("button", { class: "btn secundario", text: "Ver todos", onclick: function () { local = null; try { localStorage.removeItem(LS_LOCAL); } catch (e) { /* ok */ } carregarLojas(); } }));
        return;
      }
      d.lojas.forEach(function (l) {
        const logo = l.logo ? el("img", { class: "app-logo", src: l.logo, alt: "" })
          : el("div", { class: "app-logo vazio", style: "background:" + (l.cor_primaria || "#e4572e"), text: l.nome.slice(0, 1) });
        const info = [l.bairro, l.distancia_km !== null ? String(l.distancia_km).replace(".", ",") + " km" : null,
          l.tempo_preparo_min ? "~" + l.tempo_preparo_min + " min" : null, l.entrega ? "Entrega" : "Retirada"].filter(Boolean).join(" · ");
        lista.appendChild(el("a", { class: "app-loja" + (l.aberta ? "" : " fechada"), href: "/" + l.slug + "/" }, [
          logo,
          el("div", { class: "app-loja-txt" }, [
            el("strong", { text: l.nome }),
            el("small", { text: info }),
            l.promocoes.length ? el("small", { class: "app-promo", text: "🔥 " + l.promocoes.join(" · ") }) : null,
          ]),
          el("span", { class: "selo" + (l.aberta ? "" : " fechada"), text: l.aberta ? "Aberto" : "Fechado" }),
        ]));
      });
    } catch (e) {
      lista.replaceChildren(el("div", { class: "cartao", text: "Sem conexão. Tente de novo em instantes." }));
    }
  }

  const NOMES = { AGUARDANDO_ACEITE: "Aguardando a loja", RECEBIDO: "Confirmado", EM_PREPARO: "Em preparo", PRONTO: "Pronto",
    SAIU_PARA_ENTREGA: "Saiu para entrega", CONCLUIDO: "Concluído", CANCELADO: "Cancelado", RECUSADO: "Recusado" };

  async function carregarPedidos() {
    const lista = $("#lista");
    let meus = [];
    try { meus = JSON.parse(localStorage.getItem("apfood_pedidos") || "[]"); } catch (e) { meus = []; }
    lista.replaceChildren();
    if (!meus.length) { lista.appendChild(el("div", { class: "cartao", text: "Você ainda não fez pedidos por este aparelho." })); return; }
    for (const m of meus) {
      const linha = el("a", { class: "app-loja", href: "/pedido/" + encodeURIComponent(m.token) + "/" }, [
        el("div", { class: "app-loja-txt" }, [el("strong", { text: m.loja + " · #" + (m.numero || "") }),
          el("small", { text: new Date(m.em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) })]),
        el("span", { class: "selo", text: "…" })]);
      lista.appendChild(linha);
      fetch("/api/publico/pedidos/" + encodeURIComponent(m.token) + "/", { headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (p) {
          if (!p) return;
          const s = linha.querySelector(".selo");
          s.textContent = NOMES[p.status] || p.etapa || p.status;
          if (["CANCELADO", "RECUSADO"].includes(p.status)) s.classList.add("fechada");
          linha.querySelector("small").textContent += " · " + C.reais(p.total_centavos);
        }).catch(function () { /* ok */ });
    }
  }

  function render() { (aba === "lojas" ? carregarLojas : carregarPedidos)(); }

  document.querySelectorAll(".aba").forEach(function (b) {
    b.addEventListener("click", function () {
      aba = b.dataset.aba;
      document.querySelectorAll(".aba").forEach(function (x) { x.classList.toggle("ativa", x === b); });
      $(".app-busca").hidden = aba !== "lojas";
      render();
    });
  });
  let espera = null;
  $("#busca").addEventListener("input", function (ev) {
    clearTimeout(espera);
    espera = setTimeout(function () { busca = ev.target.value.trim(); carregarLojas(); }, 300);
  });
  $("#local").addEventListener("click", function () {
    if (!("geolocation" in navigator)) { alert("Este aparelho não informa a localização."); return; }
    $("#local").textContent = "📍 Localizando…";
    navigator.geolocation.getCurrentPosition(function (pos) {
      local = { lat: pos.coords.latitude.toFixed(5), lng: pos.coords.longitude.toFixed(5) };
      try { localStorage.setItem(LS_LOCAL, JSON.stringify(local)); } catch (e) { /* ok */ }
      $("#local").textContent = "📍 Perto de mim";
      carregarLojas();
    }, function () {
      $("#local").textContent = "📍 Perto de mim";
      $("#onde").textContent = "Não foi possível pegar a localização — escolha a cidade.";
    }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
  });
  render();
})();
