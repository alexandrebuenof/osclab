// Teste de NAVEGADOR da relação de TC/TP digitada (Chrome sem janela, via CDP).
//
//   node tests/navegador/relacoes.mjs <url-base> <sha-alimentador> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_relacoes_navegador.py`, num acervo temporário com
// o alimentador de `tests/casos_calculadora.py` (o «Current IN» dele NÃO
// declara relação de TC). Os três lugares onde se digita a relação, clicados
// como o usuário clicaria, e conferidos contra o que o SERVIDOR gravou:
//   - o cartão do grupo em «editar grupos» (vale para as três fases);
//   - o campo ⚠ da calculadora (grava NO REGISTRO, e o ⚠ sai);
//   - a coluna «relação» da tela «canais» (vence o grupo; «gravar»);
//   - e a legenda: em primário, o canal convertido pela digitada diz
//     «digitado» no lugar do aviso de sem relação.
import { abrirChrome, P } from "./comum.mjs";

const [BASE, ALIM, FOTOS, PORTA = "9955"] = process.argv.slice(2);
const { avaliar, confere, foto, navegar, terminar, assentar } =
  await abrirChrome({ porta: PORTA, prefixo: "relacoes", fotos: FOTOS });
const ir = async () => {
  await navegar(`${BASE}/`, "document.body");
  await avaliar(`localStorage.setItem('osclab-tema', 'claro'); localStorage.setItem('osclab:catalogo:visao', 'avancado')`);
  await navegar(`${BASE}/onda/${ALIM}`);
};
const AJUDANTES = `
  window.__botao = (texto, raiz) => [...(raiz || document).querySelectorAll('button')]
    .find(b => b.offsetParent && b.textContent.trim().includes(texto));
  window.__catalogo = async () => { __botao('+ sinal', document.querySelector('section.grafico')).click(); await ${P(600)}; };
  window.__digitar = async (campo, texto) => { campo.focus(); campo.value = texto;
    campo.dispatchEvent(new Event('change', { bubbles: true })); await ${P(800)}; };
  window.__relacoes = async () => (await (await fetch('/api/onda/${ALIM}')).json()).relacoes;
  // A janela de CIMA: «editar grupos» e «canais» abrem por cima do catálogo,
  // que continua aberto (e é o primeiro \`dialog[open]\` do documento).
  window.__dialogo = () => [...document.querySelectorAll('dialog[open]')].pop();
  window.__fecharDialogos = () => document.querySelectorAll('dialog[open]').forEach(d => d.close());
  1`;
// O índice do «Current IN» no arquivo (o servidor é quem sabe).
const indiceDe = async (nome) => avaliar(`(async () => { const d = await (await fetch('/api/onda/${ALIM}')).json();
  const x = (d.catalogo || []).find(c => c.canal >= 0 && (c.nome === ${JSON.stringify(nome)} || c.linha === ${JSON.stringify(nome)}));
  return x ? x.canal : null; })()`);

await ir();
await avaliar(AJUDANTES);
const IN = await indiceDe("Current IN");
confere(Number.isInteger(IN), `o alimentador tem o «Current IN» (canal ${IN})`);
const antes = await avaliar("__relacoes()");
confere(antes && antes.canais && antes.canais[String(IN)]?.origem === "",
  `o «Current IN» começa sem relação (${JSON.stringify(antes?.canais?.[String(IN)])})`);

// --- 1. o cartão do grupo ----------------------------------------------------
await avaliar("__catalogo()");
await avaliar(`(async () => { __botao('editar grupos').click(); await ${P(600)}; })()`);
const cartao = await avaliar(`(() => { const d = __dialogo();
  const c = d && [...d.querySelectorAll('input[aria-label="RTC"]')];
  return c ? c.map(x => [x.value, x.placeholder]) : null; })()`);
confere(Array.isArray(cartao) && cartao.length >= 1, `«editar grupos» tem o campo RTC no cartão do grupo de corrente (${JSON.stringify(cartao)})`);
// O placeholder é a relação que vale: cortado («13800:1»), lê-se errado.
const cortados = await avaliar(`(() => { const c = document.createElement('canvas').getContext('2d');
  return [...__dialogo().querySelectorAll('input.relacao-digitavel')].filter(x => {
    const s = getComputedStyle(x); c.font = s.font;
    const util = x.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
    return c.measureText(x.placeholder).width > util + 0.5; }).map(x => x.placeholder); })()`);
confere(Array.isArray(cortados) && cortados.length === 0, `nenhuma relação cortada no cartão do grupo (${JSON.stringify(cortados)})`);
await foto("1-grupos-antes.png");
await avaliar(`(async () => { const c = __dialogo().querySelector('input[aria-label="RTC"]');
  await __digitar(c, '1000/1'); })()`);
let r = await avaliar("__relacoes()");
const grupoGravado = Object.values(r?.grupos || {});
confere(grupoGravado.includes("1000"), `o servidor gravou a RTC do grupo (${JSON.stringify(r?.grupos)})`);
const fasesDigitadas = Object.entries(r?.canais || {}).filter(([, v]) => v.origem === "digitado").map(([k]) => k);
confere(fasesDigitadas.length >= 3, `as três fases passam a «digitado» (${fasesDigitadas})`);
confere(r?.canais?.[String(IN)]?.origem === "digitado" && r.canais[String(IN)].em_uso === "1000",
  `o neutro sem relação no arquivo herda a do grupo (${JSON.stringify(r?.canais?.[String(IN)])})`);
