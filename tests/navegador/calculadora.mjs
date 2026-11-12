// Teste de NAVEGADOR da gaveta da calculadora (Chrome sem janela, via CDP).
//
//   node tests/navegador/calculadora.mjs <url-base> <sha-trafo> <sha-alimentador> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_calculadora_navegador.py` (que sobe o servidor
// num acervo temporário) e, à mão, contra qualquer servidor com os dois
// registros de `tests/casos_calculadora.py`. Sai com código 1 se alguma
// conferência falhar; as fotos, nos dois temas, ficam na pasta dada.
//
// O que se confere é o que nome comprido de canal poderia estragar:
//   - a fileira tem 8 teclas IGUAIS com rótulo padronizado; com duas trincas
//     de corrente, o seletor «G1 · TC BUC 69kV:I *» fica acima, e a tecla
//     insere o nome COMPLETO do canal do grupo escolhido;
//   - o visor quebra a expressão, cresce até um teto e rola; o valor do
//     cursor fica dentro da gaveta;
//   - a lista «[ ]» corta o nome pela largura medida, com o inteiro no hover,
//     e o padronizado numa coluna fixa;
//   - a gaveta nunca rola na horizontal; a barra de cima fica inteira;
//   - abrir e fechar: o botão alterna; clique no gráfico não fecha; clique
//     fora fecha só com o visor vazio.
import { abrirChrome, P } from "./comum.mjs";

const [BASE, TRAFO, ALIM, FOTOS, PORTA = "9953"] = process.argv.slice(2);
const { avaliar, confere, foto, navegar, terminar, assentar: espera } =
  await abrirChrome({ porta: PORTA, prefixo: "calc", fotos: FOTOS });
const ir = async (sha, tema) => {
  await navegar(`${BASE}/`, "document.body");
  await avaliar(`localStorage.setItem('osclab-tema', '${tema}')`);
  await navegar(`${BASE}/onda/${sha}`);
};
const AJUDANTES = `
  window.__g = () => document.querySelector('.calc-gaveta');
  window.__abrir = async () => { [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'calculadora').click(); await ${P(900)}; };
  window.__expr = () => document.querySelector('.calc-expr');
  window.__tecla = (rotulo) => [...__g().querySelectorAll('.calc-t')].find(b => b.textContent.trim() === rotulo);
  window.__escrever = async (t) => { const e = __expr(); e.value = t; e.selectionStart = e.selectionEnd = t.length; e.dispatchEvent(new Event('input')); await ${P(1400)}; };
  window.__dentro = (el, caixa) => { const a = el.getBoundingClientRect(), b = caixa.getBoundingClientRect(); return a.left >= b.left - 1 && a.right <= b.right + 1; };
  1`;

