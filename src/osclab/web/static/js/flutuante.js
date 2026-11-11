/* Janela flutuante (lógica, eventos): onde ela pode ficar.
 *
 * Uma conta só para as duas janelas, para elas não divergirem. A janela
 * cabe INTEIRA na área visível: abaixo da barra de cima (presa ao rolar, e
 * que antes ficava por cima do cabeçalho e escondia o ×) e dentro da largura
 * e da altura do navegador. Se não couber, ela encolhe — a lista rola por
 * dentro — e o cabeçalho com o × continua à vista. (11/11/2026)
 *
 * Pixel de posição não é número de medida: decidir isto aqui no navegador
 * não fere a regra de que o JavaScript não decide número nenhum.
 */
"use strict";

function caberNaTela(painel, x, y, l, a) {
  const margem = 8;
  const barra = document.querySelector(".barra-de-cima");
  const topo = barra ? Math.max(0, barra.getBoundingClientRect().bottom) : 0;

  const largMax = Math.max(0, window.innerWidth - 2 * margem);
  const altMax = Math.max(0, window.innerHeight - topo - 2 * margem);
  if (l > largMax) { l = largMax; painel.style.width = l + "px"; }
  if (a > altMax) { a = altMax; painel.style.height = a + "px"; }

  return {
    x: Math.max(margem, Math.min(x, window.innerWidth - l - margem)),
    y: Math.max(topo + margem, Math.min(y, window.innerHeight - a - margem)),
  };
}
