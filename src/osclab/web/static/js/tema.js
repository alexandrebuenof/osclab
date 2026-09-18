/* Tema claro e escuro.
 *
 * O padrão é o ESCURO, por escolha do projeto — quem analisa oscilografia
 * costuma ficar horas na tela, muitas vezes em sala de controle com pouca luz.
 * O sistema operacional não decide aqui: quem decide é a preferência salva no
 * navegador, e o padrão dela é escuro.
 *
 * Este arquivo roda no <head>, sem `defer`, de propósito: se rodasse depois do
 * desenho da página, o tema claro apareceria por um instante antes de o escuro
 * entrar — aquele clarão que incomoda.
 */

(() => {
  "use strict";
  const CHAVE = "osclab-tema";
  const PADRAO = "escuro";

  const ler = () => {
    // Navegação anônima e sites com armazenamento bloqueado fazem isto
    // levantar. Cair no padrão é melhor do que quebrar a página.
    try { return localStorage.getItem(CHAVE) || PADRAO; } catch { return PADRAO; }
  };

  const gravar = (tema) => {
    try { localStorage.setItem(CHAVE, tema); } catch { /* segue sem lembrar */ }
  };

  const aplicar = (tema) => {
    document.documentElement.dataset.tema = tema;
    document.dispatchEvent(new CustomEvent("osclab:tema", { detail: tema }));
  };

  aplicar(ler());

  // O botão só existe depois que a página é montada.
  document.addEventListener("DOMContentLoaded", () => {
    const botao = document.getElementById("tema");
    if (!botao) return;
    const rotular = () =>
      (botao.textContent = document.documentElement.dataset.tema === "claro"
        ? "tema escuro" : "tema claro");
    rotular();
    botao.addEventListener("click", () => {
      const novo = document.documentElement.dataset.tema === "claro"
        ? "escuro" : "claro";
      aplicar(novo);
      gravar(novo);
      rotular();
    });
  });
})();
