/* A barra de cima: o que nela abre alguma coisa — hoje, a janelinha «sobre».
 *
 * O tema tem dono próprio (`tema.js`, no <head>); aqui fica só o «sobre», que
 * mora em toda página desde que a versão passou para a barra (10/11/2026).
 * Antes ele era da tela inicial e vivia no `menu.js`.
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

  const sobre = document.getElementById("janela-sobre");
  const botaoSobre = document.getElementById("sobre");
  if (sobre && botaoSobre) {
    botaoSobre.addEventListener("click", () => sobre.showModal());
    document.getElementById("fechar-sobre")
      ?.addEventListener("click", () => sobre.close());
    fecharNoFundo(sobre);
  }
})();
