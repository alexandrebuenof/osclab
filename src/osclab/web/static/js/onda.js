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
  const CONTRATO = 3;

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
  const FONTE_TIRA = "10.5px ui-monospace, Consolas, monospace";

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


  //: As células das tabelinhas, por canal: `{indice, celas, botao}`. O índice
  //: é o do canal NO REGISTRO — é por ele que se casa com a leitura do cursor.
  let celulas = { canais: [] };

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
  let filtro = lerGuardado("osclab:filtro", ["0", "1"], "0") === "1";

  //: A medida de cada grupo, pela unidade dele. Quem não está aqui é
  //: instantâneo.
  let medidas = lerMedidasGuardadas();

  //: Como cada vista se chama no canto da tabelinha. Curto: a coluna é estreita.
  const ROTULO = {
    instantaneo: "valor", filtrado: "60 Hz", rms: "RMS", fundamental: "|F|",
  };

  //: O canal que o usuário clicou para ser o zero dos ângulos, ou null para a
  //: regra automática (a tensão da fase A). Vai no pedido; quem subtrai é o
  //: servidor, como todo número.
  let referencia = null;

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
    if (filtro) p.set("filtro", "1");
    const escolhas = medidasEmTexto();
    if (escolhas) p.set("medidas", escolhas);
    if (digitaisNaTela !== null) p.set("digitais", digitaisNaTela.join(","));
    const acrescentados = extrasEmTexto();
    if (acrescentados) p.set("extras", acrescentados);
    if (ocultos.size) p.set("ocultos", [...ocultos].join(","));

    try {
      const r = await fetch(`/api/onda/${sha}?${p}`);
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
      marcarLado();
      // O veredito de bruto × filtrado chega junto com a janela: é ele que
      // trava o botão e é ele que a tira anuncia.
      marcarBotoes();
      mostrarFiltragem();
      mostrarTaxa();
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
    rodape.textContent = recado;
    rodape.classList.add("atencao");
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
    const temDireito = (dados && dados.grupos || []).some((g) => g.eixo_dir);
    MARGEM.dir = temDireito ? 62 : MARGEM_DIR_BASE;

    MARGEM.esq = MARGEM_BASE;
    const tiras = dados && dados.digitais ? dados.digitais.tiras : null;
    if (!tiras || !tiras.length) return;
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
    rodape.classList.add("atencao");
    rodape.textContent = "versão do servidor diferente da versão da tela";
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

  function desenharTudo() {
    if (!dados) return;

    if (!dados.grupos || dados.grupos.length === 0) {
      area.replaceChildren(criar("p", "vazio", "Este registro não tem canal analógico."));
      return;
    }

    ajustarMargem();
    // Sinal que saiu da tela não pode continuar selecionado: o Delete seguinte
    // apagaria algo que o usuário não está mais vendo.
    selecionados = selecionados.filter((s) => {
      if (s.tipo === "digital") {
        return (dados.digitais ? dados.digitais.tiras : [])
          .some((t) => t.indice === s.chave);
      }
      const grupo = dados.grupos.find((g) => g.unidade_do_arquivo === s.unidade);
      if (!grupo) return false;
      return s.tipo === "canal"
        ? grupo.canais.some((c) => c.indice === s.chave)
        : (grupo.extras || []).some((e) => e.id === s.chave);
    });
    celulas = { canais: [], extras: [] };
    linhasDoTempo = [];
    const temDigitais = dados.digitais && dados.digitais.tiras.length > 0;
    blocos = dados.grupos.map((grupo, i) =>
      bloco(grupo, !temDigitais && i === dados.grupos.length - 1)
    );
    if (temDigitais) blocos.push(blocoDigitais(dados.digitais));
    area.replaceChildren(...blocos);

    rodape.classList.remove("atencao");
    rodape.textContent =
      `${dados.amostras_na_janela} amostras · ${duracao(dados.ate - dados.de)} na tela` +
      (dados.inteiro ? " (registro inteiro)" : "") +
      (dados.reduzido ? " · reduzidas para caber na tela, preservando os picos" : "") +
      semRelacao();

    mostrarLeitura();
    repintar();
    marcarLegenda();
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

  //: Altura de cada tira digital, em pixels de CSS. Estreita de propósito: um
  //: evento real mexe em algumas dezenas de digitais, e elas precisam caber na
  //: mesma tela que as ondas.
  const TIRA = 15;

  //: As duas espessuras da linha de um digital, em pixels de CSS: 0 é um fio,
  //: 1 é uma barra. A razão entre elas é o que se lê de longe — sete para um
  //: se distingue numa tela cheia de tiras sem precisar de cor diferente.
  const FINA = 1;
  const GROSSA = 7;

  /** O bloco dos digitais: uma tira por canal, no mesmo eixo de tempo.
   *
   * Nasce como um `.grafico` igual aos outros de propósito — assim os gestos
   * (roda, arrasto, seleção) e os cursores funcionam nele sem uma linha a
   * mais: `areaDoEvento` procura o `.tela` mais próximo e acha este também.
   */
  function blocoDigitais(digitais) {
    const el = criar("section", "grafico digitais");

    const titulo = criar("h2", "grafico-titulo");
    const quantos = digitais.tiras.length;
    titulo.append(criar("span", null,
      `Digitais (${quantos} ${quantos === 1 ? "sinal" : "sinais"})`));

    const parados = digitais.disponiveis.length - digitais.mudaram;
    const busca = criar("button", "medida", "+ sinal");
    busca.title = `${digitais.mudaram} mudaram durante o registro e estão na `
                + `tela; ${parados} ficaram parados. Clique para procurar `
                + "qualquer um pelo nome e trazê-lo para cá.";
    busca.addEventListener("click", () => abrirBusca(digitais));

    titulo.append(busca);
    el.append(titulo);

    const corpo = criar("div", "grafico-corpo");
    const caixa = criar("div", "tela");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    // A segunda coluna existe vazia para as tiras ficarem alinhadas com as
    // ondas quando a tabelinha dos cursores está aberta.
    corpo.append(caixa, criar("div", "sem-tabela"));
    el.append(corpo);

    // O nome inteiro na dica do navegador, tira por tira. E' o que salva o
    // modo cortado: o nome completo esta' sempre a um segundo de distancia,
    // sem gastar largura de desenho nenhuma.
    canvas.addEventListener("pointermove", (evento) => {
      const caixaCanvas = canvas.getBoundingClientRect();
      const k = Math.floor((evento.clientY - caixaCanvas.top - MARGEM.topo) / TIRA);
      const tira = digitais.tiras[k];
      const dica = tira ? tira.nome : "";
      if (canvas.title !== dica) canvas.title = dica;
      // Sobre o NOME, o cursor vira o de clicar: ali não se arrasta nem se
      // amplia — escolhe-se a tira, como na legenda das ondas.
      const noNome = tira && (evento.clientX - caixaCanvas.left) < MARGEM.esq;
      canvas.style.cursor = noNome ? "pointer" : "";
    });

    // O nome da tira é o alvo certeiro: as tiras têm 15 px de altura, e acertar
    // a certa no meio de quarenta é mira. O nome está sempre no mesmo lugar.
    canvas.addEventListener("click", (evento) => {
      const caixaCanvas = canvas.getBoundingClientRect();
      if (evento.clientX - caixaCanvas.left >= MARGEM.esq) return;  // o desenho
      const achado = digitalPerto(digitais, evento.clientY - caixaCanvas.top);
      if (!achado) return;
      // Sem isto, o clique sobe até o `document` e a regra de "clicou fora,
      // limpa a seleção" desfaria o que acabou de ser feito.
      evento.stopPropagation();
      alternarSelecao(achado, evento.ctrlKey || evento.metaKey);
    });

    el._canvas = canvas;
    el._digitais = digitais;
    return el;
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
      ctx.restore();
    });
  }

  /** Desenha as tiras. Mesmo eixo de tempo das ondas, mesmo arrasto. */
  function pintarDigitais(canvas, digitais) {
    const linhas = digitais.tiras;
    const cssLargura = canvas.parentElement.clientWidth;
    const cssAltura = MARGEM.topo + linhas.length * TIRA + MARGEM.baixo;
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
    const y1 = y0 + linhas.length * TIRA;
    if (x1 <= x0 || !linhas.length) return;

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
    const haEscolha = selecionados.some((x) => x.tipo === "digital");
    ctx.textAlign = "right";
    linhas.forEach((tira, k) => {
      const escolhida = estaSelecionado(null, "digital", tira.indice);
      ctx.fillStyle = escolhida ? token("--destaque") : token("--suave");
      ctx.globalAlpha = haEscolha && !escolhida ? 0.4 : 1;
      const meio = y0 + k * TIRA + TIRA / 2;
      ctx.fillText(encaixar(tira.nome, x0 - 12), x0 - 8, meio);
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
    const tempo = digitais.tempo;
    const corBarra = token("--digital");
    const corEscolhida = token("--destaque");
    linhas.forEach((tira, k) => {
      const escolhida = estaSelecionado(null, "digital", tira.indice);
      const meio = Math.round(y0 + k * TIRA + TIRA / 2);
      ctx.globalAlpha = haEscolha && !escolhida ? 0.35 : 1;

      // Colunas de mesmo estado seguidas viram UM retângulo só. Desenhar uma
      // por uma deixava a barra tracejada: cada retângulo cai em fração de
      // pixel e o antialiasing abre uma fresta clara entre vizinhos. Um trip
      // contínuo que aparece pontilhado se lê como trip intermitente.
      ctx.fillStyle = escolhida ? corEscolhida : corBarra;
      const fim = (i) => (i + 1 < tempo.length ? emX(tempo[i + 1]) : emX(tMax));
      const trecho = (i, j, ligado) => {
        const a = emX(tempo[i]);
        // A tira escolhida engorda um pouco: no meio de quarenta tiras, só a
        // cor não salta — o olho encontra a espessura antes da cor.
        const alto = (ligado ? GROSSA : FINA) + (escolhida ? 2 : 0);
        // Pulso de uma amostra num registro longo cai numa coluna só: o
        // mínimo de 1 px é o que o mantém visível. Trip que some da tela é
        // pior que trip mais gordo do que é.
        // Mesmo azul nos dois estados: quem distingue é a ESPESSURA. Clarear
        // o zero deixava a linha quase invisível no tema claro, e um canal
        // apagado precisa se ver tanto quanto um aceso — é ele que prova que
        // o sinal existe e não mudou.
        ctx.fillRect(a, meio - alto / 2, Math.max(fim(j) - a, 1), alto);
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
  }

  //: Quais digitais estão na tela. `null` = ainda não se escolheu, e o servidor
  //: decide (os que mudaram). Lista vazia é escolha legítima e não é `null`.
  let digitaisNaTela = null;

  /** A busca: qualquer digital do arquivo, pelo nome, para trazer à tela.
   *
   * Existe porque "só os que mudaram" é o padrão certo e não é a regra toda:
   * num laudo, às vezes o que importa é provar que um sinal **não** mudou.
   * Escondido não pode virar inexistente.
   */
  function abrirBusca(digitais) {
    const escolhidos = new Set(digitaisNaTela ?? digitais.escolhidos);
    const janelinha = criar("dialog", "busca");

    const campo = document.createElement("input");
    campo.type = "search";
    campo.placeholder = "procurar sinal pelo nome…";
    const lista = criar("div", "achados");

    const desenharLista = () => {
      const procura = campo.value.trim().toUpperCase();
      // A busca filtra só os que ainda NÃO estão na tela: os outros já se veem
      // no gráfico, e quem procura está procurando entre os que faltam.
      const fora = digitais.disponiveis
        .filter((d) => !escolhidos.has(d.indice))
        .filter((d) => !procura || d.nome.toUpperCase().includes(procura))
        .slice(0, 300);
      const naTela = digitais.disponiveis.filter((d) => escolhidos.has(d.indice));

      const desenhar = (d) => {
        const item = criar("label", d.mudou ? "achado mudou" : "achado");
        const marca = document.createElement("input");
        marca.type = "checkbox";
        marca.checked = escolhidos.has(d.indice);
        marca.addEventListener("change", () => {
          if (marca.checked) escolhidos.add(d.indice);
          else escolhidos.delete(d.indice);
        });
        item.append(marca, criar("span", "nome", d.nome));
        // Quem mudou ganha a hora da primeira mudança: é o que distingue
        // "este é o trip que eu procuro" de um homônimo.
        if (d.instante !== null && d.instante !== undefined) {
          item.append(criar("span", "quando",
                            `${formatar(d.instante * 1000, 1)} ms`));
        }
        return item;
      };

      montarAchados(lista, fora, naTela, desenhar,
                    procura ? "Nenhum digital com esse nome fora da tela."
                            : "Todos os digitais do registro já estão na tela.");
    };

    campo.addEventListener("input", desenharLista);
    desenharLista();

    const aplicar = criar("button", "aceitar", "mostrar na tela");
    aplicar.addEventListener("click", () => {
      // A ordem é a da lista (hora da mudança), não a de clique: a tela conta
      // a sequência do evento, e isso não pode depender de em que ordem o
      // usuário marcou as caixas.
      guardarParaDesfazer();
      digitaisNaTela = digitais.disponiveis
        .filter((d) => escolhidos.has(d.indice)).map((d) => d.indice);
      janelinha.close();
      carregar();
    });

    // Fechar sem escolher nada. O Esc já fazia isso, e Esc é um atalho que
    // quem não conhece não descobre — a janela precisa dizer como se sai dela.
    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem mudar a tela";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());

    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, "Sinais digitais"), campo, fechar);
    janelinha.append(cabeca, lista, aplicar);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
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
      ? fora.map(desenhar)
      : [criar("p", "vazio", vazio)];
    if (naTela.length) {
      nos.push(criar("div", "divisor",
                     `já na tela (${naTela.length}) — desmarque para tirar`));
      nos.push(...naTela.map(desenhar));
    }
    lista.replaceChildren(...nos);
  }

  //: Como a tela escreve de onde veio o vínculo de cada canal.
  const ORIGEM_DO_VINCULO = {
    escolhida: "você corrigiu este vínculo",
    automatico: "voltou para a dedução automática",
    declarada: "o próprio arquivo declara a fase deste canal (campo `ph`)",
    deduzida: "deduzido do NOME do canal — confira",
    desconhecida: "o nome do canal não disse que fase é",
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

    if (mexido) {
      // Enquanto não se aplica, mostra o que FOI PEDIDO, não o que está
      // valendo: a tela tem que refletir a mão do usuário na hora.
      const g = x.grandeza_do_canal || "";
      const texto = pendente === "" ? "automático"
                  : pendente === "-" ? "nenhuma" : `${g}${pendente}`;
      const chip = criar("span", "vinculo pendente", texto);
      chip.title = "Correção pendente — clique em «mostrar na tela» para "
                 + "gravar. Ela vale para este registro e fica gravada.";
      caixa.append(chip);
    } else if (x.fundamental) {
      const chip = criar("span", "vinculo", x.fundamental);
      chip.title = `${ORIGEM_DO_VINCULO[origem] || ""} — é de ${x.fundamental} `
                 + "que saem o RMS, as componentes simétricas e a localização "
                 + "de falta.";
      if (origem === "deduzida") chip.classList.add("deduzida");
      if (origem === "escolhida") chip.classList.add("escolhida");
      caixa.append(chip);
    } else {
      const sem = criar("span", "vinculo nenhum", "não reconhecido");
      sem.title = (ORIGEM_DO_VINCULO[origem] || "")
                + ". O canal continua desenhável, mas não entra em componente "
                + "simétrica nem em localização de falta. Corrija no lápis.";
      caixa.append(sem);
    }

    const lapis = criar("button", "editar-vinculo", "✎");
    lapis.type = "button";
    lapis.title = "corrigir a fase deste canal";
    lapis.setAttribute("aria-label", "corrigir a fase deste canal");
    lapis.addEventListener("click", (evento) => {
      // O clique não pode virar clique no `<label>`, senão marca a caixinha.
      evento.preventDefault();
      evento.stopPropagation();
      const escolha = document.createElement("select");
      escolha.className = "escolher-fase";
      for (const [valor, rotulo] of fasesPossiveis(x.grandeza_do_canal)) {
        const o = document.createElement("option");
        o.value = valor;
        o.textContent = rotulo;
        escolha.append(o);
      }
      escolha.value = pendente !== undefined ? pendente : "";
      escolha.addEventListener("click", (e) => e.preventDefault());
      escolha.addEventListener("change", () => {
        correcoes.set(x.canal, escolha.value);
        redesenhar();
      });
      // Escolher o MESMO valor que já estava não dispara `change`, e sem isto a
      // listinha ficava aberta para sempre no lugar do vínculo: quem abriu o
      // lápis, olhou e escolheu "automático" — que já era o estado — perdia a
      // etiqueta de vista e parecia que o canal tinha deixado de ser
      // reconhecido. Sair do campo devolve a etiqueta, tendo mudado ou não.
      escolha.addEventListener("blur", () => redesenhar());
      caixa.replaceChildren(escolha);
      escolha.focus();
    });
    caixa.append(lapis);
    return caixa;
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
      rodape.classList.add("atencao");
      rodape.textContent = "Não consegui gravar a correção de fase: "
                         + `${erro.message}. O vínculo continua como estava.`;
    }
  }

  /** Troca os sinais acrescentados a um gráfico e recarrega a janela. */
  function trocarExtras(unidade, ids) {
    guardarParaDesfazer();
    extras[unidade] = ids;
    carregar();                 // a escala do gráfico muda; a leitura vem junto
  }

  /** O catálogo: o que se pode acrescentar a UM gráfico.
   *
   * Duas abas, porque são duas coisas diferentes e a tela não pode deixar
   * dúvida sobre qual é qual: em `canais` está o que o relé gravou; em
   * `calculados`, o que saiu de uma conta nossa. Um relatório que diz
   * "3I0 = 412 A" tem que deixar claro que aquele número é do OscLab.
   */
  function abrirCatalogo(grupo) {
    const unidade = grupo.unidade_do_arquivo;
    // Um canal da MESMA unidade do gráfico já tem lugar ali: marcar e desmarcar
    // é mostrar e esconder, não acrescentar. Canal de outra unidade é que vira
    // sinal acrescentado, no segundo eixo. Para quem usa, é a mesma caixinha.
    const daCasa = (x) => x.familia === "canal" && x.unidade === unidade;
    const escolhidos = new Set(extras[unidade] || []);
    for (const x of (dados.catalogo || [])) {
      if (daCasa(x) && !ocultos.has(x.canal)) escolhidos.add(x.id);
    }
    //: Correções de fase pendentes nesta janela: canal → fase pedida. Só vão
    //: para o servidor quando se aplica; o × desiste de tudo.
    const correcoes = new Map();
    const janelinha = criar("dialog", "busca catalogo");
    let aba = "canal";

    const campo = document.createElement("input");
    campo.type = "search";
    campo.placeholder = "procurar sinal pelo nome…";
    const lista = criar("div", "achados");

    const abas = criar("div", "abas");
    const botoesDeAba = {};
    for (const [chave, rotulo] of [["canal", "IED"],
                                   ["calculado", "OscLab"]]) {
      const b = criar("button", "aba", rotulo);
      b.title = chave === "canal"
        ? "Os canais analógicos como o IED os gravou, com o nome que o "
          + "fabricante deu. À direita de cada um, a variável fundamental que "
          + "o OscLab vinculou a ele — é a conferência do vínculo em que "
          + "todas as contas se apoiam."
        : "O que o IED não gravou: IA RMS, IA 60Hz, IA 60Hz RMS e as "
          + "componentes simétricas — estas sempre em eficaz, porque "
          + "componente simétrica é fasor e fasor não tem valor instantâneo.";
      b.addEventListener("click", () => { aba = chave; marcarAbas(); desenharLista(); });
      botoesDeAba[chave] = b;
      abas.append(b);
    }
    const marcarAbas = () => {
      for (const [chave, b] of Object.entries(botoesDeAba)) {
        b.classList.toggle("escolhido", chave === aba);
      }
    };

    const desenharLista = () => {
      const procura = campo.value.trim().toUpperCase();
      const todos = dados.catalogo || [];
      const fora = todos
        .filter((x) => !escolhidos.has(x.id))
        .filter((x) => x.familia === aba)
        .filter((x) => !procura || x.nome.toUpperCase().includes(procura)
                    || (x.origem || "").toUpperCase().includes(procura));
      const naTela = todos.filter((x) => escolhidos.has(x.id));

      const desenhar = (x) => {
        const item = criar("label", "achado mudou");
        const marca = document.createElement("input");
        marca.type = "checkbox";
        marca.checked = escolhidos.has(x.id);
        marca.addEventListener("change", () => {
          if (marca.checked) escolhidos.add(x.id);
          else escolhidos.delete(x.id);
        });
        const nome = criar("span", "nome", x.nome);
        nome.title = x.descricao + (x.origem ? ` — de ${x.origem}` : "");
        item.append(marca, nome);
        // Só o canal do IED leva coisa à direita: o vínculo com a
        // fundamental, que é conferência. De que canais saiu uma variável
        // calculada fica no hover do nome — escrever isso em toda linha enchia
        // a lista de texto repetido, e o que importa ali é o NOME do sinal.
        if (x.familia === "canal") {
          item.append(vinculoDoCanal(x, correcoes, desenharLista));
        }
        // Unidade diferente da do gráfico vai para o segundo eixo, e isso
        // precisa estar escrito ANTES de o usuário marcar.
        if (x.unidade !== unidade) {
          const marcaEixo = criar("span", "quando", `→ ${x.unidade_mostrada}`);
          marcaEixo.title = "Outra unidade: este sinal vai para a escala da "
                          + "direita, e é desenhado tracejado.";
          item.append(marcaEixo);
        }
        return item;
      };

      const vazio = procura
        ? "Nada com esse nome fora do gráfico."
        : (aba === "calculado"
            ? "Todos os sinais do OscLab já estão neste gráfico. As "
              + "componentes simétricas só existem se o registro tiver um "
              + "conjunto trifásico completo."
            : "Todos os canais do IED já estão neste gráfico.");
      montarAchados(lista, fora, naTela, desenhar, vazio);
    };

    campo.addEventListener("input", desenharLista);
    marcarAbas();
    desenharLista();

    const aplicar = criar("button", "aceitar", "mostrar na tela");
    aplicar.addEventListener("click", async () => {
      // A ordem é a do catálogo, não a de clique: a tela não pode mudar de
      // arrumação conforme a ordem em que alguém marcou as caixas.
      const catalogo = dados.catalogo || [];
      const ids = catalogo.filter((x) => escolhidos.has(x.id)).map((x) => x.id);
      janelinha.close();
      // As correções de fase vão PRIMEIRO e são gravadas no servidor: elas
      // mudam o nome de tudo que vem depois, inclusive dos sinais que se
      // acabou de escolher.
      if (correcoes.size) await gravarVinculos(correcoes);

      for (const x of catalogo.filter(daCasa)) {
        if (escolhidos.has(x.id)) ocultos.delete(x.canal);
        else ocultos.add(x.canal);
      }
      trocarExtras(unidade, ids.filter((id) => !catalogo.some(
        (x) => x.id === id && daCasa(x))));
    });

    const fechar = criar("button", "fechar", "×");
    fechar.type = "button";
    fechar.title = "fechar sem mudar a tela";
    fechar.setAttribute("aria-label", "fechar");
    fechar.addEventListener("click", () => janelinha.close());

    const cabeca = criar("div", "cabeca");
    cabeca.append(criar("h3", null, `Sinais de ${grupo.titulo}`), campo, fechar);
    janelinha.append(cabeca, abas, lista, aplicar);
    janelinha.addEventListener("close", () => janelinha.remove());
    document.body.append(janelinha);
    janelinha.showModal();
    campo.focus();
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
    if (!bloco) return;

    const achado = bloco._digitais
      ? digitalPerto(bloco._digitais, y)
      : sinalPerto(bloco._grupo, canvas, x, y);

    if (!achado) {
      if (!acumular) marcarSelecao([]);
      return;
    }
    alternarSelecao(achado, acumular);
  }

  /** Acrescenta, tira ou troca a seleção — a regra é uma só na tela inteira.
   *
   * Sem Ctrl o clique TROCA (e clicar no que já estava escolhido desmarca);
   * com Ctrl, acumula. Vale para o traço, para o nome na legenda e para o nome
   * da tira digital: três lugares, um comportamento.
   */
  function alternarSelecao(alvo, acumular) {
    const jaEstava = selecionados.some((x) => mesmoSinal(x, alvo));
    if (acumular) {
      marcarSelecao(jaEstava
        ? selecionados.filter((x) => !mesmoSinal(x, alvo))
        : [...selecionados, alvo]);
      return;
    }
    const sozinho = jaEstava && selecionados.length === 1;
    marcarSelecao(sozinho ? [] : [alvo]);
  }

  function marcarSelecao(novos) {
    selecionados = novos;
    repintar();
    marcarLegenda();
  }

  /** A tira digital sob o clique. Não há distância a medir: a faixa é a tira. */
  function digitalPerto(digitais, y) {
    const k = Math.floor((y - MARGEM.topo) / TIRA);
    const tira = digitais.tiras[k];
    if (!tira) return null;
    return { unidade: null, tipo: "digital", chave: tira.indice,
             nome: tira.nome };
  }

  /** O sinal desenhado mais perto de `(x, y)` naquele gráfico, ou `null`.
   *
   * Compara pela distância VERTICAL na coluna sob o cursor, e não pela
   * distância ao traço inteiro: num gráfico de onda as curvas se cruzam o
   * tempo todo, e o que o olho entende por "cliquei nesta" é a que está na
   * altura do clique naquele instante.
   */
  function sinalPerto(grupo, canvas, x, y) {
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

    const emY = (v, minimo, maximo) =>
      y1 - ((v - minimo) / (maximo - minimo || 1)) * (y1 - y0);

    let achado = null;
    let menor = PERTO;
    const olhar = (serie, minimo, maximo, alvo) => {
      // Três colunas: a onda sobe muito dentro de uma coluna só, e o traço
      // desenhado liga uma à outra.
      for (const k of [i - 1, i, i + 1]) {
        const v = serie[k];
        if (v === null || v === undefined) continue;
        const d = Math.abs(emY(v, minimo, maximo) - y);
        if (d < menor) { menor = d; achado = alvo; }
      }
    };

    for (const canal of grupo.canais) {
      olhar(canal.serie, grupo.minimo, grupo.maximo,
            { unidade: grupo.unidade_do_arquivo, tipo: "canal",
              chave: canal.indice, nome: canal.sinal || canal.nome });
    }
    for (const extra of (grupo.extras || [])) {
      const eixo = extra.eixo === "dir" ? grupo.eixo_dir : grupo;
      olhar(extra.serie, eixo.minimo, eixo.maximo,
            { unidade: grupo.unidade_do_arquivo, tipo: "extra",
              chave: extra.id, nome: extra.sinal });
    }
    return achado;
  }

  /** Tira da tela tudo que está selecionado, de uma vez.
   *
   * Nada some do registro: canal do arquivo e digital voltam pelo «+ sinal»,
   * onde aparecem desmarcados, e o Ctrl+Z traz tudo de volta de um golpe.
   */
  function apagarSelecionados() {
    if (!selecionados.length) return;
    guardarParaDesfazer();

    for (const { unidade, tipo, chave } of selecionados) {
      if (tipo === "extra") {
        extras[unidade] = (extras[unidade] || []).filter((x) => x !== chave);
      } else if (tipo === "canal") {
        ocultos.add(chave);
      } else if (tipo === "digital") {
        const atuais = digitaisNaTela ?? (dados.digitais
          ? dados.digitais.escolhidos : []);
        digitaisNaTela = atuais.filter((x) => x !== chave);
      }
    }
    selecionados = [];
    carregar();
  }

  /** Repinta o que já está montado. É o que roda a cada movimento do mouse. */
  function repintar() {
    for (const b of blocos) {
      if (b._digitais) pintarDigitais(b._canvas, b._digitais);
      else pintar(b._canvas, b._grupo, b._ultimo);
    }
  }

  function bloco(grupo, ultimo) {
    const el = criar("section", "grafico");

    const titulo = criar("h2", "grafico-titulo");
    titulo.append(criar("span", null, grupo.titulo));

    // A medida é de CADA gráfico: corrente em RMS e tensão em instantâneo ao
    // mesmo tempo é leitura comum numa falta. Discreto de propósito — é escolha
    // de vista, não um dado do registro.
    const medida = criar("button", "medida", grupo.medida === "rms" ? "RMS" : "instantâneo");
    medida.classList.toggle("escolhido", grupo.medida === "rms");
    medida.title = grupo.medida === "rms"
      ? "Mostrando o eficaz da janela de um ciclo. Clique para ver o valor instantâneo."
      : "Clique para ver o eficaz da janela de um ciclo em vez do valor instantâneo.";
    medida.addEventListener("click", () => alternarMedida(grupo.unidade_do_arquivo));

    // Acrescentar sinal a ESTE gráfico. O catálogo inteiro vem no pacote da
    // janela; a busca só o separa em abas.
    const mais = criar("button", "medida", "+ sinal");
    mais.title = "Acrescentar um canal do arquivo ou uma componente calculada "
               + "a este gráfico.";
    mais.addEventListener("click", () => abrirCatalogo(grupo));
    titulo.append(medida, mais);

    // O que não coube: sinal de uma terceira unidade, que não tem eixo.
    for (const aviso of (grupo.avisos || [])) {
      titulo.append(criar("span", "aviso-extra", aviso));
    }
    el.append(titulo);

    const legenda = criar("ul", "legenda");
    for (const canal of grupo.canais) {
      const item = criar("li");
      item.dataset.tipo = "canal";
      item.dataset.chave = String(canal.indice);
      const marca = criar("span", "marca");
      marca.style.background = corDaFase(canal.fase);
      item.append(marca, criar("span", "nome", canal.nome));

      // O nome do ARQUIVO acima, o nome do OSCLAB aqui — e a moldura é o que
      // os separa a olho. Cada fabricante nomeia como quer (`Current IA`,
      // `TC BUC 69kV:I A`, `IAW`); o nome padronizado é sempre o mesmo, e é
      // por ele que o resto do programa vai falar dos canais quando calcular
      // componentes simétricas e localização de falta. Quem analisa um evento
      // com registros de dois fabricantes precisa ver os dois lado a lado.
      if (canal.sinal) {
        const nosso = criar("span", "padrao", canal.sinal);
        nosso.style.color = corDaFase(canal.fase);
        nosso.title = `${canal.sinal} — nome dado pelo OscLab. O canal do `
                    + `arquivo é "${canal.nome}"; o sufixo diz o que foi feito `
                    + "com ele. IA e IA RMS são sinais diferentes.";
        item.append(nosso);
      } else if (canal.fase) {
        // Sem grandeza reconhecida não há nome padronizado: mostra só a fase,
        // sem moldura, porque um palpite com cara de nome nosso é pior que
        // nome nenhum.
        item.append(criar("span", "fase", canal.fase));
      }

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
      selecionavel(item, grupo, "canal", canal.indice);
      legenda.append(item);
    }

    // Os acrescentados à mão, marcados como tais: o nome é só o nosso (não há
    // nome de arquivo para um 3I0), e quem está no segundo eixo diz isso.
    (grupo.extras || []).forEach((extra, i) => {
      const item = criar("li", "extra");
      item.dataset.tipo = "extra";
      item.dataset.chave = extra.id;
      const cor = corDoExtra(extra, i);
      const marca = criar("span", extra.eixo === "dir" ? "marca tracejada" : "marca");
      marca.style.background = cor;
      const nosso = criar("span", "padrao", extra.sinal);
      nosso.style.color = cor;
      nosso.title = `${extra.sinal} — ${extra.descricao}`
                  + (extra.origem ? ` (de ${extra.origem})` : "");
      item.append(marca, nosso);
      if (extra.eixo === "dir") {
        const lado = criar("span", "lado", `→ ${extra.unidade}`);
        lado.title = "Este sinal está na escala da DIREITA, porque a unidade "
                   + "dele não é a do gráfico.";
        item.append(lado);
      }
      const tirar = criar("button", "tirar", "×");
      tirar.title = "tirar este sinal do gráfico";
      tirar.addEventListener("click", () =>
        trocarExtras(grupo.unidade_do_arquivo,
                     (extras[grupo.unidade_do_arquivo] || [])
                       .filter((x) => x !== extra.id)));
      item.append(tirar);
      selecionavel(item, grupo, "extra", extra.id);
      legenda.append(item);
    });
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

  /** Clicar no nome da legenda escolhe o sinal, igual a clicar no traço.
   *
   * O traço é o gesto natural e é o que erra: num gráfico com oito curvas
   * sobrepostas na pré-falta, acertar o traço certo com o mouse é sorte. O
   * nome na legenda está sempre no mesmo lugar e não se move.
   */
  function selecionavel(item, grupo, tipo, chave) {
    item.classList.add("clicavel");
    item.addEventListener("click", (evento) => {
      // O × de tirar o sinal tem a sua própria ação.
      if (evento.target.closest(".tirar")) return;
      alternarSelecao({ unidade: grupo.unidade_do_arquivo, tipo, chave },
                      evento.ctrlKey || evento.metaKey);
    });
  }

  /** Acende na legenda o sinal escolhido no gráfico. */
  function marcarLegenda() {
    for (const b of blocos) {
      if (!b._grupo) continue;
      for (const item of b.querySelectorAll(".legenda li")) {
        const tipo = item.dataset.tipo;
        const chave = tipo === "canal" ? Number(item.dataset.chave)
                                       : item.dataset.chave;
        item.classList.toggle("escolhido",
                              estaSelecionado(b._grupo, tipo, chave));
      }
    }
  }

  /** A tabelinha de um grupo: os canais dele, sempre nas mesmas três colunas.
   *
   * Cursor 1, cursor 2 e a diferença — em qualquer grandeza. A largura nunca
   * muda, e isso é de propósito: tabela que cresce e encolhe empurra o gráfico
   * no meio de uma medição, e a onda foge de debaixo do mouse.
   *
   * O que não cabe em três colunas (ângulo, DC, distorção, e o instantâneo
   * quando o gráfico não está mostrando ele) fica no hover de cada valor.
   */
  function tabelinha(grupo) {
    const tabela = criar("table", "mini");

    const cabeca = criar("tr");
    // O canto diz que grandeza está na tabela. NÃO é botão: quem manda é o
    // cabeçalho da página, e dois lugares mandando na mesma coisa é como eles
    // passam a discordar.
    const canto = criar("th", "unidade", ROTULO[grupo.grandeza] || "valor");
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
    for (const canal of grupo.canais) {
      const linha = criar("tr");

      // O nome é botão: clicar nele faz o canal virar o zero dos ângulos, como
      // no SIGRA. Ângulo absoluto não existe — alguém tem que ser o zero.
      const nome = criar("th", canal.fase ? `canal fase-${canal.fase}` : "canal");
      const alvo = criar("button", "refere", canal.nome);
      // A coluna é estreita e o nome do arquivo é o que o engenheiro
      // reconhece, então é ele que fica escrito. O nome do OscLab aparece na
      // legenda logo acima, e aqui no title, para o par ficar sempre à mão.
      alvo.title = (canal.padrao ? `${canal.padrao} — ${canal.nome}` : canal.nome)
                 + " — clique para medir os ângulos a partir dele";
      alvo.addEventListener("click", () => escolherReferencia(canal.indice));
      nome.append(alvo);

      const celas = [criar("td", "valor-1 vazio-valor", "—"),
                     criar("td", "valor-2 vazio-valor", "—"),
                     criar("td", "vazio-valor", "—")];

      linha.append(nome, ...celas);
      tbody.append(linha);
      celulas.canais.push({ indice: canal.indice, celas, botao: alvo });
    }

    // Os acrescentados, casados pelo `id` e não pela posição: eles não estão
    // na lista de canais do registro, e a ordem deles é a de quem escolheu.
    for (const extra of (grupo.extras || [])) {
      const linha = criar("tr", "extra");
      const nome = criar("th", "canal");
      const etiqueta = criar("span", "padrao", extra.sinal);
      etiqueta.title = `${extra.sinal} — ${extra.descricao}`;
      nome.append(etiqueta);
      // A unidade da linha, quando NÃO é a do gráfico. O rótulo da tabela vale
      // para as outras linhas; sem este aviso, 72,8 V se leria como 72,8 A.
      if (extra.unidade !== grupo.unidade) {
        const un = criar("span", "unidade-extra", `(${extra.unidade})`);
        un.title = "Este sinal está em outra unidade, na escala da direita.";
        nome.append(un);
      }
      const celas = [criar("td", "valor-1 vazio-valor", "—"),
                     criar("td", "valor-2 vazio-valor", "—"),
                     criar("td", "vazio-valor", "—")];
      linha.append(nome, ...celas);
      tbody.append(linha);
      celulas.extras.push({ id: extra.id, celas });
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

  function lerMedidasGuardadas() {
    try {
      const guardado = JSON.parse(localStorage.getItem("osclab:medidas") || "{}");
      const limpo = {};
      for (const [unidade, medida] of Object.entries(guardado)) {
        if (medida === "rms") limpo[unidade] = "rms";
      }
      return limpo;
    } catch {
      return {};
    }
  }

  function guardar(chave, valor) {
    try {
      localStorage.setItem(chave, valor);
    } catch { /* não poder lembrar não impede de usar */ }
  }

  /** O que o servidor precisa saber para montar cada grupo: `A:rms,kV:rms`. */
  const medidasEmTexto = () =>
    Object.entries(medidas).map(([u, m]) => `${u}:${m}`).join(",");

  //: O que o usuário acrescentou a cada gráfico: unidade do arquivo → ids de
  //: sinal. Nada entra aqui sozinho — ver `plot/catalogo.py`.
  let extras = {};

  //: Os canais que ele TIROU do gráfico, por índice no registro. Vão para o
  //: servidor porque a escala vertical depende de quem está desenhado: esconder
  //: só no navegador deixaria o eixo esticado por um canal que não se vê.
  let ocultos = new Set();

  //: Os sinais selecionados por clique. Cada um é `{unidade, tipo, chave}`;
  //: `tipo` é `canal`, `extra` ou `digital`. Lista, e não um só, porque
  //: comparar duas fases é o gesto mais comum do ofício — e porque apagar
  //: quatro sinais um a um é quatro vezes o mesmo trabalho.
  let selecionados = [];

  //: A pilha do desfazer. Cada item é uma fotografia do que está na tela.
  //: Ações que mexem em DADO gravado (a correção de fase) ficam de fora: o
  //: Ctrl+Z desfaz o que se está vendo, não o que se decidiu.
  const desfazer = [];

  const mesmoSinal = (a, b) =>
    a.tipo === b.tipo && a.chave === b.chave && a.unidade === b.unidade;

  const estaSelecionado = (grupo, tipo, chave) =>
    selecionados.some((s) => mesmoSinal(s, {
      unidade: grupo ? grupo.unidade_do_arquivo : null, tipo, chave }));

  /** Guarda o estado atual da tela para o Ctrl+Z. */
  function guardarParaDesfazer() {
    desfazer.push({
      extras: JSON.parse(JSON.stringify(extras)),
      ocultos: [...ocultos],
      digitais: digitaisNaTela === null ? null : [...digitaisNaTela],
    });
    // Vinte passos é mais do que qualquer análise precisa, e segura a memória.
    if (desfazer.length > 20) desfazer.shift();
  }

  function desfazerUltimo() {
    const antes = desfazer.pop();
    if (!antes) return;
    extras = antes.extras;
    ocultos = new Set(antes.ocultos);
    digitaisNaTela = antes.digitais;
    selecionados = [];
    carregar();
  }

  const extrasEmTexto = () =>
    Object.entries(extras)
      .filter(([, ids]) => ids && ids.length)
      .map(([u, ids]) => `${u}=${ids.join(",")}`).join(";");

  //: As cores dos sinais CALCULADOS. Não são fase nenhuma — pintá-los com a
  //: cor de uma fase faria 3I0 se passar por IA no gráfico de correntes.
  const CORES_CALCULADAS = ["--calculado-1", "--calculado-2", "--calculado-3"];

  function corDoExtra(extra, ordem) {
    if (extra.familia === "calculado") {
      return token(CORES_CALCULADAS[ordem % CORES_CALCULADAS.length]);
    }
    // Canal acrescentado à mão continua com a cor da fase dele: é a mesma
    // corrente, e trocar a cor faria parecer outro sinal.
    const achado = (dados.catalogo || []).find((x) => x.id === extra.id);
    return corDaFase(faseDoNome(achado ? achado.nome : extra.sinal));
  }

  /** A letra da fase no começo do nome do sinal (`IA RMS` → `A`). */
  function faseDoNome(nome) {
    const casou = /^[IV]([ABCN])\b/.exec((nome || "").trim());
    return casou ? casou[1] : "";
  }

  const medidaDe = (grupo) => medidas[grupo.unidade_do_arquivo] || "instantaneo";

  function alternarFiltro() {
    if (filtroTravado()) return;
    filtro = !filtro;
    guardar("osclab:filtro", filtro ? "1" : "0");
    marcarBotoes();
    recarregar();
  }

  function alternarMedida(unidade) {
    if (medidas[unidade] === "rms") delete medidas[unidade];
    else medidas[unidade] = "rms";
    guardar("osclab:medidas", JSON.stringify(medidas));
    recarregar();
  }

  /** A curva inteira muda: é o servidor que a calcula, sobre a janela de um
   * ciclo que termina em cada ponto. O navegador não tem como derivá-la do que
   * já está desenhado — o traço na tela é mínimo e máximo por coluna de pixel.
   */
  function recarregar() {
    carregar();
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

  function marcarBotoes() {
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
    botao.title = travado
      ? "Este registro já vem filtrado do relé, e não há como desfiltrá-lo."
      : (filtro
        ? "Mostrando só a componente de 60 Hz. Clique para ver a onda do arquivo."
        : "Clique para ver só a componente de 60 Hz — o mesmo filtro que o relé "
          + "roda por dentro. Ele atrasa até um ciclo nas transições.");
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
    alvo.textContent = `${taxas.length} taxas: ${taxas.join(" · ")}`;
    alvo.title = "Este registro muda de taxa de amostragem no meio. Cada trecho "
      + "tem a sua janela de um ciclo, e por isso há um pedaço sem curva logo "
      + "depois de cada troca — uma janela com metade das amostras de um lado e "
      + "metade do outro não seria um ciclo de coisa nenhuma.";
  }

  /** A tira de cima: o que o ARQUIVO é, que não é escolha de ninguém. */
  function mostrarFiltragem() {
    const alvo = document.getElementById("filtragem");
    if (!alvo || !dados) return;
    const deduzido = dados.filtragem_origem === "deduzido";
    const texto = {
      bruto: "gravação bruta",
      filtrado: "gravação já filtrada pelo relé",
      desconhecido: "bruta ou filtrada? não deu para saber",
    }[dados.filtragem];
    alvo.hidden = !texto;
    if (!texto) return;
    alvo.textContent = deduzido ? `${texto} (deduzido)` : texto;
    alvo.title = dados.filtragem === "filtrado"
      ? "Este registro já contém só a componente de 60 Hz, filtrada pelo "
        + "próprio relé. Por isso o botão do filtro está travado: filtrar de "
        + "novo não limparia nada, só acrescentaria mais um ciclo de atraso."
      : "Deduzido da distorção medida nos trechos em que a amplitude está "
        + "parada. Rede real sempre tem algum harmônico; sinal filtrado não "
        + "tem nenhum.";
  }

  document.getElementById("filtro")?.addEventListener("click", alternarFiltro);
  marcarBotoes();

  function escolherReferencia(indice) {
    // Clicar de novo no canal que já é a referência volta à regra automática.
    referencia = referencia === indice ? null : indice;
    lerCursores();
  }

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

    // --- o segundo eixo, à direita ---------------------------------------
    //
    // Sem linha de grade própria: duas grades cruzadas na mesma área viram
    // xadrez e nenhuma das duas se lê. A grade é a da esquerda; a régua da
    // direita são os números, alinhados nas marcações DELA.
    const dir = grupo.eixo_dir;
    const emYdir = (v) => dir
      ? y1 - ((v - dir.minimo) / (dir.maximo - dir.minimo || 1)) * (y1 - y0)
      : y1;
    if (dir) {
      ctx.textAlign = "left";
      for (const marca of dir.marcacoes) {
        ctx.fillText(formatar(marca, dir.casas), x1 + 8, Math.round(emYdir(marca)));
      }
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
    //
    // Com um sinal escolhido, os outros perdem opacidade em vez de sumirem: o
    // que se quer é destacar UM traço sem perder de vista onde ele passa em
    // relação aos vizinhos — tirar os vizinhos da tela tiraria justamente a
    // comparação que fez alguém clicar ali.
    const haEscolha = selecionados.some(
      (x) => x.unidade === grupo.unidade_do_arquivo);
    ctx.lineJoin = "round";
    for (const canal of grupo.canais) {
      const escolhido = estaSelecionado(grupo, "canal", canal.indice);
      ctx.globalAlpha = haEscolha && !escolhido ? 0.3 : 1;
      ctx.lineWidth = escolhido ? 2.6 : 1.4;
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
    ctx.globalAlpha = 1;

    // --- os sinais acrescentados à mão ------------------------------------
    //
    // Quem está no segundo eixo é desenhado TRACEJADO. Não é enfeite: ele está
    // numa escala diferente da do resto do gráfico, e a altura dele não se
    // compara com a dos outros traços. O tracejado é o aviso.
    (grupo.extras || []).forEach((extra, i) => {
      const escolhido = estaSelecionado(grupo, "extra", extra.id);
      ctx.save();
      ctx.globalAlpha = haEscolha && !escolhido ? 0.3 : 1;
      ctx.strokeStyle = corDoExtra(extra, i);
      ctx.lineWidth = escolhido ? 2.8 : 1.6;
      if (extra.eixo === "dir") ctx.setLineDash([7, 4]);
      const paraY = extra.eixo === "dir" ? emYdir : emY;
      ctx.beginPath();
      let comecou = false;
      const s = extra.serie;
      for (let k = 0; k < s.length; k++) {
        const v = s[k];
        if (v === null) { comecou = false; continue; }
        const x = emX(tempo[k]);
        const y = paraY(v);
        if (comecou) ctx.lineTo(x, y);
        else { ctx.moveTo(x, y); comecou = true; }
      }
      ctx.stroke();
      ctx.restore();
    });

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

    pintarEtiquetas(ctx, emX, x0, x1, y0);

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
    if (referencia !== null) p.set("refere", String(referencia));
    // A mesma grandeza do gráfico: a tabelinha nunca mostra outra coisa.
    if (filtro) p.set("filtro", "1");
    const escolhas = medidasEmTexto();
    if (escolhas) p.set("medidas", escolhas);
    const acrescentados = extrasEmTexto();
    if (acrescentados) p.set("extras", acrescentados);
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
    //
    // O casamento é por ÍNDICE do canal no registro, nunca por posição: os
    // grupos reordenam os canais (correntes juntas, tensões juntas) e a leitura
    // vem na ordem do arquivo. Num registro que intercale as duas, casar por
    // posição poria a tensão na linha da corrente.
    const diferencas = medida && medida.entre ? medida.entre.valores : null;
    const escolhido = medida && medida.referencia ? medida.referencia.indice : null;

    for (const { indice, celas, botao } of celulas.canais) {
      botao.classList.toggle("escolhido", indice === escolhido);

      for (const k of [0, 1]) {
        const v = c[k] ? c[k].valores[indice] : null;
        escrever(celas[k], v);
        celas[k].title = v ? emPalavras(v) : "";
      }
      escrever(celas[2], diferencas && diferencas[indice]);
    }

    const difExtras = medida && medida.entre ? (medida.entre.extras || {}) : null;
    for (const { id, celas } of celulas.extras) {
      for (const k of [0, 1]) {
        const v = c[k] && c[k].extras ? c[k].extras[id] : null;
        escrever(celas[k], v);
        celas[k].title = v ? emPalavras(v) : "";
      }
      escrever(celas[2], difExtras && difExtras[id]);
    }

    mostrarTempo(c);
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
    const embaixo = bloco && bloco._digitais
      ? MARGEM.topo + bloco._digitais.tiras.length * TIRA
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

  area.addEventListener("wheel", (evento) => {
    const a = areaDoEvento(evento);
    // Fora da moldura do desenho a roda não é nossa: ela rola a página. Sem
    // `preventDefault`, o navegador faz o que sempre fez.
    if (!noDesenho(a) || arrastando) return;
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
      const dentro = noDesenho(a);
      const naEtiqueta = sobreEtiqueta(a);
      sobreOMouse = dentro ? instanteEm(a) : null;
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

    // Clique parado: não é gesto de navegação, é escolha de sinal. O limiar de
    // 4 px é o mesmo da faixa — mão nenhuma fica imóvel de verdade.
    if (!faixa && Math.abs(arrastoPx) < 4) {
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
    if (!selecionados.length) return;
    if (evento.target.closest(".legenda li.clicavel, dialog")) return;
    if (noDesenho(areaDoEvento(evento))) return;   // o desenho já se tratou
    marcarSelecao([]);
  });

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

    // Ctrl+Z desfaz a última mudança do que está na tela: sinal tirado, sinal
    // acrescentado, digital escondido. Não desfaz correção de fase — aquilo é
    // dado gravado, e se desfaz no próprio lápis.
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
      porCursor(k, jaEstava ? null : onde);
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
