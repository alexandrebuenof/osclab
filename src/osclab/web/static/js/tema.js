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

  // --- as CORES DAS FASES: a convenção de cada país ou empresa --------------
  //
  // Vale para o programa inteiro, como o tema: a fase A não pode ser azul num
  // gráfico e marrom no outro. As cores moram em `fases.css`; aqui só a lista
  // para o menu (o teste confere que os ids são os mesmos dos dois lados).
  const CHAVE_FASES = "osclab-fases";
  const FABRICA = "energisa";
  const CONVENCOES = [
    ["energisa", "Energisa MT", "convenção de campo da distribuidora — padrão de fábrica"],
    ["iec60445", "IEC 60445 / NBR 5410", "Brasil e Europa: L1 marrom, L2 preto, L3 cinza, N azul-claro"],
    ["ryb", "Vermelho-amarelo-azul", "BS 7671 antiga (Reino Unido até 2004), Índia, Hong Kong"],
    ["eua208", "EUA 208/120 V", "costume NEC: preto, vermelho, azul; N branco"],
    ["eua480", "EUA 480/277 V", "costume NEC: marrom, laranja, amarelo; N cinza"],
    ["canada", "Canadá", "CEC: vermelho, preto, azul; N branco"],
    ["aunz", "Austrália / NZ", "AS/NZS 3000: vermelho, branco, azul; N preto"],
    ["china", "China (GB)", "GB 50303: amarelo, verde, vermelho; N azul-claro"],
  ];
  const lerFases = () => {
    let id = FABRICA;
    try { id = localStorage.getItem(CHAVE_FASES) || FABRICA; } catch { /* fábrica */ }
    return CONVENCOES.some(c => c[0] === id) ? id : FABRICA;
  };
  const aplicarFases = (id) => {
    // A de fábrica é o `osclab.css` sem atributo nenhum.
    if (id === FABRICA) delete document.documentElement.dataset.fases;
    else document.documentElement.dataset.fases = id;
    // Repintar é o mesmo que numa troca de tema: os tokens mudaram.
    document.dispatchEvent(new CustomEvent("osclab:tema",
      { detail: document.documentElement.dataset.tema }));
  };
  aplicarFases(lerFases());
  // Outra aba (ou o quadro de uma aba de registros) trocou: segue junto.
  window.addEventListener("storage", (e) => {
    if (e.key === CHAVE_FASES) aplicarFases(lerFases());
  });

  document.addEventListener("DOMContentLoaded", () => {
    const botao = document.getElementById("fases");
    if (!botao) return;
    let menu = null;
    const fechar = () => { if (menu) { menu.remove(); menu = null; } };
    botao.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (menu) { fechar(); return; }
      menu = document.createElement("div");
      menu.className = "menu-fases";
      const atual = lerFases();
      menu.innerHTML = '<div class="rot">cores das fases · vale para o programa todo</div>';
      for (const [id, nome, origem] of CONVENCOES) {
        const item = document.createElement("button");
        item.type = "button";
        if (id === atual) item.className = "atual";
        item.innerHTML = `<span class="fases-amostra" data-p="${id}">`
          + '<span class="a"></span><span class="b"></span><span class="c"></span><span class="n"></span></span>'
          + `<span><span>${nome}</span><br><span class="peq">${origem}</span></span>`;
        item.title = "A, B, C e N, nesta ordem";
        item.addEventListener("click", () => {
          try { localStorage.setItem(CHAVE_FASES, id); } catch { /* só nesta página */ }
          aplicarFases(id);
          fechar();
        });
        menu.append(item);
      }
      const r = botao.getBoundingClientRect();
      menu.style.top = `${r.bottom + window.scrollY + 4}px`;
      menu.style.right = `${Math.max(8, document.documentElement.clientWidth - r.right)}px`;
      document.body.append(menu);
    });
    document.addEventListener("click", (ev) => { if (menu && !menu.contains(ev.target)) fechar(); });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fechar(); });
  });

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
