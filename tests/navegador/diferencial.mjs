// Teste de NAVEGADOR da gaveta de ajustes do diferencial (variante 10, 12/11/2026).
//
//   node tests/navegador/diferencial.mjs <url-base> <sha-trafo> <pasta-das-fotos> [porta-cdp]
//
// Roda dentro de `tests/test_diferencial_navegador.py`, que sobe o servidor
// num acervo temporário com o trafo de `tests/casos_calculadora.py` (duas
// trincas de corrente, nenhum ajuste no arquivo). Confere, com o CSS aplicado:
//   - sem ajustes, o painel mostra a característica APAGADA e o que falta vai
//     numa linha ABAIXO do desenho, nunca por cima dele;
//   - «ajustes» abre a gaveta à direita, embaixo da barra de cima, e a coluna
//     dos gráficos encolhe (o painel continua à vista);
//   - a gaveta mostra o grupo só como «G1»/«G2»: nenhum radical, nenhum
//     «G1 · …» em lugar nenhum dela (o radical fica no hover);
//   - digitar o pickup muda a prévia AO VIVO (conta do servidor), e ao sair
//     do campo ele vira «digitado» (moldura) e entra no pedido do painel;
//   - nenhum botão da gaveta com a cara do navegador;
//   - clique fora NÃO fecha (é janela de edição); Esc fecha.
import { abrirChrome, P } from "./comum.mjs";

const [BASE, TRAFO, FOTOS, PORTA = "9957"] = process.argv.slice(2);
const W = 1600, H = 1000;
const { avaliar, confere, foto, navegar, terminar, assentar } =
  await abrirChrome({ porta: PORTA, prefixo: "diferencial", fotos: FOTOS, largura: W, altura: H });

await navegar(`${BASE}/`, "document.body");
await avaliar(`localStorage.setItem('osclab-tema', 'claro'); localStorage.setItem('osclab:catalogo:visao', 'avancado')`);
await navegar(`${BASE}/onda/${TRAFO}`);

await avaliar(`(async () => {
  window.__nativos = (raiz) => [...(raiz || document).querySelectorAll('button')]
    .filter(b => b.offsetParent && b.getClientRects().length)
    .filter(b => { const s = getComputedStyle(b); return s.borderTopStyle === 'outset' || s.backgroundColor === 'rgb(239, 239, 239)'; })
    .map(b => (b.className || '(sem classe)') + ' «' + b.textContent.trim().slice(0, 40) + '»');
  window.__dif = () => [...document.querySelectorAll('section.grafico.diferencial')].pop();
  document.querySelector('.novo-grafico').click(); await ${P(300)};
  [...document.querySelectorAll('.opcao-de-tipo')].find(b => b.textContent.includes('diferencial percentual')).click();
  await ${P(2500)};
  __dif().scrollIntoView({ block: 'start' }); window.scrollBy(0, -70); await ${P(300)};
  return 1; })()`);

// --- 1. o estado vazio: característica apagada, o que falta embaixo ----------------
const vazio = JSON.parse(await avaliar(`(() => {
  const g = __dif();
  const tela = g.querySelector('.tela-diferencial canvas.previa-87.fantasma');
  const linha = g.querySelector(':scope > .faltam-ajustes');
  if (!tela || !linha) return JSON.stringify({ tela: !!tela, linha: !!linha });
  const t = tela.getBoundingClientRect(), l = linha.getBoundingClientRect();
  // Algum texto ou botão por cima do desenho?
  const porCima = [...g.querySelectorAll('p, span, b, button, div')].filter(e => {
    if (e.contains(tela) || tela.contains(e) || !e.offsetParent) return false;
    const r = e.getBoundingClientRect();
    return r.width && r.height && r.left < t.right && r.right > t.left && r.top < t.bottom - 1 && r.bottom > t.top + 1
      && e.closest('.tela-diferencial');
  }).length;
  const ctx = tela.getContext('2d');
  const px = ctx.getImageData(0, 0, tela.width, tela.height).data;
  let tinta = 0; for (let i = 3; i < px.length; i += 4) if (px[i]) tinta++;
  return JSON.stringify({ tela: true, linha: true, abaixo: l.top >= t.bottom - 1, porCima, tinta,
    altura: Math.round(t.height), texto: linha.textContent }); })()`));
confere(vazio.tela && vazio.linha, `vazio: característica apagada e linha do que falta (${JSON.stringify(vazio).slice(0, 80)})`);
confere(vazio.abaixo && vazio.porCima === 0, `vazio: o que falta fica ABAIXO do desenho, nada por cima (${vazio.porCima})`);
confere(vazio.tinta > 1000 && vazio.altura === 300, `vazio: a característica foi pintada na altura do gráfico (${vazio.tinta} px, ${vazio.altura})`);
confere(/Faltam \d+ ajustes? para desenhar/.test(vazio.texto || ""), "vazio: a linha diz quantos faltam");
await foto("diferencial-vazio.png");

