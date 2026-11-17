/* ApFood Entregador: login com telefone + PIN, disponível/indisponível, chamadas
   (30 s para aceitar), retirada e entrega com códigos, ganhos e troca de PIN. */
(function () {
  "use strict";
  const API = "/api/entregador/";
  const CHAVE = "apfood_entregador_token";
  const app = document.getElementById("app");
  const CAP = window.Capacitor && window.Capacitor.Plugins ? window.Capacitor.Plugins : {};

  let token = ler(CHAVE);
  let estado = null;
  let aba = "entregas";
  let timer = null;
  let batimento = null;
  let posicao = null;
  let vigia = null;
  let ofertaVista = null;
  let tique = null;
  let audio = null;
  let somTimer = null;
  let wakeLock = null;
  let ocupado = false;
  const codigos = {};
  const cobrando = {};   // pedido → forma escolhida na tela de cobrança
  let pixTimer = null;
  let hist = null, histEm = 0;  // texto digitado nos campos de código (sobrevive aos redesenhos)

  function ler(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function gravar(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* ok */ } }

  function el(tag, attrs, filhos) {
    const e = document.createElement(tag);
    Object.entries(attrs || {}).forEach(function ([k, v]) {
      if (v === null || v === undefined || v === false) return;
      if (k === "class") e.className = v; else if (k === "text") e.textContent = v;
      else if (k === "style") e.setAttribute("style", v);
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (k === "value") e.value = v;
      else e.setAttribute(k, v === true ? "" : v);
    });
    (Array.isArray(filhos) ? filhos : filhos !== undefined ? [filhos] : []).forEach(function (f) {
      if (f) e.appendChild(typeof f === "string" || typeof f === "number" ? document.createTextNode(String(f)) : f);
    });
    return e;
  }
  const reais = function (c) { return (c / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); };
  const centavosDe = function (t) {
    const s = String(t || "").replace(/[^\d,.]/g, "");
    if (!s) return null;
    const n = s.includes(",") ? Number(s.replace(/\./g, "").replace(",", ".")) : Number(s);
    return isFinite(n) ? Math.round(n * 100) : null;
  };
  const emReais = function (c) { return (c / 100).toFixed(2).replace(".", ","); };
  const km = function (v) { return v === null || v === undefined ? "—" : String(v).replace(".", ",") + " km"; };

  async function req(metodo, caminho, corpo) {
    const op = { method: metodo, headers: { Accept: "application/json" } };
    if (token) op.headers.Authorization = "Entregador " + token;
    if (corpo !== undefined) { op.headers["Content-Type"] = "application/json"; op.body = JSON.stringify(corpo); }
    const r = await fetch(API + caminho, op);
    const d = await r.json().catch(function () { return {}; });
    if (r.status === 401) { sair(true); throw new Error(d.detail || "Entre de novo."); }
    if (!r.ok) {
      const msg = d.detail || Object.values(d).flat()[0] || "Não foi possível agora. Tente de novo.";
      throw new Error(msg);
    }
    return d;
  }

  // ------------------------------------------------------------------ login
  function telaEntrar(msg) {
    pararTudo();
    const tel = el("input", { type: "tel", inputmode: "tel", autocomplete: "tel", placeholder: "(81) 99999-0000", required: true, value: ler("apfood_entregador_tel") || "" });
    const pin = el("input", { type: "password", inputmode: "numeric", autocomplete: "current-password", class: "pin", maxlength: 6, pattern: "[0-9]*", placeholder: "••••", required: true });
    const erro = el("p", { class: "erro", text: msg || "" });
    const botao = el("button", { class: "btn bloco", type: "submit", text: "Entrar" });
    const form = el("form", { novalidate: true, onsubmit: async function (ev) {
      ev.preventDefault();
      erro.textContent = ""; botao.disabled = true;
      try {
        const r = await req("POST", "entrar/", { telefone: tel.value, pin: pin.value });
        token = r.token; gravar(CHAVE, token); gravar("apfood_entregador_tel", tel.value); sincronizarNativo();
        await carregar(); iniciar();
      } catch (e) { erro.textContent = e.message; botao.disabled = false; }
    } }, [
      el("div", { class: "marca" }, el("img", { src: "/static/marca/logo.png", alt: "ApFood" })),
      el("h1", { text: "ApFood Entregador" }),
      el("p", { text: "Entre com o celular cadastrado pela loja e o seu PIN." }),
      el("label", { class: "campo" }, [el("span", { text: "Celular com DDD" }), tel]),
      el("label", { class: "campo" }, [el("span", { text: "PIN (4 a 6 números)" }), pin]),
      erro, botao,
      el("p", { text: "Esqueceu o PIN? Peça para a loja definir um novo no cadastro de entregadores." }),
    ]);
    app.replaceChildren(el("div", { class: "entrar" }, form));
  }

  function sair(expirou) {
    pararTudo();
    token = null; gravar(CHAVE, null); estado = null; sincronizarNativo();
    telaEntrar(expirou ? "Sua sessão terminou. Entre de novo." : "");
  }

  // ------------------------------------------------------------------ ciclo
  async function carregar() {
    estado = await req("GET", "estado/");
    tratarOferta();
    vigiarPix();
    desenhar();
  }

  // Pix gerado na porta: pergunta a cada 4 s se o cliente já pagou (o gateway confirma e conclui)
  function vigiarPix() {
    const abertos = ((estado && estado.entregas) || []).filter(function (e) { return e.cobranca && e.cobranca.pix && e.cobrar_centavos; });
    clearInterval(pixTimer); pixTimer = null;
    if (!abertos.length) return;
    pixTimer = setInterval(async function () {
      for (const e of abertos) {
        try {
          const r = await req("GET", "entregas/" + e.id + "/pix/");
          if (r.pago) {
            clearInterval(pixTimer); pixTimer = null;
            if (navigator.vibrate) navigator.vibrate([200, 100, 200]);
            delete cobrando[e.id];
            await carregar();
            alert(r.concluido ? "✅ Pix recebido! Entrega concluída." : "✅ Pix recebido!");
            return;
          }
        } catch (err) { /* sem rede: tenta de novo */ }
      }
    }, 4000);
  }

  function agendar() {
    clearTimeout(timer);
    const ms = estado && estado.online ? 3000 : 15000;
    timer = setTimeout(async function () {
      if (ocupado) { agendar(); return; }
      try { await carregar(); } catch (e) { /* sem rede: tenta de novo */ }
      if (token) agendar();
    }, ms);
  }

  // ---------------------------------------------------------- integração nativa (APK)
  // o código nativo lê a sessão para responder Aceitar/Recusar direto da notificação
  function sincronizarNativo() {
    const P = CAP.Preferences;
    if (!P) return;
    if (token) {
      P.set({ key: "apfood_entregador_token", value: token }).catch(function () {});
      P.set({ key: "apfood_base", value: location.origin }).catch(function () {});
    } else {
      P.remove({ key: "apfood_entregador_token" }).catch(function () {});
    }
  }

  async function registrarPush() {
    const P = CAP.Preferences;
    if (!P || registrarPush.feito) return;
    try {
      const r = await P.get({ key: "apfood_push_token" });
      if (r && r.value) { await req("POST", "push/", { token: r.value }); registrarPush.feito = true; }
      else setTimeout(registrarPush, 15000);  // o Firebase entrega o token alguns segundos depois
    } catch (e) { /* sem Firebase neste APK */ }
  }

  function idNotificacao(chamada) {  // igual ao Ofertas.idDa() do Android: a mesma notificação, sem duplicar
    let h = 0;
    for (let i = 0; i < chamada.length; i++) h = (Math.imul(31, h) + chamada.charCodeAt(i)) | 0;
    return Math.abs(h % 1000000);
  }

  let acoesProntas = false;
  function prepararNotificacoes() {
    const LN = CAP.LocalNotifications;
    if (!LN || acoesProntas) return;
    acoesProntas = true;
    LN.registerActionTypes({ types: [{ id: "OFERTA", actions: [
      { id: "aceitar", title: "✅ Aceitar", foreground: true },
      { id: "recusar", title: "Recusar", destructive: true, foreground: false },
    ] }] }).catch(function () {});
    if (LN.createChannel) LN.createChannel({ id: "ofertas", name: "Chamadas de entrega", importance: 5, visibility: 1, vibration: true }).catch(function () {});
    LN.addListener("localNotificationActionPerformed", function (a) {
      const chamada = a.notification && a.notification.extra && a.notification.extra.chamada;
      if (!chamada || (a.actionId !== "aceitar" && a.actionId !== "recusar")) return;
      pararSom();
      req("POST", "ofertas/" + chamada + "/" + a.actionId + "/").catch(function (e) { alert(e.message); })
        .then(function () { aba = "entregas"; return carregar(); }).catch(function () {});
    });
  }

  function iniciar() {
    sincronizarNativo();
    prepararNotificacoes();
    registrarPush();
    agendar();
    if (estado && estado.online) ligarSinais();
  }

  function pararTudo() {
    clearTimeout(timer); clearInterval(batimento); clearInterval(tique); clearInterval(pixTimer); pararSom();
    if (vigia !== null && navigator.geolocation) navigator.geolocation.clearWatch(vigia);
    vigia = null;
    soltarTela();
  }

  // disponível: manda posição a cada 15 s e mantém a tela acesa
  function ligarSinais() {
    if (navigator.geolocation && vigia === null) {
      vigia = navigator.geolocation.watchPosition(function (p) {
        posicao = { latitude: p.coords.latitude.toFixed(6), longitude: p.coords.longitude.toFixed(6) };
      }, function () { /* sem GPS: segue sem posição */ }, { enableHighAccuracy: true, maximumAge: 15000, timeout: 20000 });
    }
    clearInterval(batimento);
    batimento = setInterval(function () { req("POST", "online/", Object.assign({ online: true }, posicao || {})).catch(function () {}); }, 15000);
    segurarTela();
  }

  async function alternarOnline() {
    prepararSom();
    pedirNotificacao();
    const novo = !(estado && estado.online);
    try {
      await req("POST", "online/", Object.assign({ online: novo }, posicao || {}));
      if (novo) ligarSinais(); else { clearInterval(batimento); soltarTela(); if (vigia !== null) { navigator.geolocation.clearWatch(vigia); vigia = null; } }
      await carregar();
      agendar();
    } catch (e) { alert(e.message); }
  }

  async function segurarTela() {
    try { if ("wakeLock" in navigator && !wakeLock) wakeLock = await navigator.wakeLock.request("screen"); } catch (e) { wakeLock = null; }
  }
  function soltarTela() { try { if (wakeLock) wakeLock.release(); } catch (e) { /* ok */ } wakeLock = null; }
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && estado && estado.online) { wakeLock = null; segurarTela(); carregar().catch(function () {}); }
  });

  // ------------------------------------------------------------------ alerta de chamada
  function prepararSom() {
    try { if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)(); if (audio.state === "suspended") audio.resume(); } catch (e) { audio = null; }
  }
  function bip() {
    if (!audio) return;
    try {
      [0, 0.22].forEach(function (t) {
        const o = audio.createOscillator(); const g = audio.createGain();
        o.type = "square"; o.frequency.value = 880; g.gain.value = 0.15;
        o.connect(g); g.connect(audio.destination);
        o.start(audio.currentTime + t); o.stop(audio.currentTime + t + 0.14);
      });
    } catch (e) { /* ok */ }
  }
  function tocarAlerta() {
    pararSom();
    bip();
    if (navigator.vibrate) navigator.vibrate([400, 200, 400, 200, 400]);
    somTimer = setInterval(function () { bip(); if (navigator.vibrate) navigator.vibrate([300, 150, 300]); }, 2500);
  }
  function pararSom() { clearInterval(somTimer); somTimer = null; if (navigator.vibrate) navigator.vibrate(0); }

  function pedirNotificacao() {
    const LN = CAP.LocalNotifications;
    if (LN && LN.requestPermissions) LN.requestPermissions().catch(function () {});
    else if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(function () {});
  }
  function notificar(o) {
    const titulo = "🛵 Nova entrega — " + o.loja;
    const corpo = "Para " + (o.bairro || "o cliente") + (o.ganho_centavos ? " · você recebe " + reais(o.ganho_centavos) : "") +
      ". Aceite em " + o.segundos + " s.";
    const LN = CAP.LocalNotifications;
    if (LN && LN.schedule) {
      prepararNotificacoes();
      LN.schedule({ notifications: [{ id: idNotificacao(o.chamada), title: titulo, body: corpo, channelId: "ofertas",
        actionTypeId: "OFERTA", extra: { chamada: o.chamada }, autoCancel: true }] }).catch(function () {});
    } else if ("Notification" in window && Notification.permission === "granted" && document.hidden) {
      try { new Notification(titulo, { body: corpo, icon: "/static/marca/icone-192.png", tag: "oferta" }); } catch (e) { /* ok */ }
    }
  }

  function tratarOferta() {
    const o = estado && estado.oferta;
    if (!o) {
      if (ofertaVista && CAP.LocalNotifications) CAP.LocalNotifications.cancel({ notifications: [{ id: idNotificacao(ofertaVista) }] }).catch(function () {});
      ofertaVista = null; pararSom(); clearInterval(tique); return;
    }
    if (ofertaVista !== o.chamada) {
      ofertaVista = o.chamada;
      o.recebida = Date.now();
      tocarAlerta();
      notificar(o);
    }
  }

  function telaOferta(o) {
    const fim = Date.now() + o.segundos * 1000;
    const num = el("b", { text: String(o.segundos) });
    const relogio = el("div", { class: "relogio" }, num);
    const atualizar = function () {
      const s = Math.max(0, Math.ceil((fim - Date.now()) / 1000));
      num.textContent = String(s);
      relogio.style.setProperty("--p", String(s / (o.total_segundos || 30)));
      if (s <= 0) { clearInterval(tique); pararSom(); }
    };
    clearInterval(tique);
    tique = setInterval(atualizar, 250);
    atualizar();
    const responder = async function (acao, botao) {
      botao.disabled = true; ocupado = true; pararSom();
      try { await req("POST", "ofertas/" + o.chamada + "/" + acao + "/"); }
      catch (e) { alert(e.message); }
      ocupado = false;
      await carregar().catch(function () {});
    };
    const recusar = el("button", { class: "btn claro", type: "button", text: "Recusar", onclick: function () { responder("recusar", recusar); } });
    const aceitar = el("button", { class: "btn ok", type: "button", text: "Aceitar", onclick: function () { responder("aceitar", aceitar); } });
    return el("div", { class: "oferta", role: "dialog", "aria-modal": "true", "aria-label": "Nova entrega" },
      el("div", { class: "caixa" }, [
        el("h2", { text: "🛵 Nova entrega!" }),
        relogio,
        el("div", { class: "dados" }, [
          el("div", { class: "largo" }, [el("small", { text: "Retirar em" }), el("b", { text: o.loja }), o.loja_endereco ? el("div", { class: "muted", text: o.loja_endereco }) : null]),
          el("div", {}, [el("small", { text: "Até a loja" }), el("b", { text: km(o.ate_loja_km) })]),
          el("div", {}, [el("small", { text: "Entrega" }), el("b", { text: km(o.entrega_km) })]),
          el("div", { class: o.ganho_centavos === null ? "largo" : "" }, [el("small", { text: "Destino" }), el("b", { text: o.bairro || "—" })]),
          o.ganho_centavos === null ? null : el("div", {}, [el("small", { text: "Você recebe" }), el("b", { text: reais(o.ganho_centavos) })]),
        ]),
        el("div", { class: "botoes" }, [recusar, aceitar]),
      ]));
  }

  // ------------------------------------------------------------------ telas
  function desenhar() {
    if (!estado) return;
    const foco = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.codigo : null;
    const topo = el("header", { class: "topo" }, [
      el("div", { class: "quem" }, [el("b", { text: estado.nome }), el("small", { text: estado.lojas.join(" · ") })]),
      el("button", { class: "chave" + (estado.online ? " on" : ""), type: "button", "aria-pressed": estado.online ? "true" : "false",
        onclick: alternarOnline }, [el("span", { class: "bola" }), estado.online ? "Disponível" : "Indisponível"]),
    ]);
    let corpo;
    if (aba === "ganhos") corpo = telaGanhos();
    else if (aba === "conta") corpo = telaConta();
    else corpo = telaEntregas();
    const n = estado.entregas.length;
    const abas = el("nav", { class: "abas", "aria-label": "Navegação" }, [
      ["entregas", "🛵", "Entregas" ],
      ["ganhos", "💰", "Ganhos"],
      ["conta", "👤", "Conta"],
    ].map(function ([id, ico, nome]) {
      return el("button", { type: "button", class: aba === id ? "ativa" : "", onclick: function () { aba = id; desenhar(); } },
        [el("span", { class: "ico", text: ico }), el("span", {}, [nome, id === "entregas" && n ? " " : null, id === "entregas" && n ? el("span", { class: "ponto", text: String(n) }) : null])]);
    }));
    app.replaceChildren(topo, el("main", { class: "conteudo" }, corpo), abas, estado.oferta ? telaOferta(estado.oferta) : null);
    if (foco) { const i = app.querySelector('[data-codigo="' + foco + '"]'); if (i) { i.focus(); const v = i.value; i.value = ""; i.value = v; } }
  }

  function telaEntregas() {
    const itens = [];
    if (estado.trocar_pin) {
      itens.push(el("div", { class: "aviso amarelo" }, [el("b", { text: "Troque seu PIN. " }), "Você ainda usa o PIN que a loja definiu. ",
        el("a", { href: "#", onclick: function (ev) { ev.preventDefault(); aba = "conta"; desenhar(); }, text: "Trocar agora" })]));
    }
    if (!estado.online) {
      itens.push(el("div", { class: "cartao vazio" }, [el("span", { class: "grande", text: "😴" }),
        el("b", { text: "Você está indisponível" }), el("p", { text: "Toque em “Indisponível” no topo para começar a receber chamadas." })]));
    } else if (!estado.entregas.length) {
      itens.push(el("div", { class: "cartao vazio" }, [el("span", { class: "grande", text: "📡" }),
        el("b", {}, [el("span", { class: "pulso" }), "Aguardando chamadas…"]),
        el("p", { text: "Deixe o app aberto: quando uma loja chamar, toca um alerta e você tem 30 segundos para aceitar." })]));
    }
    estado.entregas.forEach(function (e) { itens.push(cartaoEntrega(e)); });
    const emMaos = ((estado.repasses && estado.repasses.lojas) || []).reduce(function (t, l) { return t + l.em_maos_centavos; }, 0);
    if (emMaos) itens.push(el("div", { class: "aviso amarelo" }, [el("b", { text: "💵 Você está com " + reais(emMaos) + " das entregas. " }),
      "Ao voltar à loja, ", el("a", { href: "#", onclick: function (ev) { ev.preventDefault(); aba = "ganhos"; desenhar(); }, text: "registre o repasse" }), "."]));
    return itens;
  }

  function campoCodigo(e, acao, rotulo, ajuda) {
    const id = e.id + ":" + acao;
    const entrada = el("input", { inputmode: "numeric", maxlength: 4, pattern: "[0-9]*", autocomplete: "off", placeholder: "0000",
      "aria-label": rotulo, "data-codigo": id, value: codigos[id] || "", oninput: function () { codigos[id] = entrada.value.replace(/\D/g, "").slice(0, 4); entrada.value = codigos[id]; } });
    const erro = el("p", { class: "erro" });
    const botao = el("button", { class: "btn ok", type: "submit", text: "Confirmar" });
    return el("form", { class: "codigo-form", novalidate: true, onsubmit: async function (ev) {
      ev.preventDefault();
      if ((codigos[id] || "").length !== 4) { erro.textContent = "Digite os 4 números."; return; }
      botao.disabled = true; erro.textContent = ""; ocupado = true;
      try {
        await req("POST", "entregas/" + e.id + "/" + acao + "/", { codigo: codigos[id] });
        delete codigos[id];
        if (acao === "entregar" && navigator.vibrate) navigator.vibrate(200);
        ocupado = false;
        await carregar();
      } catch (err) { ocupado = false; erro.textContent = err.message; botao.disabled = false; }
    } }, [el("label", { text: rotulo }), entrada, botao, el("small", { class: "muted", style: "grid-column:1/-1", text: ajuda }), erro]);
  }

  // ------------------------------------------------------------------ cobrança na porta
  async function enviarCobranca(e, corpo, botao, erro) {
    botao.disabled = true; erro.textContent = ""; ocupado = true;
    try {
      await req("POST", "entregas/" + e.id + "/cobrar/", corpo);
      delete cobrando[e.id];
      Object.keys(codigos).forEach(function (k) { if (k.indexOf(e.id + ":") === 0 && k !== e.id + ":entregar") delete codigos[k]; });
      if (navigator.vibrate) navigator.vibrate(120);
      ocupado = false;
      await carregar();
    } catch (err) { ocupado = false; erro.textContent = err.message; botao.disabled = false; }
  }

  function campoValor(id, rotulo, inicial, aoMudar) {
    if (codigos[id] === undefined) codigos[id] = inicial;
    const i = el("input", { inputmode: "decimal", autocomplete: "off", placeholder: "0,00", "aria-label": rotulo, "data-codigo": id,
      value: codigos[id], oninput: function () { codigos[id] = i.value; if (aoMudar) aoMudar(); } });
    return el("label", { class: "campo" }, [el("span", { text: rotulo }), i]);
  }

  function blocoCobranca(e) {
    const valor = e.cobrar_centavos;
    const sugerida = { DINHEIRO: "DINHEIRO", PIX: "PIX", CARTAO_CREDITO: "CARTAO_CREDITO", CARTAO_DEBITO: "CARTAO_DEBITO" }[e.forma_prevista] || "";
    const forma = cobrando[e.id] || (e.cobranca && e.cobranca.pix ? "PIX" : sugerida);
    const topo = el("div", { class: "aviso amarelo" }, [el("div", { class: "cobrar", text: "Cobrar " + reais(valor) }),
      e.forma ? el("div", { text: "Cliente escolheu: " + e.forma + (e.troco_para_centavos ? " · troco para " + reais(e.troco_para_centavos) : "") }) : null]);
    const opcoes = el("div", { class: "formas", role: "group", "aria-label": "Como o cliente pagou" }, [
      ["DINHEIRO", "💵 Dinheiro"], ["CARTAO_CREDITO", "💳 Crédito"], ["CARTAO_DEBITO", "💳 Débito"], ["PIX", "⚡ Pix"],
    ].map(function ([id, nome]) {
      return el("button", { type: "button", class: "btn claro" + (forma === id ? " escolhida" : ""), "aria-pressed": forma === id ? "true" : "false",
        text: nome, onclick: function () { cobrando[e.id] = id; desenhar(); } });
    }));
    const erro = el("p", { class: "erro" });
    let corpo = null;
    if (forma === "DINHEIRO") {
      const idR = e.id + ":recebido", idT = e.id + ":troco";
      const inicial = e.troco_para_centavos && e.troco_para_centavos > valor ? e.troco_para_centavos : valor;
      const dica = el("small", { class: "muted" });
      const conta = function () {
        const r = centavosDe(codigos[idR]), t = centavosDe(codigos[idT]) || 0;
        dica.textContent = r === null ? "" : r - t === valor ? "✓ A conta fecha." : "Recebido − troco precisa dar " + reais(valor) + " (troco certo: " + reais(Math.max(0, r - valor)) + ").";
      };
      const troco = campoValor(idT, "Troco que você deu (R$)", emReais(Math.max(0, inicial - valor)), conta);
      const recebido = campoValor(idR, "Valor que recebeu do cliente (R$)", emReais(inicial), function () {
        const r = centavosDe(codigos[idR]);
        if (r !== null && r >= valor) { codigos[idT] = emReais(r - valor); troco.querySelector("input").value = codigos[idT]; }
        conta();
      });
      conta();
      const botao = el("button", { class: "btn ok bloco", type: "submit", text: "Marcar como recebido" });
      corpo = el("form", { class: "cobranca", novalidate: true, onsubmit: function (ev) {
        ev.preventDefault();
        const r = centavosDe(codigos[idR]);
        if (r === null) { erro.textContent = "Digite o valor recebido."; return; }
        enviarCobranca(e, { forma: "DINHEIRO", valor_recebido_centavos: r, troco_centavos: centavosDe(codigos[idT]) || 0 }, botao, erro);
      } }, [recebido, troco, dica, botao, erro]);
    } else if (forma === "CARTAO_CREDITO" || forma === "CARTAO_DEBITO") {
      const botao = el("button", { class: "btn ok bloco", type: "button", text: "Aprovado — marcar como pago",
        onclick: function () { enviarCobranca(e, { forma: forma }, botao, erro); } });
      corpo = el("div", { class: "cobranca" }, [
        el("p", { text: "Passe " + reais(valor) + " no " + (forma === "CARTAO_CREDITO" ? "crédito" : "débito") + " na maquininha da loja. Quando aprovar, marque como pago." }),
        botao, erro]);
    } else if (forma === "PIX") {
      const manual = el("button", { class: "btn claro bloco", type: "button", text: "Cliente pagou na chave Pix da loja — marcar como pago",
        onclick: function () { if (confirm("Confirme: você viu o Pix de " + reais(valor) + " cair para a loja?")) enviarCobranca(e, { forma: "PIX" }, manual, erro); } });
      const filhosPix = [];
      const pix = e.cobranca && e.cobranca.pix;
      if (pix) {
        if (pix.qr_code_base64) filhosPix.push(el("img", { class: "qr", alt: "QR Code Pix", src: "data:image/png;base64," + pix.qr_code_base64 }));
        filhosPix.push(el("p", { class: "centro" }, [el("span", { class: "pulso" }), "Aguardando o pagamento de " + reais(pix.valor_centavos) + "…"]));
        if (pix.qr_code) filhosPix.push(el("button", { class: "btn claro bloco", type: "button", text: "Copiar código Pix (copia e cola)", onclick: function (ev) {
          const b = ev.currentTarget;
          (navigator.clipboard ? navigator.clipboard.writeText(pix.qr_code) : Promise.reject()).then(function () { b.textContent = "Copiado ✓"; })
            .catch(function () { prompt("Copie o código Pix:", pix.qr_code); });
        } }));
        filhosPix.push(el("small", { class: "muted", text: "Quando o banco confirmar, a entrega é concluída sozinha." }));
      } else if (e.pix_automatico) {
        const gerar = el("button", { class: "btn ok bloco", type: "button", text: "Gerar QR Code Pix de " + reais(valor), onclick: async function () {
          gerar.disabled = true; erro.textContent = ""; ocupado = true;
          try { await req("POST", "entregas/" + e.id + "/pix/"); ocupado = false; await carregar(); }
          catch (err) { ocupado = false; erro.textContent = err.message; gerar.disabled = false; }
        } });
        filhosPix.push(el("p", { text: "Mostre o QR para o cliente pagar agora. A confirmação é automática." }), gerar);
      } else {
        filhosPix.push(el("p", { text: "Esta loja recebe Pix na chave dela. Peça ao cliente para pagar e confira antes de marcar." }));
      }
      filhosPix.push(manual, erro);
      corpo = el("div", { class: "cobranca" }, filhosPix);
    } else {
      corpo = el("p", { class: "muted", text: "Toque em como o cliente vai pagar." });
    }
    return el("div", { class: "bloco-cobranca" }, [topo, opcoes, corpo]);
  }

  function cartaoEntrega(e) {
    const etapa = e.saiu ? el("span", { class: "etiqueta caminho", text: "A caminho do cliente" })
      : e.pronto ? el("span", { class: "etiqueta pronto", text: "Pronto para retirar" })
      : el("span", { class: "etiqueta", text: "Em preparo na loja" });
    const filhos = [el("div", { class: "cab" }, [el("b", { text: "#" + e.numero + " · " + e.loja }), etapa])];
    if (!e.saiu) {
      filhos.push(el("div", { class: "linha" }, "🏪 " + (e.loja_endereco || e.loja)));
      filhos.push(el("div", { class: "botoes" }, [
        el("a", { class: "btn claro", href: e.loja_mapa, target: "_blank", rel: "noopener", text: "🗺️ Ir à loja" }),
        e.loja_telefone ? el("a", { class: "btn claro", href: "tel:" + e.loja_telefone, text: "📞 Loja" }) : el("span")]));
      filhos.push(el("div", { class: "linha muted" }, "Entrega em: " + (e.endereco || "—")));
      if (e.pronto) filhos.push(campoCodigo(e, "retirar", "Código de retirada", "A loja informa este código quando você pegar o pedido."));
      else filhos.push(el("div", { class: "aviso amarelo" }, "Aguarde: a loja ainda está preparando. Quando ficar pronto, peça o código de retirada."));
    } else {
      filhos.push(el("div", { class: "linha" }, [el("b", { text: e.cliente || "Cliente" })]));
      filhos.push(el("div", { class: "linha" }, "📍 " + (e.endereco || "—")));
      if (e.referencia) filhos.push(el("div", { class: "linha muted" }, "Ref.: " + e.referencia));
      filhos.push(el("div", { class: "botoes" }, [
        el("a", { class: "btn claro", href: e.mapa, target: "_blank", rel: "noopener", text: "🗺️ Rota" }),
        e.telefone ? el("a", { class: "btn claro", href: "tel:" + e.telefone, text: "📞 Cliente" }) : el("span")]));
      ((e.cobranca && e.cobranca.feitos) || []).forEach(function (f) {
        filhos.push(el("div", { class: "aviso verde" }, [el("b", { text: "✓ " + f.forma_rotulo + " " + reais(f.valor_centavos) }),
          f.forma === "DINHEIRO" ? el("div", { text: "Recebido " + reais(f.recebido_centavos || f.valor_centavos) + " · troco " + reais(f.troco_centavos || 0) }) : null,
          f.com_voce ? el("div", { class: "muted", text: "Fica com você até repassar à loja (aba Ganhos)." }) : null]));
      });
      if (e.cobrar_centavos) filhos.push(blocoCobranca(e));
      else {
        if (!((e.cobranca && e.cobranca.feitos) || []).length) filhos.push(el("div", { class: "aviso verde", text: "✓ Já está pago" }));
        filhos.push(campoCodigo(e, "entregar", "Código de recebimento", "O cliente tem este código no acompanhamento do pedido e no WhatsApp."));
      }
    }
    if (e.ganho_centavos !== null && e.ganho_centavos !== undefined) filhos.push(el("div", { class: "muted", style: "margin-top:6px", text: "Você recebe: " + reais(e.ganho_centavos) }));
    return el("article", { class: "cartao entrega" }, filhos);
  }

  function telaGanhos() {
    const g = estado.ganhos;
    const valor = function (c) { return g.mostrar_ganhos ? reais(c) : "—"; };
    const historico = el("ul", { class: "lista" }, el("li", { class: "muted" }, "Carregando…"));
    const fresco = hist && Date.now() - histEm < 30000;
    (fresco ? Promise.resolve(hist) : req("GET", "historico/")).then(function (h) {
      if (!fresco) { hist = h; histEm = Date.now(); }
      historico.replaceChildren.apply(historico, h.length ? h.map(function (x) {
        return el("li", {}, [el("span", {}, [el("b", { text: "#" + x.numero + " " }), x.loja + (x.bairro ? " · " + x.bairro : "")]),
          el("span", { text: g.mostrar_ganhos ? reais(x.ganho_centavos) : new Date(x.concluido_em).toLocaleDateString("pt-BR") })]);
      }) : [el("li", { class: "muted" }, "Nenhuma entrega concluída ainda.")]);
    }).catch(function () {});
    return [
      cartaoRepasse(),
      el("div", { class: "numeros" }, [
        el("div", { class: "numero" }, [el("small", { text: "Hoje" }), el("b", { text: valor(g.hoje.ganhos_centavos) }), el("span", { text: g.hoje.entregas + " entrega(s)" })]),
        el("div", { class: "numero" }, [el("small", { text: "Esta semana" }), el("b", { text: valor(g.semana.ganhos_centavos) }), el("span", { text: g.semana.entregas + " entrega(s)" })]),
        el("div", { class: "numero" }, [el("small", { text: "Este mês" }), el("b", { text: valor(g.mes.ganhos_centavos) }), el("span", { text: g.mes.entregas + " entrega(s)" })]),
        el("div", { class: "numero destaque" }, [el("small", { text: "Projeção do mês" }), el("b", { text: valor(g.projecao_mes_centavos) }),
          el("span", { text: "≈ " + g.projecao_entregas_mes + " entregas no ritmo atual" })]),
      ]),
      el("div", { class: "cartao" }, [el("h2", { text: "Pagamentos da loja" }),
        el("div", { class: "aviso amarelo", style: "margin-bottom:8px" }, [el("b", { text: "A receber: " + valor(g.pendente_centavos) }),
          el("div", { text: g.pendente_entregas + " entrega(s) ainda não acertada(s)" })]),
        (g.acertos || []).length ? el("ul", { class: "lista" }, g.acertos.map(function (a) {
          return el("li", {}, [el("span", { text: new Date(a.em).toLocaleDateString("pt-BR") + " · " + a.loja + " · " + a.entregas + " entrega(s)" }),
            el("b", { text: reais(a.pago_centavos) })]);
        })) : el("p", { class: "muted", style: "margin:0", text: "Nenhum acerto registrado ainda." })]),
      el("div", { class: "cartao" }, [el("h2", { text: "Total: " + g.total_entregas + " entrega(s) feitas" }),
        el("p", { class: "muted", text: "Os valores são uma estimativa pelo combinado com cada loja. O pagamento é feito pela loja, como vocês acertaram." }),
        el("ul", { class: "lista" }, g.acordo.map(function (a) {
          return el("li", {}, [el("span", { text: a.loja }), el("span", { class: "muted", text: a.regra + (a.valor_centavos ? ": " + reais(a.valor_centavos) : "") })]);
        }))]),
      el("div", { class: "cartao" }, [el("h2", { text: "Últimas entregas" }), historico]),
    ];
  }

  function cartaoRepasse() {
    const rp = estado.repasses || { lojas: [], ultimos: [] };
    const linhas = [];
    rp.lojas.forEach(function (l) {
      (l.aguardando || []).forEach(function (r) {
        linhas.push(el("div", { class: "aviso" }, [el("b", { text: l.loja + ": você informou " + reais(r.informado_entregador_centavos) }),
          el("div", { class: "muted", text: "Aguardando a loja conferir (" + r.entregas + " entrega(s), " + reais(r.esperado_centavos) + " cobrados)." })]));
      });
      if (!l.em_maos_centavos) return;
      const id = "repasse:" + l.entregador_id;
      const campo = campoValor(id, "Quanto você entregou à loja (R$)", emReais(l.em_maos_centavos));
      const erro = el("p", { class: "erro" });
      const botao = el("button", { class: "btn ok bloco", type: "submit", text: "Marcar como repassado à loja" });
      linhas.push(el("form", { class: "repasse", novalidate: true, onsubmit: async function (ev) {
        ev.preventDefault();
        const v = centavosDe(codigos[id]);
        if (v === null) { erro.textContent = "Digite o valor."; return; }
        if (v !== l.em_maos_centavos && !confirm("O valor é diferente do cobrado (" + reais(l.em_maos_centavos) + "). Enviar mesmo assim?")) return;
        botao.disabled = true; erro.textContent = ""; ocupado = true;
        try { await req("POST", "repasses/", { entregador_id: l.entregador_id, valor_centavos: v }); delete codigos[id]; ocupado = false; await carregar(); }
        catch (err) { ocupado = false; erro.textContent = err.message; botao.disabled = false; }
      } }, [el("div", { class: "aviso amarelo" }, [el("b", { text: "💵 Com você: " + reais(l.em_maos_centavos) }),
        el("div", { text: l.loja + " · " + l.entregas + " entrega(s) em dinheiro" })]), campo, botao, erro]));
    });
    if (!linhas.length && !(rp.ultimos || []).length) return null;
    return el("div", { class: "cartao" }, [el("h2", { text: "Dinheiro das entregas" }),
      linhas.length ? null : el("p", { class: "muted", style: "margin:0 0 8px", text: "Nenhum dinheiro com você agora." }),
      ...linhas,
      (rp.ultimos || []).length ? el("ul", { class: "lista" }, rp.ultimos.map(function (r) {
        return el("li", {}, [el("span", { text: new Date(r.recebido_em || r.criado_em).toLocaleDateString("pt-BR") + " · " + r.loja + " · " + r.status_rotulo }),
          el("b", { style: r.diferenca_centavos < 0 ? "color:var(--erro)" : "", text: reais(r.recebido_loja_centavos || 0) + (r.diferenca_centavos ? " (" + (r.diferenca_centavos > 0 ? "+" : "") + reais(r.diferenca_centavos) + ")" : "") })]);
      })) : null]);
  }

  function telaConta() {
    const atual = el("input", { type: "password", inputmode: "numeric", class: "pin", maxlength: 6, autocomplete: "current-password" });
    const novo = el("input", { type: "password", inputmode: "numeric", class: "pin", maxlength: 6, autocomplete: "new-password" });
    const conf = el("input", { type: "password", inputmode: "numeric", class: "pin", maxlength: 6, autocomplete: "new-password" });
    const msg = el("p", { class: "erro" });
    const botao = el("button", { class: "btn bloco", type: "submit", text: "Salvar novo PIN" });
    const form = el("form", { class: "cartao", style: "display:grid;gap:12px", novalidate: true, onsubmit: async function (ev) {
      ev.preventDefault();
      msg.style.color = ""; msg.textContent = "";
      if (novo.value !== conf.value) { msg.textContent = "A confirmação não confere."; return; }
      botao.disabled = true;
      try {
        const r = await req("POST", "pin/", { atual: atual.value, novo: novo.value });
        token = r.token; gravar(CHAVE, token); sincronizarNativo();
        atual.value = novo.value = conf.value = "";
        msg.style.color = "var(--ok)"; msg.textContent = "PIN alterado!";
        await carregar();
      } catch (e) { msg.textContent = e.message; }
      botao.disabled = false;
    } }, [el("h2", { text: "Trocar PIN" }),
      el("label", { class: "campo" }, [el("span", { text: "PIN atual" }), atual]),
      el("label", { class: "campo" }, [el("span", { text: "Novo PIN (4 a 6 números)" }), novo]),
      el("label", { class: "campo" }, [el("span", { text: "Repita o novo PIN" }), conf]), msg, botao]);
    return [
      el("div", { class: "cartao" }, [el("h2", { text: estado.nome }), el("p", { class: "muted", text: "Lojas: " + estado.lojas.join(", ") })]),
      form,
      el("div", { class: "cartao", style: "display:grid;gap:10px" }, [
        el("p", { class: "muted", style: "margin:0", text: "Para receber as chamadas, deixe o app aberto e “Disponível”. A tela fica acesa enquanto você estiver disponível." }),
        el("button", { class: "btn perigo bloco", type: "button", text: "Sair da conta", onclick: async function () {
          try { await req("POST", "online/", { online: false }); } catch (e) { /* ok */ }
          sair(false);
        } })]),
    ];
  }

  // ------------------------------------------------------------------ início
  (async function () {
    if (!token) { telaEntrar(); return; }
    try { await carregar(); iniciar(); } catch (e) { if (token) { app.replaceChildren(el("div", { class: "carregando", text: "Sem conexão. Tentando de novo…" })); setTimeout(function () { location.reload(); }, 5000); } }
  })();
})();
