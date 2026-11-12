/* A janela «refinar» da seq. negativa de dois terminais (variante 11 da
 * maquete, aprovada em 11/11/2026).
 *
 * Os números todos vêm de `/api/onda/<a>/refino` (`plot/refino.py`, em cima
 * de `faultloc/refino.py`): a janela de tempo (os gestos vão como GESTO, e
 * `plot/navegacao` decide), a escala de cada gráfico, as curvas reduzidas por
 * coluna de pixel, o deslocamento de B (caído numa amostra de B), V2/I2 e o km
 * em cada cursor, já escritos. Aqui só se converte valor em pixel.
 *
 * Barra: «vista ▾» (trifásico, ou monofásico com a fase), «sequência»
 * (liga/desliga: cada gráfico troca o conteúdo pela sequência negativa dele),
 * «alinhar: automático | manual». No manual: «mover: A | B», o deslocamento,
 * −1/+1 amostra (no terminal escolhido) e «marcar início».
 *
 * Gestos: roda amplia no mouse; arrastar anda a janela — no MANUAL, arrastar
 * move o registro inteiro do terminal escolhido, e o cursor se pega pela
 * etiqueta numerada (acima da moldura) ou pelas teclas 1/2; botão direito
 * volta à janela inteira; clique põe o cursor ativo; ←/→ andam uma amostra
 * de A (Shift, um ciclo); Esc fecha o menu, desarma a marcação, tira os
 * cursores e, sem nada disso, fecha a janela.
 *
 * O deslocamento MANUAL escolhido aqui vale para o painel localizador
 * (decidido em 11/11/2026) e fica GRAVADO ao lado do registro: cada mudança
 * dele vai ao servidor (`/api/onda/<a>/refino-alinhamento`), e só depois de
 * gravada a oscilografia é avisada por `postMessage` («refino-alinhamento»)
 * para pedir a localização de novo. Voltar ao automático APAGA o gravado.
 * A janela abre no que estiver gravado (`data-manual`).
 */
