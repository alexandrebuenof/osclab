// Teste de NAVEGADOR dos painéis (Chrome sem janela, via CDP).
//
//   node tests/navegador/paineis.mjs <url-base> <sha-trafo> <sha-alimentador> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_paineis_navegador.py`, que sobe o servidor num
// acervo temporário com os registros de `tests/casos_calculadora.py`. Sai
// com código 1 se alguma conferência falhar. Confere, com o CSS aplicado:
//   - todo tipo de gráfico do «+ adicionar gráfico» tem a engrenagem;
//   - nenhum botão visível sai com a cara do botão do navegador — nem nos
//     estados de «falta ajuste», nem dentro das caixas das engrenagens;
//   - a caixa da engrenagem é larga e baixa, e cabe na janela;
//   - o estado «falta o terminal remoto» do plano alfa é dito UMA vez;
//   - a roda no localizador: amplia proporcional ao deltaY dentro da moldura
//     sem rolar a página, rola a página fora dela, e no piso não anda de lado.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [BASE, TRAFO, ALIM, FOTOS, PORTA = "9954"] = process.argv.slice(2);
const CHROMES = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
                 "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                 "/usr/bin/google-chrome", "/usr/bin/chromium"];
const CHROME = CHROMES.find((c) => existsSync(c));
if (!CHROME) { console.log("SEM CHROME"); process.exit(77); }
mkdirSync(FOTOS, { recursive: true });
const W = 1600, H = 1000;
const perfil = join(tmpdir(), `osclab-paineis-cdp-${PORTA}`);
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--hide-scrollbars",
  `--remote-debugging-port=${PORTA}`, `--user-data-dir=${perfil}`, `--window-size=${W},${H}`, "about:blank"],
  { stdio: "ignore" });
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
let alvo;
for (let i = 0; i < 60 && !alvo; i++) {
  try { alvo = (await (await fetch(`http://127.0.0.1:${PORTA}/json`)).json()).find((t) => t.type === "page"); }
  catch { await espera(250); }
}
const ws = new WebSocket(alvo.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let seq = 0; const pend = new Map(); const erros = []; const falhas = [];
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); return; }
  if (m.method === "Runtime.exceptionThrown") erros.push((m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).split("\n")[0]);
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") erros.push(m.params.args.map((a) => a.value ?? a.description).join(" "));
});
const cdp = (method, params = {}) => new Promise((r) => { const id = ++seq; pend.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
await cdp("Runtime.enable"); await cdp("Page.enable");
await cdp("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
const avaliar = async (expr) => {
  const r = await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.result?.exceptionDetails) erros.push("avaliar: " + (r.result.exceptionDetails.exception?.description || "").split("\n")[0]);
  return r.result?.result?.value;
};
const confere = (ok, oque) => { if (!ok) falhas.push(oque); console.log(`${ok ? "ok " : "FALHA"} ${oque}`); };
const foto = async (nome) => {
  const r = await cdp("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(FOTOS, nome), Buffer.from(r.result.data, "base64"));
};
const roda = (x, y, dy) => cdp("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaX: 0, deltaY: dy });
const P = (ms) => `new Promise(r => setTimeout(r, ${ms}))`;
const ir = async (sha) => {
  await cdp("Page.navigate", { url: `${BASE}/` }); await espera(800);
  await avaliar(`localStorage.setItem('osclab-tema', 'claro'); localStorage.setItem('osclab:catalogo:visao', 'avancado')`);
  await cdp("Page.navigate", { url: `${BASE}/onda/${sha}` }); await espera(3500);
};
const AJUDANTES = `
  window.__fechar = () => document.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  window.__tipos = async () => { document.querySelector('.novo-grafico').click(); await ${P(300)};
    const t = [...document.querySelectorAll('.opcao-de-tipo')].map(b => [b.textContent, b.disabled]); __fechar(); await ${P(200)}; return t; };
  window.__criar = async (rotulo) => { document.querySelector('.novo-grafico').click(); await ${P(300)};
    [...document.querySelectorAll('.opcao-de-tipo')].find(b => b.textContent === rotulo).click(); await ${P(2500)}; };
  // A cara do botão do navegador: borda "outset" de 2 px e fundo ButtonFace.
  window.__nativos = (raiz) => [...(raiz || document).querySelectorAll('button')]
    .filter(b => b.offsetParent && b.getClientRects().length)
    .filter(b => { const s = getComputedStyle(b); return s.borderTopStyle === 'outset' || s.backgroundColor === 'rgb(239, 239, 239)'; })
    .map(b => (b.className || '(sem classe)') + ' «' + b.textContent.trim().slice(0, 40) + '»');
  1`;

// --- 1. todo tipo, engrenagem, botão nativo, caixa da engrenagem ------------------
for (const [nome, sha] of [["trafo", TRAFO], ["alimentador", ALIM]]) {
  await ir(sha);
  await avaliar(AJUDANTES);
  const tipos = await avaliar("__tipos().then(JSON.stringify)").then(JSON.parse);
  confere(tipos.length === 11 && tipos.every(([, d]) => !d), `${nome}: os 11 tipos no menu, todos habilitados`);
  for (const [rotulo] of tipos) await avaliar(`__criar(${JSON.stringify(rotulo)})`);
  const sem = await avaliar(`JSON.stringify([...document.querySelectorAll('section.grafico')]
    .filter(g => !g.querySelector('.grafico-titulo .engrenagem')).map(g => g.querySelector('.grafico-titulo')?.textContent.slice(0, 30)))`);
  confere(sem === "[]", `${nome}: todo gráfico tem a engrenagem ${sem}`);
  const nativos = await avaliar("JSON.stringify(__nativos())");
  confere(nativos === "[]", `${nome}: nenhum botão com a cara do navegador ${nativos}`);

  const n = await avaliar("document.querySelectorAll('section.grafico').length");
  for (let i = 0; i < n; i++) {
    const r = JSON.parse(await avaliar(`(async () => {
      const g = document.querySelectorAll('section.grafico')[${i}];
      g.scrollIntoView({ block: 'start' }); window.scrollBy(0, -70); await ${P(250)};
      g.querySelector('.grafico-titulo .engrenagem').click(); await ${P(400)};
      const m = document.querySelector('.menu-suspenso.menu-de-ajustes');
      const titulo = g.querySelector('.grafico-titulo').firstChild.textContent;
      if (!m) return JSON.stringify({ titulo });
      const b = m.getBoundingClientRect(), e = g.querySelector('.engrenagem').getBoundingClientRect();
      const r = { titulo, l: Math.round(b.width), a: Math.round(b.height), topo: b.top, base: b.bottom,
                  esq: b.left, dir: b.right, perto: Math.abs(b.left - e.left) < 600,
                  nativos: __nativos(m) };
      __fechar(); await ${P(200)};
      return JSON.stringify(r); })()`));
    if (r.l === undefined) { confere(false, `${nome}: «${r.titulo}» abre a caixa da engrenagem`); continue; }
    confere(r.topo >= 0 && r.base <= H && r.esq >= 0 && r.dir <= W && r.perto,
      `${nome}: a caixa da engrenagem de «${r.titulo}» cabe na janela, junto do botão (${r.l}×${r.a})`);
    confere(r.l <= 540 && r.a <= H - 16, `${nome}: «${r.titulo}» tem largura até 540 px (${r.l})`);
    // Não alta e estreita: a caixa do alfa era 230 × 772 e a do plano de
    // impedância 230 × 457.
    confere(r.a < 220 || r.a <= r.l * 1.3, `${nome}: a engrenagem de «${r.titulo}» não é alta e estreita (${r.l}×${r.a})`);
    confere(r.nativos.length === 0, `${nome}: nada com a cara do navegador na engrenagem de «${r.titulo}» ${r.nativos}`);
    if (r.titulo.startsWith("Plano alfa") && nome === "trafo") {
      confere(r.l >= 440 && r.a < r.l * 1.4, `${nome}: a engrenagem do alfa é larga e baixa (${r.l}×${r.a})`);
      await avaliar(`(async () => { const g = document.querySelectorAll('section.grafico')[${i}];
        g.querySelector('.grafico-titulo .engrenagem').click(); await ${P(400)}; })()`);
      await foto(`${nome}-engrenagem-alfa.png`);
      await avaliar(`(async () => { __fechar(); await ${P(200)}; })()`);
    }
  }
  if (nome === "alimentador") {
    // O alfa sem terminal remoto diz isso UMA vez, fora do desenho.
    const vezes = await avaliar(`(() => { const g = [...document.querySelectorAll('section.grafico')]
      .find(x => x.querySelector('.grafico-titulo').textContent.startsWith('Plano alfa'));
      return (g.textContent.match(/trinca de corrente só/g) || []).length; })()`);
    confere(vezes === 1, `${nome}: «falta o terminal remoto» dito uma vez só (${vezes})`);
  }
  if (nome === "trafo") {
    // O quadro do diferencial sem ajustes: o «preencher» com a cara do programa.
    const preencher = await avaliar(`(() => { const b = [...document.querySelectorAll('.faltam-ajustes button')][0];
      if (!b) return null; b.scrollIntoView({ block: 'center' }); const s = getComputedStyle(b);
      return [s.borderTopStyle, s.borderTopWidth, s.backgroundColor].join(' '); })()`);
    confere(preencher && preencher.startsWith("solid 1px"), `${nome}: «preencher …» do diferencial no desenho do programa (${preencher})`);
    await espera(300);
    await foto(`${nome}-diferencial-sem-ajustes.png`);
  }
}

// --- 2. a roda no localizador -----------------------------------------------
await ir(ALIM);
await avaliar(AJUDANTES);
await avaliar("__criar('localizador de faltas')");
await avaliar(`document.querySelector('.grafico-localizador').scrollIntoView({ block: 'center' })`);
await espera(500);
const caixa = async () => JSON.parse(await avaliar(`(() => { const c = document.querySelector('.grafico-localizador canvas').getBoundingClientRect();
  return JSON.stringify({ l: c.left, t: c.top, w: c.width, sy: scrollY, j: window.__janela }); })()`));
let c = await caixa();
const largura = (j) => j.ate - j.de;
const dentro = [c.l + c.w * 0.45, c.t + 80];
await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: dentro[0], y: dentro[1] });
// Um gesto LEVE: oito eventos de 15 px, como manda uma roda de alta resolução.
for (let i = 0; i < 8; i++) { await roda(dentro[0], dentro[1], -15); await espera(16); }
await espera(900);
let d = await caixa();
const fator = largura(d.j) / largura(c.j);
confere(fator > 0.6 && fator < 0.9, `localizador: 120 px de roda ampliam ~0,77× (${fator.toFixed(3)})`);
confere(d.sy === c.sy, "localizador: a roda dentro da moldura não rola a página");
// Fora da moldura (a margem dos rótulos): a página rola, a janela não muda.
c = await caixa();
await roda(c.l + 20, c.t + 80, -100);   // para CIMA: o localizador é o último, a página já está no fim
await espera(700);
d = await caixa();
confere(d.sy !== c.sy && largura(d.j) === largura(c.j), `localizador: fora da moldura a roda rola a página (${c.sy} → ${d.sy})`);
// No piso, girar mais não anda de lado.
await avaliar(`document.querySelector('.grafico-localizador').scrollIntoView({ block: 'center' })`);
await espera(400);
c = await caixa();
const p = [c.l + c.w * 0.3, c.t + 80];
for (let g = 0; g < 4; g++) {
  for (let i = 0; i < 6; i++) { await roda(p[0], p[1], -100); await espera(10); }
  await espera(500);
}
const piso = (await caixa()).j;
for (let i = 0; i < 3; i++) { await roda(p[0], p[1], -100); await espera(400); }
await espera(500);
const depois = (await caixa()).j;
confere(Math.abs(depois.de - piso.de) < 1e-9 && Math.abs(depois.ate - piso.ate) < 1e-9,
  `localizador: no piso a roda não anda de lado (${piso.de.toFixed(5)} → ${depois.de.toFixed(5)})`);
await foto("localizador-no-piso.png");

confere(erros.length === 0, `sem erro no console${erros.length ? ": " + erros.slice(0, 3).join(" | ") : ""}`);
ws.close();
chrome.kill();
console.log(falhas.length ? `\n${falhas.length} FALHA(S)` : "\ntudo certo");
process.exit(falhas.length ? 1 : 0);
