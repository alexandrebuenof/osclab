// Teste de NAVEGADOR da navegação com o servidor LENTO (12/11/2026: «estou
// sentindo meio travado nas oscilografias maiores»).
//
//   node tests/navegador/navegacao.mjs <url-base> <sha> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_navegacao_navegador.py`: um sintético com 210
// digitais que mudam (o painel de tiras muitas vezes mais alto que a janela).
// O roteiro ATRASA as respostas do servidor, como a roda do localizador:
//
//   * dois arrastos soltos com o primeiro pedido ainda em voo andam OS DOIS
//     (antes o segundo pedido saía da mesma janela e apagava o primeiro);
//   * seis toques de seta com a leitura lenta andam seis amostras (antes os
//     do meio sumiam);
//   * o pacote de janela seguinte não repete a lista de todos os digitais
//     nem o catálogo (`janela.sem_repetir`), e a tela continua com eles;
//   * a última tira, lá embaixo, aparece pintada ao rolar até ela (a tela só
//     pinta a faixa do painel que está à vista);
//   * vinte recargas não acumulam ouvintes nem nós.
import { abrirChrome, P } from "./comum.mjs";

const [BASE, SHA, FOTOS, PORTA = "9961"] = process.argv.slice(2);
const { cdp, avaliar, confere, foto, navegar, terminar, espera, assentar } =
  await abrirChrome({ porta: PORTA, prefixo: "navegacao", fotos: FOTOS });

