/* A calculadora de sinais: a GAVETA lateral (variante 10 da maquete,
 * aprovada pelo Alexandre em 11/11/2026).
 *
 * Cara de calculadora: um VISOR marinho (o nome, a expressão, o valor no
 * cursor 1 grande e o do cursor 2 menor, e a prévia da curva no registro
 * inteiro) e um teclado científico em grade, com a FILEIRA dos oito sinais de
 * todo dia (IA IB IC IN VA VB VC VN) em cima. Três abas: «calculadora»,
 * «sugestões» (os modelos) e «minhas contas».
 *
 * ## Quem decide o quê
 *
 * Nada de conta aqui. Quem lê a expressão, calcula, reduz a prévia por mínimo
 * e máximo e ESCREVE os números (casas, unidade, ângulo) é o servidor
 * (`plot/calculadora.py`, rotas `/api/onda/<sha>/calculadora/...`). Esta tela
 * converte valor em pixel, monta teclas e guarda o que está sendo digitado.
 *
 * ## A tecla mostra o padronizado e INSERE o nome do canal
 *
 * `IA` no rótulo, `[TC BUC 69kV:I A]` no visor: quem olha o visor tem de ver
 * qual canal entrou na conta — num trafo `[IA]` não diz de que lado. Os
 * modelos continuam escritos com `[IA]` (valem em qualquer relé) e chegam ao
 * visor já com os nomes completos; `[IA]` digitado à mão também vira o nome
 * completo. «guardar como modelo» faz o caminho de volta (`generalizar`).
 *
 * Com mais de uma trinca da mesma grandeza, um seletor acima da fileira
 * escolhe o GRUPO — «G1» (o radical do nome, «I*W», no hover), nunca «alta» ou
 * «baixa» (o programa não diz lado). Corrente e tensão têm seletores
 * próprios, e a escolha vale até ser trocada. O IN da fileira é o RESÍDUO da
 * trinca escolhida.
 *
 * ## Fechar
 *
 * O botão «calculadora» do gráfico abre e fecha; o «›» do cabeçalho fecha. O
 * clique fora fecha SÓ com o visor vazio e FORA do gráfico: pôr o cursor no
 * gráfico é parte de usar a calculadora, e uma conta pela metade não se perde
 * por um clique distraído.
 *
 * ## Nome comprido não estraga a gaveta
 *
 * Nome de canal de IED chega a 27 caracteres (`MAIN : Timer stage N elaps.`).
 * As teclas têm largura fixa e rótulo padronizado; a lista da tecla «[ ]»
 * corta o nome pela largura MEDIDA (reticências do CSS), com o inteiro no
 * hover e o padronizado numa coluna fixa; o visor quebra a expressão e cresce
 * até um teto, e depois rola; o valor do cursor fica numa linha própria. A
 * gaveta nunca rola na horizontal.
 */
"use strict";