(() => {
  "use strict";
  const shaA = document.body.dataset.a, shaB = document.body.dataset.b;
  //: O contexto que o painel deixou: a linha em uso (a mesma do painel).
  let ctx = {};
  try { ctx = JSON.parse(sessionStorage.getItem(`osclab:refino:${shaA}:${shaB}`) || "{}") || {}; } catch (_e) { ctx = {}; }
  const $ = (id) => document.getElementById(id);
  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined && texto !== null) el.textContent = texto;
    return el;
  };
  const token = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim() || "#888";
  const virgula = (x, c) => (x === null || x === undefined || !isFinite(x)) ? "—"
    : x.toFixed(c).replace("-", "−").replace(".", ",");

  // --- o estado ------------------------------------------------------------------
  const estado = {
    vista: "tri", seq: false, fase: "A", s: "A",
    de: null, ate: null, t1: null, t2: null, ativo: 1,
    alinhar: "auto", manual: {}, armado: null, digitados: { A: {}, B: {} },
  };
  // O alinhamento manual GRAVADO do par: a janela abre no manual com ele.
  const gravado = document.body.dataset.manual ? parseFloat(document.body.dataset.manual) : NaN;
  if (isFinite(gravado)) {
    estado.alinhar = "manual";
    estado.manual = { d: gravado };
  }
  let pacote = null;
  let emVoo = false, deNovo = null;
  //: O último deslocamento gravado (null: nenhum, vale o automático;
  //: undefined: a primeira resposta ainda não veio).
  let avisado;
  /** Grava o manual ao lado do registro (`null` apaga) e avisa o painel. */
  async function avisarPainel() {
    const al = pacote.alinhamento;
    const d = al.modo === "manual" && al.manual.d != null ? al.d : null;
    // A primeira resposta é o que JÁ está gravado (na grade deste B): abrir
    // a janela não grava nada.
    if (avisado === undefined) { avisado = isFinite(gravado) ? d : null; if (d === avisado) return; }
    if (d === avisado || (d != null && avisado != null && Math.abs(d - avisado) < 1e-12)) return;
    const antes = avisado;
    avisado = d;
    try {
      const r = await fetch(`/api/onda/${shaA}/refino-alinhamento`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ b: shaB, d }),
      });
      if (!r.ok) throw new Error((await r.json()).erro || "falhou");
    } catch (e) {
      avisado = antes;
      $("rf-chaves").append(criar("span", "rf-aviso", `o alinhamento não foi gravado (${e.message})`));
      return;
    }
    window.parent.postMessage({ tipo: "refino-alinhamento", b: shaB, d }, location.origin);
  }
  let mouseT = null;
  let arrastoPx = 0;                    // o pan, enquanto a mão arrasta
  const arrastoTer = { A: 0, B: 0 };    // um terminal, enquanto a mão o arrasta
  let mover = "B";                      // qual terminal o arrasto (e o ±1) mexe
  let animB = 0;                        // B ainda a caminho da posição nova (s)
  let semAnimar = false;
  let arrasto = null;
  let menuAberto = null;
  const tri = () => estado.vista === "tri";
  const manual = () => pacote && pacote.alinhamento.modo === "manual";

  function corpoDoPedido(gesto) {
    const grafs = $("rf-graficos");
    const larg = Math.max(300, (grafs ? grafs.clientWidth : 900) - 76);
    return {
      b: shaB, vista: estado.vista, seq: estado.seq, fase: estado.fase,
      modo: estado.alinhar, manual: estado.manual, s: estado.s,
      de: estado.de, ate: estado.ate, gesto: gesto || null, t1: estado.t1, t2: estado.t2,
      linha: ctx.linha || null, digitados: estado.digitados,
      // o «alinhar por» da aba: o automático daqui é o do painel
      alinhar: ctx.alinhar || null,
      colunas: Math.round(larg * (window.devicePixelRatio || 1)),
    };
  }

  async function pedir(gesto) {
    if (emVoo) { deNovo = gesto || deNovo || {}; return; }
    emVoo = true;
    try {
      const r = await fetch(`/api/onda/${shaA}/refino`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpoDoPedido(gesto)),
      });
      const novo = await r.json();
      if (!r.ok) throw new Error(novo.erro || "falhou");
      const dAntes = pacote ? pacote.alinhamento.d : null;
      pacote = novo;
      estado.de = pacote.janela.de;
      estado.ate = pacote.janela.ate;
      // Com a mão segurando um cursor a resposta NÃO refaz os gráficos:
      // desenhar() troca os <canvas>, e o que tinha a captura do ponteiro
      // sumia no meio do arrasto. Só números e pintura; a posição é da mão.
      if (arrasto && arrasto.tipo === "cursor") {
        barra(); valores(); pintarTudo();
      } else {
        if (pacote.cursores.t1) estado.t1 = pacote.cursores.t1.t;
        if (pacote.cursores.t2) estado.t2 = pacote.cursores.t2.t;
        arrastoPx = 0;
        desenhar();
      }
      // B anda INTEIRO: as fases dele, corrente e tensão, deslizam juntas
      if (dAntes != null && !semAnimar && Math.abs(pacote.alinhamento.d - dAntes) > 1e-9) animar(pacote.alinhamento.d - dAntes);
      semAnimar = false;
      avisarPainel();
    } catch (e) {
      $("rf-chaves").replaceChildren(criar("span", "rf-aviso", `o servidor não respondeu (${e.message}) — reinicie o OscLab`));
    }
    emVoo = false;
    if (deNovo) { const g = deNovo; deNovo = null; pedir(Object.keys(g).length ? g : null); }
  }

  function animar(dt) {
    const t0 = performance.now(), dur = 520;
    const passo = (agora) => {
      const f = Math.max(0, 1 - (agora - t0) / dur);
      animB = dt * f * f * (3 - 2 * f);
      pintarTudo();
      if (f > 0) requestAnimationFrame(passo); else { animB = 0; pintarTudo(); }
    };
    requestAnimationFrame(passo);
  }

  // --- peças da barra ------------------------------------------------------------
  function botao(texto, titulo, fazer, classe) {
    const b = criar("button", "rf-botao" + (classe ? ` ${classe}` : ""), texto);
    b.type = "button";
    if (titulo) b.title = titulo;
    b.addEventListener("click", (e) => { e.stopPropagation(); fazer(e); });
    return b;
  }
  function segmentado(opcoes, atual, escolher, classe) {
    const p = criar("span", classe || "rf-par");
    for (const [valor, texto, titulo] of opcoes) {
      const b = criar("button", valor === atual ? "aceso" : "", texto);
      b.type = "button";
      if (titulo) b.title = titulo;
      b.addEventListener("click", () => escolher(valor));
      p.append(b);
    }
    return p;
  }
  function fecharMenu() {
    if (!menuAberto) return;
    const l = menuAberto.querySelector(".rf-menu-lista");
    if (l) l.remove();
    menuAberto = null;
  }
  document.addEventListener("pointerdown", (e) => { if (menuAberto && !menuAberto.contains(e.target)) fecharMenu(); });

  const TITULO_TRI = "Quatro gráficos: correntes de A, de B, tensões de A, de B — três fases cada.";
  const TITULO_MONO = "Dois gráficos, corrente e tensão, com A e B sobrepostos — uma fase só.";

  function menuDaVista() {
    const caixa = criar("span", "rf-menu");
    const rot = tri() ? "trifásico" : estado.seq ? "monofásico" : `monofásico · fase ${estado.fase}`;
    const b = botao(`vista: ${rot} ▾`, "Trifásico, ou monofásico com a fase.", () => {
      if (menuAberto === caixa) { fecharMenu(); return; }
      fecharMenu();
      const lista = criar("div", "rf-menu-lista");
      const item = (texto, aceso, titulo, fazer, inerte) => {
        const li = criar("button", "rf-menu-item" + (aceso ? " aceso" : ""), (aceso ? "● " : "") + texto);
        li.type = "button";
        li.title = titulo;
        li.disabled = !!inerte;
        li.addEventListener("click", (e) => { e.stopPropagation(); fecharMenu(); fazer(); });
        lista.append(li);
      };
      item("trifásico", tri(), TITULO_TRI, () => { estado.vista = "tri"; estado.armado = null; pedir(); });
      for (const f of "ABC") {
        item(`monofásico · fase ${f}`, !tri() && estado.fase === f && !estado.seq,
          estado.seq ? "Na sequência não há fase: I2 e V2 saem das três." : TITULO_MONO,
          () => { estado.fase = f; estado.vista = "mono"; estado.armado = null; pedir(); });
      }
      caixa.append(lista);
      menuAberto = caixa;
    });
    caixa.append(b);
    return caixa;
  }
  function botaoSeq() {
    return botao("sequência", "Troca o conteúdo de cada gráfico pela sequência negativa dele (I2, V2).",
      () => { estado.seq = !estado.seq; fecharMenu(); pedir(); }, estado.seq ? "aceso" : "");
  }

  function dicaDoAlinhamento() {
    const al = pacote.alinhamento, tx = al.txt, cf = al.confere;
    return [`B deslocado de ${tx.usado} ms (${al.modo === "auto" ? `automático, pelo ${al.auto.nome}` : `manual; o automático dava ${tx.auto} ms`}).`,
      `Precisão: 1 amostra de B (${tx.passo_b} ms).`,
      tx.relogio ? `O relógio de B difere ${tx.relogio} ms do de A.` : "",
      cf ? `Correlação de |I2|: ${tx.confere} ms${cf.mistura ? " (não vale como conferência: um terminal é filtrado pelo relé)" : ""}.` : "",
      "O deslocamento daqui é conferência: não muda o painel."].filter(Boolean).join("\n");
  }

  // Move o registro INTEIRO de um terminal `dt` segundos para a DIREITA na
  // tela (todas as fases, corrente e tensão). B: d − dt. A: d + dt, e a
  // janela anda junto, para B ficar parado e A ser o que se mexe.
  function moverTerminal(ter, dt, arrastado) {
    const al = pacote.alinhamento;
    const d = al.manual.d ?? al.d;
    estado.alinhar = "manual";
    estado.armado = null;
    if (ter === "B") estado.manual = { d: d - dt };
    else {
      estado.manual = { d: d + dt };
      estado.de -= dt; estado.ate -= dt;
      if (estado.t1 != null) estado.t1 -= dt;
      if (estado.t2 != null) estado.t2 -= dt;
    }
    semAnimar = !!arrastado;
    pedir();
  }

  // «alinhar: automático | manual». No automático só o ⚠ quando a
  // correlação discorda (o hover dá o valor; o clique passa ao manual com
  // ele). No manual: «mover: A | B», o deslocamento, ±1 amostra, marcar início.
  function chaveDoAlinhamento() {
    const al = pacote.alinhamento, tx = al.txt, cf = al.confere;
    const g = criar("span", "rf-grupo rf-alinhar");
    g.append(criar("span", "rf-rotulo", "alinhar"));
    const noManual = al.modo === "manual" || !!estado.armado;
    const chave = segmentado([["auto", "automático", "B deslocado pelo início da falta de cada um."],
                              ["manual", "manual", "Você escolhe o deslocamento: arrastando, ±1 amostra ou marcando o início."]],
      noManual ? "manual" : "auto", (v) => {
        if (v === "auto") { estado.alinhar = "auto"; estado.armado = null; estado.manual = {}; pedir(); }
        else { estado.alinhar = "manual"; estado.manual = { d: al.d }; pedir(); }
      });
    chave.title = dicaDoAlinhamento();
    g.append(chave);
    const discorda = cf && cf.discorda && Math.abs(al.d - cf.d) > 0.25 * al.ciclo;
    if (!noManual) {
      if (discorda) {
        const av = criar("button", "rf-alerta", "⚠");
        av.type = "button";
        av.title = `A correlação de |I2| acha ${tx.confere} ms (${tx.dif} ms do automático). Clique para passar ao manual com esse valor.`;
        av.addEventListener("click", () => { estado.alinhar = "manual"; estado.manual = { d: cf.d }; pedir(); });
        g.append(av);
      }
      return g;
    }
    const gm = criar("span", "rf-grupo");
    gm.append(criar("span", "rf-rotulo", "mover"),
      segmentado([["A", "A", "O arrasto e o ±1 movem o registro de A."],
                  ["B", "B", "O arrasto e o ±1 movem o registro de B."]], mover,
        (v) => { mover = v; barra(); }, "rf-par rf-mover"));
    const desl = criar("span", "rf-desl");
    desl.append(document.createTextNode(`${mover} deslocado de `),
      criar("b", null, `${mover === "B" ? tx.usado : tx.menos_usado} ms`));
    desl.title = dicaDoAlinhamento() + "\nArraste no gráfico para mover o terminal; o cursor se pega pela etiqueta numerada (ou teclas 1 e 2).";
    const passo = mover === "B" ? al.passo_b : al.passo_a;
    const txp = mover === "B" ? tx.passo_b : tx.passo_a;
    g.append(gm, desl,
      botao("−1 amostra", `${mover} uma amostra para a esquerda (${txp} ms).`, () => moverTerminal(mover, -passo)),
      botao("+1 amostra", `${mover} uma amostra para a direita (${txp} ms).`, () => moverTerminal(mover, passo)),
      botao(estado.armado ? `clique no início em ${estado.armado}` : "marcar início",
        "Clique no início da falta em A e depois em B (corrente ou tensão). B se desloca inteiro.",
        () => { estado.armado = estado.armado ? null : "A"; desenhar(); }, estado.armado ? "armado" : ""));
    return g;
  }

  function barra() {
    const cab = $("rf-chaves");
    cab.replaceChildren();
    if (!pacote) return;
    cab.append(menuDaVista(), botaoSeq(), chaveDoAlinhamento());
  }

  // --- os gráficos -----------------------------------------------------------------
  const M = { esq: 62, dir: 14, topo: 16, baixo: 6, eixo: 18 };
  //: A partir de quantos pixels entre duas amostras cada uma ganha um ponto.
  const PX_POR_AMOSTRA = 6;
  const blocos = [];

  function cabecalho(g) {
    const cab = criar("div", "rf-graf-cab");
    cab.append(criar("span", "rf-t", g.titulo), criar("span", "rf-u", g.unidade));
    for (const s of g.series) {
      if (s.falta) { cab.append(criar("span", "rf-leg", `${s.nome}: ${s.aviso || "sem sinal"}`)); continue; }
      const l = criar("span", "rf-leg");
      const i = criar("i"); i.style.background = `var(${s.cor})`;
      l.append(i, document.createTextNode(s.nome));
      cab.append(l);
      if (s.env) {
        // a curva fina é a ONDA da sequência (Re{X2}·√2), não uma fase
        const l2 = criar("span", "rf-leg fina");
        const i2 = criar("i"); i2.style.background = `var(${s.cor})`;
        l2.append(i2, document.createTextNode("onda"));
        l2.title = "A onda de sequência negativa Re{X2}·√2 (fina); a grossa é o eficaz |X2|.";
        cab.append(l2);
      }
    }
    return cab;
  }

  function desenhar() {
    barra();
    const grafs = $("rf-graficos");
    grafs.replaceChildren();
    blocos.length = 0;
    if (!pacote) return;
    const lista = [...pacote.graficos];
    if (pacote.km_curva) lista.push({ id: "km", km: true });
    lista.forEach((g, k) => {
      const caixa = criar("div", "rf-graf" + (g.terminal ? ` terminal-${g.terminal.toLowerCase()}` : ""));
      if (g.km) {
        const cab = criar("div", "rf-graf-cab");
        const tk = criar("span", "rf-t", `km da seq. negativa no tempo · a partir de ${pacote.s}`);
        const kc = pacote.km_curva;
        if (kc.mediana != null) tk.title = `Mediana no platô: ${kc.txt.mediana} km (± ${kc.txt.dispersao}).`;
        cab.append(tk, criar("span", "rf-u", "km"));
        caixa.append(cab);
      } else {
        caixa.append(cabecalho(g));
      }
      if (g.vazio) {
        caixa.append(criar("div", "rf-vazio", `${g.vazio}${g.grandeza === "V" ? " — digite V2 deste terminal ao lado, ou a impedância de fonte atrás dele" : ""}`));
        grafs.append(caixa);
        return;
      }
      const cv = criar("canvas");
      caixa.append(cv);
      grafs.append(caixa);
      const ultimo = k === lista.length - 1;
      const alto = g.km ? 112 : (tri() ? 132 : 214);
      const b = { g, cv, alto: alto + (ultimo ? M.eixo : 0), ultimo, terminal: g.terminal || null };
      blocos.push(b);
      ligar(b);
    });
    pintarTudo();
    valores();
  }

  function pintarTudo() { for (const b of blocos) pintar(b); }
  function geometria(b) {
    const w = b.cv.clientWidth || b.cv.parentElement.clientWidth;
    return { w, h: b.alto, x0: M.esq, x1: w - M.dir, y0: M.topo, y1: b.alto - M.baixo - (b.ultimo ? M.eixo : 0) };
  }
  const emX = (G, t) => G.x0 + ((t - pacote.janela.de) / ((pacote.janela.ate - pacote.janela.de) || 1)) * (G.x1 - G.x0);
  const emT = (G, x) => pacote.janela.de + ((x - G.x0) / ((G.x1 - G.x0) || 1)) * (pacote.janela.ate - pacote.janela.de);

  function milimetrado(c, G) {
    c.fillStyle = token("--fundo");
    c.fillRect(G.x0, G.y0, G.x1 - G.x0, G.y1 - G.y0);
    for (const [passo, nome] of [[10, "--milimetrado-fino"], [50, "--milimetrado-medio"]]) {
      c.strokeStyle = token(nome);
      c.lineWidth = 1;
      c.beginPath();
      for (let k = passo; G.x0 + k < G.x1; k += passo) { if (passo === 10 && k % 50 === 0) continue; c.moveTo(G.x0 + k + .5, G.y0); c.lineTo(G.x0 + k + .5, G.y1); }
      for (let k = passo; G.y0 + k < G.y1; k += passo) { if (passo === 10 && k % 50 === 0) continue; c.moveTo(G.x0, G.y0 + k + .5); c.lineTo(G.x1, G.y0 + k + .5); }
      c.stroke();
    }
  }
  function linhaV(c, G, x, cor, tracejado, larg) {
    if (x < G.x0 - 1 || x > G.x1 + 1) return;
    c.save();
    c.strokeStyle = cor; c.lineWidth = larg || 1;
    if (tracejado) c.setLineDash(tracejado);
    c.beginPath(); c.moveTo(Math.round(x) + .5, G.y0); c.lineTo(Math.round(x) + .5, G.y1); c.stroke();
    c.restore();
  }

  function traco(c, G, emY, ts, vs, cor, larg, desl, amostras) {
    if (!ts || !ts.length) return;
    c.strokeStyle = cor; c.lineWidth = larg; c.lineJoin = "round";
    c.beginPath();
    let pena = false;
    for (let i = 0; i < ts.length; i++) {
      const v = vs[i];
      if (v === null || v === undefined) { pena = false; continue; }
      const x = emX(G, ts[i]) + desl, y = emY(v);
      if (!pena) { c.moveTo(x, y); pena = true; } else c.lineTo(x, y);
    }
    c.stroke();
    // VER AS AMOSTRAS: com o zoom deixando ≥ 6 px entre duas, um ponto em
    // cada — só quando a série não foi reduzida (cada ponto É amostra)
    if (amostras && ts.length > 1 && Math.abs(emX(G, ts[1]) - emX(G, ts[0])) >= PX_POR_AMOSTRA) {
      c.fillStyle = cor;
      const r = Math.max(1.6, larg * 0.9 + 0.6);
      for (let i = 0; i < ts.length; i++) {
        const v = vs[i];
        if (v === null || v === undefined) continue;
        const x = emX(G, ts[i]) + desl;
        if (x < G.x0 - r || x > G.x1 + r) continue;
        c.beginPath(); c.arc(x, emY(v), r, 0, 2 * Math.PI); c.fill();
      }
    }
  }

  function pintar(b) {
    const G = geometria(b);
    const dpr = window.devicePixelRatio || 1;
    b.cv.style.height = `${G.h}px`;
    b.cv.width = Math.round(G.w * dpr); b.cv.height = Math.round(G.h * dpr);
    const c = b.cv.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, G.w, G.h);
    milimetrado(c, G);
    const g = b.g;
    const esc = g.km ? pacote.km_curva.escala : g.escala;
    const emY = (v) => G.y1 - ((v - esc.min) / ((esc.max - esc.min) || 1)) * (G.y1 - G.y0);
    // o deslocamento de cada terminal na tela: o arrasto da mão e, para B, a
    // animação — o MESMO para todo sinal dele (o registro anda inteiro)
    const porSeg = (G.x1 - G.x0) / ((pacote.janela.ate - pacote.janela.de) || 1);
    const dTer = { A: arrastoTer.A, B: arrastoTer.B + animB * porSeg };
    c.font = "11px " + token("--mono");
    c.textBaseline = "middle"; c.textAlign = "right";
    for (const m of esc.marcas) {
      const y = Math.round(emY(m)) + .5;
      if (y < G.y0 - 1 || y > G.y1 + 1) continue;
      c.strokeStyle = token("--linha"); c.lineWidth = 1;
      c.beginPath(); c.moveTo(G.x0, y); c.lineTo(G.x1, y); c.stroke();
      c.fillStyle = token("--suave");
      c.fillText(virgula(m, Math.abs(m) >= 100 || m === Math.round(m) ? 0 : (Math.abs(m) >= 10 ? 1 : 2)), G.x0 - 6, y);
    }
    c.textAlign = "center";
    for (const mt of pacote.janela.marcas_t) {
      const x = emX(G, mt.t);
      if (x < G.x0 || x > G.x1) continue;
      c.strokeStyle = token("--linha");
      c.beginPath(); c.moveTo(Math.round(x) + .5, G.y0); c.lineTo(Math.round(x) + .5, G.y1); c.stroke();
      if (b.ultimo && x > G.x0 + 16) { c.fillStyle = token("--suave"); c.fillText(`${virgula(mt.ms, 0)}`, x, G.y1 + 11); }
    }
    if (b.ultimo) { c.textAlign = "right"; c.fillStyle = token("--suave"); c.fillText("ms", G.x0 - 6, G.y1 + 11); }

    c.save();
    c.beginPath(); c.rect(G.x0, G.y0, G.x1 - G.x0, G.y1 - G.y0); c.clip();
    if (g.km) {
      const kc = pacote.km_curva;
      if (kc.plato) {
        c.fillStyle = token("--loc-plato-fundo");
        const xa = emX(G, kc.plato[0]) + arrastoPx + dTer.A, xb = emX(G, kc.plato[1]) + arrastoPx + dTer.A;
        c.fillRect(xa, G.y0, xb - xa, G.y1 - G.y0);
      }
      traco(c, G, emY, kc.t, kc.v, token("--loc-seqneg"), 1.8, arrastoPx + dTer.A, false);
    } else {
      for (const s of g.series) {
        if (s.falta) continue;
        const desl = arrastoPx + dTer[s.terminal];
        const cor = token(s.cor);
        if (s.env) {
          c.globalAlpha = 0.55;
          traco(c, G, emY, s.t, s.onda, cor, 1, desl, false);
          c.globalAlpha = 1;
          traco(c, G, emY, s.t, s.env, cor, 2.2, desl, s.amostras);
        } else {
          traco(c, G, emY, s.t, s.onda, cor, 1.4, desl, s.amostras);
        }
      }
    }
    // o início da falta pelo detector, em A e em B
    const ev = pacote.eventos;
    const rot = (x, texto, linha) => { c.fillStyle = token("--suave"); c.textAlign = "left"; c.font = "10px " + token("--sans"); c.fillText(texto, x + 3, G.y0 + 8 + 12 * (linha || 0)); };
    if (ev.inicio_a != null && b.terminal !== "B") {
      const x = emX(G, ev.inicio_a) + arrastoPx + dTer.A;
      linhaV(c, G, x, token("--suave"), [3, 3]);
      if (!g.km) rot(x, "início A");
    }
    if (ev.inicio_b != null && b.terminal !== "A" && !g.km) {
      const x = emX(G, ev.inicio_b) + arrastoPx + dTer.B;
      linhaV(c, G, x, token("--suave"), [1, 3]);
      rot(x, "início B (detector)", b.terminal ? 0 : 1);
    }
    // as marcas do início (manual): a de B em TODO gráfico de B
    const mk = pacote.alinhamento.manual.marcas;
    if (mk && (manual() || estado.armado)) {
      if (mk.ta != null && b.terminal !== "B") linhaV(c, G, emX(G, mk.ta) + arrastoPx + dTer.A, token("--refino-marca"), [5, 3], 1.6);
      if (mk.tb != null && b.terminal !== "A" && !g.km) linhaV(c, G, emX(G, mk.tb - pacote.alinhamento.d) + arrastoPx + dTer.B, token("--refino-marca"), [5, 3], 1.6);
    }
    c.restore();
    for (const [k, t] of [[1, estado.t1], [2, estado.t2]]) {
      if (t == null) continue;
      const x = emX(G, t) + arrastoPx;
      const cor = token(k === 1 ? "--cursor-1" : "--cursor-2");
      linhaV(c, G, x, cor, null, estado.ativo === k ? 1.6 : 1);
      if (x >= G.x0 && x <= G.x1) {
        c.fillStyle = cor; c.font = "600 10px " + token("--mono"); c.textAlign = "center";
        c.fillRect(x - 6, G.y0 - 13, 12, 12);
        c.fillStyle = token("--fundo"); c.fillText(String(k), x, G.y0 - 7);
      }
    }
    c.strokeStyle = token("--borda"); c.lineWidth = 1;
    c.strokeRect(G.x0 + .5, G.y0 + .5, G.x1 - G.x0 - 1, G.y1 - G.y0 - 1);
  }

  // --- o gesto -------------------------------------------------------------------------
  function noDesenho(b, ev) {
    const G = geometria(b);
    const r = b.cv.getBoundingClientRect();
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    return { G, x, y, dentro: x >= G.x0 && x <= G.x1 && y >= G.y0 - 14 && y <= G.y1 };
  }

  function ligar(b) {
    const cv = b.cv;
    cv.addEventListener("wheel", (ev) => {
      const p = noDesenho(b, ev);
      if (!p.dentro) return;
      ev.preventDefault();
      // Proporcional ao deltaY, como em `onda.js` (`fatorDaRoda`): roda de
      // alta resolução manda vários eventos pequenos por entalhe.
      const escala = ev.deltaMode === 1 ? 33 : ev.deltaMode === 2 ? 600 : 1;
      const px = Math.max(-300, Math.min(300, (ev.deltaY || 0) * escala));
      pedir({ zoom: Math.pow(0.8, -px / 100), foco: emT(p.G, p.x) });
    }, { passive: false });
    cv.addEventListener("contextmenu", (ev) => { ev.preventDefault(); pedir({ tudo: true }); });
    cv.addEventListener("pointerleave", () => { mouseT = null; });
    cv.addEventListener("pointermove", (ev) => {
      const p = noDesenho(b, ev);
      if (p.dentro) mouseT = emT(p.G, p.x);
      if (!arrasto) {
        const pelaEtiqueta = !manual() || p.y < p.G.y0;
        const perto = p.dentro && pelaEtiqueta && [estado.t1, estado.t2].some((t) => t != null && Math.abs(emX(p.G, t) - p.x) <= 6);
        cv.style.cursor = !p.dentro ? "default" : estado.armado ? "crosshair"
          : perto || (manual() && !b.g.km) ? "ew-resize" : "grab";
      }
    });
    cv.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      const p = noDesenho(b, ev);
      if (!p.dentro) return;
      ev.preventDefault();
      try { cv.setPointerCapture(ev.pointerId); } catch (_e) { /* evento sintético */ }
      // no manual o arrasto é do TERMINAL: o cursor só se pega pela etiqueta
      const pelaEtiqueta = !manual() || p.y < p.G.y0;
      const perto = (estado.armado || !pelaEtiqueta) ? null
        : [[1, estado.t1], [2, estado.t2]].find(([, t]) => t != null && Math.abs(emX(p.G, t) - p.x) <= 6);
      const terminal = !perto && !estado.armado && manual() && !b.g.km;
      arrasto = { b, x0: p.x, G: p.G, tipo: perto ? "cursor" : terminal ? "terminal" : "pan",
                  ter: mover, cursor: perto ? perto[0] : null, moveu: false };
      if (perto) estado.ativo = perto[0];
    });
    cv.addEventListener("pointermove", (ev) => {
      if (!arrasto || arrasto.b !== b) return;
      const x = ev.clientX - cv.getBoundingClientRect().left;
      const dx = x - arrasto.x0;
      if (Math.abs(dx) > 3) arrasto.moveu = true;
      if (!arrasto.moveu) return;
      if (arrasto.tipo === "cursor") {
        const t = emT(arrasto.G, x);
        if (arrasto.cursor === 1) estado.t1 = t; else estado.t2 = t;
        pintarTudo();
        pedir();
      } else if (arrasto.tipo === "terminal") { arrastoTer[arrasto.ter] = dx; pintarTudo(); }
      else { arrastoPx = dx; pintarTudo(); }
    });
    cv.addEventListener("pointerup", (ev) => {
      if (!arrasto || arrasto.b !== b) return;
      const a = arrasto;
      arrasto = null;
      const x = ev.clientX - cv.getBoundingClientRect().left;
      const dt = (x - a.x0) / ((a.G.x1 - a.G.x0) || 1) * (pacote.janela.ate - pacote.janela.de);
      if (!a.moveu) { clique(b, emT(a.G, x)); return; }
      if (a.tipo === "pan") pedir({ andar: -dt });
      else if (a.tipo === "terminal") { arrastoTer.A = arrastoTer.B = 0; moverTerminal(a.ter, dt, true); }
      else pedir();
    });
    cv.addEventListener("pointercancel", () => {
      if (arrasto && arrasto.b === b) { arrasto = null; arrastoPx = 0; arrastoTer.A = arrastoTer.B = 0; pintarTudo(); }
    });
  }

  function clique(b, t) {
    if (b.g.km && estado.armado) return;
    if (estado.armado) {
      // marcar o início: um clique em A, outro em B; com os dois, B anda.
      // No monofásico os dois estão no mesmo gráfico: vale a ordem A, B.
      const mk = { ...(pacote.alinhamento.manual.marcas || {}) };
      const ter = b.terminal || estado.armado;
      if (ter === "A") { mk.ta = t; estado.armado = mk.tb == null ? "B" : null; }
      else { mk.tb = t + pacote.alinhamento.d; estado.armado = mk.ta == null ? "A" : null; }
      estado.manual = { ta: mk.ta ?? null, tb: mk.tb ?? null };
      if (mk.ta != null && mk.tb != null) { estado.alinhar = "manual"; estado.armado = null; }
      else estado.manual.d = pacote.alinhamento.d;
      pedir();
      return;
    }
    if (estado.ativo === 2) estado.t2 = t; else estado.t1 = t;
    pedir();
  }

  document.addEventListener("keydown", (ev) => {
    const alvo = ev.target;
    if (alvo && (alvo.tagName === "INPUT" || alvo.tagName === "TEXTAREA" || alvo.isContentEditable)) return;
    if (!pacote) return;
    if (ev.key === "1" || ev.key === "2") {
      if (mouseT == null) return;
      const k = Number(ev.key), chave = k === 1 ? "t1" : "t2";
      const perto = estado[chave] != null && Math.abs(estado[chave] - mouseT) < (pacote.janela.ate - pacote.janela.de) / 150;
      estado[chave] = perto ? null : mouseT;
      estado.ativo = k;
      pedir();
      ev.preventDefault();
    } else if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
      const chave = estado.ativo === 2 ? "t2" : "t1";
      if (estado[chave] == null) return;
      ev.preventDefault();
      estado[chave] += (ev.key === "ArrowRight" ? 1 : -1) * (ev.shiftKey ? pacote.alinhamento.ciclo : pacote.alinhamento.passo_a);
      pedir();
    } else if (ev.key === "Escape") {
      if (menuAberto) { fecharMenu(); return; }
      if (estado.armado) { estado.armado = null; desenhar(); return; }
      if (estado.t1 != null || estado.t2 != null) { estado.t1 = estado.t2 = null; pedir(); return; }
      fechar();
    }
  });

  function fechar() { window.parent.postMessage({ tipo: "refino-fechar" }, location.origin); }
  $("rf-fechar").addEventListener("click", fechar);

  // --- os números: o resultado, e V2/I2/ângulo de cada terminal ----------------
  const CAMPOS = [["v2", "|V2|", "kV"], ["i2", "|I2|", "A"], ["ang", "∠I2 − ∠V2", "°"]];
  let esperaDigitar = null;

  function campoDigitado(letra, chave, titulo) {
    const inp = criar("input", "rf-campo");
    const atual = estado.digitados[letra][chave];
    inp.value = atual ?? "";
    inp.placeholder = "digitar";
    if (atual) inp.classList.add("dig");
    inp.title = titulo || "Um número aqui vale no lugar do lido, em todos os instantes. Vazio volta ao lido.";
    inp.addEventListener("input", () => {
      const v = inp.value.trim();
      if (v) estado.digitados[letra][chave] = v; else delete estado.digitados[letra][chave];
      inp.classList.toggle("dig", !!v);
      clearTimeout(esperaDigitar);
      esperaDigitar = setTimeout(() => { const foco = document.activeElement; pedir(); manterFoco(foco); }, 450);
    });
    inp.dataset.chave = `${letra}:${chave}`;
    return inp;
  }
  function manterFoco(el) {
    if (!el || !el.dataset || !el.dataset.chave) return;
    const k = el.dataset.chave, pos = el.selectionStart;
    const volta = () => {
      const novo = document.querySelector(`input[data-chave="${k}"]`);
      if (novo && document.activeElement !== novo) { novo.focus(); try { novo.setSelectionRange(pos, pos); } catch (_e) { /* ok */ } }
    };
    setTimeout(volta, 60); setTimeout(volta, 250);
  }
  function celula(val, chave) {
    const td = criar("td", "n");
    if (!val) { td.textContent = "—"; return td; }
    td.textContent = val.txt[chave];
    const o = val.origem[chave];
    if (o === "digitado") { td.classList.add("dig"); td.title = `digitado (lido: ${val.lido.txt[chave]})`; }
    if (o === "fonte") { td.classList.add("fonte"); td.title = "da impedância de fonte digitada: V2 = −Z2fonte · I2"; }
    return td;
  }
  function blocoDoResultado() {
    const c1 = pacote.cursores.t1, c2 = pacote.cursores.t2;
    const bl = criar("div", "rf-bloco");
    const h = criar("h3", null, "Seq. negativa · dois terminais");
    const outro = estado.s === "A" ? "B" : "A";
    const de = criar("button", "rf-de-terminal", `a partir de ${estado.s} · ${pacote.nomes[estado.s]}`);
    de.type = "button";
    de.title = `Clique para contar a partir de ${outro} · ${pacote.nomes[outro]}.`;
    de.addEventListener("click", () => { estado.s = outro; pedir(); });
    h.append(de);
    bl.append(h);
    const tab = criar("table", "rf-tab rf-tab-resultado");
    const cab = criar("tr");
    cab.append(criar("th", null, ""), criar("th", "rf-c1", "cursor 1"), criar("th", "rf-c2", "cursor 2"));
    const th = criar("thead"); th.append(cab); tab.append(th);
    const tb = criar("tbody");
    const v = (c, k) => (c && c.km.km != null) ? c.km.txt[k] : "—";
    for (const [nome, k] of [["km", "km"], ["% da linha", "pct"]]) {
      const tr = criar("tr");
      tr.append(criar("td", null, nome), criar("td", "n", v(c1, k)), criar("td", "n", v(c2, k)));
      tb.append(tr);
    }
    tab.append(tb);
    bl.append(tab);
    const motivo = c1 ? c1.km.motivo : "ponha o cursor 1 no platô da falta (clique, ou tecla 1)";
    if (motivo) bl.append(criar("div", "rf-nota-bloco", motivo));
    return bl;
  }
  function blocoTerminal(letra) {
    const ter = pacote.terminais[letra === "A" ? 0 : 1];
    const c1 = pacote.cursores.t1, c2 = pacote.cursores.t2;
    const bl = criar("div", "rf-bloco");
    const h = criar("h3", null, `${letra} · ${ter.nome}`);
    h.append(criar("small", null, `${ter.por_ciclo_txt} am/ciclo`));
    bl.append(h);
    const tab = criar("table", "rf-tab");
    const cab = criar("tr");
    cab.append(criar("th", null, ""), criar("th", "rf-c1", "cursor 1"), criar("th", "rf-c2", "cursor 2"), criar("th", null, "digitar"));
    const th = criar("thead"); th.append(cab); tab.append(th);
    const tb = criar("tbody");
    for (const [chave, nome, uni] of CAMPOS) {
      const tr = criar("tr");
      const td = criar("td"); td.append(campoDigitado(letra, chave));
      tr.append(criar("td", null, `${nome} (${uni})`), celula(c1 && c1[letra], chave), celula(c2 && c2[letra], chave), td);
      tb.append(tr);
    }
    tab.append(tb);
    bl.append(tab);
    if (!ter.tem_v || estado.digitados[letra].z2f_mod) {
      const d = criar("div", "rf-nota-bloco");
      d.append(document.createTextNode(ter.tem_v ? "Z2 da fonte atrás de " : `${letra} não grava tensão: digite V2, ou Z2 da fonte atrás de ${letra} `),
        criar("b", null, "|Z| (Ω)"), document.createTextNode(" "),
        campoDigitado(letra, "z2f_mod", "Módulo da impedância de sequência negativa da fonte atrás do terminal, ohm primário."),
        document.createTextNode(" ∠ (°) "), campoDigitado(letra, "z2f_ang", "Ângulo da impedância de fonte, em graus."));
      bl.append(d);
    }
    return bl;
  }
  function valores() {
    const el = $("rf-valores");
    el.replaceChildren();
    if (!pacote) return;
    el.append(blocoDoResultado(), blocoTerminal("A"), blocoTerminal("B"));
  }

  // para o teste de navegador (tests/test_refino_navegador.py)
  window.__refino = () => pacote;
  window.__refinoEstado = () => estado;
  window.addEventListener("resize", () => { if (pacote) pintarTudo(); });
  window.addEventListener("storage", (e) => {
    if (e.key === "osclab-tema" && e.newValue) { document.documentElement.dataset.tema = e.newValue; if (pacote) desenhar(); }
  });
  pedir().then(() => {
    // o cursor 1 começa no meio do platô — onde a conta é mais estável
    const kc = pacote && pacote.km_curva;
    if (kc && kc.plato && estado.t1 == null) { estado.t1 = (kc.plato[0] + kc.plato[1]) / 2; pedir(); }
    else if (pacote && estado.t1 == null && pacote.eventos.inicio_a != null) {
      estado.t1 = pacote.eventos.inicio_a + 2.5 * pacote.alinhamento.ciclo; pedir();
    }
  });
})();