// reaberta a página, o cartão mostra o que ficou gravado
await ir(); await avaliar(AJUDANTES);
await avaliar("__catalogo()");
await avaliar(`(async () => { __botao('editar grupos').click(); await ${P(600)}; })()`);
const reaberto = await avaliar(`__dialogo().querySelector('input[aria-label="RTC"]')?.value`);
confere(reaberto === "1000", `reaberto, o cartão traz a RTC gravada («${reaberto}»)`);
await foto("2-grupos-gravado.png");
// apagar volta ao arquivo
await avaliar(`(async () => { await __digitar(__dialogo().querySelector('input[aria-label="RTC"]'), ''); })()`);
r = await avaliar("__relacoes()");
confere(Object.keys(r?.grupos || {}).length === 0 && r?.canais?.[String(IN)]?.origem === "",
  `campo vazio apaga a do grupo e o neutro volta a não ter relação (${JSON.stringify(r?.grupos)})`);
await avaliar("__fecharDialogos()");

// --- 2. a calculadora ----------------------------------------------------------
await ir(); await avaliar(AJUDANTES);
await avaliar(`(async () => { __botao('calculadora').click(); await ${P(900)};
  document.querySelector('.calc-dom.onda')?.click(); await ${P(200)};
  const e = document.querySelector('.calc-expr'); const t = '[Current IN] - ([IA] + [IB] + [IC])';
  e.value = t; e.selectionStart = e.selectionEnd = t.length; e.dispatchEvent(new Event('input')); await ${P(1400)}; })()`);
const campoCalc = await avaliar(`(() => { const f = document.querySelector('.calc-param.relacao');
  return f ? { alerta: !!f.querySelector('.calc-alerta'), valor: f.querySelector('input').value,
               ph: f.querySelector('input').placeholder } : null; })()`);
confere(campoCalc && campoCalc.alerta && campoCalc.valor === "" && campoCalc.ph === "RTC",
  `a calculadora pede a RTC do neutro, com ⚠ (${JSON.stringify(campoCalc)})`);
await foto("3-calculadora-sem-tc.png");
await avaliar(`(async () => { const c = document.querySelector('.calc-param.relacao input');
  c.value = '100/1'; c.dispatchEvent(new Event('change')); await ${P(1500)}; })()`);
r = await avaliar("__relacoes()");
confere(r?.canais?.[String(IN)]?.no_canal === "100" && r.canais[String(IN)].origem === "digitado",
  `a RTC da calculadora foi gravada NO CANAL (${JSON.stringify(r?.canais?.[String(IN)])})`);
const depoisCalc = await avaliar(`(async () => { await __esperar(() => document.querySelector('.calc-param.relacao input')?.value, 5000);
  const f = document.querySelector('.calc-param.relacao');
  return f ? { alerta: !!f.querySelector('.calc-alerta'), valor: f.querySelector('input').value } : null; })()`);
confere(depoisCalc && !depoisCalc.alerta && depoisCalc.valor === "100",
  `depois de gravar, o campo fica preenchido e sem ⚠ (${JSON.stringify(depoisCalc)})`);
await foto("4-calculadora-digitado.png");

// --- 3. a tela «canais» ------------------------------------------------------------
await ir(); await avaliar(AJUDANTES);
await avaliar("__catalogo()");
await avaliar(`(async () => { __botao('canais').click(); await ${P(600)}; })()`);
const linhaIN = await avaliar(`(() => { const l = [...__dialogo().querySelectorAll('.linha-do-canal')]
  .find(x => x.textContent.includes('Current IN')); const c = l?.querySelector('.col-relacao input');
  return c ? { valor: c.value, ph: c.placeholder } : null; })()`);
confere(linhaIN && linhaIN.valor === "100", `«canais» mostra a RTC digitada do neutro (${JSON.stringify(linhaIN)})`);
await avaliar(`(async () => { const l = [...__dialogo().querySelectorAll('.linha-do-canal')]
  .find(x => x.textContent.includes('Current IN')); const c = l.querySelector('.col-relacao input');
  c.value = '200/1'; c.dispatchEvent(new Event('change')); await ${P(200)};
  })()`);
await foto("5-canais.png");
await avaliar(`(async () => {
  __botao('gravar as correções', __dialogo()).click(); await ${P(1500)}; })()`);
r = await avaliar("__relacoes()");
confere(r?.canais?.[String(IN)]?.no_canal === "200", `«gravar as correções» grava a RTC do canal (${JSON.stringify(r?.canais?.[String(IN)])})`);

// --- 4. a legenda em primário ---------------------------------------------------------
await ir(); await avaliar(AJUDANTES);
await avaliar(`(async () => { document.querySelector('#lado button[data-lado="primario"]').click(); await ${P(1200)}; })()`);
const legenda = await avaliar(`(() => { const itens = [...document.querySelectorAll('.legenda *')]
  .filter(x => x.children.length === 0 && x.textContent.trim() === 'digitado');
  const semRelacao = [...document.querySelectorAll('.legenda .sem-relacao')].map(x => x.parentElement.textContent);
  return { digitado: itens.length, semRelacao }; })()`);
const temIN = await avaliar(`[...document.querySelectorAll('.legenda')].some(x => x.textContent.includes('Current IN'))`);
if (temIN) {
  confere(legenda.digitado >= 1 && !legenda.semRelacao.some((t) => t.includes("Current IN")),
    `em primário o neutro diz «digitado», não «sem relação» (${JSON.stringify(legenda)})`);
} else {
  confere(false, "o «Current IN» devia estar no gráfico padrão (o residual solto entra na trinca)");
}
await foto("6-legenda-primario.png");

terminar();
