// Teste de NAVEGADOR da janela «? métodos» do painel localizador
// (variante 06, 12/11/2026: as equações desenhadas, lado a lado).
//
//   node tests/navegador/metodos.mjs <url-base> <sha-A> <sha-B> <linha-json> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_metodos_navegador.py`, que sobe o servidor num
// acervo temporário com os dois terminais de uma falta AG. A linha entra
// como DIGITADA: o roteiro acrescenta `fonte: "manual"` e a linha ao corpo
// do pedido da localização — é o que a janela «parâmetros» manda quando se
// digita a linha e se escolhe «usar» na coluna «Digitado».
import { abrirChrome, P } from "./comum.mjs";

const [BASE, SHA_A, SHA_B, LINHA, FOTOS, PORTA = "9956"] = process.argv.slice(2);
const { cdp, avaliar, confere, foto, navegar, terminar } =
  await abrirChrome({ porta: PORTA, prefixo: "metodos", fotos: FOTOS });

await cdp("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
  const anterior = window.fetch.bind(window);
  window.fetch = (url, opcoes) => {
    if (String(url).includes("/localizar") && opcoes && typeof opcoes.body === "string") {
      const corpo = JSON.parse(opcoes.body);
      corpo.fonte = "manual";
      corpo.manual = ${LINHA};
      opcoes = { ...opcoes, body: JSON.stringify(corpo) };
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

// O painel localizador, pelo «+ adicionar gráfico».
await avaliar(`(async () => {
  document.querySelector('.novo-grafico').click(); await ${P(300)};
  [...document.querySelectorAll('.opcao-de-tipo')].find(b => b.textContent === 'localizador de faltas').click();
  await ${P(1500)};
  await window.__esperar(() => /\\d km/.test(document.querySelector('.pl-comprimento')?.textContent || ''), 30000);
  return 1; })()`);

const abrir = `(async () => {
  [...document.querySelectorAll('button.medida')].find(b => b.textContent === '? métodos').click();
  await window.__esperar(() => document.querySelector('dialog.ajuda-metodos-loc[open]'));
  await ${P(200)}; return 1; })()`;
await avaliar(abrir);

const lista = JSON.parse(await avaliar(`JSON.stringify([...document.querySelectorAll('dialog.ajuda-metodos-loc .lista-mt button')]
  .map(b => ({ mt: b.dataset.mt, km: b.querySelector('.km-mt')?.textContent || '', atual: b.classList.contains('atual') })))`));
const metodos = lista.filter((x) => x.mt !== "_fecho");
confere(JSON.stringify(metodos.map((x) => x.mt)) === JSON.stringify(["seqneg", "laco", "takagi", "takagi_i2"]),
  `a lista tem os quatro métodos, na ordem (${lista.map((x) => x.mt).join(", ")})`);
confere(metodos.every((x) => /^-?\d+,\d{2} km$/.test(x.km)), `cada método com o km dele (${metodos.map((x) => x.km).join(" · ")})`);
confere(lista.at(-1)?.mt === "_fecho", "«resultado e trecho» no fim da lista");
confere(lista.filter((x) => x.atual).map((x) => x.mt).join() === "seqneg",
  "abre no método do resultado (a seq. negativa, com dois terminais)");

const direita = () => avaliar(`JSON.stringify((() => {
  const d = document.querySelector('dialog.ajuda-metodos-loc .miolo-mt');
  const m = d.querySelector('.metodo-loc');
  return { mt: m?.dataset.mt || null, titulo: d.querySelector('.titulo-mt')?.textContent || '',
           fracoes: d.querySelectorAll('.eq-frac').length, eqs: d.querySelectorAll('.eq').length,
           esquema: !!d.querySelector('svg.esquema-lt'),
           neste: [...d.querySelectorAll('.pares .neste .eq-n')].map(n => n.textContent),
           texto: d.textContent };
})())`).then(JSON.parse);

const r0 = await direita();
confere(r0.mt === "seqneg" && r0.esquema && r0.eqs >= 2, `à direita a seq. negativa, com a equação e o esquema da linha (${r0.eqs} equações)`);
confere(r0.neste.at(-1) && metodos[0].km.startsWith(r0.neste.at(-1)),
  `«neste registro» é a conta, com o km da lista (${r0.neste.join(" · ")})`);
await foto("metodos-seqneg.png");

for (const { mt } of metodos.slice(1)) {
  await avaliar(`(async () => { document.querySelector('dialog.ajuda-metodos-loc .lista-mt button[data-mt="${mt}"]').click(); await ${P(100)}; return 1; })()`);
  const r = await direita();
  const atual = await avaliar(`document.querySelector('dialog.ajuda-metodos-loc .lista-mt button.atual')?.dataset.mt`);
  confere(r.mt === mt && atual === mt, `clicar em ${mt} troca o da direita (${r.titulo})`);
  confere(r.fracoes >= 1, `${mt}: a equação é desenhada, com fração (${r.fracoes})`);
}
await foto("metodos-takagi-i2.png");

// O laço: a fração não se aninha (Im{Z_laço} / X1L, e Z_laço numa auxiliar).
await avaliar(`document.querySelector('dialog.ajuda-metodos-loc .lista-mt button[data-mt="laco"]').click(); 1`);
const aninhadas = await avaliar(`document.querySelectorAll('dialog.ajuda-metodos-loc .eq-frac .eq-frac').length`);
confere(aninhadas === 0, `nenhuma fração dentro de fração no laço (${aninhadas})`);
await foto("metodos-laco.png");

// O símbolo apontado acende o mesmo símbolo no método inteiro e diz o que é.
const realce = JSON.parse(await avaliar(`(async () => {
  const v = document.querySelector('dialog.ajuda-metodos-loc .eq-v[data-sim="Ilaço"]');
  v.dispatchEvent(new PointerEvent('pointerover', { bubbles: true }));
  await ${P(50)};
  const r = { acesos: document.querySelectorAll('dialog.ajuda-metodos-loc .eq-aceso').length,
              dica: document.querySelector('.eq-dica')?.textContent || '' };
  v.dispatchEvent(new PointerEvent('pointerout', { bubbles: true }));
  await ${P(50)};
  r.depois = document.querySelectorAll('.eq-dica').length;
  return JSON.stringify(r); })()`));
confere(realce.acesos >= 2 && /corrente do laço/.test(realce.dica) && realce.depois === 0,
  `o símbolo acende em todo o método e a dica diz o que é (${realce.acesos} acesos, «${realce.dica}»)`);

await avaliar(`document.querySelector('dialog.ajuda-metodos-loc .lista-mt button[data-mt="_fecho"]').click(); 1`);
const fecho = await direita();
confere(/trecho a patrulhar/.test(fecho.texto) && /platô/i.test(fecho.texto), "«resultado e trecho» mostra de onde sai o número");

// Fecha no clique fora (no fundo do diálogo modal)…
await cdp("Input.dispatchMouseEvent", { type: "mousePressed", x: 6, y: 500, button: "left", clickCount: 1 });
await cdp("Input.dispatchMouseEvent", { type: "mouseReleased", x: 6, y: 500, button: "left", clickCount: 1 });
await avaliar(P(150));
confere(!(await avaliar(`!!document.querySelector('dialog.ajuda-metodos-loc')`)), "fecha no clique fora");
// …e no Esc.
await avaliar(abrir);
await cdp("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
await cdp("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
await avaliar(P(150));
confere(!(await avaliar(`!!document.querySelector('dialog.ajuda-metodos-loc')`)), "fecha no Esc");

// O escuro, só para a foto.
await avaliar(`document.documentElement.dataset.tema = 'escuro'; 1`);
await avaliar(abrir);
await foto("metodos-escuro.png");

terminar();