await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
  const anterior = window.fetch.bind(window);
  window.__atrasarJanela = false;
  window.__atrasarLeitura = 0;
  window.__pacotes = [];
  let vez = 0;
  window.fetch = (url, opcoes) => {
    const u = String(url);
    const janela = /\\/api\\/onda\\/[0-9a-f]+\\?/.test(u);
    let p = anterior(url, opcoes);
    if (janela) {
      p = p.then((r) => { r.clone().json().then((j) => window.__pacotes.push(Object.keys(j))).catch(() => {}); return r; });
    }
    if (janela && window.__atrasarJanela) {
      const ms = (vez++ % 2) ? 150 : 450;
      p = p.then((r) => new Promise((ok) => setTimeout(() => ok(r), ms)));
    }
    if (u.includes("/leitura") && window.__atrasarLeitura) {
      const ms = window.__atrasarLeitura;
      p = p.then((r) => new Promise((ok) => setTimeout(() => ok(r), ms)));
    }
    return p;
  };
})()` });

await navegar(`${BASE}/`, "document.body");
await avaliar(`localStorage.setItem('osclab-tema', 'claro'); sessionStorage.clear(); 1`);
await navegar(`${BASE}/onda/${SHA}`);
await assentar(500);
await avaliar(`window.scrollTo(0, 0); 1`);

const caixa = async (sel) => JSON.parse(await avaliar(`(() => { const r = document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect();
  return JSON.stringify({ l: r.left, t: r.top, w: r.width, h: r.height }); })()`));
const janela = async () => JSON.parse(await avaliar(`JSON.stringify(window.__janela)`));
const c = await caixa("section.grafico canvas");
const x = c.l + c.w * 0.5, y = c.t + c.h * 0.5;
const mouse = (type, o = {}) => cdp("Input.dispatchMouseEvent", { type, x, y, ...o });
await mouse("mouseMoved");

// Amplia antes, para haver para onde andar dos dois lados.
for (let i = 0; i < 4; i++) { await mouse("mouseWheel", { deltaX: 0, deltaY: -100 }); await assentar(250); }

async function arrastar(dx) {
  await mouse("mousePressed", { button: "left", buttons: 1, clickCount: 1 });
  for (let i = 1; i <= 6; i++) {
    await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: x + (dx * i) / 6, y, button: "left", buttons: 1 });
    await espera(16);
  }
  await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x: x + dx, y, button: "left", buttons: 0, clickCount: 1 });
}

// 1. Um arrasto com o servidor rápido: quanto ele anda.
const j0 = await janela();
await arrastar(-120);
await assentar(400);
const j1 = await janela();
const um = j1.de - j0.de;
confere(um > 0, `um arrasto para a esquerda anda para a frente (${(um * 1000).toFixed(2)} ms)`);
confere(Math.abs((j1.ate - j1.de) - (j0.ate - j0.de)) < 1e-9, "arrastar não muda a largura da janela");

// 2. Dois arrastos seguidos com o servidor lento: andam os dois.
await mouse("mouseMoved");
await avaliar(`window.__atrasarJanela = true; 1`);
await arrastar(-120);
await espera(60);
await arrastar(-120);
await assentar(2500);
await avaliar(`window.__atrasarJanela = false; 1`);
const j2 = await janela();
const dois = j2.de - j1.de;
confere(Math.abs(dois / um - 2) < 0.02,
  `dois arrastos com o primeiro pedido em voo andam os dois (${(dois * 1000).toFixed(2)} ms, esperado ${(2 * um * 1000).toFixed(2)})`);

// 3. Seis toques de seta com a leitura lenta: seis amostras.
await mouse("mouseMoved");
await cdp("Input.dispatchKeyEvent", { type: "keyDown", key: "1", code: "Digit1", windowsVirtualKeyCode: 49 });
await cdp("Input.dispatchKeyEvent", { type: "keyUp", key: "1", code: "Digit1" });
await assentar(500);
const t0 = (await avaliar(`JSON.stringify(window.__cursores)`)) && JSON.parse(await avaliar(`JSON.stringify(window.__cursores)`))[0];
await avaliar(`window.__atrasarLeitura = 300; 1`);
for (let i = 0; i < 6; i++) {
  await cdp("Input.dispatchKeyEvent", { type: "keyDown", key: "ArrowRight", code: "ArrowRight", windowsVirtualKeyCode: 39 });
  await cdp("Input.dispatchKeyEvent", { type: "keyUp", key: "ArrowRight", code: "ArrowRight" });
  await espera(40);
}
await assentar(1500);
await avaliar(`window.__atrasarLeitura = 0; 1`);
const t1 = JSON.parse(await avaliar(`JSON.stringify(window.__cursores)`))[0];
const amostras = Math.round((t1 - t0) * 2000);
confere(amostras === 6, `seis toques de seta com a leitura lenta andam seis amostras (${amostras})`);

// 4. O pacote seguinte não repete a lista de todos os digitais.
const pacotes = JSON.parse(await avaliar(`JSON.stringify(window.__pacotes)`));
confere(pacotes.length > 2 && pacotes[0].includes("digitais_disponiveis"),
  "o primeiro pacote traz a lista de todos os digitais");
confere(pacotes.slice(1).every((k) => !k.includes("digitais_disponiveis") && k.includes("estaticos_omitidos")),
  `os seguintes não a repetem (${pacotes.length} pacotes)`);

// 5. A última tira aparece pintada ao rolar até ela.
const alto = await avaliar(`Math.max(...[...document.querySelectorAll('section.grafico canvas')].map((k) => k.getBoundingClientRect().height))`);
confere(alto > 2000, `o painel de tiras é mais alto que a janela (${Math.round(alto)} px)`);
await avaliar(`(() => { const c = [...document.querySelectorAll('section.grafico canvas')].find((k) => k.getBoundingClientRect().height > 2000);
  window.scrollTo(0, scrollY + c.getBoundingClientRect().bottom - innerHeight + 10); return 1; })()`);
await assentar(400);
const pintada = await avaliar(`(() => {
  const c = [...document.querySelectorAll('section.grafico canvas')].find((k) => k.getBoundingClientRect().height > 2000);
  const ctx = c.getContext('2d'); const dpr = devicePixelRatio || 1;
  // a faixa da última tira: 60 px acima do pé do canvas, a largura toda
  const y = Math.round((c.height / dpr - 60) * dpr);
  const linha = ctx.getImageData(0, y - 40, c.width, 80).data;
  let tinta = 0; for (let i = 3; i < linha.length; i += 4) if (linha[i] > 0) tinta++;
  return tinta; })()`);
confere(pintada > 1000, `a última tira, lá embaixo, está pintada (${pintada} pixels com tinta)`);
await foto("navegacao-fim-das-tiras.png");
await avaliar(`window.scrollTo(0, 0); 1`);
await assentar(300);

// 6. Vinte recargas não acumulam ouvintes nem nós.
const metricas = async () => Object.fromEntries((await cdp("Performance.getMetrics")).result.metrics
  .filter((m) => ["JSEventListeners", "Nodes"].includes(m.name)).map((m) => [m.name, m.value]));
await cdp("Performance.enable");
await mouse("mouseMoved");
// Dez de aquecimento: a primeira recarga depois de pôr o cursor monta a
// tabelinha e a moldura, que ficam — isso é estado, não vazamento.
for (let i = 0; i < 10; i++) { await mouse("mouseWheel", { deltaX: 0, deltaY: i % 2 ? -100 : 100 }); await assentar(200); }
await cdp("HeapProfiler.collectGarbage");
const antes = await metricas();
for (let i = 0; i < 20; i++) { await mouse("mouseWheel", { deltaX: 0, deltaY: i % 2 ? -100 : 100 }); await assentar(200); }
await cdp("HeapProfiler.collectGarbage");
const depois = await metricas();
confere(depois.JSEventListeners <= antes.JSEventListeners + 5,
  `vinte recargas não acumulam ouvintes (${antes.JSEventListeners} → ${depois.JSEventListeners})`);
confere(depois.Nodes <= antes.Nodes * 1.1 + 50, `nem nós (${antes.Nodes} → ${depois.Nodes})`);

terminar();
