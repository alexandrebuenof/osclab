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
  const CONTRATO = 20;

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
    if (!paineis.length) return undefined;
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        paineis: paineis.map((x) => ({
          id: x.id, tipo: x.tipo, nome: x.nome, do_padrao: x.do_padrao,
          medida: x.medida, sinais: x.sinais,
          // Só o fasorial usa, e ela VAI ao servidor: o sinal que é o zero
          // dos ângulos pode não estar no diagrama, e mesmo assim o fasor
          // dele precisa ser calculado. Ver `plot/paineis.py`.
          referencia: x.referencia || "",
        })),
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
        ? (x.tiras || []).map((s) => String(s.indice))
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
  //: Um só, e mesmo assim em lista: o botão diz "aplicar filtro" e a setinha
  //: diz QUAL. Sem isso, "filtrado" na tela não significa nada preciso — um
  //: Fourier de um ciclo, um de meio ciclo e um cosseno dão números
  //: diferentes na mesma falta, e é o número que o usuário lê.
  const FILTROS = [
    ["fourier", "Fourier (um ciclo)",
     "Fasor de um ciclo pela transformada discreta: o mesmo filtro que o relé "
     + "roda por dentro. Atrasa até um ciclo nas transições."],
  ];

  //: Qual deles está aplicado. Enquanto houver um só, não vai ao servidor —
  //: mandar um parâmetro que ninguém lê seria fingir uma escolha que não
  //: existe. Quando entrar o segundo, ele passa a ir junto com `filtro`.
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
    rodape.classList.add("atencao");
    rodape.textContent = "versão do servidor diferente da versão da tela";
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
        ? (painel.tiras || []).some((t) => t.indice === s.chave)
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

    rodape.classList.remove("atencao");
    rodape.textContent =
      `${dados.amostras_na_janela} amostras · ${duracao(dados.ate - dados.de)} na tela` +
      (dados.inteiro ? " (registro inteiro)" : "") +
      (dados.reduzido ? " · reduzidas para caber na tela, preservando os picos" : "") +
      semRelacao();

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
        saida.push(linha);
        i += 1;
        continue;
      }
      saida.push(lista[i]);
    }
    return saida;
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
    ["harmonicos", "harmônicos",
     "O espectro do sinal BRUTO no instante de um cursor, em barras, com a "
     + "distorção total. É onde se vê o 2º harmônico de uma energização de "
     + "trafo e a saturação de um TC."],
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
          const soNoAvancado = tipo === "harmonicos"
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
  function criarPainel(tipo) {
    guardarParaDesfazer();
    const quantos = paineis.filter((x) => x.tipo === tipo).length + 1;
    const nome = tipo === "digital" ? `Gráfico digital ${quantos}`
               : tipo === "fasorial" ? `Fasores ${quantos}`
               : tipo === "harmonicos" ? `Harmônicos ${quantos}`
               : `Gráfico analógico ${quantos}`;
    paineis.push({ id: `t${proximoId++}`, tipo, nome, sinais: [],
                   medida: "instantaneo", do_padrao: false, cores: {},
                   // Só no fasorial: de qual cursor ele mostra o instante,
                   // qual sinal é o zero dos ângulos DELE, e a base do pu que
                   // o usuário digitou para cada unidade (`{"kV": 7.967}`).
                   cursor: 1, referencia: null, bases: {},
                   // **Sem escala por padrão**: a pergunta que se faz num
                   // fasorial é de ÂNGULO, e com todas as setas do mesmo
                   // tamanho ela se responde de relance. O módulo está na
                   // tabela ao lado, em ampère e volt, o tempo todo.
                   escala: false });
    carregar();
  }

  function apagarPainel(id) {
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
      if (painel.tipo === "fasorial") continue;     // não tem lado desenhado
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
  const TIRA = 15;

  //: As duas espessuras da linha de um digital, em pixels de CSS: 0 é um fio,
  //: 1 é uma barra. A razão entre elas é o que se lê de longe — sete para um
  //: se distingue numa tela cheia de tiras sem precisar de cor diferente.
  const FINA = 1;
  const GROSSA = 7;

  /** Um painel de tiras digitais.
   *
   * Nasce como um `.grafico` igual aos outros de propósito — assim os gestos
   * (roda, arrasto, seleção) e os cursores funcionam nele sem uma linha a
   * mais: `areaDoEvento` procura o `.tela` mais próximo e acha este também.
   */
  function blocoDigitais(painel, ultimo) {
    const el = criar("section", "grafico digitais");
    const quantos = painel.tiras.length;

    const parados = (dados.digitais_disponiveis || []).length
                  - (dados.digitais_mudaram || 0);
    const busca = criar("button", "medida", "+ sinal");
    busca.title = `${dados.digitais_mudaram} digitais mudaram durante o `
                + `registro; ${parados} ficaram parados. Clique para procurar `
                + "qualquer um pelo nome e trazê-lo para cá.";
    busca.addEventListener("click", () => abrirBusca(painel));

    el.append(cabecalhoDoPainel(painel, [busca],
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
      const noNome = tira && (evento.clientX - caixaCanvas.left) < MARGEM.esq;
      canvas.style.cursor = noNome ? "pointer" : "";
    });

    // O nome da tira é o alvo certeiro: as tiras têm 15 px de altura, e acertar
    // a certa no meio de quarenta é mira. O nome está sempre no mesmo lugar.
    canvas.addEventListener("click", (evento) => {
      const caixaCanvas = canvas.getBoundingClientRect();
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
  function cabecalhoDoPainel(painel, botoes, contagem) {
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
    "button, input, select, a, canvas, .tela, .tela-fasorial, .mini, "
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

  /** Pode parear? Só dois fasoriais, e nenhum deles já num par. */
  function podeParear(idA, idB) {
    if (idA === idB) return false;
    const a = painelPorId(idA);
    const b = painelPorId(idB);
    if (!a || !b || a.tipo !== "fasorial" || b.tipo !== "fasorial") return false;
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
  function pintarDigitais(canvas, painel) {
    const linhas = painel.tiras;
    const cssLargura = canvas.parentElement.clientWidth;
    const cssAltura = MARGEM.topo + Math.max(linhas.length, 1) * TIRA + MARGEM.baixo;
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
      const escolhida = estaSelecionado(painel, "digital", tira.indice);
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
    const tempo = dados.tempo_digitais || [];
    const corBarra = token("--digital");
    const corEscolhida = token("--destaque");
    linhas.forEach((tira, k) => {
      const escolhida = estaSelecionado(painel, "digital", tira.indice);
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
    const escolhidos = new Set((meu ? meu.sinais : []).map(Number));
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
        .filter((d) => !escolhidos.has(d.indice))
        .filter((d) => !procura || d.nome.toUpperCase().includes(procura))
        .slice(0, 300);
      const naTela = disponiveis.filter((d) => escolhidos.has(d.indice));

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
        .filter((d) => escolhidos.has(d.indice)).map((d) => String(d.indice));
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
                  unidade: x.unidade, unidade_mostrada: x.unidade_mostrada,
                  grandeza_do_canal: x.grandeza_do_canal || "",
                  origem: x.origem || "", conjunto: x.conjunto || null,
                  nota: x.nota || "",
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
      destino.append(criar("span", "nome", nome.slice(0, -fim.length)),
                     criar("span", "chip-no-nome", grupo));
    } else {
      destino.append(criar("span", "nome", nome));
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
    const unidade = canal.unidade_mostrada || canal.unidade || "";
    if (!nome) return unidade ? `grupo · ${unidade}` : "grupo";
    return unidade ? `${nome} · ${unidade}` : nome;
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

  function blocosDoCatalogo(linhas, modo, silenciosos = new Set()) {
    const alternados = linhas.filter((l) => l.bloco !== "outros");
    const outros = linhas.filter((l) => l.bloco === "outros");
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
    } else {
      const canais = alternados.filter((l) => l.canal >= 0);
      const nossos = alternados.filter((l) => l.canal < 0);
      if (canais.length) {
        blocos.push({ chave: "senoidais", titulo: "Senoidais", icone: "seno",
                      secoes: [{ linhas: canais }] });
      }
      if (nossos.length) {
        blocos.push({ chave: "calculados", titulo: "Calculados",
                      icone: "calculado", secoes: [{ linhas: nossos }] });
      }
    }
    if (outros.length) {
      blocos.push({ chave: "outros", titulo: "Outros sinais", icone: "outros",
                    recolhido: true,
                    dica: "Canais em que não dá para tirar fasor: a tela não "
                        + "diz que são contínuos, diz que não sabe medi-los em "
                        + "eficaz. O motivo de cada um está ao lado do nome.",
                    secoes: [{ linhas: outros }] });
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
  function nomeDoSinal(id) {
    const x = (dados.catalogo || []).find((y) => y.id === id);
    return x ? (x.linha || x.nome) : "";
  }

  //: Os blocos do catálogo do fasorial, na ordem. São os dois do «agrupar por
  //: lista» do catálogo analógico: o que o relé gravou e o que o OscLab
  //: contou. Não há «Outros sinais» — ver `comFasor`.
  const BLOCOS_DO_FASORIAL = [
    ["senoidais", "Senoidais", "seno",
     "Canais do arquivo em que o programa mediu onda alternada: é deles que "
     + "sai fasor."],
    ["calculados", "Calculados", "calculado",
     "O que o OscLab contou a partir dos canais: o resíduo e as componentes "
     + "simétricas da trinca."],
  ];

  function abrirCatalogoFasorial(painel) {
    abrirCatalogoDeSinais(painel, {
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
        || (x.linha || x.nome).toUpperCase().includes(procura);
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
        item.append(nome);
        if (x.sem_sinal) {
          const etiqueta = criar("span", "etiqueta", "sem sinal");
          etiqueta.title = "A entrada do relé não está cabeada: este canal lê "
                         + "só o ruído do conversor.";
          item.append(etiqueta);
        }
        item.append(criar("span", "quando", x.unidade_mostrada || x.unidade));
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
        if (!recolhido) nos.push(...dele.map((x) => desenhar(x, false)));
      }
      if (!fora.length) {
        nos.push(criar("p", "vazio", procura ? opcoes.vazio : opcoes.cheio));
      }
      if (naTela.length) {
        nos.push(criar("div", "divisor",
                       `já na tela (${naTela.length}) — desmarque para tirar`));
        nos.push(...naTela.map((x) => desenhar(x, true)));
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
  function abrirCatalogo(painel) {
    // Os ids vêm do ARRANJO da tela; `painel.sinais` da resposta é a lista de
    // sinais DESENHADOS, com série e escala dentro — outra coisa.
    const meu = painelPorId(painel.id);
    const escolhidos = new Set(meu ? meu.sinais : []);
    const janelinha = criar("dialog", "busca catalogo");

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
    const temMudo = (dados.catalogo || []).some((x) => x.sem_sinal);
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
             linhasDoCatalogo(dados.catalogo || []))) {
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
      const todas = linhasDoCatalogo(dados.catalogo || []);
      const silenciosos = gruposSilenciosos(todas);
      const chavesVisiveis = colunasDaVisao().map(([chave]) => chave);
      const visiveis = todas.filter((l) => {
        // Sem nenhuma conta na vista atual, a linha seria uma fileira de
        // risquinhos — que é o que este modo veio evitar. Ela volta no
        // «avançado», que é onde as contas dela moram.
        if (!chavesVisiveis.some((c) => l.contas.has(c))) return false;
        const naTela = [...l.contas.values()].some((x) => escolhidos.has(x.id));
        // A trinca inteiramente sem sinal não some da lista em «grupo
        // trifásico»: ela vira um cabeçalho recolhido no fim. Esconder tem que
        // ser visível e reversível — e é justamente o sumiço dela que faz a
        // numeração parecer ter buraco.
        const daTrincaMuda = modo === "grupo" && l.grupo
                          && silenciosos.has(l.grupo);
        if (ocultarMudos && l.sem_sinal && !naTela && !daTrincaMuda) return false;
        if (!procura) return true;
        return l.nome.toUpperCase().includes(procura)
            || (l.origem || "").toUpperCase().includes(procura)
            || [...l.contas.values()].some(
                 (x) => x.nome.toUpperCase().includes(procura));
      });

      lista.replaceChildren();
      caixasPorId.clear();
      if (!visiveis.length) {
        lista.append(criar("p", "vazio", procura
          ? "Nada com esse nome neste registro."
          : "Este registro não tem sinal nenhum a acrescentar."));
        return;
      }

      // O cabeçalho da matriz. A primeira coluna é o nome; as outras cinco são
      // as contas, e a de 60 Hz leva o ⓘ que diz QUAL filtro as produziu —
      // um só, no cabeçalho, e não vinte e um espalhados pelas linhas.
      // O cabeçalho tem DOIS andares. Em cima, de que SINAL é a coluna —
      // filtrado ou bruto; embaixo, COMO se olha para ele — onda, RMS, DC.
      // São duas perguntas diferentes, e enquanto foram cinco colunas irmãs
      // nada na tela dizia que `onda` e `60 Hz` eram sinais diferentes.
      const colunas = colunasDaVisao();
      const andarDeCima = criar("div", "linha-do-sinal cabeca-dos-grupos");
      andarDeCima.append(criar("div", "col-sinal"));
      let i = 0;
      while (i < colunas.length) {
        const grupo = colunas[i][0].split(".")[0];
        let quantas = 0;
        while (i + quantas < colunas.length
               && colunas[i + quantas][0].startsWith(`${grupo}.`)) quantas += 1;
        const [rotulo, explicacao] = GRUPOS_DE_COLUNA[grupo];
        const cela = criar("div", `grupo-de-colunas de-${quantas}`);
        cela.append(criar("span", "nome-do-grupo-de-colunas", rotulo));
        // O ⓘ fica no FILTRADO: é ali que há o que perguntar — qual filtro
        // produziu aqueles números, e o que ele tira do sinal.
        if (grupo === "filtrado") cela.append(informacaoDoFiltro());
        cela.title = rotuloDaColuna(explicacao);
        andarDeCima.append(cela);
        i += quantas;
      }
      lista.append(andarDeCima);

      const titulos = criar("div", "linha-do-sinal cabeca-da-matriz");
      titulos.append(celaDoCabecalho("sinal", "", "col-sinal"));
      for (const [, rotulo, explicacao] of colunas) {
        titulos.append(celaDoCabecalho(rotuloDaColuna(rotulo),
                                       rotuloDaColuna(explicacao), "col-conta"));
      }
      lista.append(titulos);

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
          for (const secao of bloco.secoes) {
            for (const l of secao.linhas) desenharLinha(l, caixa);
          }
        }
        if (ehGrupo) lista.append(caixa);
      }

      desenharPeDaTela();
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

    const desenharLinha = (l, destino) => {
      // A linha cujo NOME é nosso — `IN G1`, `3I0 G1` — sai na cor dos
      // calculados. `IAW · RMS` não entra nisso: a linha dele é o canal `IAW`,
      // que é nome de arquivo; o que é nosso ali é a COLUNA.
      //
      // A cor aqui nomeia a FAMÍLIA, não o traço — e é por isso que ela se
      // apaga no pé da lista: lá o sinal já está desenhado, tem cor de traço de
      // verdade, e a bolinha ao lado dele é que responde qual é.
      const fileira = criar("div", "linha-do-sinal");
      const nome = criar("div", "col-sinal nome-da-linha"
                         + (l.canal < 0 ? " calculado" : ""));
      nomeComGrupo(nome, l.nome, l.canal < 0 ? l.grupo : "");
      if (l.sem_sinal) {
        const marca = criar("span", "etiqueta", "sem sinal");
        marca.title = "A entrada do relé não está cabeada: este canal lê só o "
                    + "ruído do conversor.";
        nome.append(marca);
      }
      // O que é conta nossa não leva marca nenhuma na linha: já está dito no
      // nome (`IN G1`, `3I0 G1` — o `·` e o nome do grupo só existem em conta
      // nossa), na cor, e no bloco onde ela mora. A frase que diz QUE conta é
      // fica no hover do nome, para quem perguntar.
      if (l.nota) nome.title = `${l.nome} — ${l.nota}`;
      // O motivo de um canal ter caído em «outros» fica escrito: ali ele
      // explica por que aquela linha tem uma coluna só, e sem ele o risquinho
      // nas outras quatro parece defeito.
      if (l.motivo) {
        const nota = criar("span", "motivo-da-linha", l.motivo);
        nota.title = l.motivo;
        nome.append(nota);
      }
      // O lápis da FASE não vem aqui: ele mora na tela «canais», que é a da
      // conferência. Um por linha seriam vinte e um convites para a mesma
      // correção, e esta tela é de escolher o que ver, não de consertar o que
      // o programa deduziu. O lápis da TRINCA fica, no cabeçalho do grupo:
      // ali ele corrige uma coisa só, e é a que o bloco inteiro assume.
      fileira.append(nome);

      for (const [chave] of colunasDaVisao()) {
        const sinal = l.contas.get(chave);
        const cela = criar("div", "col-conta cela-de-conta");
        // Com o filtro aceso, a coluna do bruto que ele substitui não tem o
        // que oferecer: marcar `IAW · RMS` ali desenharia `IAW · 60Hz RMS`, e
        // a marca pularia de coluna debaixo do clique. A DC fica — o filtro
        // não tem par para ela, e ela continua sendo o que diz ser.
        //
        // O mesmo vale para a MEDIDA do gráfico: num painel em RMS o canal
        // aparece em eficaz, e a «onda» dele não tem como entrar ali.
        const empurrado = sinal && desenhadoDe(sinal.id) !== sinal.id;
        if (!sinal || empurrado) {
          const risco = criar("span", "risquinho", "—");
          const vira = empurrado
            && (doCatalogo.get(desenhadoDe(sinal.id)) || {}).nome;
          risco.title = !empurrado
            ? motivoDaAusencia(l, chave)
            : dados.filtro
              ? `com o filtro aceso a tela mostra o filtrado: ${sinal.nome} `
                + `apareceria como ${vira}. Apague o filtro para ver o bruto.`
              : `este gráfico está em RMS: ${sinal.nome} apareceria como `
                + `${vira}. Troque para «inst.» no topo do gráfico para ver `
                + "a onda.";
          cela.append(risco);
          fileira.append(cela);
          continue;
        }
        // Só a caixinha: a cor mora no pé da lista, junto do nome do sinal.
        // Na célula ela disputaria espaço com a marca e responderia outra
        // pergunta que não a da coluna.
        cela.append(caixaDoSinal(sinal, pedidoDaCela(l, sinal)));
        fileira.append(cela);
      }
      (destino || lista).append(fileira);
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
  function abrirGrupos() {
    // Um grupo por `grupo`, com a trinca de onde ele saiu. A trinca vem no
    // sinal — é o único campo que diz QUAIS três canais entraram na conta.
    const porGrupo = new Map();
    for (const x of dados.catalogo || []) {
      if (!x.grupo) continue;
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
      }
      cartao.append(topo);
      cartao.append(criar("div", "canais-do-grupo", grupo.origem || "—"));
      const grandeza = grupo.tipo === "tensões" ? "V" : "I";
      cartao.append(criar("div", "saidas-do-grupo",
                          `deste grupo saem ${grandeza}N ${grupo.nome}, `
                          + `3${grandeza}0 ${grupo.nome}, ${grandeza}1 `
                          + `${grupo.nome} e ${grandeza}2 ${grupo.nome}`));
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
        linha.append(criar("span", "col-nome", x.nome));
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
        if (x.grupo && trincaDoGrupo.has(x.grupo)) {
          grupo.append(lapisDaTrinca({ nome: x.grupo,
                                       conjunto: trincaDoGrupo.get(x.grupo) }));
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
      if (painel.tipo === "fasorial") continue;   // não tem eixo do tempo
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
                       chave: tira.indice, rotulo: tira.nome });
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
    return { painel: painel.id, tipo: "digital", chave: tira.indice,
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

    const emY = (v, minimo, maximo) =>
      y1 - ((v - minimo) / (maximo - minimo || 1)) * (y1 - y0);

    let achado = null;
    let menor = PERTO;
    for (const sinal of (painel.sinais || [])) {
      const eixo = sinal.eixo === "dir" ? painel.eixo_dir : painel;
      if (!eixo) continue;
      // Três colunas: a onda sobe muito dentro de uma coluna só, e o traço
      // desenhado liga uma à outra.
      for (const k of [i - 1, i, i + 1]) {
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
  function repintar() {
    for (const b of blocos) {
      if (!b._painel) continue;
      if (b._painel.tipo === "digital") pintarDigitais(b._canvas, b._painel);
      else if (b._painel.tipo === "fasorial") pintarFasorial(b._canvas, b._painel);
      else if (b._painel.tipo === "harmonicos") pintarHarmonicos(b._canvas, b._painel);
      else pintar(b._canvas, b._painel, b._ultimo);
    }
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
    // `inst.` e não `instantâneo`: o botão mostra o ESTADO, então ele troca de
    // palavra a cada clique, e onze caracteres contra três faziam o `+ sinal`
    // ao lado dançar. A largura mínima no CSS segura o resto.
    const botaoMedida = criar("button", "medida",
                              painel.medida === "rms" ? "RMS" : "inst.");
    botaoMedida.classList.toggle("escolhido", painel.medida === "rms");
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
      : painel.medida === "rms"
        ? "Mostrando o eficaz da janela de um ciclo dos canais do IED deste "
          + "gráfico. Clique para ver o valor instantâneo."
        : "Clique para ver os canais do IED deste gráfico em eficaz de um ciclo.";
    botaoMedida.addEventListener("click", () => alternarMedida(painel.id));

    // Acrescentar sinal a ESTE painel. O catálogo inteiro vem no pacote da
    // janela; a busca só o separa em abas.
    const mais = criar("button", "medida", "+ sinal");
    mais.title = "Acrescentar um canal do IED ou uma variável do OscLab a "
               + "este gráfico.";
    mais.addEventListener("click", () => abrirCatalogo(painel));

    el.append(cabecalhoDoPainel(painel, [botaoMedida, mais]));

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

      // UM nome, escrito normal. Houve dois: o do arquivo à esquerda e o
      // nosso numa moldura em itálico e colorida ao lado, porque o nosso era
      // `IA` e o do arquivo `IAW` — duas nomenclaturas que precisavam ser
      // vistas juntas. Desde que o nome do sinal PASSOU A SER o do arquivo
      // (`IAW`, `IAW · 60Hz`), a moldura repetia a mesma palavra ao lado dela
      // mesma; e quando o filtro entrava, sobrava só a moldura, e a legenda
      // trocava de estilo conforme o botão.
      const escrito = sinal.sinal || sinal.nome || "";
      if (escrito) {
        const nome = criar("span", "nome", escrito);
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
    "--traco-2",      // laranja  croma 78,6
    "--traco-1",      // verde    croma 74,0
    "--calculado-1",  // roxo     croma 59,7
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

    for (const sinal of lista) {
      if (mapa.has(sinal.id)) continue;
      const daFase = CORES_DE_FASE[sinal.fase];
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


  // --- o painel de harmônicos -----------------------------------------------

  //: O quadro das barras, em pixels de CSS. Fixo, e não medido do pai: medir
  //: era um laço no fasorial (o quadro se ajusta ao canvas e o canvas ao
  //: quadro) e seria o mesmo laço aqui.
  const LARGURA_HARMONICOS = 620;
  const ALTURA_HARMONICOS = 236;
  const MARGEM_HARMONICOS = { esq: 44, dir: 10, topo: 14, baixo: 34 };

  //: Abaixo disto a barra não é desenhada.
  //:
  //: Não é gosto: é o PISO DA MEDIDA. Com a taxa fracionária do SEL a 2000 Hz
  //: (33,3 amostras/ciclo) a janela de um ciclo de tempo deixa 0,31 % de resto
  //: numa ordem vazia — ver `dsp/fasor.espectro`, que traz a medição. Desenhar
  //: abaixo disso é desenhar vazamento do próprio método, e uma fileira de
  //: barrinhas espúrias esconde as três que importam. Com taxa inteira o
  //: espectro é exato e nada se perde: ali não há o que fique abaixo do piso.
  const RUIDO_DA_BARRA = 0.6;

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

    el.append(cabecalhoDoPainel(painel,
                                [...botaoDaJanela(painel), mais]));

    const corpo = criar("div", "corpo-fasorial");
    const caixa = criar("div", "tela-harmonicos");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    corpo.append(caixa, tabelaHarmonicos(painel));
    el.append(corpo);

    if (!(painel.sinais || []).length) {
      el.append(criar("p", "vazio",
        "Nenhum sinal neste painel. Use o «+ sinal» para escolher as correntes "
        + "ou tensões cujo espectro você quer ver."));
    }

    const notas = [];
    // A primeira linha diz QUAL janela foi medida, e ela muda com os cursores:
    // fica num nó próprio, refeito a cada leitura.
    const daJanela = criar("div", null, "");
    notasDaJanela.push({ painel: painel.id, nota: daJanela });
    // O teto de ordens é do ARQUIVO, e precisa estar escrito: além dele não há
    // zero, há aliasing. Ver `plot/harmonicos.py`.
    notas.push(`a taxa deste registro mede até o ${painel.teto}º harmônico`);
    // E o aviso que muda a leitura do painel inteiro.
    if (painel.ja_filtrado) {
      notas.push(painel.filtragem_deduzida !== false
        ? "ATENÇÃO: o programa DEDUZIU que esta gravação já está filtrada em "
          + frequenciaDoRegistro() + " — a distorção em regime está no nível "
          + "do ruído de quantização. Se for isso mesmo, não há harmônico no "
          + "arquivo para medir."
        : "ATENÇÃO: o arquivo DECLARA que o relé gravou já filtrado em "
          + frequenciaDoRegistro() + ". Não há harmônico no arquivo para "
          + "medir — o que aparecer aqui é resto de filtro, não do sistema.");
    }
    for (const linha of (painel.rodape || [])) notas.push(linha);
    const nota = criar("div", "rodape-do-painel");
    nota.append(daJanela);
    for (const linha of notas) nota.append(criar("div", null, linha));
    el.append(nota);

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
      nome.style.color = corDoSinal(sinal, painel);
      rotulo.append(criar("span", "nome", sinal.sinal));
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
    const quadro = criar("div", "lado-fasorial");
    quadro.append(tabela);
    return quadro;
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

  /** Reescreve o «medido sobre …» de todos os painéis de harmônicos.
   *
   * Dizer a janela não é enfeite: "o espectro deste instante" e "a média deste
   * trecho" são leituras diferentes do mesmo desenho, e quantos ciclos
   * entraram muda a segunda. E é aqui que o arredondamento para ciclo inteiro
   * aparece — o usuário marcou 7,3 e mediu 7.
   */
  function mostrarJanelasDoEspectro() {
    for (const { painel: id, nota } of notasDaJanela) {
      if (!nota.isConnected) continue;
      const painel = (dados.paineis || []).find((x) => x.id === id);
      if (!painel) continue;
      const janela = janelaDoPainel(painel);
      if (janela !== "entre") {
        nota.textContent = `janela de 1 ciclo, terminando no cursor ${janela}`;
        nota.classList.remove("recado-do-painel");
        continue;
      }
      const { erro, ciclos, pedidos } = leituraDoEspectro(painel);
      if (erro) {
        nota.textContent = `sem espectro do trecho: ${erro}`;
        nota.classList.add("recado-do-painel");
        continue;
      }
      nota.classList.remove("recado-do-painel");
      const sobra = pedidos && pedidos - ciclos >= 0.05
                  ? ` — você marcou ${formatar(pedidos, 2)}, e o resto fica de `
                    + "fora para as raias caírem em cima dos múltiplos de "
                    + frequenciaDoRegistro()
                  : "";
      nota.textContent = `janela do trecho entre os cursores: `
                       + `${ciclos} ciclo${ciclos === 1 ? "" : "s"}${sobra}`;
    }
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
      saida.push({ sinal, base, unidade: sinal.unidade,
                   raias: v.harmonicos.map((x) => (x === null ? 0 : x)) });
    }
    return saida;
  }

  /** Desenha as barras. Canvas, como todo gráfico desta tela. */
  function pintarHarmonicos(canvas, painel) {
    const larg = LARGURA_HARMONICOS;
    const alt = ALTURA_HARMONICOS;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${larg}px`;
    canvas.style.height = `${alt}px`;
    canvas.width = Math.round(larg * dpr);
    canvas.height = Math.round(alt * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, larg, alt);

    const m = MARGEM_HARMONICOS;
    const x0 = m.esq;
    const y0 = alt - m.baixo;
    const largura = larg - m.esq - m.dir;
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
    let topo = 100;
    for (const x of dados_) {
      for (let h = 1; h < x.raias.length && h < ordens; h += 1) {
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
    ctx.textBaseline = "alphabetic";
    for (let h = 0; h < ordens; h += 1) {
      const xi = x0 + h * passo + passo * 0.14;
      dados_.forEach((x, n) => {
        const pct = 100 * (x.raias[h] || 0) / x.base;
        if (pct < RUIDO_DA_BARRA) return;
        const h_ = altura * Math.min(pct, topo) / topo;
        ctx.fillStyle = corDoSinal(x.sinal, painel);
        ctx.fillRect(xi + n * (larguraDaBarra + 1.4), y0 - h_,
                     larguraDaBarra, h_);
      });
      // A ordem embaixo. Com muitas ordens, de dois em dois: rótulo colado em
      // rótulo não se lê, e o 1 e o 2 são os que importam.
      const cada = passo >= 18 ? 1 : passo >= 10 ? 2 : 5;
      if (h === 0 || (h + 1) % cada === 0) {
        ctx.fillStyle = token("--suave");
        ctx.textAlign = "center";
        ctx.fillText(String(h + 1),
                     xi + (quantos * larguraDaBarra) / 2, y0 + 14);
      }
    }
    ctx.fillStyle = token("--suave");
    ctx.textAlign = "center";
    ctx.fillText("ordem do harmônico · % da fundamental de cada sinal",
                 x0 + largura / 2, alt - 6);
    ctx.restore();

    // O valor exato de cada barra no hover: o desenho responde "quanto, mais
    // ou menos"; quem precisa do número não deveria ter que mudar de painel.
    canvas._harm = { dados: dados_, ordens, x0, passo, quantos,
                     larguraDaBarra, painel };
    if (!canvas._temHover) {
      canvas._temHover = true;
      canvas.addEventListener("mousemove", (evento) => {
        const d = canvas._harm;
        if (!d) return;
        const r = canvas.getBoundingClientRect();
        const h = Math.floor((evento.clientX - r.left - d.x0) / d.passo);
        if (h < 0 || h >= d.ordens) { canvas.title = ""; return; }
        const linhas = [`${h + 1}º harmônico`];
        for (const x of d.dados) {
          const v = x.raias[h] || 0;
          linhas.push(`${x.sinal.sinal}: ${formatar(v, casasDaBase(v))} `
                    + `${x.unidade} — ${formatar(100 * v / x.base, 1)} % da `
                    + "fundamental");
        }
        canvas.title = linhas.join("\n");
      });
    }
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

    const botoes = [botaoCursor, ...botaoDaEscala(painel),
                    ...botaoDaReferencia(painel), mais];
    // O «ao lado» só aparece no painel que AINDA não tem par: dois diagramas
    // é o que cabe numa linha, e um terceiro espremeria os três. O da direita
    // não oferece o botão — quem desfaz o par é o × dele.
    if (!temPar(painel.id) && !eDaDireita(painel.id)) {
      const aoLado = criar("button", "medida", "+ diagrama lateral");
      aoLado.title = "Cria um segundo diagrama de fasores, vazio, à direita "
                   + "deste. É a comparação que se faz num evento: os fasores "
                   + "de antes da falta ao lado dos de durante, na mesma "
                   + "tela. Dá no mesmo arrastar um diagrama que já existe "
                   + "para cima deste.";
      aoLado.addEventListener("click", () => criarParFasorial(painel.id));
      botoes.push(aoLado);
    }
    el.append(cabecalhoDoPainel(painel, botoes));

    const corpo = criar("div", "corpo-fasorial");
    const caixa = criar("div", "tela-fasorial");
    const canvas = document.createElement("canvas");
    caixa.append(canvas);
    corpo.append(caixa, tabelaFasorial(painel));
    el.append(corpo);

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
    const automatica = (medida && medida.referencia && medida.referencia.nome)
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
            || (x.linha || x.nome).toUpperCase().includes(procura);
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
      nome.style.color = corDoSinal(sinal, painel);

      // O nome é botão: clicar faz este sinal ser o zero dos ângulos DESTE
      // diagrama. Ângulo absoluto não existe — alguém tem que ser o zero, e
      // aqui é onde se escolhe quem.
      const alvo = criar("button", "refere", sinal.sinal);
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

    tabela.append(thead, tbody);
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
  function pintarFasorial(canvas, painel) {
    // Tamanho FIXO, e não medido do pai. Medir era um laço: o quadro se ajusta
    // ao canvas (`flex: 0 0 auto`) e o canvas se ajustava ao quadro, então
    // cada desenho mudava a largura do seguinte e o painel nunca parava quieto.
    const lado = 2 * (RAIO_FASORIAL + FOLGA_FASORIAL);
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = `${lado}px`;
    canvas.style.height = `${lado}px`;
    canvas.width = Math.round(lado * dpr);
    canvas.height = Math.round(lado * dpr);

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
    return i >= 0 && !!paineis[i].par
        && paineis[i + 1] && paineis[i + 1].tipo === "fasorial";
  };

  const eDaDireita = (id) => {
    const i = paineis.findIndex((x) => x.id === id);
    return i > 0 && !!paineis[i - 1].par && paineis[i - 1].tipo === "fasorial";
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

  /** O botão que escolhe o que o comprimento das setas diz, com o menu. */
  function botaoDaEscala(painel) {
    const ancoraId = `menu-escala-${painel.id}`;
    const meu = painelPorId(painel.id) || {};
    const agora = ESCALAS_DO_FASORIAL.find(([v]) => v === !!meu.escala)
               || ESCALAS_DO_FASORIAL[0];

    const botao = criar("button", "medida");
    botao.type = "button";
    botao.setAttribute("aria-haspopup", "true");
    botao.setAttribute("aria-expanded", "false");
    botao.classList.toggle("escolhido", !!meu.escala);
    botao.append(criar("span", null, agora[1]),
                 criar("span", "seta-do-menu", "▾"));
    botao.title = agora[2];
    const ancora = criar("span", "ancora-de-menu");
    ancora.id = ancoraId;

    botao.addEventListener("click", () => {
      menuSuspenso(ancoraId, "o comprimento da seta é:", (caixa) => {
        for (const [valor, rotulo, explicacao] of ESCALAS_DO_FASORIAL) {
          const linha = criar("label", "opcao");
          const marca = document.createElement("input");
          marca.type = "radio";
          marca.name = `escala-${painel.id}`;
          marca.checked = !!meu.escala === valor;
          marca.addEventListener("change", () => escolherEscala(painel.id, valor));
          linha.title = explicacao;
          linha.append(marca, criar("span", null, rotulo));
          caixa.append(linha);
        }
      });
    });
    return [botao, ancora];
  }

  /** Escolhe o que o comprimento das setas de um fasorial diz. */
  function escolherEscala(id, valor) {
    const meu = painelPorId(id);
    if (!meu || !!meu.escala === valor) return;
    guardarParaDesfazer();
    meu.escala = valor;
    const vindo = (dados.paineis || []).find((x) => x.id === id);
    if (vindo) vindo.escala = valor;
    desenharTudo();
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
      // A MESMA função de cor do desenho, e não uma classe de CSS por fase:
      // era por isso que as componentes simétricas saíam cinzas na tabela e
      // coloridas no gráfico. Tabela e traço têm que combinar por construção,
      // senão voltam a divergir na próxima cor que se acrescente.
      nome.style.color = corDoSinal(sinal, painel);

      // O nome, sem mais. Clicar nele já fez o canal virar o zero dos
      // ângulos — e saiu daqui: a escolha do zero é de um DIAGRAMA, não da
      // tela inteira, e aqui ela era global e invisível. Quem compara ângulo
      // compara no fasorial, e é lá que ela mora agora, por painel.
      const etiqueta = criar("span", "nome", sinal.sinal || sinal.nome);
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

  function menuSuspenso(idDaAncora, titulo, montar) {
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
        rodape.textContent = "Não consegui gravar o nome: "
                           + `${erro.message}. O registro continua com o nome `
                           + "de antes.";
        rodape.classList.add("atencao");
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
      for (const [chave, rotulo, explicacao] of FILTROS) {
        const linha = criar("label", "opcao");
        const marca = document.createElement("input");
        marca.type = "radio";
        marca.name = "filtro-escolhido";
        marca.checked = chave === filtroEscolhido;
        marca.addEventListener("change", () => {
          filtroEscolhido = chave;
          marcarBotoes();
        });
        linha.title = so_um
          ? `${explicacao} — é o único filtro que o OscLab tem hoje.`
          : explicacao;
        linha.append(marca, criar("span", null, rotulo));
        caixa.append(linha);
      }
    });
  }

  function marcarBotoes() {
    const qualVisao = VISOES.find(([c]) => c === visaoDeAnalise) || VISOES[0];
    const botaoDoModo = document.getElementById("modo");
    if (botaoDoModo) {
      botaoDoModo.textContent = qualVisao[1];
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
    alvo.textContent = `${taxas.length} taxas: ${taxas.join(" · ")}`;
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
    const texto = {
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

  /** "3 canais sem sinal · mostrar" — e o clique que os traz de volta.
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
    const quantos = criar("span", "atencao",
      `${fora.length} ${fora.length > 1 ? "canais" : "canal"} sem sinal`);
    quantos.title = `${fora.map((x) => x.nome).join(", ")} — entradas do relé `
      + "que não estão lendo nada além do ruído do conversor, e por isso não "
      + "entraram nos gráficos. Continuam inteiras no buscador de sinais.";
    alvo.append(quantos, document.createTextNode(" · "));

    const botao = criar("button", "link", "mostrar");
    botao.type = "button";
    botao.addEventListener("click", () => devolverOsSemSinal());
    alvo.append(botao);
  }

  /** Devolve ao gráfico os canais que o arranjo padrão deixou de fora. */
  function devolverOsSemSinal() {
    const fora = (dados && dados.sem_sinal) || [];
    if (!fora.length) return;
    guardarParaDesfazer();

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
    }
    // O aviso some sozinho: os canais deixaram de estar fora do arranjo, e o
    // próximo pacote traz a lista já vazia.
    carregar();
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

  function pintar(canvas, painel, ultimo) {
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
    for (const marca of painel.marcacoes) {
      const y = Math.round(emY(marca)) + 0.5;
      ctx.globalAlpha = marca === 0 ? 0.9 : 0.4;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(formatar(marca, painel.casas), x0 - 8, y);
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
    //
    // O sinal do segundo eixo era desenhado TRACEJADO, como aviso de que a
    // altura dele não se compara com a dos outros. Saiu: desde que o gráfico
    // nunca repete cor, a cor sozinha já separa as curvas, e o tracejado
    // gastava a única variação de traço que sobrava — que vale mais guardada
    // para algo que ainda não existe. Quem está no segundo eixo continua
    // dizendo isso na legenda (`→ kV`), na tabelinha e no próprio eixo.
    const haEscolha = selecionados.some((x) => x.painel === painel.id);
    ctx.lineJoin = "round";
    for (const sinal of (painel.sinais || [])) {
      const escolhido = estaSelecionado(painel, "sinal", sinal.id);
      ctx.save();
      ctx.globalAlpha = haEscolha && !escolhido ? 0.3 : 1;
      ctx.lineWidth = escolhido ? 2.6 : 1.4;
      ctx.strokeStyle = corDoSinal(sinal, painel);
      const paraY = sinal.eixo === "dir" ? emYdir : emY;
      ctx.beginPath();
      tracar(ctx, sinal.serie, tempo, emX, paraY);
      ctx.stroke();
      ctx.restore();
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
    // A mesma grandeza do gráfico: a tabelinha nunca mostra outra coisa.
    if (filtro) p.set("filtro", "1");
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
