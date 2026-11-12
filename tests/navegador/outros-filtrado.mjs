// Teste de NAVEGADOR: canal de «Outros sinais» num registro JÁ FILTRADO
// (Chrome sem janela, via CDP).
//
//   node tests/navegador/outros-filtrado.mjs <url-base> <sha> <pasta-das-fotos> [porta-cdp]
//
// Num `.CEV` o próprio canal mora na coluna do filtrado. O cartão de um canal
// sem fase (`V1MEM`, `VS1`, `FREQ`) nascia com o interruptor apagado e mostrava
// onda, RMS e DC todos riscados — não havia como pôr o canal na tela
// (12/11/2026). Confere que a folha «onda» existe e que o canal entra.
import { abrirChrome, P } from "./comum.mjs";

const [BASE, SHA, FOTOS, PORTA = "9958"] = process.argv.slice(2);
const { avaliar, confere, foto, navegar, terminar } =
  await abrirChrome({ porta: PORTA, prefixo: "outros-filtrado", fotos: FOTOS });

await navegar(`${BASE}/`, "document.body");
await avaliar(`localStorage.setItem('osclab-tema', 'claro')`);
await navegar(`${BASE}/onda/${SHA}`);

const sinaisDoPrimeiro = async () => JSON.parse(await avaliar(`(() => {
  const pedido = window.osclab.pedido();
  const lista = pedido ? (JSON.parse(pedido.body).paineis || []) : [];
  const p = lista.find(x => x.tipo !== 'digital');
  return JSON.stringify(p ? p.sinais : null);
})()`));
const antes = await sinaisDoPrimeiro();

const cartao = JSON.parse(await avaliar(`(async () => {
  const b = [...document.querySelectorAll('section.grafico button')].find(x => x.textContent.trim() === '+ sinal');
  b.click(); await ${P(400)};
  // «Outros sinais» nasce recolhido: abre o bloco.
  const titulo = [...document.querySelectorAll('dialog .titulo-do-bloco')]
    .find(x => x.textContent.trim() === 'Outros sinais');
  if (titulo && !document.querySelector('dialog .cartao-do-sinal .nome-do-cartao')?.textContent.startsWith('FREQ')) {
    titulo.click(); await ${P(300)};
  }
  const c = [...document.querySelectorAll('dialog .cartao-do-sinal')]
    .find(x => (x.querySelector('.nome-do-cartao')?.textContent || '').startsWith('FREQ'));
  if (!c) return JSON.stringify({ achou: false });
  if (!c.classList.contains('aberto')) { c.querySelector('.topo-do-cartao').click(); await ${P(200)}; }
  const c2 = [...document.querySelectorAll('dialog .cartao-do-sinal')]
    .find(x => (x.querySelector('.nome-do-cartao')?.textContent || '').startsWith('FREQ'));
  const folhas = [...c2.querySelectorAll('.folha-do-cartao')].map(f => ({
    rotulo: f.querySelector('.rotulo-da-folha')?.textContent, apagada: f.classList.contains('apagada') }));
  const onda = [...c2.querySelectorAll('.folha-do-cartao')]
    .find(f => f.querySelector('.rotulo-da-folha')?.textContent === 'onda' && !f.classList.contains('apagada'));
  const caixa = onda?.querySelector('input[type=checkbox]');
  if (caixa) caixa.click();
  return JSON.stringify({ achou: true, folhas, caixa: !!caixa });
})()`));
confere(cartao.achou, "o cartão do FREQ está no «+ sinal»");
confere(cartao.caixa, `a folha «onda» existe e se marca: ${JSON.stringify(cartao.folhas)}`);
await foto("cartao-outros.png");

await avaliar(`(async () => { document.querySelector('dialog .aceitar').click(); await ${P(800)}; })()`);
const depois = await sinaisDoPrimeiro();
confere(Array.isArray(depois) && depois.length === (antes || []).length + 1,
        `o canal entrou no gráfico: ${JSON.stringify(antes)} → ${JSON.stringify(depois)}`);
await foto("com-outros.png");

await terminar();
