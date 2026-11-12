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
import { abrirChrome, P } from "./comum.mjs";

const [BASE, TRAFO, ALIM, FOTOS, PORTA = "9954"] = process.argv.slice(2);
const W = 1600, H = 1000;
const { cdp, avaliar, confere, foto, navegar, terminar, espera, assentar } =
  await abrirChrome({ porta: PORTA, prefixo: "paineis", fotos: FOTOS, largura: W, altura: H });
const roda = (x, y, dy) => cdp("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaX: 0, deltaY: dy });
const ir = async (sha) => {
  await navegar(`${BASE}/`, "document.body");
  await avaliar(`localStorage.setItem('osclab-tema', 'claro'); localStorage.setItem('osclab:catalogo:visao', 'avancado')`);
  await navegar(`${BASE}/onda/${sha}`);
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
    await assentar(300);
    await foto(`${nome}-diferencial-sem-ajustes.png`);
  }
}

// --- 2. a roda no localizador -----------------------------------------------
await ir(ALIM);
await avaliar(AJUDANTES);
await avaliar("__criar('localizador de faltas')");
await avaliar(`document.querySelector('.grafico-localizador').scrollIntoView({ block: 'center' })`);
await assentar(500);
const caixa = async () => JSON.parse(await avaliar(`(() => { const c = document.querySelector('.grafico-localizador canvas').getBoundingClientRect();
  return JSON.stringify({ l: c.left, t: c.top, w: c.width, sy: scrollY, j: window.__janela }); })()`));
let c = await caixa();
const largura = (j) => j.ate - j.de;
const dentro = [c.l + c.w * 0.45, c.t + 80];
await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: dentro[0], y: dentro[1] });
// Um gesto LEVE: oito eventos de 15 px, como manda uma roda de alta resolução.
for (let i = 0; i < 8; i++) { await roda(dentro[0], dentro[1], -15); await espera(16); }
await assentar(900);
let d = await caixa();
const fator = largura(d.j) / largura(c.j);
confere(fator > 0.6 && fator < 0.9, `localizador: 120 px de roda ampliam ~0,77× (${fator.toFixed(3)})`);
confere(d.sy === c.sy, "localizador: a roda dentro da moldura não rola a página");
// Fora da moldura (a margem dos rótulos): a página rola, a janela não muda.
c = await caixa();
await roda(c.l + 20, c.t + 80, -100);   // para CIMA: o localizador é o último, a página já está no fim
await assentar(700);
d = await caixa();
confere(d.sy !== c.sy && largura(d.j) === largura(c.j), `localizador: fora da moldura a roda rola a página (${c.sy} → ${d.sy})`);
// No piso, girar mais não anda de lado.
await avaliar(`document.querySelector('.grafico-localizador').scrollIntoView({ block: 'center' })`);
await assentar(400);
c = await caixa();
const p = [c.l + c.w * 0.3, c.t + 80];
for (let g = 0; g < 4; g++) {
  for (let i = 0; i < 6; i++) { await roda(p[0], p[1], -100); await espera(10); }
  await assentar(500);
}
const piso = (await caixa()).j;
for (let i = 0; i < 3; i++) { await roda(p[0], p[1], -100); await assentar(400); }
await assentar(500);
const depois = (await caixa()).j;
confere(Math.abs(depois.de - piso.de) < 1e-9 && Math.abs(depois.ate - piso.ate) < 1e-9,
  `localizador: no piso a roda não anda de lado (${piso.de.toFixed(5)} → ${depois.de.toFixed(5)})`);
await foto("localizador-no-piso.png");

terminar();
