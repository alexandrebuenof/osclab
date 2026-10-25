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

  //: A versão do formato do pacote que esta tela sabe ler. O servidor manda a
  //: dele em `contrato`; quando não batem, a tela avisa em vez de desenhar
  //: errado. Existe porque os `.py` só são lidos quando o programa SOBE e o
  //: navegador recarrega o `.js` sozinho: quem troca de versão sem reiniciar
  //: fica com tela nova e servidor velho, e o resultado é uma tela que mostra
  //: coisas que não fazem sentido sem dar erro nenhum. Já custou três rodadas.
  const CONTRATO = 24;

  //: A margem de cima abriga a etiqueta numerada dos cursores, que fica FORA da
  //: área de desenho: por dentro ela tapa o pico da onda — e o pico é
  //: exatamente o que se está medindo quando se põe um cursor ali.
  const MARGEM = { esq: 74, dir: 16, topo: 20, baixo: 26 };

  //: A margem esquerda de repouso, que cabe as etiquetas do eixo das ondas.
  //: `MARGEM.esq` cresce acima dela quando os nomes dos digitais estão
  //: inteiros — e cresce para TODOS os graficos, senao o eixo do tempo das
  //: tiras deixaria de coincidir com o das ondas e os cursores mentiriam.
  const MARGEM_BASE = 74;

  //: A margem direita de repouso. Ela cresce quando algum gráfico ganha um
  //: segundo eixo — ver `ajustarMargem`.
  const MARGEM_DIR_BASE = 16;

  //: A fonte das etiquetas das tiras. Fica aqui porque quem mede o nome (para
  //: decidir a margem) e quem o desenha precisam usar exatamente a mesma.
  //: O nome da tira. 12 px e SEMIBOLD: a 10,5 px em cinza ele era a coisa mais
//: apagada da tela, e numa lista de 76 nomes parecidos (`51S1R`, `51S2R`,
//: `51S3R`) é justamente o nome que se lê.
const FONTE_TIRA = "600 12px ui-monospace, Consolas, monospace";

  const ETIQUETA = { largura: 15, altura: 13 };

  const sha = document.body.dataset.sha;
  // Enquanto a janela não chega, a página mostra "Carregando o registro…". Se
  // o script morrer antes disso — e o jeito mais fácil de ele morrer é o
  // Alexandre trocar de versão sem reiniciar o servidor, ficando com o
  // JavaScript novo e o HTML velho em memória — aquela frase fica para sempre e
  // não diz nada. Um "carregando" eterno é o pior aviso de erro que existe.
  window.addEventListener("error", (evento) => {
    const alvo = document.getElementById("graficos");
    if (!alvo || !alvo.querySelector(".vazio")) return;   // já desenhou: não mexe
    alvo.replaceChildren(
      Object.assign(document.createElement("p"), {
        className: "vazio",
        textContent: "A página não carregou: "
          + (evento.message || "erro no script")
          + ". Se o OscLab acabou de ser atualizado, feche o servidor, abra de "
          + "novo e recarregue com Ctrl+F5 — o Python só lê os arquivos .html "
          + "uma vez, na partida.",
      }),
    );
  });

  /** Arredonda o PASSO da lista de sinais e a ALTURA da barra de energia para
   *  um número inteiro de pixels DE TELA.
   *
   * Sem isto, as barras saem com grossuras diferentes em qualquer zoom que não
   * seja redondo. Medido com o navegador a 110 %: a barra de 4 px vira 4,4
   * pixels de tela e o passo de 32 px vira 35,2 — então cada linha da lista
   * começa numa fração diferente de pixel (0; 0,2; 0,4; 0,6; 0,8) e a mesma
   * barra é rasterizada ora em cinco fileiras, ora em quatro. Era isso que ele
   * via: «as barras estão com grossuras diferentes».
   *
   * Duas contas, e as duas em pixels de tela:
   *
   *   passo  = round(32 × dpr) / dpr   → toda linha começa na MESMA fração
   *   altura = round(4 × dpr) / dpr    → a fração é igual nas duas pontas
   *
   * Em zoom redondo as contas devolvem exatamente os valores de antes, então
   * isto não muda nada onde já estava certo. Roda na partida e a cada `resize`
   * — que é o evento que o navegador dispara quando se muda o zoom.
   */
  function ajustarGradeDaLista() {
    const dpr = window.devicePixelRatio || 1;
    const noPixel = (v) => Math.max(1, Math.round(v * dpr)) / dpr;
    const raiz = document.documentElement.style;
    const passo = noPixel(32);
    const vao = noPixel(2);
    // O miolo é o que sobra do passo depois do vão, do respiro de cima e de
    // baixo (4 + 4) e das duas bordas: é ele que o `.topo-do-cartao` trava.
    raiz.setProperty("--vao-do-cartao", `${vao}px`);
    raiz.setProperty("--miolo-do-cartao", `${passo - vao - 8 - 2}px`);
    raiz.setProperty("--alto-da-barra", `${noPixel(4)}px`);
  }
  ajustarGradeDaLista();
  window.addEventListener("resize", ajustarGradeDaLista);

  /** Encosta cada barra de energia na grade de pixels DA TELA.
   *
   * O passo da lista já sai arredondado (ver acima), mas o navegador guarda
   * cada medida de layout num múltiplo de 1/64 de pixel: 31,8181… vira
   * 31,8125, e os 0,0056 de diferença se acumulam linha a linha. Vinte linhas
   * abaixo, a fração de pixel em que a barra começa já é outra — e a mesma
   * barra aparece com uma fileira a mais pintada, que é a grossura diferente
   * que ele viu.
   *
   * Aqui cada barra é empurrada por menos de um pixel de tela, com
   * `translateY`, até o topo dela cair em cima da grade. O desenho não muda de
   * lugar para o olho; muda de lugar para o rasterizador, que é quem estava
   * errando.
   *
   * Roda depois de montar a lista e a cada ROLAGEM: rolar move tudo junto, mas
   * move por uma fração de pixel, e a fração muda. Com `requestAnimationFrame`
   * no meio, uma rolagem longa faz uma medição por quadro, não uma por evento.
   */
  function alinharBarras(raiz) {
    if (!raiz) return;
    const dpr = window.devicePixelRatio || 1;
    const barras = [...raiz.querySelectorAll(".barra-de-energia")];
    if (!barras.length) return;
    // Zera tudo primeiro e mede depois, em dois laços: medir e escrever
    // alternados forçariam um recálculo de layout por barra.
    for (const b of barras) b.style.transform = "";
    const ajustes = barras.map((b) => {
      const topo = b.getBoundingClientRect().top * dpr;
      return (Math.round(topo) - topo) / dpr;
    });
    barras.forEach((b, i) => {
      b.style.transform = ajustes[i] ? `translateY(${ajustes[i]}px)` : "";
    });
  }

  /** Liga o alinhamento das barras ao que rola dentro de `raiz`. */
  function seguirRolagemDasBarras(raiz) {
    if (!raiz || raiz._seguindoBarras) return;
    raiz._seguindoBarras = true;
    let marcado = false;
    const refazer = () => {
      if (marcado) return;
      marcado = true;
      requestAnimationFrame(() => { marcado = false; alinharBarras(raiz); });
    };
    raiz.addEventListener("scroll", refazer, true);
    window.addEventListener("resize", refazer);
  }

  const area = document.getElementById("graficos");
  const rodape = document.getElementById("rodape");

  /** O aviso do pé da tela.
   *
   * Texto vazio ESCONDE a faixa: uma faixa vazia é tela ocupada dizendo nada.
   * Ela era um placar («2000 amostras · 33 ms na tela») e virou só aviso, por
   * pedido do Alexandre — a tela acaba no «+ adicionar gráfico». O que sobrou
   * aqui é o que não se pode calar, e some sozinho quando o motivo some.
   */
  function avisarNoPe(texto) {
    if (!rodape) return;
    rodape.textContent = texto || "";
    rodape.classList.toggle("atencao", !!texto);
    rodape.hidden = !texto;
  }

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

  //: A geometria do gráfico onde o mouse estava na última vez. As teclas 1 e 2
  //: precisam dela para converter o raio do ímã, que é em PIXELS, no tempo que
  //: aqueles pixels valem — e isso muda a cada zoom.
  let geometriaDoMouse = null;

  //: Uma leitura de cada vez: durante o arrasto o último pedido vence.
  let lendo = false;
  let pedidoDeLeitura = null;


  //: As células das tabelinhas, por canal: `{indice, celas, botao}`. O índice
  //: é o do canal NO REGISTRO — é por ele que se casa com a leitura do cursor.
  let celulas = [];

  //: Onde escrever o «1 pu = …» de cada painel fasorial. Guardado na
  //: montagem e preenchido a cada leitura, como as células da tabelinha.
  let notasDoPu = [];
  //: A linha do rodapé do painel de harmônicos que diz sobre QUANTOS ciclos o
  //: espectro foi medido. Refeita a cada leitura: ela depende de onde estão os
  //: cursores, e o painel não é redesenhado quando eles andam.
  let notasDaJanela = [];


  //: De que lado os valores são mostrados: "arquivo", "secundario" ou
  //: "primario". Vai junto em todo pedido, porque a conversão pela relação de
  //: TC/TP é feita no servidor — é ela que decide a faixa vertical do gráfico.
  let lado = lerLadoGuardado();

  //: Duas escolhas independentes, e elas valem para o GRÁFICO e para a
  //: tabelinha ao mesmo tempo:
  //:
  //:                  | instantâneo  | RMS
  //:   60 Hz apagado  | a onda crua  | eficaz verdadeiro (harmônicos + DC)
  //:   60 Hz aceso    | a senoide de | eficaz da fundamental
  //:                  | 60 Hz        |
  //:
  //: O **filtro** é do registro inteiro: meia tela filtrada e meia não seria
  //: armadilha, e ele trava quando o relé já filtrou antes de gravar. A
  //: **medida** é de cada gráfico — corrente em RMS e tensão em instantâneo ao
  //: mesmo tempo é leitura comum numa falta.
  //: **Aceso por padrão.** O sinal filtrado é o que a análise usa — é dele que
  //: saem os valores com que o relé atuou —, e era ele que ficava escondido
  //: atrás de um botão que ninguém sabia que precisava apertar. Quem quiser a
  //: onda como o relé gravou apaga o botão, e aí vê a assimetria da falta, a
  //: saturação do TC e o instante exato do trip, que o filtro não mostra.
  let filtro = lerGuardado("osclab:filtro", ["0", "1"], "1") === "1";

  //: O ÍMÃ: com ele aceso, o cursor gruda no ponto notável mais próximo em vez
  //: de cair onde a mão soltou. Do registro inteiro, como o filtro — um cursor
  //: que gruda num gráfico e não gruda no de baixo seria armadilha, porque é o
  //: MESMO cursor atravessando os dois. Ver `plot/imas.py`.
  let magnetico = lerGuardado("osclab:imã", ["0", "1"], "0") === "1";

  //: No que cada cursor grudou da última vez, ou `null`. Serve para a tela
  //: DIZER no que grudou: com um pico e uma transição a três pixels um do
  //: outro, o cursor pega um dos dois e sem etiqueta ninguém sabe qual — e o
  //: número que sair dali vai para o laudo.
  const presos = [null, null];

  //: O raio do ímã, em pixels. Largo o bastante para a mão, estreito o
  //: bastante para o cursor não saltar para um ponto que o usuário não estava
  //: mirando. Fora dele o ímã não age, e o cursor cai onde foi posto.
  const RAIO_DO_IMA = 14;

  //: A ordem de preferência quando dois pontos estão à MESMA distância do
  //: mouse. Primeiro o mais exato: a transição de um digital é uma amostra sem
  //: nenhuma dúvida; o início da perturbação é um palpite calibrado; o extremo
  //: de uma onda amostrada cai entre duas amostras e a gente entrega a mais
  //: próxima. Empate é raro, mas quando acontece tem que ser sempre igual.
  const PRECEDENCIA = { transicao: 0, inicio: 1, zero: 2, pico: 3 };

  //: O que o ímã PODE procurar, na ordem em que aparece no menu. Só `transicao`
  //: vem ligado: é o ponto que serve à medida mais comum do ofício (trip,
  //: abertura, religamento) e o único que nunca é ambíguo. O resto o usuário
  //: liga quando precisa — tela que já vem com tudo ligado é tela em que o
  //: cursor gruda onde ninguém pediu.
  const ATRACOES = [
    ["transicao", "transições de digital"],
    ["inicio", "início da falta"],
    ["pico", "picos de analógico"],
    ["zero", "passagens por zero"],
  ];

  //: Quais delas estão ligadas. Mora na tela e fica guardado: quem analisa com
  //: os picos ligados costuma querer o mesmo na próxima oscilografia.
  let atracoes = lerAtracoesGuardadas();

  function lerAtracoesGuardadas() {
    const validas = new Set(ATRACOES.map(([chave]) => chave));
    try {
      const cru = JSON.parse(localStorage.getItem("osclab:imã:atracoes") || "");
      if (Array.isArray(cru)) {
        const escolhidas = cru.filter((x) => validas.has(x));
        // Lista vazia guardada seria um ímã que nunca gruda em nada, e um
        // botão aceso que não faz nada é pior que botão apagado.
        if (escolhidas.length) return new Set(escolhidas);
      }
    } catch { /* nada guardado, ou lixo: vale o padrão */ }
    return new Set(["transicao"]);
  }

  function guardarAtracoes() {
    guardar("osclab:imã:atracoes", JSON.stringify([...atracoes]));
  }

  //: O ARRANJO da tela: a lista de painéis, na ordem em que aparecem. Cada um
  //: é `{id, tipo, nome, sinais[], medida}`. É o estado principal desta tela —
  //: tudo que o usuário monta mora aqui, e é isto que vai ao servidor a cada
  //: pedido. Ver `plot/paineis.py` para por que o NOME e a ORDEM não são
  //: assunto do servidor.
  let paineis = [];

  // --- várias oscilografias na mesma aba ------------------------------------
  //
  // Uma aba pode ter até três registros: o desta página (IED A) e mais dois
  // (IED B, IED C). A lista dos outros fica na SESSÃO desta aba do navegador
  // — fechar a aba esquece, como esquece o arranjo — e viaja no corpo de todo
  // pedido, junto com os painéis. Quem alinha, monta e lê é o servidor: ver
  // `plot/varios.py` e `plot/alinhamento.py`. Escolhas dele, 22/10/2026
  // (maquete «abas»): um conjunto de gráficos por IED, selo antes do nome,
  // uma linha por IED na tira, alinhamento pelo início da falta.

  const CHAVE_DA_ABA = `osclab:aba:${sha}:${new URLSearchParams(location.search).get("aba") || ""}`;
  const MAXIMO_DE_OUTROS = 2;
  const NOME_DO_ALINHAMENTO = {
    falta: "início da falta", disparo: "disparo", hora: "hora do arquivo",
  };

  function lerAba() {
    try {
      const cru = JSON.parse(sessionStorage.getItem(CHAVE_DA_ABA) || "{}");
      return {
        outros: Array.isArray(cru.outros) ? cru.outros.slice(0, MAXIMO_DE_OUTROS) : [],
        alinhar: NOME_DO_ALINHAMENTO[cru.alinhar] ? cru.alinhar : "falta",
      };
    } catch (_e) {
      return { outros: [], alinhar: "falta" };
    }
  }
  function guardarAba() {
    try {
      sessionStorage.setItem(CHAVE_DA_ABA, JSON.stringify(
        { outros: outrosRegistros, alinhar: alinharPor }));
    } catch (_e) { /* sem armazenamento: vale até recarregar */ }
  }
  let { outros: outrosRegistros, alinhar: alinharPor } = lerAba();

  /** Há mais de um IED nesta aba? Com um só, nada de letra em lugar nenhum. */
  const variosIeds = () => !!(dados && dados.ieds && dados.ieds.length > 1);

  /** O selo do IED (A, B, C) antes do nome de um sinal, ou `null`. */
  function seloDoIed(letra) {
    if (!variosIeds()) return null;
    const qual = letra || "A";
    const selo = criar("span", `selo-ied ied-${qual.toLowerCase()}`, qual);
    const ficha = (dados.ieds || []).find((x) => x.letra === qual);
    selo.title = ficha ? `IED ${qual}: ${ficha.apelido || ficha.arquivo}` : `IED ${qual}`;
    return selo;
  }

  /** A coluna de `tempo` mais perto do instante `t`. */
  function colunaMaisProxima(tempo, t) {
    let a = 0, b = tempo.length - 1;
    while (b - a > 1) {
      const m = (a + b) >> 1;
      if (tempo[m] < t) a = m; else b = m;
    }
    return Math.abs(tempo[a] - t) <= Math.abs(tempo[b] - t) ? a : b;
  }

  /** Muda a lista de registros da aba e recomeça o arranjo no padrão. */
  function trocarRegistros(lista) {
    // Sem Ctrl+Z: o desfazer é do arranjo da tela, e a lista de registros
    // da aba não mora nele.
    outrosRegistros = lista.slice(0, MAXIMO_DE_OUTROS);
    guardarAba();
    paineis = [];
    carregar();
    if (estadoLoc.aberta) pedirLocalizacao();
  }

  /** A tira dos IEDs: uma linha por registro, mais os controles da aba. */
  function montarTiraDosIeds() {
    const caixa = document.getElementById("tira-dos-ieds");
    if (!caixa || !dados) return;
    caixa.hidden = false;
    caixa.replaceChildren();
    const ieds = dados.ieds || [];

    const barra = criar("div", "barra-dos-ieds");
    const ancora = criar("span", "ancora-de-menu");
    ancora.id = "menu-mais-oscilografia";
    const mais = criar("button", "chave mais-oscilografia", "+ adicionar oscilografia");
    mais.type = "button";
    mais.disabled = outrosRegistros.length >= MAXIMO_DE_OUTROS;
    mais.title = mais.disabled
      ? "Até três oscilografias por aba: tire uma para pôr outra."
      : "Pôr outro registro do acervo nesta aba, para comparar no mesmo tempo.";
    mais.addEventListener("click", abrirEscolhaDeRegistro);
    barra.append(mais, ancora);

    if (ieds.length > 1) {
      barra.append(criar("span", "rotulo-dos-ieds", "alinhar por"));
      for (const [chave, nome] of Object.entries(NOME_DO_ALINHAMENTO)) {
        const b = criar("button", "chave" + (alinharPor === chave ? " escolhido" : ""), nome);
        b.type = "button";
        b.title = {
          falta: "O início da perturbação de cada registro no mesmo instante. "
            + "Alinha dois terminais mesmo com os relógios dos relés em desacordo.",
          disparo: "O gatilho de cada registro no mesmo instante.",
          hora: "O carimbo de tempo de cada arquivo: mostra a diferença de "
            + "relógio entre os relés como ela é.",
        }[chave];
        b.addEventListener("click", () => {
          if (alinharPor === chave) return;
          alinharPor = chave;
          guardarAba();
          carregar();
          // A localização lê B no instante que o alinhamento manda.
          if (estadoLoc.aberta) pedirLocalizacao();
        });
        barra.append(b);
      }
    }
    caixa.append(barra);
    if (ieds.length < 2) return;

    for (const ficha of ieds) caixa.append(linhaDoIed(ficha));
  }

  function linhaDoIed(ficha) {
    const linha = criar("div", "linha-do-ied");
    linha.append(seloDoIed(ficha.letra));
    const nome = criar("span", "apelido-do-ied", ficha.apelido || ficha.arquivo || ficha.sha);
    nome.title = `Arquivo: ${ficha.arquivo}`;
    const lapis = criar("button", "lapis-do-ied", "✎");
    lapis.type = "button";
    lapis.title = "Dar um nome a este IED. O arquivo não muda.";
    lapis.addEventListener("click", () => {
      const campo = document.createElement("input");
      campo.className = "campo-do-apelido";
      campo.value = ficha.apelido || "";
      campo.placeholder = ficha.arquivo;
      let pronto = false;
      const terminar = async (gravar) => {
        if (pronto) return;
        pronto = true;
        if (gravar) {
          try {
            await fetch(`/api/acervo/${ficha.sha}/nome`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ nome: campo.value.trim() }),
            });
          } catch (_e) { /* a tira volta como estava */ }
        }
        carregar();
      };
      campo.addEventListener("keydown", (e) => {
        if (e.key === "Enter") terminar(true);
        if (e.key === "Escape") terminar(false);
      });
      campo.addEventListener("blur", () => terminar(true));
      nome.replaceWith(campo);
      lapis.hidden = true;
      campo.focus();
    });
    linha.append(nome, lapis);

    const fato = (rotulo, valor, classe, dica) => {
      const f = criar("span", "fato-do-ied" + (classe ? ` ${classe}` : ""));
      f.append(criar("b", null, rotulo), criar("span", null, valor));
      if (dica) f.title = dica;
      linha.append(f);
    };
    if (ficha.rele) fato("relé", ficha.rele);
    if ((ficha.taxas_hz || []).length) fato("taxa", `${ficha.taxas_hz.join(" / ")} Hz`);
    if (ficha.letra !== "A") {
      fato("alinhado por", NOME_DO_ALINHAMENTO[ficha.alinhado_por] || "nada",
           ficha.alinhado_por !== alinharPor ? "aviso-do-ied" : "",
           ficha.alinhado_por !== alinharPor
             ? "Este registro não deu para alinhar do jeito pedido; valeu o seguinte."
             : "");
      if (ficha.precisao_ms !== null && ficha.precisao_ms !== undefined) {
        fato("precisão", `± ${formatar(ficha.precisao_ms, 2)} ms`, "",
             "Uma amostra do registro mais lento: serve para OLHAR as formas e "
             + "ver quem disparou antes, não para calcular fasor entre os dois "
             + "registros (1 ms são 21,6° a 60 Hz).");
      }
      if (ficha.relogio_ms !== null && ficha.relogio_ms !== undefined) {
        const r = ficha.relogio_ms;
        fato("relógio × A", `${r >= 0 ? "+" : "−"}${formatar(Math.abs(r), 1)} ms`,
             Math.abs(r) > (ficha.precisao_ms || 1) ? "aviso-do-ied" : "",
             "A hora do mesmo evento neste arquivo menos a hora dele no IED A. "
             + "Aparece qualquer que seja o alinhamento: é a sincronização dos relés.");
      }
      const tirar = criar("button", "botao-x tirar-do-ied", "×");
      tirar.type = "button";
      tirar.title = "Tirar este registro da aba. Ele continua no acervo.";
      tirar.addEventListener("click", () =>
        trocarRegistros(outrosRegistros.filter((x) => x.sha !== ficha.sha)));
      linha.append(tirar);
    }
    return linha;
  }

  /** A lista do acervo, para pôr mais um registro nesta aba. */
  // O «eventos» do cabeçalho: cinza até a lista de eventos do relé ser lida.
  // O clique EXPLICA, em vez de não responder — a regra do dicionário.
  document.getElementById("eventos")?.addEventListener("click", () => {
    menuSuspenso("menu-dos-eventos", "eventos do relé", (caixa) => {
      caixa.append(criar("p", "nada-a-ajustar",
        "Ainda não implementado. A lista de eventos (partida, trip, abertura "
        + "do disjuntor, com hora) vai ser lida do .hdr/.txt que acompanha o "
        + "registro — o da Schneider traz o «Fault log» — ou importada de um "
        + "arquivo do relé, e vai ficar ligada ao cursor."));
    });
  });

  async function abrirEscolhaDeRegistro() {
    let itens = [];
    try {
      const r = await fetch("/api/acervo");
      itens = (await r.json()).itens || [];
    } catch (_e) { /* lista vazia: o menu diz isso */ }
    const ja = new Set([sha, ...outrosRegistros.map((x) => x.sha)]);
    menuSuspenso("menu-mais-oscilografia", "pôr nesta aba:", (caixa) => {
      const livres = itens.filter((x) => !ja.has(x.sha));
      if (!livres.length) {
        caixa.append(criar("p", "nota-do-menu", "Não há outro registro no acervo."));
        return;
      }
      for (const x of livres) {
        const b = criar("button", "opcao-de-registro");
        b.type = "button";
        b.append(criar("span", "nome-do-registro", x.nome));
        const sub = [x.estacao, x.equipamento, x.disparo].filter(Boolean).join(" · ");
        if (sub) b.append(criar("span", "sub-do-registro", sub));
        b.title = x.nome;
        b.addEventListener("click", () => {
          if (menuAberto) menuAberto();
          trocarRegistros([...outrosRegistros, { sha: x.sha }]);
        });
        caixa.append(b);
      }
    });
  }

  //: Contador dos ids que a tela cria. Não reaproveita número de painel
  //: apagado: id repetido casaria seleção e leitura com o painel errado.
  let proximoId = 1;

  const painelPorId = (id) => paineis.find((x) => x.id === id);

  /** O corpo de um pedido: o arranjo, ou nada na primeira carga.
   *
   * Vai no CORPO, e não na URL, porque é uma estrutura — painéis com listas de
   * sinais dentro. Sem arranjo nenhum, o servidor monta o padrão, e é assim
   * que a primeira janela nasce.
   */
  function pedidoComLayout() {
    if (!paineis.length && !outrosRegistros.length) return undefined;
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paineis: !paineis.length ? null : paineis.map((x) => ({
          id: x.id, tipo: x.tipo, nome: x.nome, do_padrao: x.do_padrao,
          medida: x.medida, sinais: x.sinais,
          // Só o fasorial usa, e ela VAI ao servidor: o sinal que é o zero
          // dos ângulos pode não estar no diagrama, e mesmo assim o fasor
          // dele precisa ser calculado. Ver `plot/paineis.py`.
          referencia: x.referencia || "",
          // Só o plano complexo usa: se a referência vale o ângulo dela no
          // começo do registro (fixa) ou em cada instante. Muda o caminho que
          // o servidor calcula. Ver `plot/complexo.py`.
          fixa: x.fixa !== false,
          // Só o triângulo usa: o VÍNCULO de onde ele sai (um campo, não seis
          // ids) e quais camadas estão acesas. Ver `plot/triangulo.py`.
          vinculo: x.vinculo || "",
          camadas: x.camadas || ["linha", "fase", "corrente"],
          // Só o plano de impedância usa: qual laço desenhar. Vai ao
          // servidor porque muda a CONTA — a de terra e a de fase são
          // fórmulas diferentes. Ver `plot/impedancia.py`.
          laco: x.laco || "AN",
          // Idem: o que o usuário digitou por cima do ajuste do arquivo.
          // Muda a zona desenhada, o veredito e o «% da LT», então é conta
          // do servidor. Sempre em ohms SECUNDÁRIOS.
          manuais: x.manuais || {},
          // Idem: a forma em vista (mho, quad, ambas). Muda o VEREDITO.
          caracteristica: x.caracteristica || "",
          // Só o plano alfa usa: de que terminal se olha e os dois ajustes
          // da característica. Mudam o `k` e a decisão, que são conta do
          // servidor. Ver `plot/alfa.py`.
          vista: x.vista || "local",
          // O que o servidor devolveu (lido do relé, digitado ou o típico).
          // Sem valor, vai `null` e o servidor decide — um 6 posto aqui se
          // confundiria com um 6 digitado.
          r87: x.r87 ?? null,
          ang87: x.ang87 ?? null,
          // Qual trinca é o local e qual é o remoto (`G1`, `G2`). Vazio é
          // «a ordem do arquivo». Do servidor ela volta como objeto.
          local: typeof x.local === "string" ? x.local : (x.local && x.local.rotulo) || "",
          // Só o diferencial: o que foi digitado e os suspeitos aceitos.
          // Mudam a conta e os estados, então vão ao servidor.
          ajustes87: x.ajustes87 || {},
          // Só o plano alfa entre dois registros: refinar pela pré-falta.
          refinar: !!x.refinar,
          remoto: typeof x.remoto === "string" ? x.remoto : (x.remoto && x.remoto.rotulo) || "",
        })),
        // As contas do usuário vão junto, e pelo mesmo motivo dos painéis:
        // são da TELA, o servidor não guarda nenhuma, e sem elas o catálogo
        // da resposta não teria os sinais que elas criam.
        contas,
        // Os OUTROS registros desta aba, e como se alinham. Ver `plot/varios.py`.
        registros: outrosRegistros,
        alinhar: alinharPor,
      }),
    };
  }

  /** Na primeira carga, a tela adota o arranjo que o servidor montou.
   *
   * Só na primeira: depois disso quem manda no arranjo é a tela. Readotar a
   * cada resposta apagaria em silêncio um sinal que o servidor tenha recusado
   * (um terceiro eixo, por exemplo) — o aviso já diz que ele não coube, e
   * tirá-lo da lista tiraria também a chance de o usuário entender por quê.
   */
  function adotarPaineis() {
    if (paineis.length || !dados.paineis) return;
    paineis = dados.paineis.map((x) => ({
      id: x.id,
      tipo: x.tipo,
      nome: x.nome,
      do_padrao: !!x.do_padrao,
      medida: x.medida || "instantaneo",
      cursor: x.cursor === 2 ? 2 : 1,
      referencia: x.referencia || null,
      //: `id do sinal → token de cor`. Só da tela: cor não muda número
      //: nenhum, então não vai ao servidor. Entra no Ctrl+Z junto com o
      //: resto do arranjo.
      cores: {},
      sinais: x.tipo === "digital"
        ? (x.tiras || []).map((s) => s.id || String(s.indice))
        : (x.sinais || []).map((s) => s.id),
    }));
    proximoId = paineis.length + 1;
  }


  //: O zero dos ângulos é de cada DIAGRAMA FASORIAL, e mora no painel
  //: (`referencia`). O servidor continua mandando o ângulo a partir da regra
  //: automática — a tensão da fase A —, e o painel subtrai o do sinal que o
  //: usuário escolher. Ver `escolherReferencia`.

  //: Em que unidade a linha do tempo está: "ms" ou "ciclos". A escolha é do
  //: usuário, fica guardada no navegador, e vale para os dois cursores e para
  //: o Δt ao mesmo tempo — é a mesma medida vista de dois jeitos.
  let unidadeDoTempo = lerUnidadeGuardada();

  //: A linha do tempo de cada tabelinha: [rotulo, t1, t2, Δ].
  let linhasDoTempo = [];

  //: A tabelinha estava aberta na última vez que se olhou? Trocar isso muda a
  //: largura do gráfico, e largura nova pede dados novos (ver `ajustarEspaco`).
  let comTabela = false;

  //: Os filtros que o OscLab sabe aplicar: `[chave, rótulo, explicação]`.
  //:
  //: O botão diz se o filtro está ligado e a setinha diz QUAL. Sem isso,
  //: "filtrado" na tela não significa nada preciso — um Fourier de um ciclo e
  //: um cosseno dão números diferentes na mesma falta, e é o número que o
  //: usuário lê. A escolha é o ESTIMADOR DO FASOR do programa inteiro: vale
  //: com o botão ligado ou não, para o cursor, as curvas de 60 Hz, as
  //: sequências, o fasorial, o complexo e a impedância (`dsp/fasor.usando`).
  //: `[chave, nome, explicação do hover, quem usa, uma linha para o menu]`.
  //: Os três de baixo vieram dos manuais do parque (22/10/2026, maquete 1 de
  //: «filtros-10»); o «pico do ciclo» da ABB fica de fora até a divisão do
  //: manual (÷2 ou ÷√2) ser conferida. Ver `dsp/fasor.ESTIMADORES`.
  const FILTROS = [
    ["fourier", "Fourier (um ciclo)",
     "Fasor de um ciclo pela transformada discreta. É o padrão, e o que foi "
     + "conferido contra o SIGRA e contra os relés. Atrasa até um ciclo nas "
     + "transições.",
     "padrão",
     "DFT de um ciclo que termina no instante. Rejeita todo harmônico inteiro."],
    ["cosseno", "cosseno (SEL)",
     "O filtro cosseno de um ciclo da linha SEL: o fasor é o cosseno agora "
     + "mais o cosseno de 1/4 de ciclo atrás. Rejeita a exponencial da falta "
     + "melhor que o Fourier e bate com o número do relé SEL; o primeiro "
     + "fasor sai em 1,25 ciclo. A onda de 60 Hz é a mesma dos dois.",
     "SEL",
     "Real = cosseno de um ciclo agora; imaginária = o mesmo ¼ de ciclo atrás."],
    ["dois_ciclos", "Fourier (dois ciclos)",
     "O «2-cycle filter» da sobrecorrente do SIPROTEC 5: a mesma DFT, com "
     + "janela de dois ciclos. Rejeita mais harmônico e inter-harmônico e "
     + "atrasa um ciclo a mais. A Siemens não publica os coeficientes; esta é "
     + "a DFT padrão de dois ciclos.",
     "Siemens SIPROTEC 5",
     "DFT de dois ciclos: mais limpa, um ciclo a mais de atraso."],
    ["meio_ciclo", "Fourier (meio ciclo)",
     "A DFT de meio ciclo da distância rápida do ABB RET670 e da tensão no "
     + "GE T60. Sobe em meio ciclo, mas oscila com a contínua da falta e com "
     + "os harmônicos pares, que meio ciclo não rejeita. É uma versão "
     + "genérica: os coeficientes adaptativos da ABB não são publicados.",
     "ABB RET670 · GE (tensão)",
     "DFT de meio ciclo: sobe em meio ciclo, oscila com DC e harmônico par."],
    ["pico_a_pico", "pico a pico",
     "O «Peak-to-Peak» da sobrecorrente ABB 615/620: (máximo − mínimo do "
     + "último ciclo) ÷ 2√2. Cancela a contínua, não rejeita harmônico e "
     + "aguenta TC saturado. Dá só MÓDULO: o ângulo, as componentes de "
     + "sequência e os planos continuam saindo do Fourier.",
     "ABB 615/620 · RET670",
     "(máx − mín do último ciclo) ÷ 2√2. Só módulo: ângulo segue o Fourier."],
  ];

  //: Qual deles está aplicado. Fourier sempre ao abrir (escolha dele,
  //: 21/10/2026): é o conferido. Só vai ao servidor quando não é o padrão.
  let filtroEscolhido = FILTROS[0][0];

  //: Distância em pixels para o mouse "pegar" um cursor.
  const PEGADA = 7;

  // --- utilidades ---------------------------------------------------------

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  /* ------------------------------------------------------------------
   * O NOME DE UM SINAL, escrito com as marcas em subscrito
   * ------------------------------------------------------------------
   *
   * O nome continua sendo UM, em texto puro, montado no Python
   * (`plot/sinais.nome`): `IAW · 60Hz RMS`. É esse que vai para o
   * relatório, para a fórmula e para a busca. O que muda aqui é só como a
   * TELA o desenha — `IAW` com `60Hz RMS` em subscrito.
   *
   * A cor das marcas não é enfeite: é a MESMA da fatia correspondente da
   * barra de energia do cartão. Turquesa é 60 Hz, rosa é contínua, e o RMS
   * fica na cor do texto porque ele não é fatia nenhuma — é o total. Lendo
   * de um jeito só: colorido é uma parcela da energia, sem cor é o todo.
   *
   * E a cor REFORÇA, não carrega: tamanho e posição já distinguem as
   * marcas sem ela, que é o que mantém o nome legível num relatório
   * impresso em preto e branco.
   *
   * Houve uma versão em subscrito antes, retirada no marco 0.3 porque o
   * servidor mandava o nome partido em três e ele passava a existir em
   * duas formas. Esta não tem esse defeito: o servidor manda UMA string, e
   * quem parte é a tela, na hora de desenhar. Ver o cabeçalho de
   * `plot/sinais.py`.
   */
  const MARCAS_COM_COR = { DC: "marca-dc" };
  const marcaDeFrequencia = /^\d+Hz$/;

  /** Preenche `destino` com o nome desenhado. Devolve o próprio destino. */
  const escreverNome = (destino, nome) => {
    const texto = String(nome == null ? "" : nome);
    destino.replaceChildren();
    const corte = texto.indexOf(" · ");
    if (corte < 0) {
      destino.append(document.createTextNode(texto));
      destino.title = destino.title || texto;
      return destino;
    }
    destino.append(document.createTextNode(texto.slice(0, corte)));
    const marcas = texto.slice(corte + 3).split(/\s+/).filter(Boolean);
    for (const m of marcas) {
      const sub = criar("sub", "marca-do-nome", m);
      if (marcaDeFrequencia.test(m)) sub.classList.add("marca-hz");
      else if (MARCAS_COM_COR[m]) sub.classList.add(MARCAS_COM_COR[m]);
      destino.append(sub);
    }
    // O nome em texto puro fica no `title`: é ele que se copia para uma
    // mensagem, e é ele que o buscador e a fórmula usam.
    if (!destino.title) destino.title = texto;
    return destino;
  };

  /** `criar`, mas desenhando o nome com as marcas em subscrito. */
  const criarNome = (tag, classe, nome) =>
    escreverNome(criar(tag, classe), nome);

  /** As palavras de um nome, para procurar: maiúsculas, sem o `·`. */
  const palavrasDoNome = (nome) =>
    String(nome == null ? "" : nome).toUpperCase().replace(/·/g, " ")
      .split(/\s+/).filter(Boolean);

  /** A busca casa com este nome?
   *
   * Uma função só, usada por TODOS os buscadores da tela — o de sinais, o da
   * calculadora, o dos digitais, o dos atalhos. Eram quatro `includes` soltos
   * com quatro comportamentos, e `IAW RMS` não achava `IAW · 60Hz RMS` em
   * nenhum deles: o nome real tem `60Hz` no meio, e a busca exigia que os
   * pedaços fossem vizinhos.
   *
   * Duas regras, nesta ordem:
   *
   * 1. **Por palavra, em ordem, com buracos.** Cada palavra digitada tem que
   *    aparecer dentro de alguma palavra do nome, e na ordem — mas não
   *    precisam ser vizinhas. `IAW RMS` acha `IAW · 60Hz RMS` E `IAW · RMS`;
   *    `IA` acha `Current IA`. A ordem é o que impede `RMS IAW` de achar
   *    qualquer coisa, e é o que mantém a lista curta.
   *
   * 2. **Tudo colado.** Junta as palavras dos dois lados e procura. É o que
   *    faz `iaw60` achar `IAW · 60Hz` sem o espaço e sem o `·`, que é como
   *    se digita num teclado ABNT — o ponto médio não está nele.
   */
  const combinaNome = (nome, procura) => {
    const pedidas = palavrasDoNome(procura);
    if (!pedidas.length) return true;
    const alvo = palavrasDoNome(nome);
    let i = 0;
    const emOrdem = pedidas.every((pedaco) => {
      while (i < alvo.length) {
        if (alvo[i++].includes(pedaco)) return true;
      }
      return false;
    });
    if (emOrdem) return true;
    return alvo.join("").includes(pedidas.join(""));
  };

  /* ------------------------------------------------------------------
   * As figurinhas do cartão de sinal
   * ------------------------------------------------------------------
   *
   * Desenhadas, e não escritas: a folha «RMS» ao lado de uma linha que sobe,
   * fica estável e cai diz o que é um eficaz sem exigir que se leia a sigla.
   * São as mesmas três de sempre, para a pessoa aprender uma vez.
   */
  const SVG_DO_ICONE = "http://www.w3.org/2000/svg";

  function _tracinho(largura, altura, pontos, cor, grossura) {
    const sv = document.createElementNS(SVG_DO_ICONE, "svg");
    sv.setAttribute("viewBox", `0 0 ${largura} ${altura}`);
    sv.setAttribute("width", largura);
    sv.setAttribute("height", altura);
    sv.setAttribute("aria-hidden", "true");
    const traco = document.createElementNS(SVG_DO_ICONE, "path");
    traco.setAttribute("d", pontos);
    traco.setAttribute("fill", "none");
    traco.setAttribute("stroke", cor || "currentColor");
    traco.setAttribute("stroke-width", grossura || 1.1);
    traco.setAttribute("stroke-linecap", "round");
    traco.setAttribute("stroke-linejoin", "round");
    sv.append(traco);
    return sv;
  }

  /** A figurinha de uma folha: onda, eficaz ou contínua.
   *
   * A onda vem SUJA quando o filtro está apagado e limpa quando está aceso —
   * é o próprio ícone dizendo o que o interruptor faz com aquele sinal.
   */
  function iconeDaFolha(grandeza, filtrado) {
    const L = 30;
    const A = 11;
    const ini = 0.30 * L;
    const fim = 0.74 * L;
    let d = "";
    for (let x = 0; x <= L; x += 1) {
      const fase = (x / L) * Math.PI * 12;
      let y;
      if (grandeza === "instantaneo") {
        const env = (x < ini || x > fim) ? 0.34 : 1;
        const dc = (x >= ini && x <= fim)
          ? 1.1 * Math.exp(-(x - ini) / 6) : 0;
        const sujeira = filtrado
          ? 0 : 0.85 * Math.sin(3 * fase + 0.6) * env;
        y = A / 2 - (A / 2 - 1) * env * Math.sin(fase) - sujeira - dc;
      } else if (grandeza === "rms") {
        let v = 0.30;
        if (x >= ini && x <= fim) v = 0.30 + 0.70 * Math.min(1, (x - ini) / 3.2);
        else if (x > fim) v = 0.30 + 0.70 * Math.max(0, 1 - (x - fim) / 2.6);
        y = A - 1.3 - (A - 2.8) * v;
      } else {
        const v = x >= ini ? Math.exp(-(x - ini) / 5.5) : 0;
        y = A - 1.6 - (A - 3.4) * v;
      }
      d += (x ? "L" : "M") + x + " " + y.toFixed(2);
    }
    const sv = _tracinho(L, A, d, "currentColor",
                         grandeza === "instantaneo" ? 1 : 1.5);
    sv.setAttribute("class", "icone-da-folha");
    return sv;
  }

  /** De onde o sinal vem, numa bolinha colorida ao lado do nome.
   *
   * Era um desenho por procedência — antena, sigma, calculadora. Saíram: o
   * sigma se lia como somatório (que não é o que ele queria dizer) e ninguém
   * identificou a antena. Desenho pequeno ou é um símbolo que a pessoa já
   * conhece, ou é charada.
   *
   * A bolinha faz os dois trabalhos de uma vez. Ela carrega a cor, e o NOME
   * fica branco — antes a cor estava na letra, e nome colorido no meio de
   * nomes brancos se lê como estado («este está selecionado?»), não como
   * família. Cor numa bolinha ao lado se lê como etiqueta.
   *
   * O que cada cor quer dizer continua escrito no `title`, porque cor sozinha
   * não se lê: num relatório impresso em preto e branco as três viram cinza.
   */
  /** O valor de um token de cor do CSS — guardado.
   *
   * `getComputedStyle` força o navegador a resolver o estilo da página INTEIRA
   * a cada chamada, e esta função é chamada de dentro do laço de desenho: uma
   * vez por cor da moldura, uma por sinal, uma por cursor, em cada painel.
   * Medido arrastando um cursor sessenta passos: **2755 resoluções de estilo**,
   * umas quarenta e seis por movimento do mouse.
   *
   * Os tokens só mudam quando o TEMA muda, que é um evento discreto e raro —
   * então guardá-los é exato, não aproximado. A memória é limpa no
   * `osclab:tema`, lá embaixo, que é o único lugar em que eles deixam de
   * valer.
   */
  const _tokens = new Map();
  const token = (nome) => {
    let valor = _tokens.get(nome);
    if (valor === undefined) {
      valor = getComputedStyle(document.documentElement)
        .getPropertyValue(nome).trim();
      _tokens.set(nome, valor);
    }
    return valor;
  };

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
    p.set("colunas", String(colunasDeVerdade()));
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
    if (filtro) p.set("filtro", "1");
    if (filtroEscolhido !== FILTROS[0][0]) p.set("estimador", filtroEscolhido);

    try {
      const r = await fetch(`/api/onda/${sha}?${p}`, pedidoComLayout());
      if (!r.ok) {
        const erro = await r.json().catch(() => ({}));
        throw new Error(erro.erro || `o servidor respondeu ${r.status}`);
      }
      dados = await r.json();
      if ((dados.contrato || 0) !== CONTRATO) {
        avisarDeVersao();
        return;
      }
      // Na primeira carga quem decidiu o lado foi o servidor; a tela obedece,
      // senão nenhum botão ficaria aceso.
      lado = dados.lado_pedido;
      adotarPaineis();
      marcarLado();
      // O veredito de bruto × filtrado chega junto com a janela: é ele que
      // trava o botão e é ele que a tira anuncia.
      marcarBotoes();
      mostrarFiltragem();
      montarTiraDosIeds();
      mostrarTaxa();
      mostrarSemSinal();
      window.__janela = { de: dados.de, ate: dados.ate };   // para teste no navegador
      arrastoPx = 0;
      desenharTudo();
    } catch (erro) {
      avisarDaFalha(erro);
    }
  }

  /** Falhou o pedido: avisa SEM apagar o que já está na tela.
   *
   * Apagar era o comportamento antigo e era o errado. Uma falha de conexão —
   * servidor fechado, tropeço de rede — destruía o gráfico que o usuário
   * estava medindo, e ele perdia zoom, cursores e o lugar onde estava. Quem
   * fica sem resposta é o pedido novo; o desenho antigo continua tão válido
   * quanto era um segundo antes.
   *
   * Só quando não há NADA desenhado é que a mensagem toma a tela, porque aí
   * não há o que preservar.
   */
  function avisarDaFalha(erro) {
    const recado = explicar(erro);
    if (!blocos.length) {
      area.replaceChildren(criar("p", "vazio", recado));
      return;
    }
    avisarNoPe(recado);
  }

  /** O erro em português de gente, e com o que fazer a respeito.
   *
   * `fetch` levanta um `TypeError` com a mensagem "Failed to fetch" quando a
   * conexão nem chega a acontecer — quase sempre porque o servidor foi fechado
   * e a aba ficou aberta. A mensagem crua não diz nada a quem não escreve
   * JavaScript, e o usuário fica olhando para um erro que não é dele.
   *
   * Erro que o servidor RESPONDEU é outra coisa: aí a mensagem veio do Python,
   * foi escrita para o engenheiro de proteção, e passa inteira.
   */
  function explicar(erro) {
    if (erro instanceof TypeError) {
      return "O servidor do OscLab não respondeu. Ele ainda está aberto? "
           + "Se você o fechou, abra de novo com osclab.cmd e recarregue esta "
           + "página.";
    }
    return `Não consegui ler o registro: ${erro.message}`;
  }

  /** Um contexto de canvas que existe so' para medir texto. */
  const regua = document.createElement("canvas").getContext("2d");

  /** O texto que cabe em `largura`, cortado com reticencias se preciso. */
  function encaixar(texto, largura) {
    regua.font = FONTE_TIRA;
    if (regua.measureText(texto).width <= largura) return texto;
    let corte = texto.length;
    while (corte > 1 && regua.measureText(`${texto.slice(0, corte)}…`).width > largura) {
      corte -= 1;
    }
    return `${texto.slice(0, corte)}…`;
  }

  /** Abre a margem esquerda ate' caber o maior nome de digital.
   *
   * O nome de um digital de IED chega a 27 caracteres (`MAIN : Timer stage N
   * elaps.`), e a margem de repouso cabe dez. Alargar so' o bloco das tiras
   * seria o caminho obvio e esta' errado: as tiras dividem o eixo do tempo com
   * as ondas, e dois eixos que comecam em x diferentes poem o mesmo instante
   * em dois lugares da tela. Entao a margem e' uma so', para todos.
   *
   * O teto de 42 % existe porque nome nenhum vale mais que a onda: passando
   * disso o nome volta a ser cortado, e o completo continua no `title`.
   */
  function ajustarMargem() {
    // O segundo eixo precisa de espaço à direita, e — como a margem esquerda —
    // ele vale para TODOS os gráficos: dois eixos do tempo que terminam em x
    // diferentes põem o mesmo instante em dois lugares da tela.
    const temDireito = (dados && dados.paineis || []).some((x) => x.eixo_dir);
    MARGEM.dir = temDireito ? 62 : MARGEM_DIR_BASE;

    MARGEM.esq = MARGEM_BASE;
    // As tiras estão espalhadas pelos painéis digitais — pode haver mais de
    // um. A margem é UMA SÓ para a tela inteira, então quem manda é o nome
    // mais largo de todos: se cada painel tivesse a sua, dois eixos do tempo
    // começariam em x diferentes e o mesmo instante apareceria em dois
    // lugares. (Saía de `dados.digitais`, que deixou de existir com os
    // painéis — e sem isto os nomes voltavam todos cortados.)
    const tiras = (dados && dados.paineis || [])
      .flatMap((x) => x.tiras || []);
    if (!tiras.length) return;
    regua.font = FONTE_TIRA;
    const maior = Math.max(...tiras.map((t) => regua.measureText(t.nome).width));
    const teto = Math.max(MARGEM_BASE, Math.round((area.clientWidth || 900) * 0.42));
    MARGEM.esq = Math.min(Math.max(MARGEM_BASE, Math.ceil(maior) + 16), teto);
  }

  /** O servidor está rodando outra versão do OscLab: avisa e para.
   *
   * Parar é o certo. Desenhar com um pacote de outro formato dá uma tela
   * plausível e errada — campos faltando viram `undefined`, e `undefined` na
   * tela não parece defeito, parece dado.
   */
  function avisarDeVersao() {
    area.replaceChildren(criar("p", "vazio",
      "O servidor está rodando uma versão diferente da tela. Feche a janela "
      + "preta do osclab e rode o osclab.cmd de novo — os arquivos .py só são "
      + "lidos quando o programa sobe, e o navegador já pegou a tela nova."));
    avisarNoPe("versão do servidor diferente da versão da tela");
  }

  /** Quantas colunas o desenho tem DE VERDADE: pixels do dispositivo.
   *
   * Era a largura em pixels de CSS, e isso é outra coisa. O canvas é criado
   * com `largura × devicePixelRatio`, e o Chrome multiplica o
   * `devicePixelRatio` pelo zoom do navegador: a 80 % ele vale 0,8 numa tela
   * comum. Pedindo colunas em pixel de CSS, o servidor mandava ~1 ponto por
   * pixel de CSS e o canvas tinha só 0,8 pixel real para cada um — mais pontos
   * que pixels, e o traçador tinha que escolher. O resultado era um batimento
   * no envelope da onda que NÃO está no arquivo: medido no registro do
   * alimentador, o pico de cada ciclo varia 1 % de um ciclo para o seguinte, e
   * a tela mostrava muito mais que isso.
   *
   * Vale para os dois lados. Com zoom acima de 100 %, ou em tela HiDPI, o
   * `devicePixelRatio` passa de 1 e o erro se inverte: o canvas tem mais
   * pixels do que os pontos que pedimos, e o traço sai mais grosseiro do que a
   * tela conseguiria mostrar.
   */
  function colunasDeVerdade() {
    const dpr = window.devicePixelRatio || 1;
    return Math.max(300, Math.round(larguraDisponivel() * dpr));
  }

  function larguraDisponivel() {
    // Mede a área de desenho de verdade, e não a página: com a tabelinha aberta
    // o gráfico é mais estreito, e pedir colunas a mais faria o servidor reduzir
    // as amostras mais fino do que a tela consegue mostrar.
    ajustarMargem();
    const tela = area.querySelector(".tela");
    const largura = (tela && tela.clientWidth) || area.clientWidth || 900;
    return Math.max(largura - MARGEM.esq - MARGEM.dir, 120);
  }

  // --- montagem da página -------------------------------------------------

  //: Sobe a cada desenho e invalida os mapas de cor guardados em cada painel.
  //: Sem ele, trocar uma cor à mão não repintaria nada — o mapa velho
  //: continuaria valendo.
  let seloDoDesenho = 0;

  function desenharTudo() {
    if (!dados) return;
    seloDoDesenho += 1;

    if (!dados.paineis || dados.paineis.length === 0) {
      area.replaceChildren(criar("p", "vazio", "Este registro não tem canal analógico."));
      return;
    }

    ajustarMargem();
    // O nome de um painel que nunca foi renomeado vem da unidade, e a unidade
    // muda quando se troca de primário para secundário. Enquanto a marca
    // estiver de pé, o nome da tela segue o do servidor.
    for (const vindo of dados.paineis) {
      const meu = painelPorId(vindo.id);
      if (meu && meu.do_padrao) meu.nome = vindo.nome;
    }
    // Sinal que saiu da tela não pode continuar selecionado: o Delete seguinte
    // apagaria algo que o usuário não está mais vendo.
    selecionados = selecionados.filter((s) => {
      const painel = dados.paineis.find((x) => x.id === s.painel);
      if (!painel) return false;
      return s.tipo === "digital"
        ? (painel.tiras || []).some((t) => (t.id || t.indice) === s.chave)
        : (painel.sinais || []).some((x) => x.id === s.chave);
    });
    celulas = [];
    notasDoPu = [];
    notasDaJanela = [];
    linhasDoTempo = [];
    blocos = dados.paineis.map((painel, i) => {
      const ultimo = i === dados.paineis.length - 1;
      if (painel.tipo === "digital") return blocoDigitais(painel, ultimo);
      if (painel.tipo === "fasorial") return blocoFasorial(painel);
      if (painel.tipo === "harmonicos") return blocoHarmonicos(painel);
      if (painel.tipo === "triangulo") return blocoTriangulo(painel);
      if (painel.tipo === "impedancia") return blocoImpedancia(painel);
      if (painel.tipo === "complexo") return blocoComplexo(painel);
      if (painel.tipo === "alfa") return blocoAlfa(painel);
      if (painel.tipo === "diferencial") return blocoDiferencial(painel);
      return bloco(painel, ultimo);
    });
    // Escolher e arrastar valem no painel INTEIRO, e por isso são ligados
    // aqui, onde as seções existem — e não no cabeçalho, que é só uma parte
    // dele. As setinhas continuam: teclado e toque precisam delas, e um gesto
    // que só funciona com mouse não pode ser o único caminho.
    for (const b of blocos) {
      if (b._painel) ligarArrastoDoPainel(b, b._painel);
    }
    area.replaceChildren(...emLinhas(blocos), rodapeDosPaineis());

    //: Do que o rodapé dizia, sobra o que é AVISO: um sinal que ficou no lado
    //: errado porque o arquivo não declara a relação de TC/TP. A contagem de
    //: amostras na janela saiu (e continua nas tarjas de cada painel).
    avisarNoPe(semRelacao().replace(/^ · /, ""));

    mostrarLeitura();
    repintar();
    marcarLegenda();
    marcarPainelEscolhido();
  }

  /** Junta os pares de fasoriais numa linha só; o resto fica como está.
   *
   * Dois diagramas lado a lado é a leitura de um evento — pré-falta e falta —
   * e um deles sozinho ocuparia uma linha inteira para 324 pixels de círculo.
   * `blocos` continua sendo a lista achatada, na ordem dos painéis: é por ela
   * que `repintar` e `marcarLegenda` andam, e aninhar ali quebraria as duas.
   */
  function emLinhas(lista) {
    const saida = [];
    for (let i = 0; i < lista.length; i += 1) {
      const painel = lista[i]._painel;
      if (painel && temPar(painel.id) && lista[i + 1]) {
        const linha = criar("div", "par-fasorial");
        linha.append(lista[i], lista[i + 1]);
        saida.push(comMolduraDoPar(linha, lista[i], lista[i + 1]));
        i += 1;
        continue;
      }
      saida.push(lista[i]);
    }
    return saida;
  }

  /** Um par de fasoriais é UM quadro, com UMA moldura de cada lado.
   *
   * Cada painel traz a sua moldura de nascença (`comMolduras`), e num par
   * elas viravam quatro riscos curtos, cortados no vão entre os dois quadros
   * — uma régua partida no meio, bem no lugar onde ela existe para dizer que
   * o cursor é o MESMO nos dois diagramas.
   *
   * Então o par devolve as molduras dos filhos e fica com as suas, por fora
   * dos dois. Quem as pinta continua sendo o primeiro bloco: `repintarAgora`
   * anda por `blocos`, que é a lista achatada, e o quadro do par não está
   * nela.
   */
  function comMolduraDoPar(linha, esquerdo, direito) {
    for (const b of [esquerdo, direito]) {
      for (const m of (b._molduras || [])) m.caixa.remove();
      b._molduras = [];
    }
    const caixa = criar("div", "par-com-moldura");
    const topo = molduraDoPainel("acima");
    const rodape = molduraDoPainel("abaixo");
    //: A de cima FLUTUA. No fluxo ela só poderia nascer antes dos dois
    //: painéis — acima dos botões, porque o cabeçalho é de cada um, um em
    //: cada coluna —, e ali ela não é moldura de nada. Fora do fluxo, ela cai
    //: onde tem que cair: rente ao topo dos dois desenhos, medindo onde eles
    //: começam. O espaço dela é reservado no CSS (ver `.par-com-moldura`), e
    //: por isso nada se mexe quando ela aparece.
    topo.flutua = true;
    caixa.append(topo.caixa, linha, rodape.caixa);
    esquerdo._molduras = [topo, rodape];
    for (const m of esquerdo._molduras) cursorArrastavelNaMoldura(m);
    return caixa;
  }

  /** Os botões que criam um painel novo, no fim da lista.
   *
   * No fim, e não no topo: a tela se lê de cima para baixo como a sequência do
   * evento, e um botão no meio disso seria um degrau. Dois botões em vez de um
   * menu porque são só dois tipos — abrir menu para escolher entre duas coisas
   * é um clique a mais para não ganhar nada.
   */
  //: Os tipos de gráfico que se pode acrescentar, e o que cada um é.
  const TIPOS_DE_PAINEL = [
    ["analogico", "gráfico analógico",
     "Ondas no tempo: o que o relé gravou, amostra por amostra."],
    ["digital", "gráfico digital",
     "Tiras de digitais: trip, partida, recepção de teleproteção."],
    ["fasorial", "diagrama fasorial",
     "Módulo e ângulo no instante de um cursor, em pu — é onde se lê "
     + "defasagem e sequência."],
    ["triangulo", "triângulo de tensões",
     "As três tensões de fase saindo do neutro; as pontas formam um triângulo "
     + "cujos lados são as tensões de linha. A FORMA diz o tipo da falta e o "
     + "baricentro é V0 — sai de um vínculo corrente×tensão, em «editar "
     + "grupos»."],
    ["harmonicos", "harmônicos",
     "Barras por ordem, em % da fundamental, do sinal BRUTO: num ciclo de um "
     + "cursor ou no trecho entre os dois. É onde se vê o 2º harmônico de uma "
     + "energização de trafo e a saturação de um TC."],
    ["espectro", "espectro (dB)",
     "A mesma medida dos harmônicos, em LINHA por frequência e em dB da "
     + "fundamental: no trecho entre os cursores aparece o que cai entre as "
     + "ordens (inter-harmônicos), e o dB mostra de uma vez a 2ª de 15 % e a "
     + "11ª de 0,5 %."],
    ["complexo", "plano complexo",
     "O caminho que o fasor de cada sinal percorre, do começo do registro até "
     + "o cursor, no plano real × imaginário. Mostra o que o gráfico de tempo "
     + "esconde: o giro de ângulo, a travessia da falta, o desvio de "
     + "frequência."],
    ["impedancia", "plano de impedância",
     "A trajetória do laço no plano R × X ao longo da janela, com as zonas do "
     + "relé por cima. É onde se lê a que distância ficou a falta e em que "
     + "zona ela caiu — sai do mesmo vínculo corrente×tensão do triângulo."],
    ["diferencial", "diferencial percentual (87T)",
     "Iop × Irt do diferencial PERCENTUAL (com restrição) de transformador, fase por fase, com a "
     + "característica de dois slopes e o bloqueio por 2ª e 5ª harmônica. Os "
     + "ajustes vêm do arquivo quando o relé os grava, e se digitam quando "
     + "não; sem todos eles, o gráfico não é desenhado."],
    ["alfa", "plano alfa",
     "A razão k = I remoto / I local entre dois terminais, fase por fase, "
     + "com a coroa de restrição do 87L da SEL. Falta externa fica perto de "
     + "1∠180°; interna vira para perto de 0°. Precisa de duas trincas de "
     + "corrente no registro."],
  ];

  /** O botão que acrescenta um gráfico, no fim da lista.
   *
   * No fim, e não no topo: a tela se lê de cima para baixo como a sequência
   * do evento, e um botão no meio disso seria um degrau.
   *
   * UM botão com menu, e não um por tipo: eram três botões lado a lado para
   * uma decisão que se toma uma vez, e cada tipo novo alargava a fileira. O
   * menu também cabe a explicação de cada um, que num botão não cabia.
   */
  function rodapeDosPaineis() {
    const barra = criar("div", "novo-painel");
    const botao = criar("button", "medida");
    botao.type = "button";
    botao.setAttribute("aria-haspopup", "true");
    botao.setAttribute("aria-expanded", "false");
    botao.append(criar("span", null, "+ adicionar gráfico"),
                 criar("span", "seta-do-menu", "▾"));
    botao.title = "Acrescenta um gráfico vazio no fim da tela. Os sinais "
                + "entram pelo «+ sinal» dele.";
    const ancora = criar("span", "ancora-de-menu");
    ancora.id = "menu-novo-painel";
    botao.addEventListener("click", () => {
      menuSuspenso("menu-novo-painel", "acrescentar:", (caixa) => {
        for (const [tipo, rotulo, explicacao] of TIPOS_DE_PAINEL) {
          // O painel de harmônicos é do modo AVANÇADO, e por um motivo que
          // não é arbitrário: ele mede o que o filtro de 60 Hz apaga. No
          // tradicional a tela inteira fala do filtrado, e oferecer ali um
          // painel que só olha o bruto seria oferecer uma contradição.
          //
          // Aparece desabilitado, e não escondido: quem não sabe que ele
          // existe não vai procurar o modo que o revela, e a linha
          // desabilitada é justamente o que ensina os dois de uma vez.
          const soNoAvancado = (tipo === "harmonicos" || tipo === "espectro")
                            && visaoDeAnalise !== "avancado";
          const item = criar("button", "opcao",
                             soNoAvancado ? `${rotulo} (só no avançado)` : rotulo);
          item.type = "button";
          item.title = soNoAvancado
            ? explicacao + " Troque para «avançado» no cabeçalho: no modo "
              + "tradicional a tela mostra só o que sai do filtro de 60 Hz, e "
              + "é exatamente isso que este painel precisa NÃO olhar."
            : explicacao;
          if (soNoAvancado) {
            item.disabled = true;
            item.classList.add("desabilitada");
          } else {
            item.addEventListener("click", () => {
              menuAberto?.();
              criarPainel(tipo);
            });
          }
          caixa.append(item);
        }
      });
    });
    barra.append(botao, ancora);
    return barra;
  }

  /** Cria um painel vazio, com nome genérico.
   *
   * O nome é genérico de propósito: obrigar a batizar um gráfico antes de ver
   * o que tem dentro dele é pedir uma decisão na hora errada. Quem quiser
   * renomeia depois, clicando no título.
   */
  /** O laço com que um plano de impedância novo nasce.
   *
   * O que o classificador de falta achou neste registro, quando achou; `AN`
   * quando não. Não é palpite: é o veredito que já está escrito no selo do
   * cabeçalho, e abrir o plano em outro laço seria a tela discordando de si
   * mesma. Ver `analysis/falta.py`.
   */
  function lacoInicial() {
    const lido = (document.body.dataset.laco || "").trim().toUpperCase();
    return LACOS_DO_PLANO.some(([x]) => x === lido) ? lido : "AN";
  }

  function criarPainel(tipoPedido) {
    // O espectro é o MESMO painel de harmônicos para o servidor — a mesma
    // medida, da mesma janela. Muda só o desenho, e o desenho é da tela
    // (`desenho`), como o nome e a cor.
    const tipo = tipoPedido === "espectro" ? "harmonicos" : tipoPedido;
    const desenho = tipoPedido === "espectro" ? "espectro" : "barras";
    guardarParaDesfazer();
    const quantos = paineis.filter((x) => x.tipo === tipo).length + 1;
    const nome = tipo === "digital" ? `Gráfico digital ${quantos}`
               : tipo === "fasorial" ? `Fasores ${quantos}`
               : tipo === "harmonicos" && desenho === "espectro"
                 ? `Espectro ${paineis.filter((x) => x.desenho === "espectro").length + 1}`
               : tipo === "harmonicos" ? `Harmônicos ${paineis.filter(
                   (x) => x.tipo === "harmonicos" && x.desenho !== "espectro").length + 1}`
               // Sem esta linha o triângulo nascia chamado «Gráfico analógico
               // 1», porque caía no último caso do encadeamento. O nome do
               // vínculo entra por cima assim que ele é escolhido.
               : tipo === "triangulo" ? `Triângulo ${quantos}`
               // Idem: sem esta linha o plano nascia «Gráfico analógico 1».
               // O laço entra no nome quando o usuário o troca.
               : tipo === "impedancia" ? `Plano de impedância ${quantos}`
               : tipo === "complexo" ? `Plano complexo ${quantos}`
               : tipo === "alfa" ? `Plano alfa ${quantos}`
               : tipo === "diferencial" ? `Diferencial percentual ${quantos}`
               : `Gráfico analógico ${quantos}`;
    paineis.push({ id: `t${proximoId++}`, tipo, desenho,
                   // O plano de impedância nasce SEM nome e com a marca do
                   // padrão: quem o nomeia é o servidor, e o nome dele traz o
                   // par e o laço (`Impedância G1↔G2 · AN`). Assim ele
                   // acompanha a troca de laço sozinho, em vez de ficar
                   // «Plano de impedância 1» enquanto o desenho é de outro
                   // laço. Renomear à mão apaga a marca, como em todo painel.
                   nome: tipo === "impedancia" ? "" : nome,
                   // O plano alfa nasce com as três fases: é o 87L por
                   // fase, e o caso mais comum de olhar.
                   sinais: tipo === "alfa" || tipo === "diferencial"
                     ? ["A", "B", "C"] : [],
                   medida: "instantaneo",
                   do_padrao: tipo === "impedancia", cores: {},
                   // Só no fasorial: de qual cursor ele mostra o instante,
                   // qual sinal é o zero dos ângulos DELE, e a base do pu que
                   // o usuário digitou para cada unidade (`{"kV": 7.967}`).
                   cursor: 1, referencia: null, bases: {},
                   // Só no plano de impedância: qual dos seis laços está
                   // desenhado. Nasce no de terra da fase A porque é nele
                   // que cai a maioria das faltas de linha — e quando o
                   // registro traz veredito de falta, o laço vem de lá.
                   laco: lacoInicial(),
                   // Só no plano: o que for digitado na caixa de ajustes.
                   // Vazio quer dizer «tudo como o arquivo trouxe».
                   manuais: {},
                   // **Sem escala por padrão**: a pergunta que se faz num
                   // fasorial é de ÂNGULO, e com todas as setas do mesmo
                   // tamanho ela se responde de relance. O módulo está na
                   // tabela ao lado, em ampère e volt, o tempo todo.
                   escala: false,
                   // Só no plano complexo: a referência nasce FIXA (é o que
                   // mostra o desvio de frequência) e o desenho em pu.
                   fixa: true, unidade: "pu",
                   // Só no plano alfa: visto do local; a região sai do relé
                   // (ou do típico, quando o arquivo não traz) — o servidor diz.
                   vista: "local", r87: null, ang87: null,
                   // Só no diferencial: o digitado e os suspeitos aceitos.
                   ajustes87: {} });
    carregar();
  }

  function apagarPainel(id) {
    // A caixa de ajustes mora no `body`, não dentro do painel: tirar o
    // painel não a leva junto, e ela ficaria flutuando sobre nada.
    if (ajustesAbertos && ajustesAbertos.painel === id) fecharAjustes();
    guardarParaDesfazer();
    // Tirar um dos dois de um par desfaz o par: o que sobra volta a ocupar a
    // linha inteira, em vez de ficar numa metade com o outro lado vazio.
    if (temPar(id) || eDaDireita(id)) desfazerPar(id);
    paineis = paineis.filter((x) => x.id !== id);
    selecionados = selecionados.filter((x) => x.painel !== id);
    carregar();
  }

  /** Desfaz o par de que este painel participa, seja ele qual for. */
  function desfazerPar(id) {
    const i = paineis.findIndex((x) => x.id === id);
    if (i < 0) return;
    if (paineis[i].par) delete paineis[i].par;
    if (i > 0 && paineis[i - 1].par) delete paineis[i - 1].par;
  }

  /** Sobe ou desce um painel na lista. */
  function moverPainel(id, passo) {
    const i = paineis.findIndex((x) => x.id === id);
    const j = i + passo;
    if (i < 0 || j < 0 || j >= paineis.length) return;
    guardarParaDesfazer();
    // Mover para fora do par desfaz o par: a linha é dos dois que estão
    // lado a lado, e quem sai dela não leva a outra metade junto.
    desfazerPar(id);
    desfazerPar(paineis[j].id);
    const [x] = paineis.splice(i, 1);
    paineis.splice(j, 0, x);
    carregar();
  }

  function renomearPainel(id, nome) {
    const painel = painelPorId(id);
    if (!painel || painel.nome === nome) return;
    guardarParaDesfazer();
    painel.nome = nome;
    // A partir daqui o nome é do usuário: o servidor para de reescrevê-lo
    // quando a unidade muda.
    painel.do_padrao = false;
    // O nome é rótulo da tela: não muda número nenhum, então não precisa do
    // servidor. Redesenhar basta, e é instantâneo.
    dados.paineis.forEach((x) => { if (x.id === id) x.nome = nome; });
    desenharTudo();
  }

  /** Troca os sinais de um painel e recarrega. */
  function trocarSinais(id, ids) {
    const painel = painelPorId(id);
    if (!painel) return;
    // Fechar a janela sem ter mexido nas caixinhas não é ação nenhuma: gastar
    // um passo do Ctrl+Z com isso faria o desfazer parecer quebrado, porque o
    // primeiro toque não mudaria nada na tela.
    const mesmos = painel.sinais.length === ids.length
                && painel.sinais.every((x, i) => x === ids[i]);
    if (mesmos) return;
    guardarParaDesfazer();
    painel.sinais = ids;
    // Cor de sinal que saiu do gráfico não fica guardada: se ele voltar, volta
    // com a cor automática, que é o que alguém espera de um sinal novo.
    const ficam = new Set(ids);
    for (const chave of Object.keys(painel.cores || {})) {
      if (!ficam.has(chave)) delete painel.cores[chave];
    }
    // A escala vertical muda — e a LEITURA DO CURSOR também, porque ela é por
    // sinal: `carregar` traz a janela e as séries, mas o pacote do cursor é
    // outro pedido. Sem esta linha o sinal recém-acrescentado entrava sem
    // módulo nem ângulo, e o desenho só aparecia quando o usuário mexia o
    // cursor — que era o pedido seguinte, por acaso.
    carregar().then(() => {
      if (cursores[0] !== null || cursores[1] !== null) lerCursores();
    });
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
    for (const painel of dados.paineis) {
      if (painel.tipo === "fasorial" || painel.tipo === "triangulo") continue;
      // nem o fasorial nem o triângulo têm lado desenhado
      for (const sinal of (painel.sinais || [])) {
        if (sinal.nome && sinal.lado !== lado) teimosos.push(sinal.nome);
      }
    }
    if (!teimosos.length) return "";
    return ` · sem relação de TC/TP no arquivo, ficaram como estão: ${teimosos.join(", ")}`;
  }

  //: Altura de cada tira digital, em pixels de CSS. Estreita de propósito: um
  //: evento real mexe em algumas dezenas de digitais, e elas precisam caber na
  //: mesma tela que as ondas.
  //: A altura de uma linha de tira digital. 19 e não 15: a barra engrossou
  //: (ver `FINA`/`GROSSA`) e o nome subiu para 12 px — com 15 a linha ficava
  //: sem respiro entre uma tira e a vizinha.
  const TIRA = 19;

  //: As duas espessuras da linha de um digital, em pixels de CSS: 0 é um fio,
  //: 1 é uma barra. A razão entre elas é o que se lê de longe — sete para um
  //: se distingue numa tela cheia de tiras sem precisar de cor diferente.
  //: A espessura do 0 e a do 1. PARES, e não 1 e 7, e o motivo é de
  //: rasterização: a tira é centrada num `y` inteiro, então uma altura ímpar
  //: cai em meio pixel dos dois lados — uma linha de 1 px desenhada de 7,5 a
  //: 8,5 vira duas meias-linhas borradas, e a de 7 faz o mesmo. Com altura
  //: par a borda cai em pixel inteiro e o traço sai nítido.
  //:
  //: É também metade da conta do degrau que aparecia na troca de estado: a
  //: outra metade é o `x` das transições, arredondado em `pintarDigitais`.
  const FINA = 2;
  const GROSSA = 10;

  /** Um painel de tiras digitais.
   *
   * Nasce como um `.grafico` igual aos outros de propósito — assim os gestos
   * (roda, arrasto, seleção) e os cursores funcionam nele sem uma linha a
   * mais: `areaDoEvento` procura o `.tela` mais próximo e acha este também.
   */
  //: As cores que a engrenagem das digitais oferece. A primeira é o padrão.
  //:
  //: Não é a `PALETA` dos traços: lá o que importa é nunca repetir cor DENTRO
  //: de um gráfico, e aqui todas as tiras são da mesma cor de propósito — o
  //: que elas têm a dizer é estado, não identidade. Então a lista é de tons
  //: que funcionam como massa: nada de oliva nem de cinza, que somem num
  //: bloco de quarenta tiras acesas.
  const CORES_DAS_TIRAS = [
    // O VERMELHO entrou a pedido dele (19/10/2026) e é o `--ruim`, o mesmo
    // tom do trip no resto do programa: uma coisa, uma cor. A fase C, que
    // também é vermelha, fica de fora — duas vermelhas na mesma paleta são
    // duas escolhas que ninguém distingue depois de pintar.
    "--digital", "--destaque", "--fase-a", "--fase-n", "--atencao", "--ruim",
    "--traco-1", "--traco-2", "--calculado-1", "--calculado-2", "--tinta",
  ];

  /* === O PINCEL e as CATEGORIAS ==========================================
   *
   * O pincel pinta UMA tira de cada vez, com a cor que está na bolinha. A cor
   * mora no mesmo lugar da cor de um traço analógico (`painel.cores`), e pelo
   * mesmo motivo: é rótulo da tela, não muda número nenhum, não vai ao
   * servidor e entra no Ctrl+Z junto com o resto do arranjo.
   *
   * As duas opções por categoria dependem do dicionário, e por isso nascem
   * apagadas enquanto não houver base de dados — avisa, nunca bloqueia: a
   * chave apagada responde ao clique dizendo o que falta.
   */
  //: O pincel mora DENTRO do painel de digitais, ao lado da engrenagem — é
  //: lá que ele age, e uma ferramenta que só vale para um painel no cabeçalho
  //: da tela inteira promete o que não cumpre. Escolha dele, 19/10/2026.
  //:
  //: `pintando` é por painel: dois painéis de digitais na tela podem estar um
  //: em modo de pintar e o outro não. A COR é uma só — é a tinta carregada no
  //: pincel, e trocá-la em cada painel seria guardar a mesma coisa duas vezes.
  const pincel = { pintando: {}, cor: "--atencao" };
  const pintando = (id) => !!pincel.pintando[id];

  //: `NOME DO SINAL → categoria`. Chega uma vez, quando alguma coisa precisa
  //: dela; sem base de dados vem vazio.
  let dicionario = null;
  let pedindoDicionario = null;

  const CATEGORIAS_EM_ORDEM = ["trip", "partida", "bloqueio", "estado", "io",
                               "auxiliar", ""];
  //: Uma cor por categoria — as mesmas dos tipinhos da tela da base, para a
  //: mesma coisa ter a mesma cor nos dois lugares.
  const COR_DA_CATEGORIA = {
    trip: "--ruim", partida: "--atencao", bloqueio: "--calculado-1",
    estado: "--digital", io: "--bom", auxiliar: "--suave", "": "--suave",
  };

  function carregarDicionario() {
    if (pedindoDicionario) return pedindoDicionario;
    pedindoDicionario = fetch("/api/dicionario/" + encodeURIComponent(sha))
      .then((r) => r.json())
      .then((d) => {
        dicionario = new Map();
        if (d && d.tem) {
          for (const v of (d.verbetes || [])) {
            dicionario.set(String(v.sinal).toUpperCase(), v.categoria || "");
          }
        }
        desenharTudo();
      })
      .catch(() => { dicionario = new Map(); });
    return pedindoDicionario;
  }

  const categoriaDe = (nome) =>
    (dicionario && dicionario.get(String(nome || "").toUpperCase())) || "";
  const temDicionario = () => !!(dicionario && dicionario.size);

  /** A cor de UMA tira, na ordem em que as regras mandam.
   *
   * O pincel vence a categoria, e a categoria vence a cor do painel: o que a
   * mão fez à mão é o mais específico que existe, e não pode ser desfeito por
   * uma chave ligada depois sem ninguém entender por quê.
   */
  function corDaTira(painel, tira) {
    const meu = painelPorId(painel.id) || {};
    const minha = (meu.cores || {})[tira.id || String(tira.indice)];
    if (minha) return token(minha);
    if (meu.por_categoria && temDicionario())
      return token(COR_DA_CATEGORIA[categoriaDe(tira.nome)] || "--digital");
    return token(meu.cor_tiras || "--digital");
  }

  /** A paleta do PINCEL: a mesma das tiras, pendurada no círculo. */
  function abrirPaletaDoPincel(ancora, idDoPainel) {
    document.querySelectorAll(".paleta-flutuante").forEach((x) => x.remove());
    const paleta = criar("div", "paleta-flutuante");
    const fechar = () => {
      paleta.remove();
      document.removeEventListener("pointerdown", fora, true);
      window.removeEventListener("resize", fechar);
    };
    const fora = (e) => {
      if (!paleta.contains(e.target) && !ancora.contains(e.target)) fechar();
    };
    for (const cor of CORES_DAS_TIRAS) {
      const opcao = criar("button", "cor-opcao");
      opcao.type = "button";
      opcao.style.background = token(cor);
      opcao.title = cor === pincel.cor ? "cor atual" : "pintar com esta";
      if (cor === pincel.cor) opcao.classList.add("escolhida");
      opcao.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        fechar();
        pincel.cor = cor;
        // Escolher a cor já LIGA o pincel: quem abriu a paleta ia pintar.
        if (idDoPainel) pincel.pintando[idDoPainel] = true;
        desenharTudo();
      });
      paleta.append(opcao);
    }
    document.body.append(paleta);
    const r = ancora.getBoundingClientRect();
    const caixa = paleta.getBoundingClientRect();
    paleta.style.left = Math.round(Math.min(Math.max(6, r.left - 4),
      window.innerWidth - caixa.width - 6)) + "px";
    paleta.style.top = Math.round(r.bottom + 4) + "px";
    paleta.firstChild.focus();
    document.addEventListener("pointerdown", fora, true);
    window.addEventListener("resize", fechar);
  }

  /** Pinta — ou despinta — a tira em que se clicou. */
  /** O CONTROLE do pincel: uma peça só, com o pincel e o círculo da cor.
   *
   * Dois botões soltos lado a lado se leriam como duas ferramentas; com a
   * moldura em volta lê-se como uma ferramenta com uma cor carregada. O
   * pincel entra e sai do modo; o círculo abre as cores. Desenho dele.
   */
  function controleDoPincel(painel) {
    const caixa = criar("span", "controle-do-pincel"
                        + (pintando(painel.id) ? " pintando" : ""));
    const lado = criar("button", "lado-pincel");
    lado.type = "button";
    lado.title = pintando(painel.id)
      ? "Sair do modo de pintar."
      : "Pintar sinais digitais um a um, com a cor do círculo ao lado.";
    const ic = criar("span", "ic-do-pincel");
    lado.append(ic, criar("span", null, pintando(painel.id) ? "pintando" : "pincel"));
    lado.addEventListener("click", () => {
      pincel.pintando[painel.id] = !pintando(painel.id);
      desenharTudo();
    });

    const botaoCor = criar("button", "lado-cor");
    botaoCor.type = "button";
    botaoCor.title = "A cor com que o pincel pinta.";
    const bolota = criar("span", "bolota");
    bolota.style.background = token(pincel.cor);
    botaoCor.append(bolota);
    botaoCor.addEventListener("click", (ev) => {
      ev.stopPropagation();
      abrirPaletaDoPincel(botaoCor, painel.id);
    });

    caixa.append(lado, botaoCor);
    return caixa;
  }

  function pincelarTira(painel, tira) {
    const meu = painelPorId(painel.id);
    if (!meu) return;
    const qual = tira.id || String(tira.indice);
    const agora = (meu.cores || {})[qual] || "";
    // A mesma cor de novo TIRA a pintura: o pincel é o que pinta e o que
    // apaga, e assim ninguém precisa procurar uma borracha.
    escolherCor(painel.id, qual, agora === pincel.cor ? "" : pincel.cor);
  }

  function escolherCorDasTiras(id, cor) {
    const painel = painelPorId(id);
    if (!painel) return;
    guardarParaDesfazer();
    // O padrão volta a ser padrão: guardar `--digital` explicitamente
    // prenderia o painel ao tom de hoje se ele mudar no tema ou na versão.
    painel.cor_tiras = cor === "--digital" ? null : cor;
    desenharTudo();
  }

  /** A paleta das tiras, pendurada na engrenagem. Mesmo desenho da paleta da
   *  bolinha de um sinal — é a mesma ação, noutro objeto. */
  function abrirPaletaDasTiras(painel, ancora) {
    document.querySelectorAll(".paleta-flutuante").forEach((x) => x.remove());
    const paleta = criar("div", "paleta-flutuante");
    const valendo = (painelPorId(painel.id) || {}).cor_tiras || "--digital";

    const fechar = () => {
      paleta.remove();
      document.removeEventListener("pointerdown", foraDaPaleta, true);
      window.removeEventListener("scroll", fechar, true);
      window.removeEventListener("resize", fechar);
    };
    const foraDaPaleta = (e) => {
      if (!paleta.contains(e.target) && !ancora.contains(e.target)) fechar();
    };

    for (const cor of CORES_DAS_TIRAS) {
      const opcao = criar("button", "cor-opcao");
      opcao.type = "button";
      opcao.style.background = token(cor);
      opcao.title = cor === valendo
        ? "cor atual" : (cor === "--digital" ? "voltar ao padrão" : "usar esta cor");
      if (cor === valendo) opcao.classList.add("escolhida");
      opcao.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        fechar();
        escolherCorDasTiras(painel.id, cor);
      });
      paleta.append(opcao);
    }
    paleta.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.stopPropagation(); fechar(); }
    });

    document.body.append(paleta);
    const r = ancora.getBoundingClientRect();
    const caixa = paleta.getBoundingClientRect();
    const margem = 6;
    const x = Math.min(Math.max(margem, r.left - 4),
                       window.innerWidth - caixa.width - margem);
    const abaixo = r.bottom + 4;
    const y = abaixo + caixa.height + margem <= window.innerHeight
      ? abaixo
      : Math.max(margem, r.top - caixa.height - 4);
    paleta.style.left = `${Math.round(x)}px`;
    paleta.style.top = `${Math.round(y)}px`;
    paleta.firstChild.focus();

    document.addEventListener("pointerdown", foraDaPaleta, true);
    window.addEventListener("scroll", fechar, true);
    window.addEventListener("resize", fechar);
  }

  /** «cor das tiras», dentro da engrenagem do painel de digitais. */
  function botaoDaCorDasTiras(painel) {
    const b = criar("button", "medida");
    b.type = "button";
    const bolinha = criar("span", "bolinha-fixa");
    bolinha.style.background =
      token((painelPorId(painel.id) || {}).cor_tiras || "--digital");
    b.append(bolinha, criar("span", null, "cor das tiras"));
    b.title = "A cor das tiras DESTE painel. Todas as tiras têm a mesma cor de "
            + "propósito: o que elas dizem é estado, não identidade.";
    b.addEventListener("click", () => abrirPaletaDasTiras(painel, b));
    return b;
  }

  /** Uma das duas opções por CATEGORIA, na engrenagem das digitais.
   *
   * Nasce apagada sem dicionário e continua clicável: o clique diz o que
   * falta. Chave que não responde é a tela discutindo com quem clicou.
   */
  function chaveDeCategoria(painel, qual) {
    const meu = painelPorId(painel.id) || {};
    const ligada = qual === "pintar" ? !!meu.por_categoria : !!meu.agrupar_categoria;
    const b = criar("button", "medida" + (ligada ? " escolhido" : ""));
    b.type = "button";
    if (qual === "pintar") {
      const bolinha = criar("span", "bolinha-fixa");
      bolinha.style.background = token("--ruim");
      b.append(bolinha);
    }
    b.append(criar("span", null, "pintar por categoria"));
    const temDic = temDicionario();
    if (!temDic) b.classList.add("sem-dicionario");
    b.title = temDic
      ? (qual === "pintar"
         ? "Cada sinal com a cor da categoria que ele tem no dicionário."
         : "Põe os sinais na ordem das categorias: trip, partida, bloqueio, estado, entrada e saída, auxiliar.")
      : "Precisa de um dicionário com os sinais deste relé — clique para saber por quê.";
    b.addEventListener("click", () => {
      if (!temDicionario()) {
        avisarNoPe("Sem dicionário não há categoria: cadastre os sinais deste "
                 + "relé na base de dados e esta opção acende.");
        return;
      }
      if (qual === "pintar") {
        guardarParaDesfazer();
        const meuAgora = painelPorId(painel.id);
        meuAgora.por_categoria = !meuAgora.por_categoria;
        desenharTudo();
        return;
      }
      agruparPorCategoria(painel);
    });
    return b;
  }

  /** As duas opções de AGRUPAR, uma escolha só com duas faces.
   *
   * «Sem agrupamento» desfaz voltando à ordem em que os sinais entraram —
   * que é a do arranjo antes do agrupamento, guardada no painel.
   */
  function chaveDeAgrupar(painel, qual) {
    const meu = painelPorId(painel.id) || {};
    const agrupado = !!meu.agrupar_categoria;
    const ligada = qual === "categoria" ? agrupado : !agrupado;
    const b = criar("button", "medida" + (ligada ? " escolhido" : ""));
    b.type = "button";
    b.append(criar("span", null,
      qual === "categoria" ? "agrupar por categoria" : "sem agrupamento"));
    const temDic = temDicionario();
    if (qual === "categoria" && !temDic) b.classList.add("sem-dicionario");
    b.title = qual === "categoria"
      ? (temDic
         ? "Põe os sinais na ordem das categorias: trip, partida, bloqueio, estado, entrada e saída, auxiliar."
         : "Precisa de um dicionário com os sinais deste relé — clique para saber por quê.")
      : "Na ordem em que os sinais entraram no gráfico.";
    b.addEventListener("click", () => {
      if (qual === "categoria") {
        if (!temDicionario()) {
          avisarNoPe("Sem dicionário não há categoria: cadastre os sinais deste "
                   + "relé na base de dados e esta opção acende.");
          return;
        }
        agruparPorCategoria(painel);
        return;
      }
      desagrupar(painel);
    });
    return b;
  }

  /** Desfaz o agrupamento, devolvendo a ordem de antes. */
  function desagrupar(painel) {
    const meu = painelPorId(painel.id);
    if (!meu || !meu.agrupar_categoria) return;
    const antes = meu.ordem_antes || meu.sinais.slice();
    meu.agrupar_categoria = false;
    meu.ordem_antes = null;
    trocarSinais(painel.id, antes);
  }

  /** Põe as tiras na ordem das categorias, mantendo a ordem de dentro.
   *
   * Reordena os SINAIS do painel e recarrega, porque é o servidor que monta
   * as tiras na ordem em que os sinais chegam — a mesma estrada de quando se
   * acrescenta um sinal novo.
   */
  function agruparPorCategoria(painel) {
    const meu = painelPorId(painel.id);
    // As TIRAS (com o nome de cada sinal) vêm do painel desenhado, que é o
    // que o servidor mandou; os SINAIS, do arranjo da tela. São dois objetos
    // diferentes com o mesmo id, e confundi-los deixa a lista vazia.
    if (!meu || !painel.tiras) return;
    const peso = (indice) => {
      const tira = painel.tiras.find((t) => String(t.indice) === String(indice));
      const i = CATEGORIAS_EM_ORDEM.indexOf(categoriaDe(tira && tira.nome));
      return i < 0 ? CATEGORIAS_EM_ORDEM.length : i;
    };
    const antes = meu.sinais.slice();
    const ordenados = antes
      .map((x, i) => [x, i])
      .sort((a, b) => (peso(a[0]) - peso(b[0])) || (a[1] - b[1]))
      .map(([x]) => x);
    // A ordem de ANTES fica guardada: «sem agrupamento» a devolve, e sem ela
    // desagrupar seria outra ordem, não a de volta.
    if (!meu.agrupar_categoria) meu.ordem_antes = antes;
    meu.agrupar_categoria = true;
    trocarSinais(painel.id, ordenados);
  }

  function blocoDigitais(painel, ultimo) {
    const el = criar("section", "grafico digitais");
    const quantos = painel.tiras.length;

    const semPlaca = dados.digitais_sem_placa || 0;
    const parados = (dados.digitais_disponiveis || []).length
                  - (dados.digitais_mudaram || 0) - semPlaca;
    const busca = criar("button", "medida", "+ sinal");
    busca.title = `${dados.digitais_mudaram} digitais mudaram durante o `
                + `registro; ${parados} ficaram parados.`
                + (semPlaca ? ` ${semPlaca} o relé grava sem ter a placa (ficam de fora).` : "")
                + " Clique para procurar qualquer um pelo nome e trazê-lo para cá.";
    busca.addEventListener("click", () => abrirBusca(painel));

    el.append(cabecalhoDoPainel(
      painel,
      [busca, controleDoPincel(painel), ...engrenagemDoPainel(painel, () => [
        "Agrupar",
        chaveDeAgrupar(painel, "nenhum"),
        chaveDeAgrupar(painel, "categoria"),
        "Cor",
        botaoDaCorDasTiras(painel),
        chaveDeCategoria(painel, "pintar"),
      ])],
      `${quantos} ${quantos === 1 ? "sinal" : "sinais"}`));

    const corpo = criar("div", "grafico-corpo");
    const caixa = criar("div", "tela");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    // A segunda coluna existe vazia para as tiras ficarem alinhadas com as
    // ondas quando a tabelinha dos cursores está aberta.
    corpo.append(caixa, criar("div", "sem-tabela"));
    el.append(corpo);

    if (!quantos) {
      el.append(criar("p", "vazio",
        "Nenhum digital neste gráfico. Use o «+ sinal» para trazer os que "
        + "você quer ver aqui."));
    }

    canvas.addEventListener("pointermove", (evento) => {
      const caixaCanvas = canvas.getBoundingClientRect();
      const k = Math.floor((evento.clientY - caixaCanvas.top - MARGEM.topo) / TIRA);
      const tira = painel.tiras[k];
      const dica = tira ? tira.nome : "";
      if (canvas.title !== dica) canvas.title = dica;
      // Sobre o NOME, o cursor vira o de clicar: ali não se arrasta nem se
      // amplia — escolhe-se a tira, como na legenda das ondas.
      if (pintando(painel.id)) { canvas.style.cursor = "crosshair"; return; }
      const noNome = tira && (evento.clientX - caixaCanvas.left) < MARGEM.esq;
      canvas.style.cursor = noNome ? "pointer" : "";
    });

    // O nome da tira é o alvo certeiro: as tiras têm 15 px de altura, e acertar
    // a certa no meio de quarenta é mira. O nome está sempre no mesmo lugar.
    /* O PINCEL pinta no `pointerdown` do próprio canvas, e não no `click`.
     *
     * Medido em 19/10/2026: sobre o DESENHO o `click` nunca chega ao canvas —
     * a área captura o ponteiro no `pointerdown` e o `click` que vem depois
     * tem como alvo a área, não o canvas. Só o clique sobre o NOME chegava
     * aqui. No `pointerdown`, o canvas é o alvo e roda primeiro; o
     * `stopPropagation` impede a área de começar um arrasto no mesmo gesto.
     */
    canvas.addEventListener("pointerdown", (evento) => {
      if (!pintando(painel.id)) return;
      const caixaCanvas = canvas.getBoundingClientRect();
      const qual = digitalPerto(painel, evento.clientY - caixaCanvas.top);
      if (!qual) return;
      evento.preventDefault();
      evento.stopPropagation();
      pincelarTira(painel, { indice: qual.chave, nome: qual.nome });
    });

    canvas.addEventListener("click", (evento) => {
      const caixaCanvas = canvas.getBoundingClientRect();
      // Com o pincel, quem pinta é o `pointerdown` logo acima. Aqui só se
      // sai do caminho, senão o mesmo gesto pintaria duas vezes — e a
      // segunda apagaria a primeira.
      if (pintando(painel.id)) return;
      if (evento.clientX - caixaCanvas.left >= MARGEM.esq) return;  // o desenho
      const achado = digitalPerto(painel, evento.clientY - caixaCanvas.top);
      if (!achado) return;
      // Sem isto, o clique sobe até o `document` e a regra de "clicou fora,
      // limpa a seleção" desfaria o que acabou de ser feito.
      evento.stopPropagation();
      alternarSelecao(achado, evento.ctrlKey || evento.metaKey);
    });

    el._canvas = canvas;
    el._painel = painel;
    el._ultimo = ultimo;
    return el;
  }

  /** O cabeçalho de um painel: nome, controles de arranjo e o que mais vier.
   *
   * O mesmo nos dois tipos de painel, e por isso está num lugar só: um
   * cabeçalho que muda de forma conforme o conteúdo faria o usuário procurar
   * o botão de novo a cada gráfico.
   */
  function cabecalhoDoPainel(painel, botoes, contagem, naDireita = []) {
    const titulo = criar("h2", "grafico-titulo");

    // O nome é botão: clicar abre a edição. Não há lápis nem menu — o alvo é
    // o próprio texto, que é onde a mão vai.
    const nome = criar("button", "nome-painel", painel.nome);
    nome.title = "clique para renomear este gráfico";
    nome.addEventListener("click", () => editarNome(nome, painel));
    titulo.append(nome);

    if (contagem) titulo.append(criar("span", "contagem-painel", contagem));
    for (const b of botoes) titulo.append(b);

    const arranjo = criar("span", "arranjo");
    // Antes do ▲▼×: o que CRIA vem antes do que move e do que tira.
    for (const b of naDireita) arranjo.append(b);
    const i = paineis.findIndex((x) => x.id === painel.id);
    for (const [rotulo, passo, dica] of [["▲", -1, "subir este gráfico"],
                                         ["▼", 1, "descer este gráfico"]]) {
      const b = criar("button", "mexer", rotulo);
      b.title = dica;
      b.disabled = i + passo < 0 || i + passo >= paineis.length;
      b.addEventListener("click", () => moverPainel(painel.id, passo));
      arranjo.append(b);
    }
    const fechar = criar("button", "mexer fechar-painel", "×");
    fechar.title = "tirar este gráfico da tela (Ctrl+Z desfaz)";
    fechar.addEventListener("click", () => apagarPainel(painel.id));
    arranjo.append(fechar);
    titulo.append(arranjo);
    return titulo;
  }

  // --- arrastar para reordenar os gráficos ----------------------------------

  //: Quantos pixels a mão precisa andar para o gesto virar arrasto. Abaixo
  //: disso é clique — e o cabeçalho tem cliques de verdade dentro dele (o
  //: nome, que renomeia).
  const LIMIAR_DO_ARRASTO = 5;

  //: Dentro desta fração CENTRAL de um diagrama fasorial, soltar outro
  //: fasorial PAREIA os dois em vez de reordenar. Nas bordas continua valendo
  //: a inserção — senão não haveria como pôr um gráfico entre dois fasoriais.
  const ALVO_DO_PAR = 0.5;

  //: O arrasto em curso, ou `null`. Mora aqui porque o `pointermove` e o
  //: `pointerup` são do documento: o ponteiro sai de cima do cabeçalho na
  //: primeira dezena de pixels, e ouvintes presos ao elemento perderiam o
  //: gesto justamente quando ele começa.
  let arrastoDePainel = null;

  //: O painel escolhido para ser movido, ou `null`. **Escolher vem antes de
  //: arrastar**: o cabeçalho tem o nome, os botões e a rolagem da página
  //: passando por ele, e um arrasto que começasse no primeiro movimento
  //: embaralharia a tela a cada gesto que encostasse ali.
  let painelEscolhido = null;

  //: A que distância da borda da janela o arrasto começa a rolar a página, e
  //: quanto ele rola por quadro. Sem isto, mover um gráfico para o fim de uma
  //: tela com dez painéis exigiria soltar, rolar e pegar de novo.
  const BORDA_DE_ROLAGEM = 90;
  const PASSO_DE_ROLAGEM = 14;

  //: Onde um clique NÃO escolhe o gráfico: é conteúdo, e já tem dono. O
  //: desenho anda pela oscilografia, a legenda e a tabelinha escolhem sinal,
  //: os botões fazem o que dizem. Todo o resto do painel — a moldura, o vão
  //: ao lado do título, o rodapé, o aviso de diagrama vazio — é pega.
  const DENTRO_DO_CONTEUDO =
    "button, input, select, a, canvas, .tela, .tela-fasorial, .tela-complexo, "
    + ".tela-alfa, .tela-diferencial, .faltam-ajustes, .mini, "
    + ".legenda, .arranjo, dialog";

  /** Liga o escolher-e-arrastar num painel inteiro.
   *
   * O painel inteiro, e não só o cabeçalho: procurar a faixa exata que
   * responde ao clique é trabalho que a tela não devia dar. O que fica de
   * fora é o CONTEÚDO — ver `DENTRO_DO_CONTEUDO` —, e fica porque ali o mesmo
   * gesto já significa outra coisa.
   */
  function ligarArrastoDoPainel(secao, painel) {
    secao.classList.add("pega-de-arrasto");
    secao.addEventListener("pointerdown", (evento) => {
      if (evento.button !== 0) return;
      // Os controles do cabeçalho continuam sendo controles — MENOS o nome,
      // que é a pega mais natural que existe. Ele continua renomeando no
      // clique: o arrasto só começa depois de a mão andar, e aí o clique que
      // viria no fim é engolido (ver `terminarArrasto`). Sem isto, segurar no
      // título abria o campo de renomear em vez de mover o gráfico — e o
      // título é o primeiro lugar em que a mão vai.
      // O nome é a exceção: ele é botão (renomeia no clique) e mesmo assim
      // arrasta, porque é o lugar mais natural para pegar um painel.
      if (evento.target.closest(DENTRO_DO_CONTEUDO)
          && !evento.target.closest(".nome-painel")) return;
      const id = painel.id;

      // Primeiro clique ESCOLHE o gráfico; a partir daí o cabeçalho dele é
      // pega. O nome continua renomeando no clique, escolhido ou não.
      if (painelEscolhido !== id) {
        if (!evento.target.closest(".nome-painel")) escolherPainel(id);
        return;
      }
      const inicio = { x: evento.clientX, y: evento.clientY };

      const mover = (e) => {
        if (!arrastoDePainel) {
          if (Math.hypot(e.clientX - inicio.x, e.clientY - inicio.y)
              < LIMIAR_DO_ARRASTO) return;
          comecarArrasto(id);
        }
        mirarArrasto(e);
      };
      const soltar = () => {
        document.removeEventListener("pointermove", mover, true);
        document.removeEventListener("pointerup", soltar, true);
        document.removeEventListener("pointercancel", cancelar, true);
        terminarArrasto(true);
      };
      const cancelar = () => {
        document.removeEventListener("pointermove", mover, true);
        document.removeEventListener("pointerup", soltar, true);
        document.removeEventListener("pointercancel", cancelar, true);
        terminarArrasto(false);
      };
      document.addEventListener("pointermove", mover, true);
      document.addEventListener("pointerup", soltar, true);
      document.addEventListener("pointercancel", cancelar, true);
    });
  }

  /** Escolhe (ou desescolhe) o gráfico que o cabeçalho vai arrastar. */
  function escolherPainel(id) {
    painelEscolhido = painelEscolhido === id ? null : id;
    marcarPainelEscolhido();
  }

  function marcarPainelEscolhido() {
    for (const b of blocos) {
      if (!b._painel) continue;
      b.classList.toggle("painel-escolhido", b._painel.id === painelEscolhido);
    }
  }

  function comecarArrasto(id) {
    arrastoDePainel = { id, destino: null, modo: null, y: 0 };
    area.classList.add("arrastando-painel");
    rolarComOArrasto();
    const bloco = blocos.find((b) => b._painel && b._painel.id === id);
    if (bloco) bloco.classList.add("em-arrasto");
    // A marca de onde o painel vai cair. Uma linha, e não um buraco do
    // tamanho do painel: o buraco empurraria o resto da tela a cada
    // movimento do mouse, e o usuário perderia a referência de onde estava.
    arrastoDePainel.marca = criar("div", "marca-de-solta");
  }

  /** Rola a página enquanto o arrasto está perto da borda da janela.
   *
   * Por quadro, e não por evento de mouse: parado junto da borda o ponteiro
   * não gera evento nenhum, e a rolagem pararia justamente onde ela precisa
   * continuar.
   */
  function rolarComOArrasto() {
    if (!arrastoDePainel) return;
    const y = arrastoDePainel.y;
    const altura = window.innerHeight;
    let passo = 0;
    if (y > 0 && y < BORDA_DE_ROLAGEM) {
      passo = -PASSO_DE_ROLAGEM * (1 - y / BORDA_DE_ROLAGEM);
    } else if (y > altura - BORDA_DE_ROLAGEM) {
      passo = PASSO_DE_ROLAGEM
            * (1 - (altura - y) / BORDA_DE_ROLAGEM);
    }
    if (passo) window.scrollBy(0, passo);
    requestAnimationFrame(rolarComOArrasto);
  }

  /** Decide onde o painel cai, e mostra isso na tela. */
  function mirarArrasto(evento) {
    const arrasto = arrastoDePainel;
    if (!arrasto) return;
    arrasto.y = evento.clientY;
    const sob = document.elementFromPoint(evento.clientX, evento.clientY);
    const alvo = sob && sob.closest(".grafico");
    limparMiraDoArrasto();

    // Soltar no MEIO de um fasorial pareia os dois, lado a lado. É o gesto
    // que o botão «+ diagrama ao lado» faz com um clique — e aqui ele serve
    // para parear dois diagramas que já existem.
    if (alvo && alvo._painel && podeParear(arrasto.id, alvo._painel.id)
        && noMiolo(alvo, evento)) {
      arrasto.destino = alvo._painel.id;
      arrasto.modo = "parear";
      alvo.classList.add("alvo-de-par");
      return;
    }

    const lugar = lugarDeInsercao(evento);
    if (!lugar) { arrasto.destino = null; arrasto.modo = null; return; }
    arrasto.destino = lugar.id;
    arrasto.modo = lugar.antes ? "antes" : "depois";
    // A marca é POSICIONADA, e não inserida na lista: como item da grade ela
    // criava uma faixa própria entre os dois gráficos, o que empurrava a
    // tela e deixava a linha acima do meio do vão. Aqui ela não ocupa
    // espaço nenhum — e cai exatamente no centro do vão.
    arrasto.marca.style.top =
      `${meioDoVao(lugar.linha, lugar.antes) - area.getBoundingClientRect().top}px`;
    if (arrasto.marca.parentElement !== area) area.append(arrasto.marca);
  }

  const noMiolo = (elemento, evento) => {
    const r = elemento.getBoundingClientRect();
    const borda = r.width * (1 - ALVO_DO_PAR) / 2;
    return evento.clientX > r.left + borda && evento.clientX < r.right - borda;
  };

  //: Os dois tipos de DIAGRAMA: fasorial e triângulo de tensões. Os dois têm
  //: o mesmo corpo (`corpo-fasorial`), o mesmo quadro quadrado de 324 px e a
  //: mesma tabela ao lado — e são as duas leituras angulares do mesmo
  //: instante. Por isso formam par entre si, inclusive um de cada tipo:
  //: «o triângulo da falta ao lado dos fasores da falta» é a comparação que
  //: ele pediu, e ela só existe se os dois couberem na mesma linha.
  const DIAGRAMAS_QUE_PAREIAM = new Set(["fasorial", "triangulo"]);

  /** Pode parear? Só dois diagramas, e nenhum deles já num par. */
  function podeParear(idA, idB) {
    if (idA === idB) return false;
    const a = painelPorId(idA);
    const b = painelPorId(idB);
    if (!a || !b || !DIAGRAMAS_QUE_PAREIAM.has(a.tipo)
        || !DIAGRAMAS_QUE_PAREIAM.has(b.tipo)) return false;
    // Três num par não cabem na linha, e o terceiro ficaria com um terço do
    // círculo. Desfaça o par existente para formar outro.
    return !temPar(idB) && !eDaDireita(idB);
  }

  /** A LINHA da tela em que o painel cai, e se cai antes ou depois dela.
   *
   * Linha, e não painel: um par de fasoriais ocupa uma linha só, e oferecer um
   * ponto de inserção ENTRE os dois quebraria o par sem o usuário ter pedido.
   */
  function lugarDeInsercao(evento) {
    const linhas = [...area.children].filter(
      (x) => x.classList.contains("grafico") || x.classList.contains("par-fasorial"));
    if (!linhas.length) return null;
    let melhor = null;
    for (const linha of linhas) {
      const r = linha.getBoundingClientRect();
      const antes = evento.clientY < r.top + r.height / 2;
      const alvo = antes ? r.top : r.bottom;
      const d = Math.abs(evento.clientY - alvo);
      if (!melhor || d < melhor.d) {
        const ponta = antes ? primeiroPainelDe(linha) : ultimoPainelDe(linha);
        if (ponta) melhor = { d, antes, id: ponta, linha };
      }
    }
    return melhor;
  }

  /** O meio do vão entre esta linha e a vizinha, em pixels da janela. */
  function meioDoVao(linha, antes) {
    const r = linha.getBoundingClientRect();
    const vizinho = antes ? linha.previousElementSibling
                          : linha.nextElementSibling;
    const v = vizinho ? vizinho.getBoundingClientRect() : null;
    if (antes) return v ? (v.bottom + r.top) / 2 : r.top - 11;
    return v ? (r.bottom + v.top) / 2 : r.bottom + 11;
  }

  const primeiroPainelDe = (linha) => {
    const el = linha.classList.contains("grafico") ? linha
             : linha.querySelector(".grafico");
    return el && el._painel ? el._painel.id : null;
  };

  const ultimoPainelDe = (linha) => {
    const todos = linha.classList.contains("grafico") ? [linha]
                : [...linha.querySelectorAll(".grafico")];
    const el = todos[todos.length - 1];
    return el && el._painel ? el._painel.id : null;
  };

  function limparMiraDoArrasto(arrasto = arrastoDePainel) {
    // Recebe o arrasto por parâmetro porque `terminarArrasto` já zerou o
    // estado quando chama: sem isto a linha ficava na tela até o próximo
    // desenho — alguns segundos depois de soltar, o que se lê como travada.
    if (arrasto && arrasto.marca) arrasto.marca.remove();
    for (const b of blocos) b.classList.remove("alvo-de-par");
  }

  /** Aplica o arrasto (ou desiste dele) e volta a tela ao normal. */
  function terminarArrasto(aplicar) {
    const arrasto = arrastoDePainel;
    arrastoDePainel = null;
    if (arrasto) {
      // O `click` vem DEPOIS do `pointerup`, e o alvo dele é o título — que
      // é botão de renomear. Engolir este um impede o campo de renomear de
      // abrir no fim de todo arrasto.
      document.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
      }, { capture: true, once: true });
    }
    area.classList.remove("arrastando-painel");
    for (const b of blocos) b.classList.remove("em-arrasto");
    if (!arrasto) return;
    limparMiraDoArrasto(arrasto);
    if (!aplicar || !arrasto.destino || !arrasto.modo) return;
    moverPainelPara(arrasto.id, arrasto.destino, arrasto.modo);
  }

  /** Tira o painel de onde ele está e o põe junto do destino.
   *
   * `modo` é `antes`, `depois` ou `parear`. O par é o único que mexe em mais
   * do que a ordem: ele acende a marca no painel da ESQUERDA, que é como a
   * tela sabe que os dois dividem a linha. Ver `emLinhas`.
   */
  function moverPainelPara(id, idDoDestino, modo) {
    const i = paineis.findIndex((x) => x.id === id);
    if (i < 0 || id === idDoDestino) return;
    guardarParaDesfazer();

    // Sair de um par desfaz o par: o que fica volta a ocupar a linha inteira.
    desfazerPar(id);
    const [movido] = paineis.splice(i, 1);
    delete movido.par;

    const j = paineis.findIndex((x) => x.id === idDoDestino);
    if (j < 0) {                       // o destino sumiu: devolve onde estava
      paineis.splice(Math.min(i, paineis.length), 0, movido);
      carregar();
      return;
    }
    if (modo === "parear") {
      paineis.splice(j + 1, 0, movido);
      paineis[j].par = true;
    } else {
      paineis.splice(modo === "antes" ? j : j + 1, 0, movido);
    }
    selecionados = [];
    painelEscolhido = null;
    carregar();
  }

  /** Troca o título por um campo de texto, e devolve o título no fim. */
  function editarNome(botao, painel) {
    const campo = document.createElement("input");
    campo.type = "text";
    campo.className = "nome-painel-campo";
    campo.value = painel.nome;
    // O `blur` dispara DENTRO do `replaceWith` — tirar o campo do documento
    // tira o foco dele —, e sem esta trava o segundo `terminar` tentava
    // substituir um nó que já saiu. Uma bandeira própria é mais confiável que
    // consultar `isConnected` no meio da operação que o desconecta.
    let pronto = false;
    const terminar = (guardar) => {
      if (pronto) return;
      pronto = true;
      const novo = campo.value.trim();
      campo.replaceWith(botao);
      if (guardar && novo) renomearPainel(painel.id, novo);
    };
    campo.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter") terminar(true);
      if (evento.key === "Escape") { evento.stopPropagation(); terminar(false); }
    });
    campo.addEventListener("blur", () => terminar(true));
    botao.replaceWith(campo);
    campo.focus();
    campo.select();
  }

  /** A etiqueta numerada dos cursores, ACIMA da moldura.
   *
   * Por dentro do gráfico ela tapava a crista da onda justamente quando se põe
   * o cursor no pico para medir amplitude. A identidade do cursor não pode
   * ficar só na cor, então a etiqueta continua — só que fora.
   *
   * Vale para as ondas e para as tiras digitais: os dois blocos dividem os
   * mesmos cursores, e um cursor numerado num bloco e anônimo no outro faria
   * duvidar se são os mesmos.
   */
  function pintarEtiquetas(ctx, emX, x0, x1, y0) {
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

      // No que o ímã grudou, ao lado do número. É a resposta à única dúvida
      // que o ímã cria: com um pico e uma transição a três pixels um do outro,
      // o cursor pega um dos dois — e sem isto escrito ninguém sabe qual.
      // Só o cursor ATIVO mostra a etiqueta. Dois cursores a nove pixels um
      // do outro — que é o caso comum, medindo trip contra abertura — têm as
      // duas etiquetas no mesmo lugar, e duas frases sobrepostas não se leem.
      // O ativo é o que acabou de ser posto ou movido, que é justamente
      // aquele sobre o qual se tem a dúvida.
      const preso = k === ativo ? presos[k] : null;
      if (preso) {
        ctx.fillStyle = token(k === 0 ? "--cursor-1" : "--cursor-2");
        ctx.globalAlpha = 0.9;
        ctx.font = "10px ui-monospace, Consolas, monospace";
        // Perto da borda direita o texto vira para a esquerda, senão a metade
        // que interessa é justamente a que sai do canvas.
        const cabe = x1 - (centro + meia + 5);
        const paraEsquerda = ctx.measureText(preso.rotulo).width > cabe;
        ctx.textAlign = paraEsquerda ? "right" : "left";
        ctx.fillText(preso.rotulo,
                     centro + (paraEsquerda ? -meia - 5 : meia + 5),
                     topo + ETIQUETA.altura / 2);
      }
      ctx.restore();
    });
  }

  /** Desenha as tiras. Mesmo eixo de tempo das ondas, mesmo arrasto. */
  function pintarDigitais(canvas, painel, ultimo) {
    const linhas = painel.tiras;
    const cssLargura = canvas.parentElement.clientWidth;
    const cssAltura = MARGEM.topo + Math.max(linhas.length, 1) * TIRA
                    + MARGEM.baixo + (ultimo ? 12 : 0);
    const dpr = window.devicePixelRatio || 1;

    canvas.style.width = `${cssLargura}px`;
    canvas.style.height = `${cssAltura}px`;
    dimensionar(canvas, Math.round(cssLargura * dpr), Math.round(cssAltura * dpr));

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssLargura, cssAltura);

    //: A grade da TELA, em coordenadas de CSS. Tudo que é barra passa por
    //: aqui: borda em pixel inteiro de tela é borda sem antialiasing, e sem
    //: antialiasing não há fresta nem degrau na troca de estado.
    const noPixel = (v) => Math.round(v * dpr) / dpr;

    const x0 = MARGEM.esq;
    const x1 = cssLargura - MARGEM.dir;
    const y0 = MARGEM.topo;
    const y1 = y0 + Math.max(linhas.length, 1) * TIRA;
    if (x1 <= x0) return;

    const tMin = dados.de;
    const tMax = dados.ate;
    const emX = (t) =>
      x0 + ((t - tMin) / (tMax - tMin || 1)) * (x1 - x0) + arrastoPx;

    ctx.font = FONTE_TIRA;
    ctx.textBaseline = "middle";

    // --- o nome de cada tira, fora da área que o arrasto mexe -------------
    //
    // O corte é pela largura medida, não por um número fixo de letras: fonte
    // monoespaçada hoje, proporcional amanhã, e a etiqueta continua cabendo.
    const haEscolha = selecionados.some(
      (x) => x.tipo === "digital" && x.painel === painel.id);
    ctx.textAlign = "right";
    linhas.forEach((tira, k) => {
      const escolhida = estaSelecionado(painel, "digital", tira.id || tira.indice);
      ctx.fillStyle = escolhida ? token("--destaque") : token("--tinta");
      ctx.globalAlpha = haEscolha && !escolhida ? 0.4 : 1;
      const meio = y0 + k * TIRA + TIRA / 2;
      if (!variosIeds()) {
        ctx.fillText(encaixar(tira.nome, x0 - 12), x0 - 8, meio);
        return;
      }
      // Com mais de um IED na aba, o selo antes do nome, como na legenda.
      const texto = encaixar(tira.nome, x0 - 30);
      ctx.fillText(texto, x0 - 8, meio);
      const letra = tira.ied || "A";
      const xs = x0 - 8 - ctx.measureText(texto).width - 16;
      ctx.save();
      ctx.globalAlpha = 1;
      ctx.fillStyle = token({ A: "--destaque", B: "--traco-2", C: "--traco-1" }[letra]);
      ctx.fillRect(xs, meio - 6, 12, 12);
      ctx.fillStyle = token("--fundo");
      ctx.font = "700 9px var(--mono), monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(letra, xs + 6, meio + 0.5);
      ctx.restore();
    });
    ctx.globalAlpha = 1;

    ctx.save();
    ctx.beginPath();
    ctx.rect(x0, y0, x1 - x0, y1 - y0);
    ctx.clip();

    // --- grade vertical, na mesma posição da das ondas --------------------
    ctx.strokeStyle = token("--linha");
    ctx.globalAlpha = 0.35;
    for (const marca of dados.marcacoes_tempo) {
      const x = Math.round(emX(marca)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // --- as tiras ---------------------------------------------------------
    //
    // Uma linha só, na mesma altura do começo ao fim, mudando de ESPESSURA:
    // fina enquanto o sinal está em 0, grossa enquanto está em 1. A linha do
    // zero é o que deixa claro que o canal existe e está desligado — sem ela,
    // um digital que nunca sobe seria indistinguível de um que não foi
    // desenhado. E como a linha nunca troca de altura, o olho lê a tira
    // inteira sem subir e descer: o que salta é a espessura.
    const tempoDoPainel = painel.tempo_digitais || dados.tempo_digitais || [];
    // A cor é de CADA painel, escolhida na engrenagem; sem escolha, o token.
    const meuPainel = painelPorId(painel.id) || {};
    const corEscolhida = token("--destaque");
    linhas.forEach((tira, k) => {
      // A tira de outro IED traz as colunas DELA, no eixo da aba.
      const tempo = tira.tempo || tempoDoPainel;
      // A cor é de CADA TIRA: o pincel vence a categoria, que vence a cor do
      // painel. Ver `corDaTira`.
      const corBarra = corDaTira(painel, tira);
      const escolhida = estaSelecionado(painel, "digital", tira.id || tira.indice);
      const meio = Math.round(y0 + k * TIRA + TIRA / 2);
      ctx.globalAlpha = haEscolha && !escolhida ? 0.35 : 1;

      // Colunas de mesmo estado seguidas viram UM retângulo só. Desenhar uma
      // por uma deixava a barra tracejada: cada retângulo cai em fração de
      // pixel e o antialiasing abre uma fresta clara entre vizinhos. Um trip
      // contínuo que aparece pontilhado se lê como trip intermitente.
      ctx.fillStyle = escolhida ? corEscolhida : corBarra;
      const fim = (i) => (i + 1 < tempo.length ? emX(tempo[i + 1]) : emX(tMax));
      const trecho = (i, j, ligado) => {
        // Arredondado no PIXEL DE TELA, e não no pixel de CSS — é isto que
        // tira o degrau da troca de estado.
        //
        // O canvas está em `dpr` (1,25 na tela do laboratório): um `x` inteiro
        // em CSS vale 1,25 px de tela, que só é inteiro de quatro em quatro.
        // Nos outros três, a borda do retângulo cai no meio de um pixel de
        // tela e o navegador a dilui em duas colunas — e a barra fina e a
        // grossa, diluídas cada uma para o seu lado, mostram um fiozinho mais
        // claro justamente na troca de 0 para 1. Arredondar na grade da TELA
        // põe as duas bordas no mesmo lugar, e a junção some.
        const a = noPixel(emX(tempo[i]));
        const b = noPixel(fim(j));
        // A tira escolhida engorda um pouco: no meio de quarenta tiras, só a
        // cor não salta — o olho encontra a espessura antes da cor.
        const alto = (ligado ? GROSSA : FINA) + (escolhida ? 2 : 0);
        // As bordas de cima e de baixo, na mesma grade, pela mesma razão: uma
        // barra diluída na horizontal parece mais clara que a vizinha, e duas
        // barras da mesma cor com brilhos diferentes se leem como dois
        // estados diferentes.
        const topo = noPixel(meio - alto / 2);
        const base = noPixel(meio + alto / 2);
        // Pulso de uma amostra num registro longo cai numa coluna só: o
        // mínimo de 1 px é o que o mantém visível. Trip que some da tela é
        // pior que trip mais gordo do que é.
        ctx.fillRect(a, topo, Math.max(b - a, 1), base - topo);
      };

      let inicio = 0;
      for (let i = 1; i <= tira.ligado.length; i++) {
        const acabou = i === tira.ligado.length;
        if (acabou || tira.ligado[i] !== tira.ligado[inicio]) {
          trecho(inicio, i - 1, !!tira.ligado[inicio]);
          inicio = i;
        }
      }
      ctx.globalAlpha = 1;
    });

    // --- os cursores ------------------------------------------------------
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

    if (arrastoPx !== 0) {
      const largura = Math.min(Math.abs(arrastoPx), x1 - x0);
      ctx.save();
      ctx.fillStyle = token("--fundo");
      ctx.globalAlpha = 0.82;
      ctx.fillRect(arrastoPx > 0 ? x0 : x1 - largura, y0, largura, y1 - y0);
      ctx.restore();
    }
    ctx.restore();

    ctx.strokeStyle = token("--linha");
    ctx.lineWidth = 1;
    ctx.strokeRect(x0 + 0.5, y0 + 0.5, x1 - x0 - 1, y1 - y0 - 1);

    pintarEtiquetas(ctx, emX, x0, x1, y0);
    pintarRodapeDoTempo(ctx, emX, x0, x1, y1, ultimo);
  }

  /** A busca: qualquer digital do arquivo, para pôr NESTE painel.
   *
   * Existe porque "só os que mudaram" é o padrão certo e não é a regra toda:
   * num laudo, às vezes o que importa é provar que um sinal **não** mudou.
   * Escondido não pode virar inexistente.
   */
  function abrirBusca(painel) {
    const disponiveis = dados.digitais_disponiveis || [];
    // Quem sabe o que está no painel é o ARRANJO da tela, não a resposta do
    // servidor: a resposta traz as tiras desenhadas, que é outra coisa (um
    // canal pedido e inexistente não vira tira, e continua pedido).
    const meu = painelPorId(painel.id);
    // O id de um digital no painel: o índice, com a letra do IED quando
    // ele não é do A (`B|3`). Ver `plot/varios.py`.
    const chaveDo = (d) => (d.ied && d.ied !== "A" ? `${d.ied}|${d.indice}` : String(d.indice));
    const escolhidos = new Set((meu ? meu.sinais : []).map(String));
    const janelinha = criar("dialog", "busca");

    const campo = document.createElement("input");
    campo.type = "search";
    campo.placeholder = "procurar sinal pelo nome…";
    const lista = criar("div", "achados");

    const desenharLista = () => {
      const procura = campo.value.trim().toUpperCase();
      // A busca filtra só os que ainda NÃO estão na tela: os outros já se veem
      // no gráfico, e quem procura está procurando entre os que faltam.
      const fora = disponiveis
        .filter((d) => !escolhidos.has(chaveDo(d)))
        .filter((d) => combinaNome(d.nome, procura))
        .slice(0, 300);
      const naTela = disponiveis.filter((d) => escolhidos.has(chaveDo(d)));

      const desenhar = (d) => {
        const item = criar("label", d.mudou ? "achado mudou" : "achado");
        const marca = document.createElement("input");
        marca.type = "checkbox";
        marca.checked = escolhidos.has(chaveDo(d));
        marca.addEventListener("change", () => {
          if (marca.checked) escolhidos.add(chaveDo(d));
          else escolhidos.delete(chaveDo(d));
        });
        item.append(marca);
        const seloDoDigital = seloDoIed(d.ied);
        if (seloDoDigital) item.append(seloDoDigital);
        item.append(criar("span", "nome", d.nome));
        // O relé grava este canal sem ter a placa: o que muda ali não é
        // entrada nenhuma (o 487E põe um contador de amostras nesses bits).
        if (d.sem_placa) {
          item.classList.add("sem-placa");
          const aviso = criar("span", "sem-placa-aviso", "sem placa");
          aviso.title = "A seção [IOBOARDS] do .hdr diz que a placa do relé não "
                      + "tem esta entrada/saída. O relé grava o bit assim mesmo, "
                      + "e o que muda nele não é sinal de nada.";
          item.append(aviso);
        } else if (d.instante !== null && d.instante !== undefined) {
          // Quem mudou ganha a hora da primeira mudança: é o que distingue
          // "este é o trip que eu procuro" de um homônimo.
          item.append(criar("span", "quando",
                            `${formatar(d.instante * 1000, 1)} ms`));
        }
        return item;
      };

      montarAchados(lista, fora, naTela, desenhar,
                    procura ? "Nenhum digital com esse nome fora da tela."
                            : "Todos os digitais do registro já estão aqui.");
    };

    campo.addEventListener("input", desenharLista);
    desenharLista();

    const aplicar = criar("button", "aceitar", "mostrar na tela");
    aplicar.addEventListener("click", () => {
      // A ordem é a da lista (hora da mudança), não a de clique: a tela conta
      // a sequência do evento, e isso não pode depender de em que ordem o
      // usuário marcou as caixas.
      const ids = disponiveis
        .filter((d) => escolhidos.has(chaveDo(d))).map(chaveDo);
      janelinha.close();
      trocarSinais(painel.id, ids);
    });

    // Fechar sem escolher nada. O Esc já fazia isso, e Esc é um atalho que
    // quem não conhece não descobre — a janela precisa dizer como se sai dela.
    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem mudar a tela";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());

    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, `Digitais de ${painel.nome}`), campo, fechar);
    janelinha.append(cabeca, lista, aplicar);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
    campo.focus();
  }

  /** Monta a lista de uma busca em duas partes: o que falta, e o que já está.
   *
   * Quem procura um sinal está procurando entre os que AINDA não estão na
   * tela — os outros ele já vê no gráfico. Então a busca e as abas filtram só
   * a parte de cima; a de baixo mostra sempre tudo que está escolhido, junto,
   * sem separar por aba: ali o que importa é poder tirar da tela, e de onde
   * veio o sinal não muda isso.
   */
  function montarAchados(lista, fora, naTela, desenhar, vazio) {
    const nos = fora.length
      ? fora.map((x) => desenhar(x, false))
      : [criar("p", "vazio", vazio)];
    if (naTela.length) {
      nos.push(criar("div", "divisor",
                     `já na tela (${naTela.length}) — desmarque para tirar`));
      // O segundo argumento diz que a linha é de um sinal que JÁ está no
      // gráfico — só ali existe cor para mostrar e para trocar.
      nos.push(...naTela.map((x) => desenhar(x, true)));
    }
    lista.replaceChildren(...nos);
  }

  /** O quadrinho com a cor de um sinal, e a listinha para trocá-la.
   *
   * Mesmo gesto do lápis do vínculo, e de propósito: clicar troca o quadrinho
   * por um `<select>`, escolher aplica na hora, sair fecha. Dois controles
   * parecidos na mesma janela precisam se comportar igual, senão cada um vira
   * uma coisa nova para aprender.
   *
   * A cor do traço é a de agora, com a escolha do usuário já aplicada — é o
   * que o quadrinho tem que mostrar, senão ele não serve de referência.
   */
  function caixaDeCor(painel, x) {
    // `corDoSinal` resolve a cor contra os VIZINHOS do painel, então precisa
    // do sinal desenhado — o do catálogo não tem fase nem posição.
    const doPainel = () =>
      (painel.sinais || []).find((s) => s.id === x.id) || { id: x.id };
    const corAgora = () => corDoSinal(doPainel(), painel);

    const botao = criar("button", "cor-do-sinal");
    botao.type = "button";
    botao.style.background = corAgora();
    botao.title = "cor deste sinal no gráfico — clique para trocar";
    botao.setAttribute("aria-label", "trocar a cor deste sinal");

    botao.addEventListener("click", (evento) => {
      // O clique não pode virar clique no `<label>`, senão marca a caixinha.
      evento.preventDefault();
      evento.stopPropagation();

      // As cores em BOLINHAS, e não numa lista de nomes: "ocre" e "oliva" são
      // a mesma palavra para quem está escolhendo a cor de uma curva. O que se
      // está comparando é cor, então o que tem que estar na tela é cor.
      const paleta = criar("span", "paleta");
      const valendo = corEscolhida(painel.id, x.id) || corDoTokenAtual(painel, x);

      let pronto = false;
      const fechar = () => {
        if (pronto) return;
        pronto = true;
        botao.style.background = corAgora();
        paleta.replaceWith(botao);
      };

      for (const cor of PALETA) {
        const bolinha = criar("button", "cor-opcao");
        bolinha.type = "button";
        bolinha.style.background = token(cor);
        bolinha.title = cor === valendo ? "cor atual" : "usar esta cor";
        if (cor === valendo) bolinha.classList.add("escolhida");
        bolinha.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          escolherCor(painel.id, x.id, cor);
          fechar();
        });
        paleta.append(bolinha);
      }

      // Sai do ar ao perder o foco para fora dela, e no Esc. `focusout` e não
      // `blur` porque o foco anda ENTRE as bolinhas, e cada passo desses é um
      // blur que fecharia a paleta na cara de quem está navegando por teclado.
      paleta.addEventListener("focusout", (e) => {
        if (!paleta.contains(e.relatedTarget)) fechar();
      });
      paleta.addEventListener("keydown", (e) => {
        if (e.key === "Escape") { e.stopPropagation(); fechar(); }
      });

      botao.replaceWith(paleta);
      paleta.firstChild.focus();
    });
    return botao;
  }

  /** O TOKEN da cor que um sinal está usando agora neste painel.
   *
   * `corDoSinal` devolve o código da cor, que é o que se pinta; aqui é preciso
   * o token, que é o que se compara com a paleta para marcar qual bolinha está
   * valendo. Guardar o token, e não o código, é o que faz a escolha acompanhar
   * o tema claro e o escuro.
   */
  function corDoTokenAtual(painel, x) {
    return coresDoPainel(painel).get(x.id) || "";
  }

  //: Como a tela escreve de onde veio o vínculo de cada canal.
  const ORIGEM_DO_VINCULO = {
    escolhida: "você corrigiu este vínculo",
    automatico: "voltou para a dedução automática",
    declarada: "o próprio arquivo declara a fase deste canal (campo `ph`)",
    deduzida: "deduzido do NOME do canal — confira",
    desconhecida: "o nome do canal não disse que fase é",
  };

  //: Os três LAÇOS: o canal mede entre duas fases, não contra o neutro.
  //: Espelha `LACOS` em `formats/fases.py` — ver lá por que a diferença
  //: importa.
  const LACOS = ["AB", "BC", "CA"];

  //: As vagas que existem numa trinca: três de fase OU três de laço. `N` não
  //: é vaga — o residual acompanha a trinca e não entra na conta.
  const VAGAS_DE_TRINCA = ["A", "B", "C", ...LACOS];

  //: De onde veio a fase, em quatro palavras — para a janelinha de corrigir.
  //: `ORIGEM_DO_VINCULO`, logo acima, é a versão longa que o hover do lápis
  //: mostra; aqui a linha tem que caber ao lado do valor.
  const DE_ONDE_VEIO_A_FASE = {
    escolhida: "você corrigiu",
    automatico: "dedução automática",
    declarada: "declarado pelo arquivo",
    deduzida: "deduzido do nome do canal",
    desconhecida: "o nome não disse",
  };

  /** As opções da correção de fase, já com a letra da grandeza.
   *
   * `IA`, `IB`, `IC`, `IN` em vez de `A`, `B`, `C`, `N`: a grandeza não é
   * palpite — vem da unidade que o arquivo declara —, então a listinha pode
   * mostrar o nome inteiro da variável, que é como o engenheiro pensa nela. O
   * que se está escolhendo continua sendo só a fase.
   */
  function fasesPossiveis(grandeza) {
    const g = grandeza || "";
    return [["", "automático (pelo nome do canal)"],
            ["A", `${g}A`], ["B", `${g}B`], ["C", `${g}C`],
            ["N", `${g}N (neutro/residual)`],
            // Os LAÇOS: o relé mediu entre duas fases, não contra o neutro.
            // `VAB` não é "a fase A" — e tratá-lo como fase A é o erro que faz
            // o 3V0 dar zero por identidade (VAB+VBC+VCA ≡ 0) e V1/V2 saírem
            // esticados de √3 e girados de 30°, tudo na unidade certa.
            ["AB", `${g}AB (entre fases)`],
            ["BC", `${g}BC (entre fases)`],
            ["CA", `${g}CA (entre fases)`],
            ["-", "nenhuma"]];
  }

  /** O vínculo canal → variável fundamental, com o botão de corrigir.
   *
   * Ele NÃO é um sinal a mais para desenhar: é a conferência daquilo em que
   * todas as contas se apoiam. `IA` só é a corrente da fase A porque o
   * programa leu `Current IA` e decidiu isso — e o nome é escrito como cada
   * fabricante quer. Vínculo errado corrompe conjunto trifásico, 3I0, V1 e a
   * localização de falta SEM dar erro nenhum, com o número saindo na unidade
   * certa e na ordem de grandeza certa.
   *
   * Por isso o botão de corrigir fica aqui, ao lado da conferência: quem viu o
   * erro conserta no mesmo lugar em que o viu.
   */
  function vinculoDoCanal(x, correcoes, redesenhar) {
    const caixa = criar("span", "vinculo-caixa");
    const pendente = correcoes.get(x.canal);
    const mexido = pendente !== undefined;
    const origem = mexido ? "escolhida" : (x.fundamental_origem || "desconhecida");

    // O chip com a fase (`IA`) saiu da lista.
    //
    // Ele era a conferência do vínculo, e a conferência continua valendo — o
    // que não vale mais é a NOMENCLATURA: os sinais se chamam pelo nome do
    // arquivo (`IAW · RMS`), e um `IA` ao lado, em outra nomenclatura, era uma
    // segunda forma de chamar a mesma coisa na mesma linha.
    //
    // O vínculo não se perde: ele está no hover do lápis, que diz o que o
    // programa deduziu e deixa corrigir. Sem isso, um vínculo torto não teria
    // mais como ser arrumado — e vínculo torto corrompe conjunto trifásico,
    // 3I0, V1 e a localização de falta SEM dar erro nenhum, com o número
    // saindo na unidade certa e na ordem de grandeza certa.
    const g = x.grandeza_do_canal || "";
    const pedido = pendente === "" ? "automático"
                 : pendente === "-" ? "nenhuma" : `${g}${pendente}`;

    const lapis = criar("button", "editar-vinculo", "✎");
    lapis.type = "button";
    if (mexido) lapis.classList.add("pendente");
    lapis.title = mexido
      ? `Correção pendente para ${pedido} — clique em «mostrar na tela» para `
        + "gravar. Ela vale para este registro e fica gravada."
      : x.fundamental
        ? `${ORIGEM_DO_VINCULO[origem] || ""}: é a fase ${x.fundamental}. `
          + "É dela que saem as componentes simétricas e a localização de "
          + "falta. Clique para corrigir."
        : "Este canal não está vinculado a uma fase: ele desenha, mas não "
          + "entra em componente simétrica nem em localização de falta. "
          + "Clique para dizer qual fase é.";
    lapis.setAttribute("aria-label", "corrigir a fase deste canal");
    lapis.addEventListener("click", (evento) => {
      // O clique não pode virar clique no `<label>`, senão marca a caixinha.
      evento.preventDefault();
      evento.stopPropagation();
      abrirFaseDoCanal(x, correcoes, redesenhar);
    });
    caixa.append(lapis);
    return caixa;
  }

  /** A janelinha de corrigir a FASE de um canal.
   *
   * Era um `<select>` solto, trocado no lugar da etiqueta, dentro de uma
   * célula de tabela. Saiu: a lista aberta do navegador é desenhada por cima
   * do que estiver ao lado, e numa tabela de vinte linhas ela tapava a coluna
   * do grupo — a informação que a pessoa está justamente conferindo.
   *
   * Agora é janelinha, igual à do grupo. As duas correções desta tela passam
   * a se parecer, e nenhuma tapa a tabela enquanto está aberta.
   */
  function abrirFaseDoCanal(x, correcoes, redesenhar) {
    const pendente = correcoes.get(x.canal);
    const janelinha = criar("dialog", "busca trincas curta");
    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem mudar nada";
    fechar.addEventListener("click", () => janelinha.close());
    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, `Que fase é ${x.nome}`), fechar);
    // Uma linha, como na janelinha do grupo: o que vale HOJE e de onde veio.
    // O parágrafo que estava aqui explicava por que a fase importa — e isso
    // é a mesma frase em toda abertura, para quem já sabe. Foi para o hover
    // da lista, junto com o resto do aviso.
    const ajuda = criar("p", "ajuda-rotulo",
      x.fundamental
        ? `Hoje: ${x.fundamental} — ${DE_ONDE_VEIO_A_FASE[
            x.fundamental_origem] || "origem desconhecida"}.`
        : "Hoje este canal não tem fase: ele desenha, mas fica fora do "
          + "resíduo e das componentes simétricas.");

    const lista = criar("div", "achados");
    const item = criar("div", "achado rotulo-trinca");
    const escolha = document.createElement("select");
    escolha.className = "escolher-fase";
    for (const [valor, rotulo] of fasesPossiveis(x.grandeza_do_canal)) {
      const o = document.createElement("option");
      o.value = valor;
      o.textContent = rotulo;
      escolha.append(o);
    }
    escolha.value = pendente !== undefined ? pendente : "";
    escolha.title = "A fase sai do NOME do canal, e nome de canal cada "
                  + "fabricante escreve como quer. É deste vínculo que saem o "
                  + "resíduo, as componentes simétricas e a localização de "
                  + "falta — errado, todos erram junto, na unidade certa e "
                  + "sem aviso.";
    item.append(criar("span", "nome", "fase"), escolha);
    lista.append(item);

    const aplicar = criar("button", "aceitar", "gravar");
    aplicar.type = "button";
    aplicar.addEventListener("click", () => {
      correcoes.set(x.canal, escolha.value);
      janelinha.close();
      redesenhar();
    });

    janelinha.append(cabeca, ajuda, lista, aplicar);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
  }

  /** Grava no servidor as correções de fase. Falhar aqui não pode ser mudo. */
  async function gravarVinculos(correcoes) {
    const corpo = {};
    for (const [canal, fase] of correcoes) corpo[String(canal)] = fase;
    try {
      const r = await fetch(`/api/onda/${sha}/vinculos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
      if (!r.ok) throw new Error(`o servidor respondeu ${r.status}`);
    } catch (erro) {
      // Silêncio aqui seria o pior: o usuário acharia que corrigiu a fase e
      // seguiria analisando com o vínculo errado.
      avisarNoPe("Não consegui gravar a correção de fase: "
                 + `${erro.message}. O vínculo continua como estava.`);
    }
  }

  //: As colunas da matriz do catálogo, na ordem em que a tela as mostra. A
  //: chave é a COLUNA do sinal, que nasce no Python — ver `plot/catalogo.py`.
  //:
  //: Uma linha por canal e uma coluna por conta é o que tirou esta tela da
  //: lista: um SEL-487E rende mais de cem nomes soltos, e as mesmas contas em
  //: vinte e uma linhas de caixinhas cabem sem rolagem. A `{f}` é preenchida
  //: com a frequência do REGISTRO — um arquivo de 50 Hz escreve 50.
  //:
  //: **Dois grupos, e o filtrado na frente.** As colunas respondem duas
  //: perguntas diferentes: QUAL sinal (o filtrado, que é só a componente de
  //: 60 Hz, ou o bruto, que é tudo o que o relé gravou) e COMO olhar para ele
  //: (a onda, o eficaz, a contínua). Enquanto foram cinco colunas irmãs, nada
  //: na tela dizia que `onda` e `60 Hz` eram sinais diferentes.
  const COLUNAS_DO_CATALOGO = [
    ["filtrado.onda", "onda", "só a componente de {f}, no tempo — a saída do "
     + "filtro, a mesma que o relé enxerga"],
    ["filtrado.rms", "RMS",
     "o eficaz dessa componente — o número com que o relé decide atuar"],
    ["bruto.onda", "onda", "a amostra como o IED gravou: {f}, harmônicos e a "
     + "contínua da falta, tudo junto"],
    ["bruto.rms", "RMS",
     "eficaz verdadeiro da janela de um ciclo — leva harmônicos e contínua"],
    ["bruto.dc", "DC",
     "a componente contínua: a média da janela de um ciclo, com sinal"],
  ];

  //: Os dois grupos de coluna, na ordem, e o que cada um é.
  const GRUPOS_DE_COLUNA = {
    filtrado: ["filtrado", "Só a componente de {f}, extraída pelo filtro: é o "
               + "sinal com que o relé decidiu atuar, e de onde saem 3I0, I1 "
               + "e I2. NÃO tem a assimetria da falta nem a saturação do TC, e "
               + "atrasa até um ciclo nas transições."],
    bruto: ["bruto", "A amostra como o relé gravou, sem filtro nenhum: {f}, "
            + "harmônicos e a contínua da falta, tudo junto. É onde se vê "
            + "saturação de TC, assimetria e o instante exato do trip."],
  };

  //: O modo de análise da TELA, guardado entre sessões. Mora aqui, e não na
  //: janelinha do catálogo, porque é um estado do programa — do mesmo tipo do
  //: filtro e do lado primário/secundário —, e o botão dele está no cabeçalho,
  //: junto dos outros. Lido do armazenamento junto com as ligações da tela.
  let visaoDeAnalise = "tradicional";

  //: Redesenha o catálogo que estiver aberto. A janelinha registra a função
  //: dela aqui enquanto vive: trocar o modo no cabeçalho tem que mexer na
  //: lista que está na frente do usuário, e não só na próxima que ele abrir.
  let redesenharCatalogo = null;

  //: Os dois modos de análise. `tradicional` é o padrão: mostra só o que sai
  //: do filtro — que é o que a análise usa — e deixa a onda crua, o eficaz com
  //: harmônicos e a contínua para o `avançado`.
  //:
  //: O preço do `tradicional` está dito no `title` das duas, e tem que estar:
  //: a onda filtrada não mostra saturação nem assimetria e chega até um ciclo
  //: atrasada. Quem mede o instante de um trip nela erra em até 16,7 ms — com
  //: a unidade certa e sem aviso nenhum.
  const VISOES = [
    ["tradicional", "tradicional",
     "só o que sai do filtro: a onda e o eficaz de 60 Hz, mais as componentes "
     + "de sequência. A onda bruta, a contínua e os canais que não são "
     + "senoidais ficam no «avançado»."],
    ["avancado", "avançado",
     "também o bruto: a onda como o relé gravou, o eficaz com harmônicos e a "
     + "componente contínua. É onde se compara o filtro com o cru."],
  ];

  //: Os dois jeitos de arrumar a lista. `lista` é o padrão, e é a ordem do
  //: ARQUIVO — a ordem em que o relé gravou os canais, não a alfabética, que
  //: embaralharia os terminais W, X e Y de um mesmo relé.
  const AGRUPAMENTOS = [
    ["lista", "lista", "os canais na ordem do arquivo, sem grupos"],
    ["grupo", "grupo trifásico",
     "cada grupo com os três canais dele, o resíduo e as componentes"],
  ];

  const SVG_NS = "http://www.w3.org/2000/svg";

  //: A senoide cheia dos sinais alternados, e o traço irregular dos outros.
  //:
  //: O «outros» é irregular de propósito: ele diz «outra forma de onda» sem
  //: afirmar QUAL. Um degrau se leria como contínua ou como digital, e é
  //: exatamente a afirmação que o programa não pode fazer — o que ele mediu é
  //: que ali não dá para tirar fasor. Ver `analysis/presenca.py`.
  const DESENHO_DO_SENO = "M1 7 C4 0.5 8.5 0.5 11.5 7 S19 13.5 22 7";
  const DESENHO_DOS_OUTROS =
    "M1 10 L4.5 5 L8 11 L11.5 3.5 L15 8.5 L18.5 6.5 L22 9.5 L25 7.5";

  //: O ícone do grupo trifásico: três senoides defasadas, nas cores das fases.
  //: É o mesmo desenho do cabeçalho do editor de grupos — o bloco e o editor
  //: falam da mesma coisa e têm que se parecer.
  const DESENHOS_DO_TRIFASICO = [
    ["M1 7 C3.5 1.5 6.5 1.5 9 7 S14.5 12.5 17 7", "--fase-a"],
    ["M5 7 C7.5 1.5 10.5 1.5 13 7 S18.5 12.5 21 7", "--fase-b"],
    ["M9 7 C11.5 1.5 14.5 1.5 17 7 S22.5 12.5 25 7", "--fase-c"],
  ];

  function iconeTrifasico() {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 26 14");
    svg.setAttribute("width", "24");
    svg.setAttribute("height", "13");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", "icone-trifasico");
    for (const [desenho, cor] of DESENHOS_DO_TRIFASICO) {
      const traco = document.createElementNS(SVG_NS, "path");
      traco.setAttribute("d", desenho);
      traco.setAttribute("fill", "none");
      traco.setAttribute("stroke", `var(${cor})`);
      traco.setAttribute("stroke-width", "1.6");
      traco.setAttribute("stroke-linecap", "round");
      svg.append(traco);
    }
    return svg;
  }

  /** O símbolo do que o OscLab calculou: `ƒx`.
   *
   * Um glifo, e não outra forma de onda. Já foi uma senoide tracejada, e saiu:
   * tracejado é como se DESENHA um sinal, e prometer no ícone um traço que o
   * gráfico não usa é mentir duas vezes — no ícone e no gráfico. `ƒx` não diz
   * nada sobre a onda; diz que ali houve conta, que é o assunto do bloco.
   */
  function iconeDoCalculado() {
    const marca = criar("span", "icone-calculado", "ƒx");
    marca.setAttribute("aria-hidden", "true");
    return marca;
  }

  /** O desenho de uma calculadora: moldura, visor e as teclas.
   *
   * Desenho, e não o `ƒx`: aquele diz "isto é calculado" e marca os sinais do
   * OscLab no catálogo — é outra coisa. O botão que ABRE a calculadora tem
   * que parecer uma calculadora, senão quem procura por ela varre o cabeçalho
   * inteiro sem ver.
   */
  function iconeDeCalculadora() {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 14 18");
    svg.setAttribute("width", "11");
    svg.setAttribute("height", "14");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", "icone-calculadora");
    const por = (nome, atributos) => {
      const no = document.createElementNS(SVG_NS, nome);
      for (const [k, v] of Object.entries(atributos)) no.setAttribute(k, v);
      svg.append(no);
    };
    // A moldura e o visor, em traço; as teclas, em cheio. É o que faz a
    // silhueta se ler a 11 px — seis quadradinhos sob uma faixa.
    por("rect", { x: 0.75, y: 0.75, width: 12.5, height: 16.5, rx: 1.75,
                  fill: "none", stroke: "currentColor", "stroke-width": 1.2 });
    por("rect", { x: 3, y: 3, width: 8, height: 3, rx: 0.6,
                  fill: "none", stroke: "currentColor", "stroke-width": 1.1 });
    for (const [cx, cy] of [[3.6, 9], [7, 9], [10.4, 9],
                            [3.6, 12.2], [7, 12.2], [10.4, 12.2],
                            [3.6, 15], [7, 15], [10.4, 15]]) {
      por("rect", { x: cx - 0.9, y: cy - 0.9, width: 1.8, height: 1.8,
                    rx: 0.4, fill: "currentColor" });
    }
    return svg;
  }

  /** Os dois desenhos do seletor de arranjo: ondas juntas × ondas empilhadas.
   *
   * Desenho e não palavra sozinha, porque a diferença entre os dois modos é
   * exatamente uma imagem: três senóides cruzando no mesmo zero, ou três
   * senóides em alturas diferentes. O ícone É o que vai acontecer com a tela.
   *
   * Nas cores de fase, como o ícone do grupo trifásico — é o mesmo assunto
   * (três sinais de um vão) visto de outro jeito.
   */
  const CORES_DO_ARRANJO = ["--fase-a", "--fase-b", "--fase-c"];

  function iconeDoArranjo(empilhado) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 26 14");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "11");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", "icone-do-arranjo");
    const alturas = empilhado ? [2.8, 7, 11.2] : [7, 8.6, 5.4];
    alturas.forEach((y, k) => {
      const traco = document.createElementNS(SVG_NS, "path");
      traco.setAttribute("d", empilhado
        ? `M1 ${y} Q5.5 ${y - 2.3} 10 ${y} T19 ${y} T25 ${y}`
        : `M1 ${y} Q7 ${y - 5.4} 13 ${y} T25 ${y}`);
      traco.setAttribute("fill", "none");
      traco.setAttribute("stroke", `var(${CORES_DO_ARRANJO[k]})`);
      traco.setAttribute("stroke-width", empilhado ? "1.4" : "1.5");
      traco.setAttribute("stroke-linecap", "round");
      svg.append(traco);
    });
    return svg;
  }

  function iconeDeTraco(desenho, classe) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 26 14");
    svg.setAttribute("width", "24");
    svg.setAttribute("height", "13");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    if (classe) svg.setAttribute("class", classe);
    const traco = document.createElementNS(SVG_NS, "path");
    traco.setAttribute("d", desenho);
    traco.setAttribute("fill", "none");
    traco.setAttribute("stroke", "currentColor");
    traco.setAttribute("stroke-width", "1.8");
    traco.setAttribute("stroke-linecap", "round");
    traco.setAttribute("stroke-linejoin", "round");
    svg.append(traco);
    return svg;
  }

  /** A frequência do registro como ela aparece num rótulo: `60 Hz`. */
  function frequenciaDoRegistro() {
    const hz = Number(dados && dados.frequencia_hz) || 60;
    return `${Number(hz.toFixed(2))} Hz`;
  }

  /** As LINHAS do catálogo: um sinal-base e as contas que existem para ele.
   *
   * `IAW`, `IAW · RMS`, `IAW · DC`, `IAW · 60Hz` e `IAW · 60Hz RMS` são cinco
   * sinais e UMA linha — a do canal —, e cada conta é uma coluna nela. Quem
   * diz qual é a linha de cada sinal é o servidor, no campo `linha`: o nome é
   * identidade e nasce no Python, e a arrumação da tela acompanha o nome.
   */
  function linhasDoCatalogo(todos) {
    const porChave = new Map();
    for (const x of todos) {
      // O índice do canal identifica a linha quando existe. O resíduo e as
      // componentes não saem de um canal só, e ali o nome é a identidade.
      const chave = x.canal >= 0 ? `c${x.canal}` : `q${x.linha}`;
      let linha = porChave.get(chave);
      if (!linha) {
        linha = { chave, nome: x.linha || x.nome, bloco: x.bloco || "alternado",
                  grupo: x.grupo || "", canal: x.canal, motivo: x.motivo || "",
                  aviso: x.aviso || "", familia: x.familia || "",
                  unidade: x.unidade, unidade_mostrada: x.unidade_mostrada,
                  grandeza_do_canal: x.grandeza_do_canal || "",
                  origem: x.origem || "", conjunto: x.conjunto || null,
                  nota: x.nota || "",
                  // De onde o sinal VEM, que é o que separa as seções da
                  // lista: `campo` veio no arquivo, `programa` o OscLab
                  // deduziu (resíduo, componente simétrica), `conta` o
                  // usuário escreveu. A expressão é o que distingue as duas
                  // últimas — as duas são `familia: "conta"` no servidor.
                  procedencia: x.familia === "canal" ? "campo"
                             : x.expressao ? "conta" : "programa",
                  // `componente`, `modulo` ou `misto` — só para conta do
                  // usuário. Ver `catalogo.Sinal.dominio`.
                  dominio: x.dominio || "",
                  // A partição de energia desta linha, quando foi possível
                  // medir: `[60 Hz, harmônicos, contínua]`.
                  energia: (dados.energia || {})[x.linha || x.nome] || null,
                  sem_sinal: false, contas: new Map() };
        porChave.set(chave, linha);
      }
      linha.contas.set(x.coluna || x.grandeza, x);
      // Sem sinal é do CANAL, não da conta: se a entrada não está cabeada,
      // nenhuma conta sobre ela tem o que dizer.
      if (x.sem_sinal) linha.sem_sinal = true;
      // A componente simétrica manda no bloco da linha dela; o resíduo fica
      // com os alternados, porque é senoide somada no tempo e não fasor.
      if (x.bloco === "sequencia") linha.bloco = "sequencia";
      if (x.conjunto) linha.conjunto = x.conjunto;
    }
    return [...porChave.values()];
  }

  /** O nome do sinal, com o nome do grupo numa caixinha.
   *
   * `IN G1` é UM nome — é assim que ele vai para a legenda, para a tabelinha e
   * para o relatório, e é assim que o `title` o mostra inteiro. O que muda
   * aqui é só o desenho: o `G1` do fim ganha a mesma caixinha que o grupo tem
   * no cabeçalho do bloco e no rodapé do gráfico, para os três se lerem como a
   * mesma coisa de relance.
   */
  function nomeComGrupo(destino, nome, grupo) {
    const fim = grupo ? ` ${grupo}` : "";
    if (fim && nome.endsWith(fim)) {
      destino.append(criarNome("span", "nome", nome.slice(0, -fim.length)),
                     criar("span", "chip-no-nome", grupo));
    } else {
      destino.append(criarNome("span", "nome", nome));
    }
    destino.title = nome;
  }

  /** `correntes · A`, `tensões · kV` — o que um grupo trifásico é.
   *
   * Sai da UNIDADE dos canais dele, não de palpite: um grupo tem uma grandeza
   * só, e é a unidade do arquivo que diz qual. Ver `formats/fases.py`.
   */
  function tipoDoGrupo(linhas) {
    const canal = linhas.find((l) => l.canal >= 0) || linhas[0] || {};
    const nome = { I: "correntes", V: "tensões" }[canal.grandeza_do_canal];
    /* A unidade do grupo era a do PRIMEIRO canal, e isso é uma mentira quando
     * os três não têm a mesma: numa trinca de potências — W, VA e var — o
     * cabeçalho dizia «grupo · W» e as outras duas ficavam desmentidas pela
     * unidade que cada linha mostra ao lado do nome.
     *
     * Agora ou ela é de todos, ou aparecem TODAS, na ordem dos canais — a
     * mesma ordem dos vínculos. Escolha dele. */
    const unidades = [];
    for (const l of linhas) {
      const u = l.unidade_mostrada || l.unidade || "";
      if (u && !unidades.includes(u)) unidades.push(u);
    }
    const unidade = unidades.join(" · ");
    /* O par de potência (`G1↔G3`) não tem grandeza de canal, porque não é um
     * canal: ele é o que SAI de dois grupos. Sem este caso o título dele caía
     * em «grupo», que não diz nada — e a caixinha ao lado já diz quais dois
     * vãos são. A seta é a marca do par (`SETA_DO_VINCULO`, em
     * `plot/catalogo.py`), e é o que distingue um vínculo de um grupo comum. */
    const doVinculo = (linhas.find((l) => l.grupo) || {}).grupo || "";
    const titulo = nome || (doVinculo.includes("↔") ? "potências" : "");
    if (!titulo) return unidade ? `grupo · ${unidade}` : "grupo";
    return unidade ? `${titulo} · ${unidade}` : titulo;
  }

  /** Os BLOCOS da tela, na ordem, conforme o «agrupar por».
   *
   * Em «grupo trifásico» cada grupo é um bloco fechado: os três canais, e
   * depois o que sai deles — o resíduo e as três componentes. Quem não está em
   * grupo nenhum vem depois, e «outros sinais» fecha a tela.
   *
   * Em «lista» a ordem é a do arquivo, com o que o OscLab calcula reunido no
   * fim: é a arrumação que havia antes das abas, sem elas.
   */
  /** Os grupos em que as TRÊS entradas estão sem sinal.
   *
   * É a trinca de reserva: o SEL-487E tem cinco terminais de TC e três livres.
   * Ela continua sendo um grupo, com o número dela — o número é a posição do
   * conjunto no ARQUIVO, e tem que ser o mesmo em todo registro daquele relé,
   * senão um `3I0 G2` guardado num relatório muda de significado no evento
   * seguinte. O que muda é o LUGAR dela na lista: vai para o fim, recolhida.
   */
  function gruposSilenciosos(linhas) {
    const porGrupo = new Map();
    for (const l of linhas) {
      if (!l.grupo || l.canal < 0) continue;
      const vivo = porGrupo.get(l.grupo);
      porGrupo.set(l.grupo, (vivo === undefined ? true : vivo) && l.sem_sinal);
    }
    return new Set([...porGrupo].filter(([, mudo]) => mudo).map(([g]) => g));
  }

  /** O bloco «Outros sinais»: canal do relé que não passou no teste de
   *  alternado, ou que não declara unidade, ou cuja fase não foi reconhecida.
   *
   * Em «lista» ele vem logo depois das senoides — os dois são canais do relé.
   * Em «grupo trifásico» ele vem no fim, porque ali os blocos de cima são os
   * VÃOS, e um canal sem fase reconhecida não é de vão nenhum.
   */
  function blocoDosOutros(outros) {
    return { chave: "outros", titulo: "Outros sinais", icone: "outros",
             recolhido: true,
             dica: "Canais do relé em que a onda não é alternada, ou que não "
                 + "declaram unidade: a tela não diz que são contínuos, diz "
                 + "que não sabe medi-los em eficaz.",
             secoes: [{ linhas: outros }] };
  }

  function blocosDoCatalogo(linhas, modo, silenciosos = new Set()) {
    /* A conta do usuário sai da divisão por BLOCO antes de tudo.
     *
     * «Senoidais», «Senoidais avulsos» e «Outros sinais» são o que o RELÉ
     * gravou — é a origem que os define, não a forma da onda. Uma conta
     * nossa listada ali se leria como um canal do arquivo, e essa é
     * exatamente a confusão que o bloco «Calculados» existe para evitar.
     *
     * Então a conta mora em «Calculados» sempre, senoidal ou não. O `bloco`
     * dela continua valendo, mas para outra pergunta: é ele que decide se ela
     * ganha fasor e espectro (ver `plot/fasorial.py` e `plot/harmonicos.py`).
     * São duas perguntas diferentes — ONDE ela é listada, e o QUE se pode
     * tirar dela — e antes daqui elas estavam amarradas na mesma resposta.
     */
    const doUsuario = linhas.filter((l) => l.familia === "conta");
    const doArquivo = linhas.filter((l) => l.familia !== "conta");
    const alternados = doArquivo.filter((l) => l.bloco !== "outros");
    const outros = doArquivo.filter((l) => l.bloco === "outros");
    //: Em «lista» o bloco «Outros sinais» entra no meio; em «grupo trifásico»,
    //: no fim. A marca é o que impede de entrar duas vezes -- e é uma marca, e
    //: não esvaziar o `outros`, porque o bloco já guarda a própria lista.
    let outrosJaEntrou = false;
    const blocos = [];

    if (modo === "grupo") {
      const grupos = [];
      for (const l of alternados) {
        if (l.grupo && !grupos.includes(l.grupo)) grupos.push(l.grupo);
      }
      // Os vivos primeiro, os silenciosos no fim — cada um com o NÚMERO que
      // sempre teve. Some a impressão de buraco na sequência sem o nome passar
      // a depender do que se mediu naquele registro.
      grupos.sort((a, b) => Number(silenciosos.has(a)) - Number(silenciosos.has(b)));
      for (const grupo of grupos) {
        const dele = alternados.filter((l) => l.grupo === grupo);
        const canais = dele.filter((l) => l.canal >= 0);
        const nossos = dele.filter((l) => l.canal < 0);
        // Um bloco só, sem separar os canais do que sai deles: o símbolo do
        // grupo já diz que tudo ali é do mesmo vão, e uma divisória no meio
        // sugeriria duas coisas onde há uma. A ordem faz o resto — os três
        // canais, o resíduo, as três componentes.
        const silencioso = silenciosos.has(grupo);
        blocos.push({
          chave: `grupo:${grupo}`, chip: grupo, titulo: tipoDoGrupo(dele),
          icone: "trifasico", silencioso,
          dica: silencioso
            ? "As três entradas do relé deste grupo não estão cabeadas: leem "
              + "só o ruído do conversor. O grupo continua existindo e com o "
              + "número dele — o número é a posição no arquivo, e mudar isso "
              + "faria o mesmo relé dar nomes diferentes em registros "
              + "diferentes."
            : "",
          conjunto: (dele.find((l) => l.conjunto) || {}).conjunto || null,
          secoes: [{ linhas: [...canais, ...nossos] }],
        });
      }
      const soltos = alternados.filter((l) => !l.grupo);
      if (soltos.length) {
        // «Avulsos» é a palavra que o programa já usa por dentro para o canal
        // que não fecha trinca (`conjuntos._avulsos`), e é mais preciso que
        // «fora de grupo»: o canal não saiu de um grupo, ele nunca formou um.
        blocos.push({ chave: "avulsos", titulo: "Senoidais avulsos",
                      icone: "seno", recolhido: true,
                      dica: "Canais senoidais que não fecham trinca: um `IG` de "
                          + "neutro, uma tensão de barra sozinha. Aceitam todas "
                          + "as contas; o que não sai deles é componente "
                          + "simétrica, que precisa de três.",
                      secoes: [{ linhas: soltos }] });
      }
      // Agrupado por trinca, o resíduo e as componentes entram no bloco do
      // grupo delas — elas SÃO daquele vão. A conta do usuário não é de
      // trinca nenhuma (pode somar canais de dois grupos, ou de nenhum), e
      // por isso ganha o bloco dela, no fim.
      if (doUsuario.length) {
        blocos.push({ chave: "calculados", titulo: "Calculados",
                      icone: "calculado",
                      dica: "As contas que você escreveu. Não entram num "
                          + "grupo porque não saem de uma trinca: podem "
                          + "misturar canais de vãos diferentes.",
                      secoes: [{ linhas: doUsuario }] });
      }
    } else {
      /* Em «lista», as seções são por PROCEDÊNCIA — de onde o sinal vem —, e
       * não pela forma da onda.
       *
       * «Senoidais» e «Calculados» respondiam duas perguntas ao mesmo tempo:
       * de onde o sinal veio E se dá para tirar fasor dele. A segunda já é
       * respondida sinal a sinal — pela engrenagem do cartão e pelo motivo ao
       * lado do nome —, e deixá-la governar a divisão da tela punha `IN G1`
       * (conta nossa, senoidal) do mesmo lado de `3I0 G1` (nossa, não é onda)
       * e do outro lado de `IAW` (do relé, senoidal). Três coisas, duas
       * caixas, nenhuma das duas sobre o que se procura.
       *
       * Procedência é o que se procura: «isto é do relé ou fomos nós?» — e a
       * resposta muda o que se pode confiar. Canal do relé é dado; o resto é
       * dedução nossa ou conta do usuário, e as duas podem estar erradas por
       * motivos diferentes.
       */
      const canais = alternados.filter((l) => l.canal >= 0);
      const nossos = alternados.filter((l) => l.canal < 0);
      if (canais.length) {
        //: «Senoides», e não «Canais do relé» (escolha dele): o bloco seguinte
        //: — «Outros sinais» — também é feito de canais do relé, e os dois
        //: títulos juntos diziam que um era do relé e o outro não. O que
        //: separa os dois é a FORMA da onda: aqui está o que passou no teste
        //: de alternado (ver `alternados` em `analysis/presenca.py`).
        blocos.push({ chave: "senoidais", titulo: "Senoides",
                      icone: "seno",
                      dica: "Canais do relé em que a onda é alternada: é "
                          + "destes que sai fasor, eficaz e espectro.",
                      secoes: [{ linhas: canais }] });
      }
      //: «Outros sinais» entra AQUI, e não no fim: ele é canal do relé como as
      //: senoides, e o que vem depois dele já é conta nossa. A ordem da tela é
      //: a da procedência — primeiro o que o relé gravou (alternado e não
      //: alternado), depois o que nós deduzimos, por último o que o usuário
      //: escreveu. Escolha dele.
      if (outros.length) {
        blocos.push(blocoDosOutros(outros));
        outrosJaEntrou = true;
      }
      if (nossos.length) {
        blocos.push({ chave: "calculados", titulo: "Calculados pelo OscLab",
                      icone: "calculado",
                      dica: "Resíduo e componentes simétricas, deduzidos dos "
                          + "canais acima. Dependem de quais três canais "
                          + "formam cada grupo — confira em «editar grupos» "
                          + "antes de confiar.",
                      secoes: [{ linhas: nossos }] });
      }
      if (doUsuario.length) {
        blocos.push({ chave: "minhas-contas", titulo: "Suas contas",
                      icone: "calculado",
                      dica: "As expressões que você escreveu.",
                      secoes: [{ linhas: doUsuario }] });
      }
    }
    if (outros.length && !outrosJaEntrou) {
      blocos.push(blocoDosOutros(outros));
    }
    return blocos;
  }

  //: Os blocos que o usuário recolheu, por chave. Vive fora da janelinha para
  //: sobreviver ao fechar e reabrir: quem recolheu «outros sinais» não quer
  //: revê-lo aberto no próximo clique em «+ sinal».
  //:
  //: O padrão é por BLOCO, não por gosto: em «grupo trifásico» os grupos abrem
  //: e o resto vem recolhido, porque o que se procura ali é o vão do evento —
  //: os avulsos e os outros sinais são o que sobra, e sobra não precisa ocupar
  //: a tela. Em «lista» abrem os senoidais e os calculados, que é a tela toda.
  const blocosRecolhidos = new Set();
  const naoMexidos = new Set();

  function estaRecolhido(bloco, silenciosoRecolhido = true) {
    if (!naoMexidos.has(bloco.chave)) {
      naoMexidos.add(bloco.chave);
      if (bloco.recolhido || (bloco.silencioso && silenciosoRecolhido)) {
        blocosRecolhidos.add(bloco.chave);
      }
    }
    return blocosRecolhidos.has(bloco.chave);
  }

  /** Por que esta conta não existe para esta linha — o texto do risquinho.
   *
   * O risquinho é diferente de caixinha desmarcada, e a diferença tem que ser
   * dizível: desmarcada é «não quero ver», risquinho é «não existe». Toda vez
   * que ele aparece há um motivo, e ele está aqui.
   */
  function motivoDaAusencia(linha, chave) {
    if (linha.bloco === "outros") {
      return linha.motivo
        ? `${linha.motivo} — só a onda do arquivo, então.`
        : "não dá para tirar fasor deste canal.";
    }
    if (linha.bloco === "sequencia") {
      return "componente simétrica é fasor, e fasor não tem valor instantâneo: "
           + "ela só existe em eficaz.";
    }
    if (chave === "bruto.dc" && linha.canal < 0
        && linha.bloco !== "alternado") {
      return "a contínua só existe no bruto.";
    }
    if (filtroTravado()) {
      return "a gravação já vem filtrada do relé: as amostras SÃO a "
           + `componente de ${frequenciaDoRegistro()}, então não há o que `
           + "filtrar de novo, nem harmônico para o eficaz incluir, nem "
           + "contínua que tenha sobrado.";
    }
    return "esta conta não existe para este sinal.";
  }

  /** O catálogo de um diagrama FASORIAL: uma linha, uma caixinha.
   *
   * A matriz de contas não existe aqui, e não deve existir: `IAW`,
   * `IAW · RMS` e `IAW · 60Hz RMS` têm o MESMO fasor, e cinco colunas
   * ofereceriam cinco caminhos para a mesma seta. O que o diagrama mostra é a
   * linha — e entram só as que têm fasor de 60 Hz: canal senoidal, resíduo de
   * um grupo e componente de sequência.
   */
  /** Os sinais do registro de que se pode tirar fasor de 60 Hz.
   *
   * Uma entrada por LINHA do catálogo, representada pelo sinal-base dela: o
   * canal cru, o resíduo instantâneo, a componente. `IAW`, `IAW · RMS` e
   * `IAW · 60Hz RMS` têm o MESMO fasor — oferecer os três seria oferecer três
   * caminhos para a mesma seta.
   *
   * Serve ao «+ sinal» do diagrama e à escolha da referência, que é a mesma
   * pergunta feita duas vezes: de que sinais este diagrama pode falar.
   */
  function comFasor() {
    const saida = [];
    const vistas = new Set();
    for (const x of (dados.catalogo || [])) {
      const base = x.canal >= 0
        ? x.id === `c${x.canal}:instantaneo`
        : (x.id.endsWith(":n:instantaneo") || x.bloco === "sequencia");
      if (!base || x.bloco === "outros" || vistas.has(x.linha || x.nome)) continue;
      vistas.add(x.linha || x.nome);
      saida.push(x);
    }
    return saida;
  }

  /** Os sinais que têm ONDA de onde tirar espectro: canal e resíduo.
   *
   * Componente simétrica fica de fora — ver `plot/harmonicos.py`: Fortescue é
   * definido sobre fasores de UMA frequência, e não existe "5º harmônico do
   * I1" a partir do número que o painel tem.
   */
  function comEspectro() {
    return comFasor().filter(
      (x) => x.canal >= 0 || x.id.endsWith(":n:instantaneo"));
  }

  /** O nome de um sinal pelo id, como ele aparece no diagrama. */
  /** Faixa sim, faixa não — a alternância das listas de sinais.
   *
   * Contada DENTRO de cada bloco, e não na lista inteira: entre um bloco e
   * outro há um cabeçalho, e contar por cima dele faria o primeiro sinal de um
   * bloco aparecer aceso e o do seguinte apagado, sem regra nenhuma visível.
   */
  const emFaixa = (el, i) => {
    if (i % 2 === 0) el.classList.add("faixa");
    return el;
  };

  function nomeDoSinal(id) {
    const x = (dados.catalogo || []).find((y) => y.id === id);
    return x ? (x.linha || x.nome) : "";
  }

  //: Os blocos do catálogo do fasorial, na ordem. São os dois do «agrupar por
  //: lista» do catálogo analógico: o que o relé gravou e o que o OscLab
  //: contou. Não há «Outros sinais» — ver `comFasor`.
  const BLOCOS_DO_FASORIAL = [
    ["senoidais", "Senoides", "seno",
     "Canais do arquivo em que o programa mediu onda alternada: é deles que "
     + "sai fasor."],
    ["calculados", "Calculados pelo OscLab", "calculado",
     "O que o OscLab contou a partir dos canais: o resíduo e as componentes "
     + "simétricas da trinca."],
  ];

  function abrirCatalogoFasorial(painel) {
    abrirCatalogoDeSinais(painel, {
      //: Só aqui: no fasorial o que entra no diagrama é a componente de 60 Hz
      //: do canal, e a marca diz isso com a mesma cor que a legenda do
      //: gráfico usa. Nos harmônicos seria mentira — lá o assunto é o
      //: espectro inteiro.
      marca60: true,
      candidatos: comFasor(),
      vazio: "Nenhum sinal com fasor e esse nome fora do diagrama.",
      cheio: "Todos os sinais com fasor já estão aqui.",
    });
  }

  /** O catálogo dos painéis que escolhem sinal por LINHA — fasorial e
   * harmônicos. O que muda entre eles é só a lista de candidatos.
   */
  function abrirCatalogoDeSinais(painel, opcoes) {
    const meu = painelPorId(painel.id);
    const escolhidos = new Set(meu ? meu.sinais : []);
    const janelinha = criar("dialog", "busca catalogo fasorial");

    const campo = document.createElement("input");
    campo.type = "search";
    campo.placeholder = "procurar sinal pelo nome…";
    const lista = criar("div", "achados");

    const candidatos = opcoes.candidatos;

    /* Esconder os sinais nulos, que é o padrão — a MESMA caixa do outro
     * catálogo, e a mesma preferência guardada: um SEL-487E com três terminais
     * de TC livres rende três trincas que nunca vão ter dado, e elas empurram
     * para fora da vista as que têm.
     *
     * Esconder vale só para o que está FORA do diagrama: uma linha dessas que
     * o usuário já pôs continua listada e marcada, senão o «mostrar na tela» a
     * apagaria sem ele ver. */
    const temMudo = candidatos.some((x) => x.sem_sinal);
    let ocultarMudos = lerGuardado("osclab:catalogo:sem-sinal",
                                   ["1", "0"], "1") === "1";
    const caixaMudos = criar("label", "peneira");
    const marcaMudos = document.createElement("input");
    marcaMudos.type = "checkbox";
    marcaMudos.checked = ocultarMudos;
    marcaMudos.addEventListener("change", () => {
      ocultarMudos = marcaMudos.checked;
      guardar("osclab:catalogo:sem-sinal", ocultarMudos ? "1" : "0");
      desenharLista();
    });
    caixaMudos.append(marcaMudos, criar("span", null, "ocultar sinais nulos"));
    caixaMudos.title = "Sinais que saem de entradas do relé que ninguém "
      + "cabeou — elas leem só o ruído do conversor. Desmarque para conferir "
      + "que estão mesmo abertas: eles voltam à ordem do arquivo, marcados "
      + "«sem sinal».";
    caixaMudos.hidden = !temMudo;
    const barra = criar("div", "barra-do-catalogo");
    barra.append(caixaMudos);

    /** O painel como ele VAI ficar: o desenhado mais o recém-marcado.
     *
     * A cor de um sinal se resolve contra os VIZINHOS dele no painel, então
     * perguntar a cor de quem ainda não entrou devolveria cinza. A fase sai
     * do nome do canal (`IAW` → A), como sai no painel desenhado.
     */
    const previsto = () => {
      const jaTem = new Set((painel.sinais || []).map((x) => x.id));
      const novos = candidatos
        .filter((x) => escolhidos.has(x.id) && !jaTem.has(x.id))
        .map((x) => {
          const letra = (x.fundamental || "").slice(-1).toUpperCase();
          return { id: x.id,
                   fase: "ABCN".includes(letra) && letra ? letra : "" };
        });
      return { id: painel.id, sinais: [...(painel.sinais || []), ...novos] };
    };

    const desenharLista = () => {
      const procura = campo.value.trim().toUpperCase();
      const cabe = (x) => !procura
        || combinaNome(x.linha || x.nome, procura);
      const fora = candidatos
        .filter((x) => !escolhidos.has(x.id))
        .filter((x) => !(ocultarMudos && x.sem_sinal))
        .filter(cabe);
      const naTela = candidatos.filter((x) => escolhidos.has(x.id));

      const desenhar = (x, naTela) => {
        const item = criar("label", "achado");
        const marca = document.createElement("input");
        marca.type = "checkbox";
        marca.checked = escolhidos.has(x.id);
        marca.addEventListener("change", () => {
          if (marca.checked) escolhidos.add(x.id);
          else escolhidos.delete(x.id);
          // Refaz a lista na hora: o sinal marcado desce para «já na tela» e
          // ganha a bolinha da cor, que é a confirmação de que ele entrou.
          // No quadro seguinte, e não aqui dentro: trocar os filhos no meio do
          // `change` arranca do DOM o próprio `<label>` que está despachando o
          // clique. E a rolagem é guardada — a lista some de baixo do dedo se
          // ela voltar ao topo a cada caixinha.
          const onde = lista.scrollTop;
          requestAnimationFrame(() => { desenharLista(); lista.scrollTop = onde; });
        });
        item.append(marca);
        // A cor do traço, e só para quem JÁ está no diagrama — igual ao outro
        // catálogo. Fora dele o sinal ainda não tem cor: ela se resolve contra
        // os vizinhos do painel, e quem não entrou ainda não é vizinho de
        // ninguém. Uma bolinha cinza ali diria «esta é a cor», e seria mentira.
        if (naTela) item.append(caixaDeCor(previsto(), x));
        else item.append(criar("span", "vaga-da-cor"));
        // O que é conta NOSSA — `IN G1`, `3I0 G1` — sai na cor dos calculados,
        // a mesma do outro catálogo e do gráfico analógico. A cor nomeia a
        // FAMÍLIA: ali o sinal ainda não tem cor de traço.
        const nome = criar("span", "nome-da-linha"
                           + (x.canal < 0 ? " calculado" : ""));
        nomeComGrupo(nome, x.linha || x.nome, x.canal < 0 ? x.grupo : "");
        //: A marca e a unidade entram DENTRO do invólucro do nome, e não
        //: soltas na linha: o invólucro é quem tem o `flex: 1`, e fora dele a
        //: unidade era empurrada para a borda da janela, longe do nome a que
        //: pertence. No catálogo analógico ela sempre esteve colada no nome.
        if (opcoes.marca60 && x.canal >= 0) {
          //: No MESMO formato das marcas do nome desenhado (ver
          //: `escreverNome`): `<sub class="marca-do-nome marca-hz">`, turquesa.
          //:
          //: E DENTRO do `.nome`, não ao lado dele: `.nome-da-linha` é uma
          //: caixa flex com `gap`, e pendurada ali a marca virava um item
          //: separado — saía `IAW · 60Hz · A`, com respiro, em vez de colada
          //: no nome como na legenda do gráfico. É o mesmo lugar em que
          //: `escreverNome` a põe.
          const marca = criar("sub", "marca-do-nome", "60Hz");
          marca.classList.add("marca-hz");
          (nome.querySelector(".nome") || nome).append(marca);
        }
        nome.append(criar("span", "unidade-da-linha",
                          x.unidade_mostrada || x.unidade));
        item.append(nome);
        if (x.sem_sinal) {
          const etiqueta = criar("span", "etiqueta", "sem sinal");
          etiqueta.title = "A entrada do relé não está cabeada: este canal lê "
                         + "só o ruído do conversor.";
          item.append(etiqueta);
        }
        return item;
      };

      // Os MESMOS blocos do catálogo analógico, e o símbolo da família no
      // cabeçalho de cada um — não repetido em cada linha. A pergunta «isto é
      // canal ou é conta nossa?» se responde uma vez, quando o olho passa
      // pelo cabeçalho; vinte ícones iguais seriam vinte vezes o mesmo aviso.
      //
      // Não há bloco «Outros sinais» aqui porque `comFasor` não traz canal de
      // `outros`: deles não sai fasor nenhum, e um diagrama fasorial é só o
      // que tem fasor.
      const nos = [];
      for (const [chave, titulo, icone, dica] of BLOCOS_DO_FASORIAL) {
        const dele = fora.filter((x) => (chave === "calculados") === (x.canal < 0));
        if (!dele.length) continue;
        const bloco = { chave: `fasorial:${chave}`, titulo, icone, dica };
        const recolhido = estaRecolhido(bloco);
        nos.push(cabecaDoBloco(bloco, dele.length, recolhido));
        if (!recolhido) nos.push(...dele.map((x, i) => emFaixa(desenhar(x, false), i)));
      }
      if (!fora.length) {
        nos.push(criar("p", "vazio", procura ? opcoes.vazio : opcoes.cheio));
      }
      //: O pé da janela, com a MESMA forma e as MESMAS palavras do catálogo
      //: analógico — «já no gráfico», a régua ao lado e, nas linhas, a cor do
      //: traço. Era «já na tela» e sem a régua: a mesma ideia escrita de dois
      //: jeitos em duas janelas que fazem a mesma coisa.
      if (naTela.length) {
        const divisor = criar("div", "divisor-da-tela");
        divisor.append(criar("span", null,
                             `já no gráfico (${naTela.length}) — desmarque `
                             + "para tirar"));
        divisor.append(criar("span", "regua"));
        nos.push(divisor);
        nos.push(...naTela.map((x, i) => emFaixa(desenhar(x, true), i)));
      }
      lista.replaceChildren(...nos);
    };

    /** O cabeçalho de um bloco: a setinha, o símbolo, o título e a contagem.
     *
     * Um BOTÃO, e não um div que escuta clique — dobrar um bloco é ação, e
     * ação tem que chegar pelo teclado. Mesma forma do catálogo analógico.
     */
    function cabecaDoBloco(bloco, quantas, recolhido) {
      const cabeca = criar("div", "cabeca-de-bloco");
      const dobrar = criar("button", "dobrar-bloco");
      dobrar.type = "button";
      dobrar.setAttribute("aria-expanded", String(!recolhido));
      dobrar.append(criar("span", "seta-da-dobra", recolhido ? "▸" : "▾"));
      dobrar.append(bloco.icone === "calculado"
                    ? iconeDoCalculado()
                    : iconeDeTraco(DESENHO_DO_SENO, "icone-alternado"));
      dobrar.append(criar("span", "titulo-do-bloco", bloco.titulo));
      dobrar.append(criar("span", "quantas-linhas", `(${quantas})`));
      if (bloco.dica) dobrar.title = bloco.dica;
      dobrar.addEventListener("click", () => {
        if (blocosRecolhidos.has(bloco.chave)) blocosRecolhidos.delete(bloco.chave);
        else blocosRecolhidos.add(bloco.chave);
        desenharLista();
      });
      cabeca.append(dobrar);
      return cabeca;
    }

    campo.addEventListener("input", desenharLista);
    desenharLista();

    const aplicar = criar("button", "aceitar", "mostrar na tela");
    aplicar.addEventListener("click", () => {
      const ids = candidatos.filter((x) => escolhidos.has(x.id)).map((x) => x.id);
      janelinha.close();
      trocarSinais(painel.id, ids);
    });

    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem mudar a tela";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());

    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, `Sinais de ${painel.nome}`), campo, fechar);
    janelinha.append(cabeca, barra, lista, aplicar);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
    campo.focus();
  }

  /** O catálogo: o que se pode pôr NESTE painel.
   *
   * Uma lista só, e a origem do número dita pela COLUNA: `onda` é o canal como
   * o relé gravou; `RMS`, `DC` e as duas de 60 Hz são contas nossas. Já foram
   * duas abas, `IED` e `OscLab`, e a separação saiu porque cobrava duas telas
   * para dizer o que o cabeçalho de uma coluna diz uma vez — e porque ver o
   * canal e as contas dele na MESMA linha é a leitura que se faz.
   *
   * O que o OscLab calculou não ganha cor nem etiqueta: está dito no nome (o
   * `·` só existe em conta nossa), na coluna e no bloco. Cor aqui seria a
   * quarta vez, e cor nesta tela é do TRAÇO — para quem está fora do gráfico
   * ela ainda não foi decidida.
   */
  function abrirCatalogo(painel, iedPedido) {
    // Os ids vêm do ARRANJO da tela; `painel.sinais` da resposta é a lista de
    // sinais DESENHADOS, com série e escala dentro — outra coisa.
    const meu = painelPorId(painel.id);
    const escolhidos = new Set(meu ? meu.sinais : []);
    // Com mais de um IED na aba, a lista é de UM deles por vez: uma aba por
    // IED no alto da janela. O que já está no gráfico continua valendo.
    const iedDaLista = variosIeds() ? (iedPedido || "A") : null;
    const daAba = (lista) => (iedDaLista
      ? lista.filter((x) => (x.ied || "A") === iedDaLista) : lista);
    const janelinha = criar("dialog", "busca catalogo");
    // De que painel esta janela é — para poder ser refeita no lugar quando o
    // catálogo muda debaixo dela. Ver `gravarVinculo`.
    janelinha.dataset.painel = String(painel.id);

    /* O SINAL QUE O GRÁFICO DESENHA, que com o filtro aceso não é o escolhido.
     *
     * O botão do filtro é do registro inteiro: com ele aceso, `IAW` desenha
     * `IAW · 60Hz` e `IAW · RMS` desenha `IAW · 60Hz RMS`. Enquanto esta tela
     * marcava a caixinha do sinal ESCOLHIDO, ela mostrava a marca numa coluna
     * do bruto enquanto a legenda do gráfico escrevia `60Hz` — e no modo
     * tradicional, que não mostra as colunas do bruto, o canal que estava na
     * tela aparecia sem marca nenhuma.
     *
     * Quem faz a conta é o servidor (`catalogo.efetivo`), e ela vem pronta no
     * campo `efetivo` de cada sinal: repeti-la aqui seria a mesma regra em
     * dois lugares, que é como o gráfico e a lista passam a discordar. */
    const doCatalogo = new Map((dados.catalogo || []).map((x) => [x.id, x]));
    // A medida é de cada gráfico: num painel em RMS, `IAW` desenha o eficaz.
    const medidaDoPainel = (meu && meu.medida) || "instantaneo";
    const desenhadoDe = (id) => {
      const x = doCatalogo.get(id);
      return (x && x.efetivo && x.efetivo[medidaDoPainel]) || id;
    };
    const desenhados = () => new Set([...escolhidos].map(desenhadoDe));

    /* Qual sinal a célula PEDE quando é marcada.
     *
     * Com o filtro aceso, a célula «onda» do grupo filtrado de `IAW` é o
     * caminho do CANAL: marcá-la põe `IAW` no gráfico, e apagar o filtro leva
     * aquele traço de volta à onda crua junto com o resto da tela. Pedir o
     * `IAW · 60Hz` ali prenderia aquele traço no filtrado — um sinal que não
     * obedece ao botão do cabeçalho, bem no modo em que todos obedecem.
     *
     * Com o filtro apagado nada é empurrado, o laço não acha outro candidato,
     * e cada célula pede o próprio sinal — que é como se escolhe `IAW · 60Hz`
     * ao lado de `IAW` para comparar os dois. */
    const pedidoDaCela = (linha, sinal) => {
      for (const y of linha.contas.values()) {
        if (y.id !== sinal.id && desenhadoDe(y.id) === sinal.id) return y.id;
      }
      return sinal.id;
    };

    let modo = lerGuardado("osclab:catalogo:agrupar",
                           AGRUPAMENTOS.map(([c]) => c), "lista");
    /** As colunas que esta tela mostra.
     *
     * Duas peneiras, nesta ordem. A primeira é o MODO: no `tradicional` só as
     * do filtrado. A segunda é o REGISTRO: coluna que nenhum sinal deste
     * arquivo tem não entra — num `.CEV` não existe bruto nenhum, e três
     * colunas de risquinho não dizem mais do que a ausência delas.
     *
     * Se as duas peneiras juntas não deixarem coluna alguma — um arquivo em
     * que nada é senoidal, aberto no `tradicional` —, valem as que o registro
     * tem: uma tela vazia seria pior que uma tela fora do modo pedido.
     */
    const colunasDaVisao = () => {
      const existe = new Set((dados.catalogo || []).map((x) => x.coluna));
      const noRegistro = COLUNAS_DO_CATALOGO.filter(([c]) => existe.has(c));
      if (visaoDeAnalise === "avancado") return noRegistro;
      const doModo = noRegistro.filter(([c]) => c.startsWith("filtrado."));
      return doModo.length ? doModo : noRegistro;
    };

    const campo = document.createElement("input");
    campo.type = "search";
    campo.placeholder = "procurar sinal pelo nome…";
    const lista = criar("div", "matriz-do-catalogo");

    // A barra do «agrupar por», mais os dois botões que abrem outra tela.
    const barra = criar("div", "barra-do-catalogo");
    const botaoDoModo = criar("button", "chave", "");
    botaoDoModo.type = "button";
    botaoDoModo.setAttribute("aria-haspopup", "true");
    botaoDoModo.setAttribute("aria-expanded", "false");
    const ancoraDoModo = criar("span", null);
    ancoraDoModo.id = "menu-do-agrupar";
    const marcarModo = () => {
      const qual = AGRUPAMENTOS.find(([c]) => c === modo) || AGRUPAMENTOS[0];
      botaoDoModo.replaceChildren(criar("span", null, qual[1]),
                                  criar("span", "seta-do-menu", "▾"));
      botaoDoModo.title = `Agrupando por ${qual[1]}: ${qual[2]}. Clique para `
                        + "trocar.";
    };
    botaoDoModo.addEventListener("click", () => {
      menuSuspenso("menu-do-agrupar", "agrupar por:", (caixa) => {
        for (const [chave, rotulo, explicacao] of AGRUPAMENTOS) {
          const opcao = criar("label", "opcao");
          const marca = document.createElement("input");
          marca.type = "radio";
          marca.name = "catalogo-agrupar";
          marca.checked = chave === modo;
          marca.addEventListener("change", () => {
            modo = chave;
            guardar("osclab:catalogo:agrupar", chave);
            marcarModo();
            desenharLista();
          });
          opcao.title = explicacao;
          opcao.append(marca, criar("span", null, rotulo));
          caixa.append(opcao);
        }
      });
    });

    const verGrupos = criar("button", "chave", "");
    verGrupos.type = "button";
    verGrupos.append(iconeTrifasico(), criar("span", null, "editar grupos"));
    verGrupos.title = "Quais três canais formam cada grupo trifásico. O "
                    + "OscLab deduz isso do NOME dos canais, e nome de canal "
                    + "cada fabricante escreve como quer — quando erra, o "
                    + "resíduo e as componentes daquele grupo erram junto, na "
                    + "unidade certa e sem aviso.";
    verGrupos.addEventListener("click", () => abrirGrupos());

    const verCanais = criar("button", "chave", "canais");
    verCanais.type = "button";
    verCanais.title = "Todos os canais como estão no arquivo, com a fase e o "
                    + "grupo que o OscLab deduziu de cada um — nada calculado. "
                    + "É onde se confere a dedução antes de confiar nas contas.";
    verCanais.addEventListener("click", () => abrirCanais());

    // A peneira dos nulos entra AQUI, na barra, e não numa linha própria: ela
    // é um ajuste da lista, como o «agrupar por» — e uma linha inteira para
    // uma caixinha é uma linha a menos de sinal na janela.
    const lugarDaPeneira = criar("span", null);
    // Sem «nova conta» aqui. A calculadora já tem o botão dela no CABEÇALHO
    // do gráfico, ao lado de «+ sinal» — dois caminhos para a mesma janela,
    // um deles escondido atrás de outra janela, é um a mais. Esta tela é de
    // ESCOLHER o que ver; criar sinal é outra coisa.
    barra.append(criar("span", "rotulo-da-barra", "Agrupar por:"),
                 botaoDoModo, ancoraDoModo, lugarDaPeneira,
                 criar("span", "empurra"), verGrupos, verCanais);
    marcarModo();

    /* Esconder os sinais nulos, que é o padrão.
     *
     * Um SEL-487E com três terminais de TC livres rende três trincas que nunca
     * vão ter dado, e elas empurram para fora da vista as que têm. A caixinha
     * só aparece quando há canal sem sinal no registro — um controle que nunca
     * muda nada é ruído.
     *
     * Esconder vale só para o que está FORA do gráfico: uma linha dessas que o
     * usuário já pôs na tela continua listada e marcada, senão o «mostrar na
     * tela» a apagaria sem ele ver. */
    const temMudo = daAba(dados.catalogo || []).some((x) => x.sem_sinal);
    let ocultarMudos = lerGuardado("osclab:catalogo:sem-sinal",
                                   ["1", "0"], "1") === "1";
    const caixaMudos = criar("label", "peneira");
    const marcaMudos = document.createElement("input");
    marcaMudos.type = "checkbox";
    marcaMudos.checked = ocultarMudos;
    marcaMudos.addEventListener("change", () => {
      ocultarMudos = marcaMudos.checked;
      guardar("osclab:catalogo:sem-sinal", ocultarMudos ? "1" : "0");
      // A caixinha manda nos grupos silenciosos: marcada, eles ficam
      // recolhidos no fim; desmarcada, abrem. Sem isto, desmarcar «ocultar
      // sinais nulos» não mostraria nada em «grupo trifásico» — os canais
      // deles estão dentro de um bloco fechado.
      for (const grupo of gruposSilenciosos(
             linhasDoCatalogo(daAba(dados.catalogo || [])))) {
        const chave = `grupo:${grupo}`;
        naoMexidos.add(chave);
        if (ocultarMudos) blocosRecolhidos.add(chave);
        else blocosRecolhidos.delete(chave);
      }
      desenharLista();
    });
    caixaMudos.title = "Sinais que saem de entradas do relé que ninguém "
      + "cabeou — elas leem só o ruído do conversor. Desmarque para conferir "
      + "que estão mesmo abertas: eles voltam ao lugar deles, no grupo ou na "
      + "ordem do arquivo, marcados «sem sinal».";
    caixaMudos.append(marcaMudos, criar("span", null,
                                        "ocultar sinais nulos"));
    caixaMudos.hidden = !temMudo;
    lugarDaPeneira.replaceWith(caixaMudos);

    const rotuloDaColuna = (texto) =>
      texto.replace("{f}", frequenciaDoRegistro());

    //: As caixinhas de cada sinal, por id. O mesmo sinal aparece em dois
    //: lugares — a célula da matriz e a linha do pé, que lista o que já está
    //: no gráfico —, e duas caixinhas dizendo coisas diferentes sobre o mesmo
    //: sinal é pior que não ter a segunda.
    //: As caixinhas são do sinal DESENHADO, e `escolhidos` guarda o PEDIDO:
    //: com o filtro aceso os dois não são o mesmo, e desmarcar tem que tirar
    //: da tela o que quer que esteja desenhando aquela curva — inclusive dois
    //: pedidos diferentes que caíram no mesmo traço.
    const caixasPorId = new Map();
    const marcar = (pedido, desenhado, ligado) => {
      if (ligado) {
        escolhidos.add(pedido);
      } else {
        for (const x of [...escolhidos]) {
          if (desenhadoDe(x) === desenhado) escolhidos.delete(x);
        }
      }
      for (const caixa of caixasPorId.get(desenhado) || []) {
        caixa.checked = ligado;
      }
      desenharPeDaTela();
    };
    const esquecerCaixas = () => {
      for (const [id, caixas] of caixasPorId) {
        caixasPorId.set(id, caixas.filter((c) => c.isConnected));
      }
    };

    const caixaDoSinal = (sinal, pedido) => {
      const quem = pedido || sinal.id;
      const marca = document.createElement("input");
      marca.type = "checkbox";
      marca.checked = desenhados().has(sinal.id);
      marca.setAttribute("aria-label", sinal.nome);
      marca.title = `${sinal.nome} — ${sinal.descricao}`;
      marca.addEventListener("change",
                             () => marcar(quem, sinal.id, marca.checked));
      if (!caixasPorId.has(sinal.id)) caixasPorId.set(sinal.id, []);
      caixasPorId.get(sinal.id).push(marca);
      return marca;
    };

    const desenharLista = () => {
      const procura = campo.value.trim().toUpperCase();
      const todas = linhasDoCatalogo(daAba(dados.catalogo || []));
      const silenciosos = gruposSilenciosos(todas);
      const chavesVisiveis = colunasDaVisao().map(([chave]) => chave);
      const visiveis = todas.filter((l) => {
        // Sem nenhuma conta na vista atual, a linha seria uma fileira de
        // risquinhos — que é o que este modo veio evitar. Ela volta no
        // «avançado», que é onde as contas dela moram.
        if (!chavesVisiveis.some((c) => l.contas.has(c))) return false;
        const naTela = [...l.contas.values()].some((x) => escolhidos.has(x.id));
        // «Ocultar sinais nulos» oculta em TODOS os modos de agrupamento.
        //
        // Havia uma exceção aqui: em «grupo trifásico» a trinca inteiramente
        // muda ficava, como um cabeçalho recolhido no fim, para a numeração
        // não parecer ter buraco (`G1`, `G3`, sem `G2`). A exceção caiu — o
        // Alexandre pediu, e com razão: a caixinha é a explicação do buraco, e
        // quem a marcou acabou de dizer que não quer ver canal nulo. Deixar um
        // cabeçalho dizendo «SEM SINAL» logo depois de pedir para escondê-los
        // é a tela discutindo com o usuário.
        //
        // A volta continua a um clique — a mesma caixinha —, e o cabeçalho da
        // página também avisa («6 canais sem sinal · mostrar»).
        if (ocultarMudos && l.sem_sinal && !naTela) return false;
        if (!procura) return true;
        return combinaNome(l.nome, procura)
            || combinaNome(l.origem || "", procura)
            || [...l.contas.values()].some((x) => combinaNome(x.nome, procura));
      });

      lista.replaceChildren();
      caixasPorId.clear();
      if (!visiveis.length) {
        lista.append(criar("p", "vazio", procura
          ? "Nada com esse nome neste registro."
          : "Este registro não tem sinal nenhum a acrescentar."));
        return;
      }

      for (const bloco of blocosDoCatalogo(visiveis, modo, silenciosos)) {
        const quantas = bloco.secoes.reduce((n, s) => n + s.linhas.length, 0);
        // O grupo trifásico vai num QUADRO próprio: ele não é uma seção da
        // lista, é um objeto — tem nome, tem canais, edita-se, e o que sai
        // dele mora dentro dele. O resto são seções mesmo, e seção não precisa
        // de moldura.
        const ehGrupo = (bloco.chave || "").startsWith("grupo:");
        const caixa = ehGrupo
          ? criar("div", `bloco-do-grupo${bloco.silencioso ? " silencioso" : ""}`)
          : lista;
        caixa.append(cabecaDeBloco(bloco, quantas));
        if (!estaRecolhido(bloco, ocultarMudos)) {
          //: A faixa alternada conta de um bloco só, e atravessa as seções
          //: dele: as seções não têm cabeçalho visível, então reiniciar a
          //: contagem em cada uma quebraria a alternância no meio da lista
          //: sem nada na tela explicando o pulo.
          let i = 0;
          for (const secao of bloco.secoes) {
            for (const l of secao.linhas) desenharLinha(l, caixa, i++);
          }
        }
        if (ehGrupo) lista.append(caixa);
      }

      desenharPeDaTela();
      //: Encosta as barras de energia na grade de pixels da tela. Depois de
      //: montar, porque antes não há o que medir — e com a rolagem ligada, que
      //: é o que muda a fração de pixel de todas elas ao mesmo tempo.
      //: Num quadro à parte: dentro do mesmo, o layout ainda não assentou —
      //: e foi isso que fez a primeira versão medir posições que o navegador
      //: ainda ia mudar, e sair sem efeito nenhum.
      requestAnimationFrame(() => alinharBarras(lista));
      seguirRolagemDasBarras(lista);
    };

    /** O painel como ele VAI ficar: o que já está desenhado mais o que se
     * acabou de marcar.
     *
     * Sem isto, a bolinha de um sinal recém-marcado saía cinza — não por
     * escolha, mas porque a cor dele ainda não existia: ela se resolve contra
     * os VIZINHOS do painel, e ele ainda não era vizinho de ninguém. Cinza ali
     * dizia «esta é a cor», e a cor verdadeira só aparecia depois de aplicar.
     *
     * A fase sai do vínculo do canal (`IA` → A), que é de onde ela sai no
     * painel desenhado também. Sinal calculado não tem fase, e é isso que o
     * manda para as cores neutras — ver `coresDoPainel`.
     */
    const painelPrevisto = () => {
      const jaTem = new Set((painel.sinais || []).map((x) => x.id));
      const novos = (dados.catalogo || [])
        .filter((x) => escolhidos.has(x.id) && !jaTem.has(x.id))
        .map((x) => {
          const letra = (x.fundamental || "").slice(-1).toUpperCase();
          return { id: x.id,
                   fase: "ABCN".includes(letra) && letra ? letra : "" };
        });
      return { id: painel.id, sinais: [...(painel.sinais || []), ...novos] };
    };

    //: Os nós do pé da lista, para poder refazer SÓ eles. Marcar uma caixinha
    //: tem que fazer o sinal aparecer aqui na hora — mas redesenhar a matriz
    //: inteira a cada clique tiraria a linha de debaixo do mouse e mandaria a
    //: rolagem de volta ao topo no meio da escolha.
    let nosDoPe = [];

    /** O que JÁ está no gráfico, no pé da lista.
     *
     * A matriz diz o que se pode acrescentar e marca o que está lá; esta parte
     * responde outra pergunta — «o que eu já pus?» — e responde de uma vez,
     * sem obrigar a varrer cento e vinte caixinhas procurando as marcadas.
     *
     * É aqui que mora a cor: o sinal já está desenhado, então a cor já existe,
     * e é esta a tela de trocá-la. Desmarcar aqui tira da tela.
     */
    const desenharPeDaTela = () => {
      for (const no of nosDoPe) no.remove();
      nosDoPe = [];
      esquecerCaixas();
      // O pé lista o que o gráfico DESENHA, com o nome que a legenda escreve
      // (`IAW · 60Hz`, e não `IAW`). Dois pedidos que caíram no mesmo traço
      // são uma linha só — o servidor também só desenha um. A cor continua
      // sendo do PEDIDO, que é por onde o painel a guarda.
      const pedidoDoTraco = new Map();
      for (const x of dados.catalogo || []) {
        if (!escolhidos.has(x.id)) continue;
        const traco = desenhadoDe(x.id);
        if (!pedidoDoTraco.has(traco)) pedidoDoTraco.set(traco, x.id);
      }
      const naTela = (dados.catalogo || []).filter((x) => pedidoDoTraco.has(x.id));
      if (!naTela.length) return;
      const previsto = painelPrevisto();
      const divisor = criar("div", "divisor-da-tela");
      divisor.append(criar("span", null,
                           `já no gráfico (${naTela.length}) — desmarque `
                           + "para tirar"));
      divisor.append(criar("span", "regua"));
      nosDoPe.push(divisor);
      for (const x of naTela) {
        const linha = criar("div", "linha-na-tela");
        const pedido = pedidoDoTraco.get(x.id);
        linha.append(caixaDoSinal(x, pedido),
                     caixaDeCor(previsto, { ...x, id: pedido }));
        nomeComGrupo(linha, x.nome, x.grupo);
        if (x.origem && x.canal < 0) {
          const origem = criar("span", "origem-do-sinal", x.origem);
          origem.title = `Sai dos canais ${x.origem}, como estão no arquivo.`;
          linha.append(origem);
        }
        nosDoPe.push(linha);
      }
      lista.append(...nosDoPe);
    };

    const celaDoCabecalho = (rotulo, dica, classe) => {
      const cela = criar("div", `cabeca-de-coluna ${classe}`);
      cela.append(criar("span", null, rotulo));
      if (dica) cela.title = dica;
      return cela;
    };

    //: O ⓘ da coluna de 60 Hz: qual filtro produziu aqueles números. Um só,
    //: no cabeçalho, porque a resposta é a mesma para todas as linhas — e
    //: porque vinte e um ícones seriam vinte e uma vezes o mesmo aviso.
    const informacaoDoFiltro = () => {
      const qual = (FILTROS.find(([c]) => c === filtroEscolhido) || FILTROS[0]);
      const marca = criar("button", "informacao", "i");
      marca.type = "button";
      marca.setAttribute("aria-label", "qual filtro produz estes sinais");
      marca.title = `Filtro ${qual[1]}: ${qual[2]} Trocar o filtro no `
                  + "cabeçalho troca estes números e as componentes de "
                  + "sequência de uma vez.";
      marca.addEventListener("click", (evento) => {
        evento.preventDefault();
        evento.stopPropagation();
      });
      return marca;
    };

    const cabecaDeBloco = (bloco, quantas) => {
      const cabeca = criar("div", "cabeca-de-bloco");
      const recolhido = estaRecolhido(bloco, ocultarMudos);
      // O cabeçalho é um BOTÃO, e não um div que escuta clique: dobrar um bloco
      // é ação, e ação tem que chegar pelo teclado. O lápis da trinca fica de
      // fora dele — botão dentro de botão não existe, e o clique do lápis seria
      // engolido pelo de dobrar.
      const dobrar = criar("button", "dobrar-bloco");
      dobrar.type = "button";
      dobrar.setAttribute("aria-expanded", String(!recolhido));
      dobrar.append(criar("span", "seta-da-dobra", recolhido ? "▸" : "▾"));
      if (bloco.icone === "seno") {
        dobrar.append(iconeDeTraco(DESENHO_DO_SENO, "icone-alternado"));
      } else if (bloco.icone === "outros") {
        dobrar.append(iconeDeTraco(DESENHO_DOS_OUTROS, "icone-outros"));
      } else if (bloco.icone === "trifasico") {
        dobrar.append(iconeTrifasico());
      } else if (bloco.icone === "calculado") {
        dobrar.append(iconeDoCalculado());
      }
      if (bloco.chip) dobrar.append(criar("span", "chip-do-grupo", bloco.chip));
      dobrar.append(criar("span", "titulo-do-bloco", bloco.titulo));
      // A contagem importa justamente quando o bloco está recolhido: é ela que
      // diz se vale abrir.
      if (bloco.silencioso) {
        dobrar.append(criar("span", "etiqueta", "sem sinal"));
      }
      dobrar.append(criar("span", "quantas-linhas", `(${quantas})`));
      dobrar.title = bloco.dica
        ? `${bloco.dica} Clique para ${recolhido ? "abrir" : "recolher"}.`
        : `Clique para ${recolhido ? "abrir" : "recolher"} este bloco.`;
      dobrar.addEventListener("click", () => {
        if (blocosRecolhidos.has(bloco.chave)) {
          blocosRecolhidos.delete(bloco.chave);
        } else {
          blocosRecolhidos.add(bloco.chave);
        }
        desenharLista();
      });
      cabeca.append(dobrar);
      if (bloco.conjunto) {
        cabeca.append(lapisDaTrinca({ nome: bloco.chip || bloco.titulo,
                                      conjunto: bloco.conjunto }));
      }
      cabeca.append(criar("span", "regua"));
      return cabeca;
    };

    /* ------------------------------------------------------------------
     * O CARTÃO DE UM SINAL
     * ------------------------------------------------------------------
     *
     * Era uma matriz de canais × contas, com cinco colunas e um risquinho em
     * cada cruzamento vazio. Virou um cartão por sinal, com três folhas
     * dentro — onda, RMS e DC — e um interruptor de filtro no cabeçalho.
     *
     * O que o interruptor resolve: `IAW` e `IAW · 60Hz` deixam de ser duas
     * linhas. São o MESMO cartão em dois estados, e é isso que o filtro de
     * 60 Hz é — não outro sinal, o mesmo sinal com o filtro ligado.
     *
     * A barra de energia responde, antes de marcar qualquer caixa, onde está
     * a energia daquele sinal: turquesa é 60 Hz, roxo é harmônico, rosa é
     * contínua. São as mesmas cores das marcas em subscrito do nome — uma
     * cor, um significado. Medida sobre o registro INTEIRO, não sobre a
     * janela à vista: aqui não há cursor, e uma barra que mudasse conforme o
     * gráfico rolou atrás da janelinha seria medida sem pergunta. Ver
     * `catalogo.energia_das_linhas`.
     */
    const COR_DA_ENERGIA = ["--energia-60", "--energia-harm", "--energia-dc"];
    const NOME_DA_ENERGIA = ["60 Hz", "harmônicos", "contínua"];

    /** As três folhas de um cartão, na ordem em que aparecem. */
    const FOLHAS = [
      ["onda", "instantaneo",
       "a forma de onda no tempo, amostra a amostra"],
      ["RMS", "rms",
       "o eficaz da janela de um ciclo"],
      ["DC", "dc",
       "a componente contínua — a média da janela de um ciclo, com sinal"],
    ];

    /* O estado do interruptor de cada cartão.
     *
     * Vive só enquanto a janelinha está aberta, e é intencional: ele responde
     * «qual destes dois sinais eu quero marcar agora», não é ajuste que se
     * guarda. Quem guarda é a marcação, que já diz qual dos dois foi. */
    const filtroDoCartao = new Map();

    /* O modo TRADICIONAL é o filtro aceso e preso — é o que o modo é. */
    const soFiltrado = () => visaoDeAnalise !== "avancado";

    /** O interruptor nasce ligado quando não há bruto a oferecer. */
    const filtroInicial = (l) => {
      // Conta do usuário nasce com o filtro DESLIGADO, sempre — inclusive no
      // tradicional. Filtrar uma potência não tem significado físico, e quem
      // avisa que não há 60 Hz ali é a barra de energia, nunca uma trava.
      if (l.procedencia === "conta") return false;
      //: Canal de «Outros sinais» nasce com o filtro DESLIGADO (pedido dele).
      //: Ele está naquele bloco porque a onda não passou no teste de
      //: alternado — filtrar 60 Hz de um sinal que não é alternado mede uma
      //: componente que não existe, e entregava um traço quase reto com cara
      //: de medida. Apagado, o cartão mostra o canal como o relé gravou, que
      //: é a única coisa verdadeira que se pode mostrar dele.
      if (l.bloco === "outros") return false;
      // Sem coluna de bruto para mostrar, o interruptor só pode estar ligado:
      // é o caso do registro que o relé já gravou filtrado, e de todo `.CEV`.
      if (!l.contas.has("bruto.onda") && !l.contas.has("bruto.rms")) return true;
      if (soFiltrado()) return true;
      return !!dados.filtro;
    };

    /** O interruptor pode ser mexido? */
    const filtroLivre = (l) => {
      // Conta do usuário NUNCA trava: ver `filtroInicial`.
      if (l.procedencia === "conta") {
        return l.contas.has("filtrado.onda") || l.contas.has("filtrado.rms");
      }
      //: E canal de «Outros sinais» fica apagado e PRESO: ver `filtroInicial`.
      //: Preso, e não livre com o padrão apagado, porque aqui não há escolha a
      //: fazer — o 60 Hz daquele canal não é uma leitura, é um artefato.
      if (l.bloco === "outros") return false;
      // No tradicional ele fica aceso e preso — é o que o modo é.
      if (soFiltrado()) return false;
      // E com o FILTRO DA TELA aceso ele também não se mexe. Quem manda no
      // que o gráfico desenha é aquele botão: marcar aqui a coluna do bruto
      // com ele ligado punha no painel o filtrado assim mesmo, e a marca
      // pulava de folha debaixo do clique. O interruptor do cartão escolhe
      // entre bruto e 60 Hz quando há escolha a fazer — e com o filtro da
      // tela aceso não há.
      if (dados.filtro) return false;
      const temBruto = l.contas.has("bruto.onda") || l.contas.has("bruto.rms");
      const temFiltrado = l.contas.has("filtrado.onda")
                       || l.contas.has("filtrado.rms");
      return temBruto && temFiltrado;
    };

    const filtroDe = (l) => {
      if (!filtroDoCartao.has(l.chave)) {
        filtroDoCartao.set(l.chave, filtroInicial(l));
      }
      const quer = filtroDoCartao.get(l.chave);
      return filtroLivre(l) ? quer : filtroInicial(l);
    };

    /** Qual COLUNA do catálogo cada folha do cartão aponta, neste estado. */
    const colunaDaFolha = (l, grandeza) => {
      // A DC não tem par filtrado: o filtro de 60 Hz não produz contínua
      // nenhuma, e a contínua continua sendo o que diz ser com ele aceso ou
      // apagado. Por isso ela é sempre a do bruto.
      if (grandeza === "dc") return "bruto.dc";
      const lado = filtroDe(l) ? "filtrado" : "bruto";
      return `${lado}.${grandeza === "instantaneo" ? "onda" : "rms"}`;
    };

    /** A barra de energia, com as porcentagens no hover. */
    const barraDeEnergia = (l) => {
      if (!l.energia) return null;
      const barra = criar("span", "barra-de-energia");
      const partes = [];
      for (let i = 0; i < 3; i += 1) {
        const fracao = l.energia[i] || 0;
        partes.push(`${NOME_DA_ENERGIA[i]} ${(fracao * 100).toFixed(1)} %`);
        if (fracao <= 0) continue;
        const fatia = criar("i");
        fatia.style.background = `var(${COR_DA_ENERGIA[i]})`;
        fatia.style.width = `${fracao * 100}%`;
        barra.append(fatia);
      }
      // No `title` e não num balão nosso: o balão teria que se reposicionar
      // dentro de uma janelinha que rola, e o `title` do navegador já faz
      // isso sem código nenhum.
      barra.title = `Onde está a energia de ${l.nome}, no registro inteiro:\n`
                  + partes.join("\n")
                  + "\n\nMedido nas amostras (RMS² = DC² + 60Hz² + harm²), "
                  + "não deduzido do cabeçalho.";
      return barra;
    };

    /** O interruptor do filtro de 60 Hz, no cabeçalho do cartão. */
    const interruptorDoFiltro = (l) => {
      const livre = filtroLivre(l);
      const aceso = filtroDe(l);
      const caixa = criar("button", `interruptor${livre ? "" : " preso"}`);
      caixa.type = "button";
      caixa.setAttribute("aria-pressed", aceso ? "true" : "false");
      caixa.append(criar("span", "rotulo-do-interruptor", "filtro 60 Hz"));
      const trilho = criar("span", `trilho${aceso ? " aceso" : ""}`);
      trilho.append(criar("span", "bolinha-do-interruptor"));
      caixa.append(trilho);
      caixa.title = livre
        ? (aceso
            ? `As folhas mostram só a componente de 60 Hz de ${l.nome}. `
              + "Apague para ver o sinal como o relé gravou."
            : `As folhas mostram ${l.nome} como o relé gravou — com `
              + "harmônicos e contínua. Acenda para ver só os 60 Hz.")
        : (l.procedencia === "conta"
            ? "Esta conta não tem 60 Hz para o filtro extrair — a barra de "
              + "energia mostra onde a energia dela está."
            : l.bloco === "outros"
            ? "Este canal não passou no teste de alternado: filtrar 60 Hz "
              + "dele mediria uma componente que não existe. Fica apagado e "
              + "preso, mostrando o canal como o relé gravou."
            : soFiltrado()
              ? "No modo tradicional o filtro fica aceso e preso: é o que o "
                + "modo é. Troque para «avançado» para poder apagá-lo."
              : dados.filtro
                ? "O botão «Filtro» do topo da tela está aceso, e é ele que "
                  + "manda no que o gráfico desenha. Apague-o para escolher "
                  + "sinal a sinal."
                : "Este registro já veio filtrado do relé, e não há como "
                  + "desfiltrá-lo.");
      if (livre) {
        caixa.addEventListener("click", (evento) => {
          evento.stopPropagation();
          filtroDoCartao.set(l.chave, !filtroDe(l));
          desenharLista();
        });
      }
      return caixa;
    };

    /* Os cartões que estão abertos. Começa tudo fechado: a lista inteira
     * aberta seriam sessenta folhas, que é a lista de cento e vinte nomes de
     * antes com outro nome. */
    const cartoesAbertos = new Set();

    /* As folhas que o usuário FORÇOU, apesar de o programa dizer que não
     * existem. Três cliques no «—» habilitam.
     *
     * Existe porque o programa pode errar, e um bloqueio sem saída transforma
     * um palpite nosso em veredito. A folha forçada carrega o selo «forçado»
     * do lado, para nunca entrar num relatório como se fosse resultado
     * normal. Ver a regra do projeto: avisa, nunca bloqueia. */
    const folhasForcadas = new Set();

    /** A engrenagem: de onde o sinal saiu, e em que gráfico ele entra.
     *
     * Responde as duas perguntas que a lista não cabe: COMO aquele sinal foi
     * obtido, e por que ele não aparece no fasorial ou nos harmônicos. Em
     * gaveta e não em hover porque é texto para ler, não para espiar.
     *
     * O «⋯» e não a engrenagem: engrenagem promete AJUSTE, e aqui não se
     * ajusta nada — lê-se. «Mais sobre este sinal» é o que o botão faz, e é
     * o que os três pontos querem dizer em qualquer tela.
     */
    const engrenagemDoCartao = (l) => {
      const botao = criar("button", "engrenagem-do-cartao", "⋯");
      botao.type = "button";
      botao.title = `Como ${l.nome} é calculado, e onde ele pode entrar.`;
      botao.addEventListener("click", (evento) => {
        evento.stopPropagation();
        const ja = l._gaveta;
        for (const g of lista.querySelectorAll(".gaveta-do-cartao")) g.remove();
        for (const x of lista.querySelectorAll(".engrenagem-do-cartao")) {
          x.classList.remove("aberta");
        }
        if (ja) { l._gaveta = null; return; }
        l._gaveta = true;
        botao.classList.add("aberta");
        const gaveta = criar("div", "gaveta-do-cartao");
        const diz = (chave, valor) => {
          if (!valor) return;
          const parte = criar("div", "parte-da-gaveta");
          parte.append(criar("span", "chave-da-gaveta", chave),
                       criar("span", "valor-da-gaveta", valor));
          gaveta.append(parte);
        };
        diz("vem de", l.procedencia === "campo"
              ? "canal do arquivo, como o relé gravou"
              : l.procedencia === "conta" ? "conta sua"
              : "calculado pelo OscLab");
        diz("conta", l.nota || l.origem);
        if (l.energia) {
          diz("energia", NOME_DA_ENERGIA
            .map((n, i) => `${n} ${(l.energia[i] * 100).toFixed(1)} %`)
            .join("  ·  "));
        }
        const emFasor = l.bloco !== "outros";
        diz("gráficos", `analógico ✓   fasorial ${emFasor ? "✓" : "✗"}`
                      + `   harmônicos ${emFasor ? "✓" : "✗"}`);
        diz("por quê", l.motivo || l.aviso);
        botao.closest(".cartao-do-sinal").after(gaveta);
      });
      return botao;
    };

    const desenharLinha = (l, destino, i = 0) => {
      const cartao = criar("div", "cartao-do-sinal");
      emFaixa(cartao, i);
      const aberto = cartoesAbertos.has(l.chave);
      if (aberto) cartao.classList.add("aberto");
      if (l.sem_sinal) cartao.classList.add("mudo");

      const topo = criar("div", "topo-do-cartao");
      topo.append(criar("span", "dobra-do-cartao", aberto ? "▾" : "▸"));

      // A FAMÍLIA está na cor do nome: branco é canal do relé, rosa é conta
      // do OscLab. Antes era uma bolinha ao lado, e a mesma informação
      // aparecia de dois jeitos diferentes nesta janela e na do fasorial.
      // Uma regra só, nas duas: a cor do nome.
      //
      // O que a bolinha dizia a mais — programa × conta sua — continua no
      // `⋯`, que é onde se lê como o sinal foi obtido.
      const nome = criar("span", "nome-do-cartao"
                         + (l.canal < 0 ? " calculado" : ""));
      nome.title = l.procedencia === "campo"
        ? "canal do relé: veio no arquivo, como o relé gravou"
        : (l.procedencia === "conta"
             ? "conta sua: foi você quem escreveu a expressão"
             : "calculado pelo OscLab a partir dos canais do arquivo");
      nomeComGrupo(nome, l.nome, l.canal < 0 ? l.grupo : "");
      topo.append(nome);
      if (l.unidade_mostrada) {
        topo.append(criar("span", "unidade-do-cartao", l.unidade_mostrada));
      }
      if (l.sem_sinal) {
        const marca = criar("span", "etiqueta", "sem sinal");
        marca.title = "A entrada do relé não está cabeada: este canal lê só o "
                    + "ruído do conversor.";
        topo.append(marca);
      }
      //: O vazio vem ANTES da barra: ela encosta no lado direito, junto do
      //: filtro e do `⋯`, em vez de ficar colada no nome. À esquerda fica o
      //: que identifica o sinal; à direita, o que se mede e o que se ajusta.
      topo.append(criar("span", "empurra-do-cartao"));
      const barra = barraDeEnergia(l);
      if (barra) topo.append(barra);
      //: O motivo NÃO vira texto na faixa (pedido dele): em «Outros sinais»
      //: ele aparecia em toda linha, empurrava a barra de energia para dentro
      //: e deixava aquele bloco com outra cara que os de cima. Ele continua
      //: existindo, no `title` do nome -- que é onde a mão vai quando estranha
      //: o interruptor preso.
      if (l.motivo) {
        nome.title = nome.title ? `${nome.title} — ${l.motivo}` : l.motivo;
      }
      // A RESSALVA de uma conta: ela FUNCIONA, e o ⓘ só diz o que tem de
      // estranho. Por isso o símbolo e não a frase — a frase ao lado de uma
      // linha que funciona se leria como defeito.
      if (l.aviso) {
        const marca = criar("span", "ressalva-da-linha", "ⓘ");
        marca.title = l.aviso;
        topo.append(marca);
      }
      if (filtroLivre(l) || l.procedencia !== "conta" || l.motivo) {
        topo.append(interruptorDoFiltro(l));
      }
      topo.append(engrenagemDoCartao(l));
      topo.addEventListener("click", () => {
        if (cartoesAbertos.has(l.chave)) cartoesAbertos.delete(l.chave);
        else cartoesAbertos.add(l.chave);
        desenharLista();
      });
      cartao.append(topo);

      if (aberto) cartao.append(folhasDoCartao(l));
      (destino || lista).append(cartao);
    };

    /** O corpo do cartão: uma folha por grandeza. */
    const folhasDoCartao = (l) => {
      const corpo = criar("div", "folhas-do-cartao");
      for (const [rotulo, grandeza, oque] of FOLHAS) {
        const chave = colunaDaFolha(l, grandeza);
        // A contínua é do sinal BRUTO — é a parte de 0 Hz do que o relé
        // gravou. No modo tradicional, que mostra só o filtrado, ela não tem
        // onde existir: oferecê-la ali seria o modo prometendo uma coisa e
        // entregando outra. Fica apagada, com o motivo escrito.
        const foraDoModo = soFiltrado() && grandeza === "dc";
        const sinal = foraDoModo ? null : l.contas.get(chave);
        const folha = criar("label", "folha-do-cartao");
        const forcada = folhasForcadas.has(`${l.chave}:${grandeza}`);
        // Com o filtro aceso, marcar a coluna do bruto desenharia o filtrado
        // e a marca pularia de folha debaixo do clique. O mesmo vale para a
        // MEDIDA do gráfico: num painel em RMS a «onda» não tem como entrar.
        const empurrado = sinal && desenhadoDe(sinal.id) !== sinal.id;
        if (sinal && !empurrado) {
          folha.append(caixaDoSinal(sinal, pedidoDaCela(l, sinal)));
          folha.append(iconeDaFolha(grandeza, filtroDe(l)));
          folha.append(criar("span", "rotulo-da-folha", rotulo));
          if (forcada) {
            const selo = criar("span", "selo-forcado", "forçado");
            selo.title = "Esta folha foi habilitada à força: o OscLab julgou "
                       + "que ela não existe para este sinal. O selo fica "
                       + "para ela não passar por resultado normal.";
            folha.append(selo);
          }
          folha.title = `${sinal.nome} — ${oque}`;
          corpo.append(folha);
          continue;
        }
        // --- a folha que não existe ---
        folha.classList.add("apagada");
        const risco = criar("span", "risquinho", "—");
        const porque = foraDoModo
          ? "a contínua é do sinal bruto: troque para «avançado» para vê-la"
          : !sinal
            ? motivoDaAusencia(l, chave)
            : `este gráfico está em RMS: ${sinal.nome} apareceria como outro `
              + "sinal. Troque para «inst.» no topo do gráfico para ver a onda.";
        risco.title = `${porque}\n\nTrês cliques aqui habilitam mesmo assim.`;
        folha.append(risco);
        folha.append(iconeDaFolha(grandeza, filtroDe(l)));
        folha.append(criar("span", "rotulo-da-folha", rotulo));
        const nota = criar("span", "porque-da-folha", porque);
        folha.append(nota);
        // O ESCAPE. Três cliques e a folha vale, mesmo que o programa ache
        // que não. É o que impede um palpite nosso de virar veredito: quem
        // decide o que faz sentido é o engenheiro, não o programa.
        if (sinal || (foraDoModo && l.contas.has("bruto.dc"))) {
          folha.addEventListener("click", (evento) => {
            if ((evento.detail || 0) < 3) return;
            folhasForcadas.add(`${l.chave}:${grandeza}`);
            desenharLista();
          });
        }
        corpo.append(folha);
      }
      return corpo;
    };

    campo.addEventListener("input", desenharLista);
    desenharLista();

    const aplicar = criar("button", "aceitar", "mostrar na tela");
    aplicar.addEventListener("click", () => {
      // A ordem é a do catálogo, não a de clique: a tela não pode mudar de
      // arrumação conforme a ordem em que alguém marcou as caixas.
      const ids = (dados.catalogo || [])
        .filter((x) => escolhidos.has(x.id)).map((x) => x.id);
      janelinha.close();
      trocarSinais(painel.id, ids);
    });

    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem mudar a tela";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());

    const pe = criar("div", "pe-do-catalogo");
    pe.append(criar("span", "empurra"), aplicar);

    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, `Sinais de ${painel.nome}`), campo, fechar);
    janelinha.append(cabeca, barra, lista, pe);
    if (iedDaLista) {
      // As abas dos IEDs: trocar de aba aplica o que já foi marcado e reabre.
      const abas = criar("div", "abas-dos-ieds");
      for (const ficha of dados.ieds || []) {
        const b = criar("button", "aba-do-ied" + (ficha.letra === iedDaLista ? " escolhida" : ""));
        b.type = "button";
        b.append(seloDoIed(ficha.letra),
                 criar("span", null, `IED ${ficha.letra} · ${ficha.apelido || ficha.arquivo}`));
        b.addEventListener("click", () => {
          if (ficha.letra === iedDaLista) return;
          const ids = (dados.catalogo || []).filter((x) => escolhidos.has(x.id)).map((x) => x.id);
          janelinha.close();
          trocarSinais(painel.id, ids);
          abrirCatalogo(painel, ficha.letra);
        });
        abas.append(b);
      }
      cabeca.after(abas);
    }
    // A janelinha se registra para ser redesenhada quando o modo de análise
    // mudar no cabeçalho: trocar o modo tem que mexer na lista que está na
    // frente do usuário, e não só na próxima que ele abrir.
    redesenharCatalogo = desenharLista;
    janelinha.addEventListener("close", () => {
      redesenharCatalogo = null;
      janelinha.remove();
    });
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
    campo.focus();
  }

  /** Os grupos trifásicos do registro: quais três canais formam cada um.
   *
   * O grupo não é escolha nossa nem do usuário: ele sai do nome dos canais, e
   * é dele que saem `IN`, `3I0`, `I1` e `I2`. Errado o grupo, os quatro saem
   * errados — na unidade certa, com cara de medida, e sem aviso nenhum. Esta
   * tela é onde se confere isso de uma vez, sem caçar o lápis bloco a bloco.
   *
   * **Só conferir e corrigir.** Criar um grupo do nada e desfazer um grupo
   * ainda não existem: os dois mudam o que o servidor calcula, e o servidor
   * hoje só sabe receber a troca dos três canais de um grupo que ele já achou.
   */
  /* ------------------------------------------------------------------
   * O VÍNCULO DE POTÊNCIA
   * ------------------------------------------------------------------
   *
   * Que trinca de corrente pertence ao mesmo vão de que trinca de tensão.
   * Com o par feito, saem P, Q, S e FP — e sem ele, nada disso existe.
   *
   * **O programa não casa sozinho, de propósito.** Dois vãos de uma
   * subestação têm nomes parecidos, e o par errado produz uma potência na
   * unidade certa, na ordem de grandeza certa, e errada — o tipo de erro que
   * não aparece no gráfico. Quem sabe qual TC pertence a qual TP é quem leu
   * o unifilar, e esse é o engenheiro, não a expressão regular.
   *
   * O vínculo vale nos DOIS sentidos: ligar G1 a G3 é a mesma afirmação que
   * ligar G3 a G1 — são o mesmo vão. O servidor grava os dois lados.
   */
  //: A seta do par: `G1↔G3`. Espelha `SETA_DO_VINCULO` em `plot/catalogo.py`,
  //: que é quem a põe no NOME dos sinais de potência — as duas têm que ser o
  //: mesmo caractere, senão a tela escreve o par de um jeito e o catálogo de
  //: outro, e quem procura `P G1↔G3` não acha.
  const SETA_DO_VINCULO = "↔";

  const chaveDoGrupo = (grupo) =>
    String((grupo.conjunto || {}).chave || "");

  const grupoPorChave = (chave) =>
    ((dados.conjuntos || []).find((c) => c.chave === chave) || null);

  const vinculoDoGrupo = (grupo) =>
    (dados.vinculos_de_potencia || {})[chaveDoGrupo(grupo)] || null;

  async function gravarVinculo(de, com, base) {
    const r = await fetch(`/api/onda/${sha}/potencia`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ de, com, base }),
    });
    const resposta = await r.json();
    if (resposta.erro) return;
    dados.vinculos_de_potencia = resposta.vinculos_de_potencia || {};
    // Redesenhar a janela inteira: os sinais de potência entram e saem do
    // catálogo com o vínculo, e metade da tela sabendo do par e a outra
    // metade não é como se vê uma potência de um vão no gráfico de outro.
    await recarregar();

    // E refazer a janelinha de GRUPOS, se ela estiver aberta.
    //
    // `recarregar` redesenha a página; um `<dialog>` aberto não faz parte
    // dela e continuava com o conteúdo de antes — o cartão seguia dizendo
    // «vincular», sem par nenhum escrito, e só fechando e abrindo é que o
    // vínculo aparecia. Quem acabou de gravar fica sem confirmação do que
    // gravou, que é pior que não ter gravado.
    // O catálogo de sinais primeiro, a de grupos por cima — é a ordem em que
    // elas estão na tela, e é de dentro do catálogo que a de grupos se abre.
    const catalogoAberto = document.querySelector("dialog.busca.catalogo");
    if (catalogoAberto) {
      const meu = painelPorId(catalogoAberto.dataset.painel || "");
      catalogoAberto.close();
      // Sem isto, P, Q, S e FP só apareciam na lista depois de fechar e abrir
      // o catálogo: o vínculo acabara de criá-los, e a janela aberta era a de
      // antes deles existirem.
      if (meu) abrirCatalogo(meu);
    }
    const aberta = document.querySelector("dialog.busca.grupos");
    if (aberta) {
      aberta.close();
      abrirGrupos();
    }
  }

  /** A linha que diz com quem este grupo está vinculado, embaixo do cartão. */
  function descricaoDoVinculo(grupo) {
    const vinculo = vinculoDoGrupo(grupo);
    if (!vinculo) return null;
    const outro = grupoPorChave(vinculo.com);
    if (!outro) return null;
    const corrente = grupo.tipo !== "tensões";
    const quais = vinculo.base === "linha"
      ? "P, Q, S e FP — tensão de linha, então não há potência por fase"
      : "P, Q, S, FP e as potências por fase";
    // O par no nome, e não o grupo: é o nome que os sinais realmente têm, e
    // repetir aqui o que a lista vai mostrar é o que faz os dois casarem.
    const par = corrente
      ? `${grupo.nome}${SETA_DO_VINCULO}${outro.rotulo}`
      : `${outro.rotulo}${SETA_DO_VINCULO}${grupo.nome}`;
    // Curta: quem é o par já está no chip do topo. O que falta dizer aqui é
    // o que o par PRODUZ e com que nome — que é o que se vai procurar no
    // catálogo depois.
    const linha = criar("div", "vinculo-do-grupo",
                        `deste par saem P ${par}, Q ${par}, S ${par} e `
                        + `FP ${par}`);
    linha.title = `Vinculado a ${outro.rotulo} — ${quais}.`;
    return linha;
  }

  function botaoDeVinculo(grupo) {
    const vinculo = vinculoDoGrupo(grupo);
    const botao = criar("button",
                        `chave vincular-o-grupo${vinculo ? " vinculado" : ""}`);
    botao.type = "button";
    botao.append(criar("span", null, vinculo ? "⛓" : "⛓"),
                 criar("span", null, vinculo ? "vinculado" : "vincular"));
    const querTensao = grupo.tipo !== "tensões";
    botao.title = vinculo
      ? "Trocar ou desfazer o vínculo de potência deste grupo."
      : `Dizer qual grupo de ${querTensao ? "tensão" : "corrente"} é do mesmo `
        + "vão que este. Com o par feito saem P, Q, S e FP — sem ele, "
        + "nenhuma potência existe. O OscLab não adivinha o par: casar o vão "
        + "errado dá um número plausível e errado.";
    botao.addEventListener("click", () => abrirVinculo(grupo));
    return botao;
  }

  /** Os nomes dos três canais de um conjunto, como o arquivo os escreve.
   *
   * A janelinha mostrava `c.chave` — `V*Y`, `V*Z`. Essa é a chave INTERNA do
   * agrupamento: o nome dos canais com a letra da fase trocada por `*`. Serve
   * para juntar os três, e não serve para escolher entre eles — ninguém
   * reconhece o seu vão por `V*Y`.
   */
  function nomesDoConjunto(conjunto) {
    const porIndice = new Map();
    for (const x of dados.catalogo || []) {
      if (x.familia === "canal" && x.canal >= 0 && !porIndice.has(x.canal)) {
        porIndice.set(x.canal, x.nome);
      }
    }
    return (conjunto.canais || [])
      .map((i) => porIndice.get(i) || `#${i}`);
  }

  /** A janelinha de escolher o par.
   *
   * Uma lista de grupos, e nada mais. A base da tensão — fase-neutro ou
   * fase-fase — SAI de cada candidato e aparece na linha dele, em vez de ser
   * um botão à parte no alto.
   *
   * Era um botão à parte, e estava errado em dois sentidos. O literal: ele
   * chutava a base a partir do PRIMEIRO candidato e depois aplicava esse
   * chute a qualquer um que fosse clicado — escolher G4 gravava a base de G3.
   * E o de fundo: desde que a trinca sabe se foi montada de `A/B/C` ou de
   * `AB/BC/CA`, a base deixou de ser pergunta para quem tem a trinca em
   * delta; perguntar de novo é abrir espaço para a tela contradizer o
   * arquivo.
   */
  function abrirVinculo(grupo) {
    const querTensao = grupo.tipo !== "tensões";
    const alvo = querTensao ? "V" : "I";
    const candidatos = (dados.conjuntos || [])
      .filter((c) => c.grandeza === alvo);
    const atual = vinculoDoGrupo(grupo);
    // De que trinca de TENSÃO sai a base, venha este menu de que lado vier.
    const tensaoDe = (c) => querTensao ? c : grupoPorChave(chaveDoGrupo(grupo));

    const janelinha = criar("dialog", "busca vinculo");
    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());
    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, `Vincular ${grupo.nome}`),
                  criar("span", "sub-do-cabeca",
                        `qual grupo de ${querTensao ? "tensão" : "corrente"} é `
                        + "do mesmo vão"),
                  fechar);

    const lista = criar("div", "lista-de-grupos");
    if (!candidatos.length) {
      lista.append(criar("p", "vazio",
        `Este registro não tem nenhum grupo de ${querTensao ? "tensão" : "corrente"} `
        + "completo, então não há com que vincular."));
    }
    for (const c of candidatos) {
      const ligado = !!(atual && atual.com === c.chave);
      const item = criar("button",
                         "opcao-de-vinculo em-duas-linhas"
                         + (ligado ? " escolhida" : ""));
      item.type = "button";

      const alto = criar("span", "alto-da-opcao");
      alto.append(criar("span", "chip-do-grupo", c.rotulo));
      // Os nomes do ARQUIVO, que é o que o engenheiro reconhece.
      alto.append(criar("span", "canais-do-candidato",
                        nomesDoConjunto(c).join(" · ")));
      alto.append(criar("span", "unidade-do-candidato", c.unidade || ""));
      if (ligado) alto.append(criar("span", "etiqueta", "vinculado"));
      item.append(alto);

      // A BASE, na linha de quem ela descreve — e derivada, não perguntada.
      const tensao = tensaoDe(c);
      const base = (tensao && tensao.base === "linha") ? "linha" : "fase";
      const baixo = criar("span", "baixo-da-opcao");
      baixo.append(criar("span", "base-do-candidato",
                         base === "linha"
                           ? "tensões de linha (fase-fase)"
                           : "tensões de fase (fase-neutro)"));
      baixo.append(criar("span", "saida-do-par",
                         base === "linha"
                           ? "→ P, Q, S e FP (sem potência por fase)"
                           : "→ P, Q, S, FP e as potências por fase"));
      // Preferir tensão de FASE não é gosto: é quanto do programa funciona.
      // Em delta não há VN, nem 3V0, nem triângulo, nem potência por fase —
      // `VAB+VBC+VCA ≡ 0` apaga o neutro, e sem o neutro essas quatro coisas
      // não existem. Dito aqui, na hora de escolher, e não depois.
      if (base === "fase") {
        const selo = criar("span", "etiqueta-boa", "mais completo");
        selo.title = "Com tensão de FASE o programa faz mais: VN, 3V0, as "
                   + "potências por fase e o triângulo de tensões só existem "
                   + "com o neutro. Em delta, VAB+VBC+VCA ≡ 0 apaga o neutro, "
                   + "e as quatro deixam de existir.";
        baixo.append(selo);
      }
      item.append(baixo);

      if (c.sem_sinal) {
        const marca = criar("span", "etiqueta", "sem sinal");
        marca.title = "As três entradas não estão cabeadas: a potência deste "
                    + "par sairia do ruído do conversor.";
        alto.append(marca);
      }
      item.title = base === "linha"
        ? "Medido entre fases: não existe potência por fase — sem referência "
          + "de neutro não há como repartir. Sai o total, pelo método dos dois "
          + "wattímetros, que é exato mesmo com desequilíbrio."
        : "Medido contra o neutro: saem as potências por fase e o total "
          + "trifásico. Se estas tensões forem de linha, corrija a fase dos "
          + "canais para VAB, VBC e VCA em «canais» — assim o 3V0 e o V1 "
          + "também saem certos, e não só a potência.";
      item.addEventListener("click", async () => {
        janelinha.close();
        await gravarVinculo(chaveDoGrupo(grupo), c.chave, base);
      });
      lista.append(item);
    }

    const pe = criar("div", "pe-do-catalogo");
    if (atual) {
      const desfazer = criar("button", "chave", "desfazer o vínculo");
      desfazer.type = "button";
      desfazer.title = "Tira o par dos DOIS lados, e as potências somem do "
                     + "catálogo. Um vínculo é um par, não duas anotações.";
      desfazer.addEventListener("click", async () => {
        janelinha.close();
        await gravarVinculo(chaveDoGrupo(grupo), "", "fase");
      });
      pe.append(desfazer);
    }
    // Uma linha. O resto — por que fase é melhor, o que some em delta — está
    // no hover do selo «mais completo», ao lado de quem ele descreve.
    const nota = criar("span", "aviso-do-risquinho",
                       "A base sai da fase declarada dos canais; corrija-a em "
                       + "«canais». O vínculo vale nos dois sentidos.");
    nota.title = "VA/VB/VC é fase-neutro; VAB/VBC/VCA é fase-fase. O OscLab "
               + "não pergunta porque a resposta já está no vínculo "
               + "canal→fase, que você confere na tela dos canais — e duas "
               + "telas mandando na mesma coisa é como elas passam a "
               + "discordar.";
    pe.append(nota);
    janelinha.append(cabeca, lista, pe);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
  }

  function abrirGrupos() {
    // Um grupo por `grupo`, com a trinca de onde ele saiu. A trinca vem no
    // sinal — é o único campo que diz QUAIS três canais entraram na conta.
    const porGrupo = new Map();
    for (const x of dados.catalogo || []) {
      if (!x.grupo) continue;
      // Os sinais de POTÊNCIA levam o par no campo `grupo` — `G1↔G3` —, porque
      // é dele que eles saem. Esta tela lia isso como mais um grupo trifásico
      // e desenhava um cartão fantasma: sem canais («—») e prometendo
      // `IN G1↔G3`, `3I0 G1↔G3`, que não existem. Um par não é um grupo: é a
      // relação entre dois.
      if (x.grupo.includes(SETA_DO_VINCULO)) continue;
      let grupo = porGrupo.get(x.grupo);
      if (!grupo) {
        grupo = { nome: x.grupo, conjunto: null, origem: "", tipo: "",
                  unidade: "", sem_sinal: false };
        porGrupo.set(x.grupo, grupo);
      }
      if (x.conjunto && !grupo.conjunto) {
        grupo.conjunto = x.conjunto;
        grupo.origem = x.origem || "";
      }
      if (x.familia === "canal" && !grupo.tipo) {
        grupo.tipo = { I: "correntes", V: "tensões" }[x.grandeza_do_canal] || "";
        grupo.unidade = x.unidade_mostrada || x.unidade || "";
      }
      if (x.sem_sinal) grupo.sem_sinal = true;
    }

    const janelinha = criar("dialog", "busca grupos");
    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());

    const cabeca = criar("div", "cabeca");
    const titulo = criar("h3", null, "");
    titulo.append(iconeTrifasico(), criar("span", null, " Grupos trifásicos"));
    cabeca.append(titulo,
                  criar("span", "sub-do-cabeca",
                        "um grupo tem uma grandeza só — três correntes ou três "
                        + "tensões, na mesma unidade"),
                  fechar);

    const lista = criar("div", "lista-de-grupos");
    if (!porGrupo.size) {
      lista.append(criar("p", "vazio",
                         "Este registro não tem nenhum conjunto trifásico "
                         + "completo: sem três fases da mesma grandeza não há "
                         + "resíduo nem componente simétrica a calcular."));
    }
    for (const grupo of porGrupo.values()) {
      const cartao = criar("div", "cartao-do-grupo");
      const topo = criar("div", "topo-do-grupo");
      topo.append(criar("span", "chip-do-grupo", grupo.nome));
      // O par, colado no nome do grupo: `G1 ↔G3`.
      //
      // Ele já estava escrito na frase embaixo do cartão, e a frase é longa o
      // bastante para ser cortada — o par sumia justamente no cartão em que
      // ele existe. Aqui ele fica onde o olho procura «quem é este grupo»,
      // que é exatamente a pergunta que o vínculo responde.
      const parDoGrupo = vinculoDoGrupo(grupo);
      const outroDoPar = parDoGrupo && grupoPorChave(parDoGrupo.com);
      if (outroDoPar) {
        const chip = criar("span", "chip-do-vinculo",
                           `${SETA_DO_VINCULO}${outroDoPar.rotulo}`);
        chip.title = `Vinculado a ${outroDoPar.rotulo}: os dois são do mesmo `
                   + "vão, e é desse par que saem P, Q, S e FP.";
        topo.append(chip);
      }
      topo.append(criar("span", "tipo-do-grupo",
                        [grupo.tipo, grupo.unidade].filter(Boolean).join(" · ")));
      // ESTA tela mostra todos os grupos, inclusive os que o catálogo esconde
      // por estarem sem sinal — é aqui que se descobre por que a numeração
      // pula de `G1` para `G3`. O número é a posição do conjunto no arquivo e
      // não se refaz quando um deles é escondido: nome que muda com checkbox é
      // pior que buraco na sequência.
      if (grupo.sem_sinal) {
        const marca = criar("span", "etiqueta", "sem sinal");
        marca.title = "As três entradas do relé não estão cabeadas: leem só o "
                    + "ruído do conversor. O grupo existe e continua com o "
                    + "número dele; o catálogo é que o esconde enquanto "
                    + "«ocultar sinais nulos» estiver marcado.";
        topo.append(marca);
      }
      topo.append(criar("span", "empurra"));
      if (grupo.conjunto) {
        const editar = criar("button", "chave editar-o-grupo", "");
        editar.type = "button";
        editar.append(criar("span", null, "✎"),
                      criar("span", null, "trocar os canais"));
        const g = grupo.tipo === "tensões" ? "V" : "I";
        editar.title = `Escolher quais três canais formam ${grupo.nome}. `
                     + "O OscLab deduziu estes do NOME deles, e nome de canal "
                     + "cada fabricante escreve como quer — errada a trinca, "
                     + `${g}N, 3${g}0, ${g}1 e ${g}2 erram junto, sem aviso.`;
        editar.addEventListener("click", () =>
          abrirCorrecaoDaTrinca({ nome: grupo.nome, conjunto: grupo.conjunto }));
        topo.append(editar);
        topo.append(botaoDeVinculo(grupo));
      }
      cartao.append(topo);
      cartao.append(criar("div", "canais-do-grupo", grupo.origem || "—"));
      const grandeza = grupo.tipo === "tensões" ? "V" : "I";
      cartao.append(criar("div", "saidas-do-grupo",
                          `deste grupo saem ${grandeza}N ${grupo.nome}, `
                          + `3${grandeza}0 ${grupo.nome}, ${grandeza}1 `
                          + `${grupo.nome} e ${grandeza}2 ${grupo.nome}`));
      const linhaDoVinculo = descricaoDoVinculo(grupo);
      if (linhaDoVinculo) cartao.append(linhaDoVinculo);
      lista.append(cartao);
    }

    const pe = criar("div", "pe-do-catalogo");
    pe.append(criar("span", "aviso-do-risquinho",
                    "a correção fica gravada com o registro e vale para tudo "
                    + "que sai do grupo"));
    janelinha.append(cabeca, lista, pe);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
  }

  /** A tela «canais»: o que está no arquivo, como está.
   *
   * Nada de calculado entra aqui, e é o ponto: esta é a tela onde se confere a
   * DEDUÇÃO antes de confiar em qualquer conta. Se a fase de um canal está
   * errada, `IN`, `3I0`, `I1` e o relatório saem errados atrás dela, na
   * unidade certa e sem aviso nenhum.
   *
   * **Linhas de verdade, não células de uma grade.** Já foi uma grade de seis
   * colunas, e uma linha que pusesse uma célula a menos empurrava TODAS as de
   * baixo uma casa para o lado — a tela inteira desalinhada por causa de uma
   * linha. Numa fileira de `flex` o erro fica preso à linha que o cometeu.
   */
  function abrirCanais() {
    const canais = (dados.catalogo || []).filter((x) => x.familia === "canal");
    // A trinca de cada grupo, para o lápis do grupo poder corrigi-la daqui: a
    // fase e o grupo são as duas deduções desta tela, e as duas se corrigem no
    // mesmo lugar.
    const trincaDoGrupo = new Map();
    for (const x of dados.catalogo || []) {
      if (x.grupo && x.conjunto && !trincaDoGrupo.has(x.grupo)) {
        trincaDoGrupo.set(x.grupo, x.conjunto);
      }
    }

    const janelinha = criar("dialog", "busca canais");
    const correcoes = new Map();

    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());

    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, "Canais"),
                  criar("span", "sub-do-cabeca",
                        "o que está no arquivo, como está — nenhum sinal "
                        + "calculado aqui"),
                  fechar);

    const tabela = criar("div", "tabela-de-canais");
    const abertos = new Set();

    const desenhar = () => {
      tabela.replaceChildren();
      const titulos = criar("div", "linha-do-canal cabeca-dos-canais");
      for (const [classe, texto] of [["col-n", "nº"],
                                     ["col-nome", "nome no arquivo"],
                                     ["col-unidade", "unidade"],
                                     ["col-fase", "fase"],
                                     ["col-grupo", "grupo"],
                                     ["col-i", ""]]) {
        titulos.append(criar("span", classe, texto));
      }
      tabela.append(titulos);

      for (const x of canais) {
        const linha = criar("div", "linha-do-canal");
        linha.append(criar("span", "col-n", String(x.canal)));
        linha.append(criarNome("span", "col-nome", x.nome));
        linha.append(criar("span", "col-unidade",
                           x.unidade_mostrada || x.unidade || "—"));

        const fase = criar("span", "col-fase");
        fase.append(criar("span", null, x.fundamental || "—"));
        fase.append(vinculoDoCanal(x, correcoes, desenhar));
        linha.append(fase);

        // O grupo leva o lápis DA TRINCA: são duas deduções diferentes — qual
        // é a fase deste canal, e quais três canais formam o grupo — e cada
        // uma se corrige onde está escrita.
        const grupo = criar("span", "col-grupo");
        grupo.append(criar("span", null, x.grupo || "—"));
        // O lápis daqui muda ESTE canal de grupo. A trinca inteira se remonta
        // em «editar grupos» — são duas perguntas diferentes, e cada uma se
        // responde na tela que fala dela.
        if (trincaDoGrupo.size) {
          grupo.append(lapisDoGrupoDoCanal(x, trincaDoGrupo, desenhar));
        }
        linha.append(grupo);

        // O ⓘ: situação e observação, a um clique. Elas são texto corrido, e
        // texto corrido em duas colunas de uma tabela de vinte e uma linhas
        // vira parede — o que se lê aqui são o nome, a fase e o grupo.
        const marca = criar("button", "informacao col-i", "i");
        marca.type = "button";
        marca.setAttribute("aria-expanded", String(abertos.has(x.canal)));
        marca.setAttribute("aria-label", `detalhes de ${x.nome}`);
        marca.title = "situação deste canal e o que o OscLab observou nele";
        marca.addEventListener("click", () => {
          if (abertos.has(x.canal)) abertos.delete(x.canal);
          else abertos.add(x.canal);
          desenhar();
        });
        linha.append(marca);
        tabela.append(linha);

        if (!abertos.has(x.canal)) continue;
        const situacao = x.sem_sinal ? "sem sinal"
                       : (x.bloco === "outros" ? "em Outros" : "lido");
        const porque = x.sem_sinal
          ? "a entrada do relé não está cabeada: este canal lê só o ruído do "
            + "conversor, e o catálogo o esconde por padrão"
          : (x.bloco === "outros"
              ? `${x.motivo} — deste canal só existe a onda como o relé `
                + "gravou; eficaz, contínua e 60 Hz não significariam nada"
              : "canal senoidal com fase reconhecida: aceita todas as contas "
                + "do catálogo");
        const aberto = criar("div", `aberto-do-canal ${x.sem_sinal ? "mudo"
                             : (x.bloco === "outros" ? "atencao" : "bom")}`);
        aberto.append(criar("span", "situacao-do-canal", situacao));
        aberto.append(criar("span", "porque-do-canal", porque));
        tabela.append(aberto);
      }
    };
    desenhar();

    const gravar = criar("button", "aceitar", "gravar as correções");
    gravar.addEventListener("click", async () => {
      janelinha.close();
      if (correcoes.size) await gravarVinculos(correcoes);
    });

    const pe = criar("div", "pe-do-catalogo");
    pe.append(criar("span", "empurra"), gravar);

    janelinha.append(cabeca, tabela, pe);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
  }

  /** A unidade de um eixo, escrita na folga de cima.
   *
   * Menor e mais apagada que os números: quem lê o gráfico está lendo os
   * números, e a unidade é a legenda deles. Chamar mais atenção que a medida
   * seria inverter a hierarquia da tela.
   *
   * Devolve a fonte como estava — quem chama continua desenhando números
   * depois, e uma fonte trocada em silêncio no meio do desenho é dos defeitos
   * mais difíceis de achar.
   */
  function escreverUnidade(ctx, unidade, x, y, alinhamento) {
    if (!unidade) return;
    const fonte = ctx.font;
    const alinhado = ctx.textAlign;
    const opacidade = ctx.globalAlpha;
    ctx.font = "10px ui-monospace, Consolas, monospace";
    ctx.textAlign = alinhamento;
    ctx.globalAlpha = 0.65;
    ctx.fillText(unidade, x, y);
    ctx.font = fonte;
    ctx.textAlign = alinhado;
    ctx.globalAlpha = opacidade;
  }

  // --- o ímã dos cursores --------------------------------------------------

  //: Os pontos de atração da janela, achatados e em ordem de tempo. Guardado
  //: por desenho: durante um arrasto esta lista é consultada a cada quadro, e
  //: remontá-la ali seria refazer o mesmo trabalho sessenta vezes por segundo.
  let pontosGuardados = null;
  let seloDosPontos = -1;

  /** Todos os pontos em que o cursor pode grudar, em ordem de tempo.
   *
   * Os instantes vêm PRONTOS do servidor (`plot/imas.py`), onde há teste:
   * achar pico e transição é conta, e conta não se faz aqui. O que a tela faz
   * é escolher qual deles está mais perto do mouse — que é mira, não conta,
   * igual ao clique que escolhe um traço.
   */
  function pontosMagneticos() {
    if (pontosGuardados && seloDosPontos === seloDoDesenho) return pontosGuardados;
    const saida = [];
    for (const painel of (dados.paineis || [])) {
      if (painel.tipo === "fasorial" || painel.tipo === "triangulo") continue;
      // nem o fasorial nem o triângulo têm eixo do tempo
      for (const sinal of (painel.sinais || [])) {
        const nome = sinal.sinal || sinal.nome;
        for (const t of (sinal.picos || [])) {
          saida.push({ t, tipo: "pico", painel: painel.id, chave: sinal.id,
                       rotulo: `pico de ${nome}` });
        }
        for (const t of (sinal.zeros || [])) {
          saida.push({ t, tipo: "zero", painel: painel.id, chave: sinal.id,
                       rotulo: `zero de ${nome}` });
        }
      }
      for (const tira of (painel.tiras || [])) {
        for (const t of (tira.transicoes || [])) {
          saida.push({ t, tipo: "transicao", painel: painel.id,
                       chave: tira.id || tira.indice, rotulo: tira.nome });
        }
      }
    }
    if (dados.inicio_da_perturbacao !== null
        && dados.inicio_da_perturbacao !== undefined) {
      // Sem dono: não é de sinal nenhum, é do registro. Por isso ele some
      // quando há seleção — selecionar é dizer "obedeça a este aqui".
      saida.push({ t: dados.inicio_da_perturbacao, tipo: "inicio",
                   painel: null, chave: null, rotulo: "início da perturbação" });
    }
    saida.sort((a, b) => a.t - b.t);
    pontosGuardados = saida;
    seloDosPontos = seloDoDesenho;
    return saida;
  }

  /** O ponto em que o cursor deve grudar, ou `null` para ficar onde está.
   *
   * São três regras, nesta ordem:
   *
   * 0. **O menu do ímã diz que TIPO de ponto conta.** É a escolha de quem
   *    analisa, e vem antes de qualquer regra automática: com só as transições
   *    ligadas — que é o padrão — nada mais existe para o ímã.
   * 1. **Com seleção, só os pontos do que foi selecionado.** Selecionar já é o
   *    gesto de "obedeça a este"; é o que dá controle numa tela com quarenta
   *    tiras digitais, e é também o jeito de pedir o pico de uma curva
   *    específica no meio de um evento.
   * 2. **Sem seleção, os EVENTOS do registro ganham dos picos** — e ganham por
   *    existirem dentro do raio, não por estarem mais perto. Um pico é
   *    propriedade de uma curva e há dois por ciclo: com seis canais na tela,
   *    qualquer lugar onde se ponha o mouse tem um pico a meio pixel, e uma
   *    disputa por distância acabaria sempre no pico. Longe de qualquer
   *    evento, os picos voltam a valer — que é o caso de medir amplitude na
   *    pré-falta.
   *
   * O preço é uma faixa de um raio em volta de cada evento onde o pico não se
   * alcança sem selecionar a curva. Perto de um trip, o trip é quase sempre o
   * que se quer.
   */
  function grudarEm(t, a) {
    if (!magnetico || !a || t === null || t === undefined) return null;
    const pontos = pontosMagneticos();
    if (!pontos.length) return null;

    const raio = RAIO_DO_IMA * Math.abs(segundosPorPixel(a));
    if (!isFinite(raio) || raio <= 0) return null;

    // O menu do ímã manda primeiro: ele diz QUE TIPO de ponto conta. Depois
    // disso é que valem a seleção e a prioridade — as duas são sobre quais
    // pontos, entre os que contam, o cursor prefere.
    const ligado = (p) => atracoes.has(p.tipo);

    if (selecionados.length) {
      // Com seleção não há disputa: só existem os pontos do que foi escolhido.
      return maisPerto(pontos, t, raio,
        (p) => ligado(p) && selecionados.some((x) => x.painel === p.painel
                                                  && x.chave === p.chave));
    }
    // Sem seleção, os EVENTOS do registro ganham dos picos — e ganham por
    // existirem, não por estarem mais perto. Um pico é propriedade de uma
    // curva e há dois por ciclo: com seis canais na tela, qualquer lugar onde
    // se ponha o mouse tem um pico a meio pixel, e o trip — que é o que se
    // quer medir — nunca ganharia uma disputa por distância.
    const evento = (p) => p.tipo === "transicao" || p.tipo === "inicio";
    return maisPerto(pontos, t, raio, (p) => ligado(p) && evento(p))
        || maisPerto(pontos, t, raio, (p) => ligado(p) && !evento(p));
  }

  /** O ponto mais próximo de `t` dentro do raio, entre os que `serve` aceita.
   *
   * Busca binária pelo vizinho e uma varredura curta a partir dele: a lista
   * está em ordem de tempo, e o que interessa é só o que cabe no raio.
   */
  function maisPerto(pontos, t, raio, serve) {
    let lo = 0;
    let hi = pontos.length;
    while (lo < hi) {
      const meio = (lo + hi) >> 1;
      if (pontos[meio].t < t) lo = meio + 1; else hi = meio;
    }

    let melhor = null;
    let melhorDistancia = Infinity;
    const olhar = (i) => {
      const p = pontos[i];
      if (!p) return false;
      const d = Math.abs(p.t - t);
      if (d > raio) return false;              // daqui para fora, só piora
      if (!serve(p)) return true;
      // Empate desempatado pela precedência, e não pela ordem da lista: dois
      // pontos no mesmo pixel têm que dar sempre o mesmo resultado.
      const perto = d < melhorDistancia - 1e-12;
      const empate = Math.abs(d - melhorDistancia) <= 1e-12;
      if (perto || (empate && melhor
                    && PRECEDENCIA[p.tipo] < PRECEDENCIA[melhor.tipo])) {
        melhor = p;
        melhorDistancia = d;
      }
      return true;
    };
    for (let i = lo; i < pontos.length && olhar(i); i++) { /* para no raio */ }
    for (let i = lo - 1; i >= 0 && olhar(i); i--) { /* idem, para trás */ }
    return melhor;
  }

  /** Põe o cursor `k` em `t`, passando pelo ímã quando ele estiver aceso. */
  function grudarCursor(k, t, a) {
    const ponto = grudarEm(t, a);
    presos[k] = ponto;
    return ponto ? ponto.t : t;
  }

  //: Distância máxima, em pixels, entre o clique e o traço para o clique valer
  //: como escolha daquele sinal. Larga o bastante para a mão, estreita o
  //: bastante para não escolher o vizinho num gráfico com oito curvas.
  const PERTO = 10;

  /** Escolhe o sinal mais próximo do clique.
   *
   * Sem Ctrl, o clique TROCA a seleção — é o gesto de "quero olhar este".
   * Com Ctrl, acrescenta ou tira, que é como se monta uma comparação de duas
   * ou três fases. Clique no vazio, sem Ctrl, limpa tudo.
   */
  function escolherSinal(canvas, x, y, acumular = false) {
    const bloco = blocos.find((b) => b._canvas === canvas);
    if (!bloco || !bloco._painel) return;

    const painel = bloco._painel;
    // Painel sem traço não tem "sinal mais perto do clique": no fasorial e no
    // de harmônicos o clique quer dizer outra coisa — marcar a seta, marcar a
    // barra — e cada um trata o seu, no canvas dele. Sem esta porta,
    // `sinalPerto` lia `sinal.serie`, que nesses painéis não existe, e o
    // clique derrubava o tratador com um erro no console.
    if (painel.tipo === "harmonicos") {
      marcarBarra(canvas, x, y, acumular);
      return;
    }
    if (painel.tipo === "fasorial") return;
    const achado = painel.tipo === "digital"
      ? digitalPerto(painel, y)
      : sinalPerto(painel, canvas, x, y);

    if (!achado) {
      if (!acumular) marcarSelecao([]);
      return;
    }
    alternarSelecao(achado, acumular);
  }

  /** Põe ou tira um sinal da seleção. O MESMO comportamento nos três lugares
   * que selecionam: o traço da onda, o nome da legenda e o nome da tira
   * digital. Três gestos com três regras seria três coisas para aprender.
   *
   * Sem Ctrl o clique TROCA a seleção — é o gesto de "quero olhar este" — e
   * clicar de novo no único escolhido desmarca, que é como se desfaz sem ter
   * que mirar no vazio. Com Ctrl acumula, que é como se monta a comparação de
   * duas ou três fases.
   */
  function alternarSelecao(alvo, acumular) {
    const jaEstava = selecionados.some((s) => mesmoSinal(s, alvo));
    if (acumular) {
      marcarSelecao(jaEstava
        ? selecionados.filter((s) => !mesmoSinal(s, alvo))
        : [...selecionados, alvo]);
      return;
    }
    marcarSelecao(jaEstava && selecionados.length === 1 ? [] : [alvo]);
  }

  function marcarSelecao(novos) {
    selecionados = novos;
    repintar();
    marcarLegenda();
  }

  /** A tira digital sob o clique. Não há distância a medir: a faixa é a tira. */
  function digitalPerto(painel, y) {
    const k = Math.floor((y - MARGEM.topo) / TIRA);
    const tira = painel.tiras[k];
    if (!tira) return null;
    return { painel: painel.id, tipo: "digital", chave: tira.id || tira.indice,
             nome: tira.nome };
  }

  /** O sinal desenhado mais perto de `(x, y)` naquele painel, ou `null`.
   *
   * Compara pela distância VERTICAL na coluna sob o cursor, e não pela
   * distância ao traço inteiro: num gráfico de onda as curvas se cruzam o
   * tempo todo, e o que o olho entende por "cliquei nesta" é a que está na
   * altura do clique naquele instante.
   */
  function sinalPerto(painel, canvas, x, y) {
    const cssLargura = canvas.parentElement.clientWidth;
    const x0 = MARGEM.esq;
    const x1 = cssLargura - MARGEM.dir;
    const y0 = MARGEM.topo;
    const y1 = ALTURA - 4;
    if (x1 <= x0 || !dados.tempo.length) return null;

    const t = dados.de + (x - x0 - arrastoPx)
            * ((dados.ate - dados.de) / (x1 - x0));
    // A coluna mais próxima no eixo reduzido. Busca linear: são 900 colunas, e
    // isto roda uma vez por clique.
    let i = 0;
    let melhorT = Infinity;
    for (let k = 0; k < dados.tempo.length; k++) {
      const d = Math.abs(dados.tempo[k] - t);
      if (d < melhorT) { melhorT = d; i = k; }
    }

    // A MESMA divisão em pistas que o desenho usa. Repetir a conta aqui, ou
    // esquecer de repeti-la, é como o clique passa a marcar o sinal de cima
    // quando se mira o de baixo — sem erro nenhum na tela.
    let achado = null;
    let menor = PERTO;
    for (const pista of pistasDoPainel(painel, y0, y1)) {
      const emY = (v, minimo, maximo) =>
        pista.y1 - ((v - minimo) / (maximo - minimo || 1))
                 * (pista.y1 - pista.y0);
      for (const sinal of pista.sinais) {
        const eixo = sinal.eixo === "dir" ? painel.eixo_dir : painel;
        if (!eixo) continue;
        // Três colunas: a onda sobe muito dentro de uma coluna só, e o traço
        // desenhado liga uma à outra.
        // Sinal de outro IED tem o SEU eixo de tempo: a coluna é a dele.
        const meu = sinal.tempo ? colunaMaisProxima(sinal.tempo, t) : i;
        for (const k of [meu - 1, meu, meu + 1]) {
          const v = sinal.serie[k];
          if (v === null || v === undefined) continue;
          const d = Math.abs(emY(v, eixo.minimo, eixo.maximo) - y);
          if (d < menor) {
            menor = d;
            achado = { painel: painel.id, tipo: "sinal", chave: sinal.id,
                       nome: sinal.sinal || sinal.nome };
          }
        }
      }
    }
    return achado;
  }

  /** Tira da tela tudo que está selecionado, de uma vez.
   *
   * Nada some do registro: o sinal volta pelo «+ sinal», onde aparece
   * desmarcado, e o Ctrl+Z traz tudo de volta de um golpe.
   */
  function apagarSelecionados() {
    if (!selecionados.length) return;
    guardarParaDesfazer();

    for (const { painel: id, chave } of selecionados) {
      const painel = painelPorId(id);
      if (!painel) continue;
      painel.sinais = painel.sinais.filter((x) => x !== String(chave));
    }
    selecionados = [];
    carregar();
  }

  /** Repinta o que já está montado. É o que roda a cada movimento do mouse. */
  /** Repinta no PRÓXIMO quadro, e uma vez só.
   *
   * Arrastando um cursor, `repintar` era chamado duas ou três vezes por
   * movimento do mouse: uma no `pointermove` e outra quando a leitura do
   * servidor voltava. Cada chamada redesenha TODOS os painéis, e o navegador
   * só mostra um quadro por vez de qualquer jeito — as outras duas eram
   * desenho jogado fora, e desenho jogado fora numa oscilografia de duas mil
   * amostras é o atraso que a mão sente.
   *
   * Pedir um quadro junta as chamadas: quantas vierem antes de o navegador
   * pintar viram uma. Nada muda no resultado — só deixa de ser desenhado o que
   * seria apagado em seguida.
   */
  /** Dá ao canvas o tamanho em pixels de verdade — e só REALOCA se mudou.
   *
   * Atribuir `width` realoca o quadro de pixels mesmo com o valor igual, e
   * isso rodava em todo painel a cada movimento do cursor: oito painéis de
   * 1400 px são uns quinze megabytes jogados fora por quadro, e o coletor de
   * lixo cobrava em engasgo — o cursor «pesado» que ele sentia ao arrastar.
   * Com o tamanho igual, `reset()` limpa e zera o estado do contexto (traço,
   * opacidade, fonte), que é o que a atribuição fazia de útil. */
  function dimensionar(canvas, largura, altura) {
    if (canvas.width !== largura || canvas.height !== altura) {
      canvas.width = largura;
      canvas.height = altura;
      return;
    }
    const ctx = canvas.getContext("2d");
    if (ctx.reset) ctx.reset();
    else canvas.width = largura;
  }

  let quadroPedido = 0;
  function repintar() {
    if (quadroPedido) return;
    quadroPedido = requestAnimationFrame(() => {
      quadroPedido = 0;
      repintarAgora();
    });
  }

  /** Deixa as duas colunas de um par com a MESMA altura de cabeçalho e de
   *  corpo — e, por consequência, com as tabelas na mesma linha.
   *
   * Elas se desencontravam por dois motivos, e os dois aparecem em registro
   * de verdade: o cabeçalho de um lado quebra numa linha a mais (o nome da
   * referência de ângulo é comprido, e o ▲▼× desce), e o corpo de um lado
   * ganha as notas de rodapé do painel («G1 — …», «G2 — …») que o outro não
   * tem. Qualquer um dos dois empurra o desenho e a tabela daquele lado para
   * baixo, e o par deixa de se ler como um par.
   *
   * Medir e igualar, e não adivinhar com uma altura fixa: a altura depende do
   * nome do canal, do zoom e da fonte, e um número escrito aqui estaria
   * errado no primeiro registro de nome comprido — que é justamente o caso
   * que gerou o problema. É a mesma regra das molduras do cursor, logo
   * abaixo: quem decide é a medida.
   */
  function alinharPares() {
    for (const par of area.querySelectorAll(".par-com-moldura")) {
      const colunas = [...par.querySelectorAll(":scope > .par-fasorial > .grafico")];
      if (colunas.length < 2) continue;
      //: Primeiro a simetria do ▲▼×: se a fileira de botões de QUALQUER um
      //: dos dois estourou e o grupo caiu para a linha de baixo, ele desce
      //: nos dois — mesmo no que caberia. Meia simetria é pior que nenhuma:
      //: o olho compara os dois cabeçalhos lado a lado.
      const titulos = colunas
        .map((c) => c.querySelector(":scope > .grafico-titulo"))
        .filter(Boolean);
      for (const t of titulos) t.classList.remove("arranjo-embaixo");
      const quebrou = titulos.some((t) => {
        const arranjo = t.querySelector(":scope > .arranjo");
        const antes = arranjo && arranjo.previousElementSibling;
        if (!arranjo || !antes) return false;
        // Linha de baixo = topo do grupo abaixo do topo do vizinho anterior.
        return arranjo.getBoundingClientRect().top
             > antes.getBoundingClientRect().top + 2;
      });
      if (quebrou) for (const t of titulos) t.classList.add("arranjo-embaixo");

      for (const classe of ["grafico-titulo", "corpo-fasorial"]) {
        const pedacos = colunas
          .map((c) => c.querySelector(`:scope > .${classe}`))
          .filter(Boolean);
        if (pedacos.length < 2) continue;
        for (const el of pedacos) el.style.minHeight = "";
        const alto = Math.max(...pedacos.map((el) => el.getBoundingClientRect().height));
        for (const el of pedacos) el.style.minHeight = `${alto}px`;
      }
    }
  }

  function repintarAgora() {
    //: ANTES das molduras: igualar as colunas muda a altura do cabeçalho, e a
    //: moldura de cima é posicionada por medida em cima dessa altura.
    alinharPares();
    for (const b of blocos) {
      if (!b._painel) continue;
      if (b._painel.tipo === "digital") {
        pintarDigitais(b._canvas, b._painel, b._ultimo);
      }
      else if (b._painel.tipo === "fasorial") pintarFasorial(b._canvas, b._painel);
      else if (b._painel.tipo === "harmonicos") pintarHarmonicos(b._canvas, b._painel);
      else if (b._painel.tipo === "triangulo") pintarTriangulo(b._canvas, b._painel);
      else if (b._painel.tipo === "impedancia") pintarImpedancia(b._canvas, b._painel);
      else if (b._painel.tipo === "complexo") pintarComplexo(b);
      else if (b._painel.tipo === "alfa") pintarAlfa(b);
      else if (b._painel.tipo === "diferencial") pintarDiferencial(b);
      else pintar(b._canvas, b._painel, b._ultimo);
      if (b._molduras) pintarMolduras(b);
    }
    atualizarBarra();
    //: E de novo no quadro SEGUINTE, só as molduras.
    //:
    //: A moldura copia a largura e a esquerda do desenho dos analógicos
    //: (`refDoDesenho`), e aqui ela é medida no meio da pintura — antes de o
    //: navegador ter assentado o que esta mesma passagem acabou de mudar.
    //: Quando o nome de um sinal é comprido, o cabeçalho do par muda de
    //: altura, a tabela aparece ou some e a largura dos painéis de cima
    //: muda junto; a moldura ficava com a medida de antes, deslocada, até a
    //: próxima pintura — era por isso que mexer no cursor «consertava».
    //:
    //: Não é laço: `pintarMolduras` só escreve quando o valor mudou, e não
    //: chama `repintar`. No caso comum a segunda medida é igual à primeira e
    //: nada é escrito.
    requestAnimationFrame(() => {
      //: E, antes delas, confere se algum DESENHO ficou com a largura errada.
      //:
      //: Os painéis escrevem a largura do canvas em pixels, medida do pai na
      //: hora de pintar (`canvas.style.width`). Se a medida saiu antes de o
      //: navegador acomodar o que essa mesma passagem mudou — um cabeçalho
      //: que ganhou uma linha por causa de um nome comprido, uma tabela que
      //: apareceu —, o canvas fica mais estreito que o painel e assim
      //: permanece, porque pixel escrito não acompanha o pai. A moldura copia
      //: essa largura e acompanha o erro. Repintar com a medida de agora
      //: resolve os dois, e é o que mexer no cursor fazia por acidente.
      if (confereLarguras()) return;   // repintou: as molduras vão junto
      for (const b of blocos) if (b._molduras) pintarMolduras(b);
    });
  }

  /** Repinta os painéis cujo canvas não tem mais a largura do pai.
   *
   * Devolve `true` se repintou algum — e aí as molduras já foram refeitas
   * dentro do `repintarAgora`, não há o que fazer depois.
   */
  //: Quantas correções de largura seguidas já se tentou. UMA, e só: se depois
  //: de repintar a largura ainda não bater, repintar de novo não vai bater
  //: também — e um laço de repinturas é pior que um desenho estreito.
  let tentouLargura = 0;

  function confereLarguras() {
    let torto = false;
    for (const b of blocos) {
      if (!b._painel || !b._canvas || !b._canvas.parentElement) continue;
      //: O fasorial e o triângulo têm lado FIXO (ver `RAIO_FASORIAL`): a
      //: largura deles não sai do pai, e compará-la com ele acusaria um erro
      //: que não existe.
      if (b._painel.tipo === "fasorial" || b._painel.tipo === "triangulo"
          || b._painel.tipo === "complexo" || b._painel.tipo === "alfa") continue;
      const pai = b._canvas.parentElement.clientWidth;
      const tem = Math.round(parseFloat(b._canvas.style.width) || 0);
      if (pai > 60 && Math.abs(pai - tem) > 1) { torto = true; break; }
    }
    if (!torto) { tentouLargura = 0; return false; }
    if (tentouLargura >= 1) { tentouLargura = 0; return false; }
    tentouLargura += 1;
    repintarAgora();
    return true;
  }

  /** O seletor de arranjo: `agrupados` × `um por gráfico`.
   *
   * Duas teclas e não um botão que troca de palavra, como o da medida. A
   * diferença: na medida há um estado e um verbo («ver RMS»); aqui há dois
   * arranjos que coexistem como ideia, e ver os dois lado a lado com o aceso
   * marcado diz, sem clicar, que a outra opção existe. É a mesma forma do
   * `secundário | primário` do cabeçalho, pela mesma razão.
   *
   * Some com menos de dois sinais: empilhar um sinal só é o próprio gráfico.
   * E um botão que não faz nada é pior que botão nenhum — quem clicar vai
   * procurar o que mudou.
   */
  function seletorDoArranjo(painel) {
    const caixa = criar("span", "seletor-do-arranjo");
    if ((painel.sinais || []).length < 2) {
      caixa.hidden = true;
      return caixa;
    }
    const meu = painelPorId(painel.id);
    const empilhado = !!(meu && meu.empilhado);
    for (const [quero, rotulo, dica] of [
      [false, "agrupados",
       "Os sinais sobrepostos no mesmo gráfico, na mesma escala. É como se "
       + "compara a defasagem entre as fases e se vê qual delas afundou."],
      [true, "um por gráfico",
       "Um sinal por pista, mesma escala e mesmo eixo de tempo. É como se "
       + "olha a assimetria e o instante de extinção de CADA fase sem os três "
       + "traços cruzando no mesmo zero."],
    ]) {
      const b = criar("button", `medida tecla-do-arranjo${
        empilhado === quero ? " aceso" : ""}`);
      b.type = "button";
      b.append(iconeDoArranjo(quero), criar("span", null, rotulo));
      b.title = dica;
      b.setAttribute("aria-pressed", empilhado === quero ? "true" : "false");
      if (empilhado !== quero) {
        b.addEventListener("click", () => alternarEmpilhado(painel.id));
      }
      caixa.append(b);
    }
    return caixa;
  }

  /** «ver amostras»: os pontinhos de cada amostra sobre o traço.
   *
   * Mora na engrenagem porque é ajuste, não leitura: liga-se uma vez para
   * conferir se a resolução do registro dá conta do que se está medindo, e
   * não se toca mais.
   *
   * O botão diz quando NÃO vai aparecer nada, e por quê. São duas razões
   * diferentes, e nenhuma delas é defeito:
   *
   *   * o traço na tela é mínimo e máximo por coluna de pixel (`reduzido`) —
   *     não existe «a amostra» para marcar, existe o par que coube no pixel;
   *   * as amostras estão a menos de `PASSO_DA_AMOSTRA` pixels uma da outra,
   *     e os pontos virariam uma faixa cheia em cima da onda.
   *
   * Nos dois casos a saída é a mesma: ampliar. Por isso o aviso fala em
   * ampliar em vez de dizer que o botão não funcionou.
   */
  function botaoDasAmostras(painel) {
    const meu = painelPorId(painel.id) || {};
    const b = criar("button", "medida", "ver amostras");
    b.type = "button";
    vestirBotaoDasAmostras(b, !!meu.amostras);
    b.addEventListener("click", () => alternarAmostras(painel.id, b));
    return b;
  }

  /** O estado do botão, separado de quem o cria.
   *
   * Separado porque o clique NÃO refaz o bloco (ver `alternarAmostras`): é
   * este mesmo botão, já na tela, que tem de passar a aceso — senão o gesto
   * não tem resposta nenhuma, que foi o que aconteceu.
   *
   * `escolhido` é a classe de aceso dos botões de gráfico em toda a tela;
   * `aceso` é a dos seletores de duas teclas, e não tem regra para `.medida`
   * — era por isso que o botão continuava apagado depois de ligado.
   */
  function vestirBotaoDasAmostras(b, ligado) {
    b.classList.toggle("escolhido", ligado);
    b.setAttribute("aria-pressed", ligado ? "true" : "false");
    b.title = ligado
      ? "Os pontos aparecem quando houver espaço para eles: é preciso ampliar "
        + "até as amostras ficarem a mais de "
        + `${PASSO_DA_AMOSTRA} px uma da outra. Clique para desligar.`
      : "Marca cada amostra do arquivo sobre o traço. Só aparece com zoom "
        + "suficiente — é o jeito de ver se a taxa do registro dá conta do "
        + "que você está medindo.";
  }

  function bloco(painel, ultimo) {
    const el = criar("section", "grafico");

    // A medida é de CADA painel: corrente em RMS e tensão em instantâneo ao
    // mesmo tempo é leitura comum numa falta. Discreto de propósito — é escolha
    // de vista, não um dado do registro. Ela manda nos canais do IED que estão
    // aqui; sinal escolhido à mão carrega a própria grandeza.
    // `botaoMedida`, e não `medida`: `medida` é o pacote da leitura dos
    // cursores, lá em cima. Duas coisas diferentes com o mesmo nome é como se
    // lê uma pelo outra ao mexer no arquivo meses depois.
    // O botão mostra o que o CLIQUE VAI DAR, não o estado de agora.
    //
    // Era o estado: escrevia `RMS` quando o gráfico estava em RMS. Lido
    // isolado, isso é indistinguível de uma promessa — «apertar aqui dá RMS» —
    // e a cada clique a palavra trocava para a que acabara de deixar de valer.
    // Botão é verbo. Com o desenho ao lado, a leitura fica direta: vendo onda,
    // ele oferece o eficaz; vendo eficaz, oferece a onda.
    //
    // E os desenhos são os MESMOS do cartão de sinal (`iconeDaFolha`): o
    // engenheiro aprende a figurinha uma vez e a reconhece nas duas telas. A
    // onda sai suja com o filtro apagado e limpa com ele aceso, como lá.
    const vaiDar = painel.medida === "rms" ? "instantaneo" : "rms";
    const botaoMedida = criar("button", "medida com-icone");
    botaoMedida.append(iconeDaFolha(vaiDar, !!dados.filtro),
                       criar("span", null,
                             vaiDar === "rms" ? "ver RMS" : "ver onda"));
    // Travado quando não há canal do IED neste gráfico para ele mandar — num
    // painel só de componentes simétricas, por exemplo, que são fasor e já
    // são eficazes. Fica visível e inerte, com a explicação no title, igual
    // ao botão do filtro num registro que o relé já filtrou: esconder
    // deixaria o usuário procurando um botão que ele viu nos outros gráficos.
    botaoMedida.disabled = painel.medida_aplicavel === false;
    botaoMedida.title = botaoMedida.disabled
      ? "Não há canal do IED neste gráfico para medir em eficaz. As "
        + "componentes simétricas são fasor e já saem em eficaz; sinais do "
        + "OscLab carregam a grandeza no próprio nome."
      : vaiDar === "rms"
        ? "Agora: valor instantâneo, amostra a amostra. Clique para ver o "
          + "eficaz da janela de um ciclo dos canais do IED deste gráfico."
        : "Agora: eficaz da janela de um ciclo. Clique para ver o valor "
          + "instantâneo, amostra a amostra.";
    botaoMedida.addEventListener("click", () => alternarMedida(painel.id));

    // Acrescentar sinal a ESTE painel. O catálogo inteiro vem no pacote da
    // janela; a busca só o separa em abas.
    const mais = criar("button", "medida", "+ sinal");
    mais.title = "Acrescentar um canal do IED ou uma variável do OscLab a "
               + "este gráfico.";
    mais.addEventListener("click", () => abrirCatalogo(painel));

    el.append(cabecalhoDoPainel(painel,
                                [botaoMedida, mais, botaoDeConta(painel),
                                 seletorDoArranjo(painel),
                                 ...engrenagemDoPainel(painel, () => {
                                   return [botaoDasAmostras(painel)];
                                 })]));

    // O que não coube: sinal de uma terceira unidade, que não tem eixo.
    for (const aviso of (painel.avisos || [])) {
      el.querySelector(".grafico-titulo").append(
        criar("span", "aviso-extra", aviso));
    }

    const legenda = criar("ul", "legenda");
    for (const sinal of (painel.sinais || [])) {
      const item = criar("li");
      item.dataset.painel = painel.id;
      item.dataset.chave = sinal.id;
      const cor = corDoSinal(sinal, painel);
      const marca = criar("span", "marca");
      marca.style.background = cor;
      item.append(marca);
      const selo = seloDoIed(sinal.ied);
      if (selo) item.append(selo);

      // UM nome, escrito normal. Houve dois: o do arquivo à esquerda e o
      // nosso numa moldura em itálico e colorida ao lado, porque o nosso era
      // `IA` e o do arquivo `IAW` — duas nomenclaturas que precisavam ser
      // vistas juntas. Desde que o nome do sinal PASSOU A SER o do arquivo
      // (`IAW`, `IAW · 60Hz`), a moldura repetia a mesma palavra ao lado dela
      // mesma; e quando o filtro entrava, sobrava só a moldura, e a legenda
      // trocava de estilo conforme o botão.
      const escrito = sinal.sinal || sinal.nome || "";
      if (escrito) {
        const nome = criarNome("span", "nome", escrito);
        nome.title = (sinal.descricao || "")
                   + (sinal.familia === "canal" ? "" : deQualCanal(sinal));
        item.append(nome);
      } else if (sinal.fase) {
        // Sem nome nenhum, a fase é tudo que dá para dizer.
        item.append(criar("span", "fase", sinal.fase));
      }

      // A etiqueta marca a EXCEÇÃO, não a regra. Com o cabeçalho já dizendo
      // "primário", carimbar "prim." em todos os canais é ruído; o que precisa
      // saltar aos olhos é o canal que NÃO pôde ser convertido.
      // Pelo ÍNDICE, e não pelo nome do arquivo: `IA RMS` não mostra o nome
      // do canal, mas continua vindo de um canal que pode não ter relação de
      // TC/TP declarada — e o aviso é sobre o canal.
      if (sinal.indice !== null && sinal.indice !== undefined) {
        if (dados.lado_pedido === "arquivo") {
          if (sinal.lado === "primario") item.append(criar("span", "lado", "prim."));
        } else if (sinal.lado !== dados.lado_pedido) {
          const aviso = criar("span", "lado sem-relacao",
                              sinal.lado === "primario" ? "prim." : "sec.");
          aviso.title = "O arquivo não declara a relação de TC/TP deste canal, "
                      + "então o valor ficou como está — em "
                      + (sinal.lado === "primario" ? "primário." : "secundário.");
          item.append(aviso);
        }
      }

      if (sinal.eixo === "dir") {
        const ladoDir = criar("span", "lado", `→ ${sinal.unidade}`);
        ladoDir.title = "Este sinal está na escala da DIREITA, porque a "
                      + "unidade dele não é a do gráfico — a altura dele não "
                      + "se compara com a dos outros traços.";
        item.append(ladoDir);
      }

      // Sem × aqui: o nome da legenda é o alvo de ESCOLHER, e um alvo de
      // apagar a poucos pixels dele é o par de botões que mais se erra. Tirar
      // um sinal é escolher e apertar Delete, ou desmarcá-lo no «+ sinal».
      selecionavel(item, painel, sinal.id);
      legenda.append(item);
    }
    el.append(legenda);

    // A onda e a tabelinha daquele painel, lado a lado e alinhadas. As células
    // existem desde já, com traços: criá-las ao pôr o cursor empurraria o
    // gráfico e a onda fugiria de debaixo do mouse no meio da medição.
    const corpo = criar("div", "grafico-corpo");
    const caixa = criar("div", "tela");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    corpo.append(caixa, tabelinha(painel));
    el.append(corpo);

    if (!(painel.sinais || []).length) {
      el.append(criar("p", "vazio",
        "Nenhum sinal neste gráfico. Use o «+ sinal» para escolher o que "
        + "você quer ver aqui."));
    }

    // O rodapé: de que canais do ARQUIVO saiu o que está aqui. É a
    // contrapartida do `[1]` — o ordinal não depende de fabricante nenhum, e é
    // por não depender que ele não diz nada sozinho. O texto nasce no Python,
    // como todo nome, porque tem que ser o mesmo no gráfico e no relatório.
    if ((painel.rodape || []).length) {
      const rodape = criar("div", "rodape-do-painel");
      for (const linha of painel.rodape) rodape.append(criar("div", null, linha));
      el.append(rodape);
    }

    el._canvas = canvas;
    el._painel = painel;
    el._ultimo = ultimo;
    return el;
  }

  /** O traço de um sinal, reto ou suavizado conforme o registro.
   *
   * ## Por que suavizar, e só às vezes
   *
   * Ligar duas amostras com uma RETA desenha menos onda do que existe: no meio
   * do caminho entre duas amostras, a corda passa abaixo da senoide. Quanto,
   * depende só de quantas amostras há por ciclo:
   *
   *      4 amostras/ciclo   -> 29,3 % abaixo
   *      8 amostras/ciclo   ->  7,6 %
   *     16 amostras/ciclo   ->  1,9 %
   *     33 amostras/ciclo   ->  0,4 %
   *
   * É por isso que um CEV filtrado (8 por ciclo) aparece como um polígono
   * pontudo e o COMTRADE bruto do mesmo evento (33 por ciclo) aparece redondo.
   * Não é defeito do arquivo nem da leitura: é o que oito pontos ligados por
   * retas desenham.
   *
   * A curva de Catmull-Rom reconstrói a senoide com 0,9 % de erro a 8 amostras
   * por ciclo — trinta vezes melhor que a reta —, passa exatamente por todas as
   * amostras e **não ultrapassa o pico** delas.
   *
   * ## Por que NÃO em todo registro
   *
   * Num sinal com descontinuidade de verdade — a entrada de uma falta num
   * registro bruto — uma curva suave passaria por fora do degrau e desenharia
   * um pico que não existe. Registro filtrado não tem degrau: o filtro do relé
   * os removeu, e a onda ali É uma senoide de 60 Hz. Daí a regra: suaviza-se
   * só onde há POUCA amostra por ciclo, que é exatamente onde o relé filtrou.
   *
   * E não se suaviza traço REDUZIDO: com mais amostras que pixels, o desenho
   * já é mínimo e máximo por coluna, e arredondar isso inventaria forma onde
   * há estatística.
   */
  const AMOSTRAS_PARA_SUAVIZAR = 8;

  function suavizavel() {
    return !!dados && !dados.reduzido
        && (dados.amostras_da_janela_do_fasor || 0) > 0
        && dados.amostras_da_janela_do_fasor <= AMOSTRAS_PARA_SUAVIZAR;
  }

  function tracar(ctx, serie, tempo, emX, paraY) {
    const suave = suavizavel();
    const pts = [];
    const despejar = () => {
      if (!pts.length) return;
      ctx.moveTo(pts[0].x, pts[0].y);
      if (!suave || pts.length < 3) {
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
      } else {
        // Catmull-Rom escrita como Bézier cúbica, que é o que o canvas sabe
        // desenhar. Os pontos de controle ficam a um sexto da distância até o
        // vizinho de cada lado — é a forma fechada da conversão, não um ajuste
        // à mão.
        for (let i = 0; i < pts.length - 1; i++) {
          const p0 = pts[Math.max(i - 1, 0)];
          const p1 = pts[i];
          const p2 = pts[i + 1];
          const p3 = pts[Math.min(i + 2, pts.length - 1)];
          ctx.bezierCurveTo(
            p1.x + (p2.x - p0.x) / 6, p1.y + (p2.y - p0.y) / 6,
            p2.x - (p3.x - p1.x) / 6, p2.y - (p3.y - p1.y) / 6,
            p2.x, p2.y);
        }
      }
      pts.length = 0;
    };

    for (let i = 0; i < serie.length; i++) {
      const v = serie[i];
      // Buraco na série corta o traço: cada pedaço é desenhado sozinho, senão
      // a curva atravessaria o vazio ligando os dois lados dele.
      if (v === null) { despejar(); continue; }
      pts.push({ x: emX(tempo[i]), y: paraY(v) });
    }
    despejar();
  }

  /** O lápis que abre a correção da trinca de uma componente simétrica. */
  /** `I` ou `V` para uma trinca, tirada da UNIDADE dos canais dela.
   *
   * Sem isto a janelinha de corrigir uma trinca de tensão prometia arrumar
   * «3I0, I1 e I2» — os nomes da trinca de corrente. Quem lê um texto desses
   * numa tela de tensão fica sem saber se o programa entendeu o que está
   * fazendo, e a resposta certa é que não estava dizendo nada: era texto fixo.
   */
  function grandezaDaTrinca(conjunto) {
    const unidade = (conjunto || {}).unidade;
    const canal = (dados.catalogo || []).find(
      (c) => c.familia === "canal" && c.unidade === unidade);
    return (canal && canal.grandeza_do_canal) === "V" ? "V" : "I";
  }

  /** O lápis da coluna GRUPO, na tela «Canais»: muda só este canal de grupo.
   *
   * Era o lápis da trinca inteira — a janelinha de três campos. Tela errada:
   * quem está olhando a linha do `IAX` quer dizer «este canal é do G1», não
   * remontar o G2 todo. A trinca inteira continua editável em «editar
   * grupos», que é a tela que fala de grupo.
   *
   * Como UM canal basta: ele já tem fase. «O canal 3, que é fase A, vai para
   * o G1» é uma instrução completa — escreve no lugar da fase A do G1. É por
   * isso que o lápis da FASE vem antes na mesma linha: sem fase, este aqui
   * não tem onde encaixar, e ele diz isso.
   *
   * O canal que ocupava aquela vaga fica de fora da trinca. É consequência
   * legítima — alguém estava errado ali —, e a tela «editar grupos» mostra o
   * resultado. O que não se aceita é repetir canal dentro da mesma trinca,
   * que é trinca nenhuma.
   */
  function lapisDoGrupoDoCanal(x, trincaDoGrupo, redesenhar) {
    const lapis = criar("button", "editar-vinculo", "✎");
    lapis.type = "button";
    const temFase = VAGAS_DE_TRINCA.includes(faseDoCanal(x));
    lapis.title = temFase
      ? `A que grupo trifásico ${x.nome} pertence. Muda só este canal de `
        + "grupo — para remontar a trinca inteira, use «editar grupos»."
      : "Este canal não ocupa vaga em trinca nenhuma: só A, B e C (ou AB, BC "
        + "e CA, entre fases) entram na conta. Corrija a fase primeiro, no "
        + "lápis ao lado.";
    lapis.setAttribute("aria-label", `mudar ${x.nome} de grupo`);
    if (!temFase) lapis.disabled = true;
    lapis.addEventListener("click", (evento) => {
      evento.preventDefault();
      evento.stopPropagation();
      abrirGrupoDoCanal(x, trincaDoGrupo, redesenhar);
    });
    return lapis;
  }

  /** A fase efetiva do canal: a corrigida, se houver, senão a deduzida.
   *
   * `x.fundamental` vem como `IA`, `VN`, `IAB` — grandeza na frente, fase
   * atrás. Tira-se a PRIMEIRA letra, e não se pega a última: com a última,
   * `IAB` viraria fase `B`, e o canal iria ocupar a vaga da fase B de uma
   * trinca onde ele não é fase nenhuma.
   */
  function faseDoCanal(x) {
    const texto = String(x.fundamental || "").toUpperCase();
    return texto ? texto.slice(1) : "";
  }

  function abrirGrupoDoCanal(x, trincaDoGrupo, redesenhar) {
    const fase = faseDoCanal(x);
    // Só os grupos da MESMA unidade: pôr um ampère numa trinca de volt não é
    // trinca de coisa nenhuma, e oferecer isso seria oferecer um erro que o
    // programa depois não teria como recusar.
    // E só os da mesma BASE: um `VAB` não tem vaga numa trinca de fase, e um
    // `VA` não tem vaga numa trinca em delta. Oferecer isso seria oferecer
    // uma trinca que mistura volt de fase com volt de linha — e Fortescue
    // sobre essa mistura devolve três números plausíveis e sem significado.
    const emDelta = LACOS.includes(fase);
    const possiveis = [...trincaDoGrupo.entries()]
      .filter(([, t]) => (t || {}).unidade === x.unidade
                      && (((t || {}).base === "linha") === emDelta));

    // `curta`: esta janelinha tem UM campo. Sem isso ela herda a altura da
    // de corrigir trinca, que tem três, e sobra meia tela de vazio.
    const janelinha = criar("dialog", "busca trincas curta");
    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem mudar nada";
    fechar.addEventListener("click", () => janelinha.close());
    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, `A que grupo ${x.nome} pertence`), fechar);
    // Uma linha, e só. A janelinha tem UM campo e UM botão; três linhas de
    // texto em cima faziam a explicação ocupar mais espaço que a escolha.
    // O resto da regra — quem sai da trinca, e que para remontar a trinca
    // inteira existe «editar grupos» — ficou no hover da lista, onde quem
    // tiver dúvida vai procurar e quem não tiver não precisa desviar.
    const comoE = LACOS.includes(fase) ? `é o laço ${fase}` : `é fase ${fase}`;
    const ajuda = criar("p", "ajuda-rotulo",
      `${x.nome} ${comoE}. Ao lado de cada grupo, quem ocupa essa vaga hoje.`);

    const lista = criar("div", "achados");
    const item = criar("div", "achado rotulo-trinca");
    const escolha = document.createElement("select");
    escolha.className = "escolher-fase";
    if (!possiveis.length) {
      // Acontece de verdade: o primeiro canal que alguém marca como `VAB` num
      // arquivo sem nenhuma trinca em delta. Dizer isso é melhor que abrir uma
      // lista vazia, que se lê como defeito do programa.
      escolha.disabled = true;
      const o = document.createElement("option");
      o.textContent = emDelta
        ? "nenhum grupo entre fases neste registro"
        : "nenhum grupo desta unidade neste registro";
      escolha.append(o);
    }
    for (const [nome, trinca] of possiveis) {
      const o = document.createElement("option");
      o.value = nome;
      const ocupante = (dados.catalogo || []).find(
        (c) => c.familia === "canal"
            && c.canal === (trinca.canais || {})[fase]);
      // Curto de propósito: `G2 — IAX`. A frase inteira («a vaga da fase A
      // é de IAX») já está no parágrafo de ajuda logo acima, e repetida em
      // cada opção ela virava um texto que ninguém lê — numa lista, o que se
      // compara é a ponta direita, e ali só interessa QUEM está na vaga.
      o.textContent = nome === x.grupo
        ? `${nome} — atual`
        : `${nome} — ${ocupante ? ocupante.nome : "vaga livre"}`;
      escolha.append(o);
    }
    escolha.value = x.grupo || (possiveis[0] || [""])[0];
    escolha.title = `Põe ${x.nome} na vaga da fase ${fase} do grupo `
                  + "escolhido. O canal que estava nessa vaga sai da trinca — "
                  + "para remontar a trinca inteira de uma vez, use «editar "
                  + "grupos».";
    item.append(criar("span", "nome", "grupo"), escolha);
    lista.append(item);

    const recado = criar("p", "ajuda-rotulo", "");
    const aplicar = criar("button", "aceitar", "gravar");
    aplicar.type = "button";
    aplicar.addEventListener("click", async () => {
      const alvo = escolha.value;
      const trinca = trincaDoGrupo.get(alvo);
      if (!trinca || alvo === x.grupo) { janelinha.close(); return; }
      const canais = { ...(trinca.canais || {}) };
      canais[fase] = x.canal;
      if (new Set(Object.values(canais)).size < 3) {
        recado.textContent = "Este canal já está em outra fase deste grupo — "
                           + "as três têm que ser canais diferentes.";
        return;
      }
      janelinha.close();
      await gravarTrinca(trinca.chave, canais);
    });

    janelinha.append(cabeca, ajuda, lista, recado, aplicar);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
  }

  function lapisDaTrinca(x) {
    const lapis = criar("button", "editar-vinculo", "✎");
    lapis.type = "button";
    const g = grandezaDaTrinca(x.conjunto);
    lapis.title = `Corrigir de que canais sai ${x.nome}. `
                + "Quais três formam a trinca sai do NOME deles, e nome de "
                + "canal cada fabricante escreve como quer — quando erra, "
                + `3${g}0, ${g}1 e ${g}2 erram junto, na unidade certa e sem `
                + "aviso.";
    lapis.setAttribute("aria-label", `corrigir a trinca de ${x.nome}`);
    lapis.addEventListener("click", (evento) => {
      evento.preventDefault();
      evento.stopPropagation();
      abrirCorrecaoDaTrinca(x);
    });
    return lapis;
  }

  /** A janelinha de corrigir a trinca: um campo por fase.
   *
   * Os candidatos são os canais da MESMA UNIDADE. Somar `IA` em ampère com
   * `VA` em volt não é trinca de coisa nenhuma, e oferecer isso seria oferecer
   * um erro que o programa depois não teria como recusar.
   */
  function abrirCorrecaoDaTrinca(x) {
    const conjunto = x.conjunto || {};
    const _g = grandezaDaTrinca(conjunto);
    const candidatos = (dados.catalogo || []).filter(
      (c) => c.familia === "canal" && c.unidade === conjunto.unidade);
    if (!candidatos.length) return;

    const janelinha = criar("dialog", "busca trincas");
    const campos = new Map();

    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem mudar nada";
    fechar.addEventListener("click", () => janelinha.close());

    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, `De que canais sai ${x.nome}`), fechar);

    const ajuda = criar("p", "ajuda-rotulo",
      "O programa deduziu esta trinca do nome dos canais. Se ele errou, "
      + `escolha aqui os três certos — vale para ${_g}N, 3${_g}0, ${_g}1 e `
      + `${_g}2 dessa trinca, e fica gravado com o registro.`);

    const lista = criar("div", "achados");
    for (const fase of ["A", "B", "C"]) {
      const item = criar("div", "achado rotulo-trinca");
      const escolha = document.createElement("select");
      escolha.className = "escolher-fase";
      for (const c of candidatos) {
        const o = document.createElement("option");
        o.value = String(c.canal);
        o.textContent = c.nome;
        escolha.append(o);
      }
      escolha.value = String((conjunto.canais || {})[fase]);
      campos.set(fase, escolha);
      item.append(criar("span", "nome", `fase ${fase}`), escolha);
      lista.append(item);
    }

    const recado = criar("p", "ajuda-rotulo", "");
    const aplicar = criar("button", "aceitar", "gravar");
    aplicar.type = "button";
    aplicar.addEventListener("click", async () => {
      const canais = {};
      for (const [fase, campo] of campos) canais[fase] = Number(campo.value);
      // Duas fases no mesmo canal não é trinca: a matriz de Fortescue sobre
      // isso devolve número, e o número não quer dizer nada. Recusar aqui é
      // mais honesto que aceitar e desenhar.
      if (new Set(Object.values(canais)).size < 3) {
        recado.textContent = "As três fases têm que ser canais diferentes.";
        return;
      }
      janelinha.close();
      await gravarTrinca(conjunto.chave, canais);
    });

    janelinha.append(cabeca, ajuda, lista, recado, aplicar);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
  }

  /** Manda a trinca corrigida ao servidor e recarrega.
   *
   * Recarrega porque a correção muda o VALOR de 3I0, I1 e I2 — e o nome dos
   * canais de origem —, e isso tudo nasce no Python. Remontar aqui seria um
   * segundo lugar onde as contas podem divergir.
   */
  async function gravarTrinca(chave, canais) {
    try {
      const r = await fetch(`/api/onda/${sha}/trincas`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [chave]: canais }),
      });
      if (!r.ok) throw new Error(`o servidor respondeu ${r.status}`);
      await carregar();
    } catch (erro) {
      avisarDaFalha(erro);
    }
  }

  /** " — de Current IA", para o hover de um sinal que o OscLab calculou. */
  const deQualCanal = (sinal) => (sinal.nome ? ` — de ${sinal.nome}` : "");

  //: As cores de FASE. São convenção de campo da distribuidora (azul-A,
  //: âmbar-B, vermelho-C), e por isso não se distribuem a qualquer sinal:
  //: quem as veste está afirmando de que fase é.
  const CORES_DE_FASE = {
    A: "--fase-a", B: "--fase-b", C: "--fase-c", N: "--fase-n",
  };

  //: As cores SEM fase, na ordem em que são distribuídas. É delas que sai a
  //: cor de um sinal calculado, e é para cá que vai um canal cuja cor de fase
  //: já está ocupada no gráfico — pôr `Voltage A-G` no âmbar da fase B para
  //: não repetir o azul resolveria a repetição inventando uma fase.
  //:
  //: A ordem é por CROMA, da mais viva para a mais apagada (o número é o croma
  //: em Lab, o menor dos dois temas). Não é gosto: as primeiras a sair são as
  //: que mais se afastam do fundo e umas das outras, e um gráfico com três
  //: sinais calculados merece as três melhores. O cinza é o último de todos —
  //: quase sem cor, ele só se distingue pela posição, e serve de sobra.
  //:
  //: Nenhuma delas se confunde com cor de fase: a mais próxima guarda ΔE 16,2
  //: do vermelho da fase C. Conferido com `tools/paleta.py`.
  const CORES_NEUTRAS = [
    "--traco-2",      // magenta  croma 78,6 (o menor dos dois temas)
    "--calculado-1",  // lilás    croma 57,4
    "--traco-1",      // verde    croma 57,1
    "--calculado-2",  // rosa     croma 53,7
    "--traco-3",      // oliva    croma 35,0
    "--calculado-3",  // cinza    croma  7,1
  ];

  //: Tudo que a paleta oferece à mão, na ordem em que aparece nas bolinhas.
  const PALETA = [
    "--fase-a", "--fase-b", "--fase-c", "--fase-n",
    ...CORES_NEUTRAS,
  ];

  /** A cor que o usuário escolheu para um sinal deste painel, ou `""`.
   *
   * Mora no arranjo da TELA, junto do nome e da ordem, e não vai ao servidor:
   * cor não muda número nenhum. Por isso também entra no Ctrl+Z, que desfaz o
   * que está na tela.
   */
  function corEscolhida(idDoPainel, idDoSinal) {
    const meu = painelPorId(idDoPainel);
    return (meu && meu.cores && meu.cores[idDoSinal]) || "";
  }

  function escolherCor(idDoPainel, idDoSinal, corToken) {
    const meu = painelPorId(idDoPainel);
    if (!meu) return;
    guardarParaDesfazer();
    meu.cores = meu.cores || {};
    if (corToken) meu.cores[idDoSinal] = corToken;
    else delete meu.cores[idDoSinal];
    // Cor é rótulo: não muda número nenhum, então não precisa do servidor.
    desenharTudo();
  }

  /** As cores de TODOS os sinais de um painel, decididas de uma vez.
   *
   * De uma vez porque a regra é sobre o conjunto: **um gráfico nunca repete
   * cor**. Duas curvas da mesma cor no mesmo eixo não se distinguem, e era o
   * que acontecia ao pôr `Current IA` e `Voltage A-G` no mesmo gráfico — as
   * duas são fase A, as duas saíam azuis. Decidir sinal a sinal não tem como
   * ver isso: a cor de um depende de quem já está lá.
   *
   * A ordem das decisões:
   *
   * 1. **A escolha do usuário manda**, e é reservada antes de tudo. Se ele
   *    pediu duas iguais, são duas iguais — ele que sabe por quê.
   * 2. Um canal com fase reconhecida fica com a **cor da fase dele**, se ela
   *    ainda estiver livre.
   * 3. Todo o resto — calculados, e canais cuja cor de fase já foi tomada —
   *    pega a primeira cor NEUTRA livre. Nunca uma cor de fase: ela afirma uma
   *    fase, e um sinal que a vestisse por sobra estaria mentindo.
   *
   * Passando de dez sinais num gráfico as cores se repetem, e não há o que
   * fazer: cor que se distingue de outras nove, nos dois temas e sob
   * daltonismo, é recurso escasso — ver `tools/paleta.py`. A legenda e a
   * tabelinha sempre nomeiam o sinal, então a cor nunca carrega sozinha a
   * identidade.
   */
  function coresDoPainel(painel) {
    // O mapa é o mesmo para todos os sinais do painel, e `pintar` pergunta a
    // cor de cada um a cada quadro do arrasto. Guardado por desenho: sem isto
    // seria um mapa novo por curva por quadro.
    if (painel._cores && painel._selo === seloDoDesenho) return painel._cores;
    const mapa = new Map();
    const usadas = new Set();
    const lista = (painel && painel.sinais) || [];

    for (const sinal of lista) {
      const escolhida = corEscolhida(painel.id, sinal.id);
      if (!escolhida) continue;
      mapa.set(sinal.id, escolhida);
      usadas.add(escolhida);
    }

    const primeiraLivre = () =>
      CORES_NEUTRAS.find((x) => !usadas.has(x))
      // Acabaram: volta ao começo. Repetir é ruim; não desenhar é pior.
      || CORES_NEUTRAS[usadas.size % CORES_NEUTRAS.length];

    // Num painel que MISTURA IEDs, a cor de fase é do IED A; os outros vão
    // para as neutras. Os «tons da fase» para o B foram tentados e não
    // passaram no `tools/paleta.py` (22/10/2026).
    const misto = new Set(lista.map((s) => s.ied || "A")).size > 1;
    for (const sinal of lista) {
      if (mapa.has(sinal.id)) continue;
      const daFase = misto && sinal.ied && sinal.ied !== "A" ? null : CORES_DE_FASE[sinal.fase];
      const cor = (daFase && !usadas.has(daFase)) ? daFase : primeiraLivre();
      mapa.set(sinal.id, cor);
      usadas.add(cor);
    }
    painel._selo = seloDoDesenho;
    painel._cores = mapa;
    return mapa;
  }

  /** A cor de um sinal dentro de um painel, já resolvida contra os vizinhos. */
  function corDoSinal(sinal, painel) {
    if (!painel) return token("--suave");
    const cor = coresDoPainel(painel).get(sinal.id);
    return cor ? (token(cor) || cor) : token("--suave");
  }



  // --- a calculadora de sinais ----------------------------------------------

  //: As contas do usuário, como a tela as guarda. Cada uma é
  //: `{id, nome, expressao}` e viaja no corpo de todo pedido, junto com o
  //: arranjo dos painéis — o servidor não guarda nenhuma, do mesmo jeito que
  //: não guarda painel. Ver `plot/contas.py`.
  let contas = [];
  let proximaConta = 1;

  /** O botão que abre a calculadora, na barra do catálogo. */
  /** O «fx nova conta» no CABEÇALHO de um painel.
   *
   * A calculadora nasceu dentro do catálogo, que é onde ela não se acha: para
   * criar um `Vab` era preciso abrir o catálogo de um painel e só então achar
   * o botão. Mas a conta não é assunto do catálogo — o catálogo é para
   * ESCOLHER o que já existe, e a conta é para CRIAR o que não existe.
   *
   * Aberta daqui ela já põe o resultado NESTE painel: quem estava olhando
   * para as três tensões e escreveu `([VAY] - [VBY]) / raiz(3)` quer ver a
   * `Vab` ali, não ir procurá-la no catálogo depois.
   */
  function botaoDeConta(painel) {
    const botao = criar("button", "medida com-icone");
    botao.type = "button";
    botao.append(iconeDeCalculadora(), criar("span", null, "calculadora"));
    botao.title = "Cria um sinal novo a partir dos que existem — "
                + "([VAY] - [VBY]) / raiz(3), ([IAW] + [IBW] + [ICW]) / 3 — e "
                + "o põe neste gráfico. O resultado é uma onda, com as mesmas "
                + "colunas de um canal.";
    botao.addEventListener("click", () => abrirCalculadora(painel, true));
    return botao;
  }

  function botaoDaCalculadora(painel) {
    const botao = criar("button", "chave");
    botao.type = "button";
    botao.append(iconeDoCalculado(), criar("span", null, "nova conta"));
    botao.title = "Cria um sinal novo a partir dos que existem: "
                + "([VAY] - [VBY]) / 1.732, [IAW] + [IBW] + [ICW]. O "
                + "resultado é uma onda, e entra no bloco «Calculados» com as "
                + "mesmas colunas de um canal.";
    botao.addEventListener("click", () => abrirCalculadora(painel));
    return botao;
  }

  //: As teclas da calculadora, em linhas. Cada uma é `[rótulo, o que insere,
  //: dica]` — e o que ela insere é TEXTO DA GRAMÁTICA, não um número pronto.
  //:
  //: `√3` insere `raiz(3)`, e não `1.732`: o número redondo erra em 0,03 %, e
  //: 0,03 % numa tensão de 13,8 kV são quatro volts que ninguém procura. A
  //: gramática já sabe tirar raiz; usar o que ela sabe é de graça e é exato.
  const TECLAS_DA_CALCULADORA = [
    [["+", " + ", "somar"],
     ["−", " - ", "subtrair"],
     ["×", " * ", "multiplicar"],
     ["÷", " / ", "dividir. Por número é direto; sinal ÷ sinal sai com "
        + "ressalva — estoura em cada passagem por zero do de baixo, e "
        + "impedância mesmo é conta de FASOR, que ainda não existe"],
     ["(", "(", "abre parêntese"],
     [")", ")", "fecha parêntese"]],
    [["√2", "raiz(2)", "1,41421… — pico ↔ eficaz"],
     ["√3", "raiz(3)", "1,73205… — fase ↔ linha"],
     ["÷√3", " / raiz(3)",
      "divide a CONTA INTEIRA por √3 — de tensão de linha para fase-terra. "
      + "Põe parênteses em volta do que já está escrito", true],
     ["÷3", " / 3",
      "divide a CONTA INTEIRA por 3 — a média das três, que faz 3I0 virar I0. "
      + "Põe parênteses em volta do que já está escrito", true],
     ["x²", "^2", "ao quadrado"],
     ["abs", "abs()", "valor absoluto — o módulo amostra a amostra"]],
  ];

  /** A janela da calculadora: nome, expressão, e o que o servidor achou dela.
   *
   * Quem confere a expressão é o SERVIDOR, a cada pausa na digitação. A
   * gramática mora num lugar só (`plot/contas.py`): uma cópia dela aqui seria
   * uma segunda gramática, e as duas divergiriam no primeiro caso esquisito —
   * que numa calculadora de laudo é justamente o caso que importa.
   */
  function abrirCalculadora(painel, paraOPainel = false) {
    const janelinha = criar("dialog", "busca calculadora");

    const campoNome = document.createElement("input");
    campoNome.type = "text";
    campoNome.className = "nome-da-conta";
    campoNome.placeholder = "nome do sinal (ex.: Vab)";
    campoNome.maxLength = 40;

    const campo = document.createElement("textarea");
    campo.className = "expressao-da-conta";
    campo.rows = 2;
    campo.placeholder = "([VAY] - [VBY]) / 1.732";
    campo.spellcheck = false;

    const veredito = criar("p", "veredito-da-conta", "");
    const aplicar = criar("button", "aceitar", "criar sinal");
    aplicar.disabled = true;

    // O que já existe, para editar ou tirar. Uma conta errada é mais fácil de
    // corrigir do que de recriar, e sem esta lista ela só se corrigiria
    // apagando e escrevendo tudo de novo.
    // `contas-existentes`, e NÃO `achados`: aquela classe tem altura fixa de
    // 46vh, porque lá ela segura uma lista de cento e vinte sinais. Aqui a
    // lista tem o tamanho do que há nela, e a janela encolhe junto.
    const lista = criar("div", "contas-existentes");
    const desenharContas = () => {
      lista.replaceChildren();
      if (!contas.length) return;
      lista.append(criar("div", "divisor", `já criadas (${contas.length})`));
      for (const conta of contas) {
        const linha = criar("div", "linha-na-tela");
        const nome = criar("span", "nome-da-linha calculado");
        nome.append(criarNome("span", "nome", conta.nome));
        const texto = criar("code", "expressao-escrita", conta.expressao);
        // A ressalva vem do CATÁLOGO, e não de um segundo pedido: o servidor
        // já analisou esta conta para montar a linha dela, e perguntar de
        // novo por conta seria a mesma análise duas vezes — com a chance de
        // as duas discordarem enquanto o usuário digita.
        const noCatalogo = (dados.catalogo || []).find(
          (x) => x.id === `${conta.id}:instantaneo`);
        const ressalva = (noCatalogo && noCatalogo.aviso) || "";
        if (ressalva) {
          const marca = criar("span", "ressalva-da-linha", "ⓘ");
          marca.title = ressalva;
          nome.append(marca);
        }
        const editar = criar("button", "link", "editar");
        editar.type = "button";
        editar.addEventListener("click", () => {
          campoNome.value = conta.nome;
          campo.value = conta.expressao;
          emEdicao = conta.id;
          aplicar.textContent = "guardar";
          conferir();
          campo.focus();
        });
        const tirar = criar("button", "link", "tirar");
        tirar.type = "button";
        tirar.addEventListener("click", () => {
          guardarParaDesfazer();
          contas = contas.filter((x) => x.id !== conta.id);
          // Tirar a conta tira também o que ela desenhava: um painel com um
          // sinal que não existe mais desenharia buraco sem dizer por quê.
          for (const p of paineis) {
            p.sinais = (p.sinais || []).filter(
              (s) => !String(s).startsWith(`${conta.id}:`));
          }
          desenharContas();
          // O catálogo que está ABERTO atrás desta janela precisa ser
          // refeito: ele lista os sinais de `dados.catalogo`, e a conta que
          // acabou de sair (ou de entrar) muda essa lista. Sem isto ele
          // continuaria oferecendo um sinal que não existe mais.
          carregar().then(() => redesenharCatalogo && redesenharCatalogo());
        });
        linha.append(nome, texto, editar, tirar);
        lista.append(linha);
      }
    };

    let emEdicao = null;
    let pedindo = null;

    /* ------------------------------------------------------------------
     * A TIRA DE CAPACIDADES
     * ------------------------------------------------------------------
     *
     * Cinco verificações numa linha: a unidade, as três folhas e o filtro. O
     * que dá, acende; o que não dá, apaga e risca.
     *
     * E o texto embaixo comenta SÓ o que não dá. Explicar o que funciona
     * dobra o tamanho da frase sem acrescentar decisão nenhuma — ninguém
     * muda a conta porque leu que o RMS funciona. Era um parágrafo corrido
     * de seis linhas que empurrava o botão «criar sinal» para fora da tela.
     *
     * A altura é FIXA: cinco pastilhas sempre, uma linha de texto sempre —
     * vazia quando dá tudo certo. Sem isso a janelinha mudava de tamanho a
     * cada tecla, e o botão escorregava debaixo do clique.
     */
    const CAPACIDADES = [
      ["onda", "a forma de onda no tempo"],
      ["RMS", "o eficaz da janela de um ciclo"],
      ["DC", "a componente contínua"],
      ["filtro", "extrair só os 60 Hz"],
    ];

    const desenharCapacidades = (resposta, avisos, soNoAvancado) => {
      veredito.replaceChildren();
      veredito.className = "veredito-da-conta";
      const tira = criar("div", "tira-de-capacidades");

      const unidade = criar("span", "capacidade unidade",
                            resposta.unidade || "número puro");
      unidade.title = "A unidade do resultado, propagada pela conta: "
                    + "V ÷ A vira Ω, V × A vira V·A.";
      tira.append(unidade);

      // Conta entre MÓDULOS não tem onda nem contínua: a série já É o valor,
      // e passar uma janela de um ciclo nela seria suavizar um número que
      // ninguém pediu para suavizar. `misto` é o «não sei» — ali fica tudo de
      // pé, porque não saber não é o mesmo que não existir.
      const modulo = resposta.dominio === "modulo";
      const temFiltro = resposta.tem_60hz !== false;
      const pode = { onda: !modulo, RMS: true, DC: !modulo,
                     filtro: temFiltro };
      for (const [nome, oque] of CAPACIDADES) {
        const p = criar("span",
                        `capacidade ${pode[nome] ? "sim" : "nao"}`,
                        pode[nome] ? `✓ ${nome}` : nome);
        p.title = oque;
        tira.append(p);
      }
      veredito.append(tira);

      // --- a linha de texto: só o que NÃO dá ---
      const faltas = CAPACIDADES.map(([n]) => n).filter((n) => !pode[n]);
      const frases = [];
      if (faltas.length) {
        frases.push(`${faltas.join(", ")}: `
          + (modulo ? "a operação usa RMS." : "a operação não tem 60 Hz."));
      }
      if (!resposta.alternado && temFiltro) {
        frases.push("fasorial e harmônicos: a operação não é senoidal.");
      }
      if (avisos.length) frases.push(avisos.join("; "));
      if (soNoAvancado) {
        frases.push("ao criar, a tela passa para «avançado»: o tradicional "
                  + "mostra só o filtrado.");
      }
      const texto = criar("p", "porque-da-conta", frases.join("  "));
      veredito.append(texto);
      veredito.className = "veredito-da-conta "
        + (avisos.length ? "ressalva" : "bom");
    };

    const conferir = () => {
      const expressao = campo.value.trim();
      aplicar.disabled = true;
      if (!expressao) {
        veredito.replaceChildren();
        veredito.className = "veredito-da-conta";
        return;
      }
      // Com um colchete ABERTO a conta está pela metade por definição, e
      // «não entendi [VA» é um erro que o usuário já sabe — ele está no meio
      // de escrever o nome. Vermelho a cada letra ensina a ignorar vermelho.
      if (digitandoNome()) {
        veredito.replaceChildren();
        veredito.className = "veredito-da-conta";
        return;
      }
      clearTimeout(pedindo);
      pedindo = setTimeout(async () => {
        try {
          const r = await fetch(`/api/onda/${sha}/conta`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // `editando` e `contas` dizem ao servidor o ALCANCE desta conta:
            // ela enxerga as criadas antes dela, e só. Ver `contas.analisar`.
            body: JSON.stringify({ expressao, lado, contas,
                                   editando: emEdicao || "" }),
          });
          const resposta = await r.json();
          if (campo.value.trim() !== expressao) return;   // já mudou: ignora
          if (!resposta.vale) {
            veredito.replaceChildren(criar("p", "porque-da-conta",
                                           resposta.erro));
            veredito.className = "veredito-da-conta ruim";
            return;
          }
          const avisos = resposta.avisos || [];
          // Sem 60 Hz, a conta não tem coluna nenhuma no modo tradicional —
          // aquele modo só mostra o filtrado. Avisar aqui e trocar de modo ao
          // criar é o mesmo caminho que o botão do filtro já faz: pedir uma
          // coisa que só existe no avançado leva ao avançado.
          const soNoAvancado = resposta.tem_60hz === false
                            && visaoDeAnalise !== "avancado";
          desenharCapacidades(resposta, avisos, soNoAvancado);
          aplicar._soNoAvancado = soNoAvancado;
          aplicar.disabled = !campoNome.value.trim();
        } catch {
          veredito.replaceChildren(criar("p", "porque-da-conta",
                                         "não consegui conferir agora"));
          veredito.className = "veredito-da-conta";
        }
      }, 250);
    };

    campo.addEventListener("input", () => { mostrarSugestoes(); conferir(); });

    // Também ao andar com o cursor: entrar num colchete que já existe tem que
    // trazer as sugestões daquele colchete.
    // Em arrow, e não passando a função direto: `mostrarSugestoes` é um
    // `const` declarado mais abaixo, e ler o nome aqui na hora de registrar o
    // ouvinte cai na zona morta temporal — a página quebrava ao abrir.
    for (const gesto of ["click", "keyup"]) {
      campo.addEventListener(gesto, () => mostrarSugestoes());
    }
    campoNome.addEventListener("input", () => {
      aplicar.disabled = aplicar.disabled || !campoNome.value.trim();
      conferir();
    });

    aplicar.addEventListener("click", () => {
      const nome = campoNome.value.trim();
      const expressao = campo.value.trim();
      if (!nome || !expressao) return;
      guardarParaDesfazer();
      if (emEdicao) {
        contas = contas.map((x) => (x.id === emEdicao
          ? { ...x, nome, expressao } : x));
      } else {
        const id = `x${proximaConta++}`;
        contas.push({ id, nome, expressao });
        // Aberta pelo cabeçalho do painel, a conta já entra nele. Pelo
        // catálogo, não: ali o gesto de pôr na tela é o «mostrar na tela», e
        // dobrar esse gesto faria o sinal aparecer duas vezes para quem
        // marcasse a caixinha também.
        if (paraOPainel && painel) {
          const meu = painelPorId(painel.id);
          if (meu) meu.sinais = [...(meu.sinais || []), `${id}:instantaneo`];
        }
      }
      // A conta sem 60 Hz não existe no tradicional: o modo só mostra as
      // colunas do filtrado, e ela não tem nenhuma. Trocar é o que o botão do
      // filtro já faz — recusar deixaria o sinal invisível sem dizer por quê.
      if (aplicar._soNoAvancado && visaoDeAnalise !== "avancado") {
        visaoDeAnalise = "avancado";
        guardar("osclab:catalogo:visao", "avancado");
        marcarBotoes();
      }
      janelinha.close();
      carregar().then(() => redesenharCatalogo && redesenharCatalogo());
    });

    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem criar";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());

    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, "Nova conta"), fechar);

    const ajuda = criar("p", "ajuda-da-conta");
    ajuda.append(criar("span", null,
      "O nome do sinal vai entre colchetes — canal do relé, resíduo, "
      + "componente de sequência ou outra conta sua. Valem + − × ÷, "
      + "parênteses, número, abs() e raiz(), com a ordem matemática de "
      + "sempre: × e ÷ antes de + e −. Nenhuma conta é barrada; o que for "
      + "estranho sai com ⓘ ao lado, dizendo o que esperar."));

    /* Os nomes dos canais, clicáveis, para não ter que digitar
     * `[Voltage A-G]` letra por letra — e, sobretudo, para não errar o nome.
     * Nome de canal cada fabricante escreve como quer, e um `[Voltage A­G]`
     * com o hífen errado é meia hora procurando o que não existe.
     *
     * Inserir NA POSIÇÃO DO CURSOR, e não no fim: metade das contas se
     * escreve de fora para dentro — primeiro `( - ) / 1.732`, depois os
     * nomes. */
    /** Põe texto na posição do cursor do campo. Metade das contas se escreve
     * de fora para dentro — primeiro `( - ) / raiz(3)`, depois os nomes —,
     * então inserir no fim seria inserir quase sempre no lugar errado. */
    const inserir = (texto, recuo = 0) => {
      const i = campo.selectionStart ?? campo.value.length;
      const j = campo.selectionEnd ?? i;
      campo.value = campo.value.slice(0, i) + texto + campo.value.slice(j);
      campo.focus();
      const onde = i + texto.length - recuo;
      campo.selectionStart = campo.selectionEnd = onde;
      conferir();
    };

    // O teclado: as operações e os escalares do ofício. A calculadora tem que
    // PARECER uma calculadora — quem abre uma espera teclas, e digitar
    // `raiz(3)` de cabeça supõe saber que a função existe.
    // NUMA FILEIRA SÓ, as doze teclas menores: a altura que sobra vai para as
    // fichas, que passam a aparecer todas (maquete 6 de «calculadora-10»,
    // escolha dele em 22/10/2026).
    const teclado = criar("div", "teclado-da-conta compacto");
    for (const fileira of [TECLAS_DA_CALCULADORA.flat()]) {
      const linha = criar("div", "fileira-de-teclas");
      for (const [rotulo, texto, dica, envolve] of fileira) {
        const tecla = criar("button", "tecla", rotulo);
        tecla.type = "button";
        tecla.title = dica;
        /* `abs()` entra com o cursor DENTRO dos parênteses: ninguém escreve
         * uma função para depois voltar com a seta.
         *
         * E as teclas que dividem a CONTA INTEIRA (`÷3`, `÷√3`) envolvem o que
         * já está escrito em parênteses, em vez de colar no fim. Sem isso elas
         * mentiam, e de um jeito perigoso: a tecla `÷3` promete "a média das
         * três", mas colada no fim de `[IAW] + [IBW] + [ICW]` a precedência
         * matemática a lê como `[IAW] + [IBW] + ([ICW] / 3)` — que não é média
         * de nada e tem cara de número certo.
         */
        tecla.addEventListener("click", () => {
          if (envolve && campo.value.trim()) {
            campo.value = `(${campo.value.trim()})${texto}`;
            campo.focus();
            campo.selectionStart = campo.selectionEnd = campo.value.length;
            conferir();
            return;
          }
          inserir(texto, texto.endsWith("()") ? 1 : 0);
        });
        linha.append(tecla);
      }
      teclado.append(linha);
    }

    const atalhos = criar("div", "canais-da-conta");
    /* O que a conta pode referenciar: TUDO que o catálogo oferece como linha.
     *
     * Canais do arquivo, o resíduo da trinca (`IN G1`), as componentes de
     * sequência (`3I0 G1`) e as contas que já existem. Uma linha tem várias
     * colunas — onda, RMS, DC — e aqui entra a NATURAL dela: a onda de quem é
     * onda, e o eficaz de quem só existe em eficaz. É exatamente a regra de
     * `contas.referenciaveis`, no servidor, e as duas têm que concordar: uma
     * ficha que insere um nome que a conta recusa é pior que ficha nenhuma.
     *
     * Uma conta em EDIÇÃO não se enxerga, nem às que vieram depois dela: é a
     * ordem de criação que torna a referência circular impossível.
     */
    const referenciaveis = () => {
      const corte = emEdicao
        ? contas.findIndex((x) => x.id === emEdicao) : contas.length;
      const proibidos = new Set(
        (corte < 0 ? [] : contas.slice(corte)).map((x) => x.nome));
      // Uma entrada por LINHA, guardando as duas colunas de onda que ela
      // tem: a bruta e a de 60 Hz. É o par que o botão alterna.
      const porLinha = new Map();
      for (const x of (dados.catalogo || [])) {
        const nome = (x.linha || x.nome || "").trim();
        if (!nome || proibidos.has(nome)) continue;
        let alvo = porLinha.get(nome);
        if (!alvo) {
          alvo = { nome, canal: x.canal, familia: x.familia,
                   descricao: x.descricao, bruto: null, filtrado: null,
                   unica: x };
          porLinha.set(nome, alvo);
        }
        if (x.grandeza === "instantaneo") alvo.bruto = x;
        else if (x.grandeza === "filtrado") alvo.filtrado = x;
      }
      /* A ordem é a de quem procura: os canais do arquivo, que se escrevem
       * o tempo todo; depois as contas DO USUÁRIO, que são o que ele acabou
       * de criar e tem na cabeça; e por último o que o OscLab calcula
       * sozinho (resíduo e componentes), que está sempre ali e se acha pelo
       * nome. Sem isso as contas dele caíam atrás do corte do «…» — logo as
       * mais frescas.
       */
      return [...porLinha.values()];
    };

    /* O nome que a ficha INSERE, conforme o botão.
     *
     * A linha que tem as duas colunas (um canal, o resíduo, uma conta) segue o
     * botão. A que só tem uma — uma componente de sequência, que é fasor —
     * ignora o botão e insere o que ela é: não há bruto de um `3I0`, e
     * oferecer um nome que não existe seria pior que ignorar o botão.
     */
    const nomeDaFicha = (linha) => {
      const quero = colunaDasFichas === "filtrado" ? linha.filtrado : linha.bruto;
      const alvo = quero || linha.bruto || linha.filtrado || linha.unica;
      return (alvo && alvo.nome) || linha.nome;
    };

    const segueOBotao = (linha) => !!(linha.bruto && linha.filtrado);

    //: Quantas fichas cabem antes do «…», POR FILEIRA. Doze é o que entra
    //: numa linha num registro de parque; um SEL-487E com catorze analógicos
    //: passa disso, e trinta fichas é uma parede que ninguém lê.
    const FICHAS_VISIVEIS = Infinity;   // maquete 6: todas à vista
    let verTodas = false;

    /* Em que COLUNA as fichas inserem o nome: a onda bruta ou a de 60 Hz.
     *
     * No modo tradicional fica travado em `filtrado`, pela mesma razão que o
     * catálogo esconde as colunas do bruto ali: aquele modo fala do sinal com
     * que o relé decidiu, e só dele. Deixar a calculadora oferecer bruto no
     * tradicional era a única parte da tela fora do modo.
     *
     * É a COLUNA que muda, não o sinal: `IN G1` e `IN G1 · 60Hz` são a mesma
     * linha vista de dois jeitos, e os dois nomes a gramática já resolve —
     * ver `contas._do_catalogo`.
     */
    /* O nome reduzido à forma com que se procura: maiúsculas, sem o `·`.
     * É a MESMA regra do servidor (`contas.chave_do_nome`), e as duas têm que
     * concordar — o ponto médio não está no teclado ABNT, e exigi-lo era pedir
     * que o usuário copiasse um caractere para escrever o nome de um sinal
     * que está na tela dele. */
    const chaveDoNome = (nome) =>
      String(nome).toUpperCase().replace(/·/g, " ").split(/\s+/).filter(Boolean)
        .join(" ");

    const travadoNoFiltrado = () => visaoDeAnalise !== "avancado";
    /* O botão segue o FILTRO da tela, e não só o modo.
     *
     * Era `travadoNoFiltrado() ? "filtrado" : "bruto"` — no avançado com o
     * filtro ACESO os atalhos ofereciam `IAW`, o canal bruto, que é
     * justamente o que a tela não está mostrando. Clicar num atalho passava
     * a inserir um sinal diferente do que estava no gráfico. */
    const queda = criar("div", "queda-de-sugestoes");
    queda.hidden = true;

    let colunaDasFichas = (travadoNoFiltrado() || dados.filtro)
      ? "filtrado" : "bruto";
    /** O que está sendo digitado DENTRO de colchetes, no ponto do cursor.
     *
     * Devolve `{de, ate, pedaco}` ou `null`. É o que transforma a fileira de
     * canais em sugestão: digitou `[V`, sobram os que começam com V; digitou
     * `[VA`, sobram `VAY` e `VAV`.
     *
     * Procura o `[` mais próximo à ESQUERDA do cursor sem `]` no caminho —
     * assim `[IAW] - [V` sugere sobre o segundo colchete, não sobre a conta
     * inteira.
     */
    const digitandoNome = () => {
      const i = campo.selectionStart ?? 0;
      const antes = campo.value.slice(0, i);
      const abre = antes.lastIndexOf("[");
      if (abre < 0 || antes.indexOf("]", abre) >= 0) return null;
      return { de: abre, ate: i, pedaco: antes.slice(abre + 1) };
    };

    /** Completa o colchete aberto com este nome. */
    const completar = (nome) => {
      const agora = digitandoNome();
      const texto = `[${nome}]`;
      if (!agora) { inserir(texto); return; }
      // Come também um `]` que já esteja logo depois do cursor, para não
      // sobrar `[VAY]]` quando o usuário já tinha fechado o colchete.
      const depois = campo.value[agora.ate] === "]" ? agora.ate + 1 : agora.ate;
      campo.value = campo.value.slice(0, agora.de) + texto
                  + campo.value.slice(depois);
      campo.focus();
      campo.selectionStart = campo.selectionEnd = agora.de + texto.length;
      conferir();
    };

    let sugeridos = [];

    /* Ao DIGITAR, a peneira passa a ser por COLUNA, e não por linha.
     *
     * Quem escreve `IAW` quer ver o que existe com esse nome: no tradicional,
     * `IAW · 60Hz` e `IAW · 60Hz RMS`; no avançado, também `IAW`, `IAW · RMS`
     * e `IAW · DC`. Mostrar uma ficha só, a da coluna que o botão escolheu,
     * esconderia justamente as outras — e obrigaria a descobrir o botão para
     * chegar nelas.
     *
     * Em repouso continua sendo uma ficha por linha: a fileira ali é o
     * lembrete de QUE SINAIS existem, e cinco colunas de cada um viram uma
     * parede.
     */
    const colunasReferenciaveis = () => {
      const corte = emEdicao
        ? contas.findIndex((x) => x.id === emEdicao) : contas.length;
      const proibidos = new Set(
        (corte < 0 ? [] : contas.slice(corte)).map((x) => x.nome));
      const vistos = new Set();
      const saida = [];
      for (const x of (dados.catalogo || [])) {
        const linha = (x.linha || x.nome || "").trim();
        if (!linha || proibidos.has(linha)) continue;
        // A mesma peneira do catálogo: no tradicional a tela fala do sinal
        // filtrado, e a calculadora acompanha. Ver `colunasDaVisao`.
        if (travadoNoFiltrado() && x.coluna
            && !String(x.coluna).startsWith("filtrado.")) continue;
        const nome = (x.nome || linha).trim();
        if (vistos.has(nome)) continue;
        vistos.add(nome);
        saida.push({ nome, canal: x.canal, familia: x.familia,
                     descricao: x.descricao, unica: x, coluna: x.coluna });
      }
      return saida;
    };

    /** Uma fileira de fichas, com rótulo à esquerda e «…» no fim. */
    const fileiraDeFichas = (rotulo, linhas, procura, dica) => {
      if (!linhas.length) return null;
      const fileira = criar("div", "fileira-de-fichas");
      fileira.append(criar("span", "rotulo-da-fileira", rotulo));
      // As fichas moram numa caixa própria, e não soltas na fileira.
      //
      // Soltas, a fileira era um `flex` com o rótulo como primeiro item: a
      // primeira linha alinhava, e a SEGUNDA voltava para a margem, debaixo
      // do rótulo. Duas fileiras que quebram em pontos diferentes deixavam de
      // ter coluna nenhuma em comum. Com a caixa, o rótulo ocupa a coluna da
      // esquerda e toda ficha — inclusive a da terceira linha — começa no
      // mesmo x.
      const caixa = criar("div", "fichas-da-fileira");
      fileira.append(caixa);
      const mostrar = (procura || verTodas)
        ? linhas : linhas.slice(0, FICHAS_VISIVEIS);
      for (const linha of mostrar) {
        // A entrada de COLUNA já traz o nome pronto; a de LINHA segue o botão.
        const nome = linha.coluna ? linha.nome : nomeDaFicha(linha);
        const chip = criarNome("button", "chip-de-canal", nome);
        chip.type = "button";
        if (linha.canal < 0) chip.classList.add("calculado");
        chip.title = `inserir [${nome}] na conta — ${dica}`
          + (linha.coluna || segueOBotao(linha) ? ""
             : ". Esta linha tem uma coluna só, então o botão bruto/60 Hz "
               + "não a muda");
        if (procura && sugeridos[0] === nome) chip.classList.add("primeiro");
        chip.addEventListener("click", () => completar(nome));
        caixa.append(chip);
      }
      if (!procura && !verTodas && linhas.length > FICHAS_VISIVEIS) {
        const mais = criar("button", "chip-de-canal reticencias", "…");
        mais.type = "button";
        mais.title = `mostrar os outros ${linhas.length - FICHAS_VISIVEIS} — `
                   + "ou escreva «[» e comece a digitar, que a fileira peneira "
                   + "sozinha";
        mais.addEventListener("click", () => { verTodas = true; mostrarSugestoes(); });
        caixa.append(mais);
      }
      return fileira;
    };

    const mostrarSugestoes = () => {
      const agora = digitandoNome();
      const procura = chaveDoNome(agora ? agora.pedaco : "").trim();
      // A busca compara pela MESMA chave do servidor: quem digita «IAW 60»
      // tem que achar «IAW · 60Hz», que é como a tela escreve o nome.
      const candidatos = procura
        ? colunasReferenciaveis().filter(
            (x) => combinaNome(x.nome, procura))
        : referenciaveis();
      sugeridos = candidatos.map((x) => (x.coluna ? x.nome : nomeDaFicha(x)));
      atalhos.replaceChildren();

      // O botão que alterna a COLUNA. Fora quando a tela não tem as duas —
      // num registro já filtrado não há bruto que oferecer.
      const temAsDuas = candidatos.some(segueOBotao);
      if (temAsDuas) atalhos.append(botaoDaColuna());

      const canais = candidatos.filter((x) => x.canal >= 0);
      const minhas = candidatos.filter((x) => x.canal < 0 && x.familia === "conta");
      const nossos = candidatos.filter((x) => x.canal < 0 && x.familia !== "conta");
      // Separadas porque são coisas diferentes: o que o relé gravou, o que o
      // OscLab contou, e o que o usuário escreveu. Numa fileira só, um `3I0
      // G1` no meio dos canais se lê como mais um canal do arquivo.
      for (const [rot, lista, dica] of [
        ["canais", canais, "canal do arquivo"],
        ["minhas contas", minhas, "conta sua"],
        ["calculados", nossos, "calculado pelo OscLab a partir dos canais"],
      ]) {
        const fileira = fileiraDeFichas(rot, lista, procura, dica);
        if (fileira) atalhos.append(fileira);
      }
      if (!procura && verTodas) {
        const menos = criar("button", "chip-de-canal reticencias", "mostrar menos");
        menos.type = "button";
        menos.addEventListener("click", () => { verTodas = false; mostrarSugestoes(); });
        atalhos.append(menos);
      }
      if (procura && !sugeridos.length) {
        atalhos.append(criar("span", "sem-sugestao",
                             `nenhum sinal com «${procura}»`));
      }
      desenharQueda(procura);
    };

    /* ------------------------------------------------------------------
     * A QUEDA DE SUGESTÕES
     * ------------------------------------------------------------------
     *
     * Aparece colada no campo assim que há um colchete aberto, e some
     * quando ele fecha. Fora dos colchetes ela não existe: ali o usuário
     * está digitando número ou operador, e uma lista caindo por cima seria
     * estorvo.
     *
     * Existe porque a fileira de atalhos responde «que sinais existem», que
     * é outra pergunta. Quem já digitou `iaw` quer ver as QUATRO formas
     * daquele canal, uma embaixo da outra, e escolher com a seta — não
     * caçar a ficha certa numa parede de doze.
     */
    let escolhidaNaQueda = 0;

    const desenharQueda = (procura) => {
      queda.replaceChildren();
      const dentro = digitandoNome();
      if (!dentro || !procura || !sugeridos.length) {
        queda.hidden = true;
        return;
      }
      queda.hidden = false;
      if (escolhidaNaQueda >= sugeridos.length) escolhidaNaQueda = 0;
      sugeridos.slice(0, 7).forEach((nome, i) => {
        const item = criar("button",
                           `sugestao${i === escolhidaNaQueda ? " escolhida" : ""}`);
        item.type = "button";
        item.append(criarNome("span", "nome-sugerido", nome));
        if (i === escolhidaNaQueda) {
          item.append(criar("span", "tecla-da-sugestao", "Enter"));
        }
        item.addEventListener("click", () => completar(nome));
        queda.append(item);
      });
      queda.append(criar("div", "pe-da-queda",
                         "↑↓ escolhe · Enter insere · o «·» é opcional"));
    };

    /** O botão que alterna entre a onda bruta e a de 60 Hz. */
    function botaoDaColuna() {
      const caixa = criar("div", "chave-da-coluna");
      caixa.append(criar("span", "rotulo-da-fileira", "usar"));
      for (const [chave, rotulo, dica] of [
        ["bruto", "bruto", "a amostra como o relé gravou: 60 Hz, harmônicos e "
         + "a contínua da falta, tudo junto"],
        ["filtrado", "60 Hz", "só a componente de 60 Hz, a mesma com que o "
         + "relé decidiu atuar"],
      ]) {
        const b = criar("button", "tecla-da-coluna", rotulo);
        b.type = "button";
        b.title = travadoNoFiltrado()
          ? "No modo tradicional a tela inteira fala do sinal filtrado, e a "
            + "calculadora acompanha. Troque para «avançado» para usar o bruto."
          : dica;
        if (colunaDasFichas === chave) b.classList.add("aceso");
        b.disabled = travadoNoFiltrado();
        b.addEventListener("click", () => {
          colunaDasFichas = chave;
          mostrarSugestoes();
          desenharProntas();
        });
        caixa.append(b);
      }
      return caixa;
    }

    // Tab completa com a primeira sugestão. Num campo de texto o Tab move o
    // foco, e aqui ele vale mais fechando o nome: é a tecla que a mão procura
    // depois de digitar três letras.
    campo.addEventListener("keydown", (evento) => {
      const agora = digitandoNome();
      // As setas e o Enter só mexem na queda quando ela está aberta. Fora
      // dela o Enter é o que sempre foi, e roubá-lo seria tirar do usuário a
      // tecla com que ele termina a conta.
      if (agora && !queda.hidden && sugeridos.length) {
        if (evento.key === "ArrowDown" || evento.key === "ArrowUp") {
          evento.preventDefault();
          const quantas = Math.min(sugeridos.length, 7);
          escolhidaNaQueda = (escolhidaNaQueda
            + (evento.key === "ArrowDown" ? 1 : quantas - 1)) % quantas;
          desenharQueda(agora.pedaco.trim().toUpperCase());
          return;
        }
        if (evento.key === "Enter") {
          evento.preventDefault();
          completar(sugeridos[escolhidaNaQueda] || sugeridos[0]);
          escolhidaNaQueda = 0;
          return;
        }
        if (evento.key === "Escape") {
          evento.preventDefault();
          queda.hidden = true;
          return;
        }
      }
      // O Tab continua valendo: é a tecla que a mão procura depois de
      // digitar três letras, e num campo de texto ele não tem uso melhor.
      if (evento.key !== "Tab" || evento.shiftKey) return;
      if (!agora || !sugeridos.length) return;
      evento.preventDefault();
      completar(sugeridos[escolhidaNaQueda] || sugeridos[0]);
      escolhidaNaQueda = 0;
    });

    /* AS CONTAS PRONTAS: um clique preenche o nome E a expressão.
     *
     * Montadas com os canais das trincas deste registro — `[VAY] - [VBY]` num
     * SEL, `[Voltage A-G] - [Voltage B-G]` num MiCOM —, pela fase que o
     * programa já conhece de cada canal. Na coluna que o botão bruto/60 Hz
     * escolheu: com o filtro ligado, `[IAW · 60Hz]`. Tensão de linha (`Vab`)
     * só sai de trinca medida contra o neutro: numa em delta ela já é o canal.
     * Com mais de uma trinca da mesma grandeza o nome leva o grupo (`Vab G3`),
     * porque nome de conta é identidade.
     */
    const prontas = criar("div", "contas-prontas");
    const desenharProntas = () => {
      prontas.replaceChildren();
      const vivos = (dados.conjuntos || []).filter((c) => !c.sem_sinal);
      const nomeDoCanal = (indice) => {
        const quero = colunaDasFichas === "filtrado" ? "filtrado" : "instantaneo";
        const da = (dados.catalogo || []).filter((x) => x.canal === indice);
        const achado = da.find((x) => x.grandeza === quero)
                    || da.find((x) => x.grandeza === "instantaneo") || da[0];
        return achado ? achado.nome : null;
      };
      const receitas = [];
      for (const g of ["V", "I"]) {
        const grupos = vivos.filter((c) => c.grandeza === g);
        for (const c of grupos) {
          const [a, b, cc] = (c.canais || []).map(nomeDoCanal);
          if (!a || !b || !cc) continue;
          const sufixo = grupos.length > 1 ? ` ${c.rotulo}` : "";
          if (g === "V" && c.base !== "linha") {
            receitas.push([`Vab${sufixo}`, `[${a}] - [${b}]`, "tensão de linha A-B"]);
            receitas.push([`Vbc${sufixo}`, `[${b}] - [${cc}]`, "tensão de linha B-C"]);
            receitas.push([`Vca${sufixo}`, `[${cc}] - [${a}]`, "tensão de linha C-A"]);
          }
          if (g === "I") {
            receitas.push([`I média${sufixo}`, `([${a}] + [${b}] + [${cc}]) / 3`,
                           "média das três fases"]);
          }
        }
      }
      if (!receitas.length) return;
      prontas.append(criar("span", "rotulo-da-fileira", "contas prontas"));
      const caixa = criar("div", "grade-das-prontas");
      for (const [nome, expressao, dica] of receitas) {
        const b = criar("button", "conta-pronta");
        b.type = "button";
        b.title = `${dica} — preenche o nome e a expressão; dá para editar antes de criar`;
        b.append(criar("b", null, nome), criar("code", null, expressao));
        b.addEventListener("click", () => {
          campoNome.value = nome;
          campo.value = expressao;
          campo.focus();
          conferir();
        });
        caixa.append(b);
      }
      prontas.append(caixa);
    };

    desenharContas();
    mostrarSugestoes();
    desenharProntas();
    janelinha.append(cabeca, campoNome, campo, queda, teclado, atalhos, prontas,
                     veredito, ajuda, lista, aplicar);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
    campoNome.focus();
  }

  // --- o painel de harmônicos -----------------------------------------------

  //: O quadro das barras, em pixels de CSS. Fixo, e não medido do pai: medir
  //: era um laço no fasorial (o quadro se ajusta ao canvas e o canvas ao
  //: quadro) e seria o mesmo laço aqui.
  //: A largura de reserva, para quando o pai ainda não foi medido (primeiro
  //: desenho antes de a grade existir). Em uso normal quem manda é a coluna.
  const LARGURA_HARMONICOS = 620;
  const ALTURA_HARMONICOS = 236;

  //: As margens do quadro das barras. A ESQUERDA e a DIREITA são as mesmas
  //: das ondas (`MARGEM`), de propósito: com os dois painéis um debaixo do
  //: outro, a área de desenho tem que começar e terminar na mesma coluna de
  //: pixel — senão a 1ª barra fica deslocada em relação ao início da onda e a
  //: tela ganha um degrau que não significa nada. Em cima e embaixo elas são
  //: próprias: aqui não há eixo de tempo, há rótulo de ordem.
  const MARGEM_HARMONICOS = { topo: 14, baixo: 34 };

  //: Abaixo disto a barra não é desenhada.
  //:
  //: Não é gosto: é o PISO DA MEDIDA. Com a taxa fracionária do SEL a 2000 Hz
  //: (33,3 amostras/ciclo) a janela de um ciclo de tempo deixa 0,31 % de resto
  //: numa ordem vazia — ver `dsp/fasor.espectro`, que traz a medição. Desenhar
  //: abaixo disso é desenhar vazamento do próprio método, e uma fileira de
  //: barrinhas espúrias esconde as três que importam. Com taxa inteira o
  //: espectro é exato e nada se perde: ali não há o que fique abaixo do piso.
  const RUIDO_DA_BARRA = 0.6;

  //: Pico que ganha rótulo em Hz na linha principal: 3 % da fundamental.
  //: Abaixo disso o rótulo vira ruído de texto no fundo do gráfico.
  const PICO_ROTULADO = 3;

  /** As barras marcadas no clique: `id do painel` → Set de `"<sinal>|<ordem>"`.
   *
   * Fora do layout de propósito, como o destaque de um traço: a marca vale
   * enquanto se está olhando para ela. Guardá-la no arquivo da tela faria o
   * usuário reabrir o registro amanhã com a segunda harmônica da fase B
   * marcada sem lembrar por quê.
   */
  const barrasMarcadas = new Map();

  const marcasDoPainel = (id) => {
    let marcas = barrasMarcadas.get(id);
    if (!marcas) { marcas = new Set(); barrasMarcadas.set(id, marcas); }
    return marcas;
  };

  /** O painel de harmônicos: barras do espectro no instante de um cursor.
   *
   * O eixo é **percentual da fundamental de cada sinal**, que é a convenção do
   * ofício ("30 % de terceiro" quer dizer 30 % da fundamental) e a única que
   * deixa corrente e tensão no mesmo desenho sem régua dupla.
   *
   * O preço está dito, e a tabela ao lado é quem o paga: 40 % de uma
   * fundamental de 1 A e 40 % de uma de 400 A desenham a mesma barra. Por isso
   * a coluna «fundamental» fica ao lado de cada sinal, em ampère e volt — é
   * olhando para ela que se sabe de quanto é o percentual, e uma fundamental
   * minúscula salta aos olhos ali.
   */
  function blocoHarmonicos(painel) {
    const el = criar("section", "grafico harmonicos");

    const mais = criar("button", "medida", "+ sinal");
    mais.title = "Acrescentar um sinal. Só entra o que é ONDA — canal "
               + "senoidal e resíduo de grupo. Componente de sequência fica "
               + "de fora: Fortescue é definido sobre fasores de UMA "
               + "frequência, e não há 5º harmônico de um I1.";
    mais.addEventListener("click", () => abrirCatalogoDeSinais(painel, {
      candidatos: comEspectro(),
      vazio: "Nenhum sinal com onda e esse nome fora deste painel.",
      cheio: "Todos os sinais com onda já estão aqui.",
    }));

    // A engrenagem existe aqui pela MESMA razão que nos outros painéis: o
    // lugar dos ajustes é o mesmo em todo gráfico, e procurar a engrenagem
    // num e não achar é pior que achá-la com pouco dentro. Hoje ela tem pouco
    // — a janela e a ordem máxima moram nas tarjas do rodapé, e tarja é
    // informação, não controle. Quando houver ajuste de verdade, ele nasce
    // aqui sem o usuário ter que aprender um lugar novo.
    el.append(cabecalhoDoPainel(painel,
                                [...botaoDaJanela(painel), mais,
                                 ...engrenagemDoPainel(painel, () => [
                                   criar("p", "nada-a-ajustar",
                                         "Este gráfico ainda não tem ajuste "
                                         + "próprio. A janela e a ordem "
                                         + "medida estão nas tarjas do "
                                         + "rodapé."),
                                 ])]));

    // A MESMA grade do gráfico analógico (`grafico-corpo`), e não a do
    // fasorial: o fasorial é quadrado e de largura fixa por natureza — num
    // retângulo, 90° ficaria mais longe do centro que 0°. O espectro é um
    // gráfico de barras como qualquer outro, e lado a lado com as ondas eles
    // têm que ter a mesma largura e a tabela na mesma coluna, senão a tela
    // vira um degrau.
    const corpo = criar("div", "grafico-corpo harmonicos");
    const caixa = criar("div", "tela");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    corpo.append(caixa, tabelaHarmonicos(painel));
    el.append(corpo);
    comMolduras(el, corpo);

    if (!(painel.sinais || []).length) {
      el.append(criar("p", "vazio",
        "Nenhum sinal neste painel. Use o «+ sinal» para escolher as correntes "
        + "ou tensões cujo espectro você quer ver."));
    }

    el.append(fichasDoEspectro(painel));

    el._canvas = canvas;
    el._painel = painel;
    el._harmonicos = true;
    return el;
  }

  //: O que o Fourier deste painel mede. As duas primeiras são UM CICLO, o que
  //: o relé faz por dentro; a terceira é o TRECHO entre os cursores, que é
  //: como se mede o que a carga injeta — ver `leitura.espectro_entre`.
  const JANELAS_DO_ESPECTRO = [
    [1, "cursor 1",
     "O ciclo que termina no cursor 1. É a janela do relé: responde «quanto "
     + "tem AGORA»."],
    [2, "cursor 2",
     "O ciclo que termina no cursor 2. Dois painéis, um em cada cursor, "
     + "comparam a energização com o regime."],
    ["entre", "cursor 2 − 1",
     "O TRECHO inteiro entre os dois cursores, não um ciclo. Responde «quanto "
     + "tem neste regime» — marque a pré-falta e leia o que a carga injeta. O "
     + "trecho é cortado em ciclos INTEIROS: num pedaço quebrado a fundamental "
     + "escorre para as vizinhas e uma senoide pura aparece com 4 % de THD."],
  ];

  const janelaDoPainel = (painel) => {
    const meu = painelPorId(painel.id) || {};
    return meu.cursor === "entre" ? "entre" : (meu.cursor === 2 ? 2 : 1);
  };

  /** O botão que escolhe a janela do espectro, com o menu. */
  function botaoDaJanela(painel) {
    const agora = janelaDoPainel(painel);
    const qual = JANELAS_DO_ESPECTRO.find(([v]) => v === agora)
              || JANELAS_DO_ESPECTRO[0];
    const botao = criar("button", "medida");
    botao.type = "button";
    botao.setAttribute("aria-haspopup", "true");
    botao.setAttribute("aria-expanded", "false");
    botao.append(criar("span", null, qual[1]),
                 criar("span", "seta-do-menu", "▾"));
    botao.title = qual[2];
    const ancora = criar("span", "ancora-de-menu");
    ancora.id = `menu-janela-${painel.id}`;
    botao.addEventListener("click", () => {
      menuSuspenso(ancora.id, "o espectro é de:", (caixa) => {
        for (const [valor, rotulo, explicacao] of JANELAS_DO_ESPECTRO) {
          const linha = criar("label", "opcao");
          const marca = document.createElement("input");
          marca.type = "radio";
          marca.name = `janela-${painel.id}`;
          marca.checked = valor === agora;
          marca.addEventListener("change",
                                 () => escolherJanela(painel.id, valor));
          linha.title = explicacao;
          linha.append(marca, criar("span", null, rotulo));
          caixa.append(linha);
        }
      });
    });
    return [botao, ancora];
  }

  function escolherJanela(id, valor) {
    const meu = painelPorId(id);
    if (!meu) return;
    guardarParaDesfazer();
    meu.cursor = valor;
    // Nada a pedir ao servidor: o espectro de cada cursor E o do trecho já vêm
    // na mesma leitura. Trocar a opção é instantâneo de propósito.
    const vindo = (dados.paineis || []).find((x) => x.id === id);
    if (vindo) vindo.cursor = valor;
    desenharTudo();
  }

  /** A tabela ao lado: a fundamental em unidade de engenharia e o THD. */
  function tabelaHarmonicos(painel) {
    const tabela = criar("table", "mini fasores");
    const cabeca = criar("tr");
    cabeca.append(criar("th", "unidade", "sinal"),
                  criar("th", null, "fundamental"),
                  criar("th", null, "THD"));
    const thead = criar("thead");
    thead.append(cabeca);
    const tbody = criar("tbody");

    for (const sinal of (painel.sinais || [])) {
      const linha = criar("tr");
      const nome = criar("th", "canal");
      const rotulo = criar("span", "rotulo");
      nome.append(rotulo);
      //: A MESMA primeira coluna do fasorial e da tabelinha do cursor:
      //: bolinha com a cor, nome em branco, unidade ao lado. Aqui a cor
      //: estava na LETRA, e letra colorida no meio de nomes brancos se lê
      //: como «este está selecionado» — e as três janelas que escolhem sinal
      //: deixavam de ser irmãs justamente na tabela, que é o que se compara.
      //: A bolinha é clicável, como nas outras: onde a cor está escrita é
      //: onde se troca a cor.
      rotulo.append(bolinhaDoSinal(painel, sinal));
      const seloDoEspectro = seloDoIed(sinal.ied);
      if (seloDoEspectro) rotulo.append(seloDoEspectro);
      rotulo.append(criarNome("span", "nome", sinal.sinal));
      if (sinal.unidade) {
        rotulo.append(criar("span", "unidade-extra", `(${sinal.unidade})`));
      }
      const base = criar("td", "valor-1 vazio-valor", "—");
      const thd = criar("td", "valor-2 vazio-valor", "—");
      linha.append(nome, base, thd);
      tbody.append(linha);
      celulas.push({ painel: painel.id, id: sinal.id, harmonicos: true,
                     celas: [base, thd] });
    }

    tabela.append(thead, tbody);
    return tabela;
  }

  /** As duas células de um sinal na tabela dos harmônicos. */
  function escreverHarmonico(item) {
    const painel = (dados.paineis || []).find((x) => x.id === item.painel);
    const valores = painel ? leituraDoEspectro(painel).valores : null;
    const lido = valores ? valores[item.id] : null;
    const [base, thd] = item.celas;

    const vazio = (cela) => {
      cela.textContent = "—";
      cela.classList.add("vazio-valor");
    };
    if (!lido || lido.fundamental === null || lido.fundamental === undefined) {
      vazio(base); vazio(thd);
      return;
    }
    base.textContent = formatar(lido.fundamental, lido.casas_fasor);
    base.classList.remove("vazio-valor");
    if (lido.thd === null || lido.thd === undefined) vazio(thd);
    else {
      thd.textContent = `${formatar(lido.thd, 1)} %`;
      thd.classList.remove("vazio-valor");
      thd.title = "Raiz da soma dos quadrados das barras acima da "
                + "fundamental, dividida pela fundamental. É o número que "
                + "fecha com o desenho — o «tudo que não é 60 Hz» da "
                + "tabelinha das ondas inclui também a DC e o que está acima "
                + "do teto de ordens, e por isso é maior.";
    }
  }

  /** Uma ficha do rodapé: um rótulo curto, o valor, e a frase inteira no
   * hover quando há mais a dizer.
   *
   * Fichas, e não linhas de texto, porque o rodapé deste painel acumula
   * quatro coisas de naturezas diferentes — o que foi medido, o limite do
   * arquivo, e dois avisos — e em texto corrido elas viram um parágrafo que
   * ninguém lê. A frase longa não se perde: fica no `title`, que é onde ela
   * é lida uma vez e não atrapalha nas outras mil.
   */
  function ficha(rotulo, valor, { tom = "", dica = "" } = {}) {
    const el = criar("span", `ficha${tom ? ` ${tom}` : ""}`);
    if (rotulo) el.append(criar("b", null, rotulo));
    el.append(criar("span", null, valor));
    if (dica) { el.title = dica; el.classList.add("tem-dica"); }
    return el;
  }

  /** O rodapé do painel de harmônicos, em fichas. */
  function fichasDoEspectro(painel) {
    const barra = criar("div", "rodape-do-painel fichas");

    // A ficha da JANELA muda com os cursores: fica guardada para
    // `mostrarJanelasDoEspectro` reescrever sem remontar o painel.
    const daJanela = ficha("janela", "");
    const deRegime = ficha("", "janela em transição", { tom: "atencao" });
    deRegime.hidden = true;
    notasDaJanela.push({ painel: painel.id, nota: daJanela,
                         regime: deRegime });
    barra.append(daJanela);

    // O teto de ordens é do ARQUIVO, e precisa estar escrito: além dele não
    // há zero, há aliasing. Ver `plot/harmonicos.py`.
    //: O teto de ordens é do ARQUIVO. A ficha diz os DOIS números, porque são
    //: dois: o que a taxa distingue (Nyquist) e o que o desenho mostra — que
    //: é uma ordem a menos, porque a vaga da última foi para a contínua.
    const desenhadas = Math.max(1, Math.min(painel.desenhadas || 25,
                                            painel.teto || 1) - 1);
    barra.append(ficha("mede até", `${painel.teto}ª ordem`,
      { dica: `A taxa deste registro distingue até a ${painel.teto}ª raia — é `
            + "o Nyquist da janela, e é esse o limite da medida com precisão. "
            + "A última ordem é sempre a mais frágil: é a que tem menos "
            + `amostras por período. Por isso o desenho vai até a ${desenhadas}ª `
            + "e usa a vaga da última para a contínua. Acima do teto não há "
            + "zero, há aliasing: uma barra plausível na ordem errada." }));

    //: A ressalva da barra DC (média do ciclo, que decai) mora no HOVER dela,
    //: e não numa tarja: «barra 0 · contínua da janela» no rodapé era texto
    //: fixo explicando um rótulo que já diz DC. Pedido dele, 22/10/2026.

    barra.append(deRegime);

    // O aviso que muda a leitura do painel inteiro.
    if (painel.ja_filtrado) {
      const deduzido = painel.filtragem_deduzida !== false;
      barra.append(ficha("", `gravação já filtrada em ${frequenciaDoRegistro()}`
                           + (deduzido ? " (deduzido)" : " (declarado)"),
        { tom: "atencao",
          dica: deduzido
            ? "O programa DEDUZIU que esta gravação já está filtrada: a "
              + "distorção em regime está no nível do ruído de quantização. "
              + "Se for isso mesmo, não há harmônico no arquivo para medir."
            : "O arquivo DECLARA que o relé gravou já filtrado. Não há "
              + "harmônico no arquivo para medir — o que aparecer aqui é "
              + "resto de filtro, não do sistema." }));
    }

    // De que canais saiu o que está no painel (`G1 = IAW, IBW, ICW`). Vem do
    // servidor e só aparece quando há resíduo ou componente na tela.
    for (const linha of (painel.rodape || [])) {
      const corte = linha.indexOf(":");
      barra.append(corte > 0 && corte < 14
        ? ficha(linha.slice(0, corte), linha.slice(corte + 1).trim(),
                { dica: linha })
        : ficha("", linha, { dica: linha }));
    }
    return barra;
  }

  /** Reescreve o «medido sobre …» de todos os painéis de harmônicos.
   *
   * Dizer a janela não é enfeite: "o espectro deste instante" e "a média deste
   * trecho" são leituras diferentes do mesmo desenho, e quantos ciclos
   * entraram muda a segunda. E é aqui que o arredondamento para ciclo inteiro
   * aparece — o usuário marcou 7,3 e mediu 7.
   */
  function mostrarJanelasDoEspectro() {
    for (const { painel: id, nota, regime } of notasDaJanela) {
      if (!nota.isConnected) continue;
      const painel = (dados.paineis || []).find((x) => x.id === id);
      if (!painel) continue;
      const escrever = (rotulo, valor, tom, dica) => {
        nota.replaceChildren(criar("b", null, rotulo), criar("span", null, valor));
        nota.className = `ficha${tom ? ` ${tom}` : ""}${dica ? " tem-dica" : ""}`;
        nota.title = dica || "";
      };
      const fora = avisoDeRegime(painel);
      regime.hidden = !fora;
      regime.title = fora;
      const janela = janelaDoPainel(painel);
      if (janela !== "entre") {
        escrever("janela", `1 ciclo · cursor ${janela}`);
        continue;
      }
      const { erro, ciclos, pedidos } = leituraDoEspectro(painel);
      if (erro) {
        escrever("sem espectro", erro, "atencao");
        regime.hidden = true;
        continue;
      }
      const sobra = pedidos && pedidos - ciclos >= 0.05
                  ? `Você marcou ${formatar(pedidos, 2)} ciclos, e o resto `
                    + "fica de fora para as raias caírem em cima dos "
                    + `múltiplos de ${frequenciaDoRegistro()}.`
                  : "";
      escrever("janela", `${ciclos} ciclo${ciclos === 1 ? "" : "s"} · entre os `
                       + "cursores", sobra ? "arredondado" : "", sobra);
    }
  }

  /** O aviso de janela fora de regime, ou string vazia.
   *
   * Discreto de propósito: meia linha no rodapé, junto do «janela de 1 ciclo»
   * que já está lá, sem cor de erro e sem apagar barra nenhuma. O desenho não
   * está errado — a janela é que pegou o sinal mudando de patamar, e parte do
   * que aparece como harmônico é o vazamento dessa transição. Num inrush, o
   * 2º harmônico daquela janela continua sendo informação de verdade, e quem
   * decide o que fazer com ela é quem está analisando. Ver
   * `fasor.regime_da_janela` para a medição que define o limiar.
   */
  function avisoDeRegime(painel) {
    const valores = leituraDoEspectro(painel).valores;
    if (!valores) return "";
    const fora = (painel.sinais || [])
      .filter((s) => valores[s.id] && valores[s.id].fora_de_regime)
      .map((s) => s.sinal);
    if (!fora.length) return "";
    const quais = fora.length === (painel.sinais || []).length
                ? "" : ` em ${fora.join(", ")}`;
    return `A janela pega o sinal mudando de patamar${quais} `
         + "(chaveamento, início de falta): parte das raias é vazamento da "
         + "transição, e não harmônico do sinal. As barras continuam valendo "
         + "— num inrush o 2º harmônico desta janela é informação de verdade. "
         + "Arraste o cursor para depois da transição para comparar.";
  }

  /** O pacote de espectro que vale para este painel: de um cursor ou do
   * trecho entre os dois. É a mesma leitura; muda só de onde se lê. */
  function leituraDoEspectro(painel) {
    if (janelaDoPainel(painel) === "entre") {
      const entre = medida ? medida.espectro_entre : null;
      return { valores: entre && entre.sinais ? entre.sinais : null,
               erro: entre ? entre.erro : "sem os dois cursores na tela",
               ciclos: entre ? entre.ciclos : null,
               pedidos: entre ? entre.ciclos_pedidos : null };
    }
    const k = janelaDoPainel(painel) === 2 ? 1 : 0;
    const lido = medida && medida.cursores ? medida.cursores[k] : null;
    return { valores: lido && lido.sinais ? lido.sinais : null,
             erro: "", ciclos: 1, pedidos: null };
  }

  /** As leituras de espectro deste painel, na janela dele. */
  function espectrosDoPainel(painel) {
    const valores = leituraDoEspectro(painel).valores;
    const saida = [];
    for (const sinal of (painel.sinais || [])) {
      const v = valores ? valores[sinal.id] : null;
      if (!v || !v.harmonicos || !v.harmonicos.length) continue;
      const base = v.harmonicos[0];
      if (!(base > 0)) continue;
      //: As raias passam a ser indexadas pela ORDEM, e não pela posição: o
      //: índice 0 é a CONTÍNUA e o 1 é a fundamental. O servidor manda as duas
      //: coisas separadas (`continua` e `harmonicos`), porque são duas contas
      //: diferentes da mesma janela — ver `_espectro_da_onda` no Python.
      const raias = [v.continua === null || v.continua === undefined
                       ? 0 : v.continua];
      for (const x of v.harmonicos) raias.push(x === null ? 0 : x);
      //: A LINHA: no trecho, toda raia da janela (`fino`, de 1/ciclos em
      //: 1/ciclos de ordem); num ciclo só, as próprias raias de harmônico.
      const ciclos = Number(leituraDoEspectro(painel).ciclos) || 1;
      const fino = v.fino && v.fino.length ? v.fino : v.harmonicos;
      const linha = [{ ordem: 0, valor: raias[0] }];
      const passoDaLinha = v.fino && v.fino.length ? 1 / ciclos : 1;
      fino.forEach((x, m) => linha.push({ ordem: (m + 1) * passoDaLinha,
                                          valor: x === null ? 0 : x }));
      saida.push({ sinal, base, unidade: sinal.unidade, raias, linha });
    }
    return saida;
  }

  /** O painel de harmônicos desenha BARRAS (o comissionado, 0.6.0) ou o
   *  ESPECTRO em dB. A medida é a mesma; só a figura muda. */
  function pintarHarmonicos(canvas, painel) {
    if ((painelPorId(painel.id) || {}).desenho === "espectro") {
      pintarEspectro(canvas, painel);
    } else {
      pintarBarras(canvas, painel);
    }
  }

  //: O piso do espectro em dB: 0,1 % da fundamental. Abaixo disso está o
  //: vazamento da própria janela (ver `RUIDO_DA_BARRA`), não medida.
  const PISO_DB = -60;

  /** Percentual da fundamental → dB da fundamental, preso ao piso. */
  const emDb = (pct) => (pct > 0 ? Math.max(20 * Math.log10(pct / 100), PISO_DB)
                                 : PISO_DB);

  /** As etiquetas do que está marcado, nos dois desenhos.
   *
   * Empilhadas quando se encostam: com três fases e duas ordens marcadas,
   * seis etiquetas na mesma altura viram uma mancha. Subo a que colide com
   * a anterior, uma linha de cada vez — é o jeito mais simples que ainda
   * deixa todas LEGÍVEIS, que é o que vale mais que o alinhamento.
   */
  function pintarEtiquetasDoEspectro(ctx, etiquetas, x0, largura, topoY) {
    ctx.font = "10.5px var(--mono), monospace";
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    const ALTURA_DA_ETIQUETA = 16;
    const postas = [];
    for (const e of etiquetas.slice().sort((a, b) => a.x - b.x)) {
      const larguraDoTexto = ctx.measureText(e.texto).width + 10;
      // Presa ao quadro: a etiqueta da 1ª ordem sairia pela esquerda, e a da
      // 16ª pela direita.
      const cx = Math.min(Math.max(e.x, x0 + larguraDoTexto / 2),
                          x0 + largura - larguraDoTexto / 2);
      let cy = e.y - 12;
      for (const p of postas) {
        const encosta = Math.abs(p.cx - cx) < (p.larg + larguraDoTexto) / 2
                     && Math.abs(p.cy - cy) < ALTURA_DA_ETIQUETA;
        if (encosta) cy = p.cy - ALTURA_DA_ETIQUETA;
      }
      // Nunca acima do quadro: ali ela sai do canvas e some.
      cy = Math.max(cy, topoY + ALTURA_DA_ETIQUETA / 2);
      postas.push({ cx, cy, larg: larguraDoTexto });
      // `--superficie`, e não `--fundo`: a etiqueta fica POR CIMA das barras
      // e precisa se separar delas. No fundo do quadro ela sumiria no preto.
      ctx.fillStyle = token("--superficie");
      ctx.globalAlpha = 0.94;
      ctx.fillRect(cx - larguraDoTexto / 2, cy - ALTURA_DA_ETIQUETA / 2,
                   larguraDoTexto, ALTURA_DA_ETIQUETA);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = e.cor;
      ctx.lineWidth = 1;
      ctx.strokeRect(cx - larguraDoTexto / 2, cy - ALTURA_DA_ETIQUETA / 2,
                     larguraDoTexto, ALTURA_DA_ETIQUETA);
      ctx.fillStyle = token("--tinta");
      ctx.fillText(e.texto, cx, cy);
    }
  }

  /** O hover dos dois desenhos: o valor exato de cada sinal na ordem `h`. */
  function hoverDoEspectro(canvas) {
    if (canvas._temHover) return;
    canvas._temHover = true;
    canvas.addEventListener("mousemove", (evento) => {
      const d = canvas._harm;
      if (!d) return;
      const r = canvas.getBoundingClientRect();
      const h = d.ordemEm(evento.clientX - r.left);
      if (h === null) { canvas.title = ""; return; }
      const f0 = Number(dados && dados.frequencia_hz) || 60;
      const linhas = [h === 0
        ? "contínua: a média da janela de um ciclo. NÃO é uma contínua "
          + "permanente — decai com a constante X/R; o decremento se vê na "
          + "curva «DC» num gráfico analógico."
        : `${h}º harmônico · ${formatar(h * f0, 0)} Hz`];
      for (const x of d.barras) {
        const v = x.raias[h] || 0;
        const pct = 100 * v / x.base;
        linhas.push(`${x.sinal.sinal}: ${formatar(v, casasDaBase(v))} `
                  + `${x.unidade} — ${formatar(pct, 1)} % da fundamental`
                  + (d.emDb ? ` (${formatar(emDb(pct), 1)} dB)` : ""));
      }
      canvas.title = linhas.join("\n");
    });
  }

  /** As BARRAS — o painel de harmônicos como foi comissionado na 0.6.0,
   *  com a contínua na ordem zero (15/10/2026). */
  function pintarBarras(canvas, painel) {
    const larg = canvas.parentElement.clientWidth || LARGURA_HARMONICOS;
    const alt = ALTURA_HARMONICOS;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${larg}px`;
    canvas.style.height = `${alt}px`;
    dimensionar(canvas, Math.round(larg * dpr), Math.round(alt * dpr));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, larg, alt);

    const m = MARGEM_HARMONICOS;
    const x0 = MARGEM.esq;
    const y0 = alt - m.baixo;
    const largura = larg - MARGEM.esq - MARGEM.dir;
    const altura = y0 - m.topo;
    if (largura < 60 || altura < 40) return;

    const dados_ = espectrosDoPainel(painel);
    const ordens = Math.min(painel.desenhadas || 25, painel.teto || 1,
                            Math.max(...dados_.map((x) => x.raias.length), 1));

    // O eixo fecha em 100 % — a fundamental — e só se estica quando alguma
    // barra passa dela. Da 2ª em diante: o índice 0 é a contínua e o 1 é a
    // fundamental, e esticar o eixo pela contínua de um inrush achataria
    // todo o resto.
    let topo = 100;
    for (const x of dados_) {
      for (let h = 2; h < x.raias.length && h < ordens; h += 1) {
        topo = Math.max(topo, 100 * x.raias[h] / x.base);
      }
    }
    topo = topo > 100 ? escalaDoFasorial(topo / 100) * 100 : 100;

    ctx.save();
    ctx.strokeStyle = token("--linha");
    ctx.fillStyle = token("--suave");
    ctx.font = "10.5px var(--mono), monospace";
    ctx.lineWidth = 1;
    ctx.textBaseline = "middle";
    const riscos = topo <= 100 ? [0, 25, 50, 75, 100] : [0, topo / 4, topo / 2,
                                                         3 * topo / 4, topo];
    for (const v of riscos) {
      const y = y0 - altura * v / topo;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x0 + largura, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.fillText(`${formatar(v, v >= 10 || v === 0 ? 0 : 1)}%`, x0 - 6, y);
    }

    const passo = largura / ordens;
    const quantos = Math.max(dados_.length, 1);
    const larguraDaBarra = Math.max(2, (passo * 0.72) / quantos - 1.4);
    const marcas = marcasDoPainel(painel.id);
    const etiquetas = [];
    ctx.textBaseline = "alphabetic";
    for (let h = 0; h < ordens; h += 1) {
      const xi = x0 + h * passo + passo * 0.14;
      dados_.forEach((x, n) => {
        const valor = x.raias[h] || 0;
        const pct = 100 * valor / x.base;
        if (pct < RUIDO_DA_BARRA) return;
        const h_ = altura * Math.min(pct, topo) / topo;
        const cor = corDoSinal(x.sinal, painel);
        const xb = xi + n * (larguraDaBarra + 1.4);
        ctx.fillStyle = cor;
        ctx.fillRect(xb, y0 - h_, larguraDaBarra, h_);
        if (marcas.has(`${x.sinal.id}|${h}`)) {
          ctx.strokeStyle = token("--tinta");
          ctx.lineWidth = 1.5;
          ctx.strokeRect(xb - 0.75, y0 - h_ - 0.75, larguraDaBarra + 1.5, h_ + 1.5);
          etiquetas.push({
            x: xb + larguraDaBarra / 2, y: y0 - h_, cor,
            texto: `${x.sinal.sinal} · ${h === 0 ? "contínua" : `${h}ª`} · `
                 + `${formatar(valor, casasDaBase(valor))} ${x.unidade}`
                 + ` · ${formatar(pct, 1)}%`,
          });
        }
      });
      // A ordem embaixo. Com muitas ordens, de dois em dois: rótulo colado em
      // rótulo não se lê, e a contínua, o 1 e o 2 são os que importam.
      const cada = passo >= 18 ? 1 : passo >= 10 ? 2 : 5;
      if (h <= 2 || h % cada === 0) {
        ctx.fillStyle = token(h === 0 ? "--energia-dc" : "--suave");
        ctx.textAlign = "center";
        ctx.fillText(h === 0 ? "DC" : String(h),
                     xi + (quantos * (larguraDaBarra + 1.4)) / 2, y0 + 14);
      }
    }
    ctx.fillStyle = token("--suave");
    ctx.textAlign = "center";
    // Sem «DC é a contínua da janela»: o rótulo da barra já diz DC, e o
    // hover dela diz o resto. Pedido dele, 22/10/2026.
    ctx.fillText("ordem do harmônico · % da fundamental de cada sinal",
                 x0 + largura / 2, alt - 6);
    pintarEtiquetasDoEspectro(ctx, etiquetas, x0, largura, m.topo);
    ctx.restore();

    canvas._harm = {
      barras: dados_, painel, emDb: false,
      ordemEm: (px) => {
        const h = Math.floor((px - x0) / passo);
        return h < 0 || h >= ordens ? null : h;
      },
      // A COLUNA inteira conta, de cima a baixo do quadro: uma 11ª de 2 %
      // tem três pixels de altura, e exigir o clique em cima deles seria
      // oferecer um alvo que ninguém acerta.
      alvoEm: (px, py) => {
        if (py > y0 + 4 || py < m.topo) return null;
        const h = Math.floor((px - x0) / passo);
        if (h < 0 || h >= ordens || !dados_.length) return null;
        const xi = x0 + h * passo + passo * 0.14;
        const n = Math.min(Math.max(Math.floor((px - xi) / (larguraDaBarra + 1.4)), 0),
                           dados_.length - 1);
        const alvo = dados_[n];
        if (100 * (alvo.raias[h] || 0) / alvo.base < RUIDO_DA_BARRA) return null;
        return { chave: `${alvo.sinal.id}|${h}`, ordem: h, dado: alvo, posicao: n };
      },
    };
    hoverDoEspectro(canvas);
  }

  /** O ESPECTRO: linha por frequência, em dB da fundamental. */
  function pintarEspectro(canvas, painel) {
    // Medido do PAI, como no gráfico analógico. Aqui não há o laço do
    // fasorial: a coluna é `1fr` de uma grade, e a largura dela não depende
    // do que está dentro — o canvas é `width: 100 %` dela.
    const larg = canvas.parentElement.clientWidth || LARGURA_HARMONICOS;
    const alt = ALTURA_HARMONICOS;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${larg}px`;
    canvas.style.height = `${alt}px`;
    dimensionar(canvas, Math.round(larg * dpr), Math.round(alt * dpr));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, larg, alt);

    const m = MARGEM_HARMONICOS;
    const x0 = MARGEM.esq;
    const y0 = alt - m.baixo;
    const largura = larg - MARGEM.esq - MARGEM.dir;
    const altura = y0 - m.topo;
    if (largura < 60 || altura < 40) return;

    const dados_ = espectrosDoPainel(painel);
    const ordens = Math.min(painel.desenhadas || 25, painel.teto || 1,
                            Math.max(...dados_.map((x) => x.raias.length), 1));

    // O eixo vai a 100 % — a fundamental. Só passa disso quando um harmônico
    // passa dela, que acontece de verdade num TC saturado em regime leve.
    // O eixo fecha em 100 % — a fundamental — e só se estica quando alguma
    // barra passa dela. Esticar sempre para o degrau seguinte deixava metade
    // do quadro vazio num espectro normal.
    // Em dB da fundamental: 0 dB é a fundamental, e o eixo desce até o piso.
    // Sobe acima de 0 só quando um harmônico (da 2ª em diante) passa dela.
    let topoDb = 0;
    for (const x of dados_) {
      for (let h = 2; h < x.raias.length && h < ordens; h += 1) {
        topoDb = Math.max(topoDb, emDb(100 * x.raias[h] / x.base));
      }
    }
    topoDb = Math.ceil(topoDb / 10) * 10;

    ctx.save();
    ctx.strokeStyle = token("--linha");
    ctx.fillStyle = token("--suave");
    ctx.font = "10.5px var(--mono), monospace";
    ctx.lineWidth = 1;
    ctx.textBaseline = "middle";
    for (let v = PISO_DB; v <= topoDb; v += 10) {
      const y = y0 - altura * (v - PISO_DB) / (topoDb - PISO_DB);
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x0 + largura, y);
      ctx.stroke();
      ctx.textAlign = "right";
      ctx.fillText(`${v} dB`, x0 - 6, y);
    }

    //: O eixo vai da contínua (0) até a última ordem desenhada; a posição é
    //: a ORDEM, que pode ser fracionária na linha fina do trecho.
    const ultima = Math.max(ordens - 1, 1);
    const X = (ordem) => x0 + largura * ordem / ultima;
    const Y = (pct) => y0 - altura * (Math.min(emDb(pct), topoDb) - PISO_DB)
                                   / (topoDb - PISO_DB);
    const f0 = Number(dados && dados.frequencia_hz) || 60;
    const marcas = marcasDoPainel(painel.id);

    // As ordens embaixo, com uma linha fina em cada harmônico inteiro.
    ctx.textBaseline = "alphabetic";
    const cada = largura / ultima >= 22 ? 1 : 2;
    for (let h = 0; h <= ultima; h += 1) {
      ctx.strokeStyle = token("--linha");
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      ctx.moveTo(X(h), m.topo);
      ctx.lineTo(X(h), y0);
      ctx.stroke();
      ctx.globalAlpha = 1;
      if (h <= 1 || h % cada === 0) {
        ctx.fillStyle = token(h === 0 ? "--energia-dc" : "--suave");
        ctx.textAlign = "center";
        ctx.fillText(h === 0 ? "0" : `${h}ª`, X(h), y0 + 14);
      }
    }

    // O Nyquist: além dele não há zero, há aliasing. Só se ele cabe no eixo.
    if (painel.teto && painel.teto <= ultima) {
      ctx.strokeStyle = token("--ruim");
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(X(painel.teto), m.topo);
      ctx.lineTo(X(painel.teto), y0);
      ctx.stroke();
      ctx.lineWidth = 1;
      ctx.fillStyle = token("--ruim");
      ctx.textAlign = "right";
      ctx.fillText(`Nyquist ${formatar(painel.teto * f0, 0)} Hz`,
                   X(painel.teto) - 4, m.topo + 10);
    }

    // As linhas: o primeiro sinal por cima e mais grosso, os outros atrás.
    const etiquetas = [];
    for (let n = dados_.length - 1; n >= 0; n -= 1) {
      const x = dados_[n];
      const cor = corDoSinal(x.sinal, painel);
      const pontos = x.linha.filter((p) => p.ordem <= ultima + 1e-9);
      ctx.strokeStyle = cor;
      ctx.lineWidth = n === 0 ? 1.7 : 1.1;
      ctx.globalAlpha = n === 0 ? 1 : 0.75;
      ctx.beginPath();
      pontos.forEach((p, k) => {
        const px = X(p.ordem);
        const py = Y(100 * p.valor / x.base);
        if (k) ctx.lineTo(px, py); else ctx.moveTo(px, py);
      });
      ctx.stroke();
      ctx.globalAlpha = 1;

      // O que foi marcado no clique: um ponto e a etiqueta com o número.
      for (let h = 0; h < x.raias.length && h <= ultima; h += 1) {
        if (!marcas.has(`${x.sinal.id}|${h}`)) continue;
        const valor = x.raias[h] || 0;
        const pct = 100 * valor / x.base;
        ctx.fillStyle = cor;
        ctx.beginPath();
        ctx.arc(X(h), Y(pct), 3.5, 0, 2 * Math.PI);
        ctx.fill();
        etiquetas.push({
          x: X(h), y: Y(pct), cor,
          texto: `${x.sinal.sinal} · ${h === 0 ? "contínua" : `${h}ª`} · `
               + `${formatar(valor, casasDaBase(valor))} ${x.unidade}`
               + ` · ${formatar(emDb(pct), 1)} dB`,
        });
      }
    }

    // Os PICOS, só da linha principal: rótulo em todo pico que passa de 3 %
    // da fundamental, fora da saia da contínua e longe do anterior. Rotular
    // as três fases empilharia nove números no mesmo lugar.
    if (dados_.length) {
      const x = dados_[0];
      const p = x.linha;
      let anterior = -1e9;
      ctx.fillStyle = token("--tinta");
      ctx.textAlign = "center";
      for (let k = 1; k < p.length - 1; k += 1) {
        const v = p[k].valor;
        if (p[k].ordem < 0.5 || p[k].ordem > ultima) continue;
        if (100 * v / x.base < PICO_ROTULADO) continue;
        let maior = true;
        for (let d = -3; d <= 3; d += 1) {
          const q = p[k + d];
          if (q && q.valor > v) { maior = false; break; }
        }
        if (!maior || p[k].ordem - anterior < 0.66) continue;
        anterior = p[k].ordem;
        ctx.fillText(`${formatar(p[k].ordem * f0, 0)} Hz`, X(p[k].ordem),
                     Math.max(m.topo + 8, Y(100 * v / x.base) - 7));
      }
    }

    ctx.fillStyle = token("--suave");
    ctx.textAlign = "center";
    ctx.fillText("ordem do harmônico · dB da fundamental de cada sinal",
                 x0 + largura / 2, alt - 6);
    pintarEtiquetasDoEspectro(ctx, etiquetas, x0, largura, m.topo);
    ctx.restore();

    canvas._harm = {
      barras: dados_, painel, emDb: true,
      ordemEm: (px) => {
        const h = Math.round((px - x0) * ultima / largura);
        return h < 0 || h > ultima ? null : h;
      },
      // A ordem inteira mais perto do clique; entre os sinais, o de ponto
      // mais perto na vertical.
      alvoEm: (px, py) => {
        if (py > y0 + 4 || py < m.topo) return null;
        const h = Math.round((px - x0) * ultima / largura);
        if (h < 0 || h > ultima) return null;
        let melhor = null;
        dados_.forEach((alvo, n) => {
          const dist = Math.abs(Y(100 * (alvo.raias[h] || 0) / alvo.base) - py);
          if (!melhor || dist < melhor.dist) melhor = { alvo, n, dist };
        });
        if (!melhor) return null;
        if (100 * (melhor.alvo.raias[h] || 0) / melhor.alvo.base < RUIDO_DA_BARRA) {
          return null;
        }
        return { chave: `${melhor.alvo.sinal.id}|${h}`, ordem: h,
                 dado: melhor.alvo, posicao: melhor.n };
      },
    };
    hoverDoEspectro(canvas);
  }


  /** Marca (ou desmarca) a barra sob o clique, e repinta.
   *
   * Entra por `escolherSinal`, e não por um `click` do canvas, por um motivo
   * de navegador: o arrasto do gráfico captura o ponteiro no `pointerdown`,
   * e com isso o `click` nunca chega ao canvas. `escolherSinal` já roda no
   * `pointerup` e já traz o "clique parado" separado do arrasto — de graça,
   * e com o mesmo limiar de 4 px do resto da tela.
   *
   * A regra do gesto é a do traço no gráfico analógico, que o rodapé ensina:
   * clique simples marca uma; com Ctrl, vai somando. Clicar numa já marcada
   * tira a marca — senão não haveria como desmarcar a última sem sair do
   * quadro.
   */
  function marcarBarra(canvas, x, y, acumular) {
    const d = canvas._harm;
    if (!d) return;
    const alvo = d.alvoEm(x, y);
    const marcas = marcasDoPainel(d.painel.id);
    if (!alvo) {
      // Clique no quadro fora de qualquer barra desenhada limpa tudo — a
      // mesma regra do resto da tela: parar de olhar é desmarcar.
      if (!acumular && marcas.size) { marcas.clear(); repintar(); }
      return;
    }
    if (acumular) {
      if (marcas.has(alvo.chave)) marcas.delete(alvo.chave);
      else marcas.add(alvo.chave);
    } else if (marcas.size === 1 && marcas.has(alvo.chave)) {
      marcas.clear();
    } else {
      marcas.clear();
      marcas.add(alvo.chave);
    }
    window.__marcas = [...marcas];   // para teste no navegador, como `__janela`
    repintar();
  }

  // --- o painel fasorial ----------------------------------------------------

  //: O raio do círculo, em pixels de CSS, e a folga até a borda do quadro.
  //: O diagrama é QUADRADO: num retângulo, 90° fica mais longe do centro que
  //: 0°, e a seta de maior módulo passa a ser a que aponta para cima.
  const RAIO_FASORIAL = 132;
  const FOLGA_FASORIAL = 30;

  //: Quanto do raio o MAIOR fasor ocupa quando a escala é automática. Sobra
  //: para a ponta da seta e para o nome dela não saírem do quadro.
  const OCUPACAO = 0.86;

  //: O comprimento MÍNIMO de uma seta, em fração do raio útil.
  //:
  //: Numa falta, a corrente da fase sã é 1 % da da fase em curto, e
  //: proporcional ela vira um ponto no centro: o ângulo dela some junto, e é
  //: justamente dele que sai a classificação da falta. Quem fica abaixo do
  //: mínimo é desenhado NO mínimo, com o trecho inventado ATENUADO — o
  //: pedaço sólido vai até onde o fasor realmente termina, e o apagado é
  //: enchimento para o ângulo continuar legível.
  //:
  //: Já foi haste tracejada (invisível em dezessete pixels) e ponta vazada
  //: (oito pixels de marca no meio do desenho). A marca agora é a haste
  //: INTEIRA, que é o que se enxerga num fasor pequeno — e ela é
  //: quantitativa: onde o sólido acaba, o fasor acabou.
  //:
  //: Subiu de 0,15 para 0,20 com a régua do registro: na pré-falta de um
  //: registro de falta TODA corrente de carga trava, e é ali que se lê o
  //: ângulo delas. Vinte e três pixels é o toco que ainda aponta.
  const MINIMO_DA_SETA = 0.20;

  //: A opacidade do trecho inventado da seta travada.
  const APAGADO_DA_SETA = 0.32;

  //: Abaixo disto não se desenha nada: o ângulo de um fasor tão pequeno é
  //: ruído do conversor, e uma seta tracejada apontando para um ruído é pior
  //: que nenhuma seta. Entrada de relé não cabeada (`sem_sinal`) também não
  //: entra, por conta própria.
  const RUIDO_DA_SETA = 0.002;

  /** O painel fasorial: um instante do registro, visto como fasores.
   *
   * Ele não calcula nada. Módulo e ângulo vêm da leitura do cursor — a mesma
   * que alimenta a tabelinha dos outros gráficos, com a mesma janela de um
   * ciclo. Duas contas do mesmo fasor é como o desenho e a tabela divergem.
   *
   * Por isso ele também não tem eixo do tempo, nem gestos de zoom: o que ele
   * mostra é UM instante, e quem o escolhe é o cursor dos gráficos de onda.
   */
  /** O botão de ajustes de um gráfico: a engrenagem.
   *
   * O que entra nela e o que fica de fora
   * =====================================
   *
   * Fica DE FORA o que se mexe durante uma medição — o cursor, o «+ sinal», a
   * referência de ângulo e a calculadora. Entra o que se ajusta uma vez e não
   * se toca mais: a escala, o diagrama lateral, o vínculo do triângulo.
   *
   * A régua é essa, e não «os menos usados»: um controle escondido custa um
   * clique toda vez, e o que se usa no meio de uma leitura não pode custar
   * clique nenhum.
   *
   * A engrenagem é DESENHADA com dentes, e não com raios saindo de um círculo
   * — com raios ela vira um sol, que é outra coisa.
   */
  function engrenagemDoPainel(painel, montar) {
    const ancoraId = `menu-ajustes-${painel.id}`;
    const botao = criar("button", "medida engrenagem");
    botao.type = "button";
    botao.title = "Ajustes deste gráfico.";
    botao.setAttribute("aria-label", "ajustes deste gráfico");
    botao.setAttribute("aria-haspopup", "true");
    botao.setAttribute("aria-expanded", "false");
    botao.innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14" '
      + 'aria-hidden="true" focusable="false">'
      + '<path d="M15.30 6.79L15.30 9.21L13.41 9.44L12.84 10.81L14.02 12.30L12.30 14.02L10.81 12.84L9.44 13.41L9.21 15.30L6.79 15.30L6.56 13.41L5.19 12.84L3.70 14.02L1.98 12.30L3.16 10.81L2.59 9.44L0.70 9.21L0.70 6.79L2.59 6.56L3.16 5.19L1.98 3.70L3.70 1.98L5.19 3.16L6.56 2.59L6.79 0.70L9.21 0.70L9.44 2.59L10.81 3.16L12.30 1.98L14.02 3.70L12.84 5.19L13.41 6.56Z" fill="currentColor"/>'
      + '<circle cx="8" cy="8" r="2.5" fill="var(--superficie)"/></svg>';
    const ancora = criar("span", "ancora-de-menu");
    ancora.id = ancoraId;
    botao.addEventListener("click", () => {
      menuSuspenso(ancoraId, "ajustes do gráfico", (caixa) => {
        for (const b of montar()) {
          // Uma string no meio da lista é TÍTULO DE GRUPO, e não um botão:
          // com meia dúzia de ajustes na mesma caixa, o olho precisa de um
          // lugar onde parar. Escolha dele, 19/10/2026.
          if (typeof b === "string") {
            caixa.append(criar("div", "titulo-de-grupo", b));
            continue;
          }
          const linha = criar("div", "linha-de-ajuste");
          linha.append(b);
          caixa.append(linha);
        }
      });
    });
    return [botao, ancora];
  }

  function blocoFasorial(painel) {
    const el = criar("section", "grafico fasorial");

    // De qual cursor este painel mostra os fasores. É de CADA painel: dois
    // fasoriais lado a lado, um em cada cursor, é a comparação pré-falta ×
    // falta — e foi assim que o usuário pediu.
    const meu = painelPorId(painel.id) || {};
    const qual = meu.cursor === 2 ? 2 : 1;
    const botaoCursor = criar("button", "medida", `cursor ${qual}`);
    botaoCursor.title = `Os fasores são do instante do cursor ${qual}. `
                      + "Clique para passar para o outro — dois painéis "
                      + "fasoriais, um em cada cursor, comparam a pré-falta "
                      + "com a falta lado a lado.";
    botaoCursor.addEventListener("click", () => alternarCursorDoPainel(painel.id));

    const mais = criar("button", "medida", "+ sinal");
    mais.title = "Acrescentar um sinal a este diagrama. Só entra o que tem "
               + "fasor de 60 Hz: os canais senoidais, o resíduo de um grupo "
               + "e as componentes de sequência.";
    mais.addEventListener("click", () => abrirCatalogoFasorial(painel));

    // Visível: o cursor, a referência de ângulo, o «+ sinal» e a calculadora
    // — os quatro que se mexem no meio de uma leitura. O resto, na
    // engrenagem. Ver `engrenagemDoPainel`.
    const botoes = [botaoCursor, ...botaoDaReferencia(painel), mais,
                    botaoDeConta(painel)];
    botoes.push(...engrenagemDoPainel(painel, () => botaoDaEscala(painel)));

    // O «+» do diagrama lateral fica na DIREITA, junto do ▲▼×: ele não ajusta
    // este gráfico — cria outro, como o ×, que tira. Ajuste é o que a
    // engrenagem guarda; criar e tirar moram no mesmo canto.
    //
    // E só no painel que AINDA não tem par: dois diagramas é o que cabe numa
    // linha, e um terceiro espremeria os três. O da direita não o oferece —
    // quem desfaz o par é o × dele.
    const direita = [];
    if (!temPar(painel.id) && !eDaDireita(painel.id)) {
      const aoLado = criar("button", "mexer", "+");
      aoLado.title = "Põe um segundo diagrama de fasores, vazio, à direita "
                   + "deste. É a comparação que se faz num evento: os fasores "
                   + "de antes da falta ao lado dos de durante, na mesma "
                   + "tela. Dá no mesmo arrastar para cima deste um diagrama "
                   + "que já existe.";
      aoLado.addEventListener("click", () => criarParFasorial(painel.id));
      direita.push(aoLado);
    }
    el.append(cabecalhoDoPainel(painel, botoes, null, direita));

    const corpo = criar("div", "corpo-fasorial");
    const caixa = criar("div", "tela-fasorial");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    corpo.append(caixa, tabelaFasorial(painel));
    el.append(corpo);
    comMolduras(el, corpo);

    if (!(painel.sinais || []).length) {
      el.append(criar("p", "vazio",
        "Nenhum sinal neste diagrama. Use o «+ sinal» para escolher as "
        + "correntes e tensões que você quer comparar em ângulo."));
    }

    // A mesma nota do gráfico de ondas: de que três canais do arquivo saiu
    // cada grupo. Aqui ela pesa mais — um diagrama de `3I0`, `I1` e `IN` é
    // feito só de sinais sem nome de arquivo a herdar.
    if ((painel.rodape || []).length) {
      const nota = criar("div", "rodape-do-painel");
      for (const linha of painel.rodape) nota.append(criar("div", null, linha));
      el.append(nota);
    }

    el._canvas = canvas;
    el._painel = painel;
    el._fasorial = true;
    return el;
  }

  /** O botão que escolhe o zero dos ângulos DESTE diagrama, com o menu.
   *
   * O botão mostra quem é a referência agora — `∠ VAY` —, porque é a pergunta
   * que se faz ao olhar um ângulo: "a partir de quê?". Um botão escrito
   * «referência» obrigaria a abrir o menu para saber a resposta.
   *
   * Clicar no nome, na lista ao lado, faz a mesma coisa: são dois caminhos
   * para um estado só (`painel.referencia`), e cada um serve a um momento —
   * o nome é o atalho de quem já está lendo a lista, o botão é onde se
   * procura quando não se sabe que o atalho existe.
   */
  function botaoDaReferencia(painel) {
    const ancoraId = `menu-ref-${painel.id}`;
    const botao = criar("button", "medida");
    botao.type = "button";
    botao.setAttribute("aria-haspopup", "true");
    botao.setAttribute("aria-expanded", "false");
    const ancora = criar("span", "ancora-de-menu");
    ancora.id = ancoraId;

    const meu = painelPorId(painel.id) || {};
    const escolhido = meu.referencia ? nomeDoSinal(meu.referencia) : "";
    // Sem escolha, quem responde é a regra do servidor — a tensão da fase A.
    // O nome dela vem na leitura; sem leitura ainda, o botão diz «automática».
    // No plano complexo quem decide a automática é a janela, não a leitura:
    // o caminho é calculado lá, com a referência que ela escolheu.
    const automatica = (painel.zero && !painel.zero.escolhida && painel.zero.nome)
                    || (medida && medida.referencia && medida.referencia.nome)
                    || "automática";
    botao.append(criar("span", null, `∠ ${escolhido || automatica}`),
                 criar("span", "seta-do-menu", "▾"));
    botao.title = escolhido
      ? `Os ângulos deste diagrama são medidos a partir de ${escolhido}.`
        + " Clique para trocar."
      : "Os ângulos deste diagrama são medidos a partir da referência "
        + `automática (${automatica}): a tensão da fase A. Clique para `
        + "escolher outro sinal.";

    botao.addEventListener("click", () => {
      menuSuspenso(ancoraId, "os ângulos saem de:", (caixa) => {
        /* **Todos os sinais com fasor, e não só os do diagrama.** Medir o
           ângulo das correntes a partir de `VAY` é a conta de direcionalidade
           do ofício, e ela não obriga a tensão a estar desenhada ali. O fasor
           da referência é calculado no servidor como o de qualquer outro —
           ver `plot/paineis.py`. */
        const todos = comFasor();
        const noDiagrama = new Set((painel.sinais || []).map((s) => s.id));

        const campo = document.createElement("input");
        campo.type = "search";
        campo.className = "busca-do-menu";
        campo.placeholder = "procurar…";
        // O menu fecha no Esc, e dentro de um campo de busca o Esc é «limpar»:
        // sem isto, apagar o que se digitou fechava o menu junto.
        campo.addEventListener("keydown", (e) => {
          if (e.key === "Escape" && campo.value) e.stopPropagation();
        });
        caixa.append(campo);

        const lista = criar("div", "opcoes-do-menu");
        caixa.append(lista);

        const desenhar = () => {
          const procura = campo.value.trim().toUpperCase();
          const cabe = (x) => !procura
            || combinaNome(x.linha || x.nome, procura);
          const opcoes = [];
          if (!procura) {
            opcoes.push({ chave: null, rotulo: `automática (${automatica})`,
                          dica: "A tensão da fase A do registro, que é o que "
                              + "o SIGRA e o relé usam quando ninguém diz "
                              + "outra coisa." });
          }
          // Os que estão no diagrama primeiro: são os candidatos prováveis, e
          // num relé com vinte e um canais a lista inteira esconderia os três
          // que estão na tela.
          const ordenados = todos.filter(cabe).sort(
            (a, b) => Number(noDiagrama.has(b.id)) - Number(noDiagrama.has(a.id)));
          for (const x of ordenados) {
            opcoes.push({ chave: x.id, rotulo: x.linha || x.nome,
                          grupo: x.canal < 0 ? x.grupo : "",
                          calculado: x.canal < 0,
                          fora: !noDiagrama.has(x.id),
                          dica: `${x.linha || x.nome} passa a valer 0°, e os `
                              + "ângulos deste diagrama são medidos a partir "
                              + "dele."
                              + (noDiagrama.has(x.id) ? ""
                                 : " Ele não precisa estar no diagrama: o "
                                   + "fasor dele é calculado do mesmo jeito.") });
          }

          lista.replaceChildren();
          if (!opcoes.length) {
            lista.append(criar("p", "vazio", "Nenhum sinal com fasor com esse nome."));
            return;
          }
          for (const opcao of opcoes) {
            const linha = criar("label", "opcao");
            const marca = document.createElement("input");
            marca.type = "radio";
            marca.name = `ref-${painel.id}`;
            marca.checked = (meu.referencia || null) === opcao.chave;
            marca.addEventListener("change", () => {
              escolherReferencia(painel.id, opcao.chave, true);
            });
            linha.title = opcao.dica;
            linha.append(marca);
            const nome = criar("span", "nome-da-linha"
                               + (opcao.calculado ? " calculado" : ""));
            nomeComGrupo(nome, opcao.rotulo, opcao.grupo || "");
            linha.append(nome);
            // O que não está no diagrama fica marcado: escolher a referência
            // não acrescenta sinal nenhum à tela, e sem a marca a lista
            // sugeriria o contrário.
            if (opcao.fora) {
              const etiqueta = criar("span", "fora-do-diagrama", "fora");
              etiqueta.title = "Não está neste diagrama — serve de referência "
                             + "mesmo assim.";
              linha.append(etiqueta);
            }
            lista.append(linha);
          }
        };

        campo.addEventListener("input", desenhar);
        desenhar();
      });
      // O foco vai para a busca, não para o primeiro rádio: quem abre este
      // menu num relé com vinte e um canais vem procurar, não percorrer.
      document.querySelector(`#${ancoraId} .busca-do-menu`)?.focus();
    });
    return [botao, ancora];
  }

  /** O painel lateral: módulo e ângulo de cada fasor, em números.
   *
   * O desenho responde "qual está adiantado"; o número responde "quanto". As
   * duas perguntas são feitas ao mesmo tempo num laudo, e por isso as duas
   * respostas ficam lado a lado.
   *
   * As células são preenchidas por `mostrarLeitura`, pelo mesmo caminho das
   * tabelinhas dos gráficos de onda: `celulas` casa tudo pelo id do sinal.
   */
  function tabelaFasorial(painel) {
    const tabela = criar("table", "mini fasores");
    const cabeca = criar("tr");
    cabeca.append(criar("th", "unidade", "sinal"),
                  criar("th", null, "módulo"),
                  criar("th", null, "ângulo"));
    const thead = criar("thead");
    thead.append(cabeca);
    const tbody = criar("tbody");

    for (const sinal of (painel.sinais || [])) {
      const linha = criar("tr");
      const nome = criar("th", "canal");
      const rotulo = criar("span", "rotulo");
      nome.append(rotulo);
      // A MESMA primeira coluna da tabelinha do cursor: bolinha com a cor,
      // nome em branco, unidade ao lado. A cor estava na LETRA, e letra
      // colorida no meio de nomes brancos se lê como «este está
      // selecionado» — aqui, pior: a tabela do fasorial TEM um estado de
      // marcação na letra, o sublinhado da referência de ângulo. Duas coisas
      // na mesma tinta.
      //
      // E a bolinha é clicável, como nas outras telas: onde a cor está
      // escrita é onde se troca a cor.
      //
      // No TRIÂNGULO não: lá o desenho pinta por FASE (`corDaFase`), e não
      // pela paleta do painel. Uma bolinha que abrisse a paleta ali ofereceria
      // trocar uma cor que o desenho ignora — e, pior, ela mostraria a cor da
      // paleta enquanto a seta no quadro ao lado está na cor da fase. A
      // bolinha do triângulo é etiqueta, e copia o desenho.
      if (painel.tipo === "triangulo") {
        const fixa = criar("span", "bolinha-fixa");
        fixa.style.background = corDaFase(sinal.fase);
        rotulo.append(fixa);
      } else {
        rotulo.append(bolinhaDoSinal(painel, sinal));
      }

      // O nome é botão: clicar faz este sinal ser o zero dos ângulos DESTE
      // diagrama. Ângulo absoluto não existe — alguém tem que ser o zero, e
      // aqui é onde se escolhe quem.
      const alvo = criar("button", "refere nome", sinal.sinal);
      alvo.title = `${sinal.sinal} — clique para medir os ângulos deste `
                 + "diagrama a partir dele";
      alvo.addEventListener("click",
                            () => escolherReferencia(painel.id, sinal.id));
      rotulo.append(alvo);
      if (sinal.unidade) {
        rotulo.append(criar("span", "unidade-extra", `(${sinal.unidade})`));
      }

      const modulo = criar("td", "valor-1 vazio-valor", "—");
      const angulo = criar("td", "valor-2 vazio-valor", "—");
      linha.append(nome, modulo, angulo);
      tbody.append(linha);
      celulas.push({ painel: painel.id, id: sinal.id, fasorial: true,
                     celas: [modulo, angulo], botao: alvo,
                     referencia: sinal.id });
    }

    // --- as tensões de LINHA, só no triângulo ---------------------------
    //
    // Só os VALORES, sem seta nenhuma: os lados do triângulo já SÃO as
    // tensões de linha, e desenhá-las de novo saindo do neutro seria a mesma
    // grandeza em dois lugares com geometrias diferentes. O triângulo mais
    // simples se lê melhor — decisão do Alexandre.
    //
    // Na cor do TRIÂNGULO, não na de fase: tensão de linha não é grandeza de
    // fase, e pintar `VAB` de azul quebraria a regra de uma cor, um
    // significado. Ver `claude/decisoes-de-interface.md`.
    //: E só quando há o que derivar: sem vínculo escolhido o diagrama está
    //: vazio, e cinco linhas de travessão não são tabela — são a promessa de
    //: uma medida que não existe. Vazio, o painel diz uma coisa só: escolha o
    //: vínculo. Pedido dele.
    if (painel.tipo === "triangulo" && (painel.sinais || []).length) {
      const celas = [];
      //: Uma linha de valor DERIVADO: não é canal do arquivo, então não tem
      //: cor para escolher — a bolinha aqui é etiqueta, não botão. O resto da
      //: coluna é igual ao de um canal, que é o ponto: a primeira coluna da
      //: tabela tem uma forma só.
      const derivada = (nome, cor, classe) => {
        const linha = criar("tr", classe);
        const cabeca = criar("th", "canal");
        const rotulo = criar("span", "rotulo");
        const bolinha = criar("span", "bolinha-fixa");
        bolinha.style.background = cor;
        rotulo.append(bolinha, criarNome("span", "nome nome-de-linha", nome));
        cabeca.append(rotulo);
        const modulo = criar("td", "valor-1 vazio-valor", "—");
        const angulo = criar("td", "valor-2 vazio-valor", "—");
        linha.append(cabeca, modulo, angulo);
        tbody.append(linha);
        celas.push({ nome, modulo, angulo, rotulo });
        return rotulo;
      };

      // As tensões de LINHA: só os valores, sem seta nenhuma — os lados do
      // triângulo já SÃO elas, e desenhá-las de novo saindo do neutro seria a
      // mesma grandeza em dois lugares com geometrias diferentes.
      //
      // Na cor do TRIÂNGULO, não na de fase: tensão de linha não é grandeza
      // de fase, e pintar `VAB` de azul quebraria a regra de uma cor, um
      // significado. Ver `claude/decisoes-de-interface.md`.
      for (const nome of ["VAB", "VBC", "VCA"]) {
        derivada(nome, token("--destaque"), "de-linha");
      }

      // O DESLOCAMENTO DO NEUTRO, em número.
      //
      // Ele é a única coisa deste gráfico que não se lê de relance: a
      // distância do baricentro à cruz é pequena em pixels mesmo quando é
      // grande em volts. E é ela que separa uma falta à terra de uma falta
      // entre fases.
      //
      // UMA linha, e é a 3V0 (escolha dele, 15/10). Eram duas — `V0` e `3V0`,
      // a mesma grandeza a um fator de três —, e a pergunta «qual destes dois
      // eu uso?» é exatamente o que uma tela de proteção não deve criar.
      //
      // A 3V0 é a útil: é o que o delta aberto entrega, é o que um 59N ou um
      // 67N mede, e é nessa grandeza que o ajuste do relé está escrito. A V0
      // é a componente simétrica «pura» — serve para conferir a conta de
      // componentes, e continua à vista como a SETA VERDE do desenho, que é
      // a distância do baricentro à cruz. Os dois papéis ficam, sem os dois
      // números lado a lado.
      derivada("3V0", token("--bom"), "de-neutro").title =
        "3V0 = VA + VB + VC — a tensão residual: o que o delta aberto entrega "
        + "e o que um 59N mede. É nela que o ajuste do relé está escrito. A "
        + "seta verde do desenho é V0 = 3V0 / 3, a distância do baricentro à "
        + "cruz — a mesma grandeza, dividida por três.";

      celasDeLinha.set(painel.id, celas);
    }

    tabela.append(thead, tbody);
    //: Sem NENHUMA linha, a tabela inteira some -- cabeçalho incluído. Um
    //: «sinal · módulo · ângulo» com nada embaixo é moldura de uma medida que
    //: não existe, e o painel vazio já diz o que fazer na frase dele.
    tabela.hidden = !tbody.children.length;
    const quadro = criar("div", "lado-fasorial");
    quadro.append(tabela);
    // A base do pu de cada grandeza, escrita. Ela vem do RTC/RTP do arquivo, e
    // o arquivo às vezes declara a relação do transformador sem ser a nominal
    // do equipamento — então o número fica à vista em vez de ficar implícito
    // no tamanho das setas.
    // A nota do 1 pu é refeita a cada leitura: quando a base não vem do
    // arquivo, ela é a maior leitura daquela grandeza NAQUELE instante — então
    // ela muda quando o cursor anda.
    const nota = criar("p", "base-do-pu");
    quadro.append(nota);
    notasDoPu.push({ painel: painel.id, nota });
    return quadro;
  }

  /** Reescreve o «1 pu = …» de todos os diagramas fasoriais da tela. */
  function mostrarBasesDoPu() {
    for (const { painel, nota } of notasDoPu) {
      if (!nota.isConnected) continue;
      // Com um campo aberto, refazer a nota tiraria o campo de debaixo do
      // dedo no meio da digitação — e a leitura é refeita a cada movimento
      // do cursor.
      if (nota.querySelector(".base-campo")) continue;
      const meu = painelPorId(painel) || {};
      const vindo = (dados.paineis || []).find((x) => x.id === painel);
      // Sem escala não há pu, e uma base escrita embaixo de um diagrama que
      // não a usa é um número para o usuário tentar casar com o desenho.
      const bases = (vindo && meu.escala) ? basesDoPainel(vindo) : [];
      nota.replaceChildren();
      if (!bases.length) continue;
      nota.append(criar("span", null, "1 pu = "));
      bases.forEach((b, i) => {
        if (i) nota.append(criar("span", null, " · "));
        const botao = criar("button", "base-valor", b.texto);
        botao.type = "button";
        const minhas = (painelPorId(painel) || {}).bases || {};
        botao.classList.toggle("digitada", !!minhas[b.unidade]);
        botao.classList.toggle("sem-base", b.doRegistro);
        botao.title = b.origem;
        botao.addEventListener("click",
                               () => editarBase(painel, b.unidade, botao));
        nota.append(botao);
      });
      // De onde o número saiu, escrito. Estava só no hover, e hover não
      // existe no celular nem num relatório impresso — e «1 pu = 2,651 A» sem
      // explicação é um número que ninguém reconhece. Clicar troca.
      if (bases.some((b) => b.doRegistro)) {
        const fonte = criar("span", "fonte-da-base",
                            bases.every((b) => b.doRegistro)
                              ? " — o maior deste diagrama no registro"
                              : " — o amarelo é o maior deste diagrama no "
                                + "registro");
        fonte.title = "O arquivo não declara uma nominal utilizável para esta "
                    + "grandeza, então o 1 pu é o maior fasor dela ENTRE OS "
                    + "SINAIS DESTE DIAGRAMA, no registro inteiro. Clique no "
                    + "número para digitar a nominal de verdade.";
        nota.append(fonte);
      }
    }
  }

  /** As bases do pu do painel, uma por grandeza, já formatadas.
   *
   * A do arquivo quando ela serve; a maior leitura daquela grandeza no
   * instante do cursor quando não serve. Ver `plot/fasorial.py` para por que a
   * segunda existe: o relé do parque grava a RELAÇÃO no lugar da nominal.
   */
  function basesDoPainel(painel) {
    const minhas = (painelPorId(painel.id) || {}).bases || {};
    const vistas = new Map();
    for (const x of fasoresDoPainel(painel)) {
      const unidade = x.sinal.unidade;
      if (vistas.has(unidade)) continue;
      const digitada = minhas[unidade];
      vistas.set(unidade, {
        unidade,
        valor: x.base,
        texto: `${formatar(x.base, casasDaBase(x.base))} ${unidade}`,
        doRegistro: x.semBase,
        origem: digitada
          ? "você digitou esta base. Clique nela para mudar; apague para "
            + "voltar ao que o programa acha."
          : x.semBase
            ? "o maior fasor desta grandeza no registro inteiro — não veio do "
              + `arquivo: ${x.sinal.base_origem || ""}. Clique para digitar a `
              + "nominal."
            : `${x.sinal.base_origem || ""}. Clique para digitar outra.`,
      });
    }
    return [...vistas.values()];
  }

  /** Troca o «1 pu» de uma grandeza por um campo, e guarda o que for digitado.
   *
   * A base é da TELA, como a cor de um traço: ela não muda número nenhum — o
   * módulo em ampère continua o mesmo na tabela — e por isso não vai ao
   * servidor. Entra no Ctrl+Z junto com o resto do arranjo.
   */
  function editarBase(idDoPainel, unidade, botao) {
    const meu = painelPorId(idDoPainel);
    if (!meu) return;
    const campo = document.createElement("input");
    campo.type = "text";
    campo.className = "base-campo";
    campo.value = String((meu.bases || {})[unidade] || "").replace(".", ",");
    campo.title = `1 pu em ${unidade}. Apague para voltar ao automático.`;
    campo.setAttribute("aria-label", `base do pu em ${unidade}`);

    let pronto = false;
    const terminar = (guardar) => {
      if (pronto) return;
      pronto = true;
      const texto = campo.value.trim().replace(",", ".");
      campo.replaceWith(botao);
      if (!guardar) return;
      const valor = Number(texto);
      const antes = (meu.bases || {})[unidade];
      if (texto && (!isFinite(valor) || valor <= 0)) return;
      guardarParaDesfazer();
      meu.bases = { ...(meu.bases || {}) };
      if (!texto) delete meu.bases[unidade];
      else meu.bases[unidade] = valor;
      if (antes === meu.bases[unidade]) return;
      desenharTudo();
    };
    campo.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter") terminar(true);
      if (evento.key === "Escape") { evento.stopPropagation(); terminar(false); }
    });
    campo.addEventListener("blur", () => terminar(true));
    botao.replaceWith(campo);
    campo.focus();
    campo.select();
  }

  /** Quantas casas a base leva: TRÊS algarismos significativos.
   *
   * Duas casas fixas arredondavam a base derivada de um TP em secundário —
   * 0,0664 kV — para «0,07 kV», que não é 66,4 V nem é nada: some justamente
   * a precisão que faz o pu valer alguma coisa. Com significativos, 13,8 kV
   * continua «13,8» e 0,0664 kV sai inteiro.
   */
  const casasDaBase = (v) => {
    const x = Math.abs(v);
    if (!(x > 0)) return 2;
    const casas = 2 - Math.floor(Math.log10(x));
    return Math.min(6, Math.max(0, casas));
  };

  /** O fasor de cada sinal do painel, no cursor que ele mostra.
   *
   * Em pu quando há base; em pu da MAIOR daquela grandeza quando não há. O
   * segundo caso é o `.CEV`, que não declara relação nenhuma: sem ele o
   * diagrama ficaria vazio num arquivo inteiro de um fabricante.
   */
  function fasoresDoPainel(painel) {
    const meu = painelPorId(painel.id) || {};
    const k = meu.cursor === 2 ? 1 : 0;
    const lido = medida && medida.cursores ? medida.cursores[k] : null;
    const valores = lido && lido.sinais ? lido.sinais : null;

    const brutos = (painel.sinais || []).map((sinal) => {
      const v = valores ? valores[sinal.id] : null;
      const modulo = v && v.fundamental !== null ? v.fundamental : null;
      return { sinal, modulo, angulo: anguloNoPainel(painel, sinal.id, valores) };
    });

    // A base de cada grandeza, na ordem em que uma vence a outra: a que o
    // usuário digitou, a do arquivo, e o maior fasor daquela unidade no
    // REGISTRO inteiro (que o servidor manda em `pico`).
    //
    // O `pico` é do registro e não do instante: depois que o disjuntor abre,
    // normalizar os 0,2 A de fuga por eles mesmos os mandaria ao raio como se
    // fossem falta.
    const digitadas = meu.bases || {};
    const maior = new Map();
    for (const x of brutos) {
      if (x.sinal.base || !x.sinal.pico) continue;
      const antes = maior.get(x.sinal.unidade) || 0;
      if (x.sinal.pico > antes) maior.set(x.sinal.unidade, x.sinal.pico);
    }

    const saida = [];
    for (const x of brutos) {
      if (x.modulo === null || x.angulo === null) continue;
      const digitada = digitadas[x.sinal.unidade];
      const base = digitada || x.sinal.base || maior.get(x.sinal.unidade) || 0;
      if (!base) continue;
      saida.push({ ...x, pu: x.modulo / base, base,
                   semBase: !digitada && !x.sinal.base });
    }
    return saida;
  }

  /** Desenha o diagrama. Só canvas, como todo gráfico desta tela. */
  /* ------------------------------------------------------------------
   * O TRIÂNGULO DE TENSÕES
   * ------------------------------------------------------------------
   *
   * As três tensões de fase saem do neutro; as pontas formam um triângulo
   * cujos lados são as tensões de linha. A FORMA diz o tipo da falta — um
   * vértice caído é monofásica, um lado achatado é bifásica, encolher
   * inteiro é trifásica — e o BARICENTRO é V0, porque `V0 = (Va+Vb+Vc)/3` é
   * literalmente o centro de massa das três pontas.
   *
   * Os seis sinais vêm do VÍNCULO, não de uma lista que o usuário monta: o
   * vínculo já diz qual trinca de tensão pertence ao mesmo vão de qual trinca
   * de corrente. Ver `plot/triangulo.py`.
   */
  /* As células das tensões de LINHA na tabela do triângulo, por painel.
   *
   * Elas não vêm da leitura do cursor como as outras: são DERIVADAS dos
   * fasores de fase (`V_AB = V_A − V_B`), e por isso se preenchem na hora de
   * pintar, que é quando os fasores existem. Guardar as células num mapa é o
   * que permite preenchê-las de lá sem refazer a tabela a cada repintura. */
  const celasDeLinha = new Map();

  const CAMADAS_DO_TRIANGULO = [
    // O rótulo diz a GRANDEZA, não o adjetivo. «linha», «fase» e «corrente»
    // lado a lado se leem como três coisas da mesma família, e as duas
    // primeiras são tensão — num painel que mostra tensão E corrente, isso é
    // exatamente o que não pode ficar implícito.
    ["linha", "tensões de linha",
     "Os lados do triângulo, que são as tensões de linha, mais o baricentro "
     + "e a seta do deslocamento do neutro."],
    ["fase", "tensões de fase", "As três tensões fase-neutro, saindo da cruz."],
    ["corrente", "correntes", "As três correntes, em escala própria — uma "
     + "corrente de falta e uma tensão afundada não cabem na mesma régua."],
  ];

  const camadasDoPainel = (painel) => {
    const meu = painelPorId(painel.id) || {};
    const quais = meu.camadas || painel.camadas || ["linha", "fase", "corrente"];
    return new Set(quais);
  };

  /** Os botões que acendem e apagam cada camada.
   *
   * Três botões independentes, e não um seletor de três estados: dá para
   * querer as tensões sem as correntes, ou as correntes sozinhas. Existem
   * porque as duas grandezas se cruzam — numa falta BC-T a corrente da fase C
   * cai praticamente em cima da tensão da fase A, e com tudo aceso não se lê
   * nenhuma das duas.
   */
  function botoesDasCamadas(painel) {
    const acesas = camadasDoPainel(painel);
    return CAMADAS_DO_TRIANGULO.map(([chave, rotulo, dica]) => {
      const b = criar("button", "medida" + (acesas.has(chave) ? " escolhido" : ""),
                      rotulo);
      b.type = "button";
      b.title = dica;
      b.addEventListener("click", () => {
        const meu = painelPorId(painel.id);
        if (!meu) return;
        const quais = new Set(camadasDoPainel(painel));
        if (quais.has(chave)) quais.delete(chave);
        else quais.add(chave);
        // Nunca todas apagadas: um quadro em branco não tem como sair dele.
        if (!quais.size) quais.add(chave);
        meu.camadas = CAMADAS_DO_TRIANGULO
          .map(([c]) => c).filter((c) => quais.has(c));
        desenharTudo();
      });
      return b;
    });
  }

  /** A fase em destaque neste painel, ou `null`. */
  const destaqueDoPainel = (painel) => {
    const meu = painelPorId(painel.id) || {};
    return meu.destaque || null;
  };

  /** O botão que escolhe de qual vínculo este triângulo sai. */
  function botaoDoVinculoDoTriangulo(painel) {
    const b = criar("button", "medida", painel.par || "escolher vínculo");
    b.type = "button";
    b.title = "De qual par corrente×tensão este triângulo sai. O par se faz "
            + "em «editar grupos», dentro do «+ sinal» — o OscLab não casa "
            + "corrente com tensão sozinho.";
    b.addEventListener("click", () => abrirEscolhaDoVinculo(painel));
    return b;
  }

  //: Os textos da janelinha do vínculo. Ela serve a DOIS painéis — o
  //: triângulo e o plano de impedância —, e o que cada um perde sem vínculo
  //: não é a mesma coisa: o triângulo não desenha nada, o plano com uma
  //: trinca de cada já sai sozinho. Um texto só mentiria para um dos dois.
  function abrirEscolhaDoVinculo(painel, textos = {}) {
    const titulo = textos.titulo || "De onde sai este triângulo";
    const sub = textos.sub || "um par corrente×tensão, com as tensões de fase";
    const semNenhum = textos.vazio
      || "Nenhum vínculo neste registro. Faça um em «+ sinal» → «editar "
       + "grupos» → «vincular»: é lá que se diz qual trinca de tensão "
       + "pertence ao mesmo vão de qual trinca de corrente.";
    const janelinha = criar("dialog", "busca vinculo");
    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());
    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, titulo),
                  criar("span", "sub-do-cabeca", sub),
                  fechar);
    const lista = criar("div", "lista-de-grupos");
    const opcoes = painel.vinculos || [];
    if (!opcoes.length) lista.append(criar("p", "vazio", semNenhum));
    for (const v of opcoes) {
      const item = criar("button", "opcao-de-vinculo" + (v.vale ? "" : " apagada"));
      item.type = "button";
      item.append(criar("span", "chip-do-grupo", v.par));
      if (!v.vale) {
        // Apagado, e NÃO escondido: um vínculo que some da lista se lê como
        // vínculo que não existe. O motivo fica escrito ao lado.
        item.append(criar("span", "porque-da-folha", v.motivo));
        item.disabled = true;
        item.title = v.motivo;
      } else if (v.vinculo === painel.vinculo) {
        item.classList.add("escolhida");
        item.append(criar("span", "etiqueta", "em uso"));
      }
      item.addEventListener("click", () => {
        const meu = painelPorId(painel.id);
        if (meu) { meu.vinculo = v.vinculo; meu.nome = ""; meu.do_padrao = true; }
        janelinha.close();
        recarregar();
      });
      lista.append(item);
    }
    janelinha.append(cabeca, lista);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    fecharAoClicarFora(janelinha);
    janelinha.showModal();
  }

  function blocoTriangulo(painel) {
    const el = criar("section", "grafico fasorial triangulo");
    const meu = painelPorId(painel.id) || {};
    const qual = meu.cursor === 2 ? 2 : 1;
    const botaoCursor = criar("button", "medida", `cursor ${qual}`);
    botaoCursor.title = `O triângulo é do instante do cursor ${qual}. `
                      + "Clique para passar para o outro — dois triângulos, "
                      + "um em cada cursor, comparam a pré-falta com a falta.";
    botaoCursor.addEventListener("click", () => alternarCursorDoPainel(painel.id));

    //: O VÍNCULO ficava na engrenagem, e saiu de lá a pedido dele: ele decide
    //: DE ONDE o triângulo inteiro sai, e sem ele o painel não desenha nada.
    //: Um botão que o painel não dispensa não é ajuste — é o painel. Fica
    //: logo depois do cursor, antes das camadas, que é a ordem em que se
    //: responde «de onde?» e só então «o que mostrar?».
    el.append(cabecalhoDoPainel(painel, [
      botaoCursor, botaoDoVinculoDoTriangulo(painel),
      ...botoesDasCamadas(painel),
      ...engrenagemDoPainel(painel, () => [criar("p", "nada-a-ajustar",
        "Este gráfico não tem ajuste próprio. O vínculo e as camadas estão "
        + "no cabeçalho, e o que cada número é está no hover da tabela.")]),
    ]));

    const corpo = criar("div", "corpo-fasorial");
    const caixa = criar("div", "tela-fasorial");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    // Clicar numa fase destaca ela e esmaece o resto — e clicar de novo
    // desfaz. Esmaecer, e não apagar: apagando some o contexto que faz o
    // destaque significar alguma coisa.
    canvas.addEventListener("click", (evento) => {
      const alvo = faseNoTriangulo(canvas, painel, evento);
      const atual = painelPorId(painel.id);
      if (!atual) return;
      atual.destaque = (alvo && alvo !== atual.destaque) ? alvo : null;
      repintar();
      desenharTabelaDoTriangulo(el, painel);
    });
    corpo.append(caixa, tabelaFasorial(painel));
    el.append(corpo);
    comMolduras(el, corpo);

    for (const aviso of (painel.avisos || [])) {
      const nota = criar("p", "vazio", aviso);
      el.append(nota);
    }

    el._painel = painel;
    el._canvas = canvas;
    return el;
  }

  /** Qual seta foi clicada, pela proximidade angular. `null` se foi longe. */
  function faseNoTriangulo(canvas, painel, evento) {
    const caixa = canvas.getBoundingClientRect();
    const x = evento.clientX - caixa.left - caixa.width / 2;
    const y = evento.clientY - caixa.top - caixa.height / 2;
    if (Math.hypot(x, y) < 12) return null;          // o centro é o neutro
    const ang = Math.atan2(-y, x) * 180 / Math.PI;
    let melhor = null;
    let menor = 18;                                   // graus de tolerância
    for (const f of fasoresDoPainel(painel)) {
      const fase = f.sinal.fase;
      if (!fase) continue;
      let d = Math.abs(((f.angulo - ang + 540) % 360) - 180);
      d = 180 - d;
      if (d < menor) { menor = d; melhor = fase; }
    }
    return melhor;
  }

  function desenharTabelaDoTriangulo(el, painel) {
    const antiga = el.querySelector(".tabela-fasorial");
    if (antiga) antiga.replaceWith(tabelaFasorial(painel));
  }

  function pintarTriangulo(canvas, painel) {
    const lado = 2 * (RAIO_FASORIAL + FOLGA_FASORIAL);
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${lado}px`;
    canvas.style.height = `${lado}px`;
    dimensionar(canvas, Math.round(lado * dpr), Math.round(lado * dpr));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, lado, lado);
    const cx = lado / 2;
    const cy = lado / 2;
    const raio = lado / 2 - FOLGA_FASORIAL;
    if (raio <= 10) return;

    const dizer = (texto, dy) => {
      ctx.save();
      ctx.fillStyle = token("--suave");
      ctx.font = "11px var(--mono), monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(texto, cx, cy + dy);
      ctx.restore();
    };
    pintarRosaDosVentos(ctx, cx, cy, raio, null);
    if (!painel.vinculo) { dizer("escolha o vínculo deste triângulo", 0); return; }
    const fasores = fasoresDoPainel(painel);
    if (!fasores.length) {
      const meu = painelPorId(painel.id) || {};
      dizer(`ponha o cursor ${meu.cursor === 2 ? 2 : 1} num gráfico`, -8);
      dizer("(tecla 1 ou 2 sobre a onda)", 8);
      return;
    }

    // As tensões vêm primeiro, na ordem A, B, C; depois as correntes. É a
    // ordem que `triangulo.sinais_do_vinculo` monta, e contar com ela aqui
    // evita adivinhar grandeza por unidade — que erraria num arquivo que
    // declara a tensão em `kV` e a corrente em `kA`.
    const porFase = (lista) => {
      const mapa = new Map();
      for (const f of lista) if (f.sinal.fase) mapa.set(f.sinal.fase, f);
      return mapa;
    };
    const tensoes = porFase(fasores.slice(0, 3));
    const correntes = porFase(fasores.slice(3, 6));
    const FASES = ["A", "B", "C"];
    if (FASES.some((f) => !tensoes.has(f))) {
      dizer("faltam tensões deste vínculo", 0);
      return;
    }

    // Escalas INDEPENDENTES, uma por grandeza. Numa falta a tensão afunda e a
    // corrente dispara: numa régua só, a corrente sai voando para fora do
    // quadro e a pré-falta vira um toco no centro — e o que este gráfico
    // responde é FORMA, que some junto.
    const maiorDe = (mapa) => Math.max(...[...mapa.values()]
      .map((f) => Math.abs(f.modulo || 0)), 1e-12);
    const escalaV = (raio * 0.72) / maiorDe(tensoes);

    /* A régua das CORRENTES sai do REGISTRO INTEIRO, não do instante do
     * cursor — a mesma régua do diagrama fasorial (`reguasDoPainel`).
     *
     * Com a régua do instante — que é o que havia aqui —, a maior corrente
     * daquele instante recebia 88 % do raio, fosse ela qual fosse. Na
     * pré-falta, com as três entradas lendo o ruído do conversor
     * (0,0011 A, 0,0009 A, 0,0058 A, medido no registro dele), a maior delas
     * virava uma seta gigante atravessando o círculo, com um ângulo que é
     * ruído puro. É a mesma razão pela qual a régua do fasorial já sai do
     * registro: a mesma corrente não pode mudar de tamanho sem nada ter
     * acontecido com ela.
     *
     * Nas TENSÕES a régua continua a do instante, de propósito: ali o que se
     * lê é a FORMA do triângulo — vértice caído, lado achatado —, e ela é
     * relativa entre as três por natureza.
     */
    const reguas = reguasDoPainel(fasores);
    const limiteI = ((reguas.get("A") || {}).limite) || 1;
    const ponto = (f, escala) => {
      const r = (f.modulo || 0) * escala;
      const a = (f.angulo || 0) * Math.PI / 180;
      return [cx + r * Math.cos(a), cy - r * Math.sin(a)];
    };

    const acesas = camadasDoPainel(painel);
    const destaque = destaqueDoPainel(painel);
    const forte = (fase) => !destaque || destaque === fase;
    const corDaFaseOuApagada = (fase) =>
      forte(fase) ? corDaFase(fase) : token("--linha");

    preencherTensoesDeLinha(painel, tensoes);

    const pontas = FASES.map((f) => ponto(tensoes.get(f), escalaV));

    if (acesas.has("linha")) {
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(pontas[0][0], pontas[0][1]);
      ctx.lineTo(pontas[1][0], pontas[1][1]);
      ctx.lineTo(pontas[2][0], pontas[2][1]);
      ctx.closePath();
      ctx.fillStyle = token("--destaque-fraco");
      ctx.globalAlpha = 0.55;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = token("--destaque");
      ctx.lineWidth = 1.6;
      ctx.stroke();
      ctx.restore();
    }

    /* As CORRENTES ganham comprimento mínimo, como no fasorial — e só elas.
     *
     * Numa falta monofásica a corrente da fase sã é 3 A ao lado de 101 A da
     * fase em curto: proporcional, ela vira um ponto no centro, e o ÂNGULO
     * dela some junto. É justamente do ângulo das três que sai a
     * classificação da falta, então o desenho estava apagando o que ele
     * existe para mostrar. Quem fica abaixo do mínimo é desenhado NO mínimo,
     * com o trecho inventado apagado: o pedaço sólido vai até onde a corrente
     * realmente termina.
     *
     * Nas TENSÕES não: ali o comprimento é a leitura — vértice caído é falta
     * à terra, lado achatado é bifásica —, e um mínimo mentiria sobre a forma
     * do triângulo. O número verdadeiro das duas continua na tabela ao lado.
     */
    if (acesas.has("corrente")) {
      const util = raio * 0.88;
      const minimo = util * MINIMO_DA_SETA;
      for (const fase of FASES) {
        const f = correntes.get(fase);
        if (!f) continue;
        /* PISO DE RUÍDO, antes de tudo — o mesmo do fasorial.
         *
         * Uma corrente de 0,001 % da régua não tem ângulo: tem ruído de
         * quantização do conversor. Desenhá-la no comprimento mínimo seria
         * dar ângulo ao que não tem, e o mínimo existe justamente para
         * tornar o ângulo legível. Entrada não cabeada também não entra. */
        const emPu = Math.abs(f.pu || 0) / limiteI;
        if (f.sinal.sem_sinal || emPu < RUIDO_DA_SETA) continue;
        const real = Math.min(emPu, 1) * util;
        const curta = real < minimo;
        const a = (f.angulo || 0) * Math.PI / 180;
        const comp = curta ? minimo : real;
        const x = cx + comp * Math.cos(a);
        const y = cy - comp * Math.sin(a);
        setaDoTriangulo(ctx, cx, cy, x, y, corDaFaseOuApagada(fase),
                        forte(fase) ? 2.4 : 1.4, true, curta ? real : 0);
      }
    }

    if (acesas.has("fase")) {
      FASES.forEach((fase, i) => {
        const [x, y] = pontas[i];
        setaDoTriangulo(ctx, cx, cy, x, y, corDaFaseOuApagada(fase),
                        forte(fase) ? 2.6 : 1.5, false);
        const d = Math.hypot(x - cx, y - cy) || 1;
        ctx.save();
        ctx.fillStyle = corDaFaseOuApagada(fase);
        ctx.font = "12px var(--mono), monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(fase, cx + (x - cx) * (1 + 13 / d),
                           cy + (y - cy) * (1 + 13 / d));
        ctx.restore();
      });
    }

    // O BARICENTRO: `V0 = (Va+Vb+Vc)/3` é o centro de massa das três pontas.
    // A distância dele até a cruz é o deslocamento do neutro — é o que separa
    // uma falta à terra de uma falta entre fases, e não aparece em lugar
    // nenhum das ondas.
    if (acesas.has("linha")) {
      const bx = (pontas[0][0] + pontas[1][0] + pontas[2][0]) / 3;
      const by = (pontas[0][1] + pontas[1][1] + pontas[2][1]) / 3;
      if (Math.hypot(bx - cx, by - cy) > 1.5) {
        setaDoTriangulo(ctx, cx, cy, bx, by, token("--bom"), 2.2, false);
      }
      ctx.save();
      ctx.fillStyle = token("--bom");
      ctx.beginPath();
      ctx.arc(bx, by, 3.2, 0, 2 * Math.PI);
      ctx.fill();
      ctx.restore();
    }

    // A cruz do neutro, por cima de tudo: é a referência de que o resto fala.
    ctx.save();
    ctx.strokeStyle = token("--tinta");
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(cx - 5, cy); ctx.lineTo(cx + 5, cy);
    ctx.moveTo(cx, cy - 5); ctx.lineTo(cx, cy + 5);
    ctx.stroke();
    ctx.restore();
  }

  /** `V_AB = V_A − V_B`, e as outras duas, escritas na tabela.
   *
   * Subtração de FASORES, não de módulos: `|V_A| − |V_B|` daria zero num
   * sistema equilibrado, e a tensão de linha é √3 vezes a de fase. O erro
   * sairia na unidade certa e sem nada na tela denunciando.
   */
  function preencherTensoesDeLinha(painel, tensoes) {
    const celas = celasDeLinha.get(painel.id);
    if (!celas) return;
    const acesa = camadasDoPainel(painel).has("linha");
    const unidade = (tensoes.get("A") || {}).sinal
                 ? (tensoes.get("A").sinal.unidade || "") : "";
    const rad = (g) => (g || 0) * Math.PI / 180;
    //: Um fasor em partes real e imaginária. `null` quando a fase não veio.
    const parte = (f) => (f && f.modulo !== null && f.modulo !== undefined)
      ? [f.modulo * Math.cos(rad(f.angulo)), f.modulo * Math.sin(rad(f.angulo))]
      : null;
    const A = parte(tensoes.get("A"));
    const B = parte(tensoes.get("B"));
    const C = parte(tensoes.get("C"));

    const apagar = (cela) => {
      cela.modulo.textContent = "—";
      cela.angulo.textContent = "—";
      cela.modulo.classList.add("vazio-valor");
      cela.angulo.classList.add("vazio-valor");
    };
    const escrever = (cela, re, im) => {
      const mod = Math.hypot(re, im);
      const ang = Math.atan2(im, re) * 180 / Math.PI;
      cela.modulo.textContent = formatar(mod, mod >= 100 ? 1 : 3);
      cela.angulo.textContent = `${formatar(ang, 1)}°`;
      cela.modulo.classList.remove("vazio-valor");
      cela.angulo.classList.remove("vazio-valor");
    };

    const PARES = { VAB: ["A", "B"], VBC: ["B", "C"], VCA: ["C", "A"] };
    for (const cela of celas) {
      // Apagada a camada das tensões de linha, estes valores somem junto com
      // o triângulo: eles SÃO o triângulo, escrito em número — e o
      // deslocamento do neutro é a seta que sai do baricentro, que some com
      // ele. Tabela e desenho dizendo coisas diferentes é o que não pode.
      if (!acesa || !A || !B || !C) { apagar(cela); continue; }

      if (PARES[cela.nome]) {
        const [de, para] = PARES[cela.nome];
        const x = parte(tensoes.get(de));
        const y = parte(tensoes.get(para));
        if (!x || !y) { apagar(cela); continue; }
        escrever(cela, x[0] - y[0], x[1] - y[1]);
        cela.rotulo.title = `${cela.nome} = V${de} − V${para}, subtração de `
                          + `fasores${unidade ? ` (${unidade})` : ""}`;
        continue;
      }

      // V0 e 3V0: a MESMA soma, dividida ou não por três. Soma de FASORES —
      // somar módulos daria 3·V num sistema equilibrado, onde o certo é zero,
      // e o erro sairia na unidade certa e na ordem de grandeza certa.
      const re = A[0] + B[0] + C[0];
      const im = A[1] + B[1] + C[1];
      const quanto = cela.nome === "V0" ? 3 : 1;
      escrever(cela, re / quanto, im / quanto);
    }
  }

  /** Uma seta do triângulo. `solidoAte` é o comprimento, em pixels, até onde
   *  ela é VERDADE — o resto é enchimento, e sai apagado.
   *
   * Zero (o padrão) quer dizer «a seta inteira é verdade», que é o caso das
   * tensões: ali o comprimento é proporcional sempre, porque a FORMA do
   * triângulo é a leitura e esticar um lado destruiria o diagnóstico.
   */
  function setaDoTriangulo(ctx, x0, y0, x1, y1, cor, grossura, tracejada,
                           solidoAte = 0) {
    const dx = x1 - x0;
    const dy = y1 - y0;
    const comp = Math.hypot(dx, dy);
    if (comp < 2) return;
    const ang = Math.atan2(dy, dx);
    ctx.save();
    ctx.strokeStyle = cor;
    ctx.fillStyle = cor;
    ctx.lineWidth = grossura;
    ctx.lineCap = "round";
    if (tracejada) ctx.setLineDash([3, 3]);
    //: O trecho inventado ANTES, apagado, e o verdadeiro por cima: assim a
    //: emenda não deixa falha, e o que é medida fica na tinta cheia.
    if (solidoAte > 0 && solidoAte < comp) {
      const mx = x0 + Math.cos(ang) * solidoAte;
      const my = y0 + Math.sin(ang) * solidoAte;
      ctx.save();
      ctx.globalAlpha = 0.3;
      ctx.beginPath();
      ctx.moveTo(mx, my);
      ctx.lineTo(x1, y1);
      ctx.stroke();
      ctx.restore();
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(mx, my);
      ctx.stroke();
      ctx.setLineDash([]);
      const p0 = 7;
      ctx.save();
      ctx.globalAlpha = 0.3;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x1 - p0 * Math.cos(ang - 0.4), y1 - p0 * Math.sin(ang - 0.4));
      ctx.lineTo(x1 - p0 * Math.cos(ang + 0.4), y1 - p0 * Math.sin(ang + 0.4));
      ctx.closePath();
      ctx.fill();
      ctx.restore();
      ctx.restore();
      return;
    }
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    ctx.setLineDash([]);
    const p = 7;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x1 - p * Math.cos(ang - 0.4), y1 - p * Math.sin(ang - 0.4));
    ctx.lineTo(x1 - p * Math.cos(ang + 0.4), y1 - p * Math.sin(ang + 0.4));
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }


  /* ======================================================================
   * O PLANO DE IMPEDÂNCIA
   * ======================================================================
   *
   * Um ponto por instante, no plano R × X, com a impedância que o relé mediu
   * naquele laço. A trajetória sai da carga — longe, no primeiro quadrante —,
   * mergulha para dentro das zonas quando a falta começa e foge para o
   * infinito quando o disjuntor abre. É de um olhar que se lê a que distância
   * ficou a falta e em que zona ela caiu.
   *
   * O que NÃO está escrito dentro do quadro: explicação. Lá dentro ficam só
   * palavras de operação — `Z1`, `Z2`, `100 % da LT`, `MTA` — e os números
   * dos eixos. De onde veio cada ajuste, que relação de TC/TP, que k0: tudo
   * isso desce para as fichas do rodapé. Escolha dele, 20/10/2026.
   *
   * O conteúdo vem pronto de `plot/impedancia.py`: pontos, zonas, parâmetros da linha,
   * k0 e a origem de cada número. Aqui não se calcula impedância nenhuma —
   * só se desenha o que veio, e se escreve de onde veio.
   */
  //: A altura do quadro. Mais baixo que isso e a Z3 não cabe junto da carga;
  //: mais alto e o painel empurra os digitais para fora da tela.
  const ALTURA_IMPEDANCIA = 360;
  const MARGEM_IMPEDANCIA = { esq: 46, dir: 16, topo: 16, baixo: 28 };

  //: A cor de cada zona. Vermelho na Z1 porque ela é a que não tem tempo:
  //: entrar nela é trip instantâneo. O âmbar e o turquesa seguem a ordem do
  //: alcance. A TRAJETÓRIA fica em `--tinta` — ela é o assunto, as zonas são
  //: referência —, e é por isso que a Z3 pôde ficar com o turquesa.
  const COR_DA_ZONA = { Z1: "--ruim", Z2: "--atencao", Z3: "--destaque" };
  const corDaZona = (nome) => token(COR_DA_ZONA[nome] || "--suave");

  //: Como o traço de cada origem é desenhado. O caso perigoso não é ficar sem
  //: zona: é uma zona INVENTADA parecer uma zona lida do relé.
  const TRACO_DA_ORIGEM = {
    lido: [], sugerido: [7, 5], digitado: [2, 3],
  };

  const LACOS_DO_PLANO = [
    ["AN", "A-terra"], ["BN", "B-terra"], ["CN", "C-terra"],
    ["AB", "A-B"], ["BC", "B-C"], ["CA", "C-A"],
  ];

  /** O botão que troca o laço do plano.
   *
   * No cabeçalho e não na engrenagem, pela regra da casa: **se muda o número,
   * é do cabeçalho; se muda só como o número aparece, é da engrenagem**. O
   * laço muda a conta inteira — `Z = Vx/(Ix + k0·3I0)` vira
   * `Z = (Vx−Vy)/(Ix−Iy)` —, então muda o número.
   */
  function botaoDoLaco(painel) {
    const ancoraId = `menu-laco-${painel.id}`;
    const b = criar("button", "medida");
    b.type = "button";
    b.setAttribute("aria-haspopup", "true");
    b.append(criar("span", null, `laço ${painel.laco || "AN"}`),
             criar("span", "seta-do-menu", "▾"));
    b.title = "Qual dos seis laços está no plano. Numa falta só o laço em "
            + "falta entra na zona — é comparando dois que se confirma o tipo.";
    const ancora = criar("span", "ancora-de-menu");
    ancora.id = ancoraId;
    b.addEventListener("click", () => {
      menuSuspenso(ancoraId, "laço:", (caixa) => {
        for (const [chave, rotulo] of LACOS_DO_PLANO) {
          const item = criar("button", "opcao"
            + (chave === (painel.laco || "AN") ? " escolhida" : ""),
            `${chave}  ·  ${rotulo}`);
          item.type = "button";
          item.title = chave.endsWith("N")
            ? "Laço de terra: Z = V / (I + k0·3I0). Sem o k0 a impedância "
              + "sai MAIOR do que é e a falta parece mais longe."
            : "Laço de fase: Z = (Vx − Vy) / (Ix − Iy). Não usa k0.";
          item.addEventListener("click", () => {
            menuAberto?.();
            const meu = painelPorId(painel.id);
            if (!meu || meu.laco === chave) return;
            guardarParaDesfazer();
            meu.laco = chave;
            recarregar();
          });
          caixa.append(item);
        }
      });
    });
    return [b, ancora];
  }

  /** As fichas do rodapé: a régua, o veredito e o que estiver faltando.
   *
   * DUAS fichas no caso normal, e não seis. A primeira versão desta tela
   * punha uma ficha por zona, mais os parâmetros, mais o k0, mais o par, mais o
   * aviso inteiro escrito por extenso — e o rodapé ficou mais comprido que o
   * gráfico. Ninguém lê seis linhas de texto para olhar um desenho.
   *
   * O corte não apaga nada, dobra: o alcance, o tempo e a origem de cada
   * zona continuam escritos, no hover da ficha do veredito e no próprio
   * desenho (tracejado = não saiu do relé, com o nome dizendo «sugerida»).
   * Na linha de frente fica só o que muda a leitura de relance — a régua
   * deste laço e em que zona a falta caiu.
   */
  function fichasDaImpedancia(painel) {
    const barra = criar("div", "rodape-do-painel fichas");
    const zonas = painel.zonas || [];
    const deTerra = (painel.laco || "AN").endsWith("N");
    const comoOrigem = (o) => o === "lido" ? "do relé"
                            : o === "sugerido" ? "sugerida"
                            : o === "digitado" ? "digitada" : o;

    // 1. A RÉGUA deste laço: os parâmetros da linha e, num laço de terra, o k0.
    // Os dois na mesma ficha porque são a mesma coisa — o que transforma o
    // Z medido em distância. Sem parâmetros, a ficha não existe e quem fala é
    // o aviso; sem k0 num laço de terra, a ficha fica vermelha, porque daí
    // a medida está errada e não apenas incompleta.
    const z = painel.parametros;
    if (z) {
      const k = painel.k0;
      const falta = deTerra && !k;
      let texto = `${formatar(z.modulo, 2)} Ω ∠${formatar(z.angulo, 0)}°`;
      if (deTerra) {
        texto += k ? ` · k0 ${formatar(Math.hypot(k.re, k.im), 3)}`
                   : " · sem k0";
      }
      barra.append(ficha("linha", texto, {
        tom: falta ? "ruim" : "",
        dica: `Parâmetros da linha, ${comoOrigem(z.origem)}`
            + `${z.variavel ? ` (${z.variavel}/${z.variavel_angulo})` : ""}`
            + ". É a régua dos «% da LT»."
            + (!deTerra ? ""
               : k ? " k0 = (Z0 − Z1)/(3·Z1), de Z0MAG/Z0ANG: é ele que faz "
                     + "o laço de terra medir a distância certa."
                   : " SEM k0: o arquivo não traz Z0MAG/Z0ANG, e a impedância "
                     + "de um laço de terra sem compensação sai MAIOR do que "
                     + "é — num sistema com Z0/Z1 ≈ 3 o erro passa de 60 % e "
                     + "a falta parece bem mais longe do que está."),
      }));
    }

    // 2. O VEREDITO: uma ficha só, a zona MAIS INTERNA em que a trajetória
    // entrou. Três fichas de zona respondiam três vezes a mesma pergunta, e
    // a resposta que interessa é a menor delas: entrar na Z1 é trip
    // instantâneo, e isso é o que se vai olhar.
    if (zonas.length) {
      const detalhe = zonas.map((x) => {
        const pct = x.pct === null || x.pct === undefined
          ? "" : ` (${formatar(x.pct, 0)} % da LT)`;
        return `${x.nome} ${formatar(x.alcance, 2)} Ω${pct}, ${x.tempo}, `
             + `${comoOrigem(x.origem)}${x.variavel ? ` de ${x.variavel}` : ""}`;
      }).join(" · ");

      if (painel.comparavel === false) {
        barra.append(ficha("zonas", "sem veredito",
          { tom: "atencao", dica: `Não dá para dizer em que zona a falta caiu `
                                + `— ver o aviso ao lado. ${detalhe}.` }));
      } else {
        const dentro = zonas
          .filter((x) => typeof (painel.entradas || {})[x.nome] === "number")
          .sort((a, b) => a.alcance - b.alcance)[0];
        barra.append(dentro
          ? ficha("entrou", `${dentro.nome} · amostra `
                            + `${painel.entradas[dentro.nome]}`,
              { tom: dentro.origem === "lido" ? "ruim" : "atencao",
                dica: (dentro.origem === "lido"
                        ? "A trajetória entrou nesta zona do relé."
                        : "Entrou numa zona que NÃO saiu do relé: isto situa "
                          + "a falta na linha, não diz se o relé devia ter "
                          + "atuado.")
                    + ` Todas as zonas: ${detalhe}.` })
          : ficha("zonas", "a falta não entrou em nenhuma",
              { dica: `Nenhuma das zonas foi alcançada pela trajetória. `
                    + `${detalhe}.` }));
      }
    }

    // 3. O que estiver faltando. Curto na ficha, inteiro no hover.
    for (const aviso of (painel.avisos || [])) {
      const texto = typeof aviso === "string" ? aviso : aviso.curto;
      const longo = typeof aviso === "string" ? "" : aviso.longo;
      barra.append(ficha("", texto, {
        tom: (typeof aviso === "string" ? "atencao" : aviso.tom) || "atencao",
        dica: longo,
      }));
    }
    return barra;
  }

  /** A tabelinha do cursor: o que o laço media naquele instante. */
  function tabelaDaImpedancia(painel) {
    const meu = painelPorId(painel.id) || {};
    const qual = meu.cursor === 2 ? 2 : 1;
    const tabela = criar("table", "mini impedancia");
    const thead = criar("thead");
    const cabeca = criar("tr");
    cabeca.append(criar("th", "unidade", "no cursor"), criar("th", null, `${qual}`));
    thead.append(cabeca);
    const tbody = criar("tbody");

    const p = pontoDoCursor(painel, qual);
    const zl = painel.parametros ? painel.parametros.modulo : 0;
    const linhas = p
      ? [["R", `${formatar(p.r, 2)} Ω`],
         ["X", `${formatar(p.x, 2)} Ω`],
         ["|Z|", `${formatar(Math.hypot(p.r, p.x), 2)} Ω`],
         ["∠Z", `${formatar(Math.atan2(p.x, p.r) * 180 / Math.PI, 1)}°`],
         ["% da LT", zl > 0 ? `${formatar(100 * Math.hypot(p.r, p.x) / zl, 1)} %`
                            : "—"]]
      : [["", "cursor fora da janela"]];

    for (const [rotulo, valor] of linhas) {
      const tr = criar("tr");
      const th = criar("th", "canal");
      th.append(criar("span", "rotulo", rotulo));
      tr.append(th, criar("td", null, valor));
      tbody.append(tr);
    }
    tabela.append(thead, tbody);
    return tabela;
  }

  /** O ponto da trajetória mais perto do instante de um cursor, ou `null`.
   *
   * Pelo TEMPO e não pelo índice: a trajetória vem decimada (600 pontos no
   * máximo), e num registro de taxa variável o índice não é régua.
   */
  function pontoDoCursor(painel, qual) {
    const t = cursores[qual - 1];
    if (t === null || t === undefined) return null;
    let melhor = null;
    let menor = Infinity;
    for (const p of (painel.pontos || [])) {
      if (p.r === null || p.x === null) continue;
      const d = Math.abs(p.t - t);
      if (d < menor) { menor = d; melhor = p; }
    }
    return melhor;
  }


  /* ======================================================================
   * OS AJUSTES DO PLANO — a terceira origem, que é o teclado
   * ======================================================================
   *
   * O painel já lia do arquivo e sugeria quando o arquivo não traz. Faltava
   * o caso mais comum na prática: você tem o ajuste na mão, ou quer ver o
   * que teria acontecido com outro alcance, e digita.
   *
   * **O valor digitado é SECUNDÁRIO**, como todo ajuste de distância — é o
   * que está escrito no relé e o que se confere no QuickSet. O servidor
   * converte para primário junto com os valores lidos, pelo mesmo caminho;
   * é isso que impede digitado e lido de divergirem de base.
   *
   * A CAIXA NÃO É FILHA DO PAINEL, e isso não é detalhe: cada tecla digitada
   * pede a janela ao servidor de novo, e a resposta refaz os painéis
   * inteiros. Um menu pendurado no cabeçalho sumiria debaixo do dedo a cada
   * letra. Pendurada no `body`, ela sobrevive à repintura e o desenho se
   * mexe atrás dela enquanto se digita — que é justamente o que se quer ver.
   */
  //: A caixa de ajustes aberta, ou `null`. Uma só na tela, como os menus.
  let ajustesAbertos = null;

  function fecharAjustes() {
    if (!ajustesAbertos) return;
    document.removeEventListener("pointerdown", ajustesAbertos.aoApontar, true);
    window.removeEventListener("resize", ajustesAbertos.posicionar);
    window.removeEventListener("scroll", ajustesAbertos.posicionar, true);
    ajustesAbertos.caixa.remove();
    ajustesAbertos = null;
  }

  const ORIGEM_POR_EXTENSO = {
    lido: "do relé", sugerido: "sugerido", digitado: "manual",
    modelagem: "modelagem", calculado: "calculado",
  };

  /** De onde vieram as zonas que se está vendo. Foi o rótulo do botão; hoje
   *  é o começo do hover dele, e a cor do botão é o aviso. */
  function rotuloDosAjustes(painel) {
    const origens = (painel.zonas || []).map((z) => z.origem);
    if (painel.parametros) origens.push(painel.parametros.origem);
    if (!origens.length) return "ajustes: nenhum";
    if (origens.every((x) => x === "digitado")) return "ajustes: manuais";
    if (origens.every((x) => x === "lido")) return "ajustes: do arquivo";
    if (origens.includes("digitado")) return "ajustes: do arquivo + manuais";
    return "ajustes: do arquivo + sugeridos";
  }
  const ajusteNaoLido = (painel) =>
    (painel.zonas || []).some((z) => z.origem !== "lido")
    || (painel.parametros && painel.parametros.origem !== "lido");

  function botaoDeAjustes(painel) {
    const ancoraId = `ancora-ajustes-${painel.id}`;
    // Só «ajustes», como nos outros painéis de proteção: o resumo («ajustes:
    // nenhum») dizia pouco e roubava largura; a origem de cada número está
    // dentro da caixa. O aviso de ajuste não lido continua na cor do botão.
    const b = criar("button", "medida", "ajustes");
    b.type = "button";
    b.setAttribute("aria-haspopup", "true");
    b.classList.toggle("aviso-no-botao", !!ajusteNaoLido(painel));
    b.title = `${rotuloDosAjustes(painel)}. `
            + "De onde vêm os parâmetros da linha e os alcances das zonas "
            + "deste plano — e onde se digita por cima deles; e a vista do plano.";
    const ancora = criar("span", "ancora-de-menu");
    ancora.id = ancoraId;
    b.addEventListener("click", () => abrirAjustesDoPlano(painel, ancoraId));
    return [b, ancora];
  }

  /** Um campo de número da caixa de ajustes. */
  function campoDoAjuste(valor, aoDigitar, dica) {
    const i = document.createElement("input");
    i.type = "text";
    i.value = valor;
    i.spellcheck = false;
    i.title = dica || "";
    i.addEventListener("input", () => aoDigitar(i.value, i));
    return i;
  }
  const numeroDigitado = (texto) => {
    const v = parseFloat(String(texto).replace(/[^\d,.-]/g, "").replace(",", "."));
    return Number.isFinite(v) ? v : null;
  };

  function abrirAjustesDoPlano(painel, ancoraId) {
    const mesmo = ajustesAbertos && ajustesAbertos.painel === painel.id;
    fecharAjustes();
    if (mesmo) return;                       // o botão que abre também fecha

    const meu = painelPorId(painel.id);
    if (!meu) return;

    /* O RASCUNHO. Os campos mexem numa cópia; «aplicar» a leva ao painel e
     * pede a janela de novo, «descartar» joga fora. Era aplicar a cada tecla,
     * e um número pela metade («1,» antes do «5») já redesenhava a zona — e
     * nada dizia o que estava valendo. Maquete 7 de «ajustes-impedancia-10»,
     * escolha dele em 22/10/2026. */
    const rascunho = JSON.parse(JSON.stringify(meu.manuais || {}));
    let formaRascunho = meu.caracteristica || "";

    // A BASE dos campos é a que o servidor mandou: a do botão geral quando há
    // relação de TC/TP, secundário quando não há. O que se digita volta com
    // ela, e o servidor converte — o ajuste do relé é secundário.
    const base = painel.ajuste || { zl: null, zonas: [] };
    const baseDosCampos = base.base === "primario" ? "primario" : "secundario";
    const unidade = baseDosCampos === "primario" ? "Ω prim" : "Ω sec";

    const caixa = criar("div", "menu-suspenso ajustes-do-plano");
    caixa.append(criar("p", "cabeca-menu", "ajustes do relé"));

    // A BASE acompanha o botão secundário | primário do cabeçalho; a faixa diz
    // só qual é, curta (pedido dele, 24/10/2026). A RTP/RTC vem logo abaixo,
    // EDITÁVEL: quando a do arquivo está errada, zona e trajetória caem em
    // réguas diferentes e a análise inteira erra sem nada denunciando.
    const faixa = criar("p", "faixa-da-base");
    faixa.append(criar("span", null, "valores em "),
                 criar("b", null, baseDosCampos === "primario" ? "ohms PRIMÁRIOS" : "ohms SECUNDÁRIOS"));
    faixa.title = "A base acompanha o botão secundário | primário do cabeçalho. "
                + "O relé guarda o ajuste em secundário; o que se digita em "
                + "primário é dividido pela RTP/RTC antes de valer.";
    caixa.append(faixa);

    // --- o que está pendente --------------------------------------------
    const pendente = criar("span", "pendente-do-ajuste", "");
    const aplicar = criar("button", "medida primario-do-ajuste", "aplicar");
    const descartar = criar("button", "medida", "descartar");
    aplicar.type = descartar.type = "button";
    aplicar.disabled = descartar.disabled = true;
    const mudou = () => {
      pendente.textContent = "alterações não aplicadas";
      aplicar.disabled = descartar.disabled = false;
    };

    const linhaDaRelacao = criar("div", "linha-de-parametros relacao-do-ajuste");
    const casasDaRelacao = v => Number.isInteger(v) ? 0 : 3;
    linhaDaRelacao.append(
      criar("span", "titulo-do-bloco", "RTP/RTC"),
      campoDoAjuste(base.relacao ? formatar(base.relacao, casasDaRelacao(base.relacao)) : "",
        (v) => {
          const n = numeroDigitado(v);
          // Campo vazio é «volte à do arquivo».
          if (String(v).trim() === "") delete rascunho.relacao;
          else if (n !== null && n > 0) rascunho.relacao = n;
          else return;
          mudou();
        },
        "A relação que leva ohm secundário a primário. Corrija se a do arquivo "
        + "estiver errada; apague para voltar à do arquivo."),
      criar("span", "unidade-do-campo", base.relacao_digitada
        ? (base.relacao_lida ? `digitada · o arquivo diz ${formatar(base.relacao_lida, casasDaRelacao(base.relacao_lida))}`
                             : "digitada · o arquivo não declara")
        : (base.relacao_lida ? "do arquivo" : "o arquivo não declara: digite para comparar zona e trajetória")));
    caixa.append(linhaDaRelacao);

    const origemChip = (origem, variavel) => {
      const texto = origem === "digitado" ? "manual"
        : origem === "lido" ? (variavel || "do relé")
        : ORIGEM_POR_EXTENSO[origem] || origem || "—";
      return criar("span", "etiqueta-origem " + (origem || "vazio"), texto);
    };
    /** A fonte de uma zona: a do ALCANCE e a do TEMPO, que podem ser
     *  diferentes (o alcance digitado e o tempo lido do relé, por exemplo). */
    const fonteDaZona = (z) => {
      const nome = (origem, variavel) => origem === "digitado" ? "manual"
        : origem === "lido" ? (variavel || "do relé")
        : ORIGEM_POR_EXTENSO[origem] || origem || "—";
      const alcance = nome(z.origem || "vazio", z.variavel);
      const tempo = nome(z.tempo_origem || "vazio", z.tempo_variavel);
      const chip = criar("span", "etiqueta-origem " + (z.origem || "vazio"),
                         alcance === tempo ? alcance : `${alcance} · ${tempo}`);
      chip.title = `alcance: ${alcance} · tempo: ${tempo}`;
      return chip;
    };

    // --- a linha: Z1, sequência positiva -------------------------------
    const zlBase = base.zl || { modulo: null, angulo: 80, origem: "sugerido" };
    const blocoLinha = criar("div", "bloco-da-linha");
    blocoLinha.append(criar("div", "titulo-do-bloco",
                            "Z1 — sequência positiva (impedância da linha)"));
    const linhaZ1 = criar("div", "linha-de-parametros");
    const guardarLinha = (campo, valor) => {
      if (!rascunho.zl) rascunho.zl = {};
      rascunho.zl[campo] = valor;
      rascunho.zl.base = baseDosCampos;
      mudou();
    };
    linhaZ1.append(
      campoDoAjuste(zlBase.modulo === null ? "" : formatar(zlBase.modulo, 3),
        (v) => { const n = numeroDigitado(v); if (n !== null) guardarLinha("modulo", n); },
        `módulo de Z1 da linha, em ${unidade}`),
      criar("span", "unidade-do-campo", unidade),
      criar("span", "unidade-do-campo", "∠"),
      campoDoAjuste(formatar(zlBase.angulo, 2),
        (v) => { const n = numeroDigitado(v); if (n !== null) guardarLinha("angulo", n); },
        "ângulo de Z1 — é para onde as zonas apontam (MTA)"),
      criar("span", "unidade-do-campo", "°"),
      origemChip(zlBase.origem, zlBase.variavel));
    blocoLinha.append(linhaZ1);
    // Z0 e k0: só leitura aqui — o k0 é o que corrige o laço de terra.
    const k0 = painel.k0;
    blocoLinha.append(criar("p", "nota-da-linha", k0
      ? `k0 = ${formatar(k0.modulo, 3)} ∠ ${formatar(k0.angulo, 1)}° · ${k0.de} `
        + `(${ORIGEM_POR_EXTENSO[k0.origem] || k0.origem}) — sequência zero, `
        + "corrige o laço de terra"
      : "k0: o arquivo não traz Z0 — o laço de terra fica sem compensação"));
    caixa.append(blocoLinha);

    // --- a característica ------------------------------------------------
    const info = painel.caracteristica || {};
    const formaEmVista = () => formaRascunho || info.escolhida || "mho";
    const linhaForma = criar("div", "linha-da-forma");
    linhaForma.append(criar("span", "titulo-do-bloco", "característica"));
    const par = criar("span", "par-de-medidas");
    const notaDaForma = criar("p", "nota-da-linha");
    const terra = String(painel.laco || "").endsWith("N");
    const escreverNota = () => {
      const f = formaEmVista();
      const nome = { mho: "mho", quad: "quadrilateral", ambas: "ambas" }[f];
      const vars = info.variaveis ? ` (${info.variaveis})` : "";
      let texto;
      if (!info.lida) {
        texto = "o arquivo não diz qual forma o relé usa; mostrando " + nome;
      } else if (info.mho && info.quad) {
        texto = `o relé usa as duas${vars}; mostrando ${nome}`;
      } else if (f !== "mho" && !info.quad) {
        texto = `o relé não tem quadrilateral ${terra ? "de terra" : "de fase"}`
              + `${vars}; digite X e R para simular`;
      } else {
        texto = `o relé usa ${info.quad && !info.mho ? "quadrilateral" : "mho"}${vars}`;
      }
      notaDaForma.textContent = texto;
      notaDaForma.classList.toggle("atencao", f !== "mho" && info.lida && !info.quad);
    };
    const botoesDaForma = [];
    for (const [chave, rotulo] of [["mho", "mho"], ["quad", "quadrilateral"],
                                   ["ambas", "ambas"]]) {
      const b = criar("button", "medida", rotulo);
      b.type = "button";
      b.title = chave === "ambas"
        ? "As duas sobrepostas: a zona atua se o ponto entrar em qualquer uma — "
          + "é como o relé decide quando usa as duas."
        : `Desenhar e julgar a entrada pela ${rotulo}.`;
      b.addEventListener("click", () => {
        formaRascunho = chave;
        for (const x of botoesDaForma) x.classList.toggle("escolhido", x === b);
        escreverNota();
        pintarColunas();
        mudou();
      });
      botoesDaForma.push(b);
      par.append(b);
    }
    for (const b of botoesDaForma) {
      b.classList.toggle("escolhido",
        ({ mho: "mho", quadrilateral: "quad", ambas: "ambas" })[b.textContent] === formaEmVista());
    }
    linhaForma.append(par);
    caixa.append(linhaForma, notaDaForma);
    escreverNota();

    // --- as zonas ---------------------------------------------------------
    const tabela = criar("div", "tabela-de-zonas zonas-v7");
    const cabeca = criar("div", "linha-de-zona cabeca");
    const colunas = [["", ""], ["dir", "direção"], ["mho", `mho (${unidade})`],
                     ["x", `X quad (${unidade})`], ["r", `R quad (${unidade})`],
                     ["t", "tempo"], ["", "fonte"]];
    for (const [chave, rotulo] of colunas) {
      const c = criar("span", chave ? `col-${chave}` : null, rotulo);
      cabeca.append(c);
    }
    tabela.append(cabeca);

    const meuItem = (nome) => {
      if (!rascunho.zonas) rascunho.zonas = {};
      if (!rascunho.zonas[nome]) rascunho.zonas[nome] = {};
      rascunho.zonas[nome].base = baseDosCampos;
      return rascunho.zonas[nome];
    };
    for (const nome of ["Z1", "Z2", "Z3"]) {
      const z = (base.zonas || []).find((x) => x.nome === nome) || {};
      const l = criar("div", "linha-de-zona");
      const rotulo = criar("b", null, nome);
      rotulo.style.color = token(COR_DA_ZONA[nome]);
      const direcao = document.createElement("select");
      for (const [v, r] of [["F", "à frente"], ["R", "reversa"]]) {
        const op = document.createElement("option");
        op.value = v;
        op.textContent = r;
        op.selected = (z.direcao || "F") === v;
        direcao.append(op);
      }
      direcao.title = z.direcao_variavel
        ? `lida do relé: ${z.direcao_variavel} := ${z.direcao}`
        : "Z1 e Z2 olham sempre para a frente na SEL; a Z3 tem DIR3.";
      direcao.addEventListener("change", () => {
        meuItem(nome).direcao = direcao.value;
        mudou();
      });
      const campoNum = (campo, valor, dica) => {
        const i = campoDoAjuste(valor === null || valor === undefined ? "" : formatar(valor, 3),
          (v) => {
            const n = numeroDigitado(v);
            if (n !== null && n > 0) { meuItem(nome)[campo] = n; mudou(); }
          }, dica);
        i.classList.add(`col-${campo === "alcance" ? "mho" : campo}`);
        return i;
      };
      const alcance = campoNum("alcance", z.alcance,
        `alcance mho da ${nome}${z.variavel ? ` — ${z.variavel}` : ""}`);
      const qx = campoNum("x", z.x, `alcance reativo da quadrilateral${z.x_variavel ? ` — ${z.x_variavel}` : ""}`);
      const qr = campoNum("r", z.r, `alcance resistivo da quadrilateral${z.r_variavel ? ` — ${z.r_variavel}` : ""}`);
      const tempo = campoDoAjuste(z.tempo || "", (v) => {
        meuItem(nome).tempo = v;
        mudou();
      }, `temporização da ${nome}${z.tempo_variavel ? ` — ${z.tempo_variavel}` : ""}`);
      tempo.classList.add("col-t");
      l.append(rotulo, direcao, alcance, qx, qr, tempo, fonteDaZona(z));
      tabela.append(l);
    }
    // A coluna que a forma em vista não usa fica apagada, mas editável: dá
    // para preparar a quadrilateral enquanto se olha a mho.
    function pintarColunas() {
      const f = formaEmVista();
      tabela.classList.toggle("sem-mho", f === "quad");
      tabela.classList.toggle("sem-quad", f === "mho");
    }
    pintarColunas();
    caixa.append(tabela);

    // --- o rodapé ---------------------------------------------------------
    const voltar = criar("button", "medida", "voltar ao do arquivo");
    voltar.type = "button";
    voltar.disabled = !Object.keys(meu.manuais || {}).length && !meu.caracteristica;
    voltar.title = "Apaga tudo o que foi digitado e volta ao que o arquivo "
                 + "trouxe (ou ao sugerido, onde ele não traz nada).";
    const reabrir = () => {
      const novo = (dados.paineis || []).find((x) => x.id === painel.id);
      if (novo) abrirAjustesDoPlano(novo, ancoraId);
    };
    const levar = (manuais, forma) => {
      guardarParaDesfazer();
      meu.manuais = manuais;
      meu.caracteristica = forma;
      fecharAjustes();
      recarregar().then(reabrir);
    };
    voltar.addEventListener("click", () => levar({}, ""));
    descartar.addEventListener("click", () => {
      fecharAjustes();
      abrirAjustesDoPlano(painel, ancoraId);
    });
    aplicar.addEventListener("click", () => levar(rascunho, formaRascunho));
    caixa.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !aplicar.disabled) { e.preventDefault(); aplicar.click(); }
    });
    const pe = criar("div", "rodape-do-ajuste");
    pe.append(pendente, voltar, descartar, aplicar);
    caixa.append(pe);
    if (formaEmVista() !== "mho") {
      caixa.append(criar("p", "nota-do-menu",
        "A quadrilateral é desenhada SIMPLIFICADA: reta de reatância em X e os "
        + "limites resistivos em ±R inclinados no ângulo da linha. O relé "
        + "inclina a reta de cima e põe o fundo no direcional."));
    }

    // --- pendurar no corpo, e não no painel ------------------------------
    document.body.append(caixa);
    const posicionar = () => {
      const ancora = document.getElementById(ancoraId);
      const gatilho = ancora && ancora.previousElementSibling;
      if (!gatilho) { fecharAjustes(); return; }
      const r = gatilho.getBoundingClientRect();
      const larg = caixa.offsetWidth;
      const esq = Math.max(8, Math.min(window.innerWidth - larg - 8, r.left));
      caixa.style.left = `${esq}px`;
      caixa.style.top = `${r.bottom + 6}px`;
    };
    const aoApontar = (e) => {
      if (caixa.contains(e.target)) return;
      const ancora = document.getElementById(ancoraId);
      const gatilho = ancora && ancora.previousElementSibling;
      if (gatilho && gatilho.contains(e.target)) return;
      fecharAjustes();
    };
    document.addEventListener("pointerdown", aoApontar, true);
    window.addEventListener("resize", posicionar);
    window.addEventListener("scroll", posicionar, true);
    ajustesAbertos = { painel: painel.id, caixa, posicionar, aoApontar };
    posicionar();
  }

  function blocoImpedancia(painel) {
    const el = criar("section", "grafico impedancia");
    const meu = painelPorId(painel.id) || {};

    const qual = meu.cursor === 2 ? 2 : 1;
    const botaoCursor = criar("button", "medida", `cursor ${qual}`);
    botaoCursor.title = `A tabela e o anel cheio são do instante do cursor `
                      + `${qual}. Clique para passar para o outro.`;
    botaoCursor.addEventListener("click", () => alternarCursorDoPainel(painel.id));

    const botaoVinculo = criar("button", "medida", painel.par || "escolher vínculo");
    botaoVinculo.type = "button";
    botaoVinculo.title = "De qual par corrente×tensão este laço sai. O par se "
                       + "faz em «editar grupos», dentro do «+ sinal».";
    botaoVinculo.addEventListener("click", () => abrirEscolhaDoVinculo(painel, {
      titulo: "De onde sai este plano",
      sub: "um par corrente×tensão, com as tensões de fase",
      vazio: "Nenhum vínculo neste registro. Com uma única trinca de corrente "
           + "e uma de tensão o plano já sai sem vínculo nenhum; com mais de "
           + "uma, faça o par em «+ sinal» → «editar grupos» → «vincular».",
    }));

    el.append(cabecalhoDoPainel(painel, [
      botaoCursor, ...botaoDoLaco(painel), botaoVinculo,
      ...botaoDeAjustes(painel),
      // A engrenagem é a VISTA (setas, régua, zonas, grade, enquadramento);
      // os «ajustes» são os do relé. Maquete 7, escolha dele em 22/10/2026.
      ...engrenagemDoPainel(painel, () => ajustesDaImpedancia(painel)),
    ]));

    const corpo = criar("div", "grafico-corpo impedancia");
    const caixa = criar("div", "tela");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    corpo.append(caixa, tabelaDaImpedancia(painel));
    el.append(corpo);
    comMolduras(el, corpo);
    el.append(fichasDaImpedancia(painel));

    el._painel = painel;
    el._canvas = canvas;
    ligarPlanoDeImpedancia(el);
    return el;
  }

  //: O que a engrenagem deste painel ajusta. Tudo aqui muda só COMO o número
  //: aparece — a unidade da régua, o preenchimento das zonas, a grade. O que
  //: muda o número (laço, vínculo) está no cabeçalho.
  function ajustesDaImpedancia(painel) {
    const meu = painelPorId(painel.id) || {};
    const feito = [];

    /* As SETAS primeiro: é a novidade, e é a vista que mais muda a leitura
     * de uma trajetória que vai e volta. Maquete 7 de «ajustes-impedancia-10». */
    const chaveDeVista = (campo, chave, rotulo, dica, padrao, amostra) => {
      const b = criar("button", "medida"
        + (String(meu[campo] ?? padrao) === String(chave) ? " escolhido" : ""), rotulo);
      b.type = "button";
      b.title = dica;
      if (amostra) b.append(amostraDeSeta(chave));
      b.addEventListener("click", () => {
        const atual = painelPorId(painel.id);
        if (!atual) return;
        atual[campo] = chave;
        if (campo === "enquadrarZ") delete atual.caixaZ;
        menuAberto?.();
        desenharTudo();
      });
      return b;
    };
    feito.push("trajetória — setas");
    feito.push(chaveDeVista("setasZ", "nenhuma", "sem setas",
      "Só o traço.", "nenhuma"));
    feito.push(chaveDeVista("setasZ", "cadaN", "com setas",
      "Pontas de seta mostrando o sentido em que a bolinha andou.", "nenhuma"));
    if ((meu.setasZ || "nenhuma") !== "nenhuma") {
      feito.push("estilo das setas");
      for (const [chave, rotulo, dica] of [
        ["pontas", "pontas", "Pontas iguais a cada N ms."],
        ["idade", "idade", "As pontas esmaecem com a idade; a mais forte é o agora."],
        ["saltos", "saltos", "Seta só onde a bolinha anda rápido — o mergulho, "
         + "onde o sentido importa."]]) {
        feito.push(chaveDeVista("estiloSetaZ", chave, rotulo, dica, "pontas", true));
      }
      if ((meu.estiloSetaZ || "pontas") !== "saltos") {
        feito.push("uma seta a cada");
        for (const ms of [5, 10, 20]) {
          feito.push(chaveDeVista("setaNZ", ms, `${ms} ms`,
            `Uma ponta a cada ${ms} ms de trajetória.`, 10));
        }
      }
    }
    feito.push("enquadrar");
    feito.push(chaveDeVista("enquadrarZ", "zonas", "nas zonas",
      "O quadro cabe as zonas e a linha — é onde se lê a falta.", "zonas"));
    feito.push(chaveDeVista("enquadrarZ", "tudo", "trajetória inteira",
      "O quadro cabe a trajetória (do 2 ao 98 %: a fuga para o infinito "
      + "depois da abertura não manda).", "zonas"));

    feito.push("régua dos eixos");
    for (const [chave, rotulo, dica] of [
      ["ohm", "ohms", "A unidade dos canais: com o cabeçalho em secundário, "
       + "ohms secundários — que é como o relé enxerga e como os ajustes "
       + "dele estão escritos."],
      ["pct", "% da linha", "Os mesmos números divididos pelos parâmetros da "
       + "linha. Responde «a que fração da LT», que é a pergunta de quem "
       + "está localizando a falta."]]) {
      const b = criar("button", "medida"
        + ((meu.unidadeZ || "ohm") === chave ? " escolhido" : ""), rotulo);
      b.type = "button";
      b.title = dica;
      b.addEventListener("click", () => {
        const atual = painelPorId(painel.id);
        if (!atual) return;
        atual.unidadeZ = chave;
        menuAberto?.();
        desenharTudo();
      });
      feito.push(b);
    }

    feito.push("zonas");
    for (const [chave, rotulo, dica] of [
      ["contorno", "só o contorno", "O círculo de cada zona, sem recheio."],
      ["cheia", "preenchidas", "Com recheio esmaecido — fica mais fácil ver "
       + "em qual delas o ponto caiu, e mais difícil ver a trajetória por "
       + "baixo. A zona sugerida ou digitada ganha recheio mais claro que a "
       + "lida do relé, e continua com o traço dela."],
      ["nenhuma", "esconder", "Só a trajetória. Serve para olhar a forma do "
       + "mergulho sem nada por cima."]]) {
      const b = criar("button", "medida"
        + ((meu.zonasZ || "contorno") === chave ? " escolhido" : ""), rotulo);
      b.type = "button";
      b.title = dica;
      b.addEventListener("click", () => {
        const atual = painelPorId(painel.id);
        if (!atual) return;
        atual.zonasZ = chave;
        menuAberto?.();
        desenharTudo();
      });
      feito.push(b);
    }

    feito.push("fundo");
    const grade = criar("button", "medida" + (meu.gradeZ === false ? "" : " escolhido"),
                        "grade");
    grade.type = "button";
    grade.title = "A grade cartesiana de fundo. Sem ela o quadro fica limpo; "
                + "com ela dá para ler um valor sem ir à tabela.";
    grade.addEventListener("click", () => {
      const atual = painelPorId(painel.id);
      if (!atual) return;
      atual.gradeZ = atual.gradeZ === false;
      menuAberto?.();
      desenharTudo();
    });
    feito.push(grade);

    const mta = criar("button", "medida" + (meu.mtaZ ? " escolhido" : ""), "MTA");
    mta.type = "button";
    mta.title = "A reta do ângulo de máximo torque, que é o ângulo dos parâmetros "
              + "da linha. Uma falta franca anda em cima dela; o que se "
              + "afasta para a direita é resistência de arco.";
    mta.addEventListener("click", () => {
      const atual = painelPorId(painel.id);
      if (!atual) return;
      atual.mtaZ = !atual.mtaZ;
      menuAberto?.();
      desenharTudo();
    });
    feito.push(mta);
    return feito;
  }

  /** Um desenhinho do estilo de seta, dentro do botão que o escolhe. */
  function amostraDeSeta(estilo) {
    const c = document.createElement("canvas");
    const dpr = window.devicePixelRatio || 1;
    c.width = 40 * dpr; c.height = 12 * dpr;
    c.style.cssText = "width:40px;height:12px;margin-left:5px;vertical-align:middle";
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const cor = token("--traco-1");
    ctx.strokeStyle = cor;
    ctx.fillStyle = cor;
    ctx.lineWidth = 1.3;
    const y = (x) => 6 + Math.sin(x / 6) * 3;
    ctx.beginPath();
    for (let x = 2; x <= 38; x += 1) (x === 2 ? ctx.moveTo(x, y(x)) : ctx.lineTo(x, y(x)));
    ctx.stroke();
    if (estilo === "saltos") {
      pontaDeSeta(ctx, 26, y(26), 0.4, 5);
    } else {
      for (const x of [11, 22, 33]) {
        ctx.globalAlpha = estilo === "idade" ? 0.3 + x / 50 : 1;
        pontaDeSeta(ctx, x, y(x), Math.atan(Math.cos(x / 6) * 0.5), 4);
      }
      ctx.globalAlpha = 1;
    }
    return c;
  }

  /** Um passo de grade "redondo" para uma extensão qualquer. */
  function passoRedondo(extensao, alvo) {
    const bruto = extensao / Math.max(alvo, 1);
    const ordem = Math.pow(10, Math.floor(Math.log10(Math.max(bruto, 1e-9))));
    for (const m of [1, 2, 5, 10]) {
      if (bruto <= m * ordem) return m * ordem;
    }
    return 10 * ordem;
  }

  /** Uma ponta de seta em `(x, y)`, apontando para `angulo` (radianos). */
  function pontaDeSeta(ctx, x, y, angulo, tamanho) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angulo);
    ctx.beginPath();
    ctx.moveTo(tamanho, 0);
    ctx.lineTo(-tamanho * 0.7, tamanho * 0.6);
    ctx.lineTo(-tamanho * 0.35, 0);
    ctx.lineTo(-tamanho * 0.7, -tamanho * 0.6);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function pintarImpedancia(canvas, painel) {
    const larg = canvas.parentElement.clientWidth || 620;
    const alt = ALTURA_IMPEDANCIA;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${larg}px`;
    canvas.style.height = `${alt}px`;
    dimensionar(canvas, Math.round(larg * dpr), Math.round(alt * dpr));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, larg, alt);

    const m = MARGEM_IMPEDANCIA;
    const cheio = larg - m.esq - m.dir;
    const util = { l: cheio, a: alt - m.topo - m.baixo };
    // O QUADRO NÃO ACOMPANHA A LARGURA DO PAINEL, e isso não é economia.
    //
    // A escala tem de ser igual nos dois eixos, senão a circunferência da
    // mho vira elipse — e uma mho que parece elipse ensina a coisa errada.
    // Num painel de 1400 px com 300 de altura, «escala igual» significa
    // mostrar cinco vezes mais R do que X: as zonas encolhem para o meio da
    // tela e a trajetória vira um borrão de dois milímetros. Então o quadro
    // tem proporção máxima e fica CENTRADO, com folga dos dois lados.
    util.l = Math.min(cheio, util.a * 1.6);
    const sobraDoPainel = (cheio - util.l) / 2;
    if (util.l < 80 || util.a < 60) return;
    const esqDoQuadro = MARGEM_IMPEDANCIA.esq + sobraDoPainel;

    const meu = painelPorId(painel.id) || {};
    const zonas = (painel.zonas || []);
    const zl = painel.parametros ? painel.parametros.modulo : 0;
    const ang = (painel.parametros ? painel.parametros.angulo : 80) * Math.PI / 180;

    // A FORMA em vista: mho, quadrilateral ou ambas. Vem do servidor, que
    // é quem julga a entrada; a tela só desenha a mesma escolha.
    const forma = (painel.caracteristica && painel.caracteristica.escolhida) || "mho";
    const usaMho = (z) => (forma === "mho" || forma === "ambas") && z.mho && z.alcance > 0;
    const usaQuad = (z) => (forma === "quad" || forma === "ambas") && z.quad;

    // O QUE TEM DE CABER. As zonas e os parâmetros, sempre — eles são a
    // referência, e um plano em que a Z2 não cabe não responde a pergunta
    // que ele existe para responder. A trajetória entra só com o que está
    // perto: a carga mora a centenas de ohms e a fuga depois da abertura vai
    // ao infinito, e esticar o quadro até elas achataria a falta num borrão.
    //
    // Pelas FORMAS, e não só pelo alcance: a zona reversa mora no 3º
    // quadrante, e a quadrilateral é mais larga que a mho do mesmo alcance.
    // «trajetória inteira» (engrenagem) troca as zonas pela trajetória.
    const caixaDe = (pontos) => {
      const rs = pontos.map((q) => q[0]), xs = pontos.map((q) => q[1]);
      return [Math.min(...rs), Math.max(...rs), Math.min(...xs), Math.max(...xs)];
    };
    const extremos = [[0, 0]];
    if (meu.enquadrarZ === "tudo") {
      const vivos = (painel.pontos || []).filter((q) => q.r !== null && q.x !== null);
      // Do 2 ao 98 %: a fuga para o infinito depois da abertura não manda.
      const corte = (v) => {
        const o = v.slice().sort((a, b) => a - b);
        return [o[Math.floor(o.length * 0.02)], o[Math.ceil(o.length * 0.98) - 1]];
      };
      if (vivos.length) {
        const [r0, r1] = corte(vivos.map((q) => q.r));
        const [x0, x1] = corte(vivos.map((q) => q.x));
        extremos.push([r0, x0], [r1, x1]);
      }
    } else {
      for (const z of zonas) {
        if (usaMho(z)) {
          const [cr, cx] = z.mho.centro;
          extremos.push([cr - z.mho.raio, cx - z.mho.raio], [cr + z.mho.raio, cx + z.mho.raio]);
        }
        if (usaQuad(z)) extremos.push(...z.quad);
      }
      if (zl > 0) extremos.push([zl * Math.cos(ang), zl * Math.sin(ang)]);
    }
    let [rMin, rMax, xMin, xMax] = caixaDe(extremos);
    if (!(rMax - rMin > 0) || !(xMax - xMin > 0)) {
      const modulos = (painel.pontos || [])
        .filter((q) => q.r !== null && q.x !== null)
        .map((q) => Math.hypot(q.r, q.x)).sort((a, b) => a - b);
      const raio = (modulos.length ? modulos[Math.floor(modulos.length * 0.3)] : 1) || 1;
      [rMin, rMax, xMin, xMax] = [-raio * 0.7, raio * 1.25, -raio * 0.45, raio * 1.4];
    } else {
      const fr = (rMax - rMin) * 0.15, fx = (xMax - xMin) * 0.15;
      rMin -= fr; rMax += fr; xMin -= fx; xMax += fx;
    }
    // O quadro AMPLIADO pela roda, quando há. É só vista: não muda número
    // nenhum, e o botão direito devolve o quadro de cima.
    // O quadro NÃO segue o cursor. Seguiu, por uma rodada: na pré-falta o
    // ponto da carga mora a centenas de ohms, o quadro foi a 800 Ω e a falta
    // virou um borrão na origem (22/10/2026). Cursor fora do quadro aparece
    // preso na borda, apontando para onde está; a roda afasta se for preciso.
    if (meu.caixaZ) ({ rMin, rMax, xMin, xMax } = meu.caixaZ);

    // ESCALA IGUAL nos dois eixos, senão a circunferência da mho vira elipse
    // — e uma mho que parece elipse ensina a coisa errada.
    const k = Math.min(util.l / (rMax - rMin), util.a / (xMax - xMin));
    const sobraR = (util.l / k - (rMax - rMin)) / 2;
    const sobraX = (util.a / k - (xMax - xMin)) / 2;
    rMin -= sobraR; rMax += sobraR;
    xMin -= sobraX; xMax += sobraX;
    const X = (r) => esqDoQuadro + (r - rMin) * k;
    const Y = (x) => alt - m.baixo - (x - xMin) * k;
    // O que os gestos do mouse precisam para voltar de pixel a ohm.
    canvas._planoZ = { esq: esqDoQuadro, topo: m.topo, l: util.l, a: util.a,
                       base: alt - m.baixo, rMin, rMax, xMin, xMax, k };

    const emPct = (meu.unidadeZ || "ohm") === "pct" && zl > 0;
    const esc = emPct ? 100 / zl : 1;
    const unidade = emPct ? "%" : "Ω";
    const suave = token("--suave");

    // --- grade e eixos ---------------------------------------------------
    const passo = passoRedondo(rMax - rMin, 7);
    ctx.save();
    ctx.font = "9.5px var(--mono), monospace";
    ctx.lineWidth = 1;
    if (meu.gradeZ !== false) {
      ctx.strokeStyle = token("--linha");
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      for (let r = Math.ceil(rMin / passo) * passo; r <= rMax; r += passo) {
        ctx.moveTo(X(r), Y(xMin)); ctx.lineTo(X(r), Y(xMax));
      }
      for (let x = Math.ceil(xMin / passo) * passo; x <= xMax; x += passo) {
        ctx.moveTo(X(rMin), Y(x)); ctx.lineTo(X(rMax), Y(x));
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    ctx.strokeStyle = suave;
    ctx.beginPath();
    ctx.moveTo(X(rMin), Y(0)); ctx.lineTo(X(rMax), Y(0));
    ctx.moveTo(X(0), Y(xMin)); ctx.lineTo(X(0), Y(xMax));
    ctx.stroke();

    ctx.fillStyle = suave;
    ctx.textBaseline = "middle";
    ctx.textAlign = "right";
    for (let x = Math.ceil(xMin / passo) * passo; x <= xMax; x += passo) {
      if (Math.abs(x) < passo / 100) continue;
      ctx.fillText(formatar(x * esc, passo * esc >= 5 ? 0 : 1), X(0) - 5, Y(x));
    }
    ctx.textBaseline = "top";
    ctx.textAlign = "center";
    for (let r = Math.ceil(rMin / passo) * passo; r <= rMax; r += passo) {
      if (Math.abs(r) < passo / 100) continue;
      ctx.fillText(formatar(r * esc, passo * esc >= 5 ? 0 : 1), X(r), Y(0) + 5);
    }
    ctx.textAlign = "right";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(`R (${unidade})`, esqDoQuadro + util.l, Y(0) - 6);
    ctx.textAlign = "left";
    ctx.fillText(`X (${unidade})`, X(0) + 6, m.topo + 4);
    ctx.restore();

    // --- as zonas --------------------------------------------------------
    // Da maior para a menor, para a Z1 ficar por cima e não ser coberta.
    const modoZonas = meu.zonasZ || "contorno";
    if (modoZonas !== "nenhuma") {
      ctx.save();
      ctx.font = "10px var(--mono), monospace";
      ctx.textBaseline = "middle";
      for (const z of [...zonas].sort((a, b) => b.alcance - a.alcance)) {
        // A GEOMETRIA vem pronta do servidor (`geometria_mho`, `geometria_quad`):
        // a mho é o círculo que passa pela origem com o alcance de diâmetro,
        // espelhada na origem quando a zona é reversa; a quadrilateral é o
        // polígono simplificado. Aqui só se converte ohm em pixel.
        const cor = corDaZona(z.nome);
        const figuras = [];
        if (usaMho(z)) figuras.push(["mho", () => {
          ctx.beginPath();
          ctx.arc(X(z.mho.centro[0]), Y(z.mho.centro[1]), z.mho.raio * k, 0, 2 * Math.PI);
        }]);
        if (usaQuad(z)) figuras.push(["quad", () => {
          ctx.beginPath();
          z.quad.forEach(([qr, qx], i) => (i ? ctx.lineTo(X(qr), Y(qx)) : ctx.moveTo(X(qr), Y(qx))));
          ctx.closePath();
        }]);
        if (!figuras.length) continue;
        for (const [qual, caminho] of figuras) {
          caminho();
          // TODA zona ganha recheio. Era só a lida, e num registro sem ajuste
          // no arquivo (o caso comum) as três são sugeridas: o botão mudava
          // nada na tela. A origem continua dita pelo traço e pelo rótulo.
          if (modoZonas === "cheia") {
            ctx.globalAlpha = z.origem === "lido" ? 0.16 : 0.11;
            ctx.fillStyle = cor;
            ctx.fill();
            ctx.globalAlpha = 1;
          }
          ctx.strokeStyle = cor;
          // Com AMBAS, a quadrilateral vai mais fina: as duas na mesma cor, e
          // o tracejado já quer dizer «sugerida» — não pode virar «a outra».
          ctx.lineWidth = forma === "ambas" && qual === "quad" ? 1 : 1.6;
          ctx.setLineDash(TRACO_DA_ORIGEM[z.origem] || []);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        // O nome é palavra de OPERAÇÃO e fica dentro do quadro. A origem
        // entra junto quando não for lida do relé: «Z2 sugerida» é aviso,
        // não enfeite — e é o único jeito de ela não se passar por lida.
        ctx.fillStyle = cor;
        ctx.textAlign = "left";
        const rotulo = (z.origem === "sugerido" ? `${z.nome} sugerida`
                     : z.origem === "digitado" ? `${z.nome} digitada` : z.nome)
                     + (z.direcao === "R" ? " (reversa)" : "");
        // NA BORDA DIREITA do círculo, e não na ponta do vetor de alcance.
        // As três zonas saem do mesmo ângulo, então as três pontas caem na
        // mesma reta — e é por essa reta que a trajetória desce. Escrever
        // ali punha os três nomes, o «100 % da LT» e o traço medido todos
        // uns por cima dos outros. A borda direita de cada círculo está a
        // uma distância diferente do eixo, porque o raio é diferente.
        // Na borda direita da figura, na altura do centro dela.
        const [dirR, altX] = usaMho(z)
          ? [z.mho.centro[0] + z.mho.raio, z.mho.centro[1]]
          : [Math.max(...z.quad.map((q) => q[0])),
             (Math.max(...z.quad.map((q) => q[1])) + Math.min(...z.quad.map((q) => q[1]))) / 2];
        ctx.fillText(rotulo, X(dirR) + 6, Y(altX));
      }
      ctx.restore();
    }

    // --- os parâmetros da linha e o MTA --------------------------------------
    if (zl > 0) {
      ctx.save();
      ctx.strokeStyle = suave;
      ctx.fillStyle = suave;
      ctx.lineWidth = 1.4;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(X(0), Y(0));
      ctx.lineTo(X(zl * Math.cos(ang)), Y(zl * Math.sin(ang)));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(X(zl * Math.cos(ang)), Y(zl * Math.sin(ang)), 3, 0, 2 * Math.PI);
      ctx.fill();
      ctx.font = "9.5px var(--mono), monospace";
      // NA ALTURA EXATA da ponta, sem deslocamento vertical. Os nomes das
      // zonas ficam no topo de cada círculo, e os topos estão a uns quatro
      // ohms de distância um do outro: empurrar este rótulo para cima ou
      // para baixo é jogá-lo em cima do vizinho. Na altura da ponta ele cai
      // no meio da folga entre a Z1 e a Z2.
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText("100 % da LT", X(zl * Math.cos(ang)) + 7,
                   Y(zl * Math.sin(ang)));
      if (meu.mtaZ) {
        const longe = (rMax - rMin) * 2;
        ctx.strokeStyle = token("--destaque");
        ctx.globalAlpha = 0.75;
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 4]);
        ctx.beginPath();
        ctx.moveTo(X(0), Y(0));
        ctx.lineTo(X(longe * Math.cos(ang)), Y(longe * Math.sin(ang)));
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = token("--destaque");
        ctx.fillText(`MTA ${formatar(ang * 180 / Math.PI, 0)}°`,
                     X(0) + 8, Y(xMax) + 14);
        ctx.globalAlpha = 1;
      }
      ctx.restore();
    }

    // SEM CURSOR, SEM TRAJETÓRIA: só os eixos, as zonas e o pedido do
    // cursor — a mesma regra do plano complexo. Escolha dele, 22/10/2026.
    // O cursor que conta é o DESTE painel (o botão «cursor 1/2»), como lá.
    const doPainel = meu.cursor === 2 ? 2 : 1;
    if (cursores[doPainel - 1] === null || cursores[doPainel - 1] === undefined) {
      ctx.save();
      ctx.fillStyle = suave;
      ctx.font = "11px var(--mono), monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`ponha o cursor ${doPainel} (tecla ${doPainel} sobre a onda)`,
                   esqDoQuadro + 6, m.topo + 4);
      ctx.fillText("para ver a trajetória", esqDoQuadro + 6, m.topo + 18);
      ctx.restore();
      return;
    }

    // --- a trajetória ----------------------------------------------------
    // Presa à área do gráfico: a carga e a fuga depois da abertura são
    // deslocamentos enormes, e sem recorte elas escrevem por cima dos eixos
    // e das fichas.
    ctx.save();
    ctx.beginPath();
    ctx.rect(esqDoQuadro, m.topo, util.l, util.a);
    ctx.clip();
    // ATÉ O CURSOR, e não o registro inteiro: o caminho cresce quando o
    // cursor anda para a frente e se APAGA quando ele volta — a mesma ideia
    // do plano complexo. Pedido dele, 22/10/2026.
    const ateOCursor = cursores[doPainel - 1];
    const pontos = (painel.pontos || []).filter(
      (p) => p.r !== null && p.x !== null && p.t <= ateOCursor + 1e-9);
    // A trajetória NÃO é da cor do texto. Branco no tema escuro lia-se como
    // eixo ou grade, e era a cor mais forte do quadro sem ser medida nenhuma.
    // Verde (`--traco-1`), validado pelo `tools/paleta.py` contra todas as
    // cores — inclusive as três das zonas (vermelho, âmbar, ciano) e as dos
    // cursores. Pedido dele, 22/10/2026.
    const tinta = token("--traco-1");
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    // TRECHO A TRECHO, e não uma polilinha só. A carga mora a centenas de
    // ohms e a fuga depois da abertura vai ao infinito: os saltos entre elas
    // e a falta são deslocamentos enormes que, cheios, dominam o desenho e
    // escondem justamente o que se foi olhar. Eles aparecem tracejados e
    // apagados — o caminho existiu, mas não é onde o laço esteve medindo.
    const diagonal = Math.hypot(util.l, util.a);
    const dentro = (p) => {
      const px = X(p.r), py = Y(p.x);
      return px >= esqDoQuadro && px <= esqDoQuadro + util.l
          && py >= m.topo && py <= alt - m.baixo;
    };
    for (let n = 1; n < pontos.length; n += 1) {
      const a = pontos[n - 1], b = pontos[n];
      const salto = Math.hypot(X(b.r) - X(a.r), Y(b.x) - Y(a.x));
      const viagem = salto > diagonal * 0.18 || !dentro(a) || !dentro(b);
      ctx.save();
      ctx.strokeStyle = tinta;
      ctx.lineWidth = viagem ? 1.1 : 2;
      ctx.globalAlpha = viagem ? 0.35 : 1;
      if (viagem) ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(X(a.r), Y(a.x));
      ctx.lineTo(X(b.r), Y(b.x));
      ctx.stroke();
      ctx.restore();
    }
    // AS SETAS: o sentido em que a bolinha andou. Escolha da engrenagem:
    // pontas a cada N ms, o traço esmaecendo com a idade, ou só nos saltos
    // rápidos (o mergulho, onde o sentido importa). Maquete 7, 22/10/2026.
    const setas = meu.setasZ || "nenhuma";
    if (setas !== "nenhuma" && pontos.length > 4) {
      const estilo = meu.estiloSetaZ || "pontas";
      const passoMs = Number(meu.setaNZ) || 10;
      const agora = pontos[pontos.length - 1].t;
      let proxima = pontos[0].t;
      let ultima = null;
      ctx.fillStyle = tinta;
      for (let i = 2; i < pontos.length - 2; i += 1) {
        const a = pontos[i - 2], b = pontos[i + 2], p = pontos[i];
        const dx = X(b.r) - X(a.r), dy = Y(b.x) - Y(a.x);
        const passo = Math.hypot(dx, dy);
        if (passo < 1.5 || !dentro(p)) continue;
        if (estilo === "saltos") {
          if (passo / 4 < 4) continue;
          if (ultima && Math.hypot(X(p.r) - ultima[0], Y(p.x) - ultima[1]) < 26) continue;
        } else {
          if (p.t < proxima) continue;
          proxima = p.t + passoMs / 1000;
        }
        ctx.globalAlpha = estilo === "idade"
          ? Math.max(0.2, 1 - (agora - p.t) / 0.16) : 1;
        pontaDeSeta(ctx, X(p.r), Y(p.x), Math.atan2(dy, dx), estilo === "saltos" ? 7 : 5);
        ultima = [X(p.r), Y(p.x)];
      }
      ctx.globalAlpha = 1;
    }

    // OS PONTOS SÓ ENQUANTO A MÃO ESTÁ NO CURSOR. Eles dizem onde cada
    // amostra caiu — é deles que se lê a velocidade do mergulho, e é por
    // eles que se mira ao procurar um instante. Mas parados, o tempo todo,
    // são duzentas bolinhas por cima do único traço que importa. Acesos no
    // gesto em que servem, apagados no resto. Escolha dele, 20/10/2026.
    if (movendoCursor) {
      // Cada ponto é uma conta no fio: um halo da cor do FUNDO e um miolo da
      // cor do traço. Só o miolo, na mesma tinta da linha, some dentro dela
      // — e um ponto que não se distingue da linha não diz onde a amostra
      // caiu, que é a única coisa que ele tem para dizer.
      for (const p of pontos) {
        const px = X(p.r), py = Y(p.x);
        ctx.beginPath();
        ctx.arc(px, py, 2.8, 0, 2 * Math.PI);
        ctx.fillStyle = token("--fundo");
        ctx.fill();
        ctx.beginPath();
        ctx.arc(px, py, 1.7, 0, 2 * Math.PI);
        ctx.fillStyle = tinta;
        ctx.fill();
      }
    }

    // Os DOIS cursores marcados, nas cores da tabelinha e da moldura; o
    // escolhido no cabeçalho vem cheio, o outro só com o anel.
    const qualCursor = meu.cursor === 2 ? 2 : 1;
    for (const n of [1, 2]) {
      const p = pontoDoCursor(painel, n);
      if (!p) continue;
      // O outro cursor só aparece se cai no trecho JÁ desenhado: depois da
      // cabeça ele marcaria um ponto de um caminho que não está na tela.
      if (n !== qualCursor && p.t > ateOCursor + 1e-9) continue;
      const cor = token(n === 1 ? "--cursor-1" : "--cursor-2");
      // FORA DO QUADRO a bolinha encosta na borda e aponta para onde está.
      // Na pré-falta a carga mora a centenas de ohms: recortada, a bolinha
      // simplesmente não existia, e o cursor parecia não chegar ao plano.
      const px = X(p.r), py = Y(p.x);
      const bx = Math.min(Math.max(px, esqDoQuadro + 8), esqDoQuadro + util.l - 8);
      const by = Math.min(Math.max(py, m.topo + 8), alt - m.baixo - 8);
      const fora = bx !== px || by !== py;
      if (fora) {
        const d = Math.hypot(px - bx, py - by);
        ctx.beginPath();
        ctx.moveTo(bx, by);
        ctx.lineTo(bx + (px - bx) / d * 14, by + (py - by) / d * 14);
        ctx.strokeStyle = cor;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.arc(bx, by, n === qualCursor ? 6.5 : 5, 0, 2 * Math.PI);
      ctx.fillStyle = n === qualCursor && !fora ? cor : token("--fundo");
      ctx.fill();
      ctx.strokeStyle = cor;
      ctx.lineWidth = n === qualCursor ? 2.5 : 2;
      if (fora) ctx.setLineDash([3, 2]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.restore();
  }

  /** Os gestos do plano de impedância: roda amplia no ponto do mouse,
   * arrastar anda, botão direito volta ao quadro inteiro, clique leva o
   * cursor à amostra mais perto. Tudo DENTRO da moldura — fora dela a roda
   * rola a página, como nas ondas. Sem isto a roda caía no gesto das ondas
   * e ampliava o eixo do TEMPO, que não está neste gráfico. */
  function ligarPlanoDeImpedancia(bloco) {
    const canvas = bloco._canvas;
    const posicao = (evento) => {
      const caixa = canvas.getBoundingClientRect();
      return { x: evento.clientX - caixa.left, y: evento.clientY - caixa.top };
    };
    const naMoldura = (q, p) => q && p.x >= q.esq && p.x <= q.esq + q.l
      && p.y >= q.topo && p.y <= q.base;
    const repintarEste = () => pintarImpedancia(canvas, bloco._painel);

    canvas.addEventListener("wheel", (evento) => {
      evento.stopPropagation();
      const q = canvas._planoZ;
      const p = posicao(evento);
      if (!naMoldura(q, p)) return;
      evento.preventDefault();
      const atual = painelPorId(bloco._painel.id);
      if (!atual) return;
      const r = q.rMin + (p.x - q.esq) / q.k;
      const x = q.xMin + (q.base - p.y) / q.k;
      const f = evento.deltaY < 0 ? 0.8 : 1.25;
      atual.caixaZ = { rMin: r - (r - q.rMin) * f, rMax: r + (q.rMax - r) * f,
                       xMin: x - (x - q.xMin) * f, xMax: x + (q.xMax - x) * f };
      repintarEste();
    }, { passive: false });

    let pego = null;
    canvas.addEventListener("pointerdown", (evento) => {
      evento.stopPropagation();
      const q = canvas._planoZ;
      const p = posicao(evento);
      if (evento.button !== 0 || !naMoldura(q, p)) return;
      evento.preventDefault();
      canvas.setPointerCapture(evento.pointerId);
      pego = { p, q, andou: false };
    });
    canvas.addEventListener("pointermove", (evento) => {
      const q = canvas._planoZ;
      const p = posicao(evento);
      if (!pego) {
        canvas.style.cursor = naMoldura(q, p) ? "grab" : "";
        return;
      }
      const dx = (p.x - pego.p.x) / pego.q.k;
      const dy = (p.y - pego.p.y) / pego.q.k;
      if (!pego.andou && Math.hypot(p.x - pego.p.x, p.y - pego.p.y) < 3) return;
      pego.andou = true;
      canvas.style.cursor = "grabbing";
      const atual = painelPorId(bloco._painel.id);
      if (!atual) return;
      atual.caixaZ = { rMin: pego.q.rMin - dx, rMax: pego.q.rMax - dx,
                       xMin: pego.q.xMin + dy, xMax: pego.q.xMax + dy };
      repintarEste();
    });
    canvas.addEventListener("pointerup", (evento) => {
      if (!pego) return;
      const andou = pego.andou;
      const q = pego.q;
      pego = null;
      canvas.style.cursor = "grab";
      if (andou) return;
      // Clique parado: o cursor vai à amostra cujo ponto está mais perto.
      const p = posicao(evento);
      let melhor = null;
      let menor = PEGADA_DO_RASTRO * PEGADA_DO_RASTRO;
      for (const ponto of (bloco._painel.pontos || [])) {
        if (ponto.r === null || ponto.x === null) continue;
        const d = (q.esq + (ponto.r - q.rMin) * q.k - p.x) ** 2
                + (q.base - (ponto.x - q.xMin) * q.k - p.y) ** 2;
        if (d <= menor) { menor = d; melhor = ponto; }
      }
      if (!melhor) return;
      const meu = painelPorId(bloco._painel.id) || {};
      porCursor(meu.cursor === 2 ? 1 : 0, melhor.t);
      repintar();
    });
    canvas.addEventListener("contextmenu", (evento) => {
      evento.stopPropagation();
      evento.preventDefault();
      const atual = painelPorId(bloco._painel.id);
      if (!atual || !atual.caixaZ) return;
      delete atual.caixaZ;
      repintarEste();
    });
    canvas.title = "Roda amplia no ponto do mouse · arrastar anda · "
                 + "botão direito volta ao quadro inteiro · clique leva o "
                 + "cursor à amostra mais perto";
  }

  // --- o plano complexo -----------------------------------------------------
  //
  // O caminho que o fasor de cada sinal percorre, do começo do registro até o
  // cursor. Os números vêm prontos de `plot/complexo.py` — o caminho inteiro,
  // já girado pela referência —, e a tela só decide ATÉ ONDE desenhar, que é
  // o cursor. É por isso que a bolinha anda sem ida ao servidor.
  //
  // Decidido com o Alexandre em 21/10/2026, depois de quatro rodadas de
  // maquetes: um cursor só, a linha amostra a amostra, o rastro esmaecendo com
  // a idade (exponencial com piso), a cabeça sem etiqueta, e a referência com
  // as duas escolhas no cabeçalho — QUAL sinal é o zero e se ele é FIXO ou
  // DINÂMICO.

  //: O lado do quadro, em pixels de CSS. Fixo pelo mesmo motivo do fasorial:
  //: medir o pai seria um laço (o pai se ajusta ao canvas).
  const LADO_COMPLEXO = 420;

  //: Os dois modos da referência, ditos uma vez só: no hover da pílula e no ⓘ.
  const DICA_DA_FIXA = "Fixa: 0° é o ângulo da referência no primeiro ponto "
    + "do registro, e fica parado. Se a frequência não é exatamente 60 Hz, "
    + "tudo gira devagar — inclusive a própria referência, que ganha caminho. "
    + "Os ângulos NÃO são os do diagrama fasorial.";
  const DICA_DA_DINAMICA = "Dinâmica: 0° é o ângulo da referência em CADA "
    + "instante, como no diagrama fasorial e no SIGRA. O giro some e a "
    + "referência fica parada no eixo real.";
  const FOLGA_COMPLEXO = 26;

  //: O rastro: forte na bolinha, caindo pela metade a cada ciclo e meio de
  //: idade, e nunca abaixo do piso — parado depois da falta, o caminho
  //: inteiro continua legível. É o «exponencial, com piso» da maquete.
  const PISO_DO_RASTRO = 0.14;
  const MEIA_VIDA_DO_RASTRO = 1.5;

  //: Quão perto do traço o mouse precisa estar para o hover dizer o instante
  //: e o clique levar o cursor até lá.
  const PEGADA_DO_RASTRO = 8;

  function blocoComplexo(painel) {
    const el = criar("section", "grafico complexo");
    const meu = painelPorId(painel.id) || {};
    const qual = meu.cursor === 2 ? 2 : 1;

    const botaoCursor = criar("button", "medida", `cursor ${qual}`);
    botaoCursor.type = "button";
    botaoCursor.title = `A bolinha anda até o cursor ${qual}. Clique para `
                      + "passar para o outro.";
    botaoCursor.addEventListener("click", () => alternarCursorDoPainel(painel.id));

    // A referência: QUAL sinal é o zero (o menu do fasorial) e COMO ele vale.
    // Os dois vão ao servidor, porque mudam o caminho que ele calcula.
    // Uma PÍLULA só, escolha dele em 22/10/2026 (maquete «referência»,
    // sugestão 2): à esquerda QUAL sinal é o zero (abre o menu), à direita
    // COMO ele vale (cada clique alterna fixa ⇄ dinâmica). Eram dois
    // controles soltos, e quem via pela primeira vez não ligava um ao outro.
    const fixa = meu.fixa !== false;
    const [botaoRef, ancoraRef] = botaoDaReferencia(painel);
    botaoRef.className = "metade-do-sinal";
    const botaoModo = criar("button", "metade-do-modo",
                            fixa ? "fixa" : "dinâmica");
    botaoModo.type = "button";
    botaoModo.style.setProperty("--ic", fixa ? "var(--ic-fixa)" : "var(--ic-dinamica)");
    botaoModo.title = (fixa ? DICA_DA_FIXA : DICA_DA_DINAMICA)
                    + ` Clique para passar para a ${fixa ? "dinâmica" : "fixa"}.`;
    botaoModo.addEventListener("click", () => {
      const atual = painelPorId(painel.id);
      if (!atual) return;
      guardarParaDesfazer();
      atual.fixa = !fixa;
      recarregar();
    });
    const par = criar("span", "pilula-da-referencia");
    par.append(botaoRef, botaoModo);

    // O ⓘ: a explicação dos dois modos, aberta no clique e não só no hover —
    // é a pergunta de quem vê a pílula pela primeira vez.
    const idInfo = `info-ref-${painel.id}`;
    const info = criar("button", "info-azul", "i");
    info.type = "button";
    info.setAttribute("aria-label", "o que é fixa e dinâmica");
    info.title = "O que é fixa e dinâmica";
    const ancoraInfo = criar("span", "ancora-de-menu");
    ancoraInfo.id = idInfo;
    info.addEventListener("click", () => {
      menuSuspenso(idInfo, "a referência angular", (caixa) => {
        // Os dois modos como dois BLOCOS, cada um com o ícone da pílula e o
        // nome em destaque; o que está valendo agora vem marcado. Em texto
        // corrido os três parágrafos se liam como um só.
        const texto = criar("div", "explica-referencia");
        for (const [nome, icone, dica, vale] of [
          ["fixa", "var(--ic-fixa)", DICA_DA_FIXA, fixa],
          ["dinâmica", "var(--ic-dinamica)", DICA_DA_DINAMICA, !fixa]]) {
          const bloco = criar("div", "modo-da-referencia" + (vale ? " valendo" : ""));
          const cabeca = criar("div", "nome-do-modo");
          const simbolo = criar("span", "icone-do-modo");
          simbolo.style.setProperty("--ic", icone);
          cabeca.append(simbolo, criar("b", null, nome));
          if (vale) cabeca.append(criar("span", "selo-valendo", "em uso"));
          bloco.append(cabeca, criar("p", null, dica.slice(dica.indexOf(": ") + 2)));
          texto.append(bloco);
        }
        texto.append(criar("p", "suave", "Na dinâmica, onde a referência some "
          + "(o disjuntor abriu, a tensão foi a zero), o ponto também some: "
          + "sem ela não há de onde medir o ângulo."));
        caixa.append(texto);
      }, { fixo: true });
    });

    const emPu = (meu.unidade || "pu") === "pu";
    // O rótulo diz o que o clique FAZ, como o «ver RMS» das ondas: escrever o
    // estado num botão de chave lia-se como a ação, e em pu ele dizia «ver em
    // pu».
    const botaoUnidade = criar("button", "medida",
                               emPu ? "ver em A / V" : "ver em pu");
    botaoUnidade.type = "button";
    botaoUnidade.title = emPu
      ? "Em pu da nominal de cada canal: tensão e corrente na mesma régua. "
        + "Clique para ver em ampère e volt, com uma régua por grandeza."
      : "Em ampère e volt, uma régua por grandeza. Clique para voltar ao pu.";
    botaoUnidade.addEventListener("click", () => {
      const atual = painelPorId(painel.id);
      if (!atual) return;
      guardarParaDesfazer();
      atual.unidade = emPu ? "av" : "pu";
      desenharTudo();
    });

    const mais = criar("button", "medida", "+ sinal");
    mais.type = "button";
    mais.title = "Pôr ou tirar sinais deste plano. Cada um ganha o seu "
               + "caminho. Só entra o que tem fasor de 60 Hz.";
    mais.addEventListener("click", () => abrirCatalogoFasorial(painel));

    el.append(cabecalhoDoPainel(painel, [
      botaoCursor, par, ancoraRef, info, ancoraInfo, botaoUnidade, mais,
      ...engrenagemDoPainel(painel, () => ajustesDoComplexo(painel)),
    ]));

    const corpo = criar("div", "corpo-fasorial");
    const caixa = criar("div", "tela-complexo");
    const canvas = document.createElement("canvas");
    const dica = criar("div", "dica-do-complexo");
    dica.hidden = true;
    caixa.append(canvas, dica);
    const lado = criar("div", "lado-fasorial");
    const tabela = criar("table", "mini fasores");
    lado.append(tabela);
    corpo.append(caixa, lado);
    el.append(corpo);
    comMolduras(el, corpo);
    // UM cursor só na moldura: o plano mostra o caminho até um instante, e o
    // outro cursor ali só fazia duvidar de qual dos dois a bolinha segue.
    for (const m of el._molduras) m.so = qual - 1;

    if (!(painel.sinais || []).length) {
      el.append(criar("p", "vazio",
        "Nenhum sinal neste plano. Use o «+ sinal» para escolher as correntes "
        + "e tensões cujo caminho você quer ver."));
    }
    const pe = criar("div", "rodape-do-painel");
    el.append(pe);

    el._painel = painel;
    el._canvas = canvas;
    el._dica = dica;
    el._tabela = tabela;
    el._pe = pe;
    montarTabelaDoComplexo(el);
    ligarRastro(el);
    return el;
  }

  //: A engrenagem do plano: o que se ajusta uma vez e não se toca mais.
  function ajustesDoComplexo(painel) {
    const meu = painelPorId(painel.id) || {};
    const chave = (campo, rotulo, dica, padrao) => {
      const ligado = meu[campo] === undefined ? padrao : !!meu[campo];
      const b = criar("button", "medida" + (ligado ? " escolhido" : ""), rotulo);
      b.type = "button";
      b.title = dica;
      b.addEventListener("click", () => {
        const atual = painelPorId(painel.id);
        if (!atual) return;
        atual[campo] = !ligado;
        menuAberto?.();
        desenharTudo();
      });
      return b;
    };
    return [
      "desenho",
      chave("ciclos", "marcar os ciclos",
            "Um ponto a cada ciclo contado do início da perturbação, para "
            + "contar em quantos ciclos o fasor assentou. O início é palpite "
            + "do programa.", false),
      chave("unitario", "círculo de 1 pu",
            "O tracejado âmbar onde o módulo vale uma vez a base. Só em pu.",
            true),
    ];
  }

  /** O fator de cada sinal para a régua do desenho, e a régua dele.
   *
   * Em pu: a base que o usuário digitou, a do arquivo, ou o maior daquela
   * unidade no registro — a MESMA ordem do fasorial (`fasoresDoPainel`), e
   * pela mesma razão. Em A/V: fator 1, e uma régua por unidade.
   */
  function escalasDoComplexo(painel) {
    const meu = painelPorId(painel.id) || {};
    const emPu = (meu.unidade || "pu") === "pu";
    const digitadas = meu.bases || {};
    const maior = new Map();
    for (const s of (painel.sinais || [])) {
      if (s.base || !s.pico) continue;
      maior.set(s.unidade, Math.max(maior.get(s.unidade) || 0, s.pico));
    }
    const saida = new Map();
    for (const s of (painel.sinais || [])) {
      const digitada = digitadas[s.unidade];
      const base = digitada || s.base || maior.get(s.unidade) || 0;
      const doRegistro = !digitada && !s.base;
      // Em A/V a base continua sabida: é dela que sai o círculo de 1 pu de
      // cada grandeza.
      if (!emPu) {
        saida.set(s.id, { fator: 1, regua: s.unidade, un: s.unidade, base, doRegistro });
        continue;
      }
      saida.set(s.id, { fator: base ? 1 / base : 0, regua: "pu", un: "pu", base,
                        doRegistro });
    }
    return saida;
  }

  /** O índice do último ponto do caminho no instante `t`, ou -1. */
  function pontoNoInstante(painel, t) {
    const tempos = (painel.pontos && painel.pontos.t) || [];
    let a = 0, b = tempos.length - 1, achado = -1;
    while (a <= b) {
      const m = (a + b) >> 1;
      if (tempos[m] <= t + 1e-12) { achado = m; a = m + 1; } else b = m - 1;
    }
    return achado;
  }

  function pintarComplexo(bloco) {
    const canvas = bloco._canvas;
    const painel = bloco._painel;
    const lado = LADO_COMPLEXO;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${lado}px`;
    canvas.style.height = `${lado}px`;
    dimensionar(canvas, Math.round(lado * dpr), Math.round(lado * dpr));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, lado, lado);

    const meu = painelPorId(painel.id) || {};
    const emPu = (meu.unidade || "pu") === "pu";
    const cx = lado / 2, cy = lado / 2;
    const raio = lado / 2 - FOLGA_COMPLEXO;
    const escalas = escalasDoComplexo(painel);
    const trilhas = painel.trajetorias || {};
    const tempos = (painel.pontos && painel.pontos.t) || [];
    const f0 = dados.frequencia_hz || 60;
    const k = meu.cursor === 2 ? 1 : 0;
    const tc = cursores[k];
    // Sem cursor, NADA de caminho: a bolinha nasce no começo do registro e
    // anda com o cursor — mostrar o registro inteiro antes disso contradiz a
    // ideia. O quadro fica com a grade e a frase pedindo o cursor. Pedido
    // dele, 21/10/2026.
    const cabeca = tc === null ? -1 : pontoNoInstante(painel, tc);
    const transicao = painel.transicao;
    const naTransicao = (t) => !!transicao && t >= transicao[0] && t < transicao[1];

    // --- as réguas: do REGISTRO INTEIRO, uma por grandeza em A/V ----------
    const maiores = new Map();
    for (const s of (painel.sinais || [])) {
      const e = escalas.get(s.id);
      const tr = trilhas[s.id];
      if (!e || !e.fator || !tr) continue;
      let m = maiores.get(e.regua) || 0;
      for (let i = 0; i < tr.re.length; i += 1) {
        if (tr.re[i] === null) continue;
        const v = Math.hypot(tr.re[i], tr.im[i]) * e.fator;
        if (v > m) m = v;
      }
      maiores.set(e.regua, m);
    }
    // Com o círculo de 1 pu ligado, a régua ESTICA até ele caber: um círculo
    // que fica fora do quadro é uma referência que ninguém vê. Desligado, a
    // régua volta a se ajustar só ao que está desenhado.
    const comUnitario = meu.unitario !== false;
    const unitarios = new Map();
    for (const s of (painel.sinais || [])) {
      const e = escalas.get(s.id);
      if (!e || !e.base || unitarios.has(e.regua)) continue;
      unitarios.set(e.regua, emPu ? 1 : e.base);
    }
    if (comUnitario) {
      for (const [nome, um] of unitarios) {
        maiores.set(nome, Math.max(maiores.get(nome) || 0, um * 1.02));
      }
    }
    const ordem = [...maiores.keys()];
    const aneis = 4;
    const reguas = new Map();
    for (const nome of ordem) {
      const m = maiores.get(nome) || 0;
      const passo = m > 0 ? passoRedondo(m * 1.04, aneis) : 1;
      reguas.set(nome, { passo, alcance: passo * aneis });
    }

    // --- grade, eixos e nomes ---------------------------------------------
    ctx.save();
    ctx.lineWidth = 1;
    ctx.strokeStyle = token("--linha");
    ctx.globalAlpha = 0.55;
    for (let i = 1; i <= aneis; i += 1) {
      ctx.beginPath();
      ctx.arc(cx, cy, (i / aneis) * raio, 0, 2 * Math.PI);
      ctx.stroke();
    }
    for (let a = 0; a < 180; a += 30) {
      const dx = raio * Math.cos(a * Math.PI / 180);
      const dy = raio * Math.sin(a * Math.PI / 180);
      ctx.beginPath();
      ctx.moveTo(cx - dx, cy + dy);
      ctx.lineTo(cx + dx, cy - dy);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.strokeStyle = token("--suave");
    ctx.beginPath();
    ctx.moveTo(cx - raio, cy); ctx.lineTo(cx + raio, cy);
    ctx.moveTo(cx, cy - raio); ctx.lineTo(cx, cy + raio);
    ctx.stroke();

    // Os números dos anéis: a primeira régua acima do eixo real, a segunda
    // (em A/V) abaixo dele, cada uma com a sua unidade.
    ctx.font = "9.5px var(--mono), monospace";
    ordem.slice(0, 2).forEach((nome, j) => {
      const r = reguas.get(nome);
      ctx.fillStyle = j === 0 ? token("--suave") : token("--tinta");
      ctx.textAlign = "left";
      ctx.textBaseline = j === 0 ? "bottom" : "top";
      for (let i = 1; i <= aneis; i += 1) {
        const v = r.passo * i;
        const texto = formatar(v, v < 1 ? 2 : v < 10 ? 1 : 0)
                    + (i === aneis ? ` ${nome}` : "");
        ctx.fillText(texto, cx + (i / aneis) * raio + 2, j === 0 ? cy - 2 : cy + 2);
      }
    });

    // O nome dos eixos: o horizontal na ponta direita, o vertical escrito ao
    // longo dele, como em todo gráfico técnico.
    // O nome dos eixos: «real» na ponta direita, «imag» no alto do eixo
    // vertical — a forma curta, escolhida por ele na maquete do rastro.
    ctx.fillStyle = token("--suave");
    ctx.font = "9.5px var(--mono), monospace";
    ctx.textAlign = "right";
    ctx.textBaseline = "bottom";
    ctx.fillText("real", cx + raio - 2, cy - 14);
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText("imag", cx + 6, cy - raio + 2);

    // O círculo de 1 pu: um só em pu; em A/V, um por grandeza, cada um no
    // valor da base dela e com a unidade escrita — dois círculos tracejados
    // sem nome não diriam qual é de quem.
    if (comUnitario) {
      ctx.strokeStyle = token("--atencao");
      ctx.fillStyle = token("--atencao");
      ctx.font = "9.5px var(--mono), monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "bottom";
      let n = 0;
      for (const [nome, um] of unitarios) {
        const r = reguas.get(nome);
        if (!r || um > r.alcance) continue;
        const r1 = raio * um / r.alcance;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.arc(cx, cy, r1, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
        const ang = 0.9 + n * 0.55;
        ctx.fillText(emPu ? "1 pu" : `1 pu ${nome}`,
                     cx + r1 * Math.cos(ang) + 4, cy - r1 * Math.sin(ang) - 2);
        n += 1;
      }
    }
    ctx.restore();

    // --- os caminhos ---------------------------------------------------------
    const alvos = [];
    const celas = bloco._celas || new Map();
    for (const s of (painel.sinais || [])) {
      const e = escalas.get(s.id);
      const tr = trilhas[s.id];
      const cel = celas.get(s.id);
      if (!e || !e.fator || !tr || s.sem_sinal) {
        if (cel) escreverComplexo(cel, null, e);
        continue;
      }
      const r = reguas.get(e.regua);
      const k2 = raio / r.alcance * e.fator;
      const X = (i) => cx + tr.re[i] * k2;
      const Y = (i) => cy - tr.im[i] * k2;
      const cor = corDoSinal(s, painel);
      const opacidade = (t) => tc === null ? 0.55
        : PISO_DO_RASTRO + (1 - PISO_DO_RASTRO)
          * Math.pow(0.5, Math.max(0, (tc - t) * f0) / MEIA_VIDA_DO_RASTRO);

      ctx.save();
      ctx.strokeStyle = cor;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.lineWidth = 1.8;
      // Os pedaços com a mesma aparência viram UM traço: um caminho de dez
      // mil pontos não pode virar dez mil `stroke`.
      let chave = null;
      let aberto = false;
      const fechar = () => { if (aberto) { ctx.stroke(); aberto = false; } };
      for (let i = 1; i <= cabeca; i += 1) {
        if (tr.re[i] === null || tr.re[i - 1] === null) { fechar(); chave = null; continue; }
        const alfa = Math.round(opacidade(tempos[i]) * 30) / 30;
        const tracejado = naTransicao(tempos[i]);
        const nova = `${alfa}|${tracejado}`;
        if (nova !== chave) {
          fechar();
          ctx.globalAlpha = alfa;
          ctx.setLineDash(tracejado ? [4, 3] : []);
          ctx.beginPath();
          ctx.moveTo(X(i - 1), Y(i - 1));
          aberto = true;
          chave = nova;
        }
        ctx.lineTo(X(i), Y(i));
      }
      fechar();
      ctx.setLineDash([]);

      if (meu.ciclos) {
        ctx.fillStyle = cor;
        ctx.font = "9px var(--mono), monospace";
        ctx.textAlign = "left";
        ctx.textBaseline = "bottom";
        for (const c of (painel.ciclos || [])) {
          if (c.k > cabeca || tr.re[c.k] === null) continue;
          ctx.globalAlpha = Math.max(0.3, opacidade(tempos[c.k]));
          ctx.beginPath();
          ctx.arc(X(c.k), Y(c.k), 2.4, 0, 2 * Math.PI);
          ctx.fill();
          if (s === painel.sinais[0] && c.ciclo % 2 === 1) {
            ctx.fillStyle = token("--suave");
            ctx.fillText(`+${c.ciclo}`, X(c.k) + 4, Y(c.k) - 3);
            ctx.fillStyle = cor;
          }
        }
      }
      ctx.globalAlpha = 1;

      // A bolinha: o ponto do cursor, sem etiqueta — pedido dele.
      const temCabeca = tc !== null && cabeca >= 0 && tr.re[cabeca] !== null;
      if (temCabeca) {
        ctx.beginPath();
        ctx.arc(X(cabeca), Y(cabeca), 4.6, 0, 2 * Math.PI);
        ctx.fillStyle = cor;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = token("--superficie");
        ctx.stroke();
      }
      ctx.restore();
      if (cel) {
        escreverComplexo(cel, temCabeca
          ? { re: tr.re[cabeca] * (emPu ? e.fator : 1),
              im: tr.im[cabeca] * (emPu ? e.fator : 1) } : null, e);
      }

      // Os alvos do hover e do clique: os pontos já desenhados.
      for (let i = 0; i <= cabeca; i += 1) {
        if (tr.re[i] === null) continue;
        alvos.push({ x: X(i), y: Y(i), i, sinal: s, e });
      }
    }
    bloco._alvos = alvos;

    if (tc === null && (painel.sinais || []).length) {
      ctx.save();
      ctx.fillStyle = token("--suave");
      ctx.font = "11px var(--mono), monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`ponha o cursor ${k + 1} (tecla ${k + 1} sobre a onda)`, 6, 4);
      ctx.fillText("para a bolinha andar", 6, 18);
      ctx.restore();
    }
    escreverPeDoComplexo(bloco, escalas);
  }

  /** O módulo e o ângulo do ponto do cursor, na linha da tabela. */
  function escreverComplexo(cel, z, e) {
    if (!z) {
      cel.modulo.textContent = "—";
      cel.angulo.textContent = "—";
      cel.modulo.classList.add("vazio-valor");
      cel.angulo.classList.add("vazio-valor");
      return;
    }
    const m = Math.hypot(z.re, z.im);
    const casas = m > 0 ? Math.min(5, Math.max(0, 4 - Math.floor(Math.log10(m)))) : 3;
    cel.modulo.textContent = formatar(m, casas);
    cel.angulo.textContent = `${formatar(Math.atan2(z.im, z.re) * 180 / Math.PI, 1, false)}°`;
    cel.modulo.classList.remove("vazio-valor");
    cel.angulo.classList.remove("vazio-valor");
    cel.modulo.title = e && e.un === "pu" && e.base
      ? `${formatar(m * e.base, 3)} ${cel.unidade} — 1 pu = ${formatar(e.base, casasDaBase(e.base))} ${cel.unidade}`
      : "";
  }

  /** A tabela ao lado: sinal, módulo e ângulo no ponto do cursor.
   *
   * O ângulo é o do PLANO — contado da referência deste painel, fixa ou
   * dinâmica —, não o da leitura do cursor: a tabela tem de dizer o número
   * do ponto que está desenhado ao lado dela.
   */
  function montarTabelaDoComplexo(bloco) {
    const painel = bloco._painel;
    const meu = painelPorId(painel.id) || {};
    const emPu = (meu.unidade || "pu") === "pu";
    const tabela = bloco._tabela;
    tabela.replaceChildren();
    const cabeca = criar("tr");
    cabeca.append(criar("th", "unidade", emPu ? "pu" : "sinal"),
                  criar("th", null, "módulo"), criar("th", null, "ângulo"));
    const thead = criar("thead");
    thead.append(cabeca);
    const tbody = criar("tbody");
    const celas = new Map();
    for (const sinal of (painel.sinais || [])) {
      const linha = criar("tr");
      const nome = criar("th", "canal");
      const rotulo = criar("span", "rotulo");
      rotulo.append(bolinhaDoSinal(painel, sinal),
                    criarNome("span", "nome", sinal.sinal));
      if (!emPu && sinal.unidade) {
        rotulo.append(criar("span", "unidade-extra", `(${sinal.unidade})`));
      }
      nome.append(rotulo);
      const modulo = criar("td", "valor-1 vazio-valor", "—");
      const angulo = criar("td", "valor-2 vazio-valor", "—");
      linha.append(nome, modulo, angulo);
      tbody.append(linha);
      celas.set(sinal.id, { modulo, angulo, unidade: sinal.unidade });
    }
    tabela.append(thead, tbody);
    tabela.hidden = !tbody.children.length;
    bloco._celas = celas;
  }

  /** O rodapé: de onde sai o zero dos ângulos, o 1 pu, e os avisos. */
  function escreverPeDoComplexo(bloco, escalas) {
    const painel = bloco._painel;
    const pe = bloco._pe;
    if (!pe) return;
    const meu = painelPorId(painel.id) || {};
    const zero = painel.zero || {};
    const linhas = [];
    if ((painel.sinais || []).length) {
      linhas.push([null, zero.fixa
        ? `0° = ${zero.nome || "—"} no primeiro ponto do registro, fixo — os `
          + "ângulos não são os do fasorial"
        : `0° = ${zero.nome || "—"} em cada instante, como no fasorial`]);
      if (!zero.fixa && zero.ate !== null && zero.ate !== undefined) {
        linhas.push(["aviso", `${zero.nome} foi a zero em `
          + `${formatar(paraMs(zero.ate), 1)} ms: dali em diante não há zero `
          + "de ângulo, e o caminho de todos para. Escolha uma tensão, ou a "
          + "referência fixa."]);
      }
      if ((meu.unidade || "pu") === "pu") {
        const vistas = new Map();
        for (const s of painel.sinais) {
          const e = escalas.get(s.id);
          if (e && e.base && !vistas.has(s.unidade)) vistas.set(s.unidade, e);
        }
        const partes = [...vistas.entries()].map(([un, e]) =>
          `${formatar(e.base, casasDaBase(e.base))} ${un}`
          + (e.doRegistro ? " (o maior do registro)" : ""));
        if (partes.length) linhas.push([null, `1 pu = ${partes.join(" · ")}`]);
      }
      if (painel.transicao) {
        linhas.push([null, "tracejado: a janela de um ciclo atravessando o "
          + "início da perturbação — ali o fasor mistura pré-falta e falta, e "
          + "as voltas são do filtro. O início é palpite do programa."]);
      }
      if ((painel.passo || 1) > 1) {
        linhas.push(["aviso", `registro longo: um ponto a cada ${painel.passo} `
          + "amostras, e o cursor cai no ponto mantido mais perto"]);
      }
    }
    for (const texto of (painel.rodape || [])) linhas.push([null, texto]);
    pe.replaceChildren(...linhas.map(([classe, texto]) =>
      criar("div", classe, texto)));
    pe.hidden = !linhas.length;
  }

  /** O hover diz o instante e o valor do ponto; o clique leva o cursor lá.
   *
   * Sem o tempo no eixo, um caminho parado não diz QUANDO passou por cada
   * lugar. Navegar pelo próprio desenho evita voltar à onda para achar o
   * instante de um ponto que se está vendo aqui.
   */
  function ligarRastro(bloco) {
    const canvas = bloco._canvas;
    const perto = (evento) => {
      const r = canvas.getBoundingClientRect();
      const x = evento.clientX - r.left;
      const y = evento.clientY - r.top;
      let melhor = null;
      let menor = PEGADA_DO_RASTRO * PEGADA_DO_RASTRO;
      for (const a of (bloco._alvos || [])) {
        const d = (a.x - x) ** 2 + (a.y - y) ** 2;
        if (d <= menor) { menor = d; melhor = a; }
      }
      return melhor;
    };
    // O gesto é DESTE desenho: a área dos gráficos não pode tratá-lo como
    // clique de seleção nem como arrasto de panorama.
    canvas.addEventListener("pointerdown", (evento) => {
      evento.stopPropagation();
      const a = perto(evento);
      if (!a || evento.button !== 0) return;
      const painel = bloco._painel;
      const meu = painelPorId(painel.id) || {};
      porCursor(meu.cursor === 2 ? 1 : 0, painel.pontos.t[a.i]);
      repintar();
    });
    canvas.addEventListener("pointermove", (evento) => {
      evento.stopPropagation();
      const a = perto(evento);
      const dica = bloco._dica;
      canvas.style.cursor = a ? "pointer" : "";
      if (!a) { dica.hidden = true; return; }
      const painel = bloco._painel;
      const t = painel.pontos.t[a.i];
      const tr = painel.trajetorias[a.sinal.id];
      const emPu = a.e.un === "pu";
      const re = tr.re[a.i] * (emPu ? a.e.fator : 1);
      const im = tr.im[a.i] * (emPu ? a.e.fator : 1);
      const m = Math.hypot(re, im);
      const casas = m > 0 ? Math.min(5, Math.max(0, 4 - Math.floor(Math.log10(m)))) : 3;
      const travessia = painel.transicao && t >= painel.transicao[0]
                     && t < painel.transicao[1];
      dica.textContent = `${a.sinal.sinal} · ${formatar(paraMs(t), 2, false)} ms · `
        + `${formatar(m, casas)} ${a.e.un} ∠ ${formatar(Math.atan2(im, re) * 180 / Math.PI, 1, false)}°`
        + (travessia ? " · janela atravessando a falta" : "")
        + " — clique para levar o cursor aqui";
      dica.hidden = false;
      dica.style.left = `${Math.min(a.x + 12, LADO_COMPLEXO - 10)}px`;
      dica.style.top = `${a.y + 12}px`;
    });
    canvas.addEventListener("pointerleave", () => {
      bloco._dica.hidden = true;
      canvas.style.cursor = "";
    });
    canvas.addEventListener("wheel", (evento) => evento.stopPropagation());
  }

  // --- o plano alfa (87L) -----------------------------------------------------
  //
  // A razão `k` entre a corrente dos dois terminais, fase por fase, andando
  // até o cursor. Todos os números vêm prontos de `plot/alfa.py` — `k`, os
  // módulos em pu, o ângulo do remoto e a DECISÃO de cada ponto. A tela só
  // escolhe o ponto do cursor e converte em pixel. Escolha dele, 22/10/2026:
  // a variação A da maquete (uma coluna por sinal na tabela), com até três
  // sinais e os ajustes na engrenagem.

  //: O lado do quadro, em pixels de CSS. Fixo, como o do plano complexo.
  const LADO_ALFA = 380;
  const FOLGA_ALFA = 24;

  //: Os sinais que o plano aceita, na ordem do menu, com o que cada um é.
  const SINAIS_DO_ALFA = [
    ["A", "IA", "fase A"], ["B", "IB", "fase B"], ["C", "IC", "fase C"],
    ["3I0", "3I0", "sequência zero ×3 — o 87LG"],
    ["I2", "I2", "sequência negativa — o 87LQ"],
  ];
  const MAXIMO_NO_ALFA = 3;

  /** Reabre a engrenagem do painel depois de um redesenho: mexer num ajuste
   * refaz o painel inteiro, e o menu sumir debaixo do dedo a cada número
   * digitado obrigaria a abrir de novo para ver o efeito. */
  function reabrirEngrenagem(id) {
    const ancora = document.getElementById(`menu-ajustes-${id}`);
    const botao = ancora && ancora.previousElementSibling;
    if (botao && !ancora.firstChild) botao.click();
  }

  function blocoAlfa(painel) {
    const el = criar("section", "grafico alfa");
    const meu = painelPorId(painel.id) || {};
    const qual = meu.cursor === 2 ? 2 : 1;

    const botaoCursor = criar("button", "medida", `cursor ${qual}`);
    botaoCursor.type = "button";
    botaoCursor.title = `O ponto anda até o cursor ${qual}. Clique para passar `
                      + "para o outro.";
    botaoCursor.addEventListener("click", () => alternarCursorDoPainel(painel.id));

    // O PONTO DE VISTA: o terminal clicado vira o denominador de `k`. É como
    // o relé daquele terminal enxerga — e serve para conferir com o
    // relatório do relé do outro lado, que calcula do ponto de vista dele.
    const vista = painel.vista === "remoto" ? "remoto" : "local";
    const par = criar("span", "par-de-medidas");
    for (const lado of ["local", "remoto"]) {
      const grupo = painel[lado];
      const rotulo = !grupo ? "" : (grupo.ied && grupo.ied !== "A"
        ? `${grupo.rotulo.split("|").pop()} · IED ${grupo.ied}` : grupo.rotulo);
      const b = criar("button", "medida" + (vista === lado ? " escolhido" : ""),
                      `${lado}${rotulo ? ` · ${rotulo}` : ""}`);
      b.type = "button";
      b.setAttribute("aria-pressed", String(vista === lado));
      if (!grupo) {
        b.disabled = true;
        b.title = "Este registro não tem a trinca do outro terminal.";
      } else {
        b.title = lado === "local"
          ? `Visto do LOCAL (${grupo.rotulo}): k = I remoto / I local — como `
            + "o relé deste terminal enxerga."
          : `Visto do REMOTO (${grupo.rotulo}): k = I local / I remoto — como `
            + "o relé do outro terminal enxerga.";
      }
      b.addEventListener("click", () => {
        const atual = painelPorId(painel.id);
        if (!atual || (atual.vista || "local") === lado) return;
        guardarParaDesfazer();
        atual.vista = lado;
        recarregar();
      });
      par.append(b);
    }

    const ancoraSinais = criar("span", "ancora-de-menu");
    ancoraSinais.id = `menu-sinais-alfa-${painel.id}`;
    const mais = criar("button", "medida", "+ sinal");
    mais.type = "button";
    mais.title = "Trocar ou acrescentar sinais: as três fases, 3I0 e I2. Até "
               + `${MAXIMO_NO_ALFA} por plano.`;
    mais.addEventListener("click", () => abrirSinaisDoAlfa(painel));

    el.append(cabecalhoDoPainel(painel, [
      botaoCursor, par, mais, ancoraSinais,
      ...engrenagemDoPainel(painel, () => ajustesDoAlfa(painel)),
    ]));

    const corpo = criar("div", "corpo-fasorial");
    const caixa = criar("div", "tela-alfa");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    const lado = criar("div", "lado-fasorial");
    const tabela = criar("table", "mini alfa-tabela");
    const tempo = criar("div", "tempo-do-alfa");
    lado.append(tabela, tempo);
    corpo.append(caixa, lado);
    el.append(corpo);
    comMolduras(el, corpo);
    for (const m of el._molduras) m.so = qual - 1;

    const pe = criar("div", "rodape-do-painel");
    if (painel.falta) pe.append(criar("div", "aviso", painel.falta));
    // Um terminal em cada registro: o ângulo entre eles só vale o que o
    // alinhamento sustenta, e isso vem PRIMEIRO, em cor de aviso quando passa
    // de 2° ou não se sabe. Ver `plot/alfa.py`.
    const incerto = painel.entre_ieds
      && !(painel.refino && painel.refino.aplicado)
      && (painel.incerteza_graus === null || painel.incerteza_graus > 2);
    (painel.rodape || []).forEach((texto, k) =>
      pe.append(criar("div", k === 0 && incerto ? "aviso" : null, texto)));
    pe.hidden = !pe.children.length;
    el.append(pe);

    el._painel = painel;
    el._canvas = canvas;
    el._tabela = tabela;
    el._tempo = tempo;
    ligarPlanoAlfa(el);
    return el;
  }

  /** O menu do «+ sinal»: caixas de marcar, com o teto de três. */
  function abrirSinaisDoAlfa(painel) {
    const id = `menu-sinais-alfa-${painel.id}`;
    menuSuspenso(id, "sinais deste plano", (caixa) => {
      const meu = painelPorId(painel.id) || {};
      const atuais = (meu.sinais || []).slice();
      const cheio = atuais.length >= MAXIMO_NO_ALFA;
      for (const [chave, nome, origem] of SINAIS_DO_ALFA) {
        const tem = atuais.includes(chave);
        const linha = criar("label", "opcao");
        const marca = document.createElement("input");
        marca.type = "checkbox";
        marca.checked = tem;
        marca.disabled = !tem && cheio;
        linha.title = marca.disabled
          ? `Até ${MAXIMO_NO_ALFA} sinais por plano: tire um para pôr este.`
          : `${nome}: a razão entre o ${origem} dos dois terminais.`;
        marca.addEventListener("change", () => {
          const atual = painelPorId(painel.id);
          if (!atual) return;
          guardarParaDesfazer();
          const lista = (atual.sinais || []).filter((x) => x !== chave);
          if (marca.checked) lista.push(chave);
          // Na ordem do menu, e não na do clique: IA, IB, IC sempre na mesma
          // coluna da tabela.
          atual.sinais = SINAIS_DO_ALFA.map(([c]) => c).filter((c) => lista.includes(c));
          recarregar();
        });
        const cor = criar("i", "cor-do-alfa");
        cor.style.background = token(painel.sinais.find((s) => s.id === chave)?.cor
                                     || corDoAlfa(chave));
        linha.append(marca, cor, criar("span", null, nome),
                     criar("small", null, origem));
        caixa.append(linha);
      }
      caixa.append(criar("p", "nota-do-menu", "Cada sinal é a razão entre o "
        + "mesmo sinal dos dois terminais. Mais de três vira um novelo; para "
        + "comparar mais, crie outro plano."));
    });
  }

  //: A cor de um sinal que ainda não está no plano (o servidor só manda a dos
  //: que estão). A MESMA tabela de `plot/alfa.CORES`.
  const corDoAlfa = (chave) => ({ A: "--fase-a", B: "--fase-b", C: "--fase-c",
                                   "3I0": "--calculado-1", I2: "--calculado-2" })[chave];

  /** A engrenagem: escala, ponto cego e os dois ajustes da característica. */
  function ajustesDoAlfa(painel) {
    const meu = painelPorId(painel.id) || {};
    const emLog = meu.escala_alfa !== "linear";
    const escala = criar("span", "par-de-medidas");
    for (const [valor, rotulo] of [["log", "log"], ["linear", "linear"]]) {
      const b = criar("button", "medida" + ((valor === "log") === emLog ? " escolhido" : ""),
                      rotulo);
      b.type = "button";
      b.addEventListener("click", () => {
        const atual = painelPorId(painel.id);
        if (!atual) return;
        atual.escala_alfa = valor;
        desenharTudo();
        reabrirEngrenagem(painel.id);
      });
      escala.append(b);
    }
    const cego = meu.ponto_cego !== false;
    const botaoCego = criar("button", "medida" + (cego ? " escolhido" : ""),
                            cego ? "ponto cego: à vista" : "ponto cego: escondido");
    botaoCego.type = "button";
    botaoCego.addEventListener("click", () => {
      const atual = painelPorId(painel.id);
      if (!atual) return;
      atual.ponto_cego = !cego;
      desenharTudo();
      reabrirEngrenagem(painel.id);
    });

    /** Um ajuste numérico: campo e controle deslizante. O número só vai ao
     * servidor ao SOLTAR (`change`): a decisão de cada ponto é conta dele. */
    const numerico = (campo, minimo, maximo, passo, unidade) => {
      const caixa = criar("span", "ajuste-numerico");
      const valor = Number(painel[campo]);
      const texto = document.createElement("input");
      texto.type = "number";
      texto.min = minimo; texto.max = maximo; texto.step = passo;
      texto.value = String(valor);
      const deslizante = document.createElement("input");
      deslizante.type = "range";
      deslizante.min = minimo; deslizante.max = maximo; deslizante.step = passo;
      deslizante.value = String(valor);
      const aplicar = (cru) => {
        const n = Number(cru);
        if (!Number.isFinite(n)) return;
        const atual = painelPorId(painel.id);
        if (!atual) return;
        guardarParaDesfazer();
        atual[campo] = n;
        recarregar().then(() => reabrirEngrenagem(painel.id));
      };
      deslizante.addEventListener("input", () => { texto.value = deslizante.value; });
      deslizante.addEventListener("change", () => aplicar(deslizante.value));
      texto.addEventListener("change", () => aplicar(texto.value));
      caixa.append(texto, criar("span", "unidade-extra", unidade), deslizante);
      return caixa;
    };
    const explica = (texto) => criar("p", "nota-do-menu", texto);

    /** Qual trinca é o local e qual é o remoto. Vai ao servidor: muda o k. */
    const terminal = (campo, outro) => {
      const lista = document.createElement("select");
      lista.className = "escolha-de-trinca";
      const atual = painel[campo] ? painel[campo].rotulo : "";
      const doOutro = painel[outro] ? painel[outro].rotulo : "";
      for (const t of (painel.trincas || [])) {
        const opcao = document.createElement("option");
        opcao.value = t.rotulo;
        opcao.textContent = `${t.rotulo} · ${t.nome}`;
        opcao.selected = t.rotulo === atual;
        // A mesma trinca dos dois lados dá k = 1∠0° em todo ponto: nada a ver.
        opcao.disabled = t.rotulo === doOutro;
        lista.append(opcao);
      }
      lista.addEventListener("change", () => {
        const meuAgora = painelPorId(painel.id);
        if (!meuAgora) return;
        guardarParaDesfazer();
        meuAgora[campo] = lista.value;
        recarregar().then(() => reabrirEngrenagem(painel.id));
      });
      return lista;
    };
    const refino = criar("label", "opcao");
    const marcaDoRefino = document.createElement("input");
    marcaDoRefino.type = "checkbox";
    marcaDoRefino.checked = !!(painelPorId(painel.id) || {}).refinar;
    marcaDoRefino.addEventListener("change", () => {
      const atual = painelPorId(painel.id);
      if (!atual) return;
      guardarParaDesfazer();
      atual.refinar = marcaDoRefino.checked;
      recarregar().then(() => reabrirEngrenagem(painel.id));
    });
    refino.append(marcaDoRefino, criar("span", null, "refinar o ângulo pela pré-falta"));
    const doRefino = painel.entre_ieds ? [
      "dois registros",
      refino,
      explica("Gira o terminal do outro registro até a carga da pré-falta "
              + "atravessar a linha a 180°. Use quando os relógios não estão "
              + "sincronizados. Supõe uma pré-falta normal: em linha em vazio, "
              + "com tap ou fonte no meio, não serve."),
    ] : [];
    const terminais = (painel.trincas || []).length >= 2 ? [
      "local",
      terminal("local", "remoto"),
      "remoto",
      terminal("remoto", "local"),
      explica("Por padrão, a primeira e a segunda trinca de corrente do "
              + "arquivo. Troque quando o relé gravar os terminais em outra "
              + "ordem."),
    ] : [];
    return [
      ...terminais,
      ...doRefino,
      "escala do |k|",
      escala,
      explica("Log põe 1/8 e 8 à mesma distância do 1. Linear mostra o "
              + "tamanho real, mas espreme tudo abaixo de 1 no centro."),
      "ponto cego",
      botaoCego,
      explica("Hachura a faixa de ±20° em torno de 180° dentro da "
              + "restrição: é onde uma falta interna com outfeed se esconde."),
      "87LR",
      numerico("r87", 1.5, 20, 0.5, "raio"),
      explica("Raio externo da restrição; o interno é 1/87LR. Maior raio "
              + "tolera mais erro de TC antes de operar."),
      "87LANG",
      numerico("ang87", 90, 270, 5, "graus"),
      explica("Abertura do setor de bloqueio, centrado em 180°. Maior ângulo "
              + "tolera mais atraso de canal entre os terminais."),
    ];
  }

  /** A conta de |k| para pixel. A escala é da tela: muda o desenho, não o
   * número. */
  function mapaDoAlfa(painel, raio) {
    const meu = painelPorId(painel.id) || {};
    const r87 = Number(painel.r87) || 6;
    const emLog = meu.escala_alfa !== "linear";
    const topoLog = Math.log10(Math.max(r87 * 2.5, 10));
    const topoLinear = r87 * 1.25;
    const radial = (m) => {
      if (!(m > 0)) return 0;
      const f = emLog ? (Math.log10(m) + topoLog) / (2 * topoLog) : m / topoLinear;
      return Math.min(Math.max(f, 0), 1) * raio;
    };
    return { radial, emLog };
  }

  function pintarAlfa(bloco) {
    const canvas = bloco._canvas;
    const painel = bloco._painel;
    const lado = LADO_ALFA;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${lado}px`;
    canvas.style.height = `${lado}px`;
    dimensionar(canvas, Math.round(lado * dpr), Math.round(lado * dpr));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, lado, lado);

    const meu = painelPorId(painel.id) || {};
    const cx = lado / 2, cy = lado / 2;
    const raio = lado / 2 - FOLGA_ALFA;
    const { radial, emLog } = mapaDoAlfa(painel, raio);
    const r87 = Number(painel.r87) || 6;
    const meia = (Number(painel.ang87) || 195) / 2;
    const ponto = (m, graus) => [cx + radial(m) * Math.cos(graus * Math.PI / 180),
                                 cy - radial(m) * Math.sin(graus * Math.PI / 180)];

    // --- eixos, a coroa de restrição e o ponto cego ------------------------
    ctx.save();
    ctx.strokeStyle = token("--linha");
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - raio - 6, cy); ctx.lineTo(cx + raio + 6, cy);
    ctx.moveTo(cx, cy - raio - 6); ctx.lineTo(cx, cy + raio + 6);
    ctx.stroke();

    const setor = (m0, m1, a0, a1) => {
      ctx.beginPath();
      for (let a = a0; a <= a1 + 0.01; a += 2) {
        const q = ponto(m1, a);
        if (a === a0) ctx.moveTo(q[0], q[1]); else ctx.lineTo(q[0], q[1]);
      }
      for (let a = a1; a >= a0 - 0.01; a -= 2) {
        const q = ponto(m0, a);
        ctx.lineTo(q[0], q[1]);
      }
      ctx.closePath();
    };
    if (!painel.falta) {
      setor(1 / r87, r87, 180 - meia, 180 + meia);
      ctx.fillStyle = token("--bom");
      ctx.globalAlpha = 0.13;
      ctx.fill();
      ctx.globalAlpha = 0.85;
      ctx.strokeStyle = token("--bom");
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.globalAlpha = 1;
      if (meu.ponto_cego !== false) {
        ctx.save();
        setor(1 / r87, r87, 160, 200);
        ctx.clip();
        ctx.strokeStyle = token("--atencao");
        ctx.globalAlpha = 0.5;
        ctx.lineWidth = 1;
        for (let x = cx - raio * 2; x < cx + raio; x += 6) {
          ctx.beginPath();
          ctx.moveTo(x, cy + raio);
          ctx.lineTo(x + raio * 2, cy - raio);
          ctx.stroke();
        }
        ctx.restore();
      }
    }

    // Os anéis 1/R, 1 e R, tracejados e com o número.
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = token("--suave");
    ctx.fillStyle = token("--suave");
    ctx.font = "10px var(--mono), monospace";
    ctx.textBaseline = "bottom";
    ctx.textAlign = "left";
    const nomeR = formatar(r87, r87 % 1 ? 1 : 0);
    for (const [m, texto] of [[1 / r87, `1/${nomeR}`], [1, "1"], [r87, nomeR]]) {
      const r = radial(m);
      if (r < 2) continue;
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, 2 * Math.PI);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(texto, cx + r * 0.71 + 3, cy - r * 0.71 - 2);
    }
    ctx.setLineDash([]);
    ctx.textAlign = "right";
    ctx.fillText("real", cx + raio, cy - 4);
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText("imag", cx + 5, cy - raio);
    ctx.fillText(emLog ? "|k| log" : "|k| linear", 2, 2);
    ctx.textAlign = "right";
    ctx.fillText(painel.vista === "remoto" ? "k = local / remoto" : "k = remoto / local",
                 lado - 2, 2);
    ctx.restore();

    const k = meu.cursor === 2 ? 1 : 0;
    const tc = cursores[k];
    const cabeca = tc === null ? -1 : pontoNoInstante(painel, tc);
    const tempos = (painel.pontos && painel.pontos.t) || [];
    const f0 = dados.frequencia_hz || 60;
    const alvos = [];

    if (painel.falta) {
      ctx.save();
      ctx.fillStyle = token("--atencao");
      ctx.font = "600 12px var(--sans), sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("falta o terminal remoto", cx, cy - 26);
      ctx.fillStyle = token("--suave");
      ctx.font = "11.5px var(--sans), sans-serif";
      ctx.fillText("o registro só tem uma trinca de corrente", cx, cy - 10);
      ctx.restore();
    }

    // --- as trajetórias, até o cursor ---------------------------------------
    for (const s of (painel.sinais || [])) {
      const tr = (painel.trajetorias || {})[s.id];
      if (!tr) continue;
      const cor = token(s.cor);
      const xy = (i) => {
        const m = Math.hypot(tr.re[i], tr.im[i]);
        const a = Math.atan2(tr.im[i], tr.re[i]);
        return [cx + radial(m) * Math.cos(a), cy - radial(m) * Math.sin(a)];
      };
      ctx.save();
      ctx.strokeStyle = cor;
      ctx.lineWidth = 1.7;
      ctx.lineCap = "round";
      for (let i = 1; i <= cabeca; i += 1) {
        if (tr.re[i] === null || tr.re[i - 1] === null) continue;
        ctx.globalAlpha = PISO_DO_RASTRO + (1 - PISO_DO_RASTRO)
          * Math.pow(0.5, Math.max(0, (tc - tempos[i]) * f0) / MEIA_VIDA_DO_RASTRO);
        const a = xy(i - 1), b = xy(i);
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      if (cabeca >= 0 && tr.re[cabeca] !== null) {
        const q = xy(cabeca);
        ctx.beginPath();
        ctx.arc(q[0], q[1], 5, 0, 2 * Math.PI);
        ctx.fillStyle = cor;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = token("--superficie");
        ctx.stroke();
      }
      ctx.restore();
      for (let i = 0; i <= cabeca; i += 1) {
        if (tr.re[i] === null) continue;
        const q = xy(i);
        alvos.push({ x: q[0], y: q[1], i });
      }
    }
    bloco._alvos = alvos;

    if (tc === null && !painel.falta) {
      ctx.save();
      ctx.fillStyle = token("--suave");
      ctx.font = "11px var(--mono), monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`ponha o cursor ${k + 1} (tecla ${k + 1} sobre a onda)`, 4, 16);
      ctx.restore();
    }
    escreverTabelaDoAlfa(bloco, cabeca, tc);
  }

  /** A tabela da variação A: uma coluna por sinal, uma linha por grandeza. */
  function escreverTabelaDoAlfa(bloco, cabeca, tc) {
    const painel = bloco._painel;
    const tabela = bloco._tabela;
    const sinais = painel.sinais || [];
    tabela.replaceChildren();
    if (!sinais.length || painel.falta) {
      tabela.hidden = true;
      bloco._tempo.textContent = "";
      return;
    }
    tabela.hidden = false;
    const thead = criar("thead");
    const cabecaDaTabela = criar("tr");
    cabecaDaTabela.append(criar("th", "unidade", "sinal"));
    for (const s of sinais) {
      const th = criar("th", "coluna-do-alfa");
      const bolinha = criar("i", "cor-do-alfa");
      bolinha.style.background = token(s.cor);
      th.append(bolinha, criar("span", null, s.sinal));
      th.style.color = token(s.cor);
      cabecaDaTabela.append(th);
    }
    thead.append(cabecaDaTabela);
    const tbody = criar("tbody");
    const lido = (s) => {
      const tr = (painel.trajetorias || {})[s.id];
      return tr && cabeca >= 0 ? tr : null;
    };
    const linha = (rotulo, valor, classe, dica) => {
      const l = criar("tr");
      const th = criar("th", null, rotulo);
      if (dica) th.title = dica;
      l.append(th);
      for (const s of sinais) {
        const tr = lido(s);
        const texto = tr ? valor(tr) : null;
        const td = criar("td", texto === null ? "vazio-valor" : (classe ? classe(tr) : ""),
                         texto === null ? "—" : texto);
        l.append(td);
      }
      tbody.append(l);
    };
    const num = (v, casas = 3) => (v === null || v === undefined ? null : formatar(v, casas));
    const visto = painel.vista === "remoto" ? "loc/rem" : "rem/loc";
    linha(`|k| ${visto}`, (tr) => num(tr.modulo[cabeca]));
    linha("∠k", (tr) => (tr.angulo[cabeca] === null ? null
                          : `${formatar(tr.angulo[cabeca], 1, false)}°`));
    linha("I local (pu)", (tr) => num(tr.loc_pu[cabeca]),
          null, "Em pu da nominal do TC do terminal local.");
    linha("I remoto (pu)", (tr) => (tr.rem_pu[cabeca] === null ? null
          : `${formatar(tr.rem_pu[cabeca], 3)}`
            + (tr.rem_ang[cabeca] === null ? ""
               : ` ∠ ${formatar(tr.rem_ang[cabeca], 1, false)}°`)),
          null, "Em pu da nominal do TC do terminal remoto; o ângulo é "
                + "contado do I local do mesmo sinal.");
    linha("decisão", (tr) => tr.decisao[cabeca] || null,
          (tr) => ({ restringe: "decisao-restringe", opera: "decisao-opera" })[
            tr.decisao[cabeca]] || "decisao-sem");
    tabela.append(thead, tbody);
    bloco._tempo.textContent = tc === null ? ""
      : `t = ${formatar(paraMs(painel.pontos.t[cabeca] ?? tc), 1, false)} ms`;
  }

  /** O clique no plano leva o cursor ao ponto mais perto de qualquer sinal. */
  function ligarPlanoAlfa(bloco) {
    const canvas = bloco._canvas;
    canvas.addEventListener("pointerdown", (evento) => {
      evento.stopPropagation();
      if (evento.button !== 0) return;
      const r = canvas.getBoundingClientRect();
      const x = evento.clientX - r.left;
      const y = evento.clientY - r.top;
      let melhor = null;
      let menor = PEGADA_DO_RASTRO * PEGADA_DO_RASTRO;
      for (const a of (bloco._alvos || [])) {
        const d = (a.x - x) ** 2 + (a.y - y) ** 2;
        if (d <= menor) { menor = d; melhor = a; }
      }
      if (!melhor) return;
      const painel = bloco._painel;
      const meu = painelPorId(painel.id) || {};
      porCursor(meu.cursor === 2 ? 1 : 0, painel.pontos.t[melhor.i]);
      repintar();
    });
    canvas.addEventListener("wheel", (evento) => evento.stopPropagation());
  }

  // --- o diferencial de transformador (87T) ----------------------------------
  //
  // Iop × Irt, fase por fase, andando até o cursor. Tudo vem pronto de
  // `plot/diferencial.py`: os ajustes com o estado de cada um, a curva da
  // característica, os limites dos eixos e, para cada ponto, Iop, Irt, o
  // limiar, a 2ª e a 5ª e a DECISÃO. A tela escolhe o ponto do cursor e pinta.
  // Escolha dele, 22/10/2026: o layout 01 da maquete (Iop × Irt com tabela) e
  // a caixa flutuante no botão «ajustes» — sem engrenagem, sem resumo no
  // cabeçalho. Sem todos os ajustes, NÃO há gráfico: há o quadro do que falta.

  //: A altura do quadro, em pixels de CSS. A largura é a da coluna.
  const ALTURA_DIFERENCIAL = 300;
  const MARGEM_DIFERENCIAL = { esq: 46, dir: 14, topo: 14, baixo: 26 };

  //: O nome de cada estado de ajuste, como a caixa escreve.
  const NOME_DO_ESTADO_87 = {
    coletado: "coletado", suspeito: "suspeito", falta: "não coletado",
    digitado: "digitado", deduzido: "deduzido",
  };
  //: A classe de cor de cada decisão, na tabela.
  const DECISAO_87 = {
    restringe: "decisao-restringe", opera: "decisao-opera",
    "opera 87U": "decisao-opera", "bloqueado 2ª": "decisao-bloqueado",
    "bloqueado 5ª": "decisao-bloqueado",
  };

  function blocoDiferencial(painel) {
    const el = criar("section", "grafico diferencial");
    const meu = painelPorId(painel.id) || {};
    const qual = meu.cursor === 2 ? 2 : 1;

    const botaoCursor = criar("button", "medida", `cursor ${qual}`);
    botaoCursor.type = "button";
    botaoCursor.title = `O ponto anda até o cursor ${qual}. Clique para passar `
                      + "para o outro.";
    botaoCursor.addEventListener("click", () => alternarCursorDoPainel(painel.id));

    // Os dois lados: cada metade abre a lista das trincas de corrente. A
    // ordem do arquivo é só o padrão.
    const par = criar("span", "par-de-medidas");
    const ancoras = [];
    for (const [lado, campo] of [["1", "lado1"], ["2", "lado2"]]) {
      const grupo = painel[campo];
      const b = criar("button", "medida", `lado ${lado}${grupo ? ` · ${grupo.rotulo}` : ""}`);
      b.type = "button";
      b.title = grupo ? `Lado ${lado}: ${grupo.nome}. Clique para escolher outra trinca.`
                      : "Este registro não tem a trinca deste lado.";
      b.disabled = !grupo;
      const ancora = criar("span", "ancora-de-menu");
      ancora.id = `menu-lado${lado}-dif-${painel.id}`;
      b.addEventListener("click", () => abrirLadoDoDiferencial(painel, lado));
      par.append(b);
      ancoras.push(ancora);
    }

    const ancoraSinais = criar("span", "ancora-de-menu");
    ancoraSinais.id = `menu-sinais-dif-${painel.id}`;
    const mais = criar("button", "medida", "+ sinal");
    mais.type = "button";
    mais.title = "Escolher as fases que aparecem no plano.";
    mais.addEventListener("click", () => abrirSinaisDoDiferencial(painel));

    // O botão de AJUSTES: só o texto. O que foi lido, deduzido ou digitado
    // mora dentro da caixa (pedido dele, 22/10/2026).
    const ancoraAjustes = criar("span", "ancora-de-menu");
    ancoraAjustes.id = `ancora-ajustes-dif-${painel.id}`;
    const ajustes = criar("button", "medida", "ajustes");
    ajustes.type = "button";
    ajustes.setAttribute("aria-haspopup", "true");
    ajustes.title = "Os ajustes do 87T: lidos do arquivo, deduzidos ou digitados.";
    ajustes.addEventListener("click", () => abrirAjustesDoDiferencial(painel));

    el.append(cabecalhoDoPainel(painel, [
      botaoCursor, par, ...ancoras, mais, ancoraSinais, ajustes, ancoraAjustes,
    ]));

    const corpo = criar("div", "grafico-corpo diferencial");
    const caixa = criar("div", "tela tela-diferencial");
    const canvas = document.createElement("canvas");
    const lado = criar("div", "lado-diferencial");
    const tabela = criar("table", "mini alfa-tabela dif-tabela");
    const tempo = criar("div", "tempo-do-alfa");
    lado.append(tabela, tempo);
    tabela.hidden = !painel.pronto || !!painel.falta;

    if (painel.falta) {
      caixa.append(quadroDosAjustes87(painel, painel.falta, null));
    } else if (!painel.pronto) {
      const nomes = (painel.faltam || []).map((x) => x.rotulo
        + (x.estado === "suspeito" ? " (suspeito: aceite ou corrija)" : ""));
      caixa.append(quadroDosAjustes87(
        painel, `Faltam ${nomes.length} ajuste${nomes.length === 1 ? "" : "s"} `
          + `para desenhar: ${nomes.join(", ")}.`,
        (painel.faltam || [])[0] || null));
    } else {
      caixa.append(canvas);
      const equacoes = criar("div", "equacoes-do-diferencial",
        `${painel.equacoes.iop} · ${painel.equacoes.irt}`);
      equacoes.title = "As equações em uso. Troque na caixa de ajustes, "
                     + "grupo «cálculo».";
      caixa.append(equacoes);
    }
    corpo.append(caixa, lado);
    el.append(corpo);
    comMolduras(el, corpo);
    for (const m of el._molduras) m.so = qual - 1;

    const pe = criar("div", "rodape-do-painel");
    for (const texto of (painel.rodape || [])) pe.append(criar("div", null, texto));
    pe.hidden = !pe.children.length;
    el.append(pe);

    el._painel = painel;
    el._canvas = painel.pronto && !painel.falta ? canvas : null;
    el._tabela = tabela;
    el._tempo = tempo;
    if (el._canvas) ligarPlanoDiferencial(el);
    return el;
  }

  /** O quadro que ocupa o lugar do gráfico quando falta algo. */
  function quadroDosAjustes87(painel, texto, primeiro) {
    const q = criar("div", "faltam-ajustes");
    q.style.minHeight = `${ALTURA_DIFERENCIAL}px`;
    q.append(criar("p", null, texto));
    if (painel.nota) q.append(criar("p", "nota-do-quadro", painel.nota));
    if (primeiro) {
      const b = criar("button", "medida", `preencher «${primeiro.rotulo}»`);
      b.type = "button";
      b.addEventListener("click", () => abrirAjustesDoDiferencial(painel, primeiro.id));
      q.append(b);
    }
    return q;
  }

  /** A escolha da trinca de um lado. */
  function abrirLadoDoDiferencial(painel, lado) {
    const campo = lado === "1" ? "local" : "remoto";
    const outro = lado === "1" ? painel.lado2 : painel.lado1;
    const atual = lado === "1" ? painel.lado1 : painel.lado2;
    menuSuspenso(`menu-lado${lado}-dif-${painel.id}`, `lado ${lado} do trafo`, (caixa) => {
      for (const t of (painel.trincas || [])) {
        const linha = criar("label", "opcao");
        const marca = document.createElement("input");
        marca.type = "radio";
        marca.name = `lado${lado}-${painel.id}`;
        marca.checked = !!atual && atual.rotulo === t.rotulo;
        // A mesma trinca dos dois lados daria Iop = 2·I em tudo: nada a ver.
        marca.disabled = !!outro && outro.rotulo === t.rotulo;
        linha.title = marca.disabled ? "Esta trinca já é o outro lado." : t.nome;
        marca.addEventListener("change", () => {
          const meu = painelPorId(painel.id);
          if (!meu) return;
          guardarParaDesfazer();
          meu[campo] = t.rotulo;
          recarregar();
        });
        linha.append(marca, criar("span", null, `${t.rotulo} · ${t.nome}`));
        caixa.append(linha);
      }
    });
  }

  /** As fases do plano: caixas de marcar, ao menos uma. */
  function abrirSinaisDoDiferencial(painel) {
    menuSuspenso(`menu-sinais-dif-${painel.id}`, "fases deste plano", (caixa) => {
      const meu = painelPorId(painel.id) || {};
      const atuais = (meu.sinais || []).slice();
      for (const [chave, nome] of [["A", "IA"], ["B", "IB"], ["C", "IC"]]) {
        const tem = atuais.includes(chave);
        const linha = criar("label", "opcao");
        const marca = document.createElement("input");
        marca.type = "checkbox";
        marca.checked = tem;
        marca.disabled = tem && atuais.length === 1;
        linha.title = marca.disabled ? "Ao menos uma fase fica no plano." : nome;
        marca.addEventListener("change", () => {
          const atual = painelPorId(painel.id);
          if (!atual) return;
          guardarParaDesfazer();
          const lista = (atual.sinais || []).filter((x) => x !== chave);
          if (marca.checked) lista.push(chave);
          atual.sinais = ["A", "B", "C"].filter((c) => lista.includes(c));
          recarregar();
        });
        const cor = criar("i", "cor-do-alfa");
        cor.style.background = token(`--fase-${chave.toLowerCase()}`);
        linha.append(marca, cor, criar("span", null, nome));
        caixa.append(linha);
      }
    });
  }

  /** A caixa de ajustes, flutuante (como a do plano de impedância).
   *
   * Cada ajuste com o seu estado: coletado (com a variável do relé e o texto
   * lido), suspeito (com o motivo e as ações), não coletado, digitado,
   * deduzido. Mexer num campo vai ao servidor — é ele quem resolve os
   * estados e refaz a conta — e a caixa é refeita com a resposta. */
  function abrirAjustesDoDiferencial(painel, focar = null) {
    const ancoraId = `ancora-ajustes-dif-${painel.id}`;
    const mesmo = ajustesAbertos && ajustesAbertos.painel === painel.id;
    fecharAjustes();
    if (mesmo && !focar) return;             // o botão que abre também fecha

    const meu = painelPorId(painel.id);
    if (!meu) return;
    if (!meu.ajustes87) meu.ajustes87 = {};
    const guardado = meu.ajustes87;
    if (!guardado.valores) guardado.valores = {};
    if (!guardado.aceitos) guardado.aceitos = [];

    // Refaz a caixa com o pacote NOVO, que traz os estados resolvidos.
    const refazer = (focoId) => {
      recarregar().then(() => {
        const novo = (dados.paineis || []).find((x) => x.id === painel.id);
        if (novo) abrirAjustesDoDiferencial(novo, focoId || "__manter__");
      });
    };

    const caixa = criar("div", "menu-suspenso ajustes-do-plano ajustes-87");
    caixa.append(criar("p", "cabeca-menu", "ajustes do diferencial"));
    if (painel.nota) caixa.append(criar("p", "nota-do-menu", painel.nota));
    caixa.append(criar("p", "nota-do-menu", painel.fabricante
      ? `Relé ${painel.fabricante}: o que o arquivo trouxe aparece com a `
        + "variável dele; o resto se digita."
      : "Fabricante não identificado: digite os ajustes."));

    // O placar e a legenda dos estados — dentro da caixa, não no cabeçalho.
    const placar = criar("div", "placar-87");
    for (const e of ["coletado", "suspeito", "falta", "digitado", "deduzido"]) {
      const n = (painel.placar || {})[e] || 0;
      if (!n) continue;
      placar.append(criar("span", `estado-87 ${e}`, `${n} ${NOME_DO_ESTADO_87[e]}`));
    }
    caixa.append(placar);

    let grupoAtual = "";
    let alvoDoFoco = null;
    for (const c of (painel.ajustes || [])) {
      if (c.grupo !== grupoAtual) {
        grupoAtual = c.grupo;
        caixa.append(criar("div", "titulo-de-grupo", c.grupo));
        if (c.grupo === "característica") {
          caixa.append(criar("p", "nota-do-menu",
            "A forma da curva é de cada fabricante. Os ajustes que a forma "
            + "escolhida não usa ficam marcados «não usado»."
            + (painel.slopes === 1 ? " Esta é de UM slope." : "")));
        }
        if (c.grupo === "cálculo") {
          caixa.append(criar("p", "equacao-87",
            `${painel.equacoes.iop}   ·   ${painel.equacoes.irt}`));
        }
      }
      const linha = criar("div", `ajuste-87 ${c.estado}`);
      linha.dataset.id = c.id;
      const rotulo = criar("span", "rotulo-87", c.rotulo);
      rotulo.title = c.dica || "";
      if (c.variavel) rotulo.append(criar("small", "variavel-87", ` ← ${c.variavel}`));

      let campo;
      if (c.tipo === "op") {
        campo = document.createElement("select");
        if (c.valor === null || c.valor === undefined) {
          const vazio = document.createElement("option");
          vazio.value = "";
          vazio.textContent = "escolha";
          campo.append(vazio);
        }
        for (const [v, r] of (c.opcoes || [])) {
          const o = document.createElement("option");
          o.value = v;
          o.textContent = r;
          o.selected = String(c.valor) === v;
          campo.append(o);
        }
      } else {
        campo = document.createElement("input");
        campo.type = "text";
        campo.inputMode = "decimal";
        campo.placeholder = "digite";
        campo.value = c.valor === null || c.valor === undefined
          ? "" : formatar(c.valor, Math.abs(c.valor) < 10 ? 3 : 2);
      }
      campo.className = "campo-87";
      campo.addEventListener("change", () => {
        const bruto = campo.value;
        if (bruto === "") delete guardado.valores[c.id];
        else if (c.tipo === "op") guardado.valores[c.id] = bruto;
        else {
          const n = numeroDigitado(bruto);
          if (n === null) return;
          guardado.valores[c.id] = n;
        }
        refazer(c.id);
      });
      if (focar && focar === c.id) alvoDoFoco = campo;

      const opcional = (painel.nao_usados || []).includes(c.id);
      const emBrancoPodeFicar = c.estado === "falta" && (painel.opcionais || []).includes(c.id);
      const chip = opcional || emBrancoPodeFicar
        ? criar("span", "estado-87 falta", opcional ? "não usado" : "opcional")
        : criar("span", `estado-87 ${c.estado}`, NOME_DO_ESTADO_87[c.estado]);
      linha.append(rotulo, campo, criar("span", "unidade-87", c.unidade || ""), chip);

      // A segunda linha: o texto lido, o motivo da suspeita, ou a conta.
      const sub = criar("div", "sub-87");
      if (c.bruto) sub.append(criar("code", null, c.bruto));
      if (c.estado === "deduzido" && c.como) sub.append(criar("span", null, c.como));
      if (c.motivo) sub.append(criar("span", "motivo-87", c.motivo));
      if (c.estado === "suspeito") {
        const aceitar = criar("button", "medida", "aceitar assim");
        aceitar.type = "button";
        aceitar.addEventListener("click", () => {
          if (!guardado.aceitos.includes(c.id)) guardado.aceitos.push(c.id);
          refazer(c.id);
        });
        sub.append(aceitar);
        if (c.sugestao) {
          const usar = criar("button", "medida", c.sugestao.texto);
          usar.type = "button";
          usar.addEventListener("click", () => {
            guardado.valores[c.id] = c.sugestao.valor;
            refazer(c.id);
          });
          sub.append(usar);
        }
      }
      if (sub.children.length) linha.append(sub);
      caixa.append(linha);
    }

    const limpar = criar("button", "medida largo", "voltar ao do arquivo");
    limpar.type = "button";
    limpar.disabled = !Object.keys(guardado.valores).length && !guardado.aceitos.length;
    limpar.title = "Apaga o que foi digitado e aceito aqui e volta ao que o "
                 + "arquivo trouxe (ou ao deduzido).";
    limpar.addEventListener("click", () => {
      meu.ajustes87 = {};
      fecharAjustes();
      recarregar();
    });
    const pe = criar("div", "linha-de-ajuste");
    pe.append(limpar);
    caixa.append(pe);

    // Pendurada no corpo, como a do plano: a resposta do servidor refaz o
    // painel inteiro, e um menu dentro dele sumiria a cada número.
    document.body.append(caixa);
    const posicionar = () => {
      const ancora = document.getElementById(ancoraId);
      const gatilho = ancora && ancora.previousElementSibling;
      if (!gatilho) { fecharAjustes(); return; }
      const r = gatilho.getBoundingClientRect();
      const larg = caixa.offsetWidth;
      const esq = Math.max(8, Math.min(window.innerWidth - larg - 8, r.left));
      caixa.style.left = `${esq}px`;
      caixa.style.top = `${Math.min(r.bottom + 6, window.innerHeight - 120)}px`;
      caixa.style.maxHeight = `${Math.max(200, window.innerHeight - r.bottom - 16)}px`;
    };
    const aoApontar = (e) => {
      if (caixa.contains(e.target)) return;
      const ancora = document.getElementById(ancoraId);
      const gatilho = ancora && ancora.previousElementSibling;
      if (gatilho && gatilho.contains(e.target)) return;
      // O botão «preencher» do quadro também abre a caixa: não a fecha.
      if (e.target.closest && e.target.closest(".faltam-ajustes")) return;
      fecharAjustes();
    };
    document.addEventListener("pointerdown", aoApontar, true);
    window.addEventListener("resize", posicionar);
    window.addEventListener("scroll", posicionar, true);
    ajustesAbertos = { painel: painel.id, caixa, posicionar, aoApontar };
    posicionar();
    if (alvoDoFoco) {
      alvoDoFoco.scrollIntoView({ block: "nearest" });
      alvoDoFoco.focus();
    }
  }

  function pintarDiferencial(bloco) {
    const canvas = bloco._canvas;
    const painel = bloco._painel;
    if (!canvas || !painel.pronto) { escreverTabelaDoDiferencial(bloco, -1, null); return; }
    // Medido do PAI, como o espectro: a coluna é `minmax(0, 1fr)` de uma
    // grade, e a largura dela não depende do canvas.
    const larg = canvas.parentElement.clientWidth || 600;
    const alt = ALTURA_DIFERENCIAL;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${larg}px`;
    canvas.style.height = `${alt}px`;
    dimensionar(canvas, Math.round(larg * dpr), Math.round(alt * dpr));
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, larg, alt);

    const m = MARGEM_DIFERENCIAL;
    const x0 = m.esq, y0 = alt - m.baixo;
    const largura = larg - m.esq - m.dir, altura = y0 - m.topo;
    if (largura < 60) return;
    const eixoIrt = painel.eixos.irt, eixoIop = painel.eixos.iop;
    const X = (v) => x0 + largura * Math.min(Math.max(v, 0), eixoIrt) / eixoIrt;
    const Y = (v) => y0 - altura * Math.min(Math.max(v, 0), eixoIop) / eixoIop;

    ctx.save();
    // As duas regiões: opera por cima de tudo, restringe debaixo da curva.
    ctx.fillStyle = token("--ruim");
    ctx.globalAlpha = 0.09;
    ctx.fillRect(x0, m.topo, largura, altura);
    const curvaIrt = painel.curva.irt, curvaIop = painel.curva.iop;
    ctx.beginPath();
    ctx.moveTo(X(0), y0);
    curvaIrt.forEach((v, i) => ctx.lineTo(X(v), Y(curvaIop[i])));
    ctx.lineTo(X(eixoIrt), y0);
    ctx.closePath();
    ctx.fillStyle = token("--bom");
    ctx.globalAlpha = 0.16;
    ctx.fill();
    ctx.globalAlpha = 1;

    // A grade e os números dos eixos.
    ctx.strokeStyle = token("--linha");
    ctx.fillStyle = token("--suave");
    ctx.lineWidth = 1;
    ctx.font = "10.5px var(--mono), monospace";
    for (let k = 0; k <= 4; k += 1) {
      const vx = eixoIrt * k / 4, vy = eixoIop * k / 4;
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      ctx.moveTo(X(vx), m.topo); ctx.lineTo(X(vx), y0);
      ctx.moveTo(x0, Y(vy)); ctx.lineTo(x0 + largura, Y(vy));
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(formatar(vx, vx % 1 ? 1 : 0), X(vx), y0 + 5);
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(formatar(vy, vy % 1 ? 1 : 0), x0 - 6, Y(vy));
    }

    // A curva da característica.
    ctx.strokeStyle = token("--tinta");
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    curvaIrt.forEach((v, i) => (i ? ctx.lineTo(X(v), Y(curvaIop[i]))
                                  : ctx.moveTo(X(v), Y(curvaIop[i]))));
    ctx.stroke();

    // As marcas: o breakpoint e o 87U, quando cabem.
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = token("--suave");
    ctx.fillStyle = token("--suave");
    ctx.textBaseline = "top";
    for (const [chave, nome, dy] of [["bp1", "breakpoint 1", 2], ["bp2", "breakpoint 2", 16]]) {
      const bp = painel.marcas[chave];
      if (!(bp > 0) || bp > eixoIrt) continue;
      ctx.beginPath(); ctx.moveTo(X(bp), m.topo); ctx.lineTo(X(bp), y0); ctx.stroke();
      ctx.textAlign = "left";
      ctx.fillText(`${nome} = ${formatar(bp, 1)}`, X(bp) + 4, m.topo + dy);
    }
    const u87 = painel.marcas.u87;
    if (u87 > 0 && u87 <= eixoIop) {
      ctx.strokeStyle = token("--ruim");
      ctx.beginPath(); ctx.moveTo(x0, Y(u87)); ctx.lineTo(x0 + largura, Y(u87)); ctx.stroke();
      ctx.fillStyle = token("--ruim");
      ctx.textAlign = "right";
      ctx.fillText(`87U = ${formatar(u87, 1)}`, x0 + largura - 4, Y(u87) + 3);
    }
    ctx.setLineDash([]);
    ctx.textAlign = "left";
    ctx.fillStyle = token("--suave");
    ctx.fillText("Iop (pu)", x0 + 4, m.topo + 2);
    ctx.fillStyle = token("--ruim");
    ctx.fillText("opera", x0 + 4, m.topo + 16);
    ctx.textAlign = "right";
    ctx.textBaseline = "bottom";
    ctx.fillStyle = token("--bom");
    ctx.fillText("restringe", x0 + largura - 4, y0 - 16);
    ctx.fillStyle = token("--suave");
    ctx.fillText("Irt (pu)", x0 + largura - 4, y0 - 3);
    ctx.restore();

    // As trajetórias, até o cursor.
    const meu = painelPorId(painel.id) || {};
    const k = meu.cursor === 2 ? 1 : 0;
    const tc = cursores[k];
    const cabeca = tc === null ? -1 : pontoNoInstante(painel, tc);
    const tempos = (painel.pontos && painel.pontos.t) || [];
    const f0 = dados.frequencia_hz || 60;
    const alvos = [];
    for (const s of (painel.sinais || [])) {
      const tr = (painel.trajetorias || {})[s.id];
      if (!tr) continue;
      const cor = token(s.cor);
      ctx.save();
      ctx.strokeStyle = cor;
      ctx.lineWidth = 1.7;
      ctx.lineCap = "round";
      for (let i = 1; i <= cabeca; i += 1) {
        if (tr.iop[i] === null || tr.iop[i - 1] === null) continue;
        ctx.globalAlpha = PISO_DO_RASTRO + (1 - PISO_DO_RASTRO)
          * Math.pow(0.5, Math.max(0, (tc - tempos[i]) * f0) / MEIA_VIDA_DO_RASTRO);
        ctx.beginPath();
        ctx.moveTo(X(tr.irt[i - 1]), Y(tr.iop[i - 1]));
        ctx.lineTo(X(tr.irt[i]), Y(tr.iop[i]));
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      if (cabeca >= 0 && tr.iop[cabeca] !== null) {
        ctx.beginPath();
        ctx.arc(X(tr.irt[cabeca]), Y(tr.iop[cabeca]), 5, 0, 2 * Math.PI);
        ctx.fillStyle = cor;
        ctx.fill();
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = token("--superficie");
        ctx.stroke();
      }
      ctx.restore();
      for (let i = 0; i <= cabeca; i += 1) {
        if (tr.iop[i] === null) continue;
        alvos.push({ x: X(tr.irt[i]), y: Y(tr.iop[i]), i });
      }
    }
    bloco._alvos = alvos;

    if (tc === null) {
      ctx.save();
      ctx.fillStyle = token("--suave");
      ctx.font = "11px var(--mono), monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`ponha o cursor ${k + 1} (tecla ${k + 1} sobre a onda)`,
                   x0 + 4, m.topo + 32);
      ctx.restore();
    }
    escreverTabelaDoDiferencial(bloco, cabeca, tc);
  }

  /** A tabela do layout 01: uma coluna por fase, uma linha por grandeza. */
  function escreverTabelaDoDiferencial(bloco, cabeca, tc) {
    const painel = bloco._painel;
    const tabela = bloco._tabela;
    const sinais = painel.sinais || [];
    tabela.replaceChildren();
    if (!sinais.length || !painel.pronto || painel.falta) {
      tabela.hidden = true;
      bloco._tempo.textContent = "";
      return;
    }
    tabela.hidden = false;
    const thead = criar("thead");
    const topo = criar("tr");
    topo.append(criar("th", "unidade", "fase"));
    for (const s of sinais) {
      const th = criar("th", "coluna-do-alfa");
      const bolinha = criar("i", "cor-do-alfa");
      bolinha.style.background = token(s.cor);
      th.append(bolinha, criar("span", null, s.sinal));
      topo.append(th);
    }
    thead.append(topo);
    const tbody = criar("tbody");
    const linha = (rotulo, valor, classe, dica) => {
      const l = criar("tr");
      const th = criar("th", null, rotulo);
      if (dica) th.title = dica;
      l.append(th);
      for (const s of sinais) {
        const tr = (painel.trajetorias || {})[s.id];
        const texto = tr && cabeca >= 0 ? valor(tr) : null;
        l.append(criar("td", texto === null ? "vazio-valor" : (classe ? classe(tr) : ""),
                       texto === null ? "—" : texto));
      }
      tbody.append(l);
    };
    const num = (v, casas = 3) => (v === null || v === undefined ? null : formatar(v, casas));
    linha("Iop (pu)", (tr) => num(tr.iop[cabeca]), null, painel.equacoes.iop);
    linha("Irt (pu)", (tr) => num(tr.irt[cabeca]), null, painel.equacoes.irt);
    linha("limiar (pu)", (tr) => num(tr.limiar[cabeca]), null,
          "A Iop que a característica exige, nesta Irt.");
    linha("2ª (% Iop)", (tr) => num(tr.h2[cabeca], 1), null,
          "2ª harmônica da corrente DIFERENCIAL, em % da fundamental dela.");
    linha("5ª (% Iop)", (tr) => num(tr.h5[cabeca], 1), null,
          "5ª harmônica da corrente diferencial, em % da fundamental dela.");
    linha("decisão", (tr) => tr.decisao[cabeca] || null,
          (tr) => DECISAO_87[tr.decisao[cabeca]] || "decisao-sem");
    tabela.append(thead, tbody);
    bloco._tempo.textContent = tc === null ? ""
      : `t = ${formatar(paraMs(painel.pontos.t[cabeca] ?? tc), 1, false)} ms`;
  }

  /** O clique no plano leva o cursor ao ponto mais perto de qualquer fase. */
  function ligarPlanoDiferencial(bloco) {
    const canvas = bloco._canvas;
    canvas.addEventListener("pointerdown", (evento) => {
      evento.stopPropagation();
      if (evento.button !== 0) return;
      const r = canvas.getBoundingClientRect();
      const x = evento.clientX - r.left;
      const y = evento.clientY - r.top;
      let melhor = null;
      let menor = PEGADA_DO_RASTRO * PEGADA_DO_RASTRO;
      for (const a of (bloco._alvos || [])) {
        const d = (a.x - x) ** 2 + (a.y - y) ** 2;
        if (d <= menor) { menor = d; melhor = a; }
      }
      if (!melhor) return;
      const painel = bloco._painel;
      const meu = painelPorId(painel.id) || {};
      porCursor(meu.cursor === 2 ? 1 : 0, painel.pontos.t[melhor.i]);
      repintar();
    });
    canvas.addEventListener("wheel", (evento) => evento.stopPropagation());
  }

  function pintarFasorial(canvas, painel) {
    // Tamanho FIXO, e não medido do pai. Medir era um laço: o quadro se ajusta
    // ao canvas (`flex: 0 0 auto`) e o canvas se ajustava ao quadro, então
    // cada desenho mudava a largura do seguinte e o painel nunca parava quieto.
    const lado = 2 * (RAIO_FASORIAL + FOLGA_FASORIAL);
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${lado}px`;
    canvas.style.height = `${lado}px`;
    dimensionar(canvas, Math.round(lado * dpr), Math.round(lado * dpr));

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, lado, lado);

    const cx = lado / 2;
    const cy = lado / 2;
    const raio = lado / 2 - FOLGA_FASORIAL;
    if (raio <= 10) return;

    const meu = painelPorId(painel.id) || {};
    const comEscala = !!meu.escala;
    const fasores = fasoresDoPainel(painel);
    if (!fasores.length && (painel.sinais || []).length) {
      // Sem cursor não há instante, e sem instante não há fasor. Dizer isso
      // no meio do círculo é melhor que um círculo vazio, que se lê como
      // defeito.
      ctx.save();
      ctx.fillStyle = token("--suave");
      ctx.font = "11px var(--mono), monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`ponha o cursor ${meu.cursor === 2 ? 2 : 1} num gráfico`,
                   cx, cy - 8);
      ctx.fillText("(tecla 1 ou 2 sobre a onda)", cx, cy + 8);
      ctx.restore();
      pintarRosaDosVentos(ctx, cx, cy, raio, null);
      return;
    }
    const limites = reguasDoPainel(fasores);

    const aneis = pintarRosaDosVentos(ctx, cx, cy, raio,
                                      comEscala ? limites : null);

    const util = raio * OCUPACAO;
    const visiveis = [];
    let temTravada = false;
    for (const x of fasores) {
      const regua = limites.get(grandezaDoSinal(x.sinal));
      const limite = regua ? regua.limite : 1;
      if (x.sinal.sem_sinal || Math.abs(x.pu) / limite < RUIDO_DA_SETA) continue;
      if (!comEscala) {
        // Sem escala, toda seta vai ao raio: o que o diagrama mostra é
        // ângulo, e comprimento diferente ali só desviaria o olho.
        visiveis.push({ ...x, comprimento: util, real: util, fora: false });
        continue;
      }
      const real = Math.min(Math.abs(x.pu) / limite, 1) * util;
      const fora = real < util * MINIMO_DA_SETA;
      if (fora) temTravada = true;
      visiveis.push({ ...x, real,
                      comprimento: fora ? util * MINIMO_DA_SETA : real, fora });
    }
    for (const x of visiveis) {
      desenharSeta(ctx, cx, cy, x.comprimento, x.angulo,
                   corDoSinal(x.sinal, painel),
                   escolhidoNoPainel(painel, x.sinal) ? 3 : 2,
                   x.fora ? x.real : 0);
    }
    const ocupados = pintarLegendaDasReguas(
      ctx, cx, cy, raio, comEscala ? limites : null, aneis, visiveis);
    pintarNomesDosFasores(ctx, cx, cy, raio, visiveis, painel,
                          temTravada, ocupados);
  }

  /** Uma régua por GRANDEZA, tirada do REGISTRO INTEIRO.
   *
   * Régua única era o erro de origem do desenho. Numa falta monofásica a
   * corrente vai a 8 pu e a tensão da fase com defeito cai a 0,35 pu: 23
   * vezes. Com uma régua só, cinco das seis setas travam no mínimo e o
   * diagrama vira um emaranhado no centro.
   *
   * E essa disparidade é ARTIFICIAL: comparar o comprimento de um volt com o
   * de um ampère não significa nada: é o pu nominal que dá a ilusão de que
   * significa, porque numa falta ele é grande para corrente e pequeno para
   * tensão por definição. O que um fasorial responde é ÂNGULO entre tudo e
   * MÓDULO dentro da mesma família — nenhum dos dois precisa de régua comum.
   *
   * Os ângulos não mudam: eles nunca dependeram da régua.
   *
   * **E a régua sai do registro inteiro, não do instante do cursor.** Era do
   * instante, e aí o comprimento de uma seta mudava de significado conforme
   * o cursor andava: a mesma corrente de carga de 1,2 A ocupava metade do
   * círculo na pré-falta (régua 0,5 pu) e virava um toco na falta (régua
   * 10 pu), sem nada ter acontecido com ela. Andar com o cursor comparando
   * pré-falta, falta e extinção é metade do trabalho numa oscilografia, e
   * com a régua do instante essa comparação era uma armadilha.
   *
   * O preço é que na pré-falta as correntes de carga ficam pequenas — mas
   * elas SÃO 2 % da corrente de falta, e a haste atenuada guarda o ângulo.
   *
   * A sequência fica na régua da FASE, de propósito: V2 dividido por V1 lido
   * direto no desenho É o fator de desequilíbrio, e uma régua só para a
   * sequência apagaria essa leitura deixando V1 e V2 do mesmo tamanho.
   */
  function reguasDoPainel(fasores) {
    const vistas = new Map();
    for (const x of fasores) {
      if (x.sinal.sem_sinal) continue;
      const g = grandezaDoSinal(x.sinal);
      // O maior do REGISTRO, não o do instante: `pico` é o maior módulo de
      // fasor deste sinal no registro inteiro, e `base` é a mesma que fez o
      // `pu` do cursor.
      const doRegistro = x.sinal.pico > 0 && x.base > 0
                       ? x.sinal.pico / x.base : 0;
      const quanto = Math.max(doRegistro, Math.abs(x.pu));
      const antes = vistas.get(g);
      if (antes) {
        antes.maior = Math.max(antes.maior, quanto);
        antes.unidades.add(x.sinal.unidade);
      } else {
        vistas.set(g, { maior: quanto, unidades: new Set([x.sinal.unidade]) });
      }
    }
    const limites = new Map();
    for (const [g, { maior, unidades }] of vistas) {
      // O rótulo mostra a UNIDADE quando todos os sinais daquela grandeza
      // estão nela (`kV`), e a grandeza quando não estão (um canal em kV e o
      // neutro em V dividem a mesma régua, porque pu não tem unidade).
      limites.set(g, { limite: escalaDoFasorial(maior),
                       rotulo: unidades.size === 1 ? [...unidades][0] : g });
    }
    return limites;
  }

  /** A grandeza de um sinal: `kV` → `V`, `A` → `A`, `kA` → `A`.
   *
   * A régua é por GRANDEZA e não pela unidade escrita no arquivo: o pu não
   * tem unidade, e um registro com a barra em `kV` e o neutro em `V` ganhava
   * duas réguas de tensão sem motivo nenhum.
   */
  function grandezaDoSinal(sinal) {
    const texto = (sinal.unidade || "").trim();
    return texto ? texto.slice(-1).toUpperCase() : "";
  }

  /** O limite de uma régua em pu: o passo redondo acima do maior fasor. */
  function escalaDoFasorial(maior) {
    if (!(maior > 0)) return 1;
    // 4, 6 e 8 existem para não desperdiçar tela: sem eles uma corrente de
    // 5,2 pu pulava para a régua de 10 e a seta parava em 52 % do círculo —
    // e é justo aí que o anel de 1 pu some, por ficar pequeno demais.
    const passos = [0.1, 0.2, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8,
                    10, 15, 20, 30, 50, 100];
    return passos.find((p) => p >= maior * 1.02) || Math.ceil(maior);
  }

  /** O círculo, os eixos, as marcas de 30 em 30 graus e as réguas.
   *
   * De 30 em 30, e não de 45: o ofício lê ângulo em múltiplos de 30 — as três
   * fases, o grupo de ligação de um trafo, o deslocamento de um delta.
   *
   * `limites` é um Map unidade → pu que o círculo vale, UM POR GRANDEZA (ver
   * `reguasDoPainel`). `null` é o diagrama sem escala: fica o círculo e os
   * graus, some tudo que fala de módulo.
   *
   * Devolve os anéis de 1 pu que couberam. Quem escreve o texto das réguas é
   * `pintarLegendaDasReguas`, DEPOIS das setas.
   */
  function pintarRosaDosVentos(ctx, cx, cy, raio, limites) {
    const linha = token("--linha");
    const suave = token("--suave");
    const util = raio * OCUPACAO;

    ctx.save();
    ctx.strokeStyle = linha;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, util, 0, 2 * Math.PI);
    ctx.stroke();

    for (let g = 0; g < 360; g += 30) {
      const rad = (-g * Math.PI) / 180;
      const dentro = g % 90 === 0 ? 0 : util * 0.94;
      ctx.beginPath();
      ctx.moveTo(cx + dentro * Math.cos(rad), cy + dentro * Math.sin(rad));
      ctx.lineTo(cx + util * Math.cos(rad), cy + util * Math.sin(rad));
      ctx.stroke();
    }

    ctx.fillStyle = suave;
    ctx.font = "11px var(--mono), monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const [g, dx, dy] of [[0, 1, 0], [90, 0, -1], [180, -1, 0], [270, 0, 1]]) {
      const rad = (-g * Math.PI) / 180;
      ctx.fillText(`${g <= 180 ? g : g - 360}°`,
                   cx + (util + 14) * Math.cos(rad) + dx * 2,
                   cy + (util + 14) * Math.sin(rad) + dy * 2);
    }
    if (!limites || !limites.size) { ctx.restore(); return []; }

    /* Os anéis tracejados de **1 pu** — a nominal, um por grandeza.
     *
     * É a pergunta que se faz olhando um fasorial de falta: quantas vezes a
     * nominal esta corrente está, e quanto desta tensão sobrou. O círculo de
     * fora é a régua; o anel é o nominal dentro dela.
     *
     * Só aparece quando cabe: com tudo abaixo da nominal a régua fecha em
     * menos de 1 pu e o anel cairia fora do desenho. Duas grandezas com a
     * MESMA régua dão o mesmo anel — desenha-se um só, com os dois nomes,
     * em vez de dois círculos rigorosamente em cima um do outro. */
    const porRaio = new Map();
    for (const { limite, rotulo } of limites.values()) {
      if (!(limite > 1)) continue;
      const anel = util / limite;
      if (anel <= 12) continue;
      const chave = Math.round(anel);
      if (!porRaio.has(chave)) porRaio.set(chave, { anel, unidades: [] });
      porRaio.get(chave).unidades.push(rotulo);
    }
    ctx.setLineDash([3, 4]);
    for (const { anel } of porRaio.values()) {
      ctx.beginPath();
      ctx.arc(cx, cy, anel, 0, 2 * Math.PI);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.restore();
    return [...porRaio.values()].sort((a, b) => a.anel - b.anel);
  }

  /** A legenda das réguas: quanto vale o círculo, e o nome de cada anel.
   *
   * Desenhada DEPOIS das setas e com um fundo atrás do texto. A régua é o que
   * dá sentido ao desenho inteiro — um fasor passando por cima dela apaga a
   * única coisa que diz o que os comprimentos significam. O nome do anel
   * ainda escolhe o quadrante mais vazio, para o fundo não precisar cobrir
   * fasor nenhum na maioria das vezes.
   *
   * Devolve as caixas ocupadas, para os nomes dos fasores desviarem delas.
   */
  function pintarLegendaDasReguas(ctx, cx, cy, raio, limites, aneis, fasores) {
    const ocupados = [];
    if (!limites || !limites.size) return ocupados;
    const util = raio * OCUPACAO;

    ctx.save();
    ctx.fillStyle = token("--suave");
    ctx.font = "11px var(--mono), monospace";
    ctx.textBaseline = "middle";

    const fundo = (texto, x, y, alinha) => {
      const largura = ctx.measureText(texto).width;
      let esquerda = alinha === "left" ? x
                   : alinha === "right" ? x - largura : x - largura / 2;
      // Encostado na borda em vez de cortado: a régua escrita pela metade
      // («1,5 pu (k») não diz nada.
      const lado = 2 * cx;
      if (esquerda + largura > lado - 2) esquerda = lado - 2 - largura;
      if (esquerda < 2) esquerda = 2;
      x = esquerda;
      alinha = "left";
      const cor = ctx.fillStyle;
      ctx.fillStyle = token("--superficie");
      ctx.fillRect(esquerda - 2, y - 7, largura + 4, 14);
      ctx.fillStyle = cor;
      ctx.textAlign = alinha;
      ctx.fillText(texto, x, y);
      ocupados.push({ esquerda, largura, y });
    };

    // A régua ENCOSTADA no círculo dela, e não no canto da moldura: o número
    // responde "quanto vale este círculo". Na diagonal de cima, onde os eixos
    // não passam. Uma linha por grandeza, porque cada uma tem a sua régua.
    //
    // «1,5 pu (kV)», e nada além disso: sem «círculo = » na frente. A unidade
    // entra sempre, inclusive com uma régua só — o diagrama ganha e perde
    // réguas conforme os sinais, e um rótulo que muda de forma sozinho
    // confunde mais do que a palavra a mais atrapalha.
    const rad = (-48 * Math.PI) / 180;
    const x0 = cx + (util + 3) * Math.cos(rad);
    let y0 = cy + (util + 3) * Math.sin(rad);
    for (const { limite, rotulo } of limites.values()) {
      // «3 pu», não «3,0 pu»: a casa decimal só aparece quando ela diz algo.
      const casas = Number.isInteger(limite) ? 0 : (limite >= 1 ? 1 : 2);
      fundo(`${formatar(limite, casas)} pu (${rotulo})`, x0, y0, "left");
      y0 += 13;
    }

    // E cada anel ganha o nome dele no quadrante mais vazio, DENTRO do anel:
    // os nomes dos fasores ficam do lado de fora das pontas, e é lá que eles
    // se chocariam com este.
    const usados = [];
    for (const { anel, unidades } of aneis) {
      const grau = quadranteVazio(fasores, usados);
      usados.push(grau);
      const r = (-grau * Math.PI) / 180;
      fundo(`1 pu (${unidades.join(", ")})`,
            cx + anel * 0.72 * Math.cos(r), cy + anel * 0.72 * Math.sin(r),
            "center");
    }
    ctx.restore();
    return ocupados;
  }

  /** O ângulo, entre as quatro diagonais, mais longe de qualquer fasor.
   *
   * As diagonais, e não qualquer ângulo: os eixos de 0°, 90°, 180° e -90°
   * passam pelo meio delas, e um texto em cima de um eixo é tão ruim quanto
   * um texto em cima de uma seta.
   */
  function quadranteVazio(fasores, usados = []) {
    const candidatos = [135, 45, -135, -45].filter((g) => !usados.includes(g));
    if (!candidatos.length) return 135;
    // A distância angular até o fasor mais próximo. `((d + 540) % 360) - 180`
    // traz a diferença para (-180, 180], que é onde «10° e 350° distam 10°»
    // vale.
    const longe = (g) => Math.min(...fasores.map(
      (x) => Math.abs(((x.angulo - g + 540) % 360) - 180)), 180);
    return candidatos.reduce((a, g) => (longe(g) > longe(a) ? g : a),
                             candidatos[0]);
  }

  function desenharSeta(ctx, cx, cy, comprimento, graus, cor, grossura,
                        solidoAte = 0) {
    if (!(comprimento > 0)) return;
    const rad = (-graus * Math.PI) / 180;
    const px = cx + comprimento * Math.cos(rad);
    const py = cy + comprimento * Math.sin(rad);

    ctx.save();
    ctx.strokeStyle = cor;
    ctx.fillStyle = cor;
    ctx.lineWidth = grossura;
    ctx.lineCap = "round";

    const travada = solidoAte > 0 && solidoAte < comprimento;
    if (travada) {
      // O pedaço que vale como medida. Num fasor quase nulo ele tem dois
      // pixels — e uma seta quase toda apagada é a leitura certa.
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + solidoAte * Math.cos(rad), cy + solidoAte * Math.sin(rad));
      ctx.stroke();
      ctx.globalAlpha = APAGADO_DA_SETA;
      ctx.beginPath();
      ctx.moveTo(cx + solidoAte * Math.cos(rad), cy + solidoAte * Math.sin(rad));
      ctx.lineTo(px, py);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(px, py);
      ctx.stroke();
    }

    // A ponta. Um triângulo cheio, e não dois riscos: numa tela com oito
    // fasores os riscos se confundem com os próprios fasores. Numa seta
    // travada ela é parte do trecho inventado, e fica apagada junto.
    const abertura = 0.38;
    const tamanho = Math.min(11, Math.max(6, comprimento * 0.18));
    ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.lineTo(px - tamanho * Math.cos(rad - abertura),
               py - tamanho * Math.sin(rad - abertura));
    ctx.lineTo(px - tamanho * Math.cos(rad + abertura),
               py - tamanho * Math.sin(rad + abertura));
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  /** O nome de cada fasor, na ponta da seta, afastado do centro.
   *
   * Fasores sobrepostos — as três fases de uma trinca equilibrada de tensão
   * em cima das de corrente — teriam os nomes um sobre o outro. Quando dois
   * caem perto, o segundo é empurrado para fora.
   */
  function pintarNomesDosFasores(ctx, cx, cy, raio, fasores, painel,
                                 temTravada = false, ocupados = []) {
    ctx.save();
    ctx.font = "11px var(--mono), monospace";
    ctx.textBaseline = "middle";
    // Os rótulos de 0°, 90°, 180° e -90° já estão na roda, e um nome de fasor
    // em cima deles some. Entram na lista como vizinhos ocupados, para o nome
    // descer em vez de escrever por cima.
    if (temTravada) {
      // No canto da moldura: a régua saiu de lá e foi para junto do círculo,
      // então sobrou o lugar — e esta frase é sobre o desenho inteiro, não
      // sobre um círculo.
      //
      // O módulo da travada NÃO vai no desenho. As setas travadas moram todas
      // no centro, por definição, e escrever o pu em cada uma empilha número
      // justo onde o desenho já está mais cheio. O valor exato de todo sinal
      // está na tabela ao lado, o tempo todo.
      ctx.save();
      ctx.fillStyle = token("--suave");
      ctx.textAlign = "left";
      ctx.fillText("haste apagada: trecho sem medida", 2, 10);
      ctx.restore();
    }
    const postos = ocupados.concat(
      [[0, 1, 0], [90, 0, -1], [180, -1, 0], [270, 0, 1]].map(
      ([g, dx, dy]) => {
        const rad = (-g * Math.PI) / 180;
        const meio = cx + (raio * OCUPACAO + 14) * Math.cos(rad) + dx * 2;
        // Os rótulos de grau são centrados e têm ~30 px: a caixa deles vai
        // de `meio - 15` a `meio + 15`.
        return { esquerda: meio - 15, largura: 30,
                 y: cy + (raio * OCUPACAO + 14) * Math.sin(rad) + dy * 2 };
      }));
    for (const x of fasores) {
      const rad = (-x.angulo * Math.PI) / 180;
      const dist = (x.comprimento || 0) + 12;
      const px = cx + dist * Math.cos(rad);
      let py = cy + dist * Math.sin(rad);
      const largura = ctx.measureText(x.sinal.sinal).width;

      // O alinhamento e o encosto na borda vêm ANTES de procurar vizinho: é a
      // posição FINAL que não pode se sobrepor, e testar a de antes do
      // encosto deixava o nome de um fasor de raio cheio em cima do `0°`.
      let alinha = Math.cos(rad) < -0.3 ? "right"
                 : Math.cos(rad) > 0.3 ? "left" : "center";
      const lado = 2 * cx;
      let ancora = px;
      let esquerda = alinha === "left" ? px
                   : alinha === "right" ? px - largura : px - largura / 2;
      if (esquerda + largura > lado - 2) {
        alinha = "right"; ancora = lado - 2; esquerda = ancora - largura;
      } else if (esquerda < 2) {
        alinha = "left"; ancora = 2; esquerda = 2;
      }

      // Quem cai perto de um nome já escrito DESCE. Afastar do centro não
      // resolvia o caso que mais acontece: numa trinca equilibrada a tensão e
      // a corrente da fase A apontam para o mesmo lado, e empurrar as duas
      // para fora as deixava na mesma linha, uma por cima da outra.
      const bate = (p) => Math.abs(p.y - py) < 12
                       && esquerda < p.esquerda + p.largura
                       && p.esquerda < esquerda + largura;
      let voltas = 0;
      while (postos.some(bate) && voltas < 8) { py += 12; voltas += 1; }

      postos.push({ esquerda, largura, y: py });
      ctx.fillStyle = corDoSinal(x.sinal, painel);
      ctx.textAlign = alinha;
      ctx.fillText(x.sinal.sinal, ancora, py);
    }
    ctx.restore();
  }

  const escolhidoNoPainel = (painel, sinal) => selecionados.some(
    (s) => s.painel === painel.id && s.chave === sinal.id);

  //: O painel da esquerda de um par guarda `par: true`, e o da direita é o
  //: SEGUINTE na lista. Não há id cruzado entre os dois: a ordem já diz quem
  //: está ao lado de quem, e um id guardado nos dois lados é mais um lugar
  //: para ficar desencontrado quando um deles é apagado.
  const temPar = (id) => {
    const i = paineis.findIndex((x) => x.id === id);
    return i >= 0 && !!paineis[i].par && !!paineis[i + 1]
        && DIAGRAMAS_QUE_PAREIAM.has(paineis[i + 1].tipo);
  };

  const eDaDireita = (id) => {
    const i = paineis.findIndex((x) => x.id === id);
    return i > 0 && !!paineis[i - 1].par
        && DIAGRAMAS_QUE_PAREIAM.has(paineis[i - 1].tipo);
  };

  /** Põe um segundo diagrama à direita deste.
   *
   * **Ele nasce VAZIO e independente** — sem sinal, no cursor 1, com a
   * referência automática e sem base digitada. O botão só decide ONDE o
   * diagrama fica; o que ele mostra é escolha de quem está analisando.
   *
   * Já nasceu copiando o da esquerda, e saiu: dois diagramas iguais lado a
   * lado se leem como um só repetido, e desfazer a cópia (tirar seis sinais,
   * trocar a referência, apagar a base) custava mais cliques do que montar do
   * zero. Quem quiser comparar o mesmo conjunto em dois instantes marca os
   * mesmos sinais e troca o cursor — dois cliques, e explícitos.
   */
  function criarParFasorial(id) {
    const i = paineis.findIndex((x) => x.id === id);
    if (i < 0) return;
    guardarParaDesfazer();
    paineis[i].par = true;
    const quantos = paineis.filter((x) => x.tipo === "fasorial").length + 1;
    paineis.splice(i + 1, 0, {
      id: `t${proximoId++}`, tipo: "fasorial", nome: `Fasores ${quantos}`,
      sinais: [], medida: "instantaneo", do_padrao: false, cores: {},
      cursor: 1, referencia: null, bases: {}, escala: false,
    });
    carregar();
  }

  //: O que o COMPRIMENTO de uma seta diz. `sem escala` é o padrão: a
  //: pergunta que se faz num fasorial é de ângulo, e com todas do mesmo
  //: tamanho ela se responde de relance. O módulo está na tabela ao lado, em
  //: ampère e volt, o tempo todo.
  const ESCALAS_DO_FASORIAL = [
    [false, "sem escala",
     "Todas as setas do mesmo tamanho: o diagrama mostra só a defasagem. O "
     + "módulo continua na tabela ao lado."],
    [true, "em pu",
     "O comprimento de cada seta é o módulo dela em pu. Cada GRANDEZA tem a "
     + "sua régua — o círculo vale tantos pu de corrente e tantos de tensão "
     + "— para a corrente de falta não esmagar as tensões."],
  ];

  /** A linha «escala» da engrenagem, que ABRE AS OPÇÕES ALI MESMO.
   *
   * Um menu dentro do menu não funciona: `menuSuspenso` mantém um aberto por
   * vez, então o segundo fechava a engrenagem — e a engrenagem levava junto a
   * âncora onde o segundo ia nascer. O clique fechava tudo sem fazer nada.
   *
   * Abrindo dentro da própria caixa, o caminho continua sendo o que se lê —
   * ajustes → escala → as duas opções — e nada precisa de um segundo menu.
   */
  function botaoDaEscala(painel) {
    const caixa = criar("div", "ajuste-com-opcoes");
    const b = criar("button", "medida", "escala");
    b.type = "button";
    b.setAttribute("aria-expanded", "false");
    //: Para BAIXO, como a de todo botão que abre coisa nesta tela. Fechada
    //: ela aponta para onde as opções vão aparecer; aberta, para o botão que
    //: as recolhe.
    const seta = criar("span", "seta-do-menu", "▾");
    b.append(seta);

    const lista = criar("div", "opcoes-do-ajuste");
    lista.hidden = true;
    const marcas = [];
    for (const [valor, rotulo, explicacao] of ESCALAS_DO_FASORIAL) {
      const linha = criar("label", "opcao");
      const marca = document.createElement("input");
      marca.type = "radio";
      marca.name = `escala-${painel.id}`;
      marca.checked = !!(painelPorId(painel.id) || {}).escala === valor;
      marca.addEventListener("change", () => {
        escolherEscala(painel.id, valor);
        //: As duas marcas vivem na caixa que o clique NÃO refaz — então quem
        //: as acerta é este laço, e não o próximo desenho.
        marcas.forEach(([m, v]) => { m.checked = v === valor; });
        b.title = explicacaoDaEscala(valor);
      });
      marcas.push([marca, valor]);
      linha.title = explicacao;
      linha.append(marca, criar("span", null, rotulo));
      lista.append(linha);
    }

    b.title = explicacaoDaEscala(!!(painelPorId(painel.id) || {}).escala);
    b.addEventListener("click", () => {
      const abrir = lista.hidden;
      lista.hidden = !abrir;
      //: A MESMA seta, virada de cabeça para baixo — e não outro caractere.
      //: `▴` e `▾` são dois desenhos diferentes, de tamanhos diferentes na
      //: fonte monoespaçada, e a troca não se lia como «agora ela aponta para
      //: cima». Virando a mesma figura, a diferença é inconfundível.
      seta.classList.toggle("virada", abrir);
      b.setAttribute("aria-expanded", abrir ? "true" : "false");
    });

    caixa.append(b, lista);
    return [caixa];
  }

  const explicacaoDaEscala = (valor) =>
    (ESCALAS_DO_FASORIAL.find(([v]) => v === !!valor) || ESCALAS_DO_FASORIAL[0])[2];

  /** Escolhe o que o comprimento das setas de um fasorial diz. */
  function escolherEscala(id, valor) {
    const meu = painelPorId(id);
    if (!meu || !!meu.escala === valor) return;
    guardarParaDesfazer();
    meu.escala = valor;
    const vindo = (dados.paineis || []).find((x) => x.id === id);
    if (vindo) vindo.escala = valor;
    // A escala é desenho — e a nota do «1 pu = …», que some sem escala. Nada
    // mais no HTML depende dela, então refazer os blocos só serviria para
    // fechar a engrenagem na cara de quem acabou de clicar.
    repintarAgora();
    mostrarBasesDoPu();
  }

  /** Troca o cursor que este painel fasorial mostra. */
  function alternarCursorDoPainel(id) {
    const meu = painelPorId(id);
    if (!meu) return;
    guardarParaDesfazer();
    meu.cursor = meu.cursor === 2 ? 1 : 2;
    // Nada a pedir ao servidor: os dois cursores já vêm na mesma leitura.
    const vindo = (dados.paineis || []).find((x) => x.id === id);
    if (vindo) vindo.cursor = meu.cursor;
    desenharTudo();
  }

  /** Escolhe o zero dos ângulos DESTE diagrama.
   *
   * É de cada painel, e não da tela: dois fasoriais lado a lado podem querer
   * referências diferentes — as correntes referidas à tensão da fase A, as
   * tensões referidas a elas mesmas. Clicar de novo no que já é a referência
   * volta à regra automática do servidor (a tensão da fase A).
   */
  function escolherReferencia(idDoPainel, idDoSinal, direta = false) {
    const meu = painelPorId(idDoPainel);
    if (!meu) return;
    // No menu a escolha é direta: marcar o que já está marcado não pode
    // desmarcar. No NOME da lista é alternância, que é o gesto de lá: clicar
    // de novo no que já é a referência volta à automática.
    meu.referencia = direta ? idDoSinal
                   : (meu.referencia === idDoSinal ? null : idDoSinal);
    const vindo = (dados.paineis || []).find((x) => x.id === idDoPainel);
    if (vindo) vindo.referencia = meu.referencia;
    // No plano complexo a referência muda o CAMINHO, que é conta da janela.
    if (meu.tipo === "complexo") { recarregar(); return; }
    desenharTudo();
  }

  /** O ângulo de um sinal já referido ao zero escolhido no painel. */
  function anguloNoPainel(painel, idDoSinal, valores) {
    const v = valores ? valores[idDoSinal] : null;
    if (!v || v.angulo === null || v.angulo === undefined) return null;
    const meu = painelPorId(painel.id) || {};
    if (!meu.referencia) return v.angulo;
    const zero = valores[meu.referencia];
    if (!zero || zero.angulo === null || zero.angulo === undefined) return v.angulo;
    let bruto = v.angulo - zero.angulo;
    while (bruto <= -180) bruto += 360;
    while (bruto > 180) bruto -= 360;
    return bruto;
  }

  /** Clicar no nome da legenda escolhe o sinal, igual a clicar no traço.
   *
   * O traço é o gesto natural e é o que erra: num gráfico com oito curvas
   * sobrepostas na pré-falta, acertar o traço certo com o mouse é sorte. O
   * nome na legenda está sempre no mesmo lugar e não se move.
   */
  function selecionavel(item, painel, chave) {
    item.classList.add("clicavel");
    item.addEventListener("click", (evento) => {
      alternarSelecao({ painel: painel.id, tipo: "sinal", chave },
                      evento.ctrlKey || evento.metaKey);
    });
  }

  /** Acende na legenda o sinal escolhido no gráfico. */
  function marcarLegenda() {
    for (const b of blocos) {
      if (!b._painel) continue;
      for (const item of b.querySelectorAll(".legenda li")) {
        item.classList.toggle("escolhido", selecionados.some(
          (s) => s.painel === item.dataset.painel && s.chave === item.dataset.chave));
      }
    }
  }

  /** A bolinha com a cor da curva, na tabelinha — e o botão de trocá-la.
   *
   * Clicar nela abre a MESMA paleta do catálogo. Duas formas de escolher cor
   * no mesmo programa seriam duas coisas para aprender, e a segunda acabaria
   * oferecendo um conjunto de cores diferente da primeira.
   */
  function bolinhaDoSinal(painel, sinal) {
    const bolinha = criar("button", "bolinha-do-sinal");
    bolinha.type = "button";
    bolinha.style.background = corDoSinal(sinal, painel);
    bolinha.title = `cor de ${sinal.sinal || sinal.nome} no gráfico — `
                  + "clique para trocar";
    bolinha.setAttribute("aria-label", "trocar a cor deste sinal");
    bolinha.addEventListener("click", (evento) => {
      evento.preventDefault();
      evento.stopPropagation();
      abrirPaletaFlutuante(painel, sinal, bolinha);
    });
    return bolinha;
  }

  /** A paleta ANCORADA na bolinha, por cima de tudo.
   *
   * Flutuante, e não trocada no lugar da bolinha como no catálogo: a célula da
   * tabelinha tem `overflow: hidden` e largura fixa — pôr seis bolinhas dentro
   * dela empurraria o nome para fora e a paleta sairia cortada pela metade.
   * `position: fixed` escapa de qualquer recorte, e por isso ela se posiciona
   * pelo retângulo da bolinha na tela, não pelo pai.
   */
  function abrirPaletaFlutuante(painel, sinal, ancora) {
    document.querySelectorAll(".paleta-flutuante").forEach((x) => x.remove());

    const paleta = criar("div", "paleta-flutuante");
    const valendo = corEscolhida(painel.id, sinal.id)
                 || corDoTokenAtual(painel, sinal);

    const fechar = () => {
      paleta.remove();
      document.removeEventListener("pointerdown", foraDaPaleta, true);
      window.removeEventListener("scroll", fechar, true);
      window.removeEventListener("resize", fechar);
    };
    const foraDaPaleta = (e) => {
      if (!paleta.contains(e.target) && e.target !== ancora) fechar();
    };

    for (const cor of PALETA) {
      const opcao = criar("button", "cor-opcao");
      opcao.type = "button";
      opcao.style.background = token(cor);
      opcao.title = cor === valendo ? "cor atual" : "usar esta cor";
      if (cor === valendo) opcao.classList.add("escolhida");
      opcao.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        fechar();
        // `escolherCor` já redesenha tudo — a tabelinha inteira é refeita, e
        // com ela esta bolinha. Por isso não há nada para repintar aqui.
        escolherCor(painel.id, sinal.id, cor);
      });
      paleta.append(opcao);
    }
    paleta.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.stopPropagation(); fechar(); }
    });

    document.body.append(paleta);
    // Medir DEPOIS de inserir: antes disso a paleta não tem largura, e o
    // encosto na borda direita da janela sairia errado justamente nos painéis
    // da direita, que são os que encostam.
    const r = ancora.getBoundingClientRect();
    const caixa = paleta.getBoundingClientRect();
    const margem = 6;
    const x = Math.min(Math.max(margem, r.left - 4),
                       window.innerWidth - caixa.width - margem);
    const abaixo = r.bottom + 4;
    const y = abaixo + caixa.height + margem <= window.innerHeight
      ? abaixo
      : Math.max(margem, r.top - caixa.height - 4);
    paleta.style.left = `${Math.round(x)}px`;
    paleta.style.top = `${Math.round(y)}px`;
    paleta.firstChild.focus();

    document.addEventListener("pointerdown", foraDaPaleta, true);
    window.addEventListener("scroll", fechar, true);
    window.addEventListener("resize", fechar);
  }

  /** A tabelinha de um painel: os sinais dele, sempre nas mesmas três colunas.
   *
   * Cursor 1, cursor 2 e a diferença — em qualquer grandeza. A largura nunca
   * muda, e isso é de propósito: tabela que cresce e encolhe empurra o gráfico
   * no meio de uma medição, e a onda foge de debaixo do mouse.
   *
   * O que não cabe em três colunas (ângulo, DC, distorção, e o instantâneo
   * quando o gráfico não está mostrando ele) fica no hover de cada valor.
   */
  function tabelinha(painel) {
    const tabela = criar("table", "mini");

    const cabeca = criar("tr");
    // O canto diz que grandeza está na tabela. NÃO é botão: quem manda é o
    // botão do próprio painel, e dois lugares mandando na mesma coisa é como
    // eles passam a discordar.
    const canto = criar("th", "unidade",
                        painel.medida === "rms" ? "RMS" : "valor");
    canto.title = "Escolha a medida no topo deste gráfico e o filtro no cabeçalho";
    cabeca.append(canto);

    for (const k of [1, 2]) {
      const th = criar("th");
      th.append(criar("span", `em-${k}`), String(k));
      cabeca.append(th);
    }
    cabeca.append(criar("th", null, "2−1"));

    const thead = criar("thead");
    thead.append(cabeca);

    const tbody = criar("tbody");
    for (const sinal of (painel.sinais || [])) {
      const linha = criar("tr");
      const nome = criar("th", "canal");
      // O `th` continua sendo célula de tabela: pôr `display:flex` nele tirava
      // a célula do cálculo de colunas do `table-layout: fixed`, e a primeira
      // coluna encolhia para o tamanho do conteúdo — o nome sumia. Quem é
      // flex é este invólucro.
      const rotulo = criar("span", "rotulo");
      nome.append(rotulo);
      // A cor saiu da LETRA e foi para uma bolinha.
      //
      // Pintar o nome fazia a cor significar duas coisas ao mesmo tempo: no
      // meio de nomes brancos, letra colorida se lê como «este está
      // selecionado», não como «esta é a curva azul». Cor numa bolinha ao
      // lado se lê como etiqueta — a mesma decisão já tomada no cartão de
      // sinal e na legenda da onda, agora valendo nas três telas.
      //
      // E a bolinha é CLICÁVEL: é o lugar onde a cor está escrita, então é o
      // lugar onde se troca a cor. Ver `bolinhaDoSinal`.
      rotulo.append(bolinhaDoSinal(painel, sinal));

      // O nome, sem mais. Clicar nele já fez o canal virar o zero dos
      // ângulos — e saiu daqui: a escolha do zero é de um DIAGRAMA, não da
      // tela inteira, e aqui ela era global e invisível. Quem compara ângulo
      // compara no fasorial, e é lá que ela mora agora, por painel.
      const seloDaLinha = seloDoIed(sinal.ied);
      if (seloDaLinha) rotulo.append(seloDaLinha);
      const etiqueta = criarNome("span", "nome", sinal.sinal || sinal.nome);
      etiqueta.title = `${sinal.sinal} — ${sinal.descricao || ""}`;
      rotulo.append(etiqueta);

      // A unidade em TODA linha, e não só na que está no segundo eixo. Desde
      // que um gráfico pode misturar sinais, a unidade deixou de ser dedutível
      // do título: `81,67` numa linha de V1 se lê como 81 V secundários quando
      // são 81 kV primários — erro de três ordens de grandeza que não tem nada
      // na tela para denunciá-lo.
      if (sinal.unidade) {
        const un = criar("span", "unidade-extra", `(${sinal.unidade})`);
        un.title = sinal.eixo === "dir"
          ? "Este sinal está na escala da DIREITA, porque a unidade dele não é "
            + "a do gráfico."
          : `valores em ${sinal.unidade}`;
        rotulo.append(un);
      }

      const celas = [criar("td", "valor-1 vazio-valor", "—"),
                     criar("td", "valor-2 vazio-valor", "—"),
                     criar("td", "vazio-valor", "—")];
      linha.append(nome, ...celas);
      tbody.append(linha);
      celulas.push({ painel: painel.id, id: sinal.id, celas,
                     indice: sinal.indice });
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

  // --- a grandeza do gráfico e a referência dos ângulos --------------------

  function lerGuardado(chave, aceitos, padrao) {
    try {
      const guardado = localStorage.getItem(chave);
      return aceitos.includes(guardado) ? guardado : padrao;
    } catch {
      return padrao;
    }
  }

  function guardar(chave, valor) {
    try {
      localStorage.setItem(chave, valor);
    } catch { /* não poder lembrar não impede de usar */ }
  }

  //: Os sinais selecionados por clique. Cada um é `{painel, tipo, chave}`;
  //: `tipo` é `sinal` ou `digital`. Lista, e não um só, porque comparar duas
  //: fases é o gesto mais comum do ofício — e porque apagar quatro sinais um a
  //: um é quatro vezes o mesmo trabalho.
  let selecionados = [];

  //: A pilha do desfazer. Cada item é uma fotografia do ARRANJO. Ações que
  //: mexem em dado gravado (a correção de fase) ficam de fora: o Ctrl+Z desfaz
  //: o que se está vendo, não o que se decidiu.
  const desfazer = [];

  const mesmoSinal = (a, b) =>
    a.tipo === b.tipo && a.chave === b.chave && a.painel === b.painel;

  const estaSelecionado = (painel, tipo, chave) =>
    selecionados.some((s) => mesmoSinal(s, {
      painel: painel ? painel.id : null, tipo, chave }));

  /** Guarda o arranjo atual para o Ctrl+Z. */
  function guardarParaDesfazer() {
    desfazer.push(JSON.parse(JSON.stringify(paineis)));
    // Vinte passos é mais do que qualquer análise precisa, e segura a memória.
    if (desfazer.length > 20) desfazer.shift();
  }

  function desfazerUltimo() {
    const antes = desfazer.pop();
    if (!antes) return;
    paineis = antes;
    selecionados = [];
    carregar();
  }

  function alternarFiltro() {
    if (filtroTravado()) return;
    filtro = !filtro;
    guardar("osclab:filtro", filtro ? "1" : "0");
    // **Apagar o filtro leva ao modo avançado.** Pedir a onda como o relé
    // gravou é pedir o bruto, e o bruto é o que o avançado oferece: recusar o
    // clique deixaria o usuário preso num modo sem dizer por quê, e aceitá-lo
    // sem trocar de modo deixaria a tela desenhando a onda crua enquanto o
    // catálogo só oferece colunas do filtrado. Os dois estados andam juntos.
    if (!filtro && visaoDeAnalise === "tradicional") {
      visaoDeAnalise = "avancado";
      guardar("osclab:catalogo:visao", "avancado");
      if (redesenharCatalogo) redesenharCatalogo();
    }
    marcarBotoes();
    recarregar();
  }

  function alternarMedida(id) {
    const painel = painelPorId(id);
    if (!painel) return;
    painel.medida = painel.medida === "rms" ? "instantaneo" : "rms";
    recarregar();
  }

  /** Agrupados ou um por gráfico. Não pede nada ao servidor.
   *
   * São os MESMOS números, arrumados de outro jeito: trocar de modo é desenho
   * puro. Recarregar aqui seria pedir ao servidor uma resposta idêntica à que
   * já está na mão, e pagar a ida e a volta por nada — num arquivo grande, o
   * botão demoraria meio segundo para fazer o que o canvas faz num quadro.
   */
  /** Liga e desliga os pontinhos de amostra deste painel.
   *
   * De CADA painel, como o arranjo e a medida: numa tela com corrente e
   * tensão, querer ver a amostra da corrente não quer dizer querer ver a da
   * tensão — e a tensão costuma ter dez vezes mais ciclos à vista.
   */
  function alternarAmostras(id, botao) {
    const painel = painelPorId(id);
    if (!painel) return;
    guardarParaDesfazer();
    painel.amostras = !painel.amostras;
    if (botao) vestirBotaoDasAmostras(botao, painel.amostras);
    //: REPINTAR, e nao `desenharTudo`: os pontinhos sao detalhe de canvas --
    //: nenhum no do DOM muda com eles. `desenharTudo` refazia os blocos, e a
    //: ancora da engrenagem morria junto: o menu fechava no mesmo quadro e o
    //: botao aceso desaparecia antes de ser visto. O clique parecia nao ter
    //: feito nada.
    repintarAgora();
  }

  function alternarEmpilhado(id) {
    const painel = painelPorId(id);
    if (!painel) return;
    guardarParaDesfazer();
    painel.empilhado = !painel.empilhado;
    desenharTudo();
  }

  /** A curva inteira muda: é o servidor que a calcula, sobre a janela de um
   * ciclo que termina em cada ponto. O navegador não tem como derivá-la do que
   * já está desenhado — o traço na tela é mínimo e máximo por coluna de pixel.
   */
  /** Recarrega a janela do servidor. Devolve a PROMESSA de estar pronta.
   *
   * Era `function recarregar()` chamando `carregar()` sem esperar — e quem
   * escrevia `await recarregar()` recebia `undefined`, seguia em frente com
   * os `dados` de antes e não tinha como saber. Foi assim que a janelinha de
   * sinais, refeita logo depois de criar um vínculo, saiu sem as potências
   * que o vínculo acabara de criar: ela foi montada com o catálogo velho.
   *
   * Quem não precisa esperar continua chamando sem `await`, como antes.
   */
  async function recarregar() {
    await carregar();
    // A leitura dos cursores sai SEM `await`, de propósito.
    //
    // Quem espera por `recarregar` espera pela JANELA — é dela que a lista de
    // sinais e a de grupos são refeitas. A leitura dos cursores é outra ida ao
    // servidor, e esperar por ela também punha as duas em fila: toda troca de
    // medida ou de filtro passava a custar dois tempos de resposta em vez de
    // um, sem que ninguém estivesse esperando pela tabelinha.
    if (cursores[0] !== null || cursores[1] !== null) lerCursores();
  }

  /** O relé já filtrou antes de gravar? Então o filtro não é escolha nossa.
   *
   * Filtrar de novo não limparia nada: só acrescentaria mais um ciclo de
   * atraso, e a falta passaria a aparecer dois ciclos depois de ter
   * acontecido. O botão fica aceso e preso porque é esse o estado do sinal —
   * tendo sido o relé quem o pôs assim.
   */
  const filtroTravado = () => !!dados && dados.filtragem === "filtrado";

  /** Liga e desliga o ímã. Fica guardado: quem analisa com ele aceso costuma
   * querer o mesmo na próxima oscilografia. */
  function alternarIma() {
    magnetico = !magnetico;
    guardar("osclab:imã", magnetico ? "1" : "0");
    // Desligar não mexe onde os cursores já estão — arrastá-los de volta por
    // conta própria seria a tela desfazer uma medição que o usuário fez.
    if (!magnetico) { presos[0] = presos[1] = null; }
    marcarBotoes();
    repintar();
  }

  /** Abre (ou fecha) um menu pendurado num botão.
   *
   * Um só para o ímã e para o filtro — e para o próximo. Não é `<dialog>`
   * modal como a busca de sinais: ali se está escolhendo conteúdo e vale
   * ocupar a tela; aqui é um ajuste de três segundos, e escurecer a
   * oscilografia inteira para isso seria desproporcional.
   *
   * `montar` recebe a caixa e põe as opções dentro. Fechar é esvaziar a
   * âncora, que por isso TEM QUE SER um nó vazio só dela: na primeira versão
   * do menu do ímã a âncora era o grupo inteiro, e fechar levava os dois
   * botões junto.
   */
  /** Clicar fora de uma janelinha fecha a janelinha.
   *
   * O `<dialog>` modal recebe o clique do fundo escuro NELE mesmo, então o que
   * distingue «fora» de «dentro» é a posição do ponteiro contra o retângulo
   * dela — e não o alvo do evento. Comparar pelo alvo fecharia também o clique
   * na borda interna, que é dentro.
   *
   * Exige que o botão tenha DESCIDO fora também: quem começa a arrastar dentro
   * da lista e solta fora (selecionando um nome, por exemplo) não está pedindo
   * para fechar.
   */
  function fecharAoClicarFora(janelinha) {
    const fora = (evento) => {
      const r = janelinha.getBoundingClientRect();
      return evento.clientX < r.left || evento.clientX > r.right
          || evento.clientY < r.top || evento.clientY > r.bottom;
    };
    let comecouFora = false;
    janelinha.addEventListener("mousedown", (e) => { comecouFora = fora(e); });
    janelinha.addEventListener("click", (e) => {
      if (comecouFora && fora(e)) janelinha.close();
    });
  }

  //: O menu suspenso aberto agora — a função que o fecha, ou `null`. Um só:
  //: a tela nunca tem dois abertos ao mesmo tempo, e é guardando o fechamento
  //: aqui que `menuSuspenso` consegue fechar DE VERDADE o que já estava
  //: aberto, em vez de apenas esvaziar a âncora. Ver o comentário lá dentro.
  let menuAberto = null;

  function menuSuspenso(idDaAncora, titulo, montar, opcoes = {}) {
    const ancora = document.getElementById(idDaAncora);
    if (!ancora) return;

    /* FECHAR É DESARMAR, e não só esvaziar a âncora.
     *
     * Cada menu registra um `pointerdown` no documento para fechar quando se
     * aponta para fora dele. Quando o menu era fechado pelo próprio botão, a
     * âncora esvaziava e esse ouvinte ficava para trás, armado. Na abertura
     * seguinte ele acordava no primeiro clique dentro do menu NOVO — o alvo
     * não estava na caixa VELHA — e esvaziava a âncora, que é a mesma: o menu
     * sumia debaixo do dedo antes de o clique chegar ao rádio.
     *
     * É o mesmo sintoma da armadilha do `focusout` (clicar no nome não
     * marcava, só a bolinha), por outro caminho — e por isso ele voltou
     * depois de consertado.
     *
     * Guardar o fechamento do menu aberto resolve os dois casos de uma vez, e
     * garante de quebra que só existe um menu aberto na tela. */
    const jaAberto = !!ancora.firstChild;
    if (menuAberto) menuAberto();
    if (jaAberto) return;                    // o botão que abre também fecha

    const caixa = criar("div", "menu-suspenso");
    caixa.append(criar("p", "cabeca-menu", titulo));
    montar(caixa);

    let pronto = false;
    const fechar = () => {
      if (pronto) return;
      pronto = true;
      if (menuAberto === fechar) menuAberto = null;
      document.removeEventListener("pointerdown", aoApontar, true);
      ancora.replaceChildren();
      gatilho?.setAttribute("aria-expanded", "false");
    };

    /* O menu fecha ao se apontar para FORA dele — e não quando ele perde o
       foco.
 
       Fechar no `focusout` era uma armadilha: clicar no NOME de uma opção
       aponta para um `<span>`, que não recebe foco, então o rádio que estava
       focado perdia o foco ali mesmo, o menu sumia no `mousedown` e o clique
       não chegava a marcar nada. Só a bolinha funcionava, porque ela própria
       recebe o foco e o menu continuava aberto. */
    const gatilho = ancora.previousElementSibling;
    const aoApontar = (e) => {
      if (caixa.contains(e.target)) return;
      // O botão que abre também fecha, e quem cuida disso é o `click` dele:
      // fechar aqui faria o menu piscar e reabrir no mesmo gesto.
      if (gatilho && gatilho.contains(e.target)) return;
      fechar();
    };
    document.addEventListener("pointerdown", aoApontar, true);

    // Sair do menu pelo TECLADO continua fechando: ali `relatedTarget` é o
    // elemento que recebeu o foco, e não `null` como no clique num texto.
    //
    // Menos quando o foco vai para o BOTÃO que abriu o menu: isso é o
    // `mousedown` de quem clicou nele para fechar. Fechar aqui fazia o
    // `click` que vem logo depois encontrar a âncora vazia e ABRIR de novo —
    // a setinha nunca fechava o menu. Quem fecha nesse caso é o `click`.
    //
    // E menos quando o foco vai para um elemento que CONTÉM o menu. É o que
    // acontece dentro de um `<dialog>` modal: clicar no nome de uma opção — um
    // `<span>`, que não recebe foco — passa o foco para a própria janelinha, e
    // não para `null` como na página. Era por isso que o «agrupar por» do
    // catálogo continuava só aceitando a bolinha depois de o menu do
    // cabeçalho ter sido consertado. Sair pelo teclado leva o foco a um
    // VIZINHO, que nunca contém o menu.
    caixa.addEventListener("focusout", (e) => {
      const foi = e.relatedTarget;
      if (!foi || caixa.contains(foi) || foi.contains(caixa)) return;
      if (gatilho && gatilho.contains(foi)) return;
      fechar();
    });
    caixa.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.stopPropagation(); fechar(); }
    });
    menuAberto = fechar;
    ancora.append(caixa);
    // Nas FILEIRAS DO CABEÇALHO o menu sai da caixa da fileira: elas rolam
    // dentro de si (`overflow-x: auto`), e um menu absoluto ali dentro era
    // CORTADO pela própria fileira — a lista do filtro aparecia pela metade,
    // sem o cosseno, e por cima dos botões. Fixo na janela, ancorado no
    // grupo do botão, ele aparece inteiro logo abaixo. Ver 22/10/2026.
    //
    // `fixo` pede o mesmo fora do cabeçalho: a explicação do plano complexo
    // era CORTADA pela borda de baixo do painel (22/10/2026). Sem lugar
    // embaixo, ela abre para cima; sem lugar nenhum, rola por dentro.
    if (opcoes.fixo || ancora.closest(".topo.registro .acoes")) {
      const base = (ancora.parentElement || ancora).getBoundingClientRect();
      caixa.style.position = "fixed";
      caixa.style.maxHeight = `${window.innerHeight - 16}px`;
      caixa.style.overflowY = "auto";
      const altura = caixa.offsetHeight;
      const embaixo = window.innerHeight - base.bottom - 14;
      caixa.style.top = altura <= embaixo || base.top < altura + 14
        ? `${Math.max(8, Math.min(base.bottom + 6, window.innerHeight - altura - 8))}px`
        : `${base.top - altura - 6}px`;
      const largura = caixa.offsetWidth;
      caixa.style.left = `${Math.max(8, Math.min(base.left,
                                     window.innerWidth - largura - 8))}px`;
      // Rolar a página com ele aberto deixaria o menu solto no ar.
      window.addEventListener("scroll", fechar, { once: true, passive: true });
    }
    // A setinha vira para cima enquanto o menu está aberto: diz que o próximo
    // clique FECHA. Quem gira é o CSS, pelo `aria-expanded` — o mesmo
    // atributo que conta a um leitor de tela que o menu abriu.
    gatilho?.setAttribute("aria-expanded", "true");
    caixa.querySelector("input")?.focus();
  }

  /** O menu do ímã: em que tipo de ponto ele gruda. */
  function abrirMenuDoIma() {
    menuSuspenso("menu-do-ima", "o ímã gruda em:", (caixa) => {
      const marcas = new Map();
      /** Trava a ÚLTIMA ligada, em vez de deixar desmarcar e desmarcar sozinha.
       *
       * Tudo desligado seria um ímã aceso que não gruda em nada. A primeira
       * versão devolvia a marca ao lugar em silêncio — e clique que não faz
       * nada sem dizer por quê é pior que clique proibido: o usuário tenta de
       * novo, acha que a tela travou, e ainda fica sem poder trocar de "só A"
       * para "só B". Travada e com a explicação no hover, ele vê que precisa
       * ligar a outra primeiro.
       */
      const travarAUltima = () => {
        const sozinha = atracoes.size === 1;
        for (const [chave, marca] of marcas) {
          const ultima = sozinha && atracoes.has(chave);
          marca.disabled = ultima;
          marca.parentElement.title = ultima
            ? "O ímã precisa grudar em alguma coisa. Ligue outra antes de "
              + "desligar esta."
            : "";
        }
      };

      for (const [chave, rotulo] of ATRACOES) {
        const linha = criar("label", "opcao");
        const marca = document.createElement("input");
        marca.type = "checkbox";
        marca.checked = atracoes.has(chave);
        marca.addEventListener("change", () => {
          if (marca.checked) atracoes.add(chave);
          else atracoes.delete(chave);
          guardarAtracoes();
          travarAUltima();
          marcarBotoes();
        });
        marcas.set(chave, marca);
        linha.append(marca, criar("span", null, rotulo));
        caixa.append(linha);
      }
      travarAUltima();
    });
  }

  /** O título da página renomeia o registro DENTRO do OscLab.
   *
   * `UPC1 ALIMENTADOR 11SEL-451-521_09_202613_36_57_649_000` é o nome que o
   * fabricante exporta, e ele não diz que evento é aquele. O nome novo fica
   * gravado ao lado do registro — como as correções de fase e de trinca, e
   * pelo mesmo motivo: é decisão humana, não cache.
   *
   * **O arquivo no disco não muda.** O acervo guarda os arquivos com o nome
   * original porque é assim que o leitor acha o `.dat` a partir do `.cfg`;
   * quem quiser o arquivo com o nome novo usa o `exportar`, que entrega uma
   * cópia renomeada sem tocar no original.
   */
  function ligarNomeDoRegistro() {
    const titulo = document.getElementById("nome-do-registro");
    if (!titulo) return;
    titulo.addEventListener("click", () => editarNome(titulo));
    titulo.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter" || evento.key === " ") {
        evento.preventDefault();
        editarNome(titulo);
      }
    });
  }

  function editarNome(titulo) {
    if (titulo.hidden) return;
    const antes = titulo.textContent.trim();
    const campo = document.createElement("input");
    campo.type = "text";
    campo.className = "campo-do-nome";
    campo.value = antes;
    campo.setAttribute("aria-label", "nome deste registro no OscLab");
    campo.maxLength = 120;

    let pronto = false;
    const terminar = async (guardar) => {
      if (pronto) return;
      pronto = true;
      const novo = campo.value.trim();
      campo.replaceWith(titulo);
      if (!guardar || novo === antes) return;
      titulo.textContent = novo || antes;
      try {
        const r = await fetch(`/api/acervo/${sha}/nome`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nome: novo }),
        });
        if (!r.ok) throw new Error(`${r.status}`);
        const resposta = await r.json();
        // O servidor devolve o nome que FICOU: ele tira o que não cabe em nome
        // de arquivo (a exportação usa este nome) e, com o campo vazio, volta
        // ao nome do arquivo. A tela mostra o que ficou, não o que foi pedido.
        titulo.textContent = resposta.nome;
        document.title = `${resposta.nome} — OscLab`;
        const doArquivo = document.getElementById("nome-do-arquivo");
        if (doArquivo) {
          doArquivo.textContent = `arquivo: ${resposta.nome_do_arquivo}`;
          doArquivo.hidden = resposta.nome === resposta.nome_do_arquivo;
        }
      } catch (erro) {
        titulo.textContent = antes;
        avisarNoPe("Não consegui gravar o nome: "
                   + `${erro.message}. O registro continua com o nome `
                   + "de antes.");
      }
    };

    campo.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter") terminar(true);
      if (evento.key === "Escape") { evento.stopPropagation(); terminar(false); }
    });
    campo.addEventListener("blur", () => terminar(true));
    titulo.replaceWith(campo);
    campo.focus();
    campo.select();
  }

  /** Troca o modo de análise, e redesenha o catálogo que estiver aberto. */
  function trocarVisao(chave) {
    if (!VISOES.some(([c]) => c === chave)) return;
    visaoDeAnalise = chave;
    guardar("osclab:catalogo:visao", chave);
    // Entrar no tradicional acende o filtro: o modo trabalha com o sinal
    // filtrado, e só com ele. Sair dele NÃO o apaga — quem foi para o avançado
    // quer escolher, e escolher é o que o botão passa a fazer.
    const acender = chave === "tradicional" && !filtro && !filtroTravado();
    if (acender) {
      filtro = true;
      guardar("osclab:filtro", "1");
    }
    marcarBotoes();
    if (redesenharCatalogo) redesenharCatalogo();
    if (acender) recarregar();
  }

  /** O botão do modo: um clique alterna entre os dois.
   *
   * São dois modos, então o botão ALTERNA — pedir um menu para escolher entre
   * duas coisas é um clique a mais para nada. A setinha ao lado continua
   * existindo porque é ela que diz o que cada modo mostra e o que cada um
   * esconde, e isso não cabe num rótulo de uma palavra.
   */
  function alternarVisao() {
    trocarVisao(visaoDeAnalise === "tradicional" ? "avancado" : "tradicional");
  }

  /** O menu do modo de análise: o que cada um mostra. */
  function abrirMenuDaVisao() {
    menuSuspenso("menu-do-modo", "modo de análise:", (caixa) => {
      for (const [chave, rotulo, explicacao] of VISOES) {
        const linha = criar("label", "opcao");
        const marca = document.createElement("input");
        marca.type = "radio";
        marca.name = "modo-de-analise";
        marca.checked = chave === visaoDeAnalise;
        marca.addEventListener("change", () => trocarVisao(chave));
        linha.title = explicacao;
        linha.append(marca, criar("span", null, rotulo));
        caixa.append(linha);
      }
    });
  }

  /** O menu do filtro: QUAL filtro o botão aplica.
   *
   * Hoje há um só, e ele aparece MARCADO — ele é a resposta, não uma escolha
   * que falhou. Já apareceu marcado e travado, e travado foi um erro: um rádio
   * desabilitado no tema escuro não se distingue de um rádio desmarcado, e a
   * tela passava a dizer que nenhum filtro estava escolhido. Clicar nele não
   * muda nada, que é o certo quando não há segunda opção.
   *
   * O dia em que entrar o segundo (meio ciclo, cosseno, mímico), a escolha
   * passa a valer também no servidor, que é quem calcula.
   */
  function abrirMenuDoFiltro() {
    menuSuspenso("menu-do-filtro", "o filtro aplicado é:", (caixa) => {
      const so_um = FILTROS.length === 1;
      // Em LISTA, cada opção com quem a usa e uma linha do que ela faz — a
      // maquete 1 de «filtros-10». O texto longo continua no hover.
      for (const [chave, rotulo, explicacao, quem, resumo] of FILTROS) {
        const linha = criar("label", "opcao opcao-do-filtro");
        const marca = document.createElement("input");
        marca.type = "radio";
        marca.name = "filtro-escolhido";
        marca.checked = chave === filtroEscolhido;
        marca.addEventListener("change", () => {
          filtroEscolhido = chave;
          marcarBotoes();
          // Muda número: as curvas e a tabelinha voltam ao servidor.
          recarregar();
        });
        linha.title = so_um
          ? `${explicacao} — é o único filtro que o OscLab tem hoje.`
          : explicacao;
        const texto = criar("span", "texto-do-filtro");
        const titulo = criar("span", "nome-do-filtro", rotulo);
        if (quem) titulo.append(criar("span", "quem-usa", quem));
        texto.append(titulo);
        if (resumo) texto.append(criar("span", "resumo-do-filtro", resumo));
        linha.append(marca, texto);
        caixa.append(linha);
      }
    });
  }

  function marcarBotoes() {
    const qualVisao = VISOES.find(([c]) => c === visaoDeAnalise) || VISOES[0];
    const botaoDoModo = document.getElementById("modo");
    if (botaoDoModo) {
      botaoDoModo.textContent = qualVisao[1];
      // O ícone acompanha o modo: senoide limpa no tradicional, senoide com o
      // harmônico por cima no avançado. É a diferença entre os dois escrita
      // em desenho — o tradicional mostra o que sai do filtro, o avançado
      // mostra também o bruto. Vai no `style` porque o ícone é máscara de
      // CSS, e não filho do botão: `textContent`, na linha acima, apagaria um
      // filho.
      botaoDoModo.classList.add("com-icone");
      botaoDoModo.style.setProperty(
        "--ic", visaoDeAnalise === "avancado"
                  ? "var(--ic-avancado)" : "var(--ic-tradicional)");
      // Sem destaque no «avançado». O destaque de um botão desta barra quer
      // dizer «isto está LIGADO» — é o que o ímã e o filtro fazem com ele. O
      // modo não liga nada: ele é uma chave de duas posições, e o rótulo do
      // próprio botão já diz em qual delas está. Pintado, o avançado parecia
      // um estado de exceção, quando é só a outra metade da chave.
      botaoDoModo.classList.remove("escolhido");
      botaoDoModo.setAttribute("aria-pressed",
                               String(visaoDeAnalise === "avancado"));
      botaoDoModo.title = `Modo ${qualVisao[1]}: ${qualVisao[2]} Clique para `
                        + "trocar.";
    }
    const setaDoModo = document.getElementById("seta-do-modo");
    if (setaDoModo) setaDoModo.title = `Modo de análise: ${qualVisao[1]}.`;

    const seta = document.getElementById("seta-do-ima");
    if (seta) {
      const quais = ATRACOES.filter(([c]) => atracoes.has(c))
                            .map(([, r]) => r).join(", ");
      seta.title = `O ímã está grudando em: ${quais}. Clique para escolher.`;
    }
    const ima = document.getElementById("ima");
    if (ima) {
      ima.classList.toggle("escolhido", magnetico);
      ima.setAttribute("aria-pressed", String(magnetico));
      const quais = ATRACOES.filter(([c]) => atracoes.has(c))
                            .map(([, r]) => r).join(", ");
      ima.title = magnetico
        ? `Ímã aceso: o cursor gruda no ponto mais próximo entre ${quais}. `
          + "Clique para soltá-lo; use a setinha para escolher em que ele gruda."
        : "Clique para o cursor grudar nos pontos notáveis. Com um sinal "
          + "selecionado, ele obedece só a esse sinal; a setinha ao lado "
          + "escolhe em que tipo de ponto ele gruda.";
    }

    const travado = filtroTravado();
    // Aceso porque o sinal ESTÁ filtrado, e mesmo assim `filtro` continua
    // falso: é o pedido que a tela manda ao servidor, e pedir o filtro num
    // registro já filtrado o faria filtrar de novo — mais um ciclo de atraso
    // em tudo que se lê. O servidor também se defende disso (`sinais.aplicavel`),
    // mas o estado da tela tem que ser honesto por conta própria.
    const aceso = filtro || travado;
    const botao = document.getElementById("filtro");
    if (!botao) return;
    botao.classList.toggle("escolhido", aceso);
    botao.setAttribute("aria-pressed", String(aceso));
    botao.disabled = travado;
    const qual = (FILTROS.find(([c]) => c === filtroEscolhido) || FILTROS[0])[1];
    // O botão se chama «Filtro», e não «aplicar filtro»: ele já vem aceso, e
    // um verbo no imperativo descreveria o contrário do estado inicial. Quem
    // diz se está ligado é o aceso; qual filtro é, a setinha.
    botao.title = travado
      ? "Este registro já vem filtrado do relé, e não há como desfiltrá-lo."
      : (filtro
        ? `Filtro ${qual} aplicado — é o que a análise usa. Clique para ver a `
          + "onda como o relé gravou, e a tela passa para o modo avançado: é "
          + "nessa onda que aparecem a assimetria da falta, a saturação do TC "
          + "e o instante exato do trip, que o filtro não mostra."
        : `A onda como o relé gravou, sem filtro. Clique para aplicar o `
          + `${qual} — o mesmo que o relé roda por dentro. Ele atrasa até um `
          + "ciclo nas transições; a setinha ao lado diz qual filtro é.");

    const setaFiltro = document.getElementById("seta-do-filtro");
    if (setaFiltro) {
      // A setinha continua viva no modo tradicional: QUAL filtro se usa é uma
      // escolha legítima ali; o que o modo prende é ligar e desligar.
      setaFiltro.disabled = travado;
      setaFiltro.title = `O filtro aplicado é ${qual}.`;
    }
  }

  /** A tira de cima: a taxa de amostragem, quando ela não é uma só.
   *
   * Não é erro — a norma permite, e é o que o relé faz para não gerar arquivo
   * gigante: grava a falta fino e o resto grosso. Mas muda como se lê o
   * gráfico, porque cada trecho tem a sua janela de um ciclo e há um pedaço
   * sem curva em cada fronteira. Quem não for avisado vai achar que é defeito.
   */
  function mostrarTaxa() {
    const alvo = document.getElementById("taxa-variavel");
    if (!alvo || !dados) return;
    alvo.hidden = !dados.taxa_variavel;
    if (!dados.taxa_variavel) return;
    // Sem separador de milhar: "5760 Hz" é taxa de amostragem, não quantidade.
    const taxas = (dados.trechos || []).map((t) => `${formatar(t.taxa_hz, 0, false)} Hz`);
    //: O rótulo da ficha ja' diz "taxa variável" — o valor so' lista.
    alvo.textContent = taxas.join(" · ");
    alvo.title = "Este registro muda de taxa de amostragem no meio. Cada trecho "
      + "tem a sua janela de um ciclo, e por isso há um pedaço sem curva logo "
      + "depois de cada troca — uma janela com metade das amostras de um lado e "
      + "metade do outro não seria um ciclo de coisa nenhuma.";
  }

  /** A tira de cima: o que o ARQUIVO é, que não é escolha de ninguém.
   *
   * **`bruto` não aparece.** Ele é o caso comum — todo COMTRADE do parque cai
   * nele —, e um aviso que aparece sempre deixa de ser lido. O que aparece é o
   * que MUDA o que se pode fazer: `filtrado` trava o botão do filtro, e
   * `desconhecido` diz que o programa não conseguiu decidir e por isso deixou
   * o botão livre.
   *
   * O diagnóstico continua sendo medido do mesmo jeito (distorção harmônica em
   * trecho de amplitude parada, `analysis/filtragem.py`) — o que mudou é só
   * quando ele é escrito na tela.
   */
  function mostrarFiltragem() {
    const alvo = document.getElementById("filtragem");
    if (!alvo || !dados) return;
    const deduzido = dados.filtragem_origem === "deduzido";
    //: O rótulo da ficha e' "gravação"; o valor nao repete a palavra.
    const texto = {
      // Curto e técnico, pedido dele em 21/10/2026: quem filtrou e como se
      // soube vão para o hover.
      filtrado: "já filtrada",
      desconhecido: "indeterminada",
    }[dados.filtragem];
    alvo.hidden = !texto;
    if (!texto) return;
    alvo.textContent = texto;
    alvo.title = (deduzido ? "(deduzido, não declarado pelo arquivo) " : "")
      + (dados.filtragem === "filtrado"
      ? "Este registro já contém só a componente de 60 Hz, filtrada pelo "
        + "próprio relé. Por isso o botão do filtro está travado: filtrar de "
        + "novo não limparia nada, só acrescentaria mais um ciclo de atraso."
      : "Deduzido da distorção medida nos trechos em que a amplitude está "
        + "parada. Rede real sempre tem algum harmônico; sinal filtrado não "
        + "tem nenhum. Não deu para decidir se é bruta ou filtrada, e por isso "
        + "o botão do filtro ficou livre.");
  }

  /** "SEM SINAL  3 canais · mostrar na tela" — e o clique que os traz de volta.
   *
   * O arranjo padrão não desenha a trinca de reserva: um relé tem mais
   * entradas do que a instalação usa, e sem isto um SEL-451 de alimentador
   * abre com seis correntes, três delas sendo uma reta em zero.
   *
   * Mas esconder só é aceitável enquanto for **visível e reversível**. Um
   * transformador energizado por um lado só tem a trinca do outro lado em zero
   * legitimamente, e não há como distinguir isso de uma entrada aberta olhando
   * um registro só — ver `analysis/presenca.py`. Por isso o aviso fica na tira
   * de cima, do lado do que o arquivo é, e não escondido num menu.
   */
  function mostrarSemSinal() {
    const alvo = document.getElementById("sem-sinal");
    if (!alvo || !dados) return;
    const fora = dados.sem_sinal || [];
    alvo.hidden = fora.length === 0;
    if (!fora.length) return;

    alvo.replaceChildren();
    //: Sem repetir "sem sinal": e' o rótulo da ficha, logo antes.
    const quantos = criar("span", "atencao",
      `${fora.length} ${fora.length > 1 ? "canais" : "canal"}`);
    quantos.title = `${fora.map((x) => x.nome).join(", ")} — entradas do relé `
      + "que não estão lendo nada além do ruído do conversor, e por isso não "
      + "entraram nos gráficos. Continuam inteiras no buscador de sinais.";
    alvo.append(quantos, document.createTextNode(" · "));

    const botao = criar("button", "link", "mostrar na tela");
    botao.type = "button";
    botao.title = "Põe estes canais num gráfico — cada um no da unidade dele, "
                + "e num gráfico «Reserva» novo quando não houver. Eles não "
                + "entraram sozinhos porque não estão lendo nada além do ruído "
                + "do conversor; mostrá-los é como se confere que a entrada "
                + "está mesmo aberta.";
    botao.addEventListener("click", () => devolverOsSemSinal());
    alvo.append(botao);
  }

  /** Devolve ao gráfico os canais que o arranjo padrão deixou de fora. */
  async function devolverOsSemSinal() {
    const fora = (dados && dados.sem_sinal) || [];
    if (!fora.length) return;
    guardarParaDesfazer();
    //: Onde o primeiro deles caiu. O botão some depois do clique — os canais
    //: deixaram de estar fora do arranjo —, e sem nada mais acontecendo na
    //: tela o gesto se lê como «não fez nada»: o gráfico que os recebeu pode
    //: estar seis painéis abaixo, fora da vista.
    let primeiro = null;

    for (const canal of fora) {
      // O painel da MESMA unidade do arquivo — misturar ampère com kV num
      // gráfico é decisão de quem analisa, nunca de um botão de conveniência.
      const doServidor = (dados.paineis || []).find(
        (p) => p.tipo === "analogico" && p.unidade_do_arquivo === canal.unidade);
      let alvo = doServidor && painelPorId(doServidor.id);
      if (!alvo) {
        alvo = { id: `t${proximoId++}`, tipo: "analogico",
                 nome: `Reserva (${canal.unidade})`, sinais: [],
                 medida: "instantaneo", do_padrao: false, cores: {} };
        paineis.push(alvo);
      }
      if (!alvo.sinais.includes(canal.id)) alvo.sinais = [...alvo.sinais, canal.id];
      if (primeiro === null) primeiro = alvo.id;
    }
    // O aviso some sozinho: os canais deixaram de estar fora do arranjo, e o
    // próximo pacote traz a lista já vazia.
    await carregar();
    const bloco_ = blocos.find((b) => b._painel && b._painel.id === primeiro);
    if (bloco_) bloco_.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  visaoDeAnalise = lerGuardado("osclab:catalogo:visao",
                               VISOES.map(([c]) => c), "tradicional");
  // O modo manda no filtro desde a abertura: um `osclab:filtro` apagado,
  // guardado numa sessão antiga, abriria o tradicional com a onda crua.
  if (visaoDeAnalise === "tradicional" && !filtro) {
    filtro = true;
    guardar("osclab:filtro", "1");
  }
  ligarNomeDoRegistro();
  document.getElementById("modo")?.addEventListener("click", alternarVisao);
  document.getElementById("seta-do-modo")
    ?.addEventListener("click", abrirMenuDaVisao);
  document.getElementById("filtro")?.addEventListener("click", alternarFiltro);
  document.getElementById("ima")?.addEventListener("click", alternarIma);
  // O dicionário chega uma vez, no fim do carregamento: é ele que acende as
  // opções por categoria na engrenagem das digitais.
  carregarDicionario();
  document.getElementById("seta-do-ima")?.addEventListener("click", abrirMenuDoIma);
  document.getElementById("seta-do-filtro")
    ?.addEventListener("click", abrirMenuDoFiltro);
  marcarBotoes();

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

  //: A folga entre duas pistas, no modo empilhado.
  const FOLGA_DA_PISTA = 5;

  /** As PISTAS de um painel: uma faixa de altura por sinal, ou uma só.
   *
   * Uma função, e não dois trechos parecidos, porque DOIS lugares precisam da
   * mesma conta: quem desenha e quem decide em que traço o usuário clicou. Se
   * as duas divergirem um pixel, o clique passa a marcar o sinal de cima
   * quando se mira o de baixo — e isso não aparece em teste nenhum, só em
   * reclamação.
   *
   * Agrupado, devolve UMA pista com todos os sinais, que é o que o programa
   * sempre fez. Empilhado, uma por sinal, na ordem em que eles estão.
   *
   * A ESCALA é a mesma em todas as pistas — a do painel. Dar a cada pista a
   * sua própria escala encheria as três igualmente, e três ondas do mesmo
   * tamanho numa falta monofásica diriam que as três fases estão iguais. A
   * altura da onda é informação; normalizá-la é apagá-la.
   */
  //: O ponto tem que se distinguir do TRAÇO, que tem 1,5 px de largura: com
  //: 3,2 px de diâmetro ele era um engrossamento da linha, não uma marca. Com
  //: 4,4 px ele é visivelmente um ponto sobre a curva.
  //:
  //: O passo acompanha: abaixo dele os pontos encostam uns nos outros e viram
  //: uma faixa cheia em cima da onda, que não diz mais nada. 8 px deixa quase
  //: um diâmetro de folga entre dois pontos — é o mesmo critério de antes,
  //: sobre o ponto novo.
  const PASSO_DA_AMOSTRA = 8;
  const RAIO_DA_AMOSTRA = 2.2;

  /** Dá para marcar cada amostra neste painel, nesta janela?
   *
   * Três condições, e as três são sobre o DADO, não sobre gosto:
   *
   *   * o usuário pediu (`amostras`);
   *   * a série é amostra a amostra, e não mínimo e máximo por coluna de
   *     pixel (`dados.reduzido`) — reduzida, «a amostra» não existe para ser
   *     marcada;
   *   * cabe espaço entre elas.
   */
  function cabemAsAmostras(painel, largura) {
    const meu = painelPorId(painel.id) || {};
    if (!meu.amostras || !dados || dados.reduzido) return false;
    const quantas = (dados.tempo || []).length;
    if (quantas < 2 || largura <= 0) return false;
    return largura / (quantas - 1) >= PASSO_DA_AMOSTRA;
  }

  /** Os pontinhos, na cor e na opacidade do traço que acabou de ser feito. */
  function pintarAmostras(ctx, serie, tempo, emX, paraY, x0, x1) {
    ctx.save();
    ctx.fillStyle = ctx.strokeStyle;
    for (let i = 0; i < serie.length && i < tempo.length; i += 1) {
      const v = serie[i];
      if (v === null || v === undefined || !Number.isFinite(v)) continue;
      const x = emX(tempo[i]);
      if (x < x0 - 2 || x > x1 + 2) continue;
      ctx.beginPath();
      ctx.arc(x, paraY(v), RAIO_DA_AMOSTRA, 0, 2 * Math.PI);
      ctx.fill();
    }
    ctx.restore();
  }

  function pistasDoPainel(painel, y0, y1) {
    const sinais = painel.sinais || [];
    // O modo mora no ARRANJO da tela, não na resposta do servidor: ele não
    // muda número nenhum — os mesmos valores, arrumados de outro jeito. Por
    // isso trocar de modo não pede nada ao servidor, e entra no Ctrl+Z junto
    // com a ordem dos painéis e as cores.
    const meu = painelPorId(painel.id);
    if (!meu || !meu.empilhado || sinais.length < 2) {
      return [{ sinais, y0, y1 }];
    }
    const n = sinais.length;
    const alta = (y1 - y0 - FOLGA_DA_PISTA * (n - 1)) / n;
    // Pista de menos de 18 px não é gráfico, é risco: com oito sinais num
    // painel o empilhado deixaria de responder a pergunta que ele existe para
    // responder. Volta a agrupar, e o botão continua lá para quem quiser
    // tentar depois de tirar sinais.
    if (alta < 18) return [{ sinais, y0, y1 }];
    return sinais.map((s, k) => ({
      sinais: [s],
      y0: y0 + k * (alta + FOLGA_DA_PISTA),
      y1: y0 + k * (alta + FOLGA_DA_PISTA) + alta,
    }));
  }

  function pintar(canvas, painel, ultimo) {
    const cssLargura = canvas.parentElement.clientWidth;
    const cssAltura = ALTURA + (ultimo ? MARGEM.baixo : 8);
    const dpr = window.devicePixelRatio || 1;

    canvas.style.width = `${cssLargura}px`;
    canvas.style.height = `${cssAltura}px`;
    dimensionar(canvas, Math.round(cssLargura * dpr), Math.round(cssAltura * dpr));

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
      y1 - ((v - painel.minimo) / (painel.maximo - painel.minimo || 1)) * (y1 - y0);

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
    // As PISTAS: uma por sinal no empilhado, uma só no agrupado.
    const pistas = pistasDoPainel(painel, y0, y1);
    const empilhado = pistas.length > 1;
    //: Onde um valor cai DENTRO de uma pista. Mesma escala em todas — ver
    //: `pistasDoPainel`.
    const naPista = (pista) => (v) =>
      pista.y1 - ((v - painel.minimo) / (painel.maximo - painel.minimo || 1))
               * (pista.y1 - pista.y0);

    // A grade estava em 40 % de opacidade sobre um cinza já escuro: na prática
    // não se lia valor nenhum fora do cursor, e grade que não se lê é tinta
    // gasta. 55 % resolve sem competir com as curvas.
    //
    // E o ZERO ganhou linha própria, na cor do texto fraco em vez de mais
    // opacidade do mesmo cinza. Ele não é mais uma marcação: é a referência de
    // toda leitura de assimetria — a componente contínua de uma falta se mede
    // olhando o quanto a onda está deslocada DELE, e sem ele visível isso vira
    // estimativa a olho.
    //
    // No empilhado cada pista recebe a MESMA grade, com as mesmas marcações:
    // é o que permite comparar a altura de uma com a da outra de relance. Com
    // pistas baixas, porém, só o zero e os extremos cabem — quatro linhas em
    // 50 px viram hachura, e uma pista hachurada esconde a onda que ela
    // deveria mostrar.
    const marcacoesDaPista = (alta) => {
      if (!empilhado) return painel.marcacoes;
      const extremos = [painel.marcacoes[0],
                        painel.marcacoes[painel.marcacoes.length - 1]];
      const comZero = painel.marcacoes.includes(0) ? [0] : [];
      return alta >= 70 ? painel.marcacoes : [...extremos, ...comZero];
    };

    for (const pista of pistas) {
      const emYp = naPista(pista);
      for (const marca of marcacoesDaPista(pista.y1 - pista.y0)) {
        const y = Math.round(emYp(marca)) + 0.5;
        if (y < pista.y0 - 0.5 || y > pista.y1 + 0.5) continue;
        const ehZero = marca === 0;
        ctx.strokeStyle = ehZero ? corSuave : corLinha;
        ctx.globalAlpha = ehZero ? 0.75 : 0.55;
        ctx.beginPath();
        ctx.moveTo(x0, y);
        ctx.lineTo(x1, y);
        ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.strokeStyle = corLinha;
        // O número das BORDAS cai para DENTRO da pista, e não centrado na
        // linha. Centrado, o `−100` do pé de uma pista e o `100` do topo da
        // seguinte ficam a cinco pixels um do outro e se sobrepõem — dois
        // números empilhados onde deveria haver dois valores legíveis. Para
        // dentro, cada um sobra na faixa da pista a que pertence, e a folga
        // entre pistas pode continuar pequena.
        ctx.textBaseline = y - pista.y0 < 6 ? "top"
                         : pista.y1 - y < 6 ? "bottom" : "middle";
        ctx.fillText(formatar(marca, painel.casas), x0 - 8, y);
        ctx.textBaseline = "middle";
      }
    }

    // A unidade do eixo, na folga de cima — onde não há número nem curva.
    // Discreta de propósito: ela não é uma medida, é o que dá sentido a todas
    // as outras. Existe porque um gráfico pode misturar sinais e o título
    // deixou de dizer a unidade: `81,67` num eixo mudo se lê como 81 V quando
    // são 81 kV, e três ordens de grandeza não podem depender de memória.
    escreverUnidade(ctx, painel.unidade, x0 - 8, y0 - MARGEM.topo / 2, "right");

    // --- o segundo eixo, à direita ---------------------------------------
    //
    // Sem linha de grade própria: duas grades cruzadas na mesma área viram
    // xadrez e nenhuma das duas se lê. A grade é a da esquerda; a régua da
    // direita são os números, alinhados nas marcações DELA.
    const dir = painel.eixo_dir;
    const emYdir = (v) => dir
      ? y1 - ((v - dir.minimo) / (dir.maximo - dir.minimo || 1)) * (y1 - y0)
      : y1;
    if (dir) {
      ctx.textAlign = "left";
      for (const marca of dir.marcacoes) {
        ctx.fillText(formatar(marca, dir.casas), x1 + 8, Math.round(emYdir(marca)));
      }
      escreverUnidade(ctx, dir.unidade, x1 + 8, y0 - MARGEM.topo / 2, "left");
      ctx.textAlign = "right";
    }

    // Daqui até a moldura, tudo que se desenha depende do tempo — e com o
    // arrasto pode escorregar para fora da área do gráfico. O recorte segura.
    ctx.save();
    ctx.beginPath();
    ctx.rect(x0, y0, x1 - x0, y1 - y0);
    ctx.clip();

    // --- grade vertical (tempo) ------------------------------------------
    ctx.strokeStyle = corLinha;
    ctx.globalAlpha = 0.5;
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
    //
    // Com um sinal escolhido, os outros perdem opacidade em vez de sumirem: o
    // que se quer é destacar UM traço sem perder de vista onde ele passa em
    // relação aos vizinhos — tirar os vizinhos da tela tiraria justamente a
    // comparação que fez alguém clicar ali.
    //
    // O sinal do segundo eixo era desenhado TRACEJADO, como aviso de que a
    // altura dele não se compara com a dos outros. Saiu: desde que o gráfico
    // nunca repete cor, a cor sozinha já separa as curvas, e o tracejado
    // gastava a única variação de traço que sobrava — que vale mais guardada
    // para algo que ainda não existe. Quem está no segundo eixo continua
    // dizendo isso na legenda (`→ kV`), na tabelinha e no próprio eixo.
    const haEscolha = selecionados.some((x) => x.painel === painel.id);
    // Os pontinhos de amostra, quando ligados E quando há espaço para eles.
    // Ver `botaoDasAmostras`.
    const pontosDeAmostra = cabemAsAmostras(painel, x1 - x0);
    ctx.lineJoin = "round";
    for (const pista of pistas) {
      const emYp = naPista(pista);
      for (const sinal of pista.sinais) {
        const escolhido = estaSelecionado(painel, "sinal", sinal.id);
        ctx.save();
        ctx.globalAlpha = haEscolha && !escolhido ? 0.3 : 1;
        ctx.lineWidth = escolhido ? 2.6 : 1.4;
        ctx.strokeStyle = corDoSinal(sinal, painel);
        // O segundo eixo continua sendo do PAINEL, não da pista: ele existe
        // para abrigar uma unidade diferente, e isso não muda com o arranjo.
        // No empilhado ele vale para a pista daquele sinal.
        const paraY = sinal.eixo === "dir"
          ? (empilhado
              ? (v) => pista.y1 - ((v - (painel.eixo_dir || painel).minimo)
                  / (((painel.eixo_dir || painel).maximo
                      - (painel.eixo_dir || painel).minimo) || 1))
                  * (pista.y1 - pista.y0)
              : emYdir)
          : emYp;
        ctx.beginPath();
        tracar(ctx, sinal.serie, tempo, emX, paraY);
        ctx.stroke();
        if (pontosDeAmostra) {
          pintarAmostras(ctx, sinal.serie, tempo, emX, paraY, x0, x1);
        }
        ctx.restore();
      }
    }
    ctx.globalAlpha = 1;

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

    // --- moldura: uma por pista -------------------------------------------
    ctx.strokeStyle = corLinha;
    ctx.lineWidth = 1;
    for (const pista of pistas) {
      ctx.strokeRect(x0 + 0.5, pista.y0 + 0.5,
                     x1 - x0 - 1, pista.y1 - pista.y0 - 1);
    }

    if (empilhado) pintarNomesDasPistas(ctx, painel, pistas, x1);

    pintarEtiquetas(ctx, emX, x0, x1, y0);
    pintarRodapeDoTempo(ctx, emX, x0, x1, y1, ultimo);
  }

  /** O eixo do tempo e a faixa de contexto — uma vez só, embaixo de tudo.
   *
   * Era código solto no fim de `pintar`, e por isso o painel de DIGITAIS não
   * tinha eixo de tempo nenhum: quando ele é o último da tela — que é o caso
   * normal, porque é onde ele nasce —, o eixo simplesmente não existia, e
   * ninguém notava porque o cursor dá o instante na tabelinha. Com o rodapé
   * numa função, os dois tipos de painel chamam o mesmo desenho.
   */
  function pintarRodapeDoTempo(ctx, emX, x0, x1, y1, ultimo) {
    if (!ultimo) return;
    ctx.save();
    ctx.font = "11px ui-monospace, Consolas, monospace";
    ctx.textBaseline = "middle";
    ctx.fillStyle = token("--suave");
    ctx.textAlign = "center";
    for (const marca of dados.marcacoes_tempo) {
      const x = emX(marca);
      if (x < x0 - 1 || x > x1 + 1) continue;   // saiu da área durante o arrasto
      ctx.fillText(formatar(paraMs(marca), casasDoTempo()), x, y1 + 13);
    }
    ctx.fillStyle = token("--tinta");
    ctx.textAlign = "left";
    ctx.fillText(
      dados.disparo_s === null ? "ms desde o início" : "ms em relação ao disparo",
      x0, y1 + 26
    );
    ctx.restore();
  }

  /** O nome de cada pista, no FIM dela.
   *
   * No fim e não na frente, porque na frente ele empurra o gráfico — e o
   * quanto empurra depende do fabricante: `IAW` da SEL contra `Current IA` do
   * Schneider deslocaria as pistas de uma distância diferente em cada
   * arquivo, e aí nem as pistas entre si nem o modo agrupado ficariam
   * alinhados. No fim, a largura do nome não entra na conta do desenho.
   *
   * Em cima ou embaixo, pelo que a ONDA está fazendo ali
   * ===================================================
   *
   * Depois do disjuntor abrir a pista fica plana e o nome pousa em cima de
   * nada — que é a razão de ele estar no fim. Mas nem todo registro abre:
   * energização, falta não eliminada, registro de carga. Nesses, um nome
   * fixado no alto cairia dentro da onda justamente na pista que alguém
   * isolou para olhar.
   *
   * Então ele mede: no último pedaço da janela, vê de que lado do meio a onda
   * se afasta mais e escreve do outro. É uma conta de duas linhas e dispensa o
   * usuário de arrastar qualquer coisa.
   */
  function pintarNomesDasPistas(ctx, painel, pistas, x1) {
    const meio = (painel.minimo + painel.maximo) / 2;
    ctx.save();
    ctx.font = "10.5px ui-monospace, Consolas, monospace";
    ctx.textBaseline = "middle";
    ctx.textAlign = "right";
    for (const pista of pistas) {
      const sinal = pista.sinais[0];
      if (!sinal) continue;
      const texto = sinal.sinal || sinal.nome || "";
      if (!texto) continue;

      const serie = sinal.serie || [];
      const desde = Math.floor(serie.length * 0.82);
      let acima = 0;
      let abaixo = 0;
      for (let i = desde; i < serie.length; i++) {
        const v = serie[i];
        if (!Number.isFinite(v)) continue;
        acima = Math.max(acima, v - meio);
        abaixo = Math.max(abaixo, meio - v);
      }
      const embaixo = acima >= abaixo;
      const y = embaixo ? pista.y1 - 10 : pista.y0 + 10;

      // A tarja: o nome tem que se ler sobre a grade, e a grade é clara o
      // bastante para engolir texto de 10 px. Semitransparente de propósito —
      // no pior caso, com a onda cheia dos dois lados, o traço ainda aparece
      // por baixo em vez de sumir atrás de um retângulo cheio.
      const largura = ctx.measureText(texto).width;
      ctx.fillStyle = token("--fundo");
      ctx.globalAlpha = 0.72;
      ctx.fillRect(x1 - largura - 12, y - 7, largura + 9, 14);
      ctx.globalAlpha = 1;
      ctx.fillStyle = corDoSinal(sinal, painel);
      ctx.fillText(texto, x1 - 7, y);
    }
    ctx.restore();
  }

  // --- a moldura do cursor ------------------------------------------------
  //
  // Nos painéis SEM eixo de tempo — fasorial, triângulo, harmônicos — o cursor
  // não tinha onde aparecer. Quem estava lendo um fasorial não sabia de que
  // instante ele era sem subir até a onda.
  //
  // A moldura é um sulco de 7 px rente à borda de cima e de baixo do painel,
  // do tamanho e no lugar do desenho dos gráficos analógicos. Enquanto não há
  // cursor ela é um detalhe do cartão; com cursor, os riscos aparecem dentro
  // dela — na MESMA coluna de pixel em que estão lá em cima.
  //
  // As etiquetas numeradas ficam ACIMA do sulco do topo, por fora: dentro de
  // 7 px não cabe número, e sem número dois riscos de cores parecidas no
  // escuro não dizem qual é o cursor 1.
  //
  // A altura das etiquetas é RESERVADA sempre, com ou sem cursor. Sem isso o
  // painel inteiro pularia 11 px a cada vez que se aperta `1` ou `Esc` — tela
  // que salta ao apertar tecla é o que cansa no uso diário.

  const SULCO = 7;

  //: Quanto a moldura que flutua fica acima do desenho. O mesmo respiro que a
  //: margem do CSS dá à moldura que está no fluxo.
  const FOLGA_DA_MOLDURA = 4;
  const ETIQUETA_DA_MOLDURA = 11;

  /** Cria o sulco de um lado do painel. `onde` é "topo" ou "rodape". */
  function molduraDoPainel(onde) {
    // `moldura-acima`/`moldura-abaixo`, e não `topo`/`rodape`: `.topo` já é o
    // cabeçalho da PÁGINA, com 20 px de respiro à esquerda e `display: flex`.
    // A moldura herdava os dois e saía vinte pixels à direita do desenho —
    // justamente o desalinhamento que ela existe para não ter.
    const caixa = criar("div", `moldura-do-cursor moldura-${onde}`);
    const tela = document.createElement("canvas");
    caixa.append(tela);
    return { caixa, tela, onde };
  }

  /** A largura e a margem esquerda do desenho dos ANALÓGICOS.
   *
   * O alinhamento é o ponto inteiro da moldura: o risco tem que cair na mesma
   * coluna de pixel do cursor lá em cima. O painel de harmônicos e o fasorial
   * têm a tabela do lado, então a largura deles NÃO é a do painel — é preciso
   * perguntar a um analógico. Sem nenhum na tela, a moldura usa a largura que
   * tem e o alinhamento vira proporcional, que é o melhor possível.
   */
  /** Quanto a onda VAI encolher quando a tabelinha do cursor aparecer.
   *
   * Zero quando ela já está na tela. Os dois números moram no CSS
   * (`--lado-da-tabelinha`, `--vao-da-tabelinha`), que é quem desenha a
   * grade; aqui só se lê.
   */
  function reservaDaTabelinha() {
    if (area.classList.contains("com-cursores")) return 0;
    const css = getComputedStyle(document.documentElement);
    const ler = (nome) => parseFloat(css.getPropertyValue(nome)) || 0;
    return ler("--lado-da-tabelinha") + ler("--vao-da-tabelinha");
  }

  function refDoDesenho() {
    for (const b of blocos) {
      if (b._painel && b._canvas && b._painel.tipo === "analogico") {
        const r = b._canvas.getBoundingClientRect();
        if (r.width <= 120) continue;
        /* A moldura usa a largura que a onda tem COM a tabelinha do cursor,
         * mesmo quando ainda não há cursor nenhum.
         *
         * Sem cursor a tabelinha não existe e a onda ocupa 282 px a mais
         * (medido) — então a moldura nascia larga, chegando quase à borda do
         * cartão, e encolhia de uma vez no instante em que o primeiro cursor
         * aparecia. Era o «fica torta, deslocada para a direita, e ao pôr o
         * cursor ela se corrige» que ele viu.
         *
         * Pela largura de DEPOIS, e não pela de agora, porque sem cursor a
         * moldura não tem nada para alinhar: ela é só um detalhe do cartão.
         * No instante em que passa a ter — o primeiro cursor —, ela já está
         * no lugar certo, e nada se mexe. */
        const largura = Math.max(120, r.width - reservaDaTabelinha());
        return { left: r.left, width: largura };
      }
    }
    return null;
  }

  function pintarMolduras(bloco) {
    //: Onde a divisória do par começa e termina: ela separa os DESENHOS, e
    //: não deve passar por cima das molduras do cursor. Quem sabe onde elas
    //: caíram é esta função — a de cima é posicionada por medida —, então é
    //: daqui que as duas distâncias vão para o CSS.
    const par = (bloco._molduras || []).map((m) => m.caixa.parentElement)
      .find((e) => e && e.classList.contains("par-com-moldura"));

    for (const m of (bloco._molduras || [])) {
      const pai = m.caixa.parentElement;
      if (!pai) continue;
      const ref = refDoDesenho();
      const L = Math.round(ref ? ref.width : pai.clientWidth);
      // E a mesma ESQUERDA, não só a mesma largura. O corpo do fasorial e o
      // dos harmônicos começam alguns pixels adiante do corpo dos analógicos
      // — grade, moldura da tela, o que for —, e vinte pixels de diferença
      // põem o risco numa coluna que não é a do cursor lá em cima, que é
      // justamente o que a moldura existe para não fazer.
      const delta = ref
        ? Math.round(ref.left - m.caixa.getBoundingClientRect().left)
        : 0;
      if (m.delta !== delta) {
        m.tela.style.marginLeft = `${delta}px`;
        m.delta = delta;
      }
      //: A etiqueta numerada mora na moldura de CIMA — menos quando não há
      //: uma: no par de fasoriais só existe a de baixo, e um cursor anônimo
      //: ali faria duvidar se é o mesmo lá de cima.
      const comEtiqueta = m.onde === "acima" || !!m.etiqueta;
      const alto = comEtiqueta ? ETIQUETA_DA_MOLDURA + SULCO : SULCO;
      //: A moldura que flutua (a de cima de um par) cai pela MEDIDA de onde
      //: os desenhos começam, e não pela ordem do HTML. Pelo mais baixo dos
      //: dois: assim ela nunca cobre um cabeçalho, mesmo que um deles quebre
      //: em duas linhas numa janela estreita.
      if (m.flutua) {
        //: Pelo CANVAS, e não pela caixa que o contém: a faixa reservada para
        //: a moldura é um `padding` dessa caixa, e medir a caixa punha a
        //: moldura ACIMA da faixa — em cima dos botões, que é o lugar de onde
        //: ela veio. O canvas é onde o desenho realmente começa.
        const desenhos = [...pai.querySelectorAll(".grafico canvas")];
        if (desenhos.length) {
          const base = pai.getBoundingClientRect().top;
          const desenho = Math.max(
            ...desenhos.map((c) => c.getBoundingClientRect().top));
          const topo = Math.round(desenho - base - alto - FOLGA_DA_MOLDURA);
          if (m.topo !== topo) {
            m.caixa.style.top = `${topo}px`;
            m.topo = topo;
          }
        }
      }
      const dpr = window.devicePixelRatio || 1;
      m.tela.style.width = `${L}px`;
      m.tela.style.height = `${alto}px`;
      dimensionar(m.tela, Math.round(L * dpr), Math.round(alto * dpr));

      const ctx = m.tela.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, L, alto);

      const x0 = MARGEM.esq;
      const x1 = L - MARGEM.dir;
      if (x1 - x0 < 60) continue;
      //: O sulco encosta no DESENHO: na moldura de cima ele fica na beirada
      //: de baixo, na de baixo fica na de cima. A etiqueta é que sai para o
      //: lado de fora, longe da onda.
      const y0 = m.onde === "acima" ? alto - SULCO : 0;

      if (par) {
        const base = par.getBoundingClientRect();
        const minha = m.caixa.getBoundingClientRect();
        const qual = m.onde === "acima" ? "--divisoria-topo" : "--divisoria-base";
        const quanto = m.onde === "acima"
          ? Math.round(minha.bottom - base.top)
          : Math.round(base.bottom - minha.top);
        if (m.corte !== quanto) {
          par.style.setProperty(qual, `${quanto}px`);
          m.corte = quanto;
        }
      }

      ctx.fillStyle = token("--cartao");
      ctx.fillRect(x0, y0, x1 - x0, SULCO);
      ctx.strokeStyle = token("--linha");
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0, y0 + 0.5);
      ctx.lineTo(x1, y0 + 0.5);
      ctx.moveTo(x0, y0 + SULCO - 0.5);
      ctx.lineTo(x1, y0 + SULCO - 0.5);
      ctx.stroke();

      if (!dados) continue;
      const onde = (t) => x0
        + ((t - dados.de) / (dados.ate - dados.de || 1)) * (x1 - x0);
      cursores.forEach((t, k) => {
        if (t === null) return;
        //: O plano complexo segue UM cursor, e a moldura dele só mostra esse.
        if (m.so !== undefined && k !== m.so) return;
        const x = Math.round(onde(t)) + 0.5;
        if (x < x0 || x > x1) return;
        const cor = token(k === 0 ? "--cursor-1" : "--cursor-2");
        ctx.strokeStyle = cor;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(x, y0);
        ctx.lineTo(x, y0 + SULCO);
        ctx.stroke();
        if (!comEtiqueta) return;
        // A etiqueta, por fora do sulco — do lado oposto ao desenho. O mesmo
        // desenho que a onda usa, para não haver duas maneiras de dizer «este
        // é o cursor 1».
        const w = 12;
        const h = ETIQUETA_DA_MOLDURA;
        const topoDaEtiqueta = m.onde === "acima" ? 0 : SULCO;
        ctx.fillStyle = cor;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x - w / 2, topoDaEtiqueta, w, h, 2);
        else ctx.rect(x - w / 2, topoDaEtiqueta, w, h);
        ctx.fill();
        ctx.fillStyle = token("--fundo");
        ctx.font = "9px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(String(k + 1), x, topoDaEtiqueta + h / 2 + 0.5);
      });
    }
  }

  /** O cursor desenhado na moldura também se PEGA e se arrasta.
   *
   * A moldura mostra onde o cursor está num painel que não tem eixo de tempo
   * — e quem vê o risco tenta movê-lo ali mesmo. Sem isto, o único jeito de
   * mexer no cursor era rolar a tela até achar um gráfico analógico, que é
   * justamente o que a moldura existe para evitar: ela nasceu para que o
   * fasorial e os harmônicos pudessem ser lidos sem perder o cursor de vista.
   *
   * A moldura não anda com o arrasto de panorama (ela não tem onda para
   * mostrar), então a conta de tempo aqui é a MESMA do desenho dela, sem
   * `arrastoPx`: o risco que o dedo pega é o risco que está na tela.
   */
  function cursorArrastavelNaMoldura(m) {
    const geometria = () => {
      const caixa = m.tela.getBoundingClientRect();
      return { caixa, x0: MARGEM.esq, x1: caixa.width - MARGEM.dir };
    };
    const emX = (g, t) => g.x0
      + ((t - dados.de) / (dados.ate - dados.de || 1)) * (g.x1 - g.x0);
    const emT = (g, x) => dados.de
      + ((x - g.x0) / (g.x1 - g.x0 || 1)) * (dados.ate - dados.de);
    //: `a` de mentira para o ímã e para a conta de segundos por pixel: as duas
    //: só perguntam a largura do desenho, e a da moldura é a mesma do
    //: analógico — é esse o trato da moldura.
    const comoArea = (g) => ({ canvas: m.tela, x0: g.x0, x1: g.x1 });
    const qualCursor = (g, x) => {
      let achado = -1;
      let menor = PEGADA;
      cursores.forEach((t, k) => {
        if (t === null) return;
        if (m.so !== undefined && k !== m.so) return;
        const d = Math.abs(emX(g, t) - x);
        if (d <= menor) { menor = d; achado = k; }
      });
      return achado;
    };

    let pego = null;

    m.tela.addEventListener("pointerdown", (evento) => {
      if (evento.button !== 0 || !dados) return;
      const g = geometria();
      const k = qualCursor(g, evento.clientX - g.caixa.left);
      if (k < 0) return;
      evento.preventDefault();
      pego = k;
      ativo = k;
      cursorNaMao = k;
      m.tela.setPointerCapture?.(evento.pointerId);
      comecouAMoverCursor();
      repintar();
    });

    m.tela.addEventListener("pointermove", (evento) => {
      if (!dados) return;
      const g = geometria();
      const x = evento.clientX - g.caixa.left;
      if (pego === null) {
        // A mãozinha só onde há risco para pegar: num sulco de 7 px, o cursor
        // de arrastar em toda a faixa prometeria um gesto que não existe.
        const sobre = qualCursor(g, x) >= 0;
        if (m.tela.style.cursor !== (sobre ? "ew-resize" : "")) {
          m.tela.style.cursor = sobre ? "ew-resize" : "";
        }
        return;
      }
      const limitado = Math.min(Math.max(x, g.x0), g.x1);
      // Pelo ímã, como na onda: o cursor que se move aqui é o mesmo de lá, e
      // dois jeitos de parar no mesmo lugar dariam dois valores diferentes.
      cursores[pego] = grudarCursor(pego, emT(g, limitado), comoArea(g));
      repintar();
      lerCursores();
    });

    const largar = (evento) => {
      if (pego === null) return;
      pego = null;
      cursorNaMao = null;
      m.tela.releasePointerCapture?.(evento.pointerId);
      terminouDeMoverCursor();
      lerCursores();
    };
    m.tela.addEventListener("pointerup", largar);
    m.tela.addEventListener("pointercancel", largar);
  }

  /** Põe as duas molduras num painel sem eixo de tempo. */
  function comMolduras(el, corpo) {
    const topo = molduraDoPainel("acima");
    const rodape = molduraDoPainel("abaixo");
    el.insertBefore(topo.caixa, corpo);
    el.append(rodape.caixa);
    el._molduras = [topo, rodape];
    for (const m of el._molduras) cursorArrastavelNaMoldura(m);
  }

  // --- a barra da onda ----------------------------------------------------
  //
  // O que ela resolve
  // =================
  //
  // Mover um cursor é um gesto que se faz OLHANDO a onda: pára-se no pico, no
  // zero, na primeira meia-onda depois do disparo. Mas a tela de uma
  // oscilografia é alta — algumas centenas de digitais, dois fasoriais, o
  // espectro — e o gráfico analógico sai por cima. Quem está lá embaixo mexe o
  // cursor às cegas e tem que subir para conferir onde ele parou.
  //
  // A barra é o ESPELHO desse gráfico enquanto o cursor anda: a mesma janela,
  // as mesmas colunas, as mesmas cores, a mesma medida. Ela não escolhe nada
  // por conta própria, e isso é a regra, não uma economia: se ela e o gráfico
  // discordassem, não haveria como saber qual dos dois acreditar.
  //
  // Quando ela aparece
  // ==================
  //
  // Enquanto um cursor está sendo movido E nenhum gráfico analógico está na
  // tela. As duas condições são necessárias: fora do movimento ela é tinta
  // gasta, e com a onda à vista ela é a mesma onda duas vezes.
  //
  // Qual gráfico ela mostra
  // =======================
  //
  // O PRIMEIRO analógico com sinal, de cima para baixo. Com a barra na tela,
  // `Tab` passa para o seguinte e volta ao primeiro no fim da volta — porque
  // numa tela com correntes e tensões a pergunta «onde estou» às vezes é da
  // tensão. O `Tab` só é interceptado enquanto a barra está visível; fora
  // disso ele continua sendo a tecla de navegação do navegador.
  //
  // Sempre AGRUPADA
  // ===============
  //
  // Mesmo com o painel em «um sinal por gráfico». Quarenta e quatro pixels não
  // comportam três pistas: com catorze pixels cada, nenhuma mostra forma de
  // onda nenhuma — e forma é a única coisa que a barra tem para dizer. É a
  // única divergência que ela se permite do painel que espelha, e é
  // geométrica, não uma escolha de conteúdo.

  //: A onda da barra, e o rodapé do tempo embaixo dela.
  const ONDA_DA_BARRA = 44;
  const EIXO_DA_BARRA = 15;

  //: Depois do último passo de teclado, quanto a barra ainda fica. Com o
  //: mouse não é preciso: o `pointerup` diz exatamente quando o gesto acabou.
  const BARRA_SOME_EM = 900;

  let movendoCursor = false;

  //: Há plano de impedância na tela? Só ele repinta quando o cursor começa e
  //: para de se mexer, e perguntar antes evita uma repintura da tela inteira
  //: a cada gesto nas telas que não têm nenhum.
  const temPlanoDeImpedancia = () =>
    (dados && dados.paineis || []).some((x) => x.tipo === "impedancia");
  let somePendente = null;
  //: Qual analógico a barra espelha, entre os que têm sinal. O `Tab` anda
  //: nele. Zero é o primeiro da tela, que é o padrão.
  let qualNaBarra = 0;
  let barra = null;

  /** Os painéis analógicos DESENHADOS que têm sinal, na ordem da tela.
   *
   * Com sinal porque um painel vazio não tem onda para espelhar, e a barra
   * mostrando um retângulo vazio se lê como defeito.
   */
  function analogicosDaBarra() {
    return blocos.filter((b) => b._painel && b._canvas
                             && b._painel.tipo === "analogico"
                             && (b._painel.sinais || []).length);
  }

  /** Algum analógico está à vista? Então a barra não tem o que fazer.
   *
   * METADE da altura, e não um pixel: um gráfico que aparece pela borda com
   * dez pixels de altura não ajuda ninguém a se localizar, e a barra tem que
   * entrar justamente aí. O teto de 160 px é para o painel mais alto que a
   * janela, em que metade da altura pode nunca caber na tela.
   */
  function algumAnalogicoNaTela() {
    const alto = window.innerHeight || document.documentElement.clientHeight;
    return analogicosDaBarra().some((b) => {
      const r = b.getBoundingClientRect();
      const visivel = Math.min(r.bottom, alto) - Math.max(r.top, 0);
      return visivel >= Math.min(r.height / 2, 160);
    });
  }

  function barraCabe() {
    return movendoCursor && analogicosDaBarra().length > 0
        && !algumAnalogicoNaTela();
  }

  function montarBarra() {
    if (barra) return barra;
    const caixa = criar("div", "barra-da-onda");
    const topo = criar("div", "topo-da-barra");
    const nome = criar("b", "nome-da-barra");
    const legenda = criar("span", "legenda-da-barra");
    const dica = criar("span", "dica-da-barra", "Tab");
    dica.title = "Tab troca qual gráfico analógico a barra mostra.";
    const leitura = criar("span", "leitura-da-barra");
    topo.append(nome, legenda, dica, leitura);
    const tela = document.createElement("canvas");
    caixa.append(topo, tela);
    document.body.append(caixa);
    barra = { caixa, nome, legenda, dica, leitura, tela };
    return barra;
  }

  /** Mostra, esconde e redesenha. Chamada do mesmo lugar que o resto do
   *  desenho, para que a barra ande junto com o cursor e não atrás dele. */
  function atualizarBarra() {
    if (!barraCabe()) {
      if (barra) barra.caixa.classList.remove("aberta");
      return;
    }
    // Só abre se houve o que pintar: uma barra vazia deslizando para dentro
    // da tela se lê como defeito.
    if (pintarBarra()) barra.caixa.classList.add("aberta");
    else if (barra) barra.caixa.classList.remove("aberta");
  }

  function comecouAMoverCursor() {
    movendoCursor = true;
    clearTimeout(somePendente);
    somePendente = null;
    // O plano de impedância acende os pontos da trajetória enquanto a mão
    // está no cursor — ver `pintarImpedancia`. Como `movendoCursor` muda
    // fora do desenho, a transição precisa pedir a repintura; sem isto os
    // pontos só apareceriam no gesto seguinte.
    if (temPlanoDeImpedancia()) repintar();
  }

  /** `BARRA_SOME_EM` para o teclado, `0` para o mouse — ver a constante. */
  function terminouDeMoverCursor(atraso = 0) {
    clearTimeout(somePendente);
    const fechar = () => {
      movendoCursor = false;
      somePendente = null;
      if (barra) barra.caixa.classList.remove("aberta");
      if (temPlanoDeImpedancia()) repintar();
    };
    if (atraso <= 0) fechar();
    else somePendente = setTimeout(fechar, atraso);
  }

  function pintarBarra() {
    const lista = analogicosDaBarra();
    if (qualNaBarra >= lista.length) qualNaBarra = 0;
    const bloco_ = lista[qualNaBarra];
    const painel = bloco_._painel;
    const ref = bloco_._canvas.getBoundingClientRect();
    const L = Math.round(ref.width);
    if (L < 120) return false;

    const b = montarBarra();
    // A barra ocupa exatamente o lugar do canvas que ela espelha: mesma
    // esquerda e mesma largura. É o que faz o risco do cursor cair na MESMA
    // coluna de pixel que ele ocupa no gráfico grande — com outra largura, a
    // posição viraria apenas proporcional, e o olho não liga uma coisa à
    // outra sozinho.
    b.caixa.style.left = `${Math.round(ref.left)}px`;
    b.caixa.style.width = `${L}px`;
    b.nome.textContent = painel.nome;
    b.dica.hidden = lista.length < 2;

    b.legenda.replaceChildren();
    for (const sinal of painel.sinais) {
      const item = criar("span", "sinal-da-barra");
      const cor = criar("i");
      cor.style.background = corDoSinal(sinal, painel);
      item.append(cor, criar("span", null, sinal.sinal || sinal.nome || ""));
      b.legenda.append(item);
    }

    const casas = casasDoTempo();
    const pedacos = [];
    cursores.forEach((t, k) => {
      if (t === null) return;
      pedacos.push(`<b class="c${k + 1}">${k + 1}</b> ${formatar(paraMs(t), casas)}`);
    });
    if (cursores[0] !== null && cursores[1] !== null) {
      pedacos.push(`<b>Δ</b> ${formatar(Math.abs(paraMs(cursores[1])
                                               - paraMs(cursores[0])), casas)}`);
    }
    b.leitura.innerHTML = `${pedacos.join(" ")} ms`;

    const A = ONDA_DA_BARRA + EIXO_DA_BARRA;
    const dpr = window.devicePixelRatio || 1;
    b.tela.style.width = `${L}px`;
    b.tela.style.height = `${A}px`;
    dimensionar(b.tela, Math.round(L * dpr), Math.round(A * dpr));

    const ctx = b.tela.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, L, A);

    const x0 = MARGEM.esq;
    const x1 = L - MARGEM.dir;
    const y0 = 1;
    const y1 = ONDA_DA_BARRA - 1;
    if (x1 - x0 < 60) return false;

    const emX = (t) =>
      x0 + ((t - dados.de) / (dados.ate - dados.de || 1)) * (x1 - x0) + arrastoPx;
    const escala = (eixo) => {
      const e = eixo === "dir" && painel.eixo_dir ? painel.eixo_dir : painel;
      return (v) => y1 - ((v - e.minimo) / (e.maximo - e.minimo || 1)) * (y1 - y0);
    };

    ctx.fillStyle = token("--cartao");
    ctx.fillRect(x0, y0, x1 - x0, y1 - y0);

    ctx.save();
    ctx.beginPath();
    ctx.rect(x0, y0, x1 - x0, y1 - y0);
    ctx.clip();

    ctx.strokeStyle = token("--linha");
    ctx.globalAlpha = 0.5;
    ctx.lineWidth = 1;
    for (const marca of dados.marcacoes_tempo) {
      const x = Math.round(emX(marca)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // O zero, quando ele está na faixa desenhada: é dele que se mede
    // assimetria, e sem ele a onda da barra flutua sem referência.
    if (painel.minimo < 0 && painel.maximo > 0) {
      const y = Math.round(escala("esq")(0)) + 0.5;
      ctx.strokeStyle = token("--suave");
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    if (dados.disparo_s !== null
        && dados.disparo_s >= dados.de && dados.disparo_s <= dados.ate) {
      const x = Math.round(emX(dados.disparo_s)) + 0.5;
      ctx.save();
      ctx.strokeStyle = token("--destaque");
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
      ctx.stroke();
      ctx.restore();
    }

    // UMA pista para todos os sinais — ver o cabeçalho desta seção.
    ctx.lineJoin = "round";
    ctx.lineWidth = 1.1;
    for (const sinal of painel.sinais) {
      ctx.strokeStyle = corDoSinal(sinal, painel);
      ctx.beginPath();
      tracar(ctx, sinal.serie, sinal.tempo || dados.tempo, emX, escala(sinal.eixo));
      ctx.stroke();
    }

    cursores.forEach((t, k) => {
      if (t === null) return;
      const x = Math.round(emX(t)) + 0.5;
      if (x < x0 - 1 || x > x1 + 1) return;
      ctx.strokeStyle = token(k === 0 ? "--cursor-1" : "--cursor-2");
      ctx.lineWidth = k === ativo ? 2 : 1.2;
      ctx.beginPath();
      ctx.moveTo(x, y0);
      ctx.lineTo(x, y1);
      ctx.stroke();
    });
    ctx.restore();

    ctx.strokeStyle = token("--linha");
    ctx.lineWidth = 1;
    ctx.strokeRect(x0 + 0.5, y0 + 0.5, x1 - x0 - 1, y1 - y0 - 1);

    // O eixo do tempo, com as MESMAS marcações do gráfico: é o que permite
    // ler um instante aqui sem ter o gráfico na tela.
    ctx.font = "10px ui-monospace, Consolas, monospace";
    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    ctx.fillStyle = token("--suave");
    for (const marca of dados.marcacoes_tempo) {
      const x = emX(marca);
      if (x < x0 - 1 || x > x1 + 1) continue;
      ctx.fillText(formatar(paraMs(marca), casas), x, ONDA_DA_BARRA + 8);
    }
    return true;
  }

  // --- cursores de medição ------------------------------------------------

  //: Qual cursor a MÃO está arrastando agora, ou `null`.
  //:
  //: A resposta do servidor encosta o cursor na amostra mais próxima, e ela
  //: chega alguns milissegundos atrasada. Aplicá-la no cursor que está sendo
  //: arrastado puxa a linha de volta para onde o mouse estava — um cabo de
  //: guerra que se vê como a linha se teletransportando. O arrasto do GRÁFICO
  //: já estava protegido por `arrastando.cursor`; o da moldura não existia
  //: quando aquilo foi escrito, e por isso aparecia o defeito lá.
  let cursorNaMao = null;

  /** Onde o instante `t` cai, em pixels, na área `a`. */
  const emPixel = (a, t) =>
    a.x0 + ((t - dados.de) / (dados.ate - dados.de || 1)) * (a.x1 - a.x0) + arrastoPx;

  /** Qual cursor está debaixo do ponto `x`, ou -1. */
  function cursorEm(a, x, pegada = PEGADA) {
    let achado = -1;
    let menor = pegada;
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
    // A mesma grandeza do gráfico: a tabelinha nunca mostra outra coisa.
    if (filtro) p.set("filtro", "1");
    if (filtroEscolhido !== FILTROS[0][0]) p.set("estimador", filtroEscolhido);
    cursores.forEach((t, k) => {
      if (t === null) return;
      p.set(`t${k + 1}`, String(t));
      if (passos[k]) p.set(`passo${k + 1}`, String(passos[k]));
      if (ciclos[k]) p.set(`ciclos${k + 1}`, String(ciclos[k]));
    });

    try {
      const r = await fetch(`/api/onda/${sha}/leitura?${p}`, pedidoComLayout());
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
          if (cursorNaMao === k) return;
          cursores[k] = c.t;
        });
        espelhar();
        mostrarLeitura();
        if (!ajustarEspaco()) repintar();
        // A localização segue o cursor 1: cada leitura nova refaz a conta.
        if (estadoLoc.aberta) pedirLocalizacao();
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

    // Tudo casado pelo ID DO SINAL — o mesmo id que o painel pediu. Era por
    // POSIÇÃO enquanto a tabelinha mostrava os canais do arquivo na ordem do
    // arquivo; com painéis, o mesmo canal pode estar em dois deles com medidas
    // diferentes, e posição deixou de identificar coisa nenhuma.
    const diferencas = medida && medida.entre ? (medida.entre.sinais || {}) : null;

    for (const item of celulas) {
      const { id, celas, botao } = item;
      if (item.fasorial) { escreverFasor(item, c); continue; }
      if (item.harmonicos) { escreverHarmonico(item); continue; }
      if (botao) botao.classList.remove("escolhido");
      for (const k of [0, 1]) {
        const v = c[k] && c[k].sinais ? c[k].sinais[id] : null;
        escrever(celas[k], v);
        celas[k].title = v ? emPalavras(v) : "";
      }
      escrever(celas[2], diferencas && diferencas[id]);
    }

    mostrarTempo(c);
    mostrarBasesDoPu();
    mostrarJanelasDoEspectro();
  }

  /** Tudo o que não coube nas três colunas, no hover do valor.
   *
   * A tabela mostra UMA grandeza porque largura fixa vale mais que completude.
   * Mas o resto não se perde: ângulo, DC, distorção e o instantâneo continuam
   * a um passar de mouse — inclusive quando o percentual não existe, caso em
   * que entra a DC em unidade de engenharia, que vale sempre.
   */
  function emPalavras(v) {
    const linhas = [];

    // O instantâneo é a impressão digital da amostra: é por ele que se confere
    // com o SIGRA se os dois programas estão no mesmo ponto do arquivo. Some
    // da tabela quando o gráfico está em fundamental ou RMS, então fica aqui.
    const atual = v.grandeza || "instantaneo";
    if (atual !== "instantaneo" && v.instantaneo !== null) {
      linhas.push(`Instantâneo ${formatar(v.instantaneo, v.casas_instantaneo)} `
                + `${v.unidade} nesta amostra`);
    }
    if (atual !== "fundamental" && v.fundamental !== null) {
      linhas.push(`Fundamental ${formatar(v.fundamental, v.casas_fasor)} ${v.unidade}`);
    }
    if (atual !== "rms" && v.rms !== null) {
      linhas.push(`RMS verdadeiro ${formatar(v.rms, v.casas_rms)} ${v.unidade}`);
    }
    if (v.angulo !== null) linhas.push(`Ângulo ${formatar(v.angulo, 1)}°`);

    if (v.dc_valor !== null && v.dc_valor !== undefined) {
      const dc = `DC ${formatar(v.dc_valor, v.casas_dc)} ${v.unidade}`
               + " (média do ciclo que termina no cursor)";
      linhas.push(v.dc !== null ? `${dc} — ${formatar(v.dc, 1)} % da fundamental`
        : `${dc}. Sem percentual: a fundamental aqui é pequena demais para `
          + "servir de referência, e dividir por ela daria um número enorme e "
          + "sem significado.");
    }
    if (v.distorcao !== null) {
      linhas.push(`Distorção ${formatar(v.distorcao, 1)} % da fundamental `
                + "(tudo que não é 60 Hz)");
    }
    return linhas.join("\n");
  }

  /** As duas células de um sinal no painel lateral do fasorial.
   *
   * Módulo em unidade de engenharia — o pu é do DESENHO, onde ele serve para
   * tensão e corrente caberem no mesmo círculo; aqui o que se copia para um
   * laudo é o ampère. O ângulo é o do painel, já referido ao zero escolhido
   * nele.
   */
  function escreverFasor(item, cursores) {
    const painel = painelPorId(item.painel) || {};
    const k = painel.cursor === 2 ? 1 : 0;
    const lido = cursores[k];
    const valores = lido && lido.sinais ? lido.sinais : null;
    const v = valores ? valores[item.id] : null;

    if (item.botao) {
      item.botao.classList.toggle("escolhido",
                                  painel.referencia === item.referencia);
    }
    const temModulo = v && v.fundamental !== null && v.fundamental !== undefined;
    item.celas[0].textContent = temModulo
      ? formatar(v.fundamental, v.casas_fasor) : "—";
    item.celas[0].classList.toggle("vazio-valor", !temModulo);
    item.celas[0].title = v ? emPalavras(v) : "";

    const angulo = anguloNoPainel({ id: item.painel }, item.id, valores);
    item.celas[1].textContent = angulo === null ? "—"
      : `${formatar(angulo, 1, false)}°`;
    item.celas[1].classList.toggle("vazio-valor", angulo === null);
    item.celas[1].title = painel.referencia
      ? "Ângulo medido a partir do sinal marcado nesta lista."
      : "Ângulo medido a partir da referência automática: a tensão da fase A.";
  }

  function escrever(celula, v) {
    const tem = v && v.valor !== null && v.valor !== undefined;
    celula.textContent = tem
      ? formatar(v.valor, v.casas, v.agrupar !== false) + (v.sufixo || "") : "—";
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

  /** A área de desenho sob o PONTO do clique, e não sob o alvo dele.
   *
   * No `click` que fecha um gesto do ponteiro, o alvo NÃO é o canvas: a
   * captura de ponteiro manda o evento para a área inteira. `areaDoEvento`
   * devolvia `null` ali, `noDesenho(null)` dava falso, e a regra de «clicou
   * fora, limpa a seleção» desfazia, no mesmo gesto, a escolha que o `soltar`
   * tinha acabado de fazer.
   *
   * O sintoma era este: clicar num traço ou numa tira digital não destacava
   * nada — só o nome da legenda funcionava. A escolha acontecia e era apagada
   * um evento depois, o que não deixava nem rastro na tela.
   *
   * É a mesma correção que o `painelEscolhido` logo acima já fazia por conta
   * própria, pela mesma razão: decidir pela posição, não pelo alvo.
   */
  function areaPelaPosicao(evento) {
    if (!dados) return null;
    for (const b of blocos) {
      const canvas = b._canvas;
      if (!canvas) continue;
      const r = canvas.getBoundingClientRect();
      if (evento.clientX < r.left || evento.clientX > r.right) continue;
      if (evento.clientY < r.top || evento.clientY > r.bottom) continue;
      return medir(canvas, evento);
    }
    return null;
  }

  function medir(canvas, evento) {
    const caixa = canvas.getBoundingClientRect();
    const x0 = MARGEM.esq;
    const x1 = caixa.width - MARGEM.dir;
    if (x1 <= x0) return null;
    return { canvas, x0, x1,
             x: evento.clientX - caixa.left,
             y: evento.clientY - caixa.top };
  }

  /** O ponteiro está DENTRO da moldura do desenho?
   *
   * A caixa do gráfico é bem maior que o desenho: ela cobre a margem dos
   * rótulos do eixo, à esquerda, e as folgas de cima e de baixo. Lá a roda do
   * mouse tem que rolar a PÁGINA — quem põe o mouse na margem para descer a
   * tela não está pedindo zoom, e a oscilografia saltando de escala nessa hora
   * é o tipo de surpresa que faz perder o ponto que se estava olhando.
   */
  /** O ponteiro está sobre a etiqueta numerada de um cursor?
   *
   * A etiqueta mora ACIMA da moldura, de propósito — por dentro ela tapava a
   * crista da onda justamente quando se põe o cursor no pico. Ela é o alvo
   * mais óbvio para pegar o cursor, então tem que continuar sendo alvo mesmo
   * ficando fora da área de desenho.
   */
  function sobreEtiqueta(a) {
    if (!a || a.x < a.x0 || a.x > a.x1) return false;
    const alto = MARGEM.topo;
    if (a.y >= alto || a.y < alto - ETIQUETA.altura - 4) return false;
    return cursorEm(a, a.x, ETIQUETA.largura) >= 0;
  }

  function noDesenho(a) {
    if (!a) return false;
    if (a.x < a.x0 || a.x > a.x1) return false;
    const bloco = blocos.find((b) => b._canvas === a.canvas);
    const embaixo = bloco && bloco._painel && bloco._painel.tipo === "digital"
      ? MARGEM.topo + Math.max(bloco._painel.tiras.length, 1) * TIRA
      : ALTURA - 4;
    return a.y >= MARGEM.topo && a.y <= embaixo;
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

  /** O painel deste canvas anda no TEMPO? Só o analógico e o digital: é só
   *  neles que ampliar e arrastar o eixo do tempo quer dizer alguma coisa. */
  function temEixoDeTempo(canvas) {
    if (!canvas || canvas._harmonicos || canvas._fasorial) return false;
    const tipo = (blocos.find((b) => b._canvas === canvas) || {})._painel?.tipo;
    return tipo === "analogico" || tipo === "digital";
  }

  area.addEventListener("wheel", (evento) => {
    const a = areaDoEvento(evento);
    // Fora da moldura do desenho a roda não é nossa: ela rola a página. Sem
    // `preventDefault`, o navegador faz o que sempre fez.
    //
    // E num painel SEM eixo de tempo (fasorial, espectro, complexo,
    // diferencial…) também não: a roda ali ampliava a oscilografia — que
    // nem está naquele gráfico — quando a mão só queria descer a página.
    // Pedido dele, 22/10/2026.
    if (!noDesenho(a) || arrastando || !temEixoDeTempo(a.canvas)) return;
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
    // O gesto começa onde a mãozinha aparece, e só lá: a margem dos rótulos e
    // as folgas da caixa não são o gráfico. Arrastar dali movia a oscilografia
    // sem que nada na tela tivesse avisado que aquilo era arrastável. A
    // exceção é a etiqueta do cursor, que mora acima da moldura e é o alvo
    // mais natural para pegá-lo.
    const naEtiqueta = sobreEtiqueta(a);
    if (!noDesenho(a) && !naEtiqueta) return;
    evento.preventDefault();

    // Um cursor debaixo do ponteiro tem prioridade sobre o arrasto do gráfico:
    // quem clicou em cima da linha quer mover a linha, não a oscilografia.
    const k = evento.shiftKey ? -1
            : (naEtiqueta ? cursorEm(a, a.x, ETIQUETA.largura) : cursorEm(a, a.x));
    if (k >= 0) {
      ativo = k;
      arrastando = { a, canvas: a.canvas, xInicial: a.x, cursor: k };
      cursorNaMao = k;
      comecouAMoverCursor();
      area.setPointerCapture?.(evento.pointerId);
      area.classList.add("no-cursor");
      repintar();
      return;
    }

    /* Painel SEM eixo de tempo não se arrasta.
     *
     * O de harmônicos tem ordem no eixo x, e o fasorial não tem eixo nenhum:
     * arrastar ali não quer dizer nada. Pior, fazia estrago — o arrasto
     * escrevia em `arrastoPx`, que é o deslocamento de PANORAMA dos gráficos
     * analógicos, e esse valor só zera no próximo `carregar()`. Então um
     * clique com dois pixels de tremor numa barra deixava `arrastoPx` em 2, e
     * daí em diante:
     *
     *   * o clique na barra seguinte era descartado pelo limiar de 4 px de
     *     `soltar`, que lê `arrastoPx` — e o usuário via "algumas barras não
     *     clicam";
     *   * os gráficos analógicos ficavam com a onda deslocada da grade.
     *
     * `marcado` deixa o gesto chegar ao `soltar` como clique parado, sem
     * passar pelo panorama.
     */
    const semEixoDeTempo = !temEixoDeTempo(a.canvas);
    arrastando = { a, canvas: a.canvas, xInicial: a.x,
                   faixa: evento.shiftKey && !semEixoDeTempo,
                   parado: semEixoDeTempo };
    if (arrastando.faixa) selecao = [a.x, a.x];
    area.setPointerCapture?.(evento.pointerId);
    area.classList.add(arrastando.faixa ? "selecionando" : "arrastando");
  });

  area.addEventListener("pointermove", (evento) => {
    if (!arrastando) {
      // Sem arrasto em curso, só se guarda onde o mouse está — é onde as
      // teclas 1 e 2 vão pôr o cursor — e se avisa que dá para pegar a linha.
      const a = areaDoEvento(evento);
      const dentro = noDesenho(a);
      const naEtiqueta = sobreEtiqueta(a);
      sobreOMouse = dentro ? instanteEm(a) : null;
      geometriaDoMouse = dentro ? a : null;
      area.classList.toggle("sobre-desenho", dentro);
      area.classList.toggle("no-cursor",
                            naEtiqueta || (dentro && cursorEm(a, a.x) >= 0));
      return;
    }

    const agora = medir(arrastando.canvas, evento);
    if (!agora) return;
    const x = agora.x;

    if (arrastando.cursor !== undefined) {
      const a = arrastando.a;
      const limitado = Math.min(Math.max(x, a.x0), a.x1);
      const solto = dados.de + (limitado - a.x0 - arrastoPx) * segundosPorPixel(a);
      cursores[arrastando.cursor] =
        grudarCursor(arrastando.cursor, solto, a);
      repintar();
      lerCursores();
      return;
    }

    if (arrastando.parado) return;      // painel sem eixo de tempo: ver acima
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
    const arrastando_parado = !!arrastando.parado;
    arrastando = null;
    area.classList.remove("arrastando", "selecionando");
    area.releasePointerCapture?.(evento.pointerId);

    if (cursor !== undefined) {
      cursorNaMao = null;
      terminouDeMoverCursor();
      lerCursores();
      return;
    }

    // Clique parado: não é gesto de navegação, é escolha de sinal. O limiar de
    // 4 px é o mesmo da faixa — mão nenhuma fica imóvel de verdade.
    // `parado` nunca mexeu em `arrastoPx`: o clique vale sempre, e não depende
    // de um valor que é de OUTRO painel.
    if (arrastando_parado || (!faixa && Math.abs(arrastoPx) < 4)) {
      const agora = medir(a.canvas, evento);
      escolherSinal(a.canvas, agora ? agora.x : xInicial,
                    evento.clientY - a.canvas.getBoundingClientRect().top,
                    evento.ctrlKey || evento.metaKey);
      return;
    }

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

  // Clicar em qualquer lugar que não seja um sinal limpa a seleção. A regra é
  // a que se espera de qualquer tela: o destaque vale enquanto se está olhando
  // para ele. Fica de fora o que TEM ação própria — a legenda, que seleciona,
  // e as janelas, que têm os próprios botões.
  document.addEventListener("click", (evento) => {
    // O gráfico escolhido para arrastar se desfaz junto, e pela mesma regra:
    // clicar FORA DELE é parar de olhar para ele. Dentro dele não — inclusive
    // no desenho, onde se está medindo o que aquele painel mostra.
    if (painelEscolhido) {
      // Pela POSIÇÃO do clique, e não pelo alvo dele: quando a mão desce num
      // canvas e sobe em outro ponto, o navegador manda o `click` para o
      // ancestral comum — que é a área inteira. Pelo alvo, medir no desenho
      // do painel escolhido o desescolhia.
      const meu = blocos.find((b) => b._painel
                                  && b._painel.id === painelEscolhido);
      const r = meu && meu.getBoundingClientRect();
      const dentro = r && evento.clientX >= r.left && evento.clientX <= r.right
                       && evento.clientY >= r.top && evento.clientY <= r.bottom;
      if (!dentro) {
        painelEscolhido = null;
        marcarPainelEscolhido();
      }
    }
    if (!selecionados.length) return;
    if (evento.target.closest(".legenda li.clicavel, dialog")) return;
    // A moldura e a barra da onda são onde se PEGA o cursor. Soltá-lo ali
    // terminava num `click` fora de qualquer desenho, e a seleção que o ímã
    // estava usando para escolher onde grudar sumia no fim do próprio gesto.
    if (evento.target.closest(".moldura-do-cursor, .barra-da-onda")) return;
    if (noDesenho(areaDoEvento(evento) || areaPelaPosicao(evento))) return;
    marcarSelecao([]);
  });

  /* Clique DUPLO dentro do desenho: destaca a tira digital sob o ponteiro.
   *
   * O nome continua sendo o alvo certeiro, mas numa tela com setenta tiras o
   * que está debaixo do olho é a barra, no meio do gráfico, e não o nome lá
   * na beirada.
   *
   * Mora AQUI, na área, e não no canvas: a captura de ponteiro do arrasto
   * leva o `click` e o `dblclick` junto para a área, e um ouvinte no canvas
   * simplesmente nunca é chamado — foi assim que a primeira versão disto não
   * fez nada. Daí também o `areaPelaPosicao`: o alvo não serve, a posição
   * serve.
   *
   * E MARCA, em vez de alternar: os dois cliques do duplo já passaram pelo
   * `soltar`, que ligou e desligou a tira. Alternar mais uma vez devolveria o
   * gesto ao ponto de partida.
   */
  area.addEventListener("dblclick", (evento) => {
    const a = areaDoEvento(evento) || areaPelaPosicao(evento);
    if (!a || !noDesenho(a)) return;
    const bloco = blocos.find((b) => b._canvas === a.canvas);
    const painel = bloco && bloco._painel;
    if (!painel || painel.tipo !== "digital") return;
    const achado = digitalPerto(painel, a.y);
    if (!achado) return;
    const acumular = evento.ctrlKey || evento.metaKey;
    marcarSelecao(acumular
      ? [...selecionados.filter((x) => !mesmoSinal(x, achado)), achado]
      : [achado]);
  });

  /* A JANELA DE AJUDA.
   *
   * O conteúdo está no HTML — é o mesmo texto em toda abertura, e montá-lo
   * aqui só esconderia as palavras da página de quem for corrigi-las. Aqui
   * ficam os três gestos: abrir, trocar de aba e fechar.
   */
  (() => {
    const janela = document.getElementById("janela-de-ajuda");
    const botao = document.getElementById("ajuda");
    if (!janela || !botao) return;

    const folhas = [...janela.querySelectorAll(".folha-da-ajuda")];
    const abas = [...janela.querySelectorAll(".aba")];
    const mostrar = (qual) => {
      for (const f of folhas) f.hidden = f.dataset.folha !== qual;
      for (const a of abas) {
        const minha = a.dataset.aba === qual;
        a.classList.toggle("escolhida", minha);
        a.setAttribute("aria-selected", minha ? "true" : "false");
      }
    };
    for (const a of abas) a.addEventListener("click", () => mostrar(a.dataset.aba));

    botao.addEventListener("click", () => janela.showModal());
    document.getElementById("fechar-ajuda")
      ?.addEventListener("click", () => janela.close());
    // Clique no escuro em volta fecha. O `<dialog>` entrega o clique do fundo
    // como se fosse dele mesmo, então o que distingue é a POSIÇÃO.
    janela.addEventListener("click", (evento) => {
      const r = janela.getBoundingClientRect();
      const dentro = evento.clientX >= r.left && evento.clientX <= r.right
                  && evento.clientY >= r.top && evento.clientY <= r.bottom;
      if (!dentro) janela.close();
    });
  })();

  // Sair da área leva a mãozinha junto: cursor de arrastar parado sobre um
  // lugar que não arrasta é promessa que a tela não cumpre.
  area.addEventListener("pointerleave", () => {
    if (arrastando) return;
    area.classList.remove("sobre-desenho", "no-cursor");
    sobreOMouse = null;
  });

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
    if (!dados) return;
    // Digitando num campo, as teclas são do campo. Sem isto, renomear um
    // gráfico com um número no nome era impossível: o `1` ia parar no cursor
    // de medição e nunca chegava ao texto — e o Delete apagava sinal em vez
    // de letra.
    const alvo = evento.target;
    if (alvo && (alvo.tagName === "INPUT" || alvo.tagName === "TEXTAREA"
                 || alvo.isContentEditable)) {
      return;
    }

    // Ctrl+Z desfaz a última mudança do que está na tela: sinal tirado, sinal
    // acrescentado, digital escondido. Não desfaz correção de fase — aquilo é
    // dado gravado, e se desfaz no próprio lápis.
    if (evento.key === "Escape" && painelEscolhido) {
      painelEscolhido = null;
      marcarPainelEscolhido();
      // Segue adiante: o Esc também tira os cursores, e quem apertou
      // provavelmente quer as duas coisas.
    }

    if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === "z") {
      if (!desfazer.length) return;
      evento.preventDefault();
      desfazerUltimo();
      return;
    }

    if (evento.ctrlKey || evento.altKey || evento.metaKey) return;

    if (evento.key === "1" || evento.key === "2") {
      const k = evento.key === "1" ? 0 : 1;
      evento.preventDefault();
      const onde = sobreOMouse ?? (dados.de + dados.ate) / 2;
      // Apertar de novo com o mouse parado em cima do cursor tira o cursor.
      const jaEstava = cursores[k] !== null && sobreOMouse !== null &&
        Math.abs(cursores[k] - sobreOMouse) < (dados.ate - dados.de) * 0.004;
      if (jaEstava) {
        presos[k] = null;
        porCursor(k, null);
        return;
      }
      porCursor(k, grudarCursor(k, onde, geometriaDoMouse));
      return;
    }

    // `Tab` troca qual analógico a barra espelha. Só enquanto ela está na
    // tela: fora disso ele continua sendo a tecla de navegação do navegador,
    // e sequestrá-la sempre quebraria o teclado de quem não usa mouse.
    if (evento.key === "Tab" && barraCabe()) {
      evento.preventDefault();
      const quantos = analogicosDaBarra().length;
      if (quantos > 1) {
        qualNaBarra = (qualNaBarra + (evento.shiftKey ? quantos - 1 : 1)) % quantos;
        repintar();
      }
      return;
    }

    if (evento.key === "Delete" || evento.key === "Backspace") {
      if (!selecionados.length) return;
      evento.preventDefault();
      apagarSelecionados();
      return;
    }

    if (evento.key === "Escape") {
      evento.preventDefault();
      // O Esc tira primeiro a seleção; só depois os cursores. Desfazer uma
      // coisa por vez é o que se espera de uma tecla de desistir.
      if (selecionados.length) { marcarSelecao([]); return; }
      cursores[0] = cursores[1] = null;
      presos[0] = presos[1] = null;
      terminouDeMoverCursor();
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
      // Pelo teclado não há `pointerup` que diga que o gesto acabou: a barra
      // fica mais um instante e some sozinha. Teclas seguidas renovam o prazo.
      comecouAMoverCursor();
      terminouDeMoverCursor(BARRA_SOME_EM);
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

  /* A LARGURA da área de desenho muda sem ninguém mexer na janela.
   *
   * Uma barra de rolagem aparece, uma fonte termina de carregar, a tabela de
   * um fasorial surge quando o primeiro sinal entra, um painel é apagado — e
   * a cada uma dessas o desenho passa a ter outra largura disponível. O
   * `resize` da janela não é disparado por nenhuma delas.
   *
   * O desenho, porém, foi pedido ao servidor com a largura ANTIGA: o número
   * de colunas sai dela. Até o pedido seguinte, o traço ocupa menos (ou mais)
   * que o painel, e a moldura do cursor — que copia a largura do desenho —
   * acompanha o erro. Era o que se via com nome de sinal comprido: a barra da
   * moldura parecia deslocada para a esquerda, e mexer no cursor «consertava»
   * porque aquilo refazia o pedido.
   *
   * Então aqui se faz o MESMO que o `resize` da janela faz: repinta já, para
   * o olho, e repede com a largura nova, pelo mesmo atraso de 200 ms — que é
   * o que impede um pedido por pixel enquanto algo ainda está se acomodando.
   *
   * Só a LARGURA conta. A altura da área muda em toda pintura, e reagir a ela
   * seria um laço: pedir, pintar, pedir de novo.
   */
  if (typeof ResizeObserver === "function") {
    let larguraDaArea = Math.round(area.getBoundingClientRect().width);
    new ResizeObserver(() => {
      const larga = Math.round(area.getBoundingClientRect().width);
      if (larga === larguraDaArea) return;
      larguraDaArea = larga;
      for (const b of blocos) if (b._molduras) pintarMolduras(b);
      clearTimeout(pendente);
      pendente = setTimeout(carregar, 200);
    }).observe(area);
  }

  document.addEventListener("osclab:tema", () => {
    // As cores vêm dos tokens do CSS, então trocar o tema é só repintar — mas
    // ANTES é preciso esquecer os tokens guardados: eles são justamente o que
    // acabou de mudar, e sem esta linha o tema claro apareceria com as cores
    // do escuro. Ver `token`.
    _tokens.clear();
    if (dados) desenharTudo();
  });

  // --- localizar falta: a TELA própria ------------------------------------------
  //
  // O botão «localizar falta» troca as ondas por este painel — painel 1 da
  // maquete, escolha dele em 23/10/2026 entre gaveta larga, tela própria e
  // gráfico na lista. Duas abas: o painel principal, em três passos (alinhar
  // A × B, conferir o platô, resultado), e as simulações, que chegam na etapa 2
  // e por isso ficam TRAVADAS, com o porquê no hover.
  //
  // Toda conta é do servidor (`faultloc/ldl.py`): curvas já reduzidas por
  // coluna de pixel, escalas, marcações, a direção e o km. Aqui só se converte
  // valor em pixel.
  //
  // O cursor é o CURSOR 1 da oscilografia: clicar num gráfico daqui chama o
  // mesmo `porCursor(0, t)` da tecla 1, as setas andam com ele, e cada leitura
  // nova refaz o pedido (ver `lerCursores`).

  const telaLoc = document.getElementById("tela-localizar");
  const estadoLoc = {
    aberta: false, fonte: "auto", pacote: null, lendo: false, denovo: false,
    modoI: "seq", modoV: "seq", zoom: "lt", ligados: new Set(["seqneg", "laco"]),
    manual: { forma: "rx", r: "", x: "", r0: "", x0: "", mod: "", ang: "", mod0: "", ang0: "",
              rkm: "", xkm: "", r0km: "", x0km: "", km: "", base: "prim" },
  };
  const NOMES_DAS_FONTES = { base: "base de dados", A: "ajustes do IED A", B: "ajustes do IED B", manual: "digitada" };
  // Cores de SOBRA da paleta validada: os dois métodos não são fase de nada.
  const CORES_LOC = { seqneg: "var(--traco-2)", laco: "var(--traco-1)" };
  const htmlLoc = texto => String(texto == null ? "" : texto)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const numLoc = (v, casas) => (v == null || !isFinite(v)) ? "—"
    : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  /** Colunas de pixel DE VERDADE (ver o CLAUDE.md: pixel de CSS × devicePixelRatio). */
  const colunasLoc = (largura) => Math.max(100, Math.round(largura * (window.devicePixelRatio || 1)));

  async function pedirLocalizacao() {
    if (!estadoLoc.aberta) return;
    if (estadoLoc.lendo) { estadoLoc.denovo = true; return; }
    estadoLoc.lendo = true;
    const larga = Math.max(300, (telaLoc.clientWidth || window.innerWidth) - 60);
    try {
      const r = await fetch(`/api/onda/${sha}/localizar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          registros: outrosRegistros, alinhar: alinharPor, t: cursores[0],
          fonte: estadoLoc.fonte, manual: estadoLoc.manual,
          estimador: filtroEscolhido !== FILTROS[0][0] ? filtroEscolhido : null,
          colunas: colunasLoc(larga), colunas_ondas: colunasLoc(larga / 2 - 20),
        }),
      });
      const corpo = await r.json();
      estadoLoc.pacote = r.ok ? corpo : { aviso: corpo.erro || "falhou", metodos: {} };
    } catch (_e) {
      estadoLoc.pacote = { aviso: "o servidor não respondeu", metodos: {} };
    }
    estadoLoc.lendo = false;
    // Sem cursor 1, o servidor leu no meio do platô: o cursor 1 passa a estar
    // lá, e a oscilografia o mostra quando se voltar a ela.
    const p = estadoLoc.pacote;
    if (cursores[0] === null && p && p.cursor) porCursor(0, p.cursor.t);
    mostrarLocalizacao();
    if (estadoLoc.denovo) { estadoLoc.denovo = false; pedirLocalizacao(); }
  }

  // --- desenho: só valor → pixel --------------------------------------------

  function eixoLoc(largura) {
    const [t0, t1] = estadoLoc.pacote.janela, x0 = 58, x1 = largura - 12;
    return { x0, x1, X: t => x0 + (t - t0) / (t1 - t0) * (x1 - x0), T: x => t0 + (x - x0) / (x1 - x0) * (t1 - t0) };
  }
  /** O traço de uma série reduzida; `null` abre um buraco. */
  function caminhoLoc(E, Y, tempos, valores) {
    let d = "", aberto = false;
    for (let k = 0; k < tempos.length; k++) {
      const v = valores[k];
      if (v == null) { aberto = false; continue; }
      d += `${aberto ? "L" : "M"}${E.X(tempos[k]).toFixed(1)},${Y(v).toFixed(1)}`;
      aberto = true;
    }
    return d;
  }
  /** O platô, o início da falta e a abertura: o mesmo fundo em todo gráfico do tempo. */
  function fundoLoc(E, y0, y1, comRotulo) {
    const ev = estadoLoc.pacote.eventos || {};
    let s = "";
    if (ev.plato) {
      s += `<rect x="${E.X(ev.plato[0])}" y="${y0}" width="${Math.max(1, E.X(ev.plato[1]) - E.X(ev.plato[0]))}" height="${y1 - y0}" fill="var(--destaque)" opacity=".09"/>`;
      if (comRotulo) s += `<text x="${E.X(ev.plato[0]) + 4}" y="${y0 + 12}" style="fill:var(--destaque)">platô — daqui sai a mediana</text>`;
    }
    if (ev.inicio != null) s += `<line x1="${E.X(ev.inicio)}" y1="${y0}" x2="${E.X(ev.inicio)}" y2="${y1}" stroke="var(--ruim)" stroke-dasharray="4 3"/>`;
    if (ev.abre_a != null && ev.abre_a <= estadoLoc.pacote.janela[1]) {
      s += `<line x1="${E.X(ev.abre_a)}" y1="${y0}" x2="${E.X(ev.abre_a)}" y2="${y1}" stroke="var(--atencao)" stroke-dasharray="4 3"/>`;
      if (comRotulo) s += `<text x="${E.X(ev.abre_a) + 3}" y="${y1 - 4}" style="fill:var(--atencao)">abre A</text>`;
    }
    return s;
  }
  function marcasTempoLoc(E, y0, y1, yTexto) {
    return (estadoLoc.pacote.marcas_t || []).map(m =>
      `<line x1="${E.X(m.t)}" y1="${y0}" x2="${E.X(m.t)}" y2="${y1}" stroke="var(--linha)" stroke-dasharray="2 5"/>`
      + (yTexto ? `<text x="${E.X(m.t)}" y="${yTexto}" text-anchor="middle">${numLoc(m.ms, 0)}</text>` : "")).join("")
      + (yTexto ? `<text x="${E.x1}" y="${yTexto + 13}" text-anchor="end">ms desde o início da falta</text>` : "");
  }
  /** O cursor 1, com a etiqueta numerada acima, como na oscilografia. */
  function cursorLoc(E, y0, y1) {
    if (cursores[0] === null) return "";
    const x = E.X(cursores[0]);
    if (x < E.x0 - 1 || x > E.x1 + 1) return "";
    return `<line x1="${x}" y1="${y0}" x2="${x}" y2="${y1}" stroke="var(--cursor-1)" stroke-width="1.4"/>`
      + `<rect x="${x - 7}" y="${y0 - 13}" width="14" height="13" rx="2" fill="var(--cursor-1)"/>`
      + `<text x="${x}" y="${y0 - 3}" text-anchor="middle" style="fill:var(--fundo);font-weight:700;font-size:10px">1</text>`;
  }
  /** Um gráfico de onda do passo 1: fases ou a sequência negativa, de um IED. */
  function ondaLoc(lado, grandeza, largura, altura, comEixo) {
    const p = estadoLoc.pacote, c = p.curvas && p.curvas[lado] && p.curvas[lado][grandeza];
    if (!c) return "";
    const modo = grandeza === "I" ? estadoLoc.modoI : estadoLoc.modoV;
    const E = eixoLoc(largura), y0 = 20, y1 = altura - (comEixo ? 30 : 6);
    const esc = modo === "fases" ? c.escala_fases : c.escala_seq;
    const Y = v => y1 - (v - esc.min) / (esc.max - esc.min) * (y1 - y0);
    const serie = modo === "fases" ? c.fases : c.seq;
    let s = `<svg class="tempo" viewBox="0 0 ${largura} ${altura}" width="${largura}" height="${altura}">`;
    s += `<text x="${E.x0}" y="11" style="fill:var(--tinta);font-weight:600">${lado} · ${htmlLoc((p.nomes || {})[lado] || "")}</text>`
      + `<text x="${E.x1}" y="11" text-anchor="end">${modo === "fases" ? (grandeza === "I" ? "IA IB IC" : "VA VB VC") : (grandeza === "I" ? "I2" : "V2")}</text>`;
    s += fundoLoc(E, y0, y1, false) + marcasTempoLoc(E, y0, y1, comEixo ? altura - 16 : 0);
    (esc.marcas || []).forEach(v => {
      s += `<text x="${E.x0 - 5}" y="${Y(v) + 4}" text-anchor="end">${numLoc(v / 1000, 1)}</text>`;
    });
    s += `<text x="4" y="${y0 + 4}">${grandeza === "I" ? "kA" : "kV"}</text>`;
    if (modo === "fases") {
      ["var(--fase-a)", "var(--fase-b)", "var(--fase-c)"].forEach((cor, k) => {
        s += `<path d="${caminhoLoc(E, Y, serie.t, serie.v[k])}" fill="none" stroke="${cor}" stroke-width="1"/>`;
      });
    } else {
      s += `<path d="${caminhoLoc(E, Y, serie.t, serie.v[0])}" fill="none" stroke="var(--calculado-1)" stroke-width="1" opacity=".55"/>`
        + `<path d="${caminhoLoc(E, Y, serie.t, serie.v[1])}" fill="none" stroke="var(--calculado-1)" stroke-width="2"/>`;
    }
    return s + cursorLoc(E, y0, y1) + `</svg>`;
  }
  /** A LDL no tempo: cada método ligado, a faixa de patrulha e o platô. */
  function ldlLoc(largura, altura) {
    const p = estadoLoc.pacote, esc = estadoLoc.zoom === "perto" && p.escala_ldl_perto ? p.escala_ldl_perto : p.escala_ldl;
    if (!esc) return "";
    const E = eixoLoc(largura), y0 = 20, y1 = altura - 32;
    const Y = v => y1 - (Math.max(esc.min, Math.min(esc.max, v)) - esc.min) / (esc.max - esc.min) * (y1 - y0);
    let s = `<svg class="tempo" viewBox="0 0 ${largura} ${altura}" width="${largura}" height="${altura}">`;
    (esc.marcas || []).forEach(v => {
      s += `<line x1="${E.x0}" y1="${Y(v)}" x2="${E.x1}" y2="${Y(v)}" stroke="var(--linha)" stroke-dasharray="2 4"/>`
        + `<text x="${E.x0 - 5}" y="${Y(v) + 4}" text-anchor="end">${numLoc(v, 0)}</text>`;
    });
    s += `<text x="4" y="${y0 - 6}">km de A</text>`;
    const res = p.resultado;
    if (res) {
      const a = Y(res.km + res.faixa), b = Y(res.km - res.faixa);
      s += `<rect x="${E.x0}" y="${a}" width="${E.x1 - E.x0}" height="${Math.max(1, b - a)}" fill="var(--destaque)" opacity=".10"/>`;
    }
    s += fundoLoc(E, y0, y1, true) + marcasTempoLoc(E, y0, y1, altura - 18);
    for (const m of ["laco", "seqneg"]) {
      const c = p.ldl && p.ldl[m];
      if (!c || !estadoLoc.ligados.has(m)) continue;
      s += `<path d="${caminhoLoc(E, Y, c.t, c.v[0])}" fill="none" stroke="${CORES_LOC[m]}" stroke-width="${res && res.metodo === m ? 2.4 : 1.6}"/>`;
      const km = p.metodos[m] && p.metodos[m].km, fim = p.eventos && p.eventos.plato && p.eventos.plato[1];
      if (km != null && fim != null) s += `<text x="${E.X(fim) + 4}" y="${Y(km) - 4}" style="fill:${CORES_LOC[m]};font-weight:600">${numLoc(km, 2)}</text>`;
    }
    return s + cursorLoc(E, y0, y1) + `</svg>`;
  }
  /** A linha, com o palpite de cada método ligado e a faixa de patrulha. */
  function unifilarLoc(largura) {
    const p = estadoLoc.pacote, km = p.km_linha;
    if (!km) return "";
    const x0 = 70, x1 = largura - 70, y = 54, X = v => x0 + Math.max(-0.1, Math.min(1.1, v / km)) * (x1 - x0);
    const metodos = ["seqneg", "laco"].filter(m => estadoLoc.ligados.has(m) && p.metodos[m] && p.metodos[m].km != null);
    const altura = y + 44 + metodos.length * 18;
    let s = `<svg viewBox="0 0 ${largura} ${altura}" width="${largura}" height="${altura}">`
      + `<line x1="${x0}" y1="${y}" x2="${x1}" y2="${y}" stroke="var(--tinta)" stroke-width="3"/>`
      + `<rect x="${x0 - 9}" y="${y - 20}" width="6" height="40" fill="var(--tinta)"/><rect x="${x1 + 3}" y="${y - 20}" width="6" height="40" fill="var(--tinta)"/>`
      + `<text x="${x0 - 6}" y="${y - 30}" style="fill:var(--tinta);font-weight:600">A · ${htmlLoc((p.nomes || {}).A || "")}</text>`
      + `<text x="${x1 + 6}" y="${y - 30}" text-anchor="end" style="fill:var(--tinta);font-weight:600">${p.nomes && p.nomes.B ? "B · " + htmlLoc(p.nomes.B) : "outro terminal"}</text>`;
    const res = p.resultado;
    if (res) {
      s += `<rect x="${X(res.km - res.faixa)}" y="${y - 8}" width="${Math.max(3, X(res.km + res.faixa) - X(res.km - res.faixa))}" height="16" rx="3" fill="var(--destaque)" opacity=".3"/>`
        + `<text x="${X(res.km)}" y="${y - 12}" text-anchor="middle" style="fill:var(--destaque)">patrulhar ${numLoc(Math.max(0, res.km - res.faixa), 1)}–${numLoc(Math.min(km, res.km + res.faixa), 1)} km</text>`;
    }
    (p.escala_ldl ? p.escala_ldl.marcas : []).forEach(v => {
      s += `<line x1="${X(v)}" y1="${y + 6}" x2="${X(v)}" y2="${y + 11}" stroke="var(--linha)"/><text x="${X(v)}" y="${y + 23}" text-anchor="middle">${numLoc(v, 0)}</text>`;
    });
    metodos.forEach((m, i) => {
      const v = p.metodos[m].km, yy = y + 42 + i * 18, xv = X(v), dir = xv > largura - 220;
      const disp = p.metodos[m].dispersao || 0;
      s += `<line x1="${X(v - disp)}" y1="${yy}" x2="${X(v + disp)}" y2="${yy}" stroke="${CORES_LOC[m]}" stroke-width="4" opacity=".35" stroke-linecap="round"/>`
        + `<circle cx="${xv}" cy="${yy}" r="${res && res.metodo === m ? 6 : 4.5}" fill="${CORES_LOC[m]}"/>`
        + `<text x="${xv + (dir ? -10 : 10)}" y="${yy + 4}" text-anchor="${dir ? "end" : "start"}" style="fill:${CORES_LOC[m]}">${htmlLoc(p.metodos[m].curto)} ${numLoc(v, 2)} km</text>`;
    });
    return s + `</svg>`;
  }

  // --- as partes da tela -------------------------------------------------------

  function faixaDoResultadoLoc() {
    const p = estadoLoc.pacote, res = p.resultado;
    if (!res) {
      return `<div class="loc-resultado"><div class="bloco"><span class="rot">resultado</span>`
        + `<span class="loc-aviso">${htmlLoc(p.aviso || Object.values(p.metodos || {}).map(m => m.motivo).filter(Boolean)[0] || "nenhum método com resposta")}</span></div></div>`;
    }
    const km = p.km_linha, met = p.metodos[res.metodo];
    const conf = (res.conferencia || []).map(c => `${htmlLoc(p.metodos[c.metodo].curto)}: ${numLoc(p.metodos[c.metodo].km, 2)} km (Δ ${numLoc(c.delta, 2)} km)`).join(" · ");
    return `<div class="loc-resultado">`
      + `<div class="bloco"><span class="rot">falta a</span><span class="km">${numLoc(res.km, 2)} km</span><span class="rot">de A · ${numLoc(km - res.km, 2)} km de ${p.nomes && p.nomes.B ? "B" : "R"}</span></div>`
      + `<div class="bloco"><span class="rot">patrulhar</span><span class="km-m">${numLoc(Math.max(0, res.km - res.faixa), 1)} a ${numLoc(Math.min(km, res.km + res.faixa), 1)} km</span>`
      + `<span class="rot" title="Sem as simulações (etapa 2), a faixa é a dispersão da LDL no platô — metade da faixa de 10 a 90 % —, com mínimo de 0,3 km.">faixa = dispersão no platô (±${numLoc(res.faixa, 2)} km)</span></div>`
      + `<div class="bloco"><span class="rot">calculado por</span><span class="met"><span class="loc-bolinha" style="background:${CORES_LOC[res.metodo]}"></span>${htmlLoc(met.nome)}</span>`
      + `<span class="rot">mediana do platô${conf ? " · " + conf : ""}</span></div></div>`;
  }
  function passoLoc(n, estado, titulo, nota, corpo) {
    return `<section class="loc-sec"><h3><span class="loc-num ${estado}">${estado === "ok" ? "✓" : estado === "aviso" ? "!" : n}</span>${titulo}`
      + `${nota ? ` <span class="loc-nota">${nota}</span>` : ""}</h3>${corpo}</section>`;
  }
  const pilulaLoc = (chave, opcoes, atual) => `<span class="pilula-loc">${opcoes.map(([v, t]) =>
    `<button type="button" data-loc="${chave}" data-v="${v}" class="${atual === v ? "on" : ""}">${t}</button>`).join("")}</span>`;

  function alinhamentoLoc() {
    const p = estadoLoc.pacote, al = p.alinhamento;
    if (!p.nomes || !p.nomes.B) return { ok: false, texto: "um terminal só: a seq. negativa fica de fora" };
    if (!al) return { ok: false, texto: "sem alinhamento" };
    const nome = NOME_DO_ALINHAMENTO[al.por] || al.por;
    // A precisão que o servidor dá é UMA amostra do registro mais lento.
    const prec = al.precisao_ms != null ? `, precisão de uma amostra (${numLoc(al.precisao_ms, 2)} ms)` : "";
    return { ok: al.por === "falta", texto: `B alinhado por «${nome}»${prec}` };
  }
  function tabelaCursorLoc() {
    const c = estadoLoc.pacote.cursor;
    if (!c) return `<div class="loc-nota">Ponha o cursor 1 (tecla 1) dentro da falta.</div>`;
    const dir = l => l.frente == null ? "—" : l.frente
      ? `<b class="loc-bom">→ para a linha (frente)</b>` : `<b class="loc-aten">← para trás (reverso)</b>`;
    const linha = (letra, l) => !l ? "" : `<tr><td><span class="loc-ied ${letra === "B" ? "b" : ""}">${letra}</span> ${htmlLoc((estadoLoc.pacote.nomes || {})[letra] || "")}</td>`
      + `<td>${numLoc(l.v2 / 1000, 3)} kV ∠ 0,0° <span class="loc-nota">ref.</span></td><td>${numLoc(l.i2, 1)} A ∠ ${numLoc(l.ang, 1)}°</td><td>${dir(l)}</td></tr>`;
    const doisFrente = c.A && c.B && c.A.frente && c.B.frente;
    const algumAtras = (c.A && c.A.frente === false) || (c.B && c.B.frente === false);
    const kms = Object.entries(c.km || {}).map(([m, v]) => `${htmlLoc(estadoLoc.pacote.metodos[m].curto)} <b style="color:${CORES_LOC[m]}">${numLoc(v, 2)} km</b>`).join(" · ");
    return `<div class="loc-nota">cursor 1 em ${numLoc((c.t - ((estadoLoc.pacote.eventos || {}).inicio || 0)) * 1000, 1)} ms desde o início da falta `
      + (c.no_plato ? `<span class="loc-selo-ok">dentro do platô</span>` : `<span class="loc-selo-aviso">fora do platô — o número lido aqui não vale</span>`) + `</div>`
      + `<table><tr><th></th><th>V2 (primário) — a referência de 0°</th><th>I2 (primário) — ângulo contra V2</th><th>direção pela seq. negativa</th></tr>`
      + linha("A", c.A) + linha("B", c.B) + `</table>`
      + `<div class="loc-nota" style="margin-top:6px">`
      + (doisFrente ? `<b class="loc-bom">Os dois terminais olham para a linha: falta interna.</b> ` : "")
      + (algumAtras ? `<b class="loc-aten">Um terminal vê a falta para trás: ela pode estar fora desta linha, e a localização não vale.</b> ` : "")
      + `Com V2 na referência, falta para frente põe I2 adiantada de 180° − ∠Z2 da fonte (perto de +100°); para trás, perto de −80°.`
      + (kms ? `<br>no cursor 1: ${kms}` : "") + `</div>`;
  }
  function passo1Loc() {
    const p = estadoLoc.pacote, al = alinhamentoLoc();
    const temB = !!(p.curvas && p.curvas.B);
    const ctl = `<div class="loc-controles">${temB ? `alinhar B por ${pilulaLoc("alinhar", Object.entries(NOME_DO_ALINHAMENTO), alinharPor)}` : ""}
      correntes ${pilulaLoc("modoI", [["fases", "fases"], ["seq", "I2"]], estadoLoc.modoI)}
      tensões ${pilulaLoc("modoV", [["fases", "fases"], ["seq", "V2"]], estadoLoc.modoV)}
      <span>o <b>cursor 1</b> é o mesmo da oscilografia: clique para pô-lo · ←/→ anda uma amostra, Shift+←/→ um ciclo</span></div>`;
    const graf = `<div class="loc-duas">`
      + `<div class="loc-g" data-g="onda" data-lado="A" data-gr="I" data-h="${temB ? 112 : 140}" data-eixo="${temB ? 0 : 1}"></div>`
      + `<div class="loc-g" data-g="onda" data-lado="A" data-gr="V" data-h="${temB ? 112 : 140}" data-eixo="${temB ? 0 : 1}"></div>`
      + (temB ? `<div class="loc-g" data-g="onda" data-lado="B" data-gr="I" data-h="140" data-eixo="1"></div>`
        + `<div class="loc-g" data-g="onda" data-lado="B" data-gr="V" data-h="140" data-eixo="1"></div>` : "")
      + `</div>`;
    const nota = temB ? `<span class="${al.ok ? "loc-selo-ok" : "loc-selo-aviso"}">${htmlLoc(al.texto)}</span>`
      : `<span class="loc-selo-aviso">só o IED A: «+ adicionar oscilografia» traz o outro terminal</span>`;
    return passoLoc(1, temB && al.ok ? "ok" : "aviso", temB ? "Alinhar A × B" : "O registro de A", nota,
      ctl + graf + `<div style="margin-top:8px">${tabelaCursorLoc()}</div>`);
  }
  function passo2Loc() {
    const p = estadoLoc.pacote, c = p.cursor;
    const chips = ["seqneg", "laco"].map(m => {
      const info = p.metodos[m] || {}, sem = info.km == null;
      return `<button type="button" class="loc-chip ${estadoLoc.ligados.has(m) && !sem ? "on" : ""}" data-metodo="${m}" ${sem ? "disabled" : ""}
        title="${htmlLoc(sem ? info.motivo : (estadoLoc.ligados.has(m) ? "clique para esconder" : "clique para mostrar"))}"><span class="loc-bolinha" style="background:${CORES_LOC[m]}"></span>${htmlLoc(info.curto || m)}</button>`;
    }).join("");
    const corpo = `<div class="loc-chips">${chips}<span class="loc-nota">os outros métodos de um terminal entram depois, cada um testado contra os exercícios da pós</span>`
      + ` ${pilulaLoc("zoom", [["lt", "LT inteira"], ["perto", "perto do resultado"]], estadoLoc.zoom)}</div>`
      + `<div class="loc-g" data-g="ldl" data-h="330"></div>`
      + `<div class="loc-nota">${c && c.no_plato ? "O cursor 1 está no platô: as curvas estão deitadas, o número vale." : "<span class=\"loc-aten\">O cursor 1 está fora do platô — o número lido ali não vale.</span>"} O resultado é a mediana do platô (faixa azul), não o valor no cursor.</div>`;
    return passoLoc(2, c && c.no_plato ? "ok" : "aviso", "Conferir o platô", "a LDL no tempo", corpo);
  }
  function linhaLoc() {
    const p = estadoLoc.pacote, fontes = p.fontes || {}, l = p.linha;
    const chips = ["base", "A", "B", "manual"].map(f => {
      const info = fontes[f] || { ok: false, motivo: "" };
      const classe = p.fonte === f ? "vale" : (info.ok || f === "manual" ? "" : "sem");
      return `<button type="button" data-fonte="${f}" class="${classe}" title="${htmlLoc(info.ok ? (info.como || "") : (info.motivo || ""))}">${NOMES_DAS_FONTES[f]}</button>`;
    }).join("");
    let s = `<div class="fila-loc"><label>linha</label><div class="fontes-loc">${chips}</div>`
      + (estadoLoc.fonte !== "auto" ? `<button type="button" class="chave" data-acao="auto">voltar ao automático</button>` : "") + `</div>`;
    if (l) {
      s += `<div class="loc-nota">Z1 = <b>${numLoc(l.r, 3)} + j${numLoc(l.x, 3)} Ω</b> · `
        + (l.r0 != null ? `Z0 = <b>${numLoc(l.r0, 3)} + j${numLoc(l.x0, 3)} Ω</b>${p.z0_de && p.z0_de !== p.fonte ? ` (de ${NOMES_DAS_FONTES[p.z0_de]})` : ""}` : `<span class="loc-aten">sem Z0</span>`)
        + ` · <b>${numLoc(l.km, 2)} km</b> · primário, linha inteira · de ${NOMES_DAS_FONTES[p.fonte]}${estadoLoc.fonte === "auto" ? " (automático)" : ""}</div>`;
    } else {
      s += `<div class="loc-aviso">Nenhuma fonte tem o parâmetro da linha: digite abaixo.</div>`;
    }
    if (!l || estadoLoc.fonte === "manual" || (l && l.r0 == null)) s += formularioLoc();
    if (p.fonte === "manual") {
      const nomes = p.nomes || {};
      s += `<div class="fila-loc"><input data-nome-linha value="${htmlLoc(`LT ${nomes.A || ""} - ${nomes.B || ""}`)}" style="flex:1;min-width:0">`
        + `<button type="button" class="chave" data-acao="guardar" title="Guarda na gaveta «linhas» da base de dados: da próxima vez ela entra sozinha">guardar na base</button></div>`;
    }
    return s;
  }
  function formularioLoc() {
    const m = estadoLoc.manual;
    const forma = (v, t) => `<button type="button" data-forma="${v}" class="${m.forma === v ? "on" : ""}">${t}</button>`;
    const campo = (c, rot) => `<label>${rot}</label><input class="num-loc" data-c="${c}" value="${htmlLoc(m[c])}">`;
    const base = (v, t) => `<button type="button" data-base="${v}" class="${m.base === v ? "on" : ""}">${t}</button>`;
    return `<div class="fila-loc"><span class="pilula-loc">${forma("rx", "R + jX")}${forma("pol", "|Z| ∠ θ")}${forma("km", "Ω/km")}</span>`
      + `<span class="pilula-loc">${base("prim", "primário")}${base("sec", "secundário")}</span></div>`
      + (m.forma === "rx" ? `<div class="fila-loc">${campo("r", "R1 (Ω)")}${campo("x", "X1 (Ω)")}${campo("r0", "R0 (Ω)")}${campo("x0", "X0 (Ω)")}</div>` : "")
      + (m.forma === "pol" ? `<div class="fila-loc">${campo("mod", "|Z1| (Ω)")}${campo("ang", "θ1 (°)")}${campo("mod0", "|Z0| (Ω)")}${campo("ang0", "θ0 (°)")}</div>` : "")
      + (m.forma === "km" ? `<div class="fila-loc">${campo("rkm", "R1 (Ω/km)")}${campo("xkm", "X1 (Ω/km)")}${campo("r0km", "R0 (Ω/km)")}${campo("x0km", "X0 (Ω/km)")}</div>` : "")
      + `<div class="fila-loc">${campo("km", "comprimento (km)")}</div>`
      + `<div class="loc-nota">Linha INTEIRA. Z1 entra nos dois métodos; Z0 só no laço de terra (k0 = (Z0 − Z1)/3Z1). Em secundário, passa a primário pelo RTP/RTC do IED A.</div>`;
  }
  function passo3Loc() {
    const p = estadoLoc.pacote, km = p.km_linha;
    const linhas = ["seqneg", "laco"].map(m => {
      const info = p.metodos[m];
      if (!info) return "";
      // Sem número, ou com número FORA da linha: o motivo no lugar das colunas.
      if (info.km == null || info.fora) return `<tr><td><span class="loc-bolinha" style="background:${CORES_LOC[m]}"></span>${htmlLoc(info.nome)}</td><td colspan="3" style="text-align:left" class="${info.fora ? "loc-aten" : "loc-nota"}">${htmlLoc(info.motivo)}</td></tr>`;
      return `<tr><td><span class="loc-bolinha" style="background:${CORES_LOC[m]}"></span>${htmlLoc(info.nome)}${p.resultado && p.resultado.metodo === m ? " <b>· resultado</b>" : ""}</td>`
        + `<td><b>${numLoc(info.km, 2)}</b></td><td>${numLoc(km - info.km, 2)}</td><td>±${numLoc(info.dispersao, 2)}</td></tr>`;
    }).join("");
    return passoLoc(3, p.resultado ? "ok" : "aviso", "Resultado", "",
      `<div class="loc-g" data-g="unifilar"></div>`
      + `<table><tr><th>método</th><th>km de A</th><th>km de ${p.nomes && p.nomes.B ? "B" : "R"}</th><th>dispersão no platô (km)</th></tr>${linhas}</table>`
      + `<div style="margin-top:10px">${linhaLoc()}</div>`);
  }

  function mostrarLocalizacao() {
    if (!telaLoc) return;
    telaLoc.hidden = !estadoLoc.aberta;
    area.classList.toggle("atras-da-localizacao", estadoLoc.aberta);
    if (!estadoLoc.aberta) return;
    const p = estadoLoc.pacote;
    const abas = `<div class="loc-abas"><button type="button" class="on">Painel principal</button>`
      + `<button type="button" disabled title="Chegam na etapa 2: faltas sorteadas nesta linha, com as fontes e a carga lidas deste registro, para medir o erro de cada método.">Simulações</button>`
      + `<button type="button" class="chave loc-fechar" data-acao="fechar" title="Voltar às ondas">voltar às ondas</button></div>`;
    let corpo;
    if (!p) corpo = `<div class="loc-nota">calculando…</div>`;
    else if (!p.curvas) corpo = `<div class="loc-aviso">${htmlLoc(p.aviso || "sem dados")}</div>` + (p.fontes ? linhaLoc() : "");
    else {
      const al = alinhamentoLoc(), temB = !!(p.curvas && p.curvas.B), c = p.cursor;
      const etapa = (n, ok, nome) => `<span class="loc-passo"><span class="loc-num ${ok ? "ok" : "aviso"}">${ok ? "✓" : "!"}</span>${nome}</span>`;
      corpo = faixaDoResultadoLoc()
        + (p.aviso ? `<div class="loc-aviso">${htmlLoc(p.aviso)}</div>` : "")
        + `<div class="loc-passos">${etapa(1, temB && al.ok, temB ? "Alinhar A × B" : "Um terminal só")}<span>→</span>`
        + `${etapa(2, !!(c && c.no_plato), "Conferir o platô")}<span>→</span>${etapa(3, !!p.resultado, "Resultado")}</div>`
        + passo1Loc() + passo2Loc() + passo3Loc();
    }
    telaLoc.innerHTML = abas + `<div class="loc-corpo">${corpo}</div>`;
    telaLoc.querySelectorAll(".loc-g[data-g]").forEach(el => {
      const largura = Math.max(200, Math.floor(el.clientWidth));
      const g = el.dataset.g;
      el.innerHTML = g === "onda" ? ondaLoc(el.dataset.lado, el.dataset.gr, largura, +el.dataset.h, el.dataset.eixo === "1")
        : g === "ldl" ? ldlLoc(largura, +el.dataset.h) : unifilarLoc(largura);
    });
    ligarLocalizacao();
  }

  function ligarLocalizacao() {
    const de = sel => telaLoc.querySelectorAll(sel);
    de("[data-acao=fechar]").forEach(b => { b.onclick = () => abrirLocalizacao(false); });
    de("[data-acao=auto]").forEach(b => { b.onclick = () => { estadoLoc.fonte = "auto"; pedirLocalizacao(); }; });
    de("[data-loc]").forEach(b => {
      b.onclick = () => {
        const k = b.dataset.loc, v = b.dataset.v;
        if (k === "alinhar") {
          if (alinharPor === v) return;
          alinharPor = v;
          guardarAba();
          carregar();
          pedirLocalizacao();
          return;
        }
        estadoLoc[k] = v;
        mostrarLocalizacao();
      };
    });
    de("[data-metodo]").forEach(b => {
      b.onclick = () => {
        const m = b.dataset.metodo;
        if (estadoLoc.ligados.has(m)) estadoLoc.ligados.delete(m); else estadoLoc.ligados.add(m);
        mostrarLocalizacao();
      };
    });
    // O cursor 1: clicar num gráfico do tempo é a tecla 1 naquele instante.
    de("svg.tempo").forEach(svg => {
      svg.addEventListener("click", e => {
        const largura = +svg.getAttribute("width"), E = eixoLoc(largura);
        const r = svg.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * largura;
        if (x < E.x0 || x > E.x1) return;
        porCursor(0, E.T(x));
      });
    });
    de("[data-fonte]").forEach(b => {
      b.onclick = () => {
        const f = b.dataset.fonte;
        const info = ((estadoLoc.pacote && estadoLoc.pacote.fontes) || {})[f];
        if (f !== "manual" && !(info && info.ok)) return;
        estadoLoc.fonte = f;
        pedirLocalizacao();
      };
    });
    de("[data-forma]").forEach(b => { b.onclick = () => { estadoLoc.manual.forma = b.dataset.forma; mostrarLocalizacao(); }; });
    de("[data-base]").forEach(b => { b.onclick = () => { estadoLoc.manual.base = b.dataset.base; pedirLocalizacao(); }; });
    de("input[data-c]").forEach(inp => {
      inp.onchange = () => {
        estadoLoc.manual[inp.dataset.c] = inp.value;
        // Sem nenhuma outra fonte, digitar já é escolher a digitada.
        if (estadoLoc.fonte === "auto" && !(estadoLoc.pacote && estadoLoc.pacote.fonte)) estadoLoc.fonte = "manual";
        pedirLocalizacao();
      };
    });
    de("[data-acao=guardar]").forEach(b => {
      b.onclick = async () => {
        const p = estadoLoc.pacote;
        const l = p && p.fontes && p.fontes.manual;
        if (!l || !l.ok) return;
        const nome = telaLoc.querySelector("[data-nome-linha]");
        try {
          const r = await fetch("/api/base/linhas", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              nome: nome ? nome.value : "", r: l.r, x: l.x, km: l.km, r0: l.r0, x0: l.x0,
              terminal_s: (p.nomes || {}).A || "", terminal_r: (p.nomes || {}).B || "",
            }),
          });
          b.textContent = r.ok ? "guardada ✓" : "não guardou (há base ativa?)";
        } catch (_e) {
          b.textContent = "não guardou";
        }
      };
    });
  }

  function abrirLocalizacao(abrir) {
    estadoLoc.aberta = abrir;
    document.getElementById("localizar")?.classList.toggle("escolhido", abrir);
    mostrarLocalizacao();
    if (abrir) { window.scrollTo(0, 0); pedirLocalizacao(); }
    // De volta às ondas: elas não se redesenharam enquanto estavam atrás.
    else carregar();
  }
  document.getElementById("localizar")?.addEventListener("click",
    () => abrirLocalizacao(!estadoLoc.aberta));

  carregar();
})();