for (const tema of ["claro", "escuro"]) {
  // ---- o TRAFO: duas trincas de corrente, nomes longos estilo SIPROTEC ----
  await ir(TRAFO, tema);
  await avaliar(AJUDANTES);
  await avaliar("window.osclab.calc.porCursores(0.06, 0.15)"); await espera(900);
  await avaliar("__abrir()");
  confere(await avaliar("document.documentElement.classList.contains('calc-aberta')"), `${tema}: o botão abre a gaveta`);
  confere(await avaliar(`(() => { const b = document.getElementById('barra-de-cima'); if (!b) return true;
    return b.getBoundingClientRect().width >= window.innerWidth - 1 && __g().getBoundingClientRect().top >= b.getBoundingClientRect().bottom - 1; })()`),
    `${tema}: a barra de cima fica inteira e a gaveta começa embaixo dela`);
  const fileira = await avaliar(`[...document.querySelectorAll('.calc-fileira .calc-t')].map(b => [b.textContent, Math.round(b.getBoundingClientRect().width)])`);
  confere(fileira.length === 8 && fileira.map((x) => x[0]).join(" ") === "IA IB IC IN VA VB VC VN",
    `${tema}: a fileira tem as 8 teclas padronizadas (${fileira.map((x) => x[0]).join(" ")})`);
  confere(new Set(fileira.map((x) => x[1])).size === 1, `${tema}: as 8 teclas têm a MESMA largura (${[...new Set(fileira.map((x) => x[1]))]})`);
  const seletor = await avaliar(`[...document.querySelectorAll('.calc-grupos.I .calc-grupo')].map(b => [b.textContent, b.title])`);
  confere(seletor.length === 2 && seletor[0][0] === "G1" && seletor[0][1].includes("G1 · TC BUC 69kV:I *"),
    `${tema}: o seletor mostra só o grupo, e o radical no hover (${seletor.map((x) => x.join(" / ")).join(" | ")})`);
  confere(!(await avaliar("!!document.querySelector('.calc-grupos.V')")), `${tema}: sem seletor de tensão (uma trinca só)`);
  // [IA G1] - [IA G2], só com as teclas, trocando o seletor no meio
  await avaliar(`(async () => {
    [...document.querySelectorAll('.calc-grupos.I .calc-grupo')][0].click(); await ${P(100)};
    __tecla('IA').click(); await ${P(100)}; __tecla('−').click(); await ${P(100)};
    [...document.querySelectorAll('.calc-grupos.I .calc-grupo')][1].click(); await ${P(100)};
    __tecla('IA').click(); await ${P(1500)}; })()`);
  const conta = await avaliar("__expr().value");
  confere(conta === "[TC BUC 69kV:I A] - [TC EXT 13-8kV:I A]", `${tema}: as teclas montam «${conta}»`);
  confere((await avaliar("__tecla('IA').title")) === "[TC EXT 13-8kV:I A]", `${tema}: o hover da tecla diz o nome que ela insere`);
  confere(!!(await avaliar("document.querySelector('.calc-r1')?.textContent")), `${tema}: o visor mostra o valor no cursor`);
  await foto(`${tema}-1-trafo-teclas.png`);

  // Zap AG com TC BUC 69kV:I A nas três fases: o visor quebra e não estoura
  await avaliar("__escrever('')");
  await avaliar(`(async () => { document.querySelector('.calc-dom.fasor').click(); await ${P(200)};
    await __escrever('[VA] / ([IA G1] + {k0} * ([IA G1] + [IB G1] + [IC G1]) / 3)'); })()`);
  await avaliar(`(async () => { const f = document.querySelector('.calc-param input'); f.value = '0,68';
    f.dispatchEvent(new Event('input')); await ${P(1400)}; })()`);
  const visor = await avaliar(`(() => { const e = __expr(), v = document.querySelector('.calc-visor'), r = document.querySelector('.calc-r1'), g = __g();
    return { texto: e.value, larg: e.scrollWidth <= e.clientWidth + 1, alt: e.clientHeight, max: 132,
             r1: r ? __dentro(r, v) && __dentro(r, g) : false,
             semH: g.scrollWidth <= g.clientWidth + 1 && document.querySelector('.calc-corpo').scrollWidth <= document.querySelector('.calc-corpo').clientWidth + 1 }; })()`);
  confere(visor.texto.includes("[TC BUC 69kV:I A]") && visor.texto.includes("[TP BAR 13-8kV:V A]"), `${tema}: [IA G1] digitado vira o nome completo no visor`);
  confere(visor.larg, `${tema}: a expressão longa quebra linha, sem estourar a largura`);
  confere(visor.alt <= visor.max + 1, `${tema}: o visor cresce até o teto (${visor.alt} px ≤ ${visor.max}) e rola`);
  confere(visor.r1, `${tema}: o valor do cursor fica dentro do visor e da gaveta`);
  confere(visor.semH, `${tema}: a gaveta não rola na horizontal`);
  await foto(`${tema}-2-trafo-nomes-longos.png`);

  // a lista «[ ]»
  await avaliar(`(async () => { __tecla('[ ]').click(); await ${P(300)};
    const b = document.querySelector('.calc-busca'); b.value = ''; b.dispatchEvent(new Event('input')); await ${P(200)}; })()`);
  await avaliar("document.querySelector('.calc-dom.onda').click()"); await espera(300);
  await avaliar(`(async () => { __tecla('[ ]').click(); await ${P(400)}; })()`);
  const lista = await avaliar(`[...document.querySelectorAll('.calc-item')].map(b => {
    const n = b.querySelector('.calc-item-nome'), p = b.querySelector('.calc-item-padrao');
    return { nome: n.textContent, cortado: n.scrollWidth > n.clientWidth, hover: b.title,
             pad: Math.round(p.getBoundingClientRect().width), dentro: __dentro(b, __g()) }; })`);
  confere(lista.length > 10 && lista.every((x) => x.hover === x.nome), `${tema}: na lista, o hover traz o nome inteiro (${lista.length} linhas)`);
  confere(new Set(lista.map((x) => x.pad)).size === 1, `${tema}: o padronizado mora numa coluna de largura fixa`);
  confere(lista.every((x) => x.dentro), `${tema}: nenhuma linha da lista sai da gaveta`);
  confere(lista.some((x) => x.nome === "87T:I diff.:phs A"), `${tema}: o canal diferencial em pu também está na lista`);
  await foto(`${tema}-3-trafo-lista.png`);

  // fechar
  const fechar = await avaliar(`(async () => {
    const aberta = () => document.documentElement.classList.contains('calc-aberta');
    const clicar = (el) => el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    const r = {};
    await __escrever('[IA G1]');
    clicar(document.querySelector('.topo.registro')); await ${P(100)}; r.foraDigitando = aberta();
    await __escrever('');
    clicar(document.querySelector('main#graficos canvas')); await ${P(100)}; r.graficoVazio = aberta();
    clicar(document.querySelector('.topo.registro')); await ${P(200)}; r.foraVazio = aberta();
    await __abrir(); r.reabre = aberta();
    await __abrir(); r.botaoFecha = !aberta();
    return r; })()`);
  confere(fechar.foraDigitando && fechar.graficoVazio && !fechar.foraVazio && fechar.reabre && fechar.botaoFecha,
    `${tema}: fechar — ${JSON.stringify(fechar)}`);

  // ---- o ALIMENTADOR: Zap AG pela sugestão, neutro sem TC, filtro ----
  await ir(ALIM, tema);
  await avaliar(AJUDANTES);
  await avaliar("window.osclab.calc.porCursores(0.06, 0.195)"); await espera(900);
  await avaliar("__abrir()");
  await avaliar(`(async () => { window.osclabCalculadora.aba('sug'); await ${P(300)};
    (await __esperar(() => [...document.querySelectorAll('.calc-modelo')].find(l => l.textContent.includes('Zap AG')))).click(); await ${P(300)};
    const f = document.querySelector('.calc-param input'); f.value = '0,68'; f.dispatchEvent(new Event('input'));
    const a = document.querySelectorAll('.calc-param input')[1]; a.value = '-4'; a.dispatchEvent(new Event('input'));
    await ${P(1500)}; })()`);
  confere((await avaliar("__expr().value")).includes("[Voltage A-G]"), `${tema}: o modelo chega ao visor com os nomes do relé`);
  const zap = await avaliar("[...(document.querySelector('.calc-r2')?.children || [])].slice(1).map(x => x.textContent).join('')");
  confere(zap.startsWith("3,79") && zap.includes("Ω"), `${tema}: Zap AG no cursor 2 = ${zap}`);
  await foto(`${tema}-4-alimentador-zap.png`);
  await avaliar(`(async () => { __tecla('= criar').click(); await ${P(2500)}; })()`);
  // Criada, a conta vai SÓ para a lista (decidido em 11/11/2026): o gráfico
  // não muda, e uma linha no visor diz onde ela está.
  confere(!(await avaliar("[...document.querySelectorAll('.legenda')].map(x => x.textContent).join(' ')")).includes("Zap AG"),
    `${tema}: a conta criada NÃO entra no gráfico sozinha`);
  confere((await avaliar("document.querySelector('.calc-feito')?.textContent || ''")).includes("Calculados"),
    `${tema}: a confirmação diz que a conta está em Calculados`);
  await avaliar(`(async () => { window.osclabCalculadora.aba('minhas'); await ${P(600)};
    const l = await __esperar(() => [...document.querySelectorAll('.calc-conta')].find(x => x.textContent.includes('Zap AG')));
    [...l.querySelectorAll('.calc-mini')].find(b => b.textContent === '→').click(); await ${P(2500)};
    window.osclabCalculadora.aba('calc'); await ${P(300)}; })()`);
  confere((await avaliar("[...document.querySelectorAll('.legenda')].map(x => x.textContent).join(' ')")).includes("Zap AG"),
    `${tema}: o → de «minhas contas» põe a conta no gráfico`);
  await avaliar(`(async () => { document.querySelector('.calc-dom.onda').click(); await ${P(200)};
    await __escrever('[Current IN] - ([IA] + [IB] + [IC])'); })()`);
  confere(await avaliar("!!document.querySelector('.calc-param.relacao input')"), `${tema}: canal sem TC ganha o campo da relação`);
  await foto(`${tema}-5-alimentador-sem-tc.png`);
  // filtro de 60 Hz aceso com a conta no gráfico (o defeito do main)
  await avaliar(`(async () => { await __escrever(''); const f = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Filtro');
    if (f && !f.classList.contains('aceso')) f.click(); await ${P(2500)}; })()`);
  confere(!(await avaliar("document.body.textContent.includes('reinicie')")) &&
          (await avaliar("[...document.querySelectorAll('.legenda')].map(x => x.textContent).join(' ')")).includes("Zap AG"),
    `${tema}: com o filtro aceso a conta continua desenhada`);
  await foto(`${tema}-6-alimentador-filtro.png`);
}
terminar();
