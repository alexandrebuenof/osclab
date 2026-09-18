/* A tela de formas de onda — desenho, zoom e arrasto (marco 0.3).
 *
 * Sem biblioteca de gráficos, por decisão do projeto: nada para baixar, nada
 * que envelhece, controle total sobre o que é específico de oscilografia.
 *
 * ## A divisão de trabalho
 *
 * Este arquivo NÃO decide número nenhum. Qual janela, quais canais, que escala
 * vertical, onde ficam as marcações e como reduzir 6000 amostras para caberem
 * em 900 pixels — tudo isso vem pronto do servidor, onde tem teste. Aqui só se
 * converte valor em pixel e se pinta.
 *
 * É o que permite trocar este desenhista sem tocar no resto do programa.
 *
 * ## Os gestos
 *
 * | gesto | o que faz |
 * |---|---|
 * | roda do mouse | amplia e reduz, em torno do ponto sob o cursor |
 * | arrastar | anda pela oscilografia (a onda segue a mão) |
 * | Shift + arrastar | seleciona uma faixa de tempo e vai até ela |
 * | botão direito | volta ao registro inteiro |
 * | 1 e 2 | põem e tiram os cursores de medição no ponto do mouse |
 * | arrastar um cursor | move aquele cursor (o mouse vira ↔ em cima dele) |
 * | ← → | andam uma amostra · com Shift, um ciclo |
 * | Esc | tira os dois cursores |
 *
 * ## O valor lido NÃO sai do traço desenhado
 *
 * O traço é mínimo e máximo por coluna de pixel: metade dos pontos é um mínimo,
 * metade é um máximo, e nenhum dos dois é "o valor naquele instante". Ler daqui
 * daria um número errado com cara de certo. O cursor pergunta ao servidor, que
 * vai à amostra — ver `plot/leitura.py`.
 *
 * O mouse fala em pixel; o servidor, em segundos. Este arquivo faz só essa
 * tradução e manda o GESTO ("amplie 0,8 em torno de t=1,234 s"). Quem decide a
 * janela que sai disso é `plot/navegacao.py`, que sabe onde o registro começa e
 * acaba e até onde vale ampliar. Por isso nenhum limite está escrito aqui.
 *
 * ## Por que o arrasto não pede nada ao servidor enquanto acontece
 *
 * Um pedido por movimento do mouse seriam dezenas por segundo. Enquanto a mão
 * arrasta, a imagem que já está na tela é repintada deslocada — é o mesmo
 * desenho andando. Ao soltar, aí sim se pede a janela nova, com os dados certos
 * das bordas que entraram. O olho vê continuidade; a rede vê um pedido.
 *
 * ## Alta resolução
 *
 * Um canvas tem dois tamanhos: o que ele ocupa na página (CSS) e quantos pixels
 * ele guarda (atributos width/height). Numa tela de notebook moderno eles são
 * diferentes, e ignorar isso deixa a onda borrada. Por isso todo desenho é
 * feito na escala do dispositivo.
 */

