// Teste de NAVEGADOR das COMBINAÇÕES de gestos com o servidor lento e as
// respostas fora de ordem (12/11/2026, pedido do Alexandre: «a janela final
// tem que ser exatamente a composição dos gestos na ordem em que foram
// feitos — nenhum se perde, nenhum é aplicado duas vezes, sem voltar para
// trás»).
//
//   node tests/navegador/combinacoes.mjs <url-base> <sha> <pasta-das-fotos> [porta-cdp]
//
// Calibra com o servidor rápido (onde cai o mouse na janela, quantos
// segundos vale um pixel) e então, com as respostas da janela atrasadas
// 450/150 ms alternados, faz cada combinação e confere a janela final contra
// a composição calculada aqui, gesto a gesto, com as contas de
// `plot/navegacao.py` (ampliar em torno do foco, andar):
//
//   1. roda e, com ela em voo, um arrasto;
//   2. arrasto e, com ele em voo, a roda;
//   3. a roda NO MEIO de um arrasto (antes era ignorada);
//   4. a roda e logo um Shift+faixa (a faixa é absoluta: vale ela);
//   5. roda, arrasto e o botão direito no meio da fila (vale o inteiro);
//   6. setas entre os gestos: o cursor anda as amostras pedidas e não se
//      mexe com o zoom.
// Em todas, a janela nunca volta a uma já deixada.
import { abrirChrome } from "./comum.mjs";

const [BASE, SHA, FOTOS, PORTA = "9963"] = process.argv.slice(2);
const { cdp, avaliar, confere, foto, navegar, terminar, espera, assentar } =
  await abrirChrome({ porta: PORTA, prefixo: "combinacoes", fotos: FOTOS });

