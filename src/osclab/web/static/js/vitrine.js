/* O desenho da subestação no portal (identidade f10, docs/identidade-visual.md).
 *
 * Duas caixas possíveis, as duas já no template:
 *
 *  - `[data-desenho="traco"]` — o início. A vista inteira em TRAÇO, recortada
 *    das torres da LT-1 aos postes dos alimentadores. Passar o mouse num
 *    cartão de serviço (ou na linha da base) acende o equipamento dele em
 *    azul-aço e mostra a linha de chamada até o cartão; passar no
 *    equipamento acende o cartão. Clicar no equipamento é clicar no cartão.
 *
 *  - `[data-desenho="casa"]` — arquivos e base. Só a casa de comando do
 *    desenho SÓLIDO, já em raio-x e com o grupo da página aceso (a classe
 *    `se-aceso-*` vem do template).
 *
 * O SVG vem por `fetch` e entra por `innerHTML` SÓ na caixa que o template
 * reservou para ele: embutido assim (e não por <img>), o CSS da página
 * alcança as variáveis `--se-*` e o aceso. Sem o desenho a página continua
 * inteira — ele é detalhe, nunca condição. Ver static/se3d/LEIA.md.
 */
(() => {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const ARQUIVO = {
    traco: "/static/se3d/vista-02-traco.svg",
    casa: "/static/se3d/vista-02-solido.svg",
  };

  // O recorte da vista no início: das torres da LT-1 até os postes dos
  // alimentadores; os cabos que iam até a borda esquerda ficam de fora. A
  // base do recorte é o pé do desenho, que pousa na linha de chão da página.
  const RECORTE = { x: 236, y: 30, l: 1410, a: 570 };
  // Só a casa de comando, para a faixa de título de arquivos e base.
  const RECORTE_DA_CASA = "1030 14 210 116";

  const svgEl = (tag, attrs) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };

  const buscar = (url) => fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.text();
  });

  // --- arquivos e base: a casa de comando ---------------------------------
  for (const caixa of document.querySelectorAll('[data-desenho="casa"]')) {
    buscar(ARQUIVO.casa).then((txt) => {
      caixa.innerHTML = txt;
      const svg = caixa.querySelector("svg");
      if (!svg) return;
      // O resto da subestação não aparece no recorte, mas pintaria por
      // cima da casa (a ordem de pintura do desenho intercala os grupos):
      // tirá-lo do documento é o mesmo que escondê-lo, e alivia o desenho.
      svg.querySelectorAll('[data-grupo="fundo"], [data-grupo="linhas"], '
        + '[data-grupo="viajantes"], [data-grupo="trafo"], #se-ancoras')
        .forEach((g) => g.remove());
      svg.setAttribute("viewBox", RECORTE_DA_CASA);
      svg.setAttribute("preserveAspectRatio", "xMaxYMax meet");
    }).catch(() => { /* sem o desenho a faixa continua inteira */ });
  }

  // --- o início: a vista e os serviços ------------------------------------
  const vista = document.querySelector('[data-desenho="traco"]');
  const palco = document.getElementById("palco");
  const chamadas = document.getElementById("chamadas");
  if (!vista || !palco || !chamadas) return;

  // Grupo do desenho → o que ele acende na página (cartão ou linha da base).
  const porGrupo = {};
  for (const alvo of palco.querySelectorAll("[data-liga]")) {
    porGrupo[alvo.dataset.liga] = alvo;
  }

  let atual = null;
  function acender(grupo) {
    if (grupo === atual) return;                 // não recalcula à toa
    if (atual) {
      vista.classList.remove("se-aceso-" + atual);
      palco.classList.remove("liga-" + atual);
      porGrupo[atual]?.classList.remove("aceso");
    }
    if (grupo) {
      vista.classList.add("se-aceso-" + grupo);
      palco.classList.add("liga-" + grupo);
      porGrupo[grupo]?.classList.add("aceso");
    }
    atual = grupo;
  }

  for (const [grupo, alvo] of Object.entries(porGrupo)) {
    alvo.addEventListener("mouseenter", () => acender(grupo));
    alvo.addEventListener("mouseleave", () => acender(null));
    alvo.addEventListener("focusin", () => acender(grupo));
    alvo.addEventListener("focusout", () => acender(null));
  }

  let svg = null;

  /* As linhas de chamada: da âncora do equipamento, desce reto até o vão
   * entre a linha de chão e os cartões, corre na horizontal até cima do
   * cartão e desce até ele. Ficam todas desenhadas; o CSS só mostra a do
   * serviço aceso. São refeitas a cada mudança de tamanho, porque é a única
   * hora em que o desenho e os cartões mudam de lugar um em relação ao outro.
   */
  function dispor() {
    chamadas.replaceChildren();
    chamadas.style.height = "0px";
    if (!svg || !vista.offsetWidth) return;      // estreito: o desenho some
    const pr = palco.getBoundingClientRect();
    const vr = svg.getBoundingClientRect();
    // com `meet` e o recorte em proporção, a escala é a da largura
    const s = vr.width / RECORTE.l;
    const cartoes = [...palco.querySelectorAll(".mosaico [data-liga]")]
      .map((m) => [m.dataset.liga, m.getBoundingClientRect()]);
    if (!cartoes.length) return;
    // Cartões em mais de uma fileira (tela média): a linha cruzaria os de
    // cima para chegar nos de baixo. Melhor nenhuma linha que uma errada.
    const topos = new Set(cartoes.map(([, b]) => Math.round(b.top)));
    if (topos.size !== 1) return;
    const topoCartao = cartoes[0][1].top - pr.top;
    const chao = vista.closest(".vitrine-miolo").getBoundingClientRect().bottom - pr.top;
    const nivel = chao + Math.max(10, (topoCartao - chao) / 2);
    chamadas.style.height = Math.ceil(topoCartao + 2) + "px";
    for (const [grupo, b] of cartoes) {
      const a = svg.querySelector(`[data-ancora="${grupo}"]`);
      if (!a) continue;
      const ax = vr.left - pr.left + (+a.getAttribute("cx") - RECORTE.x) * s;
      const ay = vr.top - pr.top + (+a.getAttribute("cy") - RECORTE.y) * s;
      const l = b.left - pr.left;
      const d = b.right - pr.left;
      const tx = Math.min(Math.max(ax, l + 28), d - 28);
      const f = (n) => n.toFixed(1);
      const caminho = Math.abs(tx - ax) < 1
        ? `M${f(ax)} ${f(ay + 4)}V${f(topoCartao)}`
        : `M${f(ax)} ${f(ay + 4)}V${f(nivel)}H${f(tx)}V${f(topoCartao)}`;
      const g = svgEl("g", { class: "linha-de-chamada", "data-liga": grupo });
      g.append(svgEl("path", { class: "chamada-halo", d: caminho }),
        svgEl("path", { class: "chamada-traco", d: caminho }),
        svgEl("circle", { class: "chamada-ancora", cx: f(ax), cy: f(ay), r: "3.5" }));
      chamadas.append(g);
    }
  }

  buscar(ARQUIVO.traco).then((txt) => {
    vista.innerHTML = txt;
    svg = vista.querySelector("svg");
    if (!svg) return;
    svg.setAttribute("viewBox", `${RECORTE.x} ${RECORTE.y} ${RECORTE.l} ${RECORTE.a}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMax meet");
    const grupoSob = (e) => {
      const g = e.target.closest?.("[data-grupo]")?.dataset.grupo;
      return g && g !== "fundo" ? g : null;
    };
    svg.addEventListener("mouseover", (e) => acender(grupoSob(e)));
    svg.addEventListener("mouseleave", () => acender(null));
    // Clicar no equipamento faz o mesmo que clicar no serviço — inclusive
    // abrir a nota de um módulo futuro, que é do menu.js.
    svg.addEventListener("click", (e) => {
      const g = grupoSob(e);
      if (g === "base") location.href = "/base";
      else if (g && porGrupo[g]) porGrupo[g].click();
    });
    dispor();
  }).catch(() => { /* sem o desenho a página continua inteira */ });

  let pedido = 0;
  addEventListener("resize", () => {
    cancelAnimationFrame(pedido);
    pedido = requestAnimationFrame(dispor);
  });
  // a fonte muda a altura do título e, com ela, onde os cartões começam
  document.fonts?.ready.then(dispor);
})();
