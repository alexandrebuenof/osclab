// Teste de NAVEGADOR do CLIQUE DUPLO no painel localizador (12/11/2026:
// «ao clicar duas vezes no gráfico de localizador de faltas ele dá um zoom
// automático para verificar mais de perto a região da falta — mas o zoom
// seria em todos os gráficos»).
//
//   node tests/navegador/zoom-falta.mjs <url-base> <sha-A> <sha-B> <linha-json> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_zoom_falta_navegador.py`: dois terminais de uma
// falta AG do mini-EMTP, a linha DIGITADA, o painel localizador. Confere:
//
//   * o duplo clique põe a janela da ABA (a de todos os gráficos) na região
//     da falta que o SERVIDOR mandou (`painel.zoom_falta`);
//   * nenhum cursor aparece e a seleção não muda com os dois cliques;
//   * o segundo duplo clique volta à janela de antes.
import { abrirChrome, P } from "./comum.mjs";

const [BASE, SHA_A, SHA_B, LINHA, FOTOS, PORTA = "9958"] = process.argv.slice(2);
const { cdp, avaliar, confere, foto, navegar, terminar, assentar } =
  await abrirChrome({ porta: PORTA, prefixo: "zoom-falta", fotos: FOTOS });

// A linha digitada vai em todo pedido da localização, e a região da falta
// que o servidor mandou fica guardada para o roteiro comparar.
await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
  const anterior = window.fetch.bind(window);
  window.fetch = (url, opcoes) => {
    if (String(url).includes("/localizar") && opcoes && typeof opcoes.body === "string") {
      const corpo = JSON.parse(opcoes.body);
      corpo.fonte = "manual";
      corpo.manual = ${LINHA};
      opcoes = { ...opcoes, body: JSON.stringify(corpo) };
      return anterior(url, opcoes).then((r) => {
        r.clone().json().then((j) => { if (j.painel) window.__zoomFalta = j.painel.zoom_falta; })
          .catch(() => {});
        return r;
      });
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
  await window.__esperar(() => window.__zoomFalta, 30000);
  return 1; })()`);
await avaliar(`document.querySelector('.grafico-localizador').scrollIntoView({ block: 'center' }); 1`);
await assentar(600);

const estado = async () => JSON.parse(await avaliar(`(() => {
  const c = document.querySelector('.grafico-localizador canvas').getBoundingClientRect();
  return JSON.stringify({ l: c.left, t: c.top, w: c.width, h: c.height, j: window.__janela,
    z: window.__zoomFalta, cur: window.__cursores || [null, null],
    tit: document.querySelector('.grafico-localizador canvas').title,
    esc: document.querySelectorAll('.legenda li.escolhido').length,
    graficos: document.querySelectorAll('section.grafico').length }); })()`));
const duplo = async (x, y) => {
  for (const clickCount of [1, 2]) {
    await cdp("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount });
    await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount });
  }
};
const igual = (a, b) => Math.abs(a - b) < 1e-9;

const c0 = await estado();
confere(c0.z && c0.z.de !== null && c0.z.de < c0.z.ate,
  `o servidor mandou a região da falta (${c0.z && (c0.z.de * 1000).toFixed(1)} a ${c0.z && (c0.z.ate * 1000).toFixed(1)} ms)`);
confere(c0.z.ate - c0.z.de < c0.j.ate - c0.j.de, "a região é menor que a janela aberta: é zoom de verdade");
confere(/Clique duplo/.test(c0.tit), `o desenho diz o gesto no title («${c0.tit.slice(0, 50)}…»)`);
confere(c0.graficos >= 3, `há outros gráficos além do localizador (${c0.graficos})`);
await foto("zoom-falta-antes.png");

// Em cima da curva, onde o clique simples escolheria um método.
const x = c0.l + c0.w * 0.45, y = c0.t + c0.h * 0.45;
await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
await duplo(x, y);
await assentar(1200);
const c1 = await estado();
confere(igual(c1.j.de, c0.z.de) && igual(c1.j.ate, c0.z.ate),
  `duplo clique: a janela da aba é a da falta (${(c1.j.de * 1000).toFixed(1)} a ${(c1.j.ate * 1000).toFixed(1)} ms)`);
confere(c1.cur[0] === null && c1.cur[1] === null, "nenhum cursor posto pelos dois cliques");
confere(c1.esc === c0.esc, `a seleção não mudou (${c0.esc} → ${c1.esc})`);
await foto("zoom-falta-depois.png");

// De novo: volta à janela de antes.
const c1b = await estado();
await duplo(c1b.l + c1b.w * 0.45, c1b.t + c1b.h * 0.45);
await assentar(1200);
const c2 = await estado();
confere(igual(c2.j.de, c0.j.de) && igual(c2.j.ate, c0.j.ate),
  `segundo duplo clique volta (${(c2.j.de * 1000).toFixed(1)} a ${(c2.j.ate * 1000).toFixed(1)} ms)`);
confere(c2.cur[0] === null && c2.cur[1] === null, "nenhum cursor depois do segundo duplo clique");

terminar();
