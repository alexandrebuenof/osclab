// Teste de NAVEGADOR da roda no painel localizador com o servidor LENTO
// (12/11/2026: «é muito difícil dar zoom; quando damos, o gráfico
// movimenta e some da tela»).
//
//   node tests/navegador/roda-localizador.mjs <url-base> <sha-A> <sha-B> <linha-json> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_roda_localizador_navegador.py`: dois terminais
// de uma falta AG do mini-EMTP, a linha DIGITADA, o painel localizador.
//
// O defeito só aparece quando a resposta da janela demora mais que o
// intervalo entre dois entalhes. Num registro de relé de verdade ela levava
// ~1 s (SEL-411L, 3968 digitais), e com as duas oscilografias do
// localizador o dobro; o registro sintético responde em 30 ms. Então o
// roteiro ATRASA as respostas da janela, 150 a 400 ms alternados — fora de
// ordem de propósito —, e gira a roda dez entalhes, um a cada 110 ms:
//
//   * os dez entalhes valem: 0,8¹⁰ (antes saía 0,51 em vez de 0,107);
//   * a janela nunca volta para trás durante o giro;
//   * o instante sob o mouse fica sob o mouse;
//   * a página não rola.
import { abrirChrome, P } from "./comum.mjs";

const [BASE, SHA_A, SHA_B, LINHA, FOTOS, PORTA = "9957"] = process.argv.slice(2);
const { cdp, avaliar, confere, foto, navegar, terminar, espera, assentar } =
  await abrirChrome({ porta: PORTA, prefixo: "roda-loc", fotos: FOTOS });

await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
  const anterior = window.fetch.bind(window);
  window.__atrasar = false;
  let vez = 0;
  window.fetch = (url, opcoes) => {
    if (String(url).includes("/localizar") && opcoes && typeof opcoes.body === "string") {
      const corpo = JSON.parse(opcoes.body);
      corpo.fonte = "manual";
      corpo.manual = ${LINHA};
      opcoes = { ...opcoes, body: JSON.stringify(corpo) };
    }
    // Só o pedido da JANELA (/api/onda/<sha>?…) atrasa, e alternando 400 e
    // 150 ms: o segundo de dois pedidos seguidos chega PRIMEIRO.
    if (window.__atrasar && /\\/api\\/onda\\/[0-9a-f]+\\?/.test(String(url))) {
      const ms = (vez++ % 2) ? 150 : 400;
      return anterior(url, opcoes).then((r) => new Promise((ok) => setTimeout(() => ok(r), ms)));
    }
    return anterior(url, opcoes);
  };
})()` });

await navegar(`${BASE}/`, "document.body");
await avaliar(`localStorage.setItem('osclab-tema', 'claro');
  localStorage.setItem('osclab:catalogo:visao', 'avancado');
  sessionStorage.setItem('osclab:aba:${SHA_A}:', JSON.stringify({ outros: [{ sha: '${SHA_B}' }], alinhar: 'falta' }));
  1`);
await navegar(`${BASE}/onda/${SHA_A}`);
await avaliar(`(async () => {
  document.querySelector('.novo-grafico').click(); await ${P(300)};
  [...document.querySelectorAll('.opcao-de-tipo')].find(b => b.textContent === 'localizador de faltas').click();
  await ${P(1500)};
  await window.__esperar(() => /\\d km/.test(document.querySelector('.pl-comprimento')?.textContent || ''), 30000);
  return 1; })()`);
await avaliar(`document.querySelector('.grafico-localizador').scrollIntoView({ block: 'center' }); 1`);
await assentar(600);

const estado = async () => JSON.parse(await avaliar(`(() => { const c = document.querySelector('.grafico-localizador canvas').getBoundingClientRect();
  return JSON.stringify({ l: c.left, t: c.top, w: c.width, h: c.height, sy: scrollY, j: window.__janela }); })()`));
const roda = (x, y, dy) => cdp("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaX: 0, deltaY: dy });
const largura = (j) => j.ate - j.de;
//: O instante que ficou PARADO entre duas janelas (o foco do zoom).
const fixo = (a, b) => (a.de * largura(b) - b.de * largura(a)) / (largura(b) - largura(a));

const c0 = await estado();
// O mouse no meio da curva: o platô fica perto de 45 % da largura.
const x = c0.l + c0.w * 0.45, y = c0.t + c0.h * 0.45;
await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
await foto("roda-loc-antes.png");

// 1. Servidor rápido, roda de alta resolução: oito eventos de −15.
for (let i = 0; i < 8; i++) { await roda(x, y, -15); await espera(16); }
await assentar(800);
const c1 = await estado();
const f1 = largura(c1.j) / largura(c0.j);
confere(f1 > 0.6 && f1 < 0.9, `rajada leve: 120 px de roda ampliam ~0,77× (${f1.toFixed(3)})`);

// 2. Servidor lento e fora de ordem: dez entalhes, um a cada 110 ms.
await avaliar(`window.__atrasar = true; 1`);
const passos = [];
for (let i = 0; i < 10; i++) {
  await roda(x, y, -100);
  await espera(110);
  passos.push(largura((await estado()).j));
}
await assentar(2500);
const c2 = await estado();
await avaliar(`window.__atrasar = false; 1`);
const f2 = largura(c2.j) / largura(c1.j);
const esperado = Math.pow(0.8, 10);
confere(Math.abs(f2 / esperado - 1) < 1e-6,
  `servidor lento: os dez entalhes valem (${f2.toFixed(4)}, esperado ${esperado.toFixed(4)})`);
const voltou = passos.some((w, i) => i && w > passos[i - 1] * (1 + 1e-9));
confere(!voltou, `servidor lento: a janela nunca volta para trás (${passos.map((w) => (w * 1000).toFixed(1)).join(" → ")} ms)`);
const p1 = fixo(c0.j, c1.j), p2 = fixo(c1.j, c2.j);
confere(Math.abs(p1 - p2) < 1e-4 * largura(c0.j),
  `o instante sob o mouse fica sob o mouse (${(p1 * 1000).toFixed(3)} ms e ${(p2 * 1000).toFixed(3)} ms)`);
confere(c2.sy === c0.sy && Math.abs(c2.t - c0.t) < 0.5, `a página não rola (${c0.sy} → ${c2.sy})`);
await foto("roda-loc-depois.png");

terminar();
