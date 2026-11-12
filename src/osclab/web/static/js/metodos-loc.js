/* «? métodos» do painel localizador: as equações DESENHADAS (variante 06 da
 * maquete `maquete/metodos`, escolhida em 12/11/2026).
 *
 * Lado a lado: à esquerda os métodos, cada um com a cor da curva e o km dele;
 * à direita o escolhido — a frase, a equação principal desenhada ao lado do
 * esquema da linha S — m — R, as auxiliares, o detalhe, quando vale e o
 * «neste registro» escrito como conta (d = m · L = …). No fim da lista, «o
 * resultado e o trecho», com o texto de `ldl.sobre_o_resultado`.
 *
 * O servidor manda cada equação como árvore (`faultloc/equacoes.py`); aqui só
 * se pinta: fração com traço, índice, |·| e {·} que esticam, Im{}. Nenhum
 * número sai daqui — o km, o m e a conta com números vêm prontos. Passar o
 * mouse num símbolo acende o mesmo símbolo no método inteiro e diz o que ele
 * é. A fonte das equações é a STIX Two Text, embutida (`static/fontes`).
 *
 * Quem abre é o `onda.js` (`abrirAjudaMetodosLoc`), que passa o pacote do
 * localizador, as cores e a ordem dos métodos e o `fecharAoClicarFora`.
 */
"use strict";

