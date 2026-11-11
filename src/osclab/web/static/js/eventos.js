/* A janela dos EVENTOS DO RELÉ, na tela da onda.
 *
 * Escolha dele em 11/11/2026 (variante 03 da maquete «eventos», ramo
 * maquete/eventos): a tabela do arquivo, com a TRILHA da distribuição em cima
 * e o texto como veio a um botão — no jeito da janela da lógica.
 *
 * O que entra (e nada mais):
 *   - o que vem DENTRO do registro: a lista do `.hdr` da Schneider, lida
 *     sozinha;
 *   - o que se IMPORTA pelo «+ arquivo» desta janela: o SER da SEL (texto),
 *     o `.eev` da GE, ou qualquer texto com data e hora em cada linha. A
 *     lista importada vale enquanto a aba estiver aberta e NÃO é gravada
 *     (decisão de 11/11/2026): ela mora na sessão desta aba e vai no corpo de
 *     cada pedido. Quem lê e faz a conta é o servidor;
 *   - texto que nenhum leitor entende aparece como veio.
 *
 * Nada se classifica: nenhuma cor, peso ou apagado sai do NOME do evento ou
 * da palavra do valor. Todos os eventos têm a mesma tinta.
 *
 * O que o arquivo não diz vira campo, com a origem escrita (lido, sugerido,
 * digitado): o deslocamento até a hora do registro, o relé de um `.eev` que
 * junta vários, a ordem de uma data ambígua. A sugestão é do servidor.
 *
 * A TRILHA é a distribuição dos eventos no tempo: quantos caem em cada
 * intervalo. A contagem vem do servidor (`plot/eventos.distribuicao`); aqui
 * só se converte tempo em pixel e se pinta. Clicar numa barra faz todos os
 * eventos daquele intervalo piscarem juntos, deixa um fundo leve neles e rola
 * a tabela até o primeiro; Esc ou clique fora limpam.
 *
 * Não mede nem desenha onda: fala com a tela pela ponte `window.osclab`
 * (`onda.js`, perto de `porCursor`). Nenhuma conta de tempo é feita aqui.
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
  const miolo = painel.querySelector(".miolo-do-painel");

  const sha = document.body.dataset.sha || "";
  const LEMBRANCA = "osclab:painel-dos-eventos";
  const MINIMO = { largura: 360, altura: 220 };

  let estado = null;            /* o que o servidor respondeu */
  let assinatura = null;        /* os registros da aba na última pergunta */
  const escondidos = new Set(); /* «letra|relé» desligados nos chips */
  const iniciados = new Set();  /* listas cujo relé padrão já foi escolhido */
  const expandidos = new Set(); /* «lista:evento» com o detalhe aberto */
  let verCru = false;           /* o botão «texto» aceso */
  let selecionado = null;       /* { li, k }: o evento clicado */
  let linhas = [];              /* [{ el, t, li, k }] na ordem da tabela */
  let linhasCruas = new Map();  /* «lista:linha» → elemento no texto */
  let popover = null;
  let selecao = null;           /* [de, até]: o recorte clicado na trilha */
  let distribuicao = null;      /* a contagem do servidor, para a trilha */

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined && texto !== null) el.textContent = texto;
    return el;
  };
  const listas = () => (estado && estado.listas) || [];
  const variosIeds = () => new Set(listas().map((l) => l.letra)).size > 1;
  const numero = (n) => n.toLocaleString("pt-BR");
  const ehRelativa = (l) => !l.tempo || l.tempo.modo !== "absoluto";

  /* Segundos com as casas que o relé escreve (3 = ms, 6 = µs) e vírgula. */
  const segundos = (t, casas) => (t === null || t === undefined) ? "—"
    : t.toFixed(casas || 3).replace("-", "−").replace(".", ",");

  /* ------------------------------------------------------------- controles */

  const campo = criar("input", "busca-do-dicionario");
  campo.type = "search";
  campo.placeholder = "procurar…";
  campo.autocomplete = "off";
  miolo.prepend(campo);
  campo.addEventListener("input", () => pintar());

  const faixa = criar("div", "ev-faixa");
  faixa.hidden = true;
  campo.after(faixa);

  const trilha = criar("div", "ev-trilha");
  trilha.hidden = true;
  faixa.after(trilha);
  const dicaDaTrilha = criar("div", "ev-dica-trilha");
  dicaDaTrilha.hidden = true;
  painel.append(dicaDaTrilha);

  const alerta = criar("span", "ev-alerta", "⚠");
  alerta.hidden = true;
  deOnde.after(alerta);

  const entrada = criar("input");
  entrada.type = "file";
  entrada.multiple = true;
  entrada.hidden = true;
  entrada.accept = ".eev,.txt,.ser,.csv,.log,text/plain";
  painel.append(entrada);
  let paraQual = sha;
  const botaoImportar = criar("button", "chave como-veio", "+ arquivo");
  botaoImportar.type = "button";
  botaoImportar.title = "importar lista de eventos";
  botaoCru.before(botaoImportar);

  const ajuda = criar("button", "chave como-veio ev-ajuda", "?");
  ajuda.type = "button";
  ajuda.title = "ajuda";
  botaoCru.after(ajuda);

  /* --------------------------------------------- as listas IMPORTADAS na aba */

  const CHAVE_IMPORTADOS = "osclab:eventos:importados:" + sha;
  let importados = [];
  try { importados = JSON.parse(sessionStorage.getItem(CHAVE_IMPORTADOS) || "[]"); }
  catch (_e) { importados = []; }
  const guardarImportados = () => {
    try { sessionStorage.setItem(CHAVE_IMPORTADOS, JSON.stringify(importados)); }
    catch (_e) { /* sem espaço na sessão: vale até recarregar */ }
  };
  const doItem = (lista) => importados.find((x) => x.sha === lista.sha && x.nome === lista.arquivo);

  /* O texto como o relé o escreveu: UTF-8 quando é, senão o Windows-1252 dos
     programas de relé em português e espanhol. */
  async function lerTexto(arquivo) {
    const bytes = await arquivo.arrayBuffer();
    try { return new TextDecoder("utf-8", { fatal: true }).decode(bytes).replace(/^﻿/, ""); }
    catch (_e) { return new TextDecoder("windows-1252").decode(bytes); }
  }

  function acrescentar(alvoSha, nome, texto) {
    importados = importados.filter((x) => !(x.sha === alvoSha && x.nome === nome));
    importados.push({ sha: alvoSha, nome, texto, escolhas: {} });
    guardarImportados();
  }

  entrada.addEventListener("change", async () => {
    if (!entrada.files.length) return;
    for (const f of entrada.files) acrescentar(paraQual, f.name, await lerTexto(f));
    entrada.value = "";
    await carregar();
    if (painel.hidden) abrir();
  });

  botaoImportar.addEventListener("click", (ev) => {
    const ieds = [...new Map(listas().map((l) => [l.letra, l])).values()];
    if (ieds.length <= 1) { paraQual = sha; entrada.click(); return; }
    ev.stopPropagation();
    abrirPopover(botaoImportar, (caixa) => {
      caixa.append(criar("p", "ev-miudo", "para qual registro?"));
      for (const l of ieds) {
        const b = criar("button", "chave ev-escolha");
        b.type = "button";
        b.append(seloDoIed(l), " " + (l.apelido || l.sha.slice(0, 8)));
        b.addEventListener("click", () => { fecharPopover(); paraQual = l.sha; entrada.click(); });
        caixa.append(b);
      }
    });
  });

  /* ------------------------------------------------------------------ dados */

  function pintarChave() {
    const tem = !!(estado && estado.tem);
    chave.classList.toggle("sem-eventos", !tem);
    const n = listas().reduce((s, l) => s + l.eventos.length, 0);
    chave.title = tem
      ? `A lista de eventos do relé (${numero(n)} eventos), ligada ao cursor.`
      : listas().some((l) => l.cru)
        ? "O arquivo de eventos não tem uma tabela que o programa saiba ler — clique para ver como veio."
        : "Este registro não trouxe lista de eventos — clique para importar uma.";
  }

  /* O corpo de todo pedido de eventos: os registros da aba (o mesmo da
     janela das ondas) mais as listas importadas nesta aba. */
  function corpoDoPedido() {
    const pedido = window.osclab && window.osclab.pedido ? window.osclab.pedido() : undefined;
    let saida = {};
    try { saida = pedido && pedido.body ? JSON.parse(pedido.body) : {}; }
    catch (_e) { saida = {}; }
    saida.importados = importados;
    return saida;
  }

  async function carregar() {
    try {
      const r = await fetch("/api/eventos/" + encodeURIComponent(sha), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpoDoPedido()),
      });
      estado = await r.json();
    } catch (_e) {
      estado = { tem: false, listas: [] };
    }
    /* Num arquivo que junta vários relés, só o deste registro entra ligado. */
    for (const l of listas()) {
      const id = l.sha + "|" + l.arquivo;
      if (iniciados.has(id)) continue;
      iniciados.add(id);
      if (l.fontes.length > 1 && l.fonte.nome) {
        for (const f of l.fontes) if (f.nome !== l.fonte.nome) escondidos.add(l.letra + "|" + f.nome);
      }
    }
    distribuicao = null;
    pintarChave();
    if (!painel.hidden) pintar();
  }

  document.addEventListener("osclab:janela", (ev) => {
    const nova = ((ev.detail && ev.detail.ieds) || []).join("|");
    if (nova === assinatura) return;
    assinatura = nova;
    carregar();
  });

  /* Fuso, relé e ordem da data de uma lista importada: ficam na aba, junto
     com ela, e vão ao servidor no próximo pedido. Vazio apaga a escolha. */
  async function escolher(lista, campoNome, valor) {
    const item = doItem(lista);
    if (!item) return;
    item.escolhas = item.escolhas || {};
    if (valor === null || valor === undefined || valor === "") delete item.escolhas[campoNome];
    else item.escolhas[campoNome] = String(valor);
    guardarImportados();
    if (campoNome === "fonte") {
      for (const f of lista.fontes) {
        const k = lista.letra + "|" + f.nome;
        if (!valor || f.nome === valor) escondidos.delete(k); else escondidos.add(k);
      }
    }
    await carregar();
  }

  async function tirar(lista) {
    importados = importados.filter((x) => !(x.sha === lista.sha && x.nome === lista.arquivo));
    guardarImportados();
    fecharPopover();
    await carregar();
  }

  /* --------------------------------------------------------------- pedaços */

  function seloDoIed(lista) {
    const selo = criar("span", `selo-ied ied-${lista.letra.toLowerCase()}`, lista.letra);
    selo.title = `IED ${lista.letra}: ${lista.apelido || lista.de}`;
    return selo;
  }

  const NOME_DA_ORIGEM = { lido: "lido", sugerido: "sugerido", digitado: "digitado", nenhum: "sem dado" };
  function origem(qual, porque) {
    const o = criar("span", `ev-origem origem-${qual || "nenhum"}`, NOME_DA_ORIGEM[qual] || qual);
    if (porque) o.title = porque;
    return o;
  }

  function grifar(destino, texto, alvo) {
    texto = texto || "";
    if (!alvo) { destino.append(texto); return; }
    const baixo = texto.toLowerCase();
    let i = 0;
    for (;;) {
      const onde = baixo.indexOf(alvo, i);
      if (onde < 0) { destino.append(texto.slice(i)); break; }
      if (onde > i) destino.append(texto.slice(i, onde));
      destino.append(criar("mark", null, texto.slice(onde, onde + alvo.length)));
      i = onde + alvo.length;
    }
  }

  function abrirPopover(ancora, encher) {
    fecharPopover();
    popover = criar("div", "ev-popover");
    encher(popover);
    painel.append(popover);
    const a = ancora.getBoundingClientRect(), p = painel.getBoundingClientRect();
    const folga = 8;
    popover.style.maxWidth = (p.width - 2 * folga) + "px";
    const w = popover.offsetWidth, h = popover.offsetHeight;
    /* Alinhado à âncora e empurrado para DENTRO da janela: nunca cortado. */
    let x = a.left - p.left > p.width / 2 ? a.right - p.left - w : a.left - p.left;
    x = Math.max(folga, Math.min(x, p.width - w - folga));
    let y = a.bottom - p.top + 4;
    if (y + h > p.height - folga) y = a.top - p.top - h - 4;
    y = Math.max(folga, Math.min(y, p.height - h - folga));
    popover.style.left = x + "px";
    popover.style.top = y + "px";
  }
  function fecharPopover() { if (popover) { popover.remove(); popover = null; } }

  /* O formulário do tempo e da origem de UMA lista importada: só controles.
     O porquê de cada sugestão mora no hover da origem; as outras hipóteses,
     na lista do próprio campo. */
  function formulario(lista) {
    const caixa = criar("div", "ev-form");
    const titulo = criar("div", "ev-form-titulo");
    if (variosIeds()) titulo.append(seloDoIed(lista), " ");
    const nome = criar("span", null, lista.arquivo || lista.de || "registro");
    nome.title = lista.formato ? "lido como " + lista.formato : "";
    titulo.append(nome);
    if (lista.importado) {
      const b = criar("button", "ev-tirar", "×");
      b.type = "button";
      b.title = "tirar este arquivo";
      b.addEventListener("click", () => tirar(lista));
      titulo.append(b);
    }
    caixa.append(titulo);
    if (!lista.tem || ehRelativa(lista)) return caixa;
    const t = lista.tempo;
    const linha = criar("div", "ev-campo");
    const inp = criar("input", "ev-desloc");
    const item = doItem(lista);
    inp.value = t.erro && item && item.escolhas ? item.escolhas.deslocamento : t.texto;
    if (t.erro) { inp.classList.add("errado"); inp.title = t.erro; }
    else inp.title = `registro: ${t.registro}\nlista: sem fuso\n+4:00, −3:30 ou 0:00:00,012`;
    const idLista = "ev-cand-" + Math.random().toString(36).slice(2, 8);
    const dl = criar("datalist");
    dl.id = idLista;
    for (const c of t.candidatos || []) {
      const o = criar("option");
      o.value = c.texto;
      o.label = `${c.casados} casam · ${c.dentro} na gravação`;
      dl.append(o);
    }
    inp.setAttribute("list", idLista);
    const gravar = () => { if (inp.value.trim() !== t.texto) escolher(lista, "deslocamento", inp.value.trim()); };
    inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); gravar(); } });
    inp.addEventListener("change", gravar);
    linha.append(criar("span", "rotulo", "fuso"), inp, dl, origem(t.origem, t.porque));
    if (t.origem === "digitado") {
      const voltar = criar("button", "ev-voltar", "↺");
      voltar.type = "button";
      voltar.title = `voltar ao sugerido (${t.sugerido.texto}): ${t.sugerido.porque}`;
      voltar.addEventListener("click", () => escolher(lista, "deslocamento", ""));
      linha.append(voltar);
    }
    caixa.append(linha);
    if (lista.fontes.length > 1) {
      const l = criar("div", "ev-campo");
      const sel = criar("select", "ev-sel");
      const todos = criar("option", null, "todos");
      todos.value = "";
      sel.append(todos);
      for (const f of lista.fontes) {
        const o = criar("option", null, f.nome);
        o.value = f.nome;
        o.selected = f.nome === lista.fonte.nome;
        sel.append(o);
      }
      sel.title = `${NOME_DA_ORIGEM[lista.fonte.origem] || ""}: ${lista.fonte.porque}`;
      sel.addEventListener("change", () => escolher(lista, "fonte", sel.value));
      l.append(criar("span", "rotulo", "relé"), sel);
      caixa.append(l);
    }
    if (lista.ordem && lista.ordem.valor) {
      const l = criar("div", "ev-campo");
      const sel = criar("select", "ev-sel");
      for (const [v, nomeDaOrdem] of [["DMA", "dd/mm/aa"], ["MDA", "mm/dd/aa"], ["AMD", "aa/mm/dd"]]) {
        const o = criar("option", null, nomeDaOrdem);
        o.value = v;
        o.selected = v === lista.ordem.valor;
        sel.append(o);
      }
      sel.title = lista.ordem.origem === "sugerido"
        ? "sugerido: nenhum número passa de 12; a ordem mais perto da data do registro"
        : NOME_DA_ORIGEM[lista.ordem.origem] || "";
      sel.addEventListener("change", () => escolher(lista, "ordem", sel.value));
      l.append(criar("span", "rotulo", "data"), sel);
      caixa.append(l);
    }
    return caixa;
  }

  /* O fuso no alto: o valor e a origem; o porquê no hover; editar no ✎. */
  function pintarAjuste() {
    faixa.replaceChildren();
    const com = listas().filter((l) => (l.tem && !ehRelativa(l)) || l.importado);
    faixa.hidden = !com.length;
    if (!com.length) return;
    for (const l of com) {
      const s = criar("span", "ev-resumo");
      if (variosIeds()) s.append(seloDoIed(l), " ");
      if (l.tem && !ehRelativa(l)) {
        s.append(criar("span", "num", l.tempo.texto), origem(l.tempo.origem, l.tempo.porque));
      } else {
        s.append(criar("span", "ev-miudo", l.arquivo));
      }
      faixa.append(s);
    }
    const lapis = criar("button", "ev-lapis", "✎");
    lapis.type = "button";
    lapis.title = "ajustar o tempo e a origem";
    lapis.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (popover) { fecharPopover(); return; }
      abrirPopover(lapis, (caixa) => { for (const l of com) caixa.append(formulario(l)); });
    });
    faixa.append(lapis);
  }

  /* O ⚠ da barra: o diagnóstico inteiro mora no hover dele. */
  function pintarAlerta() {
    const avisos = [];
    for (const l of listas()) {
      if (!l.tem && l.cru) avisos.push(`${l.arquivo || l.de}: sem tabela reconhecida — vai como veio`);
      for (const a of l.avisos || []) if (!/fuso/.test(a)) avisos.push(`${l.arquivo}: ${a}`);
      if (l.tem && !ehRelativa(l) && l.tempo.origem === "nenhum") avisos.push(`${l.arquivo}: ${l.tempo.porque}`);
    }
    alerta.hidden = !avisos.length;
    alerta.title = avisos.join("\n");
  }

  ajuda.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (popover) { fecharPopover(); return; }
    abrirPopover(ajuda, (caixa) => {
      const dl = criar("dl", "ev-ajuda-lista");
      for (const [t, d] of [
        ["clique", "cursor no instante do evento; a tira do digital de mesmo nome fica selecionada"],
        ["Shift+clique", "cursor 2 — o Δt sai na tabelinha"],
        ["trilha", "quantos eventos em cada intervalo; clique numa barra para achar os dela na tabela"],
        ["▸", "detalhe da linha: número, operando, medidas do relé, linha do arquivo"],
        ["texto", "o arquivo como veio, linha a linha"],
        ["lido · sugerido · digitado", "de onde saiu o número; moldura pontilhada = sugerido"],
        ["fuso", "o que somar à hora da lista para cair no tempo do registro"],
        ["+ arquivo", ".eev (GE), SER (SEL) ou texto com data e hora por linha; vale nesta aba"],
      ]) dl.append(criar("dt", null, t), criar("dd", null, d));
      caixa.append(dl);
    });
  });

  document.addEventListener("pointerdown", (ev) => {
    if (popover && !popover.contains(ev.target) && !ev.target.closest?.(".ev-lapis, .ev-ajuda")
        && ev.target !== botaoImportar) fecharPopover();
    /* Clique fora da trilha e fora de uma linha de evento limpa o recorte. */
    if (selecao && !trilha.contains(ev.target)
        && !(ev.target.closest && ev.target.closest("tr.evento, .ev-detalhe"))) {
      selecao = null;
      pintar();
    }
  });

  /* Os relés: um chip por relé do arquivo (ou por IED da aba). */
  function pintarFiltro() {
    filtro.replaceChildren();
    const grupos = [];
    for (const l of listas()) {
      if (!l.tem) continue;
      if (l.fontes.length > 1) {
        for (const f of l.fontes) grupos.push({ l, nome: f.nome, n: f.n, eh: f.nome === l.fonte.nome });
      } else if (variosIeds()) {
        grupos.push({ l, nome: l.fontes[0] ? l.fontes[0].nome : "", n: l.eventos.length, eh: true });
      }
    }
    filtro.hidden = !grupos.length;
    for (const g of grupos) {
      const k = g.l.letra + "|" + g.nome;
      const b = criar("button", "chave" + (escondidos.has(k) ? "" : " escolhido"));
      b.type = "button";
      if (variosIeds()) b.append(seloDoIed(g.l));
      b.append(criar("span", null, ` ${g.nome || g.l.arquivo} `), criar("span", "ev-n", numero(g.n)));
      b.title = g.l.fontes.length > 1 && g.eh ? g.l.fonte.porque : "";
      b.addEventListener("click", () => {
        if (escondidos.has(k)) escondidos.delete(k); else escondidos.add(k);
        pintar();
      });
      filtro.append(b);
    }
  }

  /* ------------------------------------------------------------- os itens */

  function itens() {
    const alvo = campo.value.trim().toLowerCase();
    const saida = [];
    listas().forEach((l, li) => {
      if (!l.tem) return;
      l.eventos.forEach((e, k) => {
        if (escondidos.has(l.letra + "|" + (e.fonte || (l.fontes[0] ? l.fontes[0].nome : "")))) return;
        if (alvo) {
          const texto = [e.descricao, e.valor, e.operando, e.fonte, e.hora, e.data, e.endereco]
            .join(" ").toLowerCase();
          if (!texto.includes(alvo)) return;
        }
        saida.push({ l, li, e, k });
      });
    });
    /* Uma lista só, em ordem de tempo; sem instante, no fim. */
    saida.sort((a, b) => (a.e.t ?? Infinity) - (b.e.t ?? Infinity));
    return { todos: saida, alvo };
  }

  function itemDe(s) {
    const l = listas()[s.li];
    if (!l || !l.eventos[s.k]) return null;
    return { l, li: s.li, e: l.eventos[s.k], k: s.k };
  }

  /* Escolher um evento: o cursor vai ao instante (Shift: o cursor 2) — o
     gráfico anda até ele, pelo gesto `andar` do servidor —, a tira do
     digital de mesmo nome fica selecionada, a linha acende no texto. Evento
     fora da gravação não leva o cursor: ali não há onda. */
  async function escolherEvento(x, ev) {
    selecionado = { li: x.li, k: x.k };
    marcarSelecionado();
    sincronizarCru(x, true);
    if (x.e.t === null || x.e.fora || !window.osclab) return;
    if (ev && ev.shiftKey && window.osclab.irParaCursor) await window.osclab.irParaCursor(1, x.e.t);
    else await window.osclab.irPara(x.e.t);
    if (x.e.digital !== null && x.e.digital !== undefined) {
      window.osclab.selecionarDigital(x.l.letra, x.e.digital);
    }
  }

  /* O que a linha tem além do que se vê: número, operando, medidas, linha. */
  function detalhes(x) {
    const e = x.e, l = x.l;
    const d = [];
    if (e.numero) d.push(["nº do evento", e.numero]);
    if (e.operando) d.push(["operando", e.operando]);
    if (e.endereco && !ehRelativa(l)) d.push(["código", e.endereco]);
    if (e.data) d.push(["data e hora como veio", e.data + " " + e.hora]);
    l.colunas_extras.forEach((n, i) => { if (e.extras && e.extras[i] !== undefined) d.push([n, e.extras[i]]); });
    if (e.linha) d.push(["linha do arquivo", String(e.linha)]);
    return d;
  }

  function colunas(todos) {
    const temData = new Set(todos.map((x) => x.e.data).filter(Boolean)).size > 1;
    const casas = Math.max(3, ...listas().map((l) => l.casas || 3));
    const cols = [];
    if (variosIeds()) cols.push(["IED"]);
    if (temData) cols.push(["data"]);
    cols.push(["hora"], ["t (s)", variosIeds() ? "no tempo da aba" : "desde a primeira amostra", "num"]);
    cols.push(["evento"], ["valor"], ["", "", "mais"]);
    return { cols, temData, casas };
  }

  function cabecalho(cols) {
    const thead = criar("thead");
    const tr = criar("tr");
    for (const [texto, dica, classe] of cols) {
      const th = criar("th", classe || null, texto);
      if (dica) th.title = dica;
      tr.append(th);
    }
    thead.append(tr);
    return thead;
  }

  function linhaDaTabela(x, info, alvo, par) {
    const e = x.e;
    const tr = criar("tr", "evento" + (e.t === null ? " sem-t" : "") + (par ? " par" : ""));
    /* O recorte clicado na trilha: fundo leve. Comparação, não conta. */
    if (selecao && e.t !== null && e.t >= selecao[0] && e.t <= selecao[1]) tr.classList.add("realce");
    if (variosIeds()) { const c = criar("td"); c.append(seloDoIed(x.l)); tr.append(c); }
    if (info.temData) tr.append(criar("td", "hora", e.data || ""));
    const h = criar("td", "hora");
    grifar(h, e.hora, alvo);
    tr.append(h, criar("td", "num", segundos(e.t, info.casas)));
    const d = criar("td", "desc");
    if (e.endereco && ehRelativa(x.l)) d.append(criar("span", "ev-end", e.endereco + "  "));
    grifar(d, e.descricao, alvo);
    if (e.operando) d.append(criar("span", "ev-end", "  (" + e.operando + ")"));
    if (e.descricao.length > 46) d.title = e.descricao;
    const v = criar("td", "valor");
    grifar(v, e.valor, alvo);
    tr.append(d, v);
    const id = x.li + ":" + x.k;
    const mais = criar("td", "mais", expandidos.has(id) ? "▾" : "▸");
    mais.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (expandidos.has(id)) expandidos.delete(id); else expandidos.add(id);
      pintar();
    });
    tr.append(mais);
    if (e.fora) tr.title = e.fora === "antes" ? "antes da gravação" : "depois da gravação";
    tr.addEventListener("click", (ev) => escolherEvento(x, ev));
    linhas.push({ el: tr, t: (e.fora || e.t === null) ? null : e.t, li: x.li, k: x.k });
    if (!expandidos.has(id)) return [tr];
    const det = criar("tr", "ev-detalhe");
    const td = criar("td");
    td.colSpan = info.cols.length;
    const grade = criar("div", "ev-grade");
    for (const [n, val] of detalhes(x)) grade.append(criar("span", "n", n), criar("span", "v", val));
    td.append(grade);
    if (e.linha) {
      const b = criar("button", "chave ev-mini", "linha " + e.linha + " ↗");
      b.type = "button";
      b.addEventListener("click", (ev) => {
        ev.stopPropagation();
        selecionado = { li: x.li, k: x.k };
        verCru = true;
        pintar();
        sincronizarCru(x, true);
      });
      td.append(b);
    }
    det.append(td);
    return [tr, det];
  }

  function pintarTabela(todos, alvo) {
    const info = colunas(todos);
    const tabela = criar("table", "tabela-dos-eventos ev-tabela");
    tabela.append(cabecalho(info.cols));
    const tb = criar("tbody");
    todos.forEach((x, i) => { for (const tr of linhaDaTabela(x, info, alvo, i % 2 === 1)) tb.append(tr); });
    tabela.append(tb);
    corpo.append(tabela);
  }

  /* O bloco de dados do relé (tipo, localização, duração): é o número do
     PRÓPRIO relé, fechado em cima, para comparar com o nosso. */
  function pintarDados() {
    for (const lista of listas()) {
      if (!lista.tem || !lista.dados || !lista.dados.length) continue;
      const caixa = criar("details", "dados-do-rele");
      caixa.append(criar("summary", null,
        `dados do relé${variosIeds() ? " " + lista.letra : ""} · ${lista.dados.length}`));
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
  }

  /* ------------------------------------------------------- o texto como veio */

  function pintarCru() {
    linhasCruas = new Map();
    listas().forEach((l, li) => {
      if (!l.cru) return;
      const cab = criar("p", "ev-nome-cru");
      if (variosIeds()) cab.append(seloDoIed(l), " ");
      cab.append(l.arquivo || l.de);
      const doEvento = new Map();
      if (l.tem) l.eventos.forEach((e, k) => { if (e.linha && !doEvento.has(e.linha)) doEvento.set(e.linha, k); });
      const caixa = criar("div", "texto-cru ev-cru");
      const frag = document.createDocumentFragment();
      l.cru.split(/\r?\n/).forEach((txt, i) => {
        const n = i + 1;
        const lin = criar("div", "ev-linha-crua");
        lin.append(criar("span", "n", String(n)), criar("span", "x", txt || " "));
        const k = doEvento.get(n);
        if (k !== undefined) {
          lin.classList.add("de-evento");
          const x = { l, li, e: l.eventos[k], k };
          lin.addEventListener("click", (ev) => escolherEvento(x, ev));
        }
        linhasCruas.set(li + ":" + n, lin);
        frag.append(lin);
      });
      caixa.append(frag);
      corpo.append(cab, caixa);
    });
  }

  function sincronizarCru(x, rolar) {
    for (const el of painel.querySelectorAll(".ev-linha-crua.marcada")) el.classList.remove("marcada");
    if (!x || !x.e.linha) return;
    const el = linhasCruas.get(x.li + ":" + x.e.linha);
    if (!el) return;
    el.classList.add("marcada");
    if (rolar) el.scrollIntoView({ block: "center" });
  }

  function marcarSelecionado() {
    for (const el of corpo.querySelectorAll(".escolhido-ev")) el.classList.remove("escolhido-ev");
    if (!selecionado) return;
    for (const l of linhas) {
      if (l.li === selecionado.li && l.k === selecionado.k) l.el.classList.add("escolhido-ev");
    }
  }

  /* ----------------------------------------------------------------- pintar */

  function pintarVazio() {
    const vazio = criar("div", "ev-vazio");
    const b = criar("button", "chave", "+ arquivo de eventos");
    b.type = "button";
    b.title = ".eev (GE), SER (SEL) ou texto com data e hora por linha";
    b.addEventListener("click", () => botaoImportar.click());
    vazio.append(criar("span", "ev-miudo", "sem lista"), b);
    corpo.append(vazio);
  }

  function pintar() {
    fecharPopover();
    corpo.replaceChildren();
    linhas = [];
    linhasCruas = new Map();
    pintarAlerta();
    pintarAjuste();
    pintarFiltro();
    pedirTrilha();
    const com = listas().filter((l) => l.tem);
    const algumCru = listas().some((l) => l.cru);
    const arquivos = listas().filter((l) => l.tem || l.cru);
    deOnde.textContent = arquivos.length === 1 ? (arquivos[0].arquivo || arquivos[0].de)
      : (arquivos.length ? `${arquivos.length} arquivos` : "");
    botaoCru.hidden = !algumCru;
    botaoCru.classList.toggle("escolhido", verCru);
    botaoCru.title = "o arquivo como veio";
    campo.hidden = !com.length || verCru;

    if ((verCru && algumCru) || (!com.length && algumCru)) {
      pintarCru();
      if (selecionado) sincronizarCru(itemDe(selecionado), true);
      return;
    }
    if (!com.length) { pintarVazio(); return; }
    const { todos, alvo } = itens();
    pintarDados();
    pintarTabela(todos, alvo);
    if (!todos.length) corpo.append(criar("p", "nada-no-grupo", "—"));
    marcarSelecionado();
    marcarPerto(true);
  }

  /* -------------------------------------------------------------- o cursor */

  /* Marca TODAS as linhas do instante mais perto do cursor ativo: um trip
     costuma vir numa rajada de vinte linhas no mesmo milissegundo. */
  function marcarPerto(rolar) {
    if (painel.hidden || !linhas.length) return;
    const ponte = window.osclab && window.osclab.cursores ? window.osclab.cursores() : null;
    const t = ponte ? (ponte.cursores[ponte.ativo] ?? ponte.cursores.find((x) => x !== null)) : null;
    let alvo = null, menor = Infinity;
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
      l.el.classList.toggle("perto", perto);
      if (perto && !primeira) primeira = l.el;
    }
    if (rolar && primeira && !selecao) primeira.scrollIntoView({ block: "center" });
  }

  document.addEventListener("osclab:cursores", () => {
    marcarPerto(true);
    if (distribuicao) desenharTrilha();
  });

  /* ------------------------------------------------------------- a trilha */

  let assinaturaDaTrilha = "";
  let pedidoDaTrilha = 0;
  const ALTURA_DA_TRILHA = 30;
  const corDe = (token) => getComputedStyle(document.documentElement).getPropertyValue(token).trim();

  async function pedirTrilha() {
    if (painel.hidden || !listas().some((l) => l.tem)) { trilha.hidden = true; return; }
    trilha.hidden = false;
    const largura = Math.round(trilha.clientWidth || 600);
    const marca = [largura, [...escondidos].sort().join(","),
      listas().map((l) => l.sha + l.arquivo + (l.tempo && l.tempo.texto)).join("|")].join("#");
    if (marca === assinaturaDaTrilha && distribuicao) { desenharTrilha(); return; }
    assinaturaDaTrilha = marca;
    const meu = ++pedidoDaTrilha;
    try {
      const pedido = Object.assign(corpoDoPedido(), { largura, escondidos: [...escondidos] });
      const r = await fetch("/api/eventos/" + encodeURIComponent(sha) + "/trilha", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(pedido),
      });
      const d = await r.json();
      if (meu !== pedidoDaTrilha) return;
      distribuicao = d.geral || null;
    } catch (_e) { distribuicao = null; }
    desenharTrilha();
  }

  function desenharTrilha() {
    const d = distribuicao;
    trilha.replaceChildren();
    if (!d || !d.total) { trilha.hidden = true; return; }
    trilha.hidden = false;
    const tela = criar("canvas", "ev-tela-trilha");
    tela.style.height = ALTURA_DA_TRILHA + "px";
    trilha.append(tela);
    const dpr = window.devicePixelRatio || 1;
    const w = tela.clientWidth;
    const altura = tela.clientHeight || ALTURA_DA_TRILHA;
    tela.width = Math.round(w * dpr);
    tela.height = Math.round(altura * dpr);
    const ctx = tela.getContext("2d");
    ctx.scale(dpr, dpr);
    const x = (t) => (t - d.inicio) / (d.fim - d.inicio) * w;
    const n = d.contagens.length;
    const bw = w / n;
    /* O trecho da gravação, marcado só na trilha. */
    if (d.gravacao) {
      const g0 = Math.max(0, x(d.gravacao[0])), g1 = Math.min(w, x(d.gravacao[1]));
      if (g1 > g0) {
        ctx.fillStyle = corDe("--destaque-fraco");
        ctx.fillRect(g0, 0, Math.max(1, g1 - g0), altura);
        ctx.fillStyle = corDe("--destaque");
        ctx.globalAlpha = 0.5;
        ctx.fillRect(g0, 0, 1, altura);
        ctx.fillRect(Math.max(g0, g1 - 1), 0, 1, altura);
        ctx.globalAlpha = 1;
      }
    }
    /* O recorte clicado. */
    if (selecao) {
      const s0 = Math.max(0, x(selecao[0])), s1 = Math.min(w, x(selecao[1]));
      ctx.fillStyle = corDe("--tinta");
      ctx.globalAlpha = 0.12;
      ctx.fillRect(s0, 0, Math.max(1, s1 - s0), altura);
      ctx.globalAlpha = 1;
    }
    /* As barras: altura PROPORCIONAL à contagem (o maior intervalo enche a
       tira); contagem > 0 nunca abaixo de 2 px, para o evento solto não sumir. */
    const base = altura - 1, util = altura - 2;
    ctx.fillStyle = corDe("--destaque");
    for (let k = 0; k < n; k++) {
      if (!d.contagens[k]) continue;
      const alto = Math.max(2, d.h[k] * util);
      ctx.fillRect(k * bw, base - alto, Math.max(1, bw - (bw > 3 ? 1 : 0)), alto);
    }
    /* O cursor ativo, como linha. */
    const ponte = window.osclab && window.osclab.cursores ? window.osclab.cursores() : null;
    const t = ponte ? ponte.cursores[ponte.ativo] : null;
    if (t !== null && t !== undefined && t >= d.inicio && t <= d.fim) {
      ctx.fillStyle = corDe("--tinta");
      ctx.fillRect(Math.round(x(t)) - 1, 0, 2, altura);
    }
    ligarGestos(tela, d);
  }

  /* Só a BARRA é alvo: mãozinha e hover só sobre ela; o resto da tira é
     fundo (clique ali limpa o recorte). */
  function ligarGestos(tela, d) {
    const barraEm = (ev) => {
      const r = tela.getBoundingClientRect();
      const n = d.contagens.length;
      const k = Math.floor((ev.clientX - r.left) / (r.width / n));
      if (k < 0 || k >= n || !d.contagens[k]) return -1;
      /* Dentro da coluna, só a altura pintada (mais 2 px de folga) é barra. */
      const alto = Math.max(2, d.h[k] * (r.height - 2));
      return ev.clientY >= r.bottom - 1 - alto - 2 ? k : -1;
    };
    tela.addEventListener("pointermove", (ev) => {
      const k = barraEm(ev);
      tela.style.cursor = k >= 0 ? "pointer" : "default";
      if (k < 0) { dicaDaTrilha.hidden = true; return; }
      const c = d.contagens[k];
      dicaDaTrilha.textContent = `${numero(c)} ${c === 1 ? "evento" : "eventos"} · ${d.rotulos[k]}`;
      dicaDaTrilha.hidden = false;
      const p = painel.getBoundingClientRect();
      const l = Math.min(ev.clientX - p.left + 10, p.width - dicaDaTrilha.offsetWidth - 8);
      dicaDaTrilha.style.left = Math.max(8, l) + "px";
      dicaDaTrilha.style.top = (tela.getBoundingClientRect().bottom - p.top + 4) + "px";
    });
    tela.addEventListener("pointerleave", () => { dicaDaTrilha.hidden = true; });
    tela.addEventListener("click", (ev) => {
      const k = barraEm(ev);
      if (k < 0) { selecao = null; pintar(); return; }
      const de = d.inicio + k * d.passo, ate = de + d.passo;
      selecao = [de, ate];
      pintar();
      rolarAteRecorte(de, ate);
    });
  }

  /* A tabela rola até o primeiro evento do recorte, e TODOS os eventos dele
     piscam juntos; o fundo leve fica (`realce`). */
  function rolarAteRecorte(de, ate) {
    const doRecorte = [];
    for (const l of linhas) {
      const x = itemDe(l);
      if (x && x.e.t !== null && x.e.t >= de && x.e.t <= ate) doRecorte.push(l.el);
    }
    if (!doRecorte.length) return;
    doRecorte[0].scrollIntoView({ block: "center" });
    for (const el of doRecorte) el.classList.remove("lampejo");
    void doRecorte[0].offsetWidth;          /* reinicia a animação */
    for (const el of doRecorte) el.classList.add("lampejo");
    setTimeout(() => { for (const el of doRecorte) el.classList.remove("lampejo"); }, 1400);
  }

  if (window.ResizeObserver) {
    let ultima = 0;
    new ResizeObserver(() => {
      const w = Math.round(trilha.clientWidth);
      if (painel.hidden || !w || Math.abs(w - ultima) < 8) return;
      ultima = w;
      pedirTrilha();
    }).observe(trilha);
  }

  /* --------------------------------------------------------- abrir e fechar */

  function lembrar() {
    try {
      localStorage.setItem(LEMBRANCA, JSON.stringify({
        x: painel.offsetLeft, y: painel.offsetTop, l: painel.offsetWidth, a: painel.offsetHeight,
      }));
    } catch (_e) { /* segue sem lembrar */ }
  }

  /* Inteiro na área visível, abaixo da barra de cima — `flutuante.js`. */
  function caber(x = painel.offsetLeft, y = painel.offsetTop) {
    const posto = caberNaTela(painel, x, y, painel.offsetWidth, painel.offsetHeight);
    painel.style.left = posto.x + "px";
    painel.style.top = posto.y + "px";
  }

  function posicionar() {
    let guardado = null;
    try { guardado = JSON.parse(localStorage.getItem(LEMBRANCA) || "null"); } catch (_e) { guardado = null; }
    const largura = Math.max(MINIMO.largura, Math.min(guardado && guardado.l || 820, window.innerWidth - 24));
    const altura = Math.max(MINIMO.altura, Math.min(guardado && guardado.a || 520, window.innerHeight - 110));
    painel.style.width = largura + "px";
    painel.style.height = altura + "px";
    /* Nasce embaixo à direita: em cima ficam as chaves e o começo das ondas. */
    const bruto = guardado ? { x: guardado.x, y: guardado.y }
      : { x: window.innerWidth - largura - 18, y: window.innerHeight - altura - 18 };
    const posto = caberNaTela(painel, bruto.x, bruto.y, largura, altura);
    painel.style.left = posto.x + "px";
    painel.style.top = posto.y + "px";
  }

  function abrir() {
    posicionar();
    painel.hidden = false;
    caber();
    pintar();
    chave.classList.add("escolhido");
  }

  function fechar() {
    painel.hidden = true;
    fecharPopover();
    dicaDaTrilha.hidden = true;
    chave.classList.remove("escolhido");
  }

  chave.addEventListener("click", () => (painel.hidden ? abrir() : fechar()));
  document.getElementById("fechar-eventos").addEventListener("click", fechar);
  botaoCru.addEventListener("click", () => { verCru = !verCru; pintar(); });

  /* Esc com o foco na janela: fecha o balão, depois limpa o recorte, depois
     fecha a janela. Fora dela o Esc é das ondas (tira os cursores) — e
     também limpa o recorte, se houver. */
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape" || painel.hidden) return;
    if (!painel.contains(ev.target)) {
      if (selecao) { selecao = null; pintar(); }
      return;
    }
    ev.stopPropagation();
    if (popover) { fecharPopover(); return; }
    if (selecao) { selecao = null; pintar(); return; }
    fechar();
  });

  /* ------------------------------------------------------------- arrastar */

  /* Ouvintes na janela (a captura na barra se perdia) e `preventDefault` no
     pointerdown (senão o Chrome começa um arrasto nativo do texto da barra) —
     as mesmas razões, medidas, da janela da lógica. */
  let pegada = null;
  const arrastar = (ev) => {
    if (!pegada) return;
    ev.preventDefault();
    caber(ev.clientX - pegada.x, ev.clientY - pegada.y);
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
      if (painel.hidden) return;
      caber();                       /* esticar pelo canto também não passa da tela */
      lembrar();
    }).observe(painel);
  }
  window.addEventListener("resize", () => { if (!painel.hidden) caber(); });
  window.addEventListener("scroll", () => { if (!painel.hidden) caber(); }, { passive: true });

  pintarChave();
  /* A primeira pergunta sai quando a tela avisa da primeira janela: é ela que
     sabe os registros da aba. */
})();
