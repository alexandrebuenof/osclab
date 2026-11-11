/* O painel dos EVENTOS DO RELÉ, na tela da onda.
 *
 * A maquete 1 de «eventos-10», escolha dele em 02/11/2026: a tabela como o
 * relé escreveu (tAbs, t, descrição, valor), com a linha mais perto do cursor
 * marcada e o clique numa linha levando o cursor até ela. «Tem bastante
 * utilidade quando clicamos e enxergamos em qual momento os eventos subiram.»
 *
 * Seco como o painel de lógica: nada se traduz nem se classifica. Flutua pelo
 * mesmo motivo dela — é para ler olhando a onda.
 *
 * Com mais de um registro na aba, a lista é UMA, em ordem de tempo, e cada
 * linha leva o selo do IED: é o que responde «o trip do B veio antes ou
 * depois do A?». O tempo de cada lista já chega no tempo da ABA, deslocado
 * pelo servidor com o mesmo alinhamento das ondas (`plot/eventos.py`) — aqui
 * não se faz conta de tempo nenhuma.
 *
 * Não mede nem desenha: fala com a tela pela ponte `window.osclab`
 * (`onda.js`, perto de `porCursor`).
 */
(() => {
  "use strict";

  const chave = document.getElementById("eventos");
  const painel = document.getElementById("painel-dos-eventos");
  const barra = document.getElementById("barra-dos-eventos");
  const deOnde = document.getElementById("de-onde-os-eventos");
  const filtro = document.getElementById("filtro-dos-eventos");
  const corpo = document.getElementById("corpo-dos-eventos");
  const botaoCru = document.getElementById("cru-dos-eventos");
  if (!chave || !painel || !botaoCru) return;

  const sha = document.body.dataset.sha || "";
  const LEMBRANCA = "osclab:painel-dos-eventos";
  const MINIMO = { largura: 320, altura: 180 };

  let estado = null;          /* o que o servidor respondeu */
  let assinatura = null;      /* os registros da aba na última pergunta */
  const escondidos = new Set();   /* letras de IED desligadas no filtro */
  let linhas = [];            /* [{ tr, t, fora }] na ordem da tabela */
  let verCru = false;         /* o botão «texto» aceso */

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  /* Segundos com três casas e vírgula: é a resolução do relé (1 ms). */
  const segundos = (t) => (t === null || t === undefined) ? "—"
    : t.toFixed(3).replace("-", "−").replace(".", ",");

  /* ------------------------------------------------------------------ dados */

  const listas = () => (estado && estado.listas) || [];
  const variosIeds = () => listas().length > 1;

  function pintarChave() {
    const tem = !!(estado && estado.tem);
    chave.classList.toggle("sem-eventos", !tem);
    const n = listas().reduce((s, l) => s + l.eventos.length, 0);
    chave.title = tem
      ? `A lista de eventos que o relé gravou (${n} eventos), ligada ao cursor.`
      : listas().some((l) => l.cru)
        ? "O arquivo que veio com o registro não tem uma tabela de eventos que o programa saiba ler — clique para ver como veio."
        : "Este registro não trouxe lista de eventos — clique para saber por quê.";
  }

  async function carregar() {
    try {
      const pedido = window.osclab && window.osclab.pedido ? window.osclab.pedido() : undefined;
      const r = await fetch("/api/eventos/" + encodeURIComponent(sha),
                            pedido || undefined);
      estado = await r.json();
    } catch (erro) {
      estado = { tem: false, listas: [] };
    }
    pintarChave();
    if (!painel.hidden) pintar();
  }

  /* A tela avisa a cada janela; só se pergunta de novo quando os registros
     da aba (ou o alinhamento deles) mudaram. */
  document.addEventListener("osclab:janela", (ev) => {
    const nova = ((ev.detail && ev.detail.ieds) || []).join("|");
    if (nova === assinatura) return;
    assinatura = nova;
    carregar();
  });

  /* ----------------------------------------------------------------- pintar */

  function seloDoIed(lista) {
    const selo = criar("span", `selo-ied ied-${lista.letra.toLowerCase()}`, lista.letra);
    selo.title = `IED ${lista.letra}: ${lista.apelido || lista.de}`;
    return selo;
  }

  function pintarFiltro() {
    filtro.replaceChildren();
    filtro.hidden = !variosIeds();
    if (!variosIeds()) return;
    for (const lista of listas()) {
      const b = criar("button", "chave" + (escondidos.has(lista.letra) ? "" : " escolhido"));
      b.type = "button";
      b.append(seloDoIed(lista), criar("span", null,
        lista.tem ? ` ${lista.eventos.length}` : " sem lista"));
      b.title = lista.tem ? `Mostrar ou esconder os eventos do IED ${lista.letra}.`
                          : lista.motivo;
      b.disabled = !lista.tem;
      b.addEventListener("click", () => {
        if (escondidos.has(lista.letra)) escondidos.delete(lista.letra);
        else escondidos.add(lista.letra);
        pintar();
      });
      filtro.append(b);
    }
  }

  function pintarVazio() {
    const vazio = criar("div", "logica-vazia");
    const motivo = (listas()[0] && listas()[0].motivo) || "não deu para ler a lista";
    vazio.append(criar("p", null, "Nada para mostrar: " + motivo + "."));
    vazio.append(criar("p", "miudo",
      "A oscilografia continua igual — a lista de eventos é um extra que o " +
      "registro traz, ou não."));
    corpo.append(vazio);
  }

  /* O ARQUIVO COMO VEIO, de cada registro que trouxe um. É o que aparece
     quando a tabela não foi reconhecida — relé que nunca vimos, colunas em
     outra ordem — e quando se pede pelo botão «texto». Texto cru não
     liga ao cursor, mas também não mente: tabela lida errado mentiria. */
  function pintarCru(pedido) {
    for (const lista of listas()) {
      if (!lista.cru) continue;
      const cab = criar("p", "aviso-dos-eventos");
      if (variosIeds()) cab.append(seloDoIed(lista), " ");
      cab.append(lista.tem || pedido
        ? `${lista.de}, como veio`
        : `${lista.de}: ${lista.motivo}.`);
      const pre = criar("pre", "texto-cru", lista.cru);
      corpo.append(cab, pre);
    }
  }

  /* O bloco de dados do relé (tipo, localização, duração): é o número do
     PRÓPRIO relé, e por isso vem antes, fechado, para comparar com o nosso. */
  function pintarDados(lista) {
    if (!lista.dados.length) return;
    const caixa = criar("details", "dados-do-rele");
    const titulo = criar("summary", null,
      `dados da falta, do relé${variosIeds() ? " " + lista.letra : ""} (${lista.dados.length})`);
    caixa.append(titulo);
    const tabela = criar("table", "tabela-dos-eventos");
    const tb = criar("tbody");
    for (const d of lista.dados) {
      const tr = criar("tr");
      tr.append(criar("td", "desc", d.descricao), criar("td", "valor", d.valor));
      tb.append(tr);
    }
    tabela.append(tb);
    caixa.append(tabela);
    corpo.append(caixa);
  }

  function pintar() {
    corpo.replaceChildren();
    linhas = [];
    pintarFiltro();
    const com = listas().filter((l) => l.tem);
    const algumCru = listas().some((l) => l.cru);
    deOnde.textContent = com.length === 1 ? com[0].de : (com.length ? `${com.length} registros` : "");
    botaoCru.hidden = !algumCru;
    botaoCru.classList.toggle("escolhido", verCru);
    if (verCru && algumCru) { pintarCru(true); return; }
    if (!com.length) {
      if (algumCru) pintarCru(false); else pintarVazio();
      return;
    }

    for (const lista of com) {
      for (const aviso of lista.avisos) corpo.append(criar("p", "aviso-dos-eventos", "⚠ " + aviso));
      if (!escondidos.has(lista.letra)) pintarDados(lista);
    }

    // Uma lista só, em ordem de tempo; dentro do mesmo instante, a ordem do
    // arquivo (o sort é estável). Sem tempo conhecido vai para o fim.
    const todas = [];
    for (const lista of com) {
      if (escondidos.has(lista.letra)) continue;
      lista.eventos.forEach((e) => todas.push({ e, lista }));
    }
    todas.sort((a, b) => (a.e.t ?? Infinity) - (b.e.t ?? Infinity));

    const tabela = criar("table", "tabela-dos-eventos");
    const cab = criar("tr");
    if (variosIeds()) cab.append(criar("th", null, "IED"));
    const th = (texto, dica, classe) => {
      const c = criar("th", classe, texto);
      if (dica) c.title = dica;
      return c;
    };
    cab.append(
      th("tAbs", "A hora que o relé escreveu, como veio no arquivo."),
      th("t (s)", variosIeds()
        ? "Segundos no tempo da aba: o do IED A desde a primeira amostra, os outros deslocados pelo alinhamento."
        : "Segundos desde a primeira amostra do registro (o tRel do relé).", "num"),
      th("descrição"), th("valor"));
    const thead = criar("thead");
    thead.append(cab);
    const tb = criar("tbody");
    for (const { e, lista } of todas) {
      const tr = criar("tr", "evento" + (e.fora ? " fora" : ""));
      if (variosIeds()) {
        const c = criar("td");
        c.append(seloDoIed(lista));
        tr.append(c);
      }
      tr.append(criar("td", "hora", e.hora), criar("td", "num", segundos(e.t)),
                criar("td", "desc", (e.endereco ? e.endereco + "  " : "") + e.descricao),
                criar("td", "valor" + (/^(end|deasserted)$/i.test(e.valor) ? " fim" : ""), e.valor));
      if (e.fora) {
        tr.title = "Depois do fim da gravação: o relé continuou listando, e ali não há onda para o cursor.";
      } else if (e.t !== null) {
        tr.title = e.digital !== null && e.digital !== undefined
          ? "Clique para levar o cursor a este instante e selecionar o digital deste sinal."
          : "Clique para levar o cursor a este instante.";
        /* O cursor vai ao instante e, quando o registro grava o mesmo sinal
           como digital, a tira dele fica selecionada — dá para VER o sinal
           mudando ali. O casamento é do servidor (`e.digital`). */
        tr.addEventListener("click", async () => {
          if (!window.osclab) return;
          await window.osclab.irPara(e.t);
          if (e.digital !== null && e.digital !== undefined) {
            window.osclab.selecionarDigital(lista.letra, e.digital);
          }
        });
      }
      tb.append(tr);
      linhas.push({ tr, t: e.fora ? null : e.t });
    }
    tabela.append(thead, tb);
    corpo.append(tabela);
    marcarPerto(true);
  }

  /* -------------------------------------------------------------- o cursor */

  /* Marca TODAS as linhas do instante mais perto do cursor ativo: um trip
     costuma vir numa rajada de vinte linhas no mesmo milissegundo, e marcar
     uma só esconderia as outras dezenove. */
  function marcarPerto(rolar) {
    if (painel.hidden || !linhas.length) return;
    const ponte = window.osclab && window.osclab.cursores ? window.osclab.cursores() : null;
    const t = ponte ? (ponte.cursores[ponte.ativo] ?? ponte.cursores.find((x) => x !== null)) : null;
    let alvo = null;
    let menor = Infinity;
    if (t !== null && t !== undefined) {
      for (const l of linhas) {
        if (l.t === null) continue;
        const d = Math.abs(l.t - t);
        if (d < menor) { menor = d; alvo = l.t; }
      }
    }
    let primeira = null;
    for (const l of linhas) {
      const perto = alvo !== null && l.t !== null && Math.abs(l.t - alvo) < 1e-6;
      l.tr.classList.toggle("perto", perto);
      if (perto && !primeira) primeira = l.tr;
    }
    if (rolar && primeira) primeira.scrollIntoView({ block: "nearest" });
  }

  document.addEventListener("osclab:cursores", () => marcarPerto(true));

  /* --------------------------------------------------------- abrir e fechar */

  function lembrar() {
    try {
      localStorage.setItem(LEMBRANCA, JSON.stringify({
        x: painel.offsetLeft, y: painel.offsetTop,
        l: painel.offsetWidth, a: painel.offsetHeight,
      }));
    } catch (erro) { /* segue sem lembrar */ }
  }

  function dentroDaTela(x, y, l, a) {
    /* Inteiro na área visível, abaixo da barra de cima — ver logica.js. */
    return caberNaTela(painel, x, y, l, a);
  }

  function posicionar() {
    let guardado = null;
    try { guardado = JSON.parse(localStorage.getItem(LEMBRANCA) || "null"); }
    catch (erro) { guardado = null; }
    const largura = Math.max(MINIMO.largura,
      Math.min(guardado && guardado.l || 620, window.innerWidth - 24));
    const altura = Math.max(MINIMO.altura,
      Math.min(guardado && guardado.a || 420, window.innerHeight - 110));
    painel.style.width = largura + "px";
    painel.style.height = altura + "px";
    /* Nasce embaixo à direita: em cima ficam as chaves e o começo das ondas. */
    const bruto = guardado
      ? { x: guardado.x, y: guardado.y }
      : { x: window.innerWidth - largura - 18, y: window.innerHeight - altura - 18 };
    const posto = dentroDaTela(bruto.x, bruto.y, largura, altura);
    painel.style.left = posto.x + "px";
    painel.style.top = posto.y + "px";
  }

  function abrir() {
    posicionar();
    painel.hidden = false;
    pintar();
    chave.classList.add("escolhido");
  }

  function fechar() {
    painel.hidden = true;
    chave.classList.remove("escolhido");
  }

  chave.addEventListener("click", () => (painel.hidden ? abrir() : fechar()));
  document.getElementById("fechar-eventos").addEventListener("click", fechar);
  botaoCru.addEventListener("click", () => { verCru = !verCru; pintar(); });

  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape" || painel.hidden) return;
    if (!painel.contains(ev.target)) return;
    ev.stopPropagation();
    fechar();
  });

  /* ------------------------------------------------------------- arrastar */

  /* Igual ao da lógica, e pelas mesmas razões medidas lá: ouvintes na janela
     (a captura na barra se perdia) e `preventDefault` no pointerdown (senão
     o Chrome começa um arrasto nativo do texto da barra). */
  let pegada = null;

  const arrastar = (ev) => {
    if (!pegada) return;
    ev.preventDefault();
    const posto = dentroDaTela(ev.clientX - pegada.x, ev.clientY - pegada.y,
                               painel.offsetWidth, painel.offsetHeight);
    painel.style.left = posto.x + "px";
    painel.style.top = posto.y + "px";
  };

  const soltar = () => {
    if (!pegada) return;
    pegada = null;
    barra.classList.remove("arrastando");
    window.removeEventListener("pointermove", arrastar);
    window.removeEventListener("pointerup", soltar);
    window.removeEventListener("pointercancel", soltar);
    lembrar();
  };

  barra.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest("button")) return;
    ev.preventDefault();
    pegada = { x: ev.clientX - painel.offsetLeft, y: ev.clientY - painel.offsetTop };
    barra.classList.add("arrastando");
    window.addEventListener("pointermove", arrastar);
    window.addEventListener("pointerup", soltar);
    window.addEventListener("pointercancel", soltar);
  });

  if (window.ResizeObserver) {
    let primeira = true;
    new ResizeObserver(() => {
      if (primeira) { primeira = false; return; }
      if (!painel.hidden) lembrar();
    }).observe(painel);
  }

  window.addEventListener("resize", () => {
    if (painel.hidden) return;
    const posto = dentroDaTela(painel.offsetLeft, painel.offsetTop,
                               painel.offsetWidth, painel.offsetHeight);
    painel.style.left = posto.x + "px";
    painel.style.top = posto.y + "px";
  });

  pintarChave();
  /* A primeira pergunta sai quando a tela avisa da primeira janela: é ela que
     sabe os registros da aba. O onda.js carrega antes deste arquivo, mas a
     janela chega por fetch, então o aviso sempre vem depois daqui. */
})();
