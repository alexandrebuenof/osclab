/* As abas de oscilografia: uma barra como a do navegador, um quadro por aba.
 *
 * Cada aba é a página `/onda/<sha>` inteira, num `<iframe>`. É o jeito de cada
 * uma ser INDEPENDENTE sem reescrever a página: o estado de uma aba (arranjo,
 * zoom, cursores, os registros que entraram nela) vive no quadro dela, e
 * trocar de aba só esconde um quadro e mostra outro — nada recarrega.
 *
 * A lista de abas abertas fica no `sessionStorage`: some ao fechar a janela do
 * navegador, como o arranjo some ao fechar a página. Nada vai ao servidor.
 */
(() => {
  "use strict";

  const CHAVE = "osclab:abas";
  const barra = document.getElementById("barra-de-abas");
  const quadros = document.getElementById("quadros-das-abas");
  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  let estado = { abas: [], ativa: null, proximo: 1 };
  try {
    const cru = JSON.parse(sessionStorage.getItem(CHAVE) || "null");
    if (cru && Array.isArray(cru.abas)) estado = cru;
  } catch (_e) { /* sem sessão: começa vazio */ }
  const guardar = () => {
    try { sessionStorage.setItem(CHAVE, JSON.stringify(estado)); } catch (_e) { /* ok */ }
  };

  let nomes = new Map();
  async function lerAcervo() {
    try {
      const r = await fetch("/api/acervo");
      const corpo = await r.json();
      nomes = new Map((corpo.itens || []).map((x) => [x.sha, x]));
    } catch (_e) { /* sem nomes: a aba usa o sha */ }
  }

  function abrir(sha) {
    const id = `a${estado.proximo++}`;
    estado.abas.push({ id, sha });
    estado.ativa = id;
    guardar();
    desenhar();
  }

  function fechar(id) {
    const i = estado.abas.findIndex((a) => a.id === id);
    if (i < 0) return;
    const [fechada] = estado.abas.splice(i, 1);
    const quadro = document.getElementById(`quadro-${id}`);
    if (quadro) quadro.remove();
    // Os registros que entraram nesta aba vão junto com ela.
    try { sessionStorage.removeItem(`osclab:aba:${fechada.sha}:${id}`); } catch (_e) { /* ok */ }
    if (estado.ativa === id) {
      estado.ativa = (estado.abas[i] || estado.abas[i - 1] || {}).id || null;
    }
    guardar();
    if (!estado.abas.length) { location.href = "/arquivos"; return; }
    desenhar();
  }

  /** A lista de registros que se abre debaixo de um botão da barra.
   *
   * Fica no CORPO da página, com posição fixa: a barra rola na horizontal
   * (`overflow-x`), e um menu dentro dela sairia cortado na borda de baixo. */
  let fecharMenu = null;
  function abrirMenu(botao, cabeca, quais, escolher) {
    const tinhaEste = fecharMenu && fecharMenu.botao === botao;
    if (fecharMenu) fecharMenu();
    if (tinhaEste) return;
    const caixa = criar("div", "menu-suspenso menu-das-abas");
    const r = botao.getBoundingClientRect();
    caixa.style.top = `${r.bottom + 4}px`;
    caixa.style.left = `${Math.min(r.left, window.innerWidth - 300)}px`;
    caixa.append(criar("p", "cabeca-menu", cabeca));
    const lista = quais();
    if (!lista.length && cabeca.endsWith(":")) {
      caixa.append(criar("p", "nota-do-menu", "Não há outro registro no acervo."));
    }
    for (const s of lista) {
      const item = nomes.get(s) || {};
      const b = criar("button", "opcao-de-registro");
      b.type = "button";
      b.append(criar("span", "nome-do-registro", item.nome || s.slice(0, 10)));
      const sub = [item.estacao, item.equipamento, item.disparo].filter(Boolean).join(" · ");
      if (sub) b.append(criar("span", "sub-do-registro", sub));
      b.title = item.nome || s;
      b.addEventListener("click", () => { fecharMenu(); escolher(s); });
      caixa.append(b);
    }
    document.body.append(caixa);
    const fora = (e) => { if (!caixa.contains(e.target) && e.target !== botao) fecharMenu(); };
    const tecla = (e) => { if (e.key === "Escape") fecharMenu(); };
    fecharMenu = () => {
      caixa.remove();
      document.removeEventListener("pointerdown", fora, true);
      document.removeEventListener("keydown", tecla);
      fecharMenu = null;
    };
    fecharMenu.botao = botao;
    document.addEventListener("pointerdown", fora, true);
    document.addEventListener("keydown", tecla);
  }

  function desenhar() {
    if (fecharMenu) fecharMenu();
    barra.replaceChildren();
    for (const aba of estado.abas) {
      const item = nomes.get(aba.sha);
      const botao = criar("div", "aba-de-oscilografia" + (aba.id === estado.ativa ? " ativa" : ""));
      botao.tabIndex = 0;
      botao.setAttribute("role", "tab");
      botao.title = item ? [item.nome, item.estacao, item.disparo].filter(Boolean).join("\n") : aba.sha;
      botao.append(criar("span", "nome-da-aba", item ? item.nome : aba.sha.slice(0, 10)));
      const x = criar("button", "botao-x fechar-aba", "×");
      x.type = "button";
      x.title = "Fechar esta aba. O registro continua no acervo.";
      x.addEventListener("click", (e) => { e.stopPropagation(); fechar(aba.id); });
      botao.append(x);
      botao.addEventListener("click", () => { estado.ativa = aba.id; guardar(); desenhar(); });
      botao.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { estado.ativa = aba.id; guardar(); desenhar(); }
      });
      barra.append(botao);
    }
    // «+ adicionar oscilografia» NÃO mora aqui: esteve, e ele preferiu no
    // lugar de antes, dentro da página (22/10/2026). Mudou só a cara.
    const nova = criar("button", "chave aba-nova", "+ nova aba");
    nova.type = "button";
    nova.title = "Abrir outro registro do acervo numa aba nova, independente desta.";
    nova.addEventListener("click", () => abrirMenu(nova, "abrir numa aba nova:",
      () => [...nomes.keys()], abrir));
    // Sem «arquivos» aqui: a barra do aplicativo, dentro de cada aba, já tem
    // o «← arquivos», e o daqui ficou repetido. Pedido dele, 22/10/2026.
    barra.append(nova);

    for (const aba of estado.abas) {
      let quadro = document.getElementById(`quadro-${aba.id}`);
      if (!quadro) {
        quadro = criar("iframe", "quadro-da-aba");
        quadro.id = `quadro-${aba.id}`;
        quadro.title = (nomes.get(aba.sha) || {}).nome || "oscilografia";
        quadro.src = `/onda/${encodeURIComponent(aba.sha)}?aba=${aba.id}`;
        quadros.append(quadro);
      }
      quadro.hidden = aba.id !== estado.ativa;
    }
  }

  (async () => {
    await lerAcervo();
    const pedido = new URLSearchParams(location.search).get("abrir");
    if (pedido) {
      const aberta = estado.abas.find((a) => a.sha === pedido);
      if (aberta) estado.ativa = aberta.id; else abrir(pedido);
      history.replaceState(null, "", "/abas");
    }
    if (!estado.abas.length) { location.href = "/arquivos"; return; }
    if (!estado.abas.some((a) => a.id === estado.ativa)) estado.ativa = estado.abas[0].id;
    guardar();
    desenhar();
  })();
})();