await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
  const anterior = window.fetch.bind(window);
  window.__atrasar = false;
  window.__urls = [];
  window.__vistas = [];
  let vez = 0;
  window.fetch = (url, opcoes) => {
    const u = String(url);
    const janela = /\\/api\\/onda\\/[0-9a-f]+\\?/.test(u);
    if (janela) window.__urls.push(u);
    let p = anterior(url, opcoes);
    if (janela && window.__atrasar) {
      const ms = (vez++ % 2) ? 150 : 450;
      p = p.then((r) => new Promise((ok) => setTimeout(() => ok(r), ms)));
    }
    return p;
  };
  // Toda janela que a tela APLICOU, na ordem.
  setInterval(() => {
    const j = window.__janela; if (!j) return;
    const k = j.de + "|" + j.ate;
    if (window.__vistas[window.__vistas.length - 1] !== k) window.__vistas.push(k);
  }, 10);
})()` });

await navegar(`${BASE}/`, "document.body");
await avaliar(`localStorage.setItem('osclab-tema', 'claro'); sessionStorage.clear(); 1`);
await navegar(`${BASE}/onda/${SHA}`);
await assentar(500);
await avaliar(`window.scrollTo(0, 0); 1`);

const r = JSON.parse(await avaliar(`(() => { const c = document.querySelector('section.grafico canvas').getBoundingClientRect();
  return JSON.stringify({ l: c.left, t: c.top, w: c.width, h: c.height }); })()`));
const x = Math.round(r.l + r.w * 0.55), y = Math.round(r.t + r.h * 0.5);
const janela = async () => JSON.parse(await avaliar(`JSON.stringify(window.__janela)`));
const ultimaUrl = async () => new URL(await avaliar(`window.__urls[window.__urls.length - 1]`), "http://x");
const mouse = (type, o = {}) => cdp("Input.dispatchMouseEvent", { type, x, y, ...o });
const roda = (px = x, dy = -100) => cdp("Input.dispatchMouseEvent", { type: "mouseWheel", x: px, y, deltaX: 0, deltaY: dy });
const tecla = (key, code, vk, mod = 0) => cdp("Input.dispatchKeyEvent", { type: "keyDown", key, code, windowsVirtualKeyCode: vk, modifiers: mod })
  .then(() => cdp("Input.dispatchKeyEvent", { type: "keyUp", key, code, modifiers: mod }));
async function arrastar(dx, passos = 6, depois = null) {
  await mouse("mousePressed", { button: "left", buttons: 1, clickCount: 1 });
  for (let i = 1; i <= passos; i++) {
    await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: x + (dx * i) / passos, y, button: "left", buttons: 1 });
    await espera(16);
    if (depois && i === passos / 2) await depois(x + (dx * i) / passos);
  }
  await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x: x + dx, y, button: "left", buttons: 0, clickCount: 1 });
}
const L = (j) => j.ate - j.de;
const ampliar = (j, z, foco) => ({ de: foco - (foco - j.de) * z, ate: foco + (j.ate - foco) * z });
const andar = (j, s) => ({ de: j.de + s, ate: j.ate + s });
const perto = (a, b, tol) => Math.abs(a.de - b.de) < tol && Math.abs(a.ate - b.ate) < tol;
const fmt = (j) => `${(j.de * 1000).toFixed(3)}–${(j.ate * 1000).toFixed(3)} ms`;
async function semVoltar(nome, desde) {
  const vistas = JSON.parse(await avaliar(`JSON.stringify(window.__vistas.slice(${desde}))`));
  const repetida = vistas.some((v, i) => vistas.indexOf(v) !== i);
  confere(!repetida, `${nome}: a janela nunca volta a uma já deixada (${vistas.length} janelas aplicadas)`);
}

// --- calibração, servidor rápido ------------------------------------------
await mouse("mouseMoved");
await mouse("mousePressed", { button: "right", buttons: 2, clickCount: 1 });
await mouse("mouseReleased", { button: "right", buttons: 0, clickCount: 1 });
await assentar(400);
const inteiro = await janela();
// O cursor 1 no mouse, para as setas — ANTES de medir: a tabelinha que ele
// abre estreita o desenho.
await tecla("1", "Digit1", 49);
await assentar(400);
const cursor0 = JSON.parse(await avaliar(`JSON.stringify(window.__cursores)`))[0];
// Uma janela no meio do registro, longe das bordas e do piso.
for (let i = 0; i < 3; i++) { await roda(); await assentar(300); }
let j = await janela();
const u = await ultimaUrl();
const f = (Number(u.searchParams.get("foco")) - Number(u.searchParams.get("de")))
        / (Number(u.searchParams.get("ate")) - Number(u.searchParams.get("de")));
await arrastar(-120);
await assentar(400);
const j2 = await janela();
const pxPorJanela = 120 / ((j2.de - j.de) / L(j));          // a largura do desenho, em px
confere(f > 0.3 && f < 0.8 && pxPorJanela > 500, `calibração: mouse em ${(f * 100).toFixed(1)} % da janela, desenho de ${pxPorJanela.toFixed(1)} px`);
const tol = (jj) => L(jj) * 1e-6;

await avaliar(`window.__atrasar = true; 1`);

// --- 1. roda e, com ela em voo, um arrasto --------------------------------
j = await janela();
let desde = await avaliar(`window.__vistas.length`);
await roda();
await espera(30);
await tecla("ArrowRight", "ArrowRight", 39);
await arrastar(-120);
await assentar(2500);
let esperado = andar(ampliar(j, 0.8, j.de + f * L(j)), 120 * L(j) / pxPorJanela);
let fim = await janela();
confere(perto(fim, esperado, tol(j)), `roda + arrasto com a roda em voo: ${fmt(fim)} (esperado ${fmt(esperado)})`);
await semVoltar("roda + arrasto", desde);

// --- 2. arrasto e, com ele em voo, a roda ---------------------------------
j = await janela();
desde = await avaliar(`window.__vistas.length`);
await arrastar(-120);
await espera(30);
await mouse("mouseMoved");
await roda();
await tecla("ArrowRight", "ArrowRight", 39);
await assentar(2500);
const andado = andar(j, 120 * L(j) / pxPorJanela);
esperado = ampliar(andado, 0.8, andado.de + f * L(andado));
fim = await janela();
confere(perto(fim, esperado, tol(j)), `arrasto + roda com o arrasto em voo: ${fmt(fim)} (esperado ${fmt(esperado)})`);
await semVoltar("arrasto + roda", desde);

// --- 3. a roda no meio de um arrasto --------------------------------------
j = await janela();
desde = await avaliar(`window.__vistas.length`);
await arrastar(-120, 6, async (xm) => {
  await cdp("Input.dispatchMouseEvent", { type: "mouseWheel", x: xm, y, deltaX: 0, deltaY: -100, buttons: 1 });
  await espera(140);                    // o entalhe sai (70 ms) antes do resto do arrasto
});
await assentar(2500);
esperado = andar(ampliar(j, 0.8, j.de + f * L(j)), 120 * L(j) / pxPorJanela);
fim = await janela();
confere(perto(fim, esperado, tol(j)), `roda no meio do arrasto vale, e o arrasto também: ${fmt(fim)} (esperado ${fmt(esperado)})`);
await semVoltar("roda no meio do arrasto", desde);

// --- 4. roda e logo um Shift+faixa ----------------------------------------
j = await janela();
desde = await avaliar(`window.__vistas.length`);
await mouse("mouseMoved");
await roda();
await espera(30);
await mouse("mousePressed", { button: "left", buttons: 1, clickCount: 1, modifiers: 8 });
for (let i = 1; i <= 5; i++) {
  await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: x + i * 30, y, button: "left", buttons: 1, modifiers: 8 });
  await espera(16);
}
await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x: x + 150, y, button: "left", buttons: 0, clickCount: 1, modifiers: 8 });
await assentar(2500);
esperado = { de: j.de + f * L(j), ate: j.de + (f + 150 / pxPorJanela) * L(j) };
fim = await janela();
confere(perto(fim, esperado, tol(j)), `roda + Shift+faixa: vale a faixa marcada na tela de então: ${fmt(fim)} (esperado ${fmt(esperado)})`);
await semVoltar("roda + faixa", desde);

// --- 6. as setas: o cursor andou as amostras pedidas -----------------------
const cursor1 = JSON.parse(await avaliar(`JSON.stringify(window.__cursores)`))[0];
const amostras = Math.round((cursor1 - cursor0) * 2000);
confere(amostras === 2, `as setas entre os gestos andaram o cursor duas amostras, sem o zoom mexer nele (${amostras})`);

// --- 5. roda, arrasto e o botão direito no meio da fila --------------------
desde = await avaliar(`window.__vistas.length`);
await mouse("mouseMoved");
await roda();
await espera(30);
await arrastar(-120);
await mouse("mousePressed", { button: "right", buttons: 2, clickCount: 1 });
await mouse("mouseReleased", { button: "right", buttons: 0, clickCount: 1 });
await assentar(3000);
fim = await janela();
confere(perto(fim, inteiro, 1e-9), `roda + arrasto + botão direito: termina no registro inteiro (${fmt(fim)})`);
await semVoltar("botão direito na fila", desde);
await foto("combinacoes-fim.png");

terminar();