(() => {
  "use strict";

  const ALTURA = 190;        // altura útil de cada gráfico, em pixels de CSS

  //: A margem de cima abriga a etiqueta numerada dos cursores, que fica FORA da
  //: área de desenho: por dentro ela tapa o pico da onda — e o pico é
  //: exatamente o que se está medindo quando se põe um cursor ali.
  const MARGEM = { esq: 74, dir: 16, topo: 20, baixo: 26 };

  const ETIQUETA = { largura: 15, altura: 13 };

  const sha = document.body.dataset.sha;
  const area = document.getElementById("graficos");
  const rodape = document.getElementById("rodape");

  let dados = null;
  let pendente = null;

  //: O arrasto em curso, ou null. Declarado aqui porque a roda também consulta.
  let arrastando = null;

  //: Deslocamento visual em pixels enquanto a mão arrasta (ver cabeçalho).
  let arrastoPx = 0;

  //: A faixa sendo selecionada com Shift, em pixels: [inicio, atual].
  let selecao = null;

  //: Os <section> dos gráficos, guardados para repintar sem remontar a página.
  let blocos = [];

  //: O instante de cada cursor, em segundos, ou null. O índice é o cursor − 1.
  const cursores = [null, null];

  //: Qual cursor as setas do teclado movem.
  let ativo = 0;

  //: A última resposta de /leitura — valores por canal e o tempo entre eles.
  let medida = null;

  //: O instante sob o mouse, para as teclas 1 e 2 saberem onde pôr o cursor.
  let sobreOMouse = null;

  //: Uma leitura de cada vez: durante o arrasto o último pedido vence.
  let lendo = false;
  let pedidoDeLeitura = null;


  //: Uma trinca [v1, v2, diferença] por canal analógico, na mesma ordem em que
  //: o servidor manda os valores — as tabelinhas de todos os gráficos juntas.
  let celulas = [];

  //: De que lado os valores são mostrados: "arquivo", "secundario" ou
  //: "primario". Vai junto em todo pedido, porque a conversão pela relação de
  //: TC/TP é feita no servidor — é ela que decide a faixa vertical do gráfico.
  let lado = lerLadoGuardado();

  //: Em que unidade a linha do tempo está: "ms" ou "ciclos". A escolha é do
  //: usuário, fica guardada no navegador, e vale para os dois cursores e para
  //: o Δt ao mesmo tempo — é a mesma medida vista de dois jeitos.
  let unidadeDoTempo = lerUnidadeGuardada();

  //: A linha do tempo de cada tabelinha: [rotulo, t1, t2, Δ].
  let linhasDoTempo = [];

  //: A tabelinha estava aberta na última vez que se olhou? Trocar isso muda a
  //: largura do gráfico, e largura nova pede dados novos (ver `ajustarEspaco`).
  let comTabela = false;

  //: Distância em pixels para o mouse "pegar" um cursor.
  const PEGADA = 7;

  // --- utilidades ---------------------------------------------------------

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  const token = (nome) =>
    getComputedStyle(document.documentElement).getPropertyValue(nome).trim();

  const corDaFase = (fase) => {
    const mapa = { A: "--fase-a", B: "--fase-b", C: "--fase-c", N: "--fase-n" };
    return token(mapa[fase] || "--suave");
  };

  const formatar = (v, casas, agrupar = true) =>
    v === null || v === undefined || !isFinite(v)
      ? "—"
      : v.toLocaleString("pt-BR", {
          minimumFractionDigits: casas,
          maximumFractionDigits: casas,
          // O tempo dispensa separador de milhar: `1043,2` cabe onde
          // `1.043,2` não cabe, e ninguém lê um instante como contagem.
          useGrouping: agrupar,
        });

  /** Instante mostrado no eixo: milissegundos em relação ao disparo. */
  const paraMs = (t) => (t - (dados.disparo_s ?? 0)) * 1000;

  /** Uma duração legível. Em pt-BR, `1.562 ms` se lê como 1,5 ms — e o ponto
   *  é separador de milhar. Acima de um segundo, então, muda-se de unidade. */
  const duracao = (s) =>
    s >= 1 ? `${formatar(s, 3)} s` : `${formatar(s * 1000, s < 0.01 ? 2 : 1)} ms`;

  /** Ampliado o bastante, o eixo em milissegundos inteiros repete números. */
  const casasDoTempo = () => {
    const ms = (dados.ate - dados.de) * 1000;
    return ms >= 20 ? 0 : ms >= 2 ? 1 : 2;
  };

  // --- carregar -----------------------------------------------------------

  /** Pede uma janela ao servidor. `gesto` é o que o mouse acabou de fazer. */
  async function carregar(gesto = {}) {
    const p = new URLSearchParams();
    p.set("colunas", String(Math.max(300, Math.round(larguraDisponivel()))));
    if (lado) p.set("lado", lado);

    // A janela atual vai junto: os gestos se aplicam sobre ela, e é isso que
    // faz o zoom ser cumulativo em vez de recomeçar do registro inteiro.
    if (dados && !gesto.tudo) {
      p.set("de", String(dados.de));
      p.set("ate", String(dados.ate));
    }
    for (const chave of ["zoom", "foco", "andar", "de", "ate"]) {
      if (gesto[chave] !== undefined) p.set(chave, String(gesto[chave]));
    }
    if (gesto.tudo) p.set("tudo", "1");

    try {
      const r = await fetch(`/api/onda/${sha}?${p}`);
      if (!r.ok) {
        const erro = await r.json().catch(() => ({}));
        throw new Error(erro.erro || `o servidor respondeu ${r.status}`);
      }
      dados = await r.json();
      // Na primeira carga quem decidiu o lado foi o servidor; a tela obedece,
      // senão nenhum botão ficaria aceso.
      lado = dados.lado_pedido;
      marcarLado();
      window.__janela = { de: dados.de, ate: dados.ate };   // para teste no navegador
      arrastoPx = 0;
      desenharTudo();
    } catch (erro) {
      area.replaceChildren(criar("p", "vazio", `Não consegui ler o registro: ${erro.message}`));
    }
  }

  function larguraDisponivel() {
    // Mede a área de desenho de verdade, e não a página: com a tabelinha aberta
    // o gráfico é mais estreito, e pedir colunas a mais faria o servidor reduzir
    // as amostras mais fino do que a tela consegue mostrar.
    const tela = area.querySelector(".tela");
    const largura = (tela && tela.clientWidth) || area.clientWidth || 900;
    return Math.max(largura - MARGEM.esq - MARGEM.dir, 120);
  }

  // --- montagem da página -------------------------------------------------

  function desenharTudo() {
    if (!dados) return;

    if (!dados.grupos || dados.grupos.length === 0) {
      area.replaceChildren(criar("p", "vazio", "Este registro não tem canal analógico."));
      return;
    }

    celulas = [];
    linhasDoTempo = [];
    blocos = dados.grupos.map((grupo, i) =>
      bloco(grupo, i === dados.grupos.length - 1)
    );
    area.replaceChildren(...blocos);

    rodape.textContent =
      `${dados.amostras_na_janela} amostras · ${duracao(dados.ate - dados.de)} na tela` +
      (dados.inteiro ? " (registro inteiro)" : "") +
      (dados.reduzido ? " · reduzidas para caber na tela, preservando os picos" : "") +
      semRelacao();

    mostrarLeitura();
    repintar();
  }

  /** Aviso dos canais que não puderam ser convertidos, ou "".
   *
   * O programa avisa, nunca bloqueia — e nunca converte por palpite: quando o
   * `.cfg` não traz a relação de TC/TP, o canal fica como está e isso precisa
   * aparecer, senão o usuário lê ampère secundário achando que é primário.
   */
  function semRelacao() {
    if (lado === "arquivo" || !dados) return "";
    const teimosos = [];
    for (const grupo of dados.grupos) {
      for (const canal of grupo.canais) {
        if (canal.lado !== lado) teimosos.push(canal.nome);
      }
    }
    if (!teimosos.length) return "";
    return ` · sem relação de TC/TP no arquivo, ficaram como estão: ${teimosos.join(", ")}`;
  }

  /** Repinta o que já está montado. É o que roda a cada movimento do mouse. */
  function repintar() {
    for (const b of blocos) pintar(b._canvas, b._grupo, b._ultimo);
  }

  function bloco(grupo, ultimo) {
    const el = criar("section", "grafico");

    el.append(criar("h2", "grafico-titulo", grupo.titulo));

    const legenda = criar("ul", "legenda");
    for (const canal of grupo.canais) {
      const item = criar("li");
      const marca = criar("span", "marca");
      marca.style.background = corDaFase(canal.fase);
      item.append(marca, criar("span", "nome", canal.nome));
      if (canal.fase) item.append(criar("span", "fase", canal.fase));

      // A etiqueta marca a EXCEÇÃO, não a regra. Com o cabeçalho já dizendo
      // "primário", carimbar "prim." em todos os canais é ruído; o que precisa
      // saltar aos olhos é o canal que NÃO pôde ser convertido, porque o
      // arquivo não trouxe a relação de TC/TP.
      if (dados.lado_pedido === "arquivo") {
        if (canal.lado === "primario") item.append(criar("span", "lado", "prim."));
      } else if (canal.lado !== dados.lado_pedido) {
        const aviso = criar("span", "lado sem-relacao",
                            canal.lado === "primario" ? "prim." : "sec.");
        aviso.title = "O arquivo não declara a relação de TC/TP deste canal, "
                    + "então o valor ficou como está — em "
                    + (canal.lado === "primario" ? "primário." : "secundário.");
        item.append(aviso);
      }
      legenda.append(item);
    }
    el.append(legenda);

    // A onda e a tabelinha daquele grupo, lado a lado e alinhadas. As células
    // existem desde já, com traços: criá-las ao pôr o cursor empurraria o
    // gráfico e a onda fugiria de debaixo do mouse no meio da medição.
    const corpo = criar("div", "grafico-corpo");
    const caixa = criar("div", "tela");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    corpo.append(caixa, tabelinha(grupo));
    el.append(corpo);

    el._canvas = canvas;
    el._grupo = grupo;
    el._ultimo = ultimo;
    return el;
  }

  /** A tabelinha de um grupo: os canais dele, nas duas colunas de cursor. */
  function tabelinha(grupo) {
    const tabela = criar("table", "mini");

    const cabeca = criar("tr");
    cabeca.append(criar("th", null, ""));
    for (const k of [1, 2]) {
      const th = criar("th");
      th.append(criar("span", `em-${k}`), String(k));
      cabeca.append(th);
    }
    cabeca.append(criar("th", null, "2−1"));
    const thead = criar("thead");
    thead.append(cabeca);

    const tbody = criar("tbody");
    for (const canal of grupo.canais) {
      const linha = criar("tr");
      const nome = criar("th", canal.fase ? `canal fase-${canal.fase}` : "canal",
                         canal.nome);
      nome.title = canal.nome;             // o nome inteiro no passar do mouse
      const a = criar("td", "valor-1 vazio-valor", "—");
      const b = criar("td", "valor-2 vazio-valor", "—");
      const d = criar("td", "vazio-valor", "—");
      linha.append(nome, a, b, d);
      tbody.append(linha);
      celulas.push([a, b, d]);
    }

    // A última linha é o tempo, e o rótulo dela é o botão que troca a unidade.
    // Pôr a unidade no rótulo, e não nas células, é o que impede a tabela de
    // mentir: o que está escrito à esquerda vale para os três números.
    const tempo = criar("tr", "tempo");
    const rotulo = criar("th", "unidade");
    const botao = criar("button", "troca");
    rotulo.append(botao);
    const t1 = criar("td", "valor-1 vazio-valor", "—");
    const t2 = criar("td", "valor-2 vazio-valor", "—");
    const dt = criar("td", "vazio-valor", "—");
    tempo.append(rotulo, t1, t2, dt);
    tbody.append(tempo);
    linhasDoTempo.push([botao, t1, t2, dt]);

    botao.addEventListener("click", trocarUnidade);

    tabela.append(thead, tbody);
    return tabela;
  }

  // --- lado dos valores: arquivo, secundário, primário --------------------
  //
  // A conta em si não está aqui: a relação de TC/TP vem do `.cfg` e é aplicada
  // em `plot/conversao.py`, junto com a escala vertical e o prefixo da unidade.
  // Converter no navegador seria recalcular a escala aqui também — duas
  // implementações da mesma conta, que é como elas divergem.

  //: `null` = ninguém escolheu ainda; o servidor decide pelo lado em que o
  //: registro já está. Abrir uma oscilografia já convertida seria surpresa.
  function lerLadoGuardado() {
    try {
      const guardado = localStorage.getItem("osclab:lado");
      return ["secundario", "primario"].includes(guardado) ? guardado : null;
    } catch {
      return null;
    }
  }

  function escolherLado(novo) {
    if (novo === lado) return;
    lado = novo;
    try {
      localStorage.setItem("osclab:lado", lado);
    } catch { /* não poder lembrar não impede de usar */ }
    marcarLado();
    carregar();            // a janela inteira muda de escala; a leitura vem junto
    if (cursores[0] !== null || cursores[1] !== null) lerCursores();
  }

  function marcarLado() {
    for (const botao of botoesDoLado) {
      const meu = botao.dataset.lado === lado;
      botao.classList.toggle("escolhido", meu);
      botao.setAttribute("aria-pressed", String(meu));
    }
  }

  const botoesDoLado = [...document.querySelectorAll("#lado button")];
  for (const botao of botoesDoLado) {
    botao.addEventListener("click", () => escolherLado(botao.dataset.lado));
  }
  marcarLado();

  // --- a unidade do tempo -------------------------------------------------

  function lerUnidadeGuardada() {
    try {
      return localStorage.getItem("osclab:tempo") === "ciclos" ? "ciclos" : "ms";
    } catch {
      return "ms";                 // navegador sem armazenamento: começa em ms
    }
  }

  function trocarUnidade() {
    unidadeDoTempo = unidadeDoTempo === "ms" ? "ciclos" : "ms";
    try {
      localStorage.setItem("osclab:tempo", unidadeDoTempo);
    } catch { /* não poder lembrar não impede de usar */ }
    mostrarLeitura();
  }

  /** O instante ou o intervalo `t` na unidade escolhida, ou null. */
  function noTempo(t) {
    if (!t) return null;
    // Sem frequência nominal declarada não há ciclo; sobra o ms.
    const valor = unidadeDoTempo === "ciclos" ? t.ciclos : t.ms;
    if (valor === null || valor === undefined) return null;
    // Quantas casas cabem vem do servidor: é o intervalo entre amostras que
    // define a resolução real, e ela muda com a taxa do registro.
    const casas = unidadeDoTempo === "ciclos"
      ? (medida.casas_ciclos ?? 2) : (medida.casas_ms ?? 1);
    return { valor, casas, agrupar: false };
  }

  // --- desenho ------------------------------------------------------------

  function pintar(canvas, grupo, ultimo) {
    const cssLargura = canvas.parentElement.clientWidth;
    const cssAltura = ALTURA + (ultimo ? MARGEM.baixo : 8);
    const dpr = window.devicePixelRatio || 1;

    canvas.style.width = `${cssLargura}px`;
    canvas.style.height = `${cssAltura}px`;
    canvas.width = Math.round(cssLargura * dpr);
    canvas.height = Math.round(cssAltura * dpr);

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssLargura, cssAltura);

    const x0 = MARGEM.esq;
    const x1 = cssLargura - MARGEM.dir;
    const y0 = MARGEM.topo;
    const y1 = ALTURA - 4;

    if (x1 <= x0) return;

    const tempo = dados.tempo;
    const tMin = dados.de;
    const tMax = dados.ate;
    // O arrasto desloca só o que depende do tempo. Os rótulos do eixo vertical
    // e a moldura ficam parados: são a régua, e régua que anda não é régua.
    const emX = (t) =>
      x0 + ((t - tMin) / (tMax - tMin || 1)) * (x1 - x0) + arrastoPx;
    const emY = (v) =>
      y1 - ((v - grupo.minimo) / (grupo.maximo - grupo.minimo || 1)) * (y1 - y0);

    const corLinha = token("--linha");
    const corSuave = token("--suave");
    const corTinta = token("--tinta");
    const corDestaque = token("--destaque");

    ctx.font = "11px ui-monospace, Consolas, monospace";
    ctx.textBaseline = "middle";

    // --- grade horizontal e rótulos do eixo vertical ---------------------
    ctx.strokeStyle = corLinha;
    ctx.fillStyle = corSuave;
    ctx.lineWidth = 1;
    ctx.textAlign = "right";
    for (const marca of grupo.marcacoes) {
      const y = Math.round(emY(marca)) + 0.5;
      ctx.globalAlpha = marca === 0 ? 0.9 : 0.4;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(formatar(marca, grupo.casas), x0 - 8, y);
    }

    // Daqui até a moldura, tudo que se desenha depende do tempo — e com o
    // arrasto pode escorregar para fora da área do gráfico. O recorte segura.
    ctx.save();
    ctx.beginPath();
    ctx.rect(x0, y0, x1 - x0, y1 - y0);
    ctx.clip();

    // --- grade vertical (tempo) ------------------------------------------
    ctx.strokeStyle = corLinha;
    ctx.globalAlpha = 0.35;
    for (const marca of dados.marcacoes_tempo) {
      const x = Math.round(emX(marca)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // --- instante do disparo ---------------------------------------------
    if (dados.disparo_s !== null && dados.disparo_s >= tMin && dados.disparo_s <= tMax) {
      const x = Math.round(emX(dados.disparo_s)) + 0.5;
      ctx.save();
      ctx.strokeStyle = corDestaque;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
      ctx.stroke();
      ctx.restore();
    }

    // --- as ondas ---------------------------------------------------------
    ctx.lineWidth = 1.4;
    ctx.lineJoin = "round";
    for (const canal of grupo.canais) {
      ctx.strokeStyle = corDaFase(canal.fase);
      ctx.beginPath();
      let comecou = false;
      const s = canal.serie;
      for (let i = 0; i < s.length; i++) {
        const v = s[i];
        if (v === null) { comecou = false; continue; }
        const x = emX(tempo[i]);
        const y = emY(v);
        if (comecou) ctx.lineTo(x, y);
        else { ctx.moveTo(x, y); comecou = true; }
      }
      ctx.stroke();
    }

    // --- os cursores de medição: a linha ----------------------------------
    // A etiqueta numerada vem depois, fora do recorte e fora do gráfico.
    cursores.forEach((t, k) => {
      if (t === null) return;
      const x = Math.round(emX(t)) + 0.5;
      if (x < x0 - 1 || x > x1 + 1) return;
      ctx.save();
      ctx.strokeStyle = token(k === 0 ? "--cursor-1" : "--cursor-2");
      ctx.lineWidth = k === ativo ? 2 : 1.2;
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
      ctx.stroke();
      ctx.restore();
    });

    // --- a faixa que o arrasto descobriu e ainda não tem dados ------------
    //
    // Sem isto, a grade horizontal continua desenhada na parte vazia e a linha
    // do zero atravessa sozinha a tela: numa oscilografia, isso se lê como
    // "sinal zerado" — exatamente o que um leitor de falta não pode insinuar.
    if (arrastoPx !== 0) {
      const largura = Math.min(Math.abs(arrastoPx), x1 - x0);
      ctx.save();
      ctx.fillStyle = token("--fundo");
      ctx.globalAlpha = 0.82;
      ctx.fillRect(arrastoPx > 0 ? x0 : x1 - largura, y0, largura, y1 - y0);
      ctx.restore();
    }

    // --- faixa sendo selecionada com Shift --------------------------------
    if (selecao) {
      const [a, b] = selecao;
      ctx.save();
      ctx.fillStyle = corDestaque;
      ctx.globalAlpha = 0.26;
      ctx.fillRect(Math.min(a, b), y0, Math.abs(b - a), y1 - y0);
      ctx.globalAlpha = 0.95;
      ctx.strokeStyle = corDestaque;
      ctx.lineWidth = 1.5;
      for (const x of [a, b]) {
        ctx.beginPath();
        ctx.moveTo(Math.round(x) + 0.5, y0);
        ctx.lineTo(Math.round(x) + 0.5, y1);
        ctx.stroke();
      }
      ctx.restore();
    }

    ctx.restore();                       // fim do recorte da área do gráfico

    // --- moldura ----------------------------------------------------------
    ctx.strokeStyle = corLinha;
    ctx.lineWidth = 1;
    ctx.strokeRect(x0 + 0.5, y0 + 0.5, x1 - x0 - 1, y1 - y0 - 1);

    // --- a etiqueta numerada dos cursores, ACIMA da moldura ---------------
    //
    // Por dentro do gráfico ela tapava a crista da onda justamente quando se
    // põe o cursor no pico para medir amplitude. A identidade do cursor não
    // pode ficar só na cor, então a etiqueta continua — só que fora.
    cursores.forEach((t, k) => {
      if (t === null) return;
      const x = Math.round(emX(t)) + 0.5;
      if (x < x0 - 1 || x > x1 + 1) return;

      // Nas bordas, a etiqueta encosta e para: metade dela fora do canvas
      // sumiria, e o cursor ficaria sem número.
      const meia = ETIQUETA.largura / 2;
      const centro = Math.min(Math.max(x, x0 + meia), x1 - meia);
      const topo = y0 - ETIQUETA.altura - 3;

      ctx.save();
      ctx.fillStyle = token(k === 0 ? "--cursor-1" : "--cursor-2");
      ctx.globalAlpha = k === ativo ? 1 : 0.75;
      ctx.fillRect(centro - meia, topo, ETIQUETA.largura, ETIQUETA.altura);
      ctx.fillStyle = token("--fundo");
      ctx.globalAlpha = 1;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = "bold 10px ui-monospace, Consolas, monospace";
      ctx.fillText(String(k + 1), centro, topo + ETIQUETA.altura / 2);
      ctx.restore();
    });

    // --- eixo do tempo, só embaixo de tudo -------------------------------
    if (!ultimo) return;
    ctx.fillStyle = corSuave;
    ctx.textAlign = "center";
    for (const marca of dados.marcacoes_tempo) {
      const x = emX(marca);
      if (x < x0 - 1 || x > x1 + 1) continue;   // saiu da área durante o arrasto
      ctx.fillText(formatar(paraMs(marca), casasDoTempo()), x, y1 + 13);
    }
    ctx.fillStyle = corTinta;
    ctx.textAlign = "left";
    ctx.fillText(
      dados.disparo_s === null ? "ms desde o início" : "ms em relação ao disparo",
      x0, y1 + 26
    );
  }

  // --- cursores de medição ------------------------------------------------

  /** Onde o instante `t` cai, em pixels, na área `a`. */
  const emPixel = (a, t) =>
    a.x0 + ((t - dados.de) / (dados.ate - dados.de || 1)) * (a.x1 - a.x0) + arrastoPx;

  /** Qual cursor está debaixo do ponto `x`, ou -1. */
  function cursorEm(a, x) {
    let achado = -1;
    let menor = PEGADA;
    cursores.forEach((t, k) => {
      if (t === null) return;
      const d = Math.abs(emPixel(a, t) - x);
      if (d <= menor) { menor = d; achado = k; }
    });
    return achado;
  }

  /** Pede a leitura ao servidor. Um pedido de cada vez; o último vence.
   *
   * Durante o arrasto de um cursor isso seria um pedido por movimento do
   * mouse. Com uma leitura em voo por vez, a fila nunca cresce e o último
   * pedido é sempre o que aparece na tela.
   */
  async function lerCursores(passos = [0, 0], ciclos = [0, 0]) {
    if (cursores[0] === null && cursores[1] === null) {
      medida = null;
      espelhar();
      mostrarLeitura();
      if (!ajustarEspaco()) repintar();
      return;
    }
    if (lendo) { pedidoDeLeitura = [passos, ciclos]; return; }

    lendo = true;
    const p = new URLSearchParams();
    if (lado) p.set("lado", lado);
    cursores.forEach((t, k) => {
      if (t === null) return;
      p.set(`t${k + 1}`, String(t));
      if (passos[k]) p.set(`passo${k + 1}`, String(passos[k]));
      if (ciclos[k]) p.set(`ciclos${k + 1}`, String(ciclos[k]));
    });

    try {
      const r = await fetch(`/api/onda/${sha}/leitura?${p}`);
      if (r.ok) {
        medida = await r.json();

        // O servidor encosta o cursor na amostra mais próxima e a tela obedece
        // — MENOS no cursor que a mão está arrastando agora.
        //
        // Os pedidos são engargalados (um em voo por vez), então a resposta que
        // chega é de uma posição do mouse de alguns milissegundos atrás. Aplicar
        // essa posição no meio do arrasto puxava a linha para trás: um cabo de
        // guerra entre a mão e a resposta atrasada. Enquanto se arrasta, a linha
        // é da mão; ao soltar, `soltar()` já zerou `arrastando` e a resposta
        // seguinte encosta na amostra.
        medida.cursores.forEach((c, k) => {
          if (!c) return;
          if (arrastando && arrastando.cursor === k) return;
          cursores[k] = c.t;
        });
        espelhar();
        mostrarLeitura();
        if (!ajustarEspaco()) repintar();
      }
    } catch { /* leitura é acessório: falhou, o desenho continua de pé */ }

    lendo = false;
    if (pedidoDeLeitura) {
      const proximo = pedidoDeLeitura;
      pedidoDeLeitura = null;
      lerCursores(...proximo);
    }
  }

  //: Espelho do estado para os testes de navegador olharem.
  const espelhar = () => { window.__cursores = [...cursores]; };

  function porCursor(k, t) {
    cursores[k] = t;
    // As setas movem um cursor que exista: tirar o 1 passa a vez para o 2.
    if (t !== null) ativo = k;
    else if (cursores[1 - k] !== null) ativo = 1 - k;
    lerCursores();
  }

  /** Abre ou fecha a coluna das tabelinhas conforme haja cursor na tela.
   *
   * Abrir estreita o gráfico, e o número de colunas de pixel muda junto — por
   * isso se pede a janela de novo. É um pedido só, no instante em que o
   * primeiro cursor aparece ou o último some; depois disso a largura fica
   * parada e a medição acontece sem a tela se mexer.
   */
  function ajustarEspaco() {
    const agora = cursores[0] !== null || cursores[1] !== null;
    if (agora === comTabela) return false;
    comTabela = agora;
    area.classList.toggle("com-cursores", agora);
    carregar();
    return true;
  }

  function mostrarLeitura() {
    const c = medida ? medida.cursores : [null, null];

    // Os valores chegam numa lista por cursor, na ordem dos canais analógicos
    // do registro; as tabelinhas foram montadas na mesma ordem, grupo a grupo.
    // Até a subtração vem pronta: quantas casas mostrar e a diferença entre os
    // dois instantes são decisões de `plot/leitura.py`, onde há teste.
    const diferencas = medida && medida.entre ? medida.entre.valores : null;
    celulas.forEach(([a, b, d], n) => {
      escrever(a, c[0] && c[0].valores[n]);
      escrever(b, c[1] && c[1].valores[n]);
      escrever(d, diferencas && diferencas[n]);
    });

    mostrarTempo(c);
  }

  function escrever(celula, v) {
    const tem = v && v.valor !== null && v.valor !== undefined;
    celula.textContent = tem
      ? formatar(v.valor, v.casas, v.agrupar !== false) : "—";
    celula.classList.toggle("vazio-valor", !tem);
  }

  /** A última linha: onde cada cursor está e quanto tempo há entre eles. */
  function mostrarTempo(c) {
    const dt = medida ? medida.entre : null;

    // Sem frequência nominal no arquivo não existe ciclo, e o botão não tem o
    // que oferecer: fica desligado e a linha permanece em ms.
    //
    // Repare no `?? true`: NÃO ter cursor não é o mesmo que não ter ciclo.
    // Tratar os dois casos juntos apagava a escolha do usuário toda vez que a
    // tela era montada sem cursor — inclusive ao abrir o registro, que é
    // justamente quando a preferência guardada acabou de ser lida.
    const cursor = c[0] || c[1];
    const temCiclo = cursor ? cursor.ciclos !== null : true;
    if (!temCiclo && unidadeDoTempo === "ciclos") unidadeDoTempo = "ms";

    for (const [botao, t1, t2, td] of linhasDoTempo) {
      botao.textContent = unidadeDoTempo === "ms" ? "t (ms)" : "t (ciclos)";
      botao.title = unidadeDoTempo === "ms"
        ? "Mostrar o tempo em ciclos" : "Mostrar o tempo em milissegundos";
      botao.disabled = !temCiclo;
      escrever(t1, noTempo(c[0]));
      escrever(t2, noTempo(c[1]));
      escrever(td, noTempo(dt));
    }
  }

  // --- gestos do mouse ----------------------------------------------------
  //
  // A geometria mora aqui porque é geometria de TELA: onde começa a área de
  // desenho, quantos pixels ela tem. A conversão para segundos usa a janela que
  // o servidor mandou; a decisão do que fazer com esses segundos é dele.

  /** A área de desenho do canvas sob o evento, em pixels de CSS.
   *
   * Guarda o próprio canvas junto. Durante o arrasto ele é indispensável: com
   * a captura do ponteiro, o navegador passa a entregar os eventos ao elemento
   * que capturou, e `evento.target` deixa de ser o canvas. Medir pelo alvo do
   * evento dava deslocamento zero — o arrasto não saía do lugar.
   */
  function areaDoEvento(evento) {
    const canvas = evento.target.closest?.(".tela")?.querySelector("canvas");
    if (!canvas || !dados) return null;
    return medir(canvas, evento);
  }

  function medir(canvas, evento) {
    const caixa = canvas.getBoundingClientRect();
    const x0 = MARGEM.esq;
    const x1 = caixa.width - MARGEM.dir;
    if (x1 <= x0) return null;
    return { canvas, x0, x1, x: evento.clientX - caixa.left };
  }

  /** Quantos segundos vale um pixel na janela atual. */
  const segundosPorPixel = (a) => (dados.ate - dados.de) / (a.x1 - a.x0);

  /** O instante sob o cursor. */
  const instanteEm = (a) => dados.de + (a.x - a.x0 - arrastoPx) * segundosPorPixel(a);

  // Roda: ampliar e reduzir em torno do cursor. Os entalhes são acumulados e
  // mandados de uma vez — girar a roda três vezes é um pedido, não três.
  let zoomAcumulado = 1;
  let zoomFoco = null;
  let zoomPendente = null;

  area.addEventListener("wheel", (evento) => {
    const a = areaDoEvento(evento);
    if (!a || arrastando) return;
    evento.preventDefault();

    zoomAcumulado *= evento.deltaY < 0 ? 0.8 : 1.25;
    zoomFoco = instanteEm(a);

    clearTimeout(zoomPendente);
    zoomPendente = setTimeout(() => {
      const gesto = { zoom: zoomAcumulado, foco: zoomFoco };
      zoomAcumulado = 1;
      carregar(gesto);
    }, 70);
  }, { passive: false });

  // Arrastar: a onda segue a mão. Com Shift, desenha a faixa a ampliar.
  area.addEventListener("pointerdown", (evento) => {
    if (evento.button !== 0) return;
    const a = areaDoEvento(evento);
    if (!a) return;
    evento.preventDefault();

    // Um cursor debaixo do ponteiro tem prioridade sobre o arrasto do gráfico:
    // quem clicou em cima da linha quer mover a linha, não a oscilografia.
    const k = evento.shiftKey ? -1 : cursorEm(a, a.x);
    if (k >= 0) {
      ativo = k;
      arrastando = { a, canvas: a.canvas, xInicial: a.x, cursor: k };
      area.setPointerCapture?.(evento.pointerId);
      area.classList.add("no-cursor");
      repintar();
      return;
    }

    arrastando = { a, canvas: a.canvas, xInicial: a.x, faixa: evento.shiftKey };
    if (arrastando.faixa) selecao = [a.x, a.x];
    area.setPointerCapture?.(evento.pointerId);
    area.classList.add(arrastando.faixa ? "selecionando" : "arrastando");
  });

  area.addEventListener("pointermove", (evento) => {
    if (!arrastando) {
      // Sem arrasto em curso, só se guarda onde o mouse está — é onde as
      // teclas 1 e 2 vão pôr o cursor — e se avisa que dá para pegar a linha.
      const a = areaDoEvento(evento);
      sobreOMouse = a ? instanteEm(a) : null;
      area.classList.toggle("no-cursor", !!a && cursorEm(a, a.x) >= 0);
      return;
    }

    const agora = medir(arrastando.canvas, evento);
    if (!agora) return;
    const x = agora.x;

    if (arrastando.cursor !== undefined) {
      const a = arrastando.a;
      const preso = Math.min(Math.max(x, a.x0), a.x1);
      cursores[arrastando.cursor] =
        dados.de + (preso - a.x0 - arrastoPx) * segundosPorPixel(a);
      repintar();
      lerCursores();
      return;
    }

    if (arrastando.faixa) {
      selecao = [arrastando.xInicial, Math.min(Math.max(x, arrastando.a.x0),
                                               arrastando.a.x1)];
    } else {
      arrastoPx = x - arrastando.xInicial;
    }
    repintar();
  });

  function soltar(evento) {
    if (!arrastando) return;
    const { a, xInicial, faixa, cursor } = arrastando;
    arrastando = null;
    area.classList.remove("arrastando", "selecionando");
    area.releasePointerCapture?.(evento.pointerId);

    if (cursor !== undefined) { lerCursores(); return; }

    if (faixa) {
      const [p1, p2] = selecao || [xInicial, xInicial];
      selecao = null;
      // Uma faixa de menos de 4 px é um clique torto, não uma seleção.
      if (Math.abs(p2 - p1) < 4) { repintar(); return; }
      const t = (px) => dados.de + (px - a.x0 - arrastoPx) * segundosPorPixel(a);
      carregar({ de: t(Math.min(p1, p2)), ate: t(Math.max(p1, p2)) });
      return;
    }

    if (arrastoPx === 0) return;
    // Arrastar para a direita traz o passado: a janela anda para trás.
    carregar({ andar: -arrastoPx * segundosPorPixel(a) });
  }

  area.addEventListener("pointerup", soltar);
  area.addEventListener("pointercancel", soltar);

  // Botão direito: desfaz todo o zoom. Sem menu de contexto em cima do gráfico.
  area.addEventListener("contextmenu", (evento) => {
    if (!areaDoEvento(evento)) return;
    evento.preventDefault();
    if (dados && dados.inteiro) return;
    carregar({ tudo: true });
  });

  // --- teclado ------------------------------------------------------------
  //
  // As teclas 1 e 2 são um interruptor: põem o cursor onde o mouse está e, se
  // ele já estiver ali, tiram. É o gesto mais curto para comparar dois
  // instantes — apontar e apertar, sem procurar botão na tela.

  document.addEventListener("keydown", (evento) => {
    if (evento.ctrlKey || evento.altKey || evento.metaKey) return;
    if (!dados) return;

    if (evento.key === "1" || evento.key === "2") {
      const k = evento.key === "1" ? 0 : 1;
      evento.preventDefault();
      const onde = sobreOMouse ?? (dados.de + dados.ate) / 2;
      // Apertar de novo com o mouse parado em cima do cursor tira o cursor.
      const jaEstava = cursores[k] !== null && sobreOMouse !== null &&
        Math.abs(cursores[k] - sobreOMouse) < (dados.ate - dados.de) * 0.004;
      porCursor(k, jaEstava ? null : onde);
      return;
    }

    if (evento.key === "Escape") {
      evento.preventDefault();
      cursores[0] = cursores[1] = null;
      medida = null;
      espelhar();
      mostrarLeitura();
      if (!ajustarEspaco()) repintar();
      return;
    }

    if (evento.key === "ArrowLeft" || evento.key === "ArrowRight") {
      if (cursores[ativo] === null) return;
      evento.preventDefault();
      const sentido = evento.key === "ArrowRight" ? 1 : -1;
      const passos = [0, 0];
      const ciclos = [0, 0];
      // Um ciclo é pedido EM CICLOS: quantas amostras cabem num ciclo depende
      // da taxa do registro, e essa conta é do servidor.
      if (evento.shiftKey) ciclos[ativo] = sentido;
      else passos[ativo] = sentido;
      lerCursores(passos, ciclos);
    }
  });

  // --- reagir a mudanças --------------------------------------------------

  window.addEventListener("resize", () => {
    // Redesenhar a cada pixel de arrasto seria desperdício; e como o número de
    // colunas depende da largura, o pedido ao servidor também muda.
    clearTimeout(pendente);
    pendente = setTimeout(carregar, 200);
  });

  document.addEventListener("osclab:tema", () => {
    // As cores vêm dos tokens do CSS, então trocar o tema é só repintar.
    if (dados) desenharTudo();
  });

  carregar();
})();
