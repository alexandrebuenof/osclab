/* A tela da BASE DE DADOS.
 *
 * Duas telas num arquivo só, porque são dois momentos da mesma coisa: enquanto
 * não houver base, o convite a criar ou escolher; havendo, as três gavetas com
 * as chaves de habilitar. Quem acabou de criar a base cai na tela que já
 * conhece, em vez de numa página que nunca viu.
 *
 * O estado chega pronto no HTML (`#estado-da-base`) e é devolvido inteiro por
 * toda rota que muda alguma coisa. Então aqui não se recalcula estado nenhum:
 * manda o pedido, recebe o retrato novo, repinta. É o que impede a tela e o
 * disco discordarem depois de um erro no meio do caminho.
 */
(() => {
  "use strict";

  const tela = document.getElementById("tela");
  const janela = document.getElementById("janela-da-gaveta");
  const corpoDaGaveta = document.getElementById("corpo-da-gaveta");
  const tituloDaGaveta = document.getElementById("titulo-da-gaveta");
  const escolherArquivo = document.getElementById("arquivo-csv");

  let E = {};
  try {
    E = JSON.parse(document.getElementById("estado-da-base").textContent) || {};
  } catch (erro) {
    E = { tem: false, gavetas: [], conhecidas: [] };
  }

  /* O que a tela vazia está mostrando agora: "", "criar" ou "escolher". Mora
     fora da pintura para sobreviver a ela — repintar não pode fechar o
     formulário que a pessoa está preenchendo. */
  let aba = "";
  let rascunho = { nome: "", onde: "", caminho: "" };

  /* O nome que a pasta ganha quando ele não dá nenhum. O servidor manda o
     mesmo valor para os dois lados não divergirem. */
  const NOME_PADRAO = (E.nome_padrao || "database");

  /* O teto do Windows para o caminho INTEIRO, arquivo incluído. Estourar não
     dá erro claro: o arquivo simplesmente «não existe». */
  const TETO = 260;

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  /* Cada gaveta tem o desenho de quem vai usá-la; a base inteira tem a
     pilha de discos. Os desenhos moram no CSS, num lugar só. */
  const DESENHOS = {
    dicionario: "var(--ic-digitais)",
    linhas: "var(--ic-linhas)",
    registros: "var(--ic-arquivos)",
  };

  const icone = (tamanho, qual) => {
    const s = criar("span", "icone-mascara ic");
    s.style.setProperty("--ic", DESENHOS[qual] || "var(--ic-base)");
    s.style.width = tamanho + "px";
    s.style.height = tamanho + "px";
    return s;
  };

  const milhar = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

  /* O apelido tem que dar o MESMO resultado que o do servidor: é ele que a
     prévia mostra antes de criar, e uma prévia que mente é pior que nenhuma. */
  const apelido = (nome) => {
    const limpo = String(nome || "").normalize("NFD").replace(/[̀-ͯ]/g, "");
    return limpo.replace(/[^a-zA-Z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase() || "base";
  };

  // =========================================================================
  // O navegador de pastas
  // =========================================================================

  const janelaDoNavegador = document.getElementById("janela-do-navegador");
  let aoEscolherPasta = null;
  let pastaAtual = "";

  const ICONE_PASTA = "<svg viewBox='0 0 16 16' width='15' height='15' fill='none' " +
    "stroke='currentColor' stroke-width='1.4' stroke-linecap='round' " +
    "stroke-linejoin='round'><path d='M1.8 4.2h4l1.2 1.6h7.2v7.4H1.8z'/></svg>";

  async function abrirNavegador(inicial, aoTerminar) {
    aoEscolherPasta = aoTerminar;
    if (!janelaDoNavegador.open) janelaDoNavegador.showModal();
    await irPara(inicial || "");
  }

  async function irPara(caminho) {
    const lista = document.getElementById("lista-de-pastas");
    lista.replaceChildren(criar("div", "pasta-item vazia", "Lendo…"));
    let dados = {};
    try {
      const r = await fetch("/api/base/pastas?onde=" + encodeURIComponent(caminho || ""));
      dados = await r.json();
    } catch (erro) {
      lista.replaceChildren(criar("div", "pasta-item vazia", "Não deu para ler esta pasta."));
      return;
    }
    pastaAtual = dados.atual || "";
    document.getElementById("caminho-atual").textContent = pastaAtual;

    const atalhos = document.getElementById("atalhos-de-pasta");
    atalhos.replaceChildren();
    for (const a of (dados.atalhos || [])) {
      const b = criar("button", "chave", a.nome);
      b.type = "button";
      b.title = a.caminho;
      b.addEventListener("click", () => irPara(a.caminho));
      atalhos.append(b);
    }

    lista.replaceChildren();
    if (dados.pai) {
      const subir = criar("button", "pasta-item subir", "..  subir um nível");
      subir.type = "button";
      subir.addEventListener("click", () => irPara(dados.pai));
      lista.append(subir);
    }
    for (const pasta of (dados.pastas || [])) {
      const b = criar("button", "pasta-item");
      b.type = "button";
      const ic = criar("span", "ic");
      ic.innerHTML = ICONE_PASTA;
      b.append(ic, criar("span", null, pasta.nome));
      b.addEventListener("click", () => irPara(pasta.caminho));
      lista.append(b);
    }
    if (!(dados.pastas || []).length) {
      lista.append(criar("div", "pasta-item vazia",
        dados.existe === false ? "Esta pasta não existe nesta máquina."
                               : "Nenhuma subpasta aqui — pode usar esta mesmo."));
    }
  }

  function fecharNavegador() {
    aoEscolherPasta = null;
    if (janelaDoNavegador.open) janelaDoNavegador.close();
  }
  document.getElementById("fechar-navegador").addEventListener("click", fecharNavegador);
  document.getElementById("cancelar-navegador").addEventListener("click", fecharNavegador);
  document.getElementById("usar-pasta").addEventListener("click", () => {
    const escolhida = pastaAtual;
    const terminar = aoEscolherPasta;
    fecharNavegador();
    if (terminar) terminar(escolhida);
  });

  /* O «…» tenta primeiro a janela DO SISTEMA — a de «salvar em…», que a
     pessoa já sabe usar. A lista desenhada na página é o plano B, para a
     máquina em que aquela não abre; quem clicou não precisa saber a
     diferença, o trabalho é o mesmo. */
  async function escolherPasta(inicial, aoTerminar, botao) {
    if (botao) { botao.disabled = true; botao.textContent = "…"; }
    try {
      const r = await fetch("/api/base/pasta-nativa", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inicial: inicial || "" }),
      });
      const dados = await r.json();
      if (dados.disponivel) {
        if (dados.caminho) aoTerminar(dados.caminho);
        return;                      // fechou sem escolher: não abre mais nada
      }
    } catch (erro) { /* cai no de dentro da página */ }
    finally {
      if (botao) { botao.disabled = false; botao.textContent = "…"; }
    }
    await abrirNavegador(inicial, aoTerminar);
  }

  function botaoDeProcurar(aoTerminar, qual) {
    const b = criar("button", "chave procurar", "…");
    b.type = "button";
    b.title = "procurar a pasta no computador";
    b.addEventListener("click", () => escolherPasta(qual(), aoTerminar, b));
    return b;
  }

  async function pedir(url, corpo) {
    const resposta = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo || {}),
    });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) throw new Error(dados.erro || "Não deu para completar.");
    return dados;
  }

  function recado(texto, qual) {
    const p = criar("p", "recado-da-base " + (qual || ""), texto);
    return p;
  }

  // =========================================================================
  // A base que ainda não existe
  // =========================================================================

  function telaVazia() {
    const caixa = criar("div", "base-vazia");
    const ic = criar("span", "ic");
    ic.append(icone(44));
    caixa.append(ic);
    caixa.append(criar("h2", null, "Você ainda não tem uma base de dados"));
    caixa.append(criar("p", "ajuda",
      "A base de dados guarda os arquivos da modelagem de linhas, o dicionário " +
      "de sinais digitais e o que vier depois. Usar uma base é opcional: a " +
      "ferramenta abre e analisa oscilografia sem ela."));

    const dupla = criar("div", "dupla");
    const bCriar = criar("button", "chave-grande" + (aba === "criar" ? " aberta" : ""),
                         "＋  criar uma base nova");
    bCriar.type = "button";
    bCriar.addEventListener("click", () => { aba = aba === "criar" ? "" : "criar"; pintar(); });
    const bEscolher = criar("button", "chave-grande" + (aba === "escolher" ? " aberta" : ""),
                            "…  escolher uma base existente");
    bEscolher.type = "button";
    bEscolher.addEventListener("click", () => { aba = aba === "escolher" ? "" : "escolher"; pintar(); });
    dupla.append(bCriar, bEscolher);
    caixa.append(dupla);

    if (aba === "criar") caixa.append(formaDeCriar());
    if (aba === "escolher") caixa.append(listaDeBases());
    return caixa;
  }

  function formaDeCriar() {
    const forma = criar("div", "forma-da-base");
    const sep = () => {
      const m = rascunho.onde || E.onde_nasce || "";
      return m.includes("\\") || !m.includes("/") ? "\\" : "/";
    };
    const mae = () => (rascunho.onde.trim() || "").replace(/[\\/]+$/, "");
    const pasta = () => rascunho.nome.trim() || NOME_PADRAO;
    const destino = () => mae() + sep() + pasta();
    /* O caminho mais fundo que a base vai ter: a gaveta de nome mais
       comprido, mais um arquivo de nome plausível. Medir o `base.json`
       seria medir o caso fácil, e o aviso serve para o difícil. */
    const maisFundo = () => {
      const maisLonga = (E.gavetas || []).map((g) => g.id)
        .sort((a, b) => b.length - a.length)[0] || "linhas";
      return destino() + sep() + maisLonga + sep() + "estruturas-da-linha.kmz";
    };

    /* 1 — O NOME. Vem primeiro porque é a pasta: é dele que sai o resto do
       desenho, e vê-lo mudar na estrutura é o que explica o que ele é. */
    const campoNome = criar("input");
    campoNome.type = "text";
    campoNome.value = rascunho.nome;
    campoNome.placeholder = NOME_PADRAO;
    campoNome.spellcheck = false;
    const c1 = criar("div");
    c1.append(criar("label", null, "nome da base"));
    c1.append(campoNome);
    c1.append(criar("p", "dizer-do-campo",
      "É o nome da pasta. Em branco, fica «" + NOME_PADRAO + "»."));

    /* 2 — ONDE. O «…» abre a janela do próprio Windows; a lista desenhada na
       página é o plano B, para a máquina em que aquela não abre. */
    const campoOnde = criar("input");
    campoOnde.type = "text";
    campoOnde.value = rascunho.onde;
    campoOnde.placeholder = E.onde_nasce || "";
    campoOnde.spellcheck = false;
    const linhaOnde = criar("div", "campo-com-botao");
    linhaOnde.append(campoOnde, botaoDeProcurar((escolhida) => {
      campoOnde.value = escolhida;
      desenhar();
    }, () => campoOnde.value.trim() || E.onde_nasce || ""));
    const c2 = criar("div");
    c2.append(criar("label", null, "onde ela vai ficar"));
    c2.append(linhaOnde);

    /* 3 — A ESTRUTURA e a BARRA, que só existem depois de haver caminho. */
    const palco = criar("div", "palco-da-base");

    const ICONE_PASTA = "M1.6 4.2a1 1 0 0 1 1-1h3.2l1.4 1.6h6.2a1 1 0 0 1 1 1" +
      "v6.8a1 1 0 0 1-1 1H2.6a1 1 0 0 1-1-1z";
    const ICONE_ARQUIVO = "M3.4 1.8h5.2l3.8 3.8v8.6H3.4z";
    const desenhoDe = (qual) => {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 16 16");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("class", "ic-da-arvore " + qual);
      const caminhos = qual === "pasta" ? [ICONE_PASTA]
                                        : [ICONE_ARQUIVO, "M8.6 1.8v3.8h3.8"];
      for (const d of caminhos) {
        const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
        p.setAttribute("d", d);
        svg.append(p);
      }
      return svg;
    };

    /* A estrutura é SECA: só ícone e nome. Comentário ao lado de cada linha
       era o que a tornava ilegível -- escolha dele, 19/10/2026. */
    const estrutura = () => {
      const a = criar("div", "estrutura-da-base");
      const linha = (nivel, qual, classe, texto) => {
        const l = criar("div", "galho");
        l.style.paddingLeft = (nivel * 22) + "px";
        l.append(desenhoDe(qual));
        l.append(criar("span", classe, texto));
        a.append(l);
      };
      linha(0, "pasta", "raiz", mae() + sep());
      linha(1, "pasta", "viva", pasta() + sep());
      linha(2, "arquivo", "arq", "base.json");
      for (const g of (E.gavetas || [])) {
        linha(2, "pasta", "fixo", g.id + sep());
        if (g.id === "dicionario") linha(3, "arquivo", "arq", "dicionario.csv");
        if (g.id === "linhas") {
          linha(3, "arquivo", "arq", "linhas.csv");
          linha(3, "pasta", "fixo", "estruturas" + sep());
        }
      }
      return a;
    };

    /* POR QUE o caminho é ruim. Avisa, nunca bloqueia: o botão «criar»
       continua valendo em todos os casos -- regra dele. */
    const PROIBIDOS_NO_NOME = /[<>:"|?*\\/]/g;
    const PROIBIDOS_NO_CAMINHO = /[<>:"|?*]/g;
    const porques = () => {
      const achados = [];
      const caminho = mae();
      const nome = pasta();

      const nomeMau = [...new Set(nome.match(PROIBIDOS_NO_NOME) || [])];
      if (nomeMau.length) achados.push({ nivel: "ruim", peso: 40, marca: "nome",
        texto: "o nome tem " + nomeMau.map((m) => "«" + m + "»").join(", ") +
               " e o Windows não aceita esses caracteres em nome de pasta" });
      else if (/[ .]$/.test(rascunho.nome)) achados.push({ nivel: "atencao", peso: 15, marca: "nome",
        texto: "o nome termina em espaço ou ponto, e o Windows corta isso sem avisar" });
      else if (/[^\x00-\x7F]/.test(nome)) achados.push({ nivel: "atencao", peso: 8, marca: "nome",
        texto: "o nome tem acento — funciona aqui, mas atrapalha quem abrir a base noutra máquina" });

      const caminhoMau = [...new Set(
        (caminho.replace(/^[A-Za-z]:/, "").match(PROIBIDOS_NO_CAMINHO) || []))];
      if (caminhoMau.length) achados.push({ nivel: "ruim", peso: 35, marca: "caminho",
        texto: "o caminho tem " + caminhoMau.map((m) => "«" + m + "»").join(", ") +
               " e o Windows não aceita esses caracteres" });

      const niveis = caminho.split(/[\\/]/).filter(Boolean).length;
      if (niveis > 4) achados.push({
        nivel: niveis > 6 ? "ruim" : "atencao", peso: niveis > 6 ? 30 : 15, marca: "fundo demais",
        texto: "são " + niveis + " níveis até aqui e a base acrescenta mais três — " +
               "escolha um caminho mais próximo da raiz" });

      const n = maisFundo().length;
      if (n >= TETO) achados.push({ nivel: "ruim", peso: 40, marca: "comprimento",
        texto: "o arquivo mais fundo fica com " + n + " caracteres, e acima de " + TETO +
               " o Windows não o encontra — o erro não diz isso, ele só «não existe»" });
      else if (n > 200) achados.push({ nivel: "atencao", peso: 12, marca: "comprimento",
        texto: "o arquivo mais fundo fica com " + n + " dos " + TETO + " do Windows, " +
               "e sobra pouco para as subpastas que vierem depois" });

      const programa = (E.pasta_do_programa || "").toLowerCase();
      if (programa && caminho.toLowerCase().startsWith(programa))
        achados.push({ nivel: "ruim", peso: 45, marca: "pasta do programa",
          texto: "aqui dentro você pode perder a base numa atualização do OscLab — " +
                 "guarde-a fora da pasta dele" });

      if (/onedrive|dropbox|google ?drive/i.test(caminho))
        achados.push({ nivel: "atencao", peso: 18, marca: "nuvem",
          texto: "pasta sincronizada: o sincronizador pode segurar o arquivo bem na " +
                 "hora em que o programa grava" });

      if (/^[A-Za-z]:[\\/](Windows|Program Files)/i.test(caminho))
        achados.push({ nivel: "ruim", peso: 35, marca: "pasta do sistema",
          texto: "pasta do sistema: o Windows vai pedir permissão de administrador " +
                 "a cada gravação" });

      return achados;
    };

    const qualidade = () => {
      const achados = porques();
      const pontos = Math.max(0, 100 - achados.reduce((t, a) => t + a.peso, 0));
      const cor = pontos >= 80 ? "bom" : pontos >= 45 ? "atencao" : "ruim";
      const palavra = pontos >= 80 ? "caminho bom"
        : pontos >= 45 ? "dá para usar" : "caminho ruim";
      const c = criar("div", "qualidade-do-caminho");
      const barra = criar("div", "barra-da-qualidade");
      const cheio = criar("i", cor);
      cheio.style.width = pontos + "%";
      barra.append(cheio);
      c.append(barra);
      const v = criar("div", "veredito");
      v.append(criar("span", "palavra " + cor, palavra));
      v.append(criar("span", "resto",
        "· " + maisFundo().length + " de " + TETO + " caracteres no arquivo mais fundo"));
      c.append(v);
      /* Os porquês só aparecem quando HÁ porquê: caminho limpo mostra a
         barra verde e mais nada. */
      if (achados.length) {
        const lista = criar("div", "porques");
        for (const a of achados) {
          const l = criar("div", "porque " + a.nivel);
          l.append(criar("span", "marca", a.marca));
          l.append(criar("span", null, a.texto));
          lista.append(l);
        }
        c.append(lista);
      }
      return c;
    };

    const ok = criar("button", "chave-grande aberta", "criar a base");
    ok.type = "button";
    const aviso = criar("div");
    ok.addEventListener("click", async () => {
      ok.disabled = true;
      try {
        E = await pedir("/api/base/criar",
                        { nome: campoNome.value, onde: campoOnde.value });
        aba = "";
        pintar();
      } catch (erro) {
        aviso.replaceChildren(recado(erro.message, "ruim"));
        ok.disabled = false;
      }
    });

    /* Só o palco é repintado a cada tecla: repintar o formulário inteiro
       tiraria o foco do campo no meio da digitação. */
    const desenhar = () => {
      rascunho.nome = campoNome.value;
      rascunho.onde = campoOnde.value;
      palco.replaceChildren();
      if (!mae()) {
        palco.append(criar("div", "espera-do-caminho",
          "Escolha a pasta para ver como a base vai ficar."));
        return;
      }
      palco.append(estrutura());
      palco.append(qualidade());
      palco.append(ok);
      palco.append(aviso);
    };
    campoNome.addEventListener("input", desenhar);
    campoOnde.addEventListener("input", desenhar);
    desenhar();

    forma.append(c1, c2, palco);
    return forma;
  }

  function listaDeBases() {
    const caixa = criar("div", "bases-achadas");

    for (const b of (E.conhecidas || [])) {
      const linha = criar("button", "base-achada" + (b.existe ? "" : " sumiu"));
      linha.type = "button";
      const lado = criar("div");
      lado.append(criar("div", "nm", b.nome));
      lado.append(criar("div", "cm", b.pasta));
      linha.append(lado);
      linha.append(criar("span", "estado", b.existe ? "abrir" : "pasta não encontrada"));
      if (b.existe) {
        linha.addEventListener("click", () => trocarPara(b.pasta, caixa));
      } else {
        /* Fica na lista, inerte e explicada. Sumir sozinha seria decidir pelo
           dono: o pen-drive pode estar na gaveta e voltar amanhã. */
        linha.disabled = true;
        linha.title = "O caminho não existe nesta máquina agora. " +
                      "Conecte o disco ou aponte o caminho novo abaixo.";
      }
      caixa.append(linha);
    }

    const campo = criar("input");
    campo.type = "text";
    campo.value = rascunho.caminho;
    campo.placeholder = "ou procure a pasta no computador";
    campo.addEventListener("input", () => { rascunho.caminho = campo.value; });
    const linha = criar("div", "campo-com-botao");
    linha.append(campo, botaoDeProcurar((escolhida) => { campo.value = escolhida; },
                                        () => campo.value.trim()));
    const bloco = criar("div", "forma-da-base");
    const c = criar("div");
    c.append(criar("label", null, "caminho da base"));
    c.append(linha);
    const ok = criar("button", "chave-grande aberta", "usar esta database");
    ok.type = "button";
    ok.addEventListener("click", () => trocarPara(campo.value, caixa));
    bloco.append(c, ok);
    caixa.append(bloco);
    return caixa;
  }

  /* «voltar» mora no CABEÇALHO, ao lado de «menu» — escolha dele,
     19/10/2026. As duas chaves fazem a mesma coisa (sair de onde se está) e
     ficam juntas; o pé do painel ficou limpo, e o botão não muda de lugar
     conforme o painel. Só aparece quando há painel aberto. */
  const chaveDeVoltar = document.getElementById("voltar-passo");
  if (chaveDeVoltar) {
    chaveDeVoltar.addEventListener("click", () => { aba = ""; pintar(); });
  }

  async function trocarPara(caminho, onde) {
    try {
      E = await pedir("/api/base/escolher", { pasta: caminho });
      aba = "";
      pintar();
    } catch (erro) {
      const antigo = onde.querySelector(".recado-da-base");
      if (antigo) antigo.remove();
      onde.append(recado(erro.message, "ruim"));
    }
  }

  // =========================================================================
  // A base que existe
  // =========================================================================

  function telaCheia() {
    const caixa = criar("div");

    const topo = criar("div", "base-topo");
    const ic = criar("span", "ic");
    ic.append(icone(34));
    const bloco = criar("div", "bloco");
    bloco.append(criar("h2", null, E.base ? E.base.nome : "Base de dados"));
    bloco.append(criar("div", "caminho", E.base ? E.base.pasta : ""));
    const acoes = criar("div", "acoes-da-base");
    const trocar = criar("button", "chave", "trocar de base");
    trocar.type = "button";
    trocar.addEventListener("click", () => { E = { ...E, tem: false }; aba = "escolher"; pintar(); });
    acoes.append(trocar);
    topo.append(ic, bloco, acoes);
    caixa.append(topo);

    if (E.base && !E.base.existe) {
      caixa.append(recado(
        "A pasta desta base não está nesta máquina agora. O programa continua " +
        "funcionando sem ela — nada foi apagado.", "ruim"));
    }
    if (E.base && E.base.futura) {
      caixa.append(recado(
        "Esta base foi montada por uma versão mais nova do OscLab. O que este " +
        "programa souber ler, ele lê.", "ruim"));
    }

    const gavetas = criar("div", "gavetas");
    for (const g of (E.gavetas || [])) gavetas.append(cartaoDaGaveta(g));
    caixa.append(gavetas);

    const p = criar("p", "ajuda");
    p.style.marginTop = "14px";
    p.textContent = "Desligar uma gaveta não apaga nada — só faz o programa " +
      "parar de consultá-la. Nenhuma delas é necessária para o leitor funcionar.";
    caixa.append(p);
    return caixa;
  }

  function cartaoDaGaveta(g) {
    const c = criar("div", "gaveta " + (g.ligada ? "ligada" : "desligada"));
    const ic = criar("span", "ic");
    ic.append(icone(26, g.id));
    const meio = criar("div");
    meio.append(criar("h3", null, g.nome));
    const conta = criar("div", "conta");
    conta.append(criar("b", null, milhar(g.itens)));
    conta.append(document.createTextNode(" " + (g.itens === 1 ? "item" : "itens") +
                                         " · " + g.dizer));
    meio.append(conta);
    if (!g.ligada) meio.append(criar("div", "efeito", "desligada — " + g.sem));
    else if (!g.editavel) {
      meio.append(criar("div", "efeito",
        "a pasta já existe e espera o módulo que vai usá-la"));
    }

    const pilha = criar("div", "pilha");
    const sw = criar("button", "interruptor");
    sw.type = "button";
    sw.setAttribute("aria-pressed", g.ligada ? "true" : "false");
    sw.append(criar("span", "bola"));
    sw.append(criar("span", null, g.ligada ? "habilitada" : "desabilitada"));
    sw.addEventListener("click", async () => {
      sw.disabled = true;
      try {
        E = await pedir("/api/base/gaveta", { gaveta: g.id, ligada: !g.ligada });
      } catch (erro) { /* a tela repinta com o estado que o servidor confirmar */ }
      pintar();
    });
    pilha.append(sw);

    const abrir = criar("button", "chave", "abrir");
    abrir.type = "button";
    abrir.disabled = !g.ligada || !g.editavel;
    abrir.title = !g.ligada ? "gaveta desabilitada"
                : !g.editavel ? "esta gaveta chega com o módulo que a usa"
                : "abrir a tabela";
    if (g.editavel) abrir.addEventListener("click", () => abrirDicionario(g));
    pilha.append(abrir);

    c.append(ic, meio, pilha);
    return c;
  }

  // =========================================================================
  // O DICIONÁRIO
  // =========================================================================

  const SEM_CATEGORIA = "sem categoria";
  let verbetes = [];
  let categorias = ["", "trip", "partida", "estado", "alarme"];
  let busca = "";
  let novo = false;

  async function abrirDicionario(g) {
    tituloDaGaveta.textContent = g.nome;
    corpoDaGaveta.replaceChildren(criar("p", "ajuda", "Carregando…"));
    if (!janela.open) janela.showModal();
    try {
      const r = await fetch("/api/base/dicionario");
      const dados = await r.json();
      verbetes = dados.verbetes || [];
      if (Array.isArray(dados.categorias) && dados.categorias.length) categorias = dados.categorias;
    } catch (erro) {
      verbetes = [];
    }
    busca = "";
    novo = false;
    pintarGaveta();
  }

  function pintarGaveta() {
    corpoDaGaveta.replaceChildren();

    const barra = criar("div", "barra-da-gaveta");
    const campo = criar("input", "busca-da-gaveta");
    campo.type = "search";
    campo.placeholder = "procurar sinal, descrição, fabricante ou modelo…";
    campo.value = busca;
    campo.addEventListener("input", () => {
      busca = campo.value;
      pintarTabela();
    });
    const bNovo = criar("button", "chave", "＋ sinal");
    bNovo.type = "button";
    bNovo.addEventListener("click", () => { novo = !novo; pintarGaveta(); });
    const bImportar = criar("button", "chave", "importar CSV");
    bImportar.type = "button";
    bImportar.addEventListener("click", () => escolherArquivo.click());
    barra.append(campo, bNovo, bImportar);
    corpoDaGaveta.append(barra);

    if (novo) corpoDaGaveta.append(formaDeVerbete());

    const rolo = criar("div", "rolo-da-gaveta");
    rolo.id = "rolo";
    corpoDaGaveta.append(rolo);

    const p = criar("p", "ajuda");
    p.style.marginTop = "10px";
    p.textContent = "Clique numa descrição para editar e na categoria para " +
      "classificar. Os dois são opcionais: o que você não souber fica vazio, " +
      "e o leitor mostra o nome cru sem reclamar.";
    corpoDaGaveta.append(p);

    pintarTabela();
  }

  function formaDeVerbete() {
    const forma = criar("div", "barra-da-gaveta");
    const campos = {};
    for (const [chave, rot] of [["fabricante", "fabricante"], ["modelo", "modelo"],
                                ["sinal", "sinal"]]) {
      const c = criar("input", "busca-da-gaveta");
      c.type = "text";
      c.placeholder = rot;
      c.style.flex = "1 1 110px";
      campos[chave] = c;
      forma.append(c);
    }
    const ok = criar("button", "chave escolhido", "anotar");
    ok.type = "button";
    ok.addEventListener("click", async () => {
      const sinal = campos.sinal.value.trim();
      if (!sinal) { campos.sinal.focus(); return; }
      await anotar({
        fabricante: campos.fabricante.value, modelo: campos.modelo.value,
        sinal: sinal, descricao: "", categoria: "",
      });
      campos.sinal.value = "";
      busca = "";
      pintarGaveta();
    });
    forma.append(ok);
    return forma;
  }

  function pintarTabela() {
    const rolo = document.getElementById("rolo");
    if (!rolo) return;
    rolo.replaceChildren();

    const alvo = busca.trim().toLowerCase();
    const vistos = verbetes.filter((v) => !alvo ||
      [v.sinal, v.descricao, v.fabricante, v.modelo].join(" ").toLowerCase().includes(alvo));

    if (!vistos.length) {
      rolo.append(criar("p", "ajuda", verbetes.length
        ? "Nenhum sinal com «" + busca + "». Use «＋ sinal» para cadastrar este."
        : "A gaveta está vazia. Cadastre o primeiro sinal, ou importe um CSV."));
      return;
    }

    const tabela = criar("table", "verbetes");
    const cabeca = criar("thead");
    const tr = criar("tr");
    for (const h of ["fabricante", "modelo", "sinal", "descrição", "categoria"]) {
      tr.append(criar("th", null, h));
    }
    cabeca.append(tr);
    tabela.append(cabeca);

    const corpo = criar("tbody");
    vistos.forEach((v, i) => {
      const linha = criar("tr", i % 2 ? "par" : "");
      linha.append(criar("td", null, v.fabricante));
      linha.append(criar("td", "cod", v.modelo));
      linha.append(criar("td", "cod" + (v.sinal.length > 12 ? " longo" : ""), v.sinal));

      const celula = criar("td", "descricao");
      if (v.descricao) celula.append(criar("span", null, v.descricao));
      else celula.append(criar("span", "sem-descricao",
                               "sem descrição — aparece com o nome cru"));
      celula.title = "clique para escrever o que este sinal é";
      celula.addEventListener("click", () => editarDescricao(celula, v));
      linha.append(celula);

      const celulaCategoria = criar("td");
      const bt = criar("button", "tipinho " + (v.categoria || "sem-categoria"),
                       v.categoria || SEM_CATEGORIA);
      bt.type = "button";
      bt.title = "clique para classificar — só classifique o que tiver certeza";
      bt.addEventListener("click", async () => {
        const i = categorias.indexOf(v.categoria || "");
        await anotar({ ...v, categoria: categorias[(i + 1) % categorias.length] });
        pintarTabela();
      });
      celulaCategoria.append(bt);
      linha.append(celulaCategoria);
      corpo.append(linha);
    });
    tabela.append(corpo);
    rolo.append(tabela);
  }

  function editarDescricao(celula, v) {
    const campo = criar("input");
    campo.type = "text";
    campo.value = v.descricao || "";
    campo.placeholder = "deixe vazio se não tiver certeza";
    celula.replaceChildren(campo);
    campo.focus();
    campo.select();
    let fechado = false;
    const terminar = async (salvar) => {
      if (fechado) return;
      fechado = true;
      if (salvar) await anotar({ ...v, descricao: campo.value });
      pintarTabela();
    };
    campo.addEventListener("blur", () => terminar(true));
    campo.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") terminar(true);
      if (ev.key === "Escape") terminar(false);
    });
  }

  /* Grava um verbete e atualiza a cópia que a tela tem. A contagem da gaveta
     vem do servidor junto: é ela que aparece no cartão e na tela inicial, e
     um número contado aqui divergiria do disco na primeira falha de rede. */
  async function anotar(v) {
    try {
      const dados = await pedir("/api/base/dicionario", v);
      const salvo = dados.verbete;
      const i = verbetes.findIndex((x) =>
        x.sinal.toUpperCase() === salvo.sinal.toUpperCase() &&
        x.modelo.toUpperCase() === salvo.modelo.toUpperCase() &&
        x.fabricante.toUpperCase() === salvo.fabricante.toUpperCase());
      if (i >= 0) verbetes[i] = salvo;
      else verbetes.push(salvo);
      const g = (E.gavetas || []).find((x) => x.id === "dicionario");
      if (g) g.itens = dados.itens;
      pintar();
    } catch (erro) {
      corpoDaGaveta.append(recado(erro.message, "ruim"));
    }
  }

  escolherArquivo.addEventListener("change", async () => {
    const arquivo = escolherArquivo.files && escolherArquivo.files[0];
    if (!arquivo) return;
    const forma = new FormData();
    forma.append("arquivo", arquivo);
    try {
      const r = await fetch("/api/base/dicionario/importar", { method: "POST", body: forma });
      const dados = await r.json();
      if (!r.ok) throw new Error(dados.erro || "Não deu para importar.");
      const atual = await (await fetch("/api/base/dicionario")).json();
      verbetes = atual.verbetes || [];
      const estado = await (await fetch("/api/base")).json();
      E = estado;
      pintarGaveta();
      corpoDaGaveta.append(recado(
        dados.acrescentados + " acrescentados, " + dados.corrigidos +
        " corrigidos — " + dados.total + " no total.", "bom"));
      pintar();
    } catch (erro) {
      corpoDaGaveta.append(recado(erro.message, "ruim"));
    }
    escolherArquivo.value = "";
  });

  document.getElementById("fechar-gaveta").addEventListener("click", () => janela.close());

  // =========================================================================

  function pintar() {
    tela.replaceChildren(E.tem ? telaCheia() : telaVazia());
    if (chaveDeVoltar) chaveDeVoltar.hidden = !aba;
  }

  pintar();
})();
