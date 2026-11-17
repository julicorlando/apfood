// Eventos em tempo real da loja (pedido novo, mudança de status, estoque).
// Um WebSocket por aba; reconecta sozinho com espera crescente.
import { sessao } from "./api.js";

const ouvintes = new Set();
let ws = null;
let lojaConectada = null;
let tentativas = 0;
let timer = null;
let conectado = false;
const ouvintesEstado = new Set();

function avisarEstado(v) {
  conectado = v;
  ouvintesEstado.forEach((f) => f(v));
}

export function aoMudarConexao(f) { ouvintesEstado.add(f); f(conectado); return () => ouvintesEstado.delete(f); }

export function conectar() {
  const loja = sessao.loja?.id;
  if (!loja) return;
  if (ws && lojaConectada === loja && ws.readyState <= 1) return;
  desconectar();
  lojaConectada = loja;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/pdv/${loja}/`);
  ws.onopen = () => { tentativas = 0; avisarEstado(true); };
  ws.onmessage = (ev) => {
    let dados;
    try { dados = JSON.parse(ev.data); } catch { return; }
    ouvintes.forEach((f) => { try { f(dados); } catch (e) { console.error(e); } });
  };
  ws.onclose = () => {
    avisarEstado(false);
    if (lojaConectada !== loja) return;
    const espera = Math.min(30000, 1000 * 2 ** tentativas++);
    timer = setTimeout(conectar, espera);
  };
}

export function desconectar() {
  clearTimeout(timer);
  lojaConectada = null;
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  avisarEstado(false);
}

export function ouvir(f) { ouvintes.add(f); return () => ouvintes.delete(f); }

// Sinal sonoro curto (sem arquivo de áudio).
let ctx = null;
// Volume do alerta de pedido (0 a 1; padrão máximo). Ajustável em Configurações → Impressão.
export function volumeAlerta() {
  try { const v = parseFloat(localStorage.getItem("apfood_volume_alerta")); return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 1; } catch { return 1; }
}
export function definirVolumeAlerta(v) {
  try { localStorage.setItem("apfood_volume_alerta", String(v)); } catch { /* ok */ }
}

// Alerta de pedido novo: onda quadrada (bem audível na cozinha), 3 toques, repetido 3 vezes, com compressor
// para soar alto sem distorcer.
export function bipe(repeticoes = 3) {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    const vol = volumeAlerta();
    if (!vol) return;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -6;
    comp.ratio.value = 4;
    const mestre = ctx.createGain();
    mestre.gain.value = vol;
    comp.connect(mestre).connect(ctx.destination);
    const inicio = ctx.currentTime + 0.02;
    for (let r = 0; r < repeticoes; r++) {
      for (const [i, freq] of [988, 1319, 1760].entries()) {
        const t = inicio + r * 1.1 + i * 0.2;
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "square";
        o.frequency.value = freq;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.9, t + 0.01);
        g.gain.setValueAtTime(0.9, t + 0.15);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
        o.connect(g).connect(comp);
        o.start(t);
        o.stop(t + 0.19);
      }
    }
  } catch { /* navegador sem áudio */ }
}
