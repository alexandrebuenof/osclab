// Teste de NAVEGADOR: a energia do «+ sinal» é pedida quando ele ABRE, não ao
// abrir o registro (14/11/2026).
//
//   node tests/navegador/energia.mjs <url-base> <sha> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_energia_navegador.py`, com o servidor ATRASANDO
// de propósito a conta da energia (passos de 0,2 s que anunciam o progresso,
// como a conta de verdade faz linha a linha). Confere:
//   - abrir o registro não pede a energia;
//   - o «+ sinal» abre NA HORA, sem as barrinhas, e com a barra de progresso
//     dentro dele, que anda e some;
//   - quando a conta chega, as barrinhas entram sem perder a busca digitada;
//   - fechar e abrir de novo não pede a energia outra vez.
import { abrirChrome, P } from "./comum.mjs";

const [BASE, SHA, FOTOS, PORTA = "9963"] = process.argv.slice(2);
const { cdp, avaliar, confere, foto, navegar, terminar } =
  await abrirChrome({ porta: PORTA, prefixo: "energia", fotos: FOTOS });

// Em TODO documento: anota os pedidos de energia e cada estado da barra.
await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
  window.__energia = { pedidos: 0, pcts: [], etapas: [] };
  const original = window.fetch;
  window.fetch = (...a) => {
    if (String(a[0]).includes('/energia')) window.__energia.pedidos++;
    return original(...a);
  };
  const olhar = () => {
    const b = document.querySelector('dialog .abertura-no-catalogo');
    if (!b) return;
    const pct = parseInt(b.querySelector('.abertura-pct')?.textContent || '', 10);
    const et = b.querySelector('.abertura-etapa')?.textContent || '';
    const e = window.__energia;
    if (Number.isFinite(pct) && e.pcts[e.pcts.length - 1] !== pct) e.pcts.push(pct);
    if (et && e.etapas[e.etapas.length - 1] !== et) e.etapas.push(et);
  };
  new MutationObserver(olhar).observe(document, { subtree: true, childList: true, characterData: true, attributes: true });
})()` });
const estado = async () => JSON.parse(await avaliar(`JSON.stringify(window.__energia)`));
const crescente = (xs) => xs.every((x, i) => i === 0 || x >= xs[i - 1]);

await navegar(`${BASE}/`, "document.body");
await avaliar(`localStorage.setItem('osclab-tema', 'claro')`);
await navegar(`${BASE}/onda/${SHA}`);
confere((await estado()).pedidos === 0, "abrir o registro não pede a energia");

const abrir = `(() => {
  const b = [...document.querySelectorAll('section.grafico button')].find(x => x.textContent.trim() === '+ sinal');
  b.click();
  return !!document.querySelector('dialog.busca.catalogo[open]');
})()`;
confere(await avaliar(abrir), "o «+ sinal» abre na hora");
const logo = JSON.parse(await avaliar(`JSON.stringify({
  cartoes: document.querySelectorAll('dialog .cartao-do-sinal').length,
  barras: document.querySelectorAll('dialog .barra-de-energia').length })`));
confere(logo.cartoes > 0 && logo.barras === 0,
        `a lista já está lá, sem as barrinhas: ${JSON.stringify(logo)}`);

// A barra de progresso aparece dentro do catálogo; digita-se uma busca no meio.
const apareceu = await avaliar(`(async () => !!(await window.__esperar(
  () => document.querySelector('dialog .abertura-no-catalogo'), 10000)))()`);
confere(apareceu, "a barra de progresso aparece dentro do «+ sinal»");
await new Promise((r) => setTimeout(r, 700));
await foto("energia-progresso.png");
await avaliar(`(() => { const c = document.querySelector('dialog .cabeca input[type=search]');
  c.value = 'IAW'; c.dispatchEvent(new Event('input')); return 1; })()`);
const nomes = `[...document.querySelectorAll('dialog .cartao-do-sinal .nome-do-cartao')].map(x => x.textContent)`;
const filtrados = JSON.parse(await avaliar(`JSON.stringify(${nomes})`));
confere((await avaliar(`!!document.querySelector('dialog .abertura-no-catalogo')`)),
        "a busca foi digitada com a energia ainda em conta");

const chegou = await avaliar(`(async () => !!(await window.__esperar(
  () => document.querySelector('dialog .barra-de-energia') && !document.querySelector('dialog .abertura-no-catalogo'),
  20000)))()`);
confere(chegou, "as barrinhas entram e a barra de progresso some");
const depois = JSON.parse(await avaliar(`JSON.stringify({
  busca: document.querySelector('dialog .cabeca input[type=search]').value,
  nomes: ${nomes},
  barras: document.querySelectorAll('dialog .barra-de-energia').length })`));
confere(depois.busca === "IAW" && depois.nomes.length > 0
        && JSON.stringify(depois.nomes) === JSON.stringify(filtrados),
        `a busca continua valendo depois da energia: ${JSON.stringify(filtrados)} → ${JSON.stringify(depois)}`);
await foto("energia-pronta.png");
const e = await estado();
confere(e.pcts.length > 2 && crescente(e.pcts), `a barra anda e só cresce: ${JSON.stringify(e.pcts)}`);
confere(e.etapas.includes("energia dos sinais"), `a barra diz o que está medindo: ${JSON.stringify(e.etapas)}`);
confere(e.pedidos === 1, `um pedido de energia (${e.pedidos})`);

// Fechar e abrir de novo: as barrinhas já estão, e nada é pedido.
await avaliar(`(async () => { document.querySelector('dialog.busca.catalogo .fechar').click(); await ${P(200)}; return 1; })()`);
await avaliar(abrir);
const reaberto = JSON.parse(await avaliar(`(async () => { await ${P(300)}; return JSON.stringify({
  barras: document.querySelectorAll('dialog .barra-de-energia').length,
  progresso: !!document.querySelector('dialog .abertura-no-catalogo') }); })()`));
confere(reaberto.barras > 0 && !reaberto.progresso,
        `reaberto, as barrinhas estão lá sem barra de progresso: ${JSON.stringify(reaberto)}`);
confere((await estado()).pedidos === 1, "reabrir não pede a energia de novo");

await terminar();