// --- 2. abrir a gaveta ---------------------------------------------------------------
const larguraAntes = await avaliar("Math.round(__dif().getBoundingClientRect().width)");
const g1 = JSON.parse(await avaliar(`(async () => {
  [...__dif().querySelectorAll('.grafico-titulo button')].find(b => b.textContent.trim() === 'ajustes').click();
  await ${P(600)};
  const gav = document.querySelector('.gaveta-87');
  if (!gav) return JSON.stringify({ aberta: false });
  const r = gav.getBoundingClientRect();
  const barra = document.getElementById('barra-de-cima');
  const grupos = [...gav.querySelectorAll('.grupo-87')].map(e => [e.textContent, e.title]);
  return JSON.stringify({ aberta: true, dir: Math.round(r.right), topo: Math.round(r.top),
    barra: barra ? Math.round(barra.getBoundingClientRect().bottom) : 0, base: Math.round(r.bottom),
    texto: gav.innerText, grupos, nativos: __nativos(gav),
    painel: Math.round(__dif().getBoundingClientRect().width), dirPainel: Math.round(__dif().getBoundingClientRect().right),
    esqGaveta: Math.round(r.left) }); })()`));
confere(g1.aberta, "«ajustes» abre a gaveta");
confere(g1.dir === W && Math.abs(g1.topo - g1.barra) <= 1 && g1.base === H,
  `a gaveta presa à direita, embaixo da barra de cima (${g1.topo} × ${g1.barra}, base ${g1.base})`);
confere(g1.painel < larguraAntes && g1.dirPainel <= g1.esqGaveta,
  `a coluna dos gráficos encolhe e o painel fica à vista (${larguraAntes} → ${g1.painel}, até ${g1.dirPainel} ≤ ${g1.esqGaveta})`);
confere(g1.grupos.length === 2 && g1.grupos.every(([t]) => /^G\d+$/.test(t)) && g1.grupos.every(([, h]) => h),
  `o grupo de cada lado é só «G1»/«G2», com o radical no hover (${JSON.stringify(g1.grupos)})`);
const radicais = g1.grupos.map(([, h]) => h).filter(Boolean);
const vazou = radicais.filter((r) => g1.texto.includes(r));
confere(vazou.length === 0, `nenhum radical escrito na gaveta (${vazou})`);
confere(!/G\d+\s*·/.test(g1.texto), "nenhum «G1 · …» na gaveta");
confere(g1.nativos.length === 0, `nenhum botão da gaveta com a cara do navegador ${g1.nativos}`);
await foto("diferencial-gaveta.png");

// --- 3. digitar o pickup: a prévia muda ao vivo, e vira «digitado» -------------------
const antes = await avaliar("document.querySelector('.gaveta-87 canvas.previa-87').toDataURL()");
await avaliar(`(async () => {
  const i = document.querySelector('.gaveta-87 .entrada-87[data-id="pickup"]');
  i.focus(); i.value = '0,6'; i.dispatchEvent(new Event('input', { bubbles: true }));
  await ${P(500)}; return 1; })()`);
const depois = await avaliar("document.querySelector('.gaveta-87 canvas.previa-87').toDataURL()");
confere(antes !== depois, "digitar o pickup muda a prévia ao vivo");
const gravado = JSON.parse(await avaliar(`(async () => {
  const i = document.querySelector('.gaveta-87 .entrada-87[data-id="pickup"]');
  i.dispatchEvent(new Event('change', { bubbles: true }));
  await ${P(1500)};
  const novo = document.querySelector('.gaveta-87 .entrada-87[data-id="pickup"]');
  const campo = novo && novo.closest('.campo-87');
  return JSON.stringify({ classe: campo ? campo.className : '', valor: novo ? novo.value : null,
    aberta: !!document.querySelector('.gaveta-87') }); })()`));
confere(gravado.aberta && /o-digitado/.test(gravado.classe) && gravado.valor === "0,6",
  `ao sair do campo, o pickup fica «digitado» e a gaveta continua aberta (${gravado.classe}, ${gravado.valor})`);
const textoDepois = await avaliar("document.querySelector('.gaveta-87').innerText");
confere(!/G\d+\s*·/.test(textoDepois) && radicais.every((r) => !textoDepois.includes(r)),
  "depois de refeita, a gaveta continua sem radical");

// --- 4. clique fora não fecha; Esc fecha ------------------------------------------------
const fora = await avaliar(`(async () => {
  const alvo = document.querySelector('section.grafico .grafico-titulo');
  alvo.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  document.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  await ${P(300)}; return !!document.querySelector('.gaveta-87'); })()`);
confere(fora, "clique fora NÃO fecha a gaveta (janela de edição)");
const esc = await avaliar(`(async () => {
  document.activeElement && document.activeElement.blur();
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await ${P(400)};
  return !document.querySelector('.gaveta-87') && !document.documentElement.classList.contains('dif-aberta'); })()`);
confere(esc, "Esc fecha a gaveta e a coluna volta");
await assentar(300);
terminar();
