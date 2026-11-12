// Teste de NAVEGADOR do digital que PICOTA (Chrome sem janela, via CDP).
//
//   node tests/navegador/picotando.mjs <url-base> <sha> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_picotando_navegador.py`. Confere:
//   - o picotando («ENX») não entra no gráfico digital padrão; o trip entra;
//   - o «+ sinal» dos digitais traz o bloco «picotando», no fim, com a
//     contagem ao lado do nome («· N mudanças»);
//   - marcar e «mostrar na tela» o põe no gráfico como qualquer outro;
//   - o cabeçalho do painel não ganha nada (só o title do «+ sinal»).
import { abrirChrome, P } from "./comum.mjs";

const [BASE, SHA, FOTOS, PORTA = "9957"] = process.argv.slice(2);
const { avaliar, confere, foto, navegar, terminar } =
  await abrirChrome({ porta: PORTA, prefixo: "picotando", fotos: FOTOS });

await navegar(`${BASE}/`, "document.body");
await avaliar(`localStorage.setItem('osclab-tema', 'claro')`);
await navegar(`${BASE}/onda/${SHA}`);

const sinaisDoDigital = async () => JSON.parse(await avaliar(`(() => {
  const pedido = window.osclab.pedido();
  const lista = pedido ? (JSON.parse(pedido.body).paineis || []) : [];
  const p = lista.find(x => x.tipo === 'digital');
  return JSON.stringify(p ? p.sinais : null);
})()`));

const antes = await sinaisDoDigital();
confere(Array.isArray(antes) && antes.length === 1, `o padrão tem só o trip: ${JSON.stringify(antes)}`);

const cabecalho = await avaliar(`document.querySelector('section.grafico.digitais .grafico-titulo')?.textContent || ''`);
confere(!/picot|mudan/i.test(cabecalho), `nada de picotando no cabeçalho: «${cabecalho.slice(0, 80)}»`);

const busca = JSON.parse(await avaliar(`(async () => {
  const b = [...document.querySelectorAll('section.grafico.digitais button')].find(x => x.textContent === '+ sinal');
  b.click(); await ${P(300)};
  const lista = document.querySelector('dialog.busca .achados');
  const filhos = [...lista.children];
  const div = filhos.findIndex(x => x.classList.contains('divisor') && x.classList.contains('picotando'));
  const enx = filhos.findIndex(x => x.querySelector?.('.nome')?.textContent === 'ENX');
  const trip = filhos.findIndex(x => x.querySelector?.('.nome')?.textContent === 'TRIP');
  const conta = enx >= 0 ? filhos[enx].querySelector('.mudancas')?.textContent : null;
  return JSON.stringify({ div, enx, trip, conta, texto: div >= 0 ? filhos[div].textContent : null,
                          titulo: b.title });
})()`));
confere(busca.div >= 0 && busca.enx > busca.div, `bloco «picotando» com o ENX dentro: ${JSON.stringify(busca)}`);
confere(/^· \d+ mudanças$/.test(busca.conta || ""), `a contagem ao lado do nome: «${busca.conta}»`);
confere(busca.trip > busca.div, "o trip está na parte «já na tela», depois do bloco");
confere(/picotam/.test(busca.titulo), "o hover do «+ sinal» conta os picotando");
await foto("busca-picotando.png");

await avaliar(`(async () => {
  const lista = document.querySelector('dialog.busca .achados');
  const item = [...lista.children].find(x => x.querySelector?.('.nome')?.textContent === 'ENX');
  item.querySelector('input[type=checkbox]').click();
  document.querySelector('dialog.busca .aceitar').click();
  await ${P(800)};
})()`);
const depois = await sinaisDoDigital();
confere(Array.isArray(depois) && depois.length === 2, `um clique o põe no gráfico: ${JSON.stringify(depois)}`);
const tiras = await avaliar(`document.querySelectorAll('section.grafico.digitais').length`);
confere(tiras === 1, "o painel digital continua um só");
await foto("com-picotando.png");

await terminar();
