/* A tela inicial: escolher o módulo, e a nota dos módulos futuros.
 *
 * Sem biblioteca nenhuma, como o resto do programa — esta tela abre um
 * `<dialog>` e navega; uma dependência aqui viajaria dentro do pacote offline
 * para não fazer nada.
 */

(() => {
  "use strict";

  /** Fecha ao clicar no escuro em volta.
   *
   * O `<dialog>` entrega o clique do fundo como se fosse dele mesmo, então o
   * que distingue é a POSIÇÃO: fora da caixa é fundo.
   */
  const fecharNoFundo = (janela) => {
    janela.addEventListener("click", (evento) => {
      const r = janela.getBoundingClientRect();
      const dentro = evento.clientX >= r.left && evento.clientX <= r.right
                  && evento.clientY >= r.top && evento.clientY <= r.bottom;
      if (!dentro) janela.close();
    });
  };

  // O «sobre» saiu daqui em 10/11/2026: a versão foi para a barra de cima,
  // que existe em toda página, e quem a abre é o `barra.js`.

  // --- os módulos que ainda não existem ------------------------------------
  //
  // Eles são CLICÁVEIS de propósito: o clique diz o que o módulo vai fazer.
  // Um botão apagado que não responde a nada é a tela discutindo com quem
  // clicou — e quem clica num cartão apagado está justamente perguntando «o
  // que é isto?».
  const nota = document.getElementById("janela-do-modulo");
  const titulo = document.getElementById("titulo-do-modulo");
  const dizer = document.getElementById("dizer-do-modulo");
  if (nota && titulo && dizer) {
    document.getElementById("fechar-modulo")
      ?.addEventListener("click", () => nota.close());
    fecharNoFundo(nota);
    for (const cartao of document.querySelectorAll(".modulo.futuro")) {
      cartao.addEventListener("click", () => {
        // O texto sai do próprio cartão: ele já o tem escrito, e duas cópias
        // da mesma frase seriam duas para corrigir no dia em que mudar.
        titulo.textContent =
          cartao.querySelector(".nome-do-modulo").textContent.trim();
        dizer.textContent =
          cartao.querySelector(".dizer-do-modulo").textContent.trim();
        nota.showModal();
      });
    }
  }
})();