window.OscMetodosLoc = (() => {
  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined && texto !== null) el.textContent = texto;
    return el;
  };
  const NS = "http://www.w3.org/2000/svg";
  const svg = (tag, at) => {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(at || {})) el.setAttribute(k, v);
    return el;
  };

  // ---- o desenhista de equações -------------------------------------------
  const PARES = { abs: ["|", "|"], par: ["(", ")"], chave: ["{", "}"] };
  const CAMINHOS = {
    abs: ["M5 0 L5 100", "M5 0 L5 100"],
    par: ["M9 0 Q0 50 9 100", "M1 0 Q10 50 1 100"],
    chave: ["M9 0 Q4 0 4 10 L4 40 Q4 50 0 50 Q4 50 4 60 L4 90 Q4 100 9 100",
            "M1 0 Q6 0 6 10 L6 40 Q6 50 10 50 Q6 50 6 60 L6 90 Q6 100 1 100"],
  };
  const temFrac = (no) => {
    if (!no) return false;
    if (no.t === "frac") return true;
    if (no.t === "r") return no.x.some(temFrac);
    if (no.t === "fn" || no.t === "d") return temFrac(no.x);
    return false;
  };
  /** O delimitador: o caractere, ou — em volta de fração — um traço em SVG
   *  que estica até a altura do que ele cerca. */
  function delim(k, lado, alto) {
    const s = criar("span", `eq-dl ${lado}${alto ? " alto" : ""}`);
    if (!alto) { s.textContent = PARES[k][lado === "esq" ? 0 : 1]; return s; }
    const g = svg("svg", { viewBox: "0 0 10 100", preserveAspectRatio: "none" });
    g.append(svg("path", { d: CAMINHOS[k][lado === "esq" ? 0 : 1] }));
    s.append(g);
    return s;
  }
  function desenhar(no) {
    switch (no.t) {
      case "r": { const s = criar("span", "eq-r"); no.x.forEach((x) => s.append(desenhar(x))); return s; }
      case "v": {
        const s = criar("span", "eq-v");
        // Δ é operador, não variável: reto, como num livro.
        if (no.x.startsWith("Δ")) s.append(criar("span", "eq-reto", "Δ"), document.createTextNode(no.x.slice(1)));
        else s.textContent = no.x;
        if (no.sub && no.sup) {
          const ss = criar("span", "eq-ss");
          ss.append(criar("span", "eq-sup", no.sup), criar("span", "eq-sub", no.sub));
          s.append(ss);
        } else {
          if (no.sub) s.append(criar("span", "eq-sub", no.sub));
          if (no.sup) s.append(criar("span", "eq-sup", no.sup));
        }
        if (no.id) s.dataset.sim = no.id;
        return s;
      }
      case "n": return criar("span", "eq-n", no.x);
      case "o": return criar("span", "eq-o", no.x);
      case "p": return criar("span", "eq-p", no.x);
      case "txt": return criar("span", "eq-txt", no.x);
      case "fn": {
        const s = criar("span", "eq-r");
        s.append(criar("span", "eq-fname", no.f), desenhar({ t: "d", k: "chave", x: no.x }));
        return s;
      }
      case "d": {
        const s = criar("span", "eq-d");
        const dentro = criar("span", "eq-dentro");
        dentro.append(desenhar(no.x));
        const alto = temFrac(no.x);
        s.append(delim(no.k, "esq", alto), dentro, delim(no.k, "dir", alto));
        return s;
      }
      case "frac": {
        const s = criar("span", "eq-frac");
        const a = criar("span", "eq-num"); a.append(desenhar(no.a));
        const b = criar("span", "eq-den"); b.append(desenhar(no.b));
        s.append(a, b);
        return s;
      }
      default: return criar("span", null, "");
    }
  }
  function equacao(arvore, rotulo) {
    const s = criar("span", "eq");
    s.append(desenhar(arvore));
    s.setAttribute("role", "math");
    s.setAttribute("aria-label", rotulo || "");
    return s;
  }

  // ---- o símbolo apontado: aceso no método inteiro, e a dica -----------------
  let dica = null;
  const tirarDica = () => { if (dica) { dica.remove(); dica = null; } };
  function ligarRealce(caixa, simbolos) {
    caixa.addEventListener("pointerover", (e) => {
      const el = e.target.closest && e.target.closest("[data-sim]");
      if (!el || !caixa.contains(el)) return;
      const sim = el.dataset.sim;
      caixa.querySelectorAll(`[data-sim="${CSS.escape(sim)}"]`).forEach((x) => x.classList.add("eq-aceso"));
      const desc = simbolos[sim];
      if (!desc) return;
      tirarDica();
      dica = criar("div", "eq-dica");
      const exemplo = criar("span", "eq");
      const copia = el.cloneNode(true);
      copia.classList.remove("eq-aceso");
      exemplo.append(copia);
      dica.append(exemplo, document.createTextNode(desc));
      (el.closest("dialog") || document.body).append(dica);
      const r = el.getBoundingClientRect();
      const w = dica.offsetWidth;
      dica.style.left = `${Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2))}px`;
      dica.style.top = `${r.bottom + 8}px`;
    });
    caixa.addEventListener("pointerout", (e) => {
      const el = e.target.closest && e.target.closest("[data-sim]");
      if (!el) return;
      caixa.querySelectorAll(".eq-aceso").forEach((x) => x.classList.remove("eq-aceso"));
      tirarDica();
    });
  }

  // ---- o esquema da linha S — m — R ------------------------------------------
  function rotuloSvg(x, y, base, sub, ancora, classe) {
    const t = svg("text", { x, y, "text-anchor": ancora || "middle" });
    if (classe) t.setAttribute("class", classe);
    const b = svg("tspan", {}); b.textContent = base;
    if (classe !== "ui") b.setAttribute("font-style", "italic");
    t.append(b);
    if (sub) {
      const s = svg("tspan", { dy: "3.5", "font-size": "9" }); s.textContent = sub;
      t.append(s);
    }
    return t;
  }
  function seta(g, x1, x2, y) {
    g.append(svg("line", { x1, y1: y, x2, y2: y, class: "seta" }));
    const dir = Math.sign(x2 - x1);
    g.append(svg("path", { d: `M${x2} ${y} l${-6 * dir} -3.2 l0 6.4 z`, class: "ponta" }));
  }
  /** O desenho da linha com a falta onde o método a pôs (`info.m`, do
   *  servidor). Converter m em pixel é a única conta daqui; fora da linha o
   *  ponto fica preso na ponta, e o número de verdade está na conta abaixo. */
  function esquema(mt, info, cor, rotulos) {
    const W = 300, H = 104, xs = 34, xr = 266, y = 46;
    const m = info.m == null ? null : Math.max(0, Math.min(1, info.m));
    const xf = xs + (m == null ? 0.5 : m) * (xr - xs);
    const g = svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: "esquema-lt" });
    g.style.setProperty("--cor-mt", cor);
    const dois = mt === "seqneg";
    g.append(svg("line", { x1: xs, y1: y - 16, x2: xs, y2: y + 16, class: "barra-se" }));
    g.append(svg("line", { x1: xr, y1: y - 16, x2: xr, y2: y + 16, class: "barra-se" }));
    g.append(svg("line", { x1: xs, y1: y, x2: xf, y2: y, class: "fio" }));
    g.append(svg("line", { x1: xf, y1: y, x2: xr, y2: y, class: dois ? "fio" : "fio apagado" }));
    // a falta
    g.append(svg("circle", { cx: xf, cy: y, r: 3.4, class: "ponto" }));
    if (dois) {
      g.append(svg("path", { d: `M${xf} ${y} l0 14 l-4 4 l8 2 l-4 4 l0 6`, class: "falta" }));
    } else {
      g.append(svg("path", { d: `M${xf} ${y} l0 8 l-4 2 l8 3 l-8 3 l8 3 l-4 2 l0 9`, class: "falta" }));
      g.append(rotuloSvg(xf + 8, y + 22, "R", "f", "start"));
    }
    g.append(svg("path", { d: `M${xf - 7} ${y + 34} l14 0 M${xf - 4.5} ${y + 37} l9 0 M${xf - 2} ${y + 40} l4 0`, class: "falta" }));
    // cotas: m·Z e (1−m)·Z
    const z = dois ? ["Z", "2L"] : ["Z", "1L"];
    const cy = y - 24;
    g.append(svg("line", { x1: xs, y1: cy + 4, x2: xf, y2: cy + 4, class: "cota" }));
    g.append(svg("line", { x1: xf, y1: cy, x2: xf, y2: cy + 8, class: "cota" }));
    const tm = svg("text", { x: (xs + xf) / 2, y: cy, "text-anchor": "middle" });
    const t1 = svg("tspan", { "font-style": "italic" }); t1.textContent = "m·" + z[0];
    const t2 = svg("tspan", { dy: "3.5", "font-size": "9" }); t2.textContent = z[1];
    tm.append(t1, t2);
    g.append(tm);
    if (dois) {
      g.append(svg("line", { x1: xf, y1: cy + 4, x2: xr, y2: cy + 4, class: "cota" }));
      const tr = svg("text", { x: (xf + xr) / 2, y: cy, "text-anchor": "middle" });
      const a = svg("tspan", {}); a.textContent = "(1−";
      const b = svg("tspan", { "font-style": "italic" }); b.textContent = "m";
      const c = svg("tspan", {}); c.textContent = ")·";
      const d = svg("tspan", { "font-style": "italic" }); d.textContent = z[0];
      const e = svg("tspan", { dy: "3.5", "font-size": "9" }); e.textContent = z[1];
      tr.append(a, b, c, d, e);
      g.append(tr);
    }
    // correntes e tensões nos terminais
    seta(g, xs + 6, xs + 30, y + 10);
    g.append(rotuloSvg(xs + 18, y + 24, "I", dois ? "2S" : "", "middle"));
    g.append(rotuloSvg(xs - 6, y - 20, "V", dois ? "2S" : "", "end"));
    if (dois) {
      seta(g, xr - 6, xr - 30, y + 10);
      g.append(rotuloSvg(xr - 18, y + 24, "I", "2R", "middle"));
      g.append(rotuloSvg(xr + 6, y - 20, "V", "2R", "start"));
    }
    g.append(rotuloSvg(xs, H - 6, rotulos.s || "S", "", "middle", "ui"));
    g.append(rotuloSvg(xr, H - 6, dois ? (rotulos.r || "R") : (rotulos.r_de_um || "R"), "", "middle", "ui"));
    g.setAttribute("role", "img");
    g.setAttribute("aria-label", m == null ? "linha S–R, posição da falta desconhecida"
      : `linha S–R, falta em m = ${info.m_txt}`);
    return g;
  }

  // ---- peças ---------------------------------------------------------------
  function kmDe(info) {
    if (info.km_txt) {
      const s = criar("span", "km-mt" + (info.fora ? " fora" : ""), `${info.km_txt} km`);
      s.title = [info.disp_txt ? `dispersão no platô ±${info.disp_txt} km` : "",
                 info.m_txt ? `m = ${info.m_txt}` : "", info.motivo || ""].filter(Boolean).join("\n");
      return s;
    }
    const s = criar("span", "km-mt sem", "sem número");
    s.title = info.motivo || "o método não deu número neste registro";
    return s;
  }
  function nesteRegistro(info) {
    if (info.neste) {
      const s = criar("span", "neste");
      s.append(equacao(info.neste, info.m_txt ? `d = ${info.km_txt} km` : ""));
      if (info.fora && info.motivo) s.append(criar("span", "prosa suave", info.motivo));
      return s;
    }
    return criar("span", "prosa suave", info.motivo || "sem número");
  }
  function pares(lista) {
    const g = criar("div", "pares");
    for (const [n, v] of lista) {
      if (!v) continue;
      g.append(criar("span", "rotulo", n));
      if (typeof v === "string") g.append(criar("span", "prosa", v)); else g.append(v);
    }
    return g;
  }

  /** O método escolhido, à direita. */
  function metodo(mt, info, p, cor) {
    const c = criar("div", "metodo-loc");
    c.dataset.mt = mt;
    c.style.setProperty("--cor-mt", cor);
    const cab = criar("div", "cabeca-mt");
    cab.append(criar("span", "marca-mt"), criar("span", "titulo-mt", info.nome || mt));
    if (p.resultado && p.resultado.metodo === mt) cab.append(criar("span", "selo-res", "resultado"));
    cab.append(criar("span", "regua"), criar("span", "qts", info.quantos || ""));
    c.append(cab, criar("div", "prosa suave", info.frase || info.como || ""));
    const eqs = info.equacoes || [];
    const bloco = criar("div", "bloco-eq");
    eqs.filter((e) => e.papel === "principal").forEach((e) => bloco.append(equacao(e.arvore, e.texto)));
    bloco.append(esquema(mt, info, cor, p.terminais_da_ajuda || {}));
    c.append(bloco);
    const aux = eqs.filter((e) => e.papel !== "principal");
    if (aux.length) {
      const a = criar("div", "eqs-aux");
      aux.forEach((e) => a.append(equacao(e.arvore, e.texto)));
      c.append(a);
    }
    c.append(pares([["detalhe", info.detalhe], ["quando vale", info.quando],
                    ["neste registro", nesteRegistro(info)]]));
    ligarRealce(c, info.simbolos || {});
    return c;
  }

  function fecho(miolo, p) {
    const cab = criar("div", "cabeca-mt");
    cab.append(criar("span", "titulo-mt", "O resultado e o trecho a patrulhar"), criar("span", "regua"));
    miolo.append(cab, pares(p.sobre_o_resultado || []));
  }

  /** Abre a janela. `ctx` = {CORES_LOC, ORDEM_LOC, fecharAoClicarFora}. */
  function abrir(p, ctx) {
    const cor = (mt) => ctx.CORES_LOC[mt] || "var(--tinta)";
    const jan = criar("dialog", "busca ajuda-metodos-loc");
    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar";
    fechar.addEventListener("click", () => jan.close());
    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, "Como cada método calcula"), fechar);
    const corpo = criar("div", "corpo-ajuda");
    const lado = criar("div", "lado-mt");
    const lista = criar("div", "lista-mt");
    const miolo = criar("div", "miolo-mt");
    const presentes = ctx.ORDEM_LOC.filter((mt) => (p.metodos || {})[mt]);
    const res = p.resultado && p.resultado.metodo;
    let atual = res && presentes.includes(res) ? res : (presentes[0] || "_fecho");
    const mostrar = () => {
      tirarDica();
      lista.querySelectorAll("button").forEach((b) => {
        b.classList.toggle("atual", b.dataset.mt === atual);
        b.setAttribute("aria-selected", b.dataset.mt === atual ? "true" : "false");
      });
      miolo.replaceChildren();
      if (atual === "_fecho") fecho(miolo, p);
      else miolo.append(metodo(atual, p.metodos[atual], p, cor(atual)));
    };
    for (const mt of presentes) {
      const info = p.metodos[mt];
      const b = criar("button");
      b.type = "button";
      b.dataset.mt = mt;
      b.setAttribute("role", "tab");
      b.style.setProperty("--cor-mt", cor(mt));
      b.append(criar("span", "marca-mt"), criar("span", "nome-curto", info.curto || mt), kmDe(info));
      b.title = info.nome || mt;
      b.addEventListener("click", () => { atual = mt; mostrar(); });
      lista.append(b);
    }
    const bf = criar("button");
    bf.type = "button";
    bf.dataset.mt = "_fecho";
    bf.setAttribute("role", "tab");
    bf.append(criar("span"), criar("span", "nome-curto", "resultado e trecho"), criar("span"));
    bf.addEventListener("click", () => { atual = "_fecho"; mostrar(); });
    lista.append(bf);
    lista.setAttribute("role", "tablist");
    lado.append(lista, miolo);
    corpo.append(lado);
    jan.append(cabeca, corpo);
    jan.addEventListener("close", () => { tirarDica(); jan.remove(); });
    // O Esc é da janela: o teclado da página (`onda.js`) faz `preventDefault`
    // no Esc para tirar os cursores, e isso impedia o `<dialog>` de fechar.
    jan.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      jan.close();
    });
    document.body.append(jan);
    ctx.fecharAoClicarFora(jan);
    mostrar();
    jan.showModal();
    return jan;
  }

  return { abrir };
})();