(() => {
  const criar = (tag, cls, texto) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (texto !== undefined && texto !== null) e.textContent = texto;
    return e;
  };
  const botao = (texto, cls, dica, acao) => {
    const b = criar("button", cls, texto);
    b.type = "button";
    if (dica) b.title = dica;
    if (acao) b.addEventListener("click", acao);
    return b;
  };
  const calc = () => window.osclab && window.osclab.calc;
  async function enviar(caminho, corpo, metodo = "POST") {
    const r = await fetch(`/api/onda/${calc().sha}/calculadora/${caminho}`, {
      method: metodo, headers: { "Content-Type": "application/json" },
      body: metodo === "GET" ? undefined : JSON.stringify(corpo || {}),
    });
    return r.json();
  }
  const virgula = (v) => String(v ?? "").replace(".", ",");
  //: NOTA (o buraco onde o denominador some, que vale para toda impedância)
  //: × RESSALVA (unidade misturada, TC não declarado). Só a ressalva acende o
  //: ⚠: um ⚠ aceso em toda impedância ensina a ignorá-lo.
  const eNota = (a) => a.startsWith("onde o de baixo");
  const separar = (avisos) => [(avisos || []).filter((a) => !eNota(a)),
                               (avisos || []).filter(eNota)];

  let cursoresAgora = [null, null];
  const ouvintesDeCursor = new Set();
  const ouvintesDeContas = new Set();
  document.addEventListener("osclab:cursores", (ev) => {
    cursoresAgora = ev.detail.cursores;
    for (const f of ouvintesDeCursor) f();
  });
  const avisarContas = () => { for (const f of ouvintesDeContas) f(); };

  //: Modelos, nomes, fileira e o k0 do relé — um pedido por abertura da gaveta.
  let info = null;
  async function carregarInfo() {
    const r = await fetch(`/api/onda/${calc().sha}/calculadora/modelos?lado=${encodeURIComponent(calc().lado() || "arquivo")}`);
    info = await r.json();
    return info;
  }

  const AJUDA = "Visor: a conta e o valor dela nos cursores 1 e 2; embaixo, a curva no registro inteiro.\n"
    + "As teclas IA…VN inserem o nome do canal por trás (o hover diz qual). [ ] abre todos os sinais.\n"
    + "Sinais entre colchetes: [Current IA], ou [IA] / [IA G2] — vira o nome do canal. Tab completa.\n"
    + "Vírgula é a casa decimal; «;» separa os argumentos de uma função.\n"
    + "ONDA, amostra a amostra: rms delta deriv integ f60 media abs raiz atrasar(x; ms) maxjan(x; ms).\n"
    + "FASOR, sobre o 60 Hz: a (1∠120°) j conj mod ang re im polar(m; graus).\n"
    + "{k0} vira campo para digitar (↺ usa o do relé).\n"
    + "«=» cria a conta: ela entra no «+ sinal», em Calculados — nunca num gráfico sozinha.\n"
    + "Em «minhas contas», → põe a conta no gráfico escolhido.";

  //: As teclas. Cada uma é [rótulo, o que insere, classe, dica]. Inserções
  //: especiais: "⌫" apaga · "C" limpa · "SINAL" abre a lista de sinais.
  const FUNCOES = {
    onda: [["rms", "rms()", "f", "eficaz de um ciclo"], ["delta", "delta()", "f", "x menos x de um ciclo atrás"],
           ["deriv", "deriv()", "f", "derivada no tempo"], ["f60", "f60()", "f", "só os 60 Hz"],
           ["integ", "integ()", "f", "integral"], ["atrasar", "atrasar(; 16,67)", "f", "atrasar(x; ms)"]],
    fasor: [["a", " a ", "f", "1 ∠ 120°"], ["a²", " a^2 ", "f", "1 ∠ 240°"], ["conj", "conj()", "f", "conjugado"],
            ["mod", "mod()", "f", "módulo"], ["ang", "ang()", "f", "ângulo, em graus"], ["re", "re()", "f", "parte real"]],
  };
  const NUMEROS = [["7", "7"], ["8", "8"], ["9", "9"], ["÷", " / ", "op"],
                   ["4", "4"], ["5", "5"], ["6", "6"], ["×", " * ", "op"],
                   ["1", "1"], ["2", "2"], ["3", "3"], ["−", " - ", "op"],
                   ["0", "0"], [",", ","], ["[ ]", "SINAL", "sig", "todos os sinais"], ["+", " + ", "op"]];
  const LADO = [[["√", "raiz()", "f", "raiz"], ["√3", "raiz(3)", "f", "1,73205…"]],
                [["x²", "^2", "f", "ao quadrado"], ["{k}", "{k0}", "f", "parâmetro — vira campo para digitar"]],
                [[";", "; ", "op", "separa os argumentos"], ["abs", "abs()", "f", "valor absoluto"]],
                [["%", " * 100", "op", "× 100"], ["±", " -", "op", "negativo"]]];
  const chunk = (a, n) => { const s = []; for (let i = 0; i < a.length; i += n) s.push(a.slice(i, i + n)); return s; };
  function teclas(dominio) {
    return [FUNCOES[dominio],
            [["C", "C", "ctl", "limpar"], ["⌫", "⌫", "ctl", "apagar"], ["(", "("], [")", ")"],
             ["j", " j ", "f", "1 ∠ 90°"], ["1/x", "1 / ()", "f", "inverso"]],
            ...chunk(NUMEROS, 4).map((l, i) => [...l, ...LADO[i]])];
  }

  // --- a gaveta --------------------------------------------------------------------
  let gaveta = null;
  let abaAtual = "calc";
  let painelAlvo = null;
  const alvo = () => painelAlvo || calc().escolhido() || null;
  //: O grupo escolhido em cada grandeza, para as teclas da fileira. Vale até
  //: ser trocado.
  const grupoEscolhido = { I: null, V: null };
  const estado = { nome: "", expressao: "", dominio: "onda", parametros: {}, relacoes: {},
                   emEdicao: null, ultima: null, semRelacao: [] };

  function montar() {
    gaveta = criar("aside", "calc-gaveta");
    const cab = criar("div", "cabeca");
    cab.append(criar("h3", null, "Calculadora"), botao("?", "calc-ajuda", AJUDA),
               botao("›", "fechar", "fechar", () => fechar()));
    const abas = criar("div", "calc-abas");
    for (const [k, t] of [["calc", "calculadora"], ["sug", "sugestões"], ["minhas", "minhas contas"]]) {
      const b = botao(t, "calc-aba", "", () => mostrarAba(k));
      b.dataset.aba = k;
      abas.append(b);
    }
    const corpo = criar("div", "calc-corpo");
    gaveta.append(cab, abas, corpo);
    document.body.append(gaveta);
    gaveta._corpo = corpo;
  }

  function mostrarAba(k) {
    abaAtual = k;
    for (const b of gaveta.querySelectorAll(".calc-aba")) b.classList.toggle("ligado", b.dataset.aba === k);
    gaveta._corpo.replaceChildren(k === "calc" ? painelCalculadora()
                                  : k === "sug" ? painelSugestoes() : painelMinhas());
  }

  const aberta = () => document.documentElement.classList.contains("calc-aberta");
  async function abrir(painel) {
    if (painel) painelAlvo = painel.id;
    if (!gaveta) { await carregarInfo(); montar(); mostrarAba("calc"); }
    // Uma gaveta à direita por vez: a dos ajustes do diferencial cede o lugar.
    document.dispatchEvent(new CustomEvent("osclab:gaveta", { detail: "calc" }));
    // A gaveta começa EMBAIXO da barra de cima, que continua inteira.
    const barra = document.getElementById("barra-de-cima");
    document.documentElement.style.setProperty("--calc-topo", `${barra ? barra.getBoundingClientRect().bottom : 0}px`);
    document.documentElement.classList.add("calc-aberta");
    setTimeout(() => window.dispatchEvent(new Event("resize")), 30);
    if (abaAtual === "calc") setTimeout(() => gaveta.querySelector(".calc-expr")?.focus(), 40);
  }
  function fechar() {
    document.documentElement.classList.remove("calc-aberta");
    setTimeout(() => window.dispatchEvent(new Event("resize")), 30);
  }

  document.addEventListener("osclab:gaveta", (ev) => {
    if (ev.detail !== "calc" && aberta()) fechar();
  });

  /* O CLIQUE FORA fecha só com o visor vazio e fora do gráfico. O clique
   * repassado pelo quadro da aba (`abas.js`) chega sem alvo: conta como
   * fora do gráfico. */
  document.addEventListener("pointerdown", (ev) => {
    if (!aberta() || estado.expressao.trim()) return;
    const t = ev.target;
    if (t instanceof Element) {
      if (t.closest(".calc-gaveta, dialog")) return;
      if (t.closest("button")?.querySelector(".icone-calculadora")) return;   // o botão alterna sozinho
      if (t.closest("main#graficos")) return;
    }
    fechar();
  }, true);

  // --- a aba CALCULADORA -------------------------------------------------------------
  function painelCalculadora() {
    const el = criar("div", "calc-calc");

    // o VISOR
    const visor = criar("div", `calc-visor ${estado.dominio}`);
    const l1 = criar("div", "calc-v1");
    const nome = criar("input", "calc-nome");
    nome.placeholder = "nome";
    nome.maxLength = 40;
    nome.value = estado.nome;
    nome.addEventListener("input", () => { estado.nome = nome.value; atualizarIgual(); });
    nome.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); criarConta(); } });
    const chave = criar("span", "calc-chave");
    for (const d of ["onda", "fasor"]) {
      chave.append(botao(d, `calc-dom ${d}` + (estado.dominio === d ? " ligado" : ""),
        d === "onda" ? "amostra a amostra: o resultado é uma onda" : "sobre o fasor de 60 Hz: Z = V ÷ I, S = V × conj(I)",
        () => trocarDominio(d)));
    }
    l1.append(nome, chave);
    const expr = criar("textarea", "calc-expr");
    expr.rows = 1;
    expr.spellcheck = false;
    expr.value = estado.expressao;
    expr.placeholder = estado.dominio === "fasor" ? "[VA] / [IA]" : "[VA] - [VB]";
    const sug = criar("div", "calc-sug");
    sug.hidden = true;
    const res = criar("div", "calc-res");
    const canvas = criar("canvas", "calc-previa");
    canvas.hidden = true;
    visor.append(l1, expr, sug, res, canvas);

    const params = criar("div", "calc-params");
    const fileira = criar("div", "calc-fileira-area");
    const lista = criar("div", "calc-lista-sinais");
    lista.hidden = true;
    const grade = criar("div", "calc-teclado");
    el.append(visor, params, fileira, lista, grade);

    function trocarDominio(d) { estado.dominio = d; mostrarAba("calc"); }

    // O visor cresce com a expressão até um teto, e depois rola.
    function crescer() {
      expr.style.height = "auto";
      expr.style.height = `${Math.min(expr.scrollHeight, 132)}px`;
    }

    function inserir(t, recuo = 0) {
      const i = expr.selectionStart ?? expr.value.length;
      const j = expr.selectionEnd ?? i;
      expr.value = expr.value.slice(0, i) + t + expr.value.slice(j);
      expr.focus();
      expr.selectionStart = expr.selectionEnd = i + t.length - recuo;
      aoMudar();
    }

    function apertar(txt) {
      if (txt === "C") { expr.value = ""; estado.parametros = {}; estado.relacoes = {}; aoMudar(); expr.focus(); return; }
      if (txt === "⌫") {
        const i = expr.selectionStart;
        if (i > 0) { expr.value = expr.value.slice(0, i - 1) + expr.value.slice(i); expr.selectionStart = expr.selectionEnd = i - 1; }
        aoMudar(); expr.focus(); return;
      }
      if (txt === "SINAL") { lista.hidden = !lista.hidden; desenharLista(); return; }
      const funcao = /\(/.test(txt) && /\)$/.test(txt) && !txt.startsWith("raiz(3");
      const i = expr.selectionStart, j = expr.selectionEnd;
      if (funcao && j > i) {                   // com seleção, a função a envolve
        const abre = txt.indexOf("(") + 1;
        expr.value = expr.value.slice(0, i) + txt.slice(0, abre) + expr.value.slice(i, j) + txt.slice(abre) + expr.value.slice(j);
        aoMudar(); return;
      }
      inserir(txt, funcao ? txt.length - txt.indexOf("(") - 1 : 0);
    }

    /* A FILEIRA: oito teclas de largura fixa, rótulo padronizado. Com mais de
     * uma trinca da mesma grandeza, o seletor de grupo vem acima. */
    function desenharFileira() {
      fileira.replaceChildren();
      const nomes = (info && info.nomes) || {};
      const grupos = nomes.grupos || {};
      const rotulos = nomes.rotulos || {};
      for (const g of ["I", "V"]) {
        const lista = grupos[g] || [];
        if (!grupoEscolhido[g] || !lista.includes(grupoEscolhido[g])) grupoEscolhido[g] = lista[0] || null;
        if (lista.length < 2) continue;
        const sel = criar("div", `calc-grupos ${g}`);
        sel.append(criar("span", "calc-grupos-g", g === "I" ? "I" : "V"));
        // Na tela só o grupo (pedido dele, 11/11/2026); o radical fica no hover.
        const rotulo = (gr) => gr;
        const dica = (gr) => `${gr} · ${rotulos[gr] || ""}`.replace(/ · $/, "");
        if (lista.length > 3) {
          // Mais de três trincas (um 487E tem cinco): lista suspensa curta.
          const s = criar("select", "calc-grupos-lista");
          for (const gr of lista) { const o = new Option(rotulo(gr), gr); o.title = dica(gr); s.append(o); }
          s.value = grupoEscolhido[g];
          s.title = dica(grupoEscolhido[g]);
          s.addEventListener("change", () => { grupoEscolhido[g] = s.value; desenharFileira(); });
          sel.append(s);
        } else {
          for (const gr of lista) {
            const b = botao(rotulo(gr), "calc-grupo" + (gr === grupoEscolhido[g] ? " ligado" : ""), dica(gr),
              () => { grupoEscolhido[g] = gr; desenharFileira(); });
            sel.append(b);
          }
        }
        fileira.append(sel);
      }
      const linha = criar("div", "calc-fileira");
      for (const t of nomes.fileira || []) {
        const nomeCompleto = t.opcoes[grupoEscolhido[t.grandeza]] || "";
        const b = botao(t.base, "calc-t sinal", nomeCompleto ? `[${nomeCompleto}]` : "", () => inserir(`[${nomeCompleto}]`));
        b.disabled = !nomeCompleto || (estado.dominio === "fasor" && !t.fasor);
        linha.append(b);
      }
      fileira.append(linha);
    }

    function desenharTeclado() {
      grade.replaceChildren();
      for (const linha of teclas(estado.dominio)) {
        for (const [r, x, c, d] of linha) grade.append(botao(r, `calc-t ${c || ""}`, d || "", () => apertar(x)));
      }
      const igual = botao("", "calc-t igual", "", () => criarConta());
      grade.append(igual);
    }
    function atualizarIgual() {
      const b = grade.querySelector(".calc-t.igual");
      if (!b) return;
      b.textContent = estado.emEdicao ? "= guardar" : "= criar";
      b.disabled = !(estado.ultima && estado.ultima.vale && (estado.nome.trim() || estado.emEdicao));
    }

    /* A lista da tecla «[ ]»: o nome do arquivo, cortado pela largura MEDIDA
     * (reticências do CSS) com o inteiro no hover, e o padronizado com o grupo
     * numa coluna fixa à direita. */
    function desenharLista() {
      lista.replaceChildren();
      if (lista.hidden) return;
      const busca = criar("input", "calc-busca");
      busca.placeholder = "procurar sinal";
      const ul = criar("div", "calc-lista");
      const pintar = () => {
        ul.replaceChildren();
        const q = busca.value.toUpperCase();
        for (const s of ((info && info.nomes && info.nomes.sinais) || [])) {
          if (estado.dominio === "fasor" && !s.fasor) continue;
          if (q && !s.escrever.toUpperCase().includes(q) && !s.padrao.toUpperCase().includes(q)) continue;
          const b = criar("button", "calc-item");
          b.type = "button";
          b.title = s.escrever;
          b.append(criar("span", "calc-item-nome", s.escrever), criar("span", "calc-item-padrao", s.padrao));
          b.addEventListener("click", () => { lista.hidden = true; desenharLista(); inserir(`[${s.escrever}]`); });
          ul.append(b);
        }
      };
      busca.addEventListener("input", pintar);
      lista.append(busca, ul);
      pintar();
      busca.focus();
    }

    // Tab completa o nome dentro do colchete
    let opcoes = [], marcada = 0;
    const colchete = () => {
      const antes = expr.value.slice(0, expr.selectionStart);
      const a = antes.lastIndexOf("["), f = antes.lastIndexOf("]");
      return a > f ? { inicio: a, texto: antes.slice(a + 1) } : null;
    };
    function mostrarSugestoes() {
      const c = colchete();
      if (!c || !info) { sug.hidden = true; return; }
      const q = c.texto.toUpperCase().trim();
      opcoes = ((info.nomes && info.nomes.completar) || [])
        .filter((n) => !q || n.toUpperCase().includes(q)).slice(0, 7);
      marcada = 0;
      sug.replaceChildren();
      opcoes.forEach((n, k) => {
        const d = criar("div", "calc-sug-item" + (k ? "" : " marcada"), n);
        d.title = n;
        d.addEventListener("mousedown", (ev) => { ev.preventDefault(); aceitar(k); });
        sug.append(d);
      });
      sug.hidden = !opcoes.length;
    }
    function aceitar(k) {
      const c = colchete(), n = opcoes[k];
      if (!c || !n) return;
      const depois = expr.value.slice(expr.selectionStart);
      expr.value = expr.value.slice(0, c.inicio) + `[${n}]` + depois.slice(depois.startsWith("]") ? 1 : 0);
      expr.selectionStart = expr.selectionEnd = c.inicio + n.length + 2;
      sug.hidden = true;
      aoMudar();
    }
    expr.addEventListener("keydown", (ev) => {
      if (!sug.hidden && ["Tab", "Enter", "ArrowDown", "ArrowUp"].includes(ev.key)) {
        ev.preventDefault();
        if (ev.key === "ArrowDown") marcada = Math.min(marcada + 1, opcoes.length - 1);
        else if (ev.key === "ArrowUp") marcada = Math.max(marcada - 1, 0);
        else { aceitar(marcada); return; }
        [...sug.children].forEach((c, k) => c.classList.toggle("marcada", k === marcada));
        return;
      }
      if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); criarConta(); }
    });
    expr.addEventListener("input", aoMudar);
    expr.addEventListener("click", mostrarSugestoes);
    expr.addEventListener("blur", () => setTimeout(() => { sug.hidden = true; }, 120));

    function aoMudar() { estado.expressao = expr.value; crescer(); mostrarSugestoes(); desenharParams(); conferir(); }

    /* Parâmetro {k0}: campo curto. A ORIGEM é um filete verde quando o número
     * veio do relé, com o texto no hover; «↺» volta ao do relé. TC sem relação
     * declarada: ⚠, o nome do canal e o campo da relação. */
    function desenharParams() {
      const nomes = [...new Set([...expr.value.matchAll(/\{([A-Za-z_][A-Za-z_0-9]{0,15})\}/g)].map((m) => m[1]))];
      for (const k of Object.keys(estado.parametros)) if (!nomes.includes(k)) delete estado.parametros[k];
      params.replaceChildren();
      for (const nomeP of nomes) {
        const s = info && info.sugeridos && info.sugeridos[nomeP];
        if (!estado.parametros[nomeP]) {
          estado.parametros[nomeP] = s ? { mod: s.mod, ang: s.ang, origem: s.origem } : { mod: "", ang: 0, origem: "digitado" };
        }
        const p = estado.parametros[nomeP];
        const f = criar("span", "calc-param");
        const m = criar("input", "calc-num"); m.value = virgula(p.mod); m.placeholder = estado.dominio === "fasor" ? "módulo" : "valor";
        const a = criar("input", "calc-num curto"); a.value = virgula(p.ang);
        const marca = () => {
          const lido = p.origem !== "digitado";
          f.classList.toggle("lido", lido);
          f.title = lido ? `${p.origem}${s ? ` — ${s.como}` : ""}` : "digitado";
        };
        const mudou = () => { p.mod = m.value; p.ang = a.value; p.origem = "digitado"; marca(); conferir(); };
        m.addEventListener("input", mudou);
        a.addEventListener("input", mudou);
        f.append(criar("code", null, nomeP), m);
        if (estado.dominio === "fasor") f.append(criar("span", null, "∠"), a, criar("span", null, "°"));
        if (s) {
          f.append(botao("↺", "calc-mini", `usar o do relé: ${virgula(s.mod)} ∠ ${virgula(s.ang)}° (${s.como})`, () => {
            estado.parametros[nomeP] = { mod: s.mod, ang: s.ang, origem: s.origem }; desenharParams(); conferir();
          }));
        }
        marca();
        params.append(f);
      }
      for (const s of estado.semRelacao) {
        const f = criar("span", "calc-param relacao");
        // A relação digitada aqui é do CANAL: vai gravada no registro e vale
        // na tela inteira (gráficos, fasorial, localização), não só nesta
        // conta. A `estado.relacoes` é de conta antiga, de antes disso — ela
        // continua valendo enquanto o canal não tiver relação no registro.
        const rotulo = s.grandeza === "V" ? "RTP" : "RTC";
        f.title = s.digitada
          ? `«${s.nome}»: ${rotulo} digitado ${s.digitada}, gravado com o registro. Vazio volta ao arquivo.`
          : `«${s.nome}»: o arquivo não declara a relação de TC/TP. Vazio, entra como gravado; digitada, fica gravada com o registro e vale em toda a tela.`;
        const r = criar("input", "calc-num relacao-digitavel"); r.placeholder = rotulo;
        r.value = s.digitada || (estado.relacoes[s.canal] ? virgula(estado.relacoes[s.canal]) : "");
        r.addEventListener("change", async () => {
          delete estado.relacoes[s.canal];
          if (calc().gravarRelacoes) await calc().gravarRelacoes({ canais: { [s.canal]: r.value.trim() } });
          estado.semRelacao = []; conferir();
        });
        // Digitada não leva ⚠ nem o filete do «lido»: é a marca de digitado
        // dos parâmetros desta gaveta.
        if (!s.digitada) f.append(criar("span", "calc-alerta", "⚠"));
        f.append(criar("code", "calc-param-canal", s.nome), r);
        params.append(f);
      }
    }

    function contaAtual() {
      const p = {};
      for (const [k, v] of Object.entries(estado.parametros)) {
        p[k] = { mod: String(v.mod).replace(",", "."), ang: String(v.ang || 0).replace(",", "."), origem: v.origem };
      }
      return { id: estado.emEdicao || "", nome: estado.nome.trim() || "nova", expressao: estado.expressao.trim(),
               dominio: estado.dominio, parametros: p, relacoes: { ...estado.relacoes } };
    }

    let pedido = null, seq = 0;
    function conferir() {
      clearTimeout(pedido);
      if (!expr.value.trim() || colchete()) {
        estado.ultima = null; res.replaceChildren(); canvas.hidden = true; atualizarIgual(); return;
      }
      pedido = setTimeout(async () => {
        const meu = ++seq;
        const enviada = expr.value;
        const r = await enviar("conferir", {
          conta: contaAtual(), contas: calc().contas(), lado: calc().lado(), estimador: calc().estimador(),
          t1: cursoresAgora[0], t2: cursoresAgora[1],
          colunas: Math.min(900, Math.round((visor.clientWidth || 360) * (window.devicePixelRatio || 1))),
        });
        if (meu !== seq || !el.isConnected) return;
        estado.ultima = r;
        // `[IA]` digitado vira o nome do canal por trás — quando o texto não
        // mudou desde o pedido e não há colchete aberto.
        if (r.expandida && r.expandida !== enviada.trim() && expr.value === enviada && !colchete()) {
          expr.value = r.expandida;
          estado.expressao = r.expandida;
          expr.selectionStart = expr.selectionEnd = expr.value.length;
          crescer();
        }
        if (JSON.stringify(r.sem_relacao || []) !== JSON.stringify(estado.semRelacao)) {
          estado.semRelacao = r.sem_relacao || [];
          desenharParams();
        }
        desenharResultado(r);
        desenharPrevia(r);
        atualizarIgual();
      }, 200);
    }
    ouvintesDeCursor.add(() => { if (el.isConnected && expr.value.trim()) conferir(); });

    /* O RESULTADO: o valor no cursor 1 grande e o do cursor 2 menor, numa
     * linha própria do visor (a expressão comprida não o empurra). O que a
     * conta é, de que canais saiu e as notas: no hover. */
    function desenharResultado(r) {
      res.replaceChildren();
      if (!r.vale) { res.append(criar("span", "calc-erro", r.erro || "")); return; }
      const [ressalvas, notas] = separar(r.avisos);
      const celulas = (r.valores && r.valores.celulas) || [];
      const um = (c, k) => {
        const s = criar("span", k ? "calc-r2" : "calc-r1");
        if (!c) { s.textContent = k ? "" : (r.unidade || "—"); return s; }
        s.append(criar("span", "calc-n", String(k + 1)), criar("span", null, c.valor));
        if (c.angulo && c.angulo !== "—") s.append(criar("span", "calc-ang", ` ∠ ${c.angulo}`));
        s.title = [c.qual, c.fasor ? `60 Hz: ${c.fasor}` : "", c.retangular].filter(Boolean).join("\n");
        return s;
      };
      res.append(um(celulas[0], 0));
      if (celulas[1]) res.append(um(celulas[1], 1));
      const linhas = [];
      if (estado.dominio === "fasor") {
        linhas.push(r.real ? "valor real na curva" : "módulo na curva");
        if (!r.real) linhas.push(r.giro === 0 ? "ângulo absoluto" : r.giro === 1 ? "ângulo contra a referência" : "ângulo não se lê");
      } else {
        linhas.push(r.alternado ? "senoidal" : "não senoidal");
      }
      if ((r.fontes || []).length) linhas.push("sai de " + r.fontes.map((f) => `«${f}»`).join(", "));
      res.title = [...linhas, ...notas].join("\n");
      if (ressalvas.length) { const a = criar("span", "calc-alerta", "⚠"); a.title = ressalvas.join("\n"); res.append(a); }
    }

    function desenharPrevia(r) {
      if (!r.vale || !r.t) { canvas.hidden = true; return; }
      canvas.hidden = false;
      const dpr = window.devicePixelRatio || 1;
      const L = Math.max(100, visor.clientWidth - 24), H = 44;
      canvas.width = L * dpr; canvas.height = H * dpr;
      canvas.style.width = `${L}px`; canvas.style.height = `${H}px`;
      const g = canvas.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, L, H);
      const css = getComputedStyle(document.documentElement);
      const x = (t) => ((t - r.t0) / (r.t1 - r.t0 || 1)) * (L - 2) + 1;
      const y = (v) => H - 4 - ((v - r.y0) / (r.y1 - r.y0 || 1)) * (H - 8);
      g.strokeStyle = css.getPropertyValue(estado.dominio === "fasor" ? "--calc-visor-fasor" : "--calc-visor-onda").trim();
      g.lineWidth = 1.2;
      g.beginPath();
      let solto = true;
      r.t.forEach((t, k) => {
        const v = r.y[k];
        if (v === null) { solto = true; return; }
        if (solto) g.moveTo(x(t), y(v)); else g.lineTo(x(t), y(v));
        solto = false;
      });
      g.stroke();
      g.strokeStyle = css.getPropertyValue("--calc-visor-apagado").trim();
      g.setLineDash([2, 3]);
      cursoresAgora.forEach((t) => {
        if (t === null || t === undefined) return;
        g.beginPath(); g.moveTo(x(t), 0); g.lineTo(x(t), H); g.stroke();
      });
      g.setLineDash([]);
      canvas.title = `registro inteiro · ${r.faixa}`;
    }

    async function criarConta() {
      if (!estado.ultima || !estado.ultima.vale) return;
      if (!estado.nome.trim() && !estado.emEdicao) { nome.focus(); return; }
      const c = contaAtual();
      const lista = [...calc().contas()];
      if (estado.emEdicao) {
        calc().trocar(lista.map((x) => (x.id === estado.emEdicao ? { ...c, id: estado.emEdicao } : x)));
      } else {
        // A conta nova vai SÓ para a lista: nada entra num gráfico porque o
        // programa sabe calcular — quem a põe é o usuário, pelo «+ sinal»
        // (Calculados) ou pelo → de «minhas contas».
        c.id = calc().novoId();
        calc().trocar([...lista, c]);
      }
      const criada = !estado.emEdicao;
      await calc().recarregar();
      Object.assign(estado, { nome: "", expressao: "", parametros: {}, relacoes: {}, emEdicao: null,
                              ultima: null, semRelacao: [] });
      avisarContas();
      mostrarAba("calc");
      // Uma linha no lugar do resultado, que some quando se volta a digitar.
      if (criada) {
        gaveta.querySelector(".calc-res")?.append(
          criar("span", "calc-feito", `«${c.nome}» criada — está no «+ sinal», em Calculados`));
      }
    }

    desenharFileira();
    desenharTeclado();
    desenharParams();
    setTimeout(crescer, 0);
    if (estado.expressao) conferir(); else atualizarIgual();
    return el;
  }

  function editar(c) {
    Object.assign(estado, {
      nome: c.nome, expressao: c.expressao, dominio: c.dominio || "onda", emEdicao: c.id,
      parametros: Object.fromEntries(Object.entries(c.parametros || {}).map(([k, v]) => [k, { ...v }])),
      relacoes: { ...(c.relacoes || {}) }, semRelacao: [],
    });
    mostrarAba("calc");
  }

  // --- a aba SUGESTÕES: nome + uma linha; clicar leva para o visor ----------------
  function painelSugestoes() {
    const el = criar("div", "calc-sugestoes");
    if (!info) return el;
    const porCategoria = new Map();
    for (const m of info.modelos) {
      if (!porCategoria.has(m.categoria)) porCategoria.set(m.categoria, []);
      porCategoria.get(m.categoria).push(m);
    }
    for (const [categoria, lista] of porCategoria) {
      el.append(criar("div", "calc-titulo", categoria));
      for (const m of lista) {
        const l = criar("div", `calc-modelo ${m.dominio}` + (m.cabe ? "" : " nao-cabe"));
        l.title = m.cabe ? m.instanciada : m.motivo;
        l.append(criar("span", "calc-modelo-nome", m.nome), criar("span", "calc-modelo-desc", m.cabe ? m.descricao : ""));
        if (!m.cabe) l.append(criar("span", "calc-alerta", "⚠"));
        if (m.de === "seu") {
          l.append(botao("×", "calc-mini", "apagar este modelo", async (ev) => {
            ev.stopPropagation();
            await enviar(`modelos/${encodeURIComponent(m.id)}`, null, "DELETE");
            await carregarInfo();
            mostrarAba("sug");
          }));
        }
        if (m.cabe) {
          l.addEventListener("click", () => {
            Object.assign(estado, { nome: m.nome, expressao: m.instanciada, dominio: m.dominio,
                                    parametros: {}, relacoes: {}, emEdicao: null, semRelacao: [] });
            mostrarAba("calc");
          });
        }
        el.append(l);
      }
    }
    return el;
  }

  // --- a aba MINHAS CONTAS: nome e valor; ações no hover ---------------------------
  function painelMinhas() {
    const el = criar("div", "calc-minhas");
    let linhas = [];
    async function atualizar() {
      if (!el.isConnected) return;
      const contas = calc().contas();
      linhas = contas.length ? ((await enviar("valores", {
        contas, lado: calc().lado(), estimador: calc().estimador(), t1: cursoresAgora[0], t2: cursoresAgora[1],
      })).linhas || []) : [];
      desenhar();
    }
    function desenhar() {
      el.replaceChildren();
      for (const c of calc().contas()) {
        const v = linhas.find((x) => x.id === c.id) || {};
        const l = criar("div", `calc-conta ${c.dominio || "onda"}`);
        const nome = criar("span", "calc-conta-nome", c.nome);
        nome.title = c.expressao;
        const valor = criar("span", "calc-conta-val");
        const x = (v.celulas || [])[0];
        if (v.erro) { valor.textContent = "erro"; valor.title = v.erro; valor.classList.add("erro"); }
        else if (x) {
          valor.textContent = x.valor + (x.angulo && x.angulo !== "—" ? ` ∠ ${x.angulo}` : "");
          valor.title = [x.qual, x.fasor, x.retangular].filter(Boolean).join("\n");
        }
        const acoes = criar("span", "calc-acoes");
        acoes.append(
          botao("✎", "calc-mini", "editar no visor", () => editar(c)),
          botao("→", "calc-mini", "pôr no gráfico escolhido", async () => {
            calc().porNoPainel(alvo(), `${c.id}:instantaneo`); await calc().recarregar();
          }),
          botao("☆", "calc-mini", "guardar como modelo: fora do registro, com os nomes padronizados", async () => {
            const g = await enviar("generalizar", { expressao: c.expressao, contas: calc().contas() });
            const preso = g.presos.length ? `\n\nPreso ao nome do relé: ${g.presos.join(", ")}.` : "";
            if (!window.confirm(`Guardar «${c.nome}» como modelo:\n\n${g.expressao}${preso}`)) return;
            await enviar("modelos", { nome: c.nome, expressao: g.expressao, dominio: c.dominio,
                                      parametros: Object.keys(c.parametros || {}) });
            await carregarInfo();
          }),
          botao("×", "calc-mini", "tirar a conta (e o que ela desenhava)", async () => {
            calc().tirar(c.id); await calc().recarregar(); avisarContas();
          }));
        l.append(nome);
        const [ressalvas] = separar(v.avisos);
        if (ressalvas.length) { const a = criar("span", "calc-alerta", "⚠"); a.title = ressalvas.join("\n"); l.append(a); }
        l.append(valor, acoes);
        el.append(l);
      }
    }
    ouvintesDeCursor.add(() => { clearTimeout(el._t); el._t = setTimeout(atualizar, 120); });
    ouvintesDeContas.add(atualizar);
    setTimeout(atualizar, 0);
    return el;
  }

  window.osclabCalculadora = {
    alternar(painel) { if (aberta()) fechar(); else abrir(painel); },
    aberta,
    // usado pelo teste de navegador (`tests/navegador/calculadora.mjs`)
    aba: (k) => mostrarAba(k),
  };
})();
