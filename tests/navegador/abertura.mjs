// Teste de NAVEGADOR da barra de progresso da ABERTURA (14/11/2026).
//
//   node tests/navegador/abertura.mjs <url-base> <rapido> <lento1> <lento2> <lento3> <fotos> [porta-cdp]
//
// Roda dentro de `tests/test_abertura_navegador.py`, com o servidor ATRASANDO
// de propósito o diagnóstico bruto × filtrado dos registros «LENTO» (passos
// de 0,2 s que anunciam o progresso, como a conta de verdade). Confere:
//   - o registro RÁPIDO abre sem a barra aparecer nunca (nada pisca);
//   - o LENTO mostra a barra, com o nome da etapa, e ela AVANÇA (mais de
//     dois valores, sempre crescendo) e SOME quando o gráfico chega;
//   - «+ adicionar oscilografia» com um registro lento mostra a barra na
//     tira dos IEDs, sem apagar os gráficos, e ela some quando ele entra;
//   - fotos no tema claro e no escuro.
import { abrirChrome } from "./comum.mjs";

const [BASE, RAPIDO, LENTO1, LENTO2, LENTO3, FOTOS, PORTA = "9961"] = process.argv.slice(2);
const { cdp, avaliar, confere, foto, navegar, espera, ocioso, terminar } =
  await abrirChrome({ porta: PORTA, prefixo: "abertura", fotos: FOTOS });

// Em TODO documento: anota cada estado da barra que aparecer (porcentagem e
// etapa), para conferir depois que ela existiu, andou e sumiu.
await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
  window.__barra = { vista: false, pcts: [], etapas: [] };
  const olhar = () => {
    const b = document.querySelector('.abertura');
    if (!b) return;
    window.__barra.vista = true;
    const pct = parseInt(b.querySelector('.abertura-pct')?.textContent || '', 10);
    const et = b.querySelector('.abertura-etapa')?.textContent || '';
    const p = window.__barra.pcts;
    if (Number.isFinite(pct) && p[p.length - 1] !== pct) p.push(pct);
    if (et && window.__barra.etapas[window.__barra.etapas.length - 1] !== et) window.__barra.etapas.push(et);
  };
  new MutationObserver(olhar).observe(document, { subtree: true, childList: true, characterData: true, attributes: true });
})()` });

const barra = async () => JSON.parse(await avaliar(`JSON.stringify(window.__barra || null)`));
const crescente = (xs) => xs.every((x, i) => i === 0 || x >= xs[i - 1]);

await navegar(`${BASE}/`, "document.body");
await avaliar(`localStorage.setItem('osclab-tema', 'claro')`);

// 1. Rápido: a barra nunca aparece.
await navegar(`${BASE}/onda/${RAPIDO}`);
const r = await barra();
confere(r && !r.vista, `registro rápido: a barra não aparece (${JSON.stringify(r)})`);
confere(await avaliar(`!!document.querySelector('section.grafico')`), "registro rápido: o gráfico está na tela");

// 2. Lento, tema claro: aparece, anda, some.
const abrirLento = async (sha, nome) => {
  await cdp("Page.navigate", { url: `${BASE}/onda/${sha}` });
  const apareceu = await avaliar(`(async () => !!(await window.__esperar(() => document.querySelector('.abertura'), 20000)))()`);
  confere(apareceu, `${nome}: a barra aparece`);
  await espera(900);
  await foto(`abertura-${nome}.png`);
  const meio = JSON.parse(await avaliar(`JSON.stringify({
    etapa: document.querySelector('.abertura-etapa')?.textContent || '',
    pct: document.querySelector('.abertura-pct')?.textContent || '',
    largura: document.querySelector('.abertura-feito')?.style.width || '',
    vazio: !!document.querySelector('#graficos > .abertura.vazio'),
    carregando: /Carregando/.test(document.getElementById('graficos').textContent),
  })`));
  confere(meio.etapa.length > 0 && /%$/.test(meio.pct), `${nome}: etapa e porcentagem ao lado (${JSON.stringify(meio)})`);
  confere(meio.vazio && !meio.carregando, `${nome}: a barra toma o lugar do «Carregando…»`);
  await avaliar(`(async () => { await window.__esperar(() => document.querySelector('section.grafico'), 30000); await window.__ocioso(); return 1; })()`);
  const b = await barra();
  confere(b.pcts.length >= 3 && crescente(b.pcts), `${nome}: a barra AVANÇA (${b.pcts.join(" → ")})`);
  confere(b.etapas.includes("bruto × filtrado"), `${nome}: diz a etapa (${b.etapas.join(" · ")})`);
  confere(await avaliar(`!document.querySelector('.abertura')`), `${nome}: a barra some ao terminar`);
  confere(await avaliar(`!!document.querySelector('section.grafico')`), `${nome}: o gráfico chegou`);
};
await abrirLento(LENTO1, "claro");

// 3. Lento, tema escuro.
await avaliar(`localStorage.setItem('osclab-tema', 'escuro')`);
await abrirLento(LENTO2, "escuro");

// 4. «+ adicionar oscilografia» com um registro lento: a barra vai na tira.
await avaliar(`window.__barra = { vista: false, pcts: [], etapas: [] }`);
await avaliar(`(async () => {
  document.querySelector('.mais-oscilografia').click();
  const b = await window.__esperar(() => [...document.querySelectorAll('.opcao-de-registro')]
    .find(x => x.title && x.title.includes('LENTO3')), 10000);
  b.click();
  return 1;
})()`);
const naTira = await avaliar(`(async () => !!(await window.__esperar(() => document.querySelector('#tira-dos-ieds .abertura'), 20000)))()`);
confere(naTira, "+ oscilografia: a barra aparece na tira dos IEDs");
await espera(700);
await foto("abertura-segundo-registro-escuro.png");
confere(await avaliar(`document.querySelectorAll('section.grafico').length > 0`),
  "+ oscilografia: os gráficos continuam na tela enquanto o outro abre");
await avaliar(`(async () => { await window.__esperar(() => !document.querySelector('.abertura') && document.querySelectorAll('.linha-do-ied').length === 2, 30000); await window.__ocioso(); return 1; })()`);
const t = await barra();
confere(t.pcts.length >= 2 && crescente(t.pcts), `+ oscilografia: a barra avança (${t.pcts.join(" → ")})`);
confere(await avaliar(`!document.querySelector('.abertura') && document.querySelectorAll('.linha-do-ied').length === 2`),
  "+ oscilografia: a barra some e o segundo IED entra");

// 5. Um gesto sobre registro aberto não mostra barra (o servidor não abre abertura).
await avaliar(`window.__barra = { vista: false, pcts: [], etapas: [] }`);
await avaliar(`localStorage.setItem('osclab-tema', 'claro')`);
await navegar(`${BASE}/onda/${LENTO1}`);
confere(!(await barra()).vista, "reabrir um registro já aberto: sem barra");
await ocioso();
terminar();
