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
export function bipe() {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    const agora = ctx.currentTime;
    for (const [i, freq] of [880, 1175].entries()) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = freq;
      g.gain.setValueAtTime(0.15, agora + i * 0.18);
      g.gain.exponentialRampToValueAtTime(0.001, agora + i * 0.18 + 0.16);
      o.connect(g).connect(ctx.destination);
      o.start(agora + i * 0.18);
      o.stop(agora + i * 0.18 + 0.17);
    }
  } catch { /* navegador sem áudio */ }
}
