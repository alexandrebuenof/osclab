/* A tela de arquivos: arrastar, enviar, listar, remover.
 *
 * Sem biblioteca nenhuma de propósito — o que esta tela faz é `fetch` e montar
 * uma lista, e uma dependência aqui teria que viajar dentro do pacote offline
 * para funcionar numa subestação sem internet.
 */

(() => {
  "use strict";

  const area = document.getElementById("envio");
  const escolher = document.getElementById("escolher");
  const botaoEscolher = document.getElementById("botao-escolher");
  const recado = document.getElementById("recado");
  const lista = document.getElementById("lista");
  const contagem = document.getElementById("contagem");
  const espera = document.getElementById("espera");

  // --- utilidades ---------------------------------------------------------

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  const numero = (v, casas = 0) =>
    typeof v === "number" && isFinite(v)
      ? v.toLocaleString("pt-BR", {
          minimumFractionDigits: casas,
          maximumFractionDigits: casas,
        })
      : "—";

  // --- envio --------------------------------------------------------------

  async function enviar(arquivos) {
    if (!arquivos || arquivos.length === 0) return;

    recado.hidden = true;
    area.classList.add("ocupada");
    const painel = progressoDoEnvio([...arquivos]);

    try {
      const corpo = await enviarComProgresso([...arquivos], painel);
      painel.fase("lido", "pronto");
      relatar(corpo);
      await carregarLista();
    } catch (erro) {
      painel.fase("erro", `falhou: ${erro.message}`);
      mostrarRecado([`Falha no envio: ${erro.message}`], "ruim");
    } finally {
      area.classList.remove("ocupada");
      setTimeout(() => painel.sumir(), 2600);
    }
  }

  // --- o progresso do envio -----------------------------------------------
  //
  // Um registro de relé chega a dezenas de MB, e numa rede de subestação o
  // envio leva tempo: sem número na tela, a pessoa não sabe se travou. Por
  // arquivo e no total, em kB e em %, e depois a fase «lendo», que é o
  // servidor abrindo o .cfg/.dat, conferindo o par e gravando no acervo — o
  // que sobra de espera depois que o último byte subiu.
  //
  // O XMLHttpRequest (em `envio.js`) diz quanto já subiu. A velocidade é a
  // real: em localhost a barra enche num piscar, e é isso mesmo.

  const kB = (bytes) => (bytes / 1024).toLocaleString("pt-BR",
    { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  function progressoDoEnvio(lista) {
    const caixa = criar("div", "progresso");
    caixa.setAttribute("role", "status");
    caixa.dataset.fase = "enviando";
    const titulo = criar("div", "progresso-titulo");
    const nomeFase = criar("span", "progresso-fase", "enviando");
    const detalhe = criar("span", "progresso-detalhe", `${lista.length} arquivo(s)`);
    titulo.append(nomeFase, detalhe);
    caixa.append(titulo);
    const total = lista.reduce((s, a) => s + a.size, 0);

    const linha = (nome, tamanho, classe) => {
      const l = criar("div", "progresso-linha" + (classe ? " " + classe : ""));
      const barra = criar("span", "progresso-barra");
      const cheio = criar("span", "progresso-cheio");
      barra.append(cheio);
      const numeros = criar("span", "progresso-numeros", `0,0 de ${kB(tamanho)} kB`);
      const pct = criar("span", "progresso-pct", "0 %");
      l.append(criar("span", "progresso-nome", nome), barra, numeros, pct);
      caixa.append(l);
      return { l, cheio, numeros, pct, tamanho };
    };
    const pinta = (x, enviados) => {
      const f = x.tamanho ? Math.min(1, enviados / x.tamanho) : 1;
      x.cheio.style.width = `${(f * 100).toFixed(1)}%`;
      x.numeros.textContent = `${kB(enviados)} de ${kB(x.tamanho)} kB`;
      x.pct.textContent = `${Math.floor(f * 100)} %`;
      x.l.classList.toggle("feito", f >= 1);
    };

    const linhas = lista.map((a) => linha(a.name, a.size));
    const linhaTotal = linha("total", total, "progresso-total");
    area.after(caixa);

    return {
      total,
      /* O navegador diz quantos bytes do PEDIDO subiram, não de qual
       * arquivo: os arquivos vão em fila dentro do formulário, então o
       * enviado é repartido na ordem — enche o primeiro, depois o segundo.
       * O pedido tem também os separadores do formulário (algumas centenas
       * de bytes); por isso os números ficam presos ao tamanho de cada um. */
      mostrar(enviados) {
        let resto = Math.min(enviados, total);
        for (const x of linhas) {
          const deste = Math.max(0, Math.min(x.tamanho, resto));
          resto -= deste;
          pinta(x, deste);
        }
        pinta(linhaTotal, Math.min(enviados, total));
      },
      fase(qual, texto) {
        caixa.dataset.fase = qual;
        nomeFase.textContent = texto;
        if (qual === "lendo") {
          detalhe.textContent = "abrindo os arquivos, conferindo o par e gravando no acervo";
        }
      },
      sumir() { caixa.remove(); },
    };
  }

  /* O pedido e a leitura da resposta são do `envio.js`, o MESMO que os menus
     da tela de oscilografia usam: aqui só se pinta o progresso por arquivo. */
  function enviarComProgresso(arquivos, painel) {
    return window.osclabEnvio.enviar(arquivos, {
      // a fração é do pedido inteiro; ela vale para os arquivos
      aoProgresso: (f) => painel.mostrar(f * painel.total),
      // O último byte subiu: a espera dali em diante é a leitura.
      aoLer: () => painel.fase("lendo", "lendo e conferindo"),
    });
  }

  function relatar(corpo) {
    const { linhas, tom } = window.osclabEnvio.relato(corpo);
    mostrarRecado(linhas, tom);
  }

  function mostrarRecado(linhas, tom) {
    recado.className = `recado ${tom}`;
    recado.replaceChildren(...linhas.map((t) => criar("p", null, t)));
    recado.hidden = false;
  }

  // --- lista --------------------------------------------------------------

  async function carregarLista() {
    try {
      const resposta = await fetch("/api/acervo");
      const corpo = await resposta.json();
      desenharLista(corpo.itens || []);
      desenharEspera(corpo.aguardando || []);
    } catch (erro) {
      lista.replaceChildren(criar("p", "vazio", `Não consegui ler o acervo: ${erro.message}`));
    }
  }

  /** O «N registros no acervo» da barra de cima: o servidor o escreve ao
   * montar a página, e depois de um envio ele ficava velho até recarregar
   * (caça de bugs B10). A barra pode estar neste documento ou no de cima
   * (as abas são quadros), e os dois são da mesma origem. */
  function contarNaBarra(n) {
    const texto = `${n.toLocaleString("pt-BR")} ${n === 1 ? "registro" : "registros"} no acervo`;
    const docs = [document];
    try { if (window.top && window.top.document !== document) docs.push(window.top.document); } catch (_e) { /* outra origem */ }
    for (const doc of docs) {
      const a = doc.getElementById("acervo-da-barra");
      if (a) a.textContent = texto;
    }
  }

  function desenharLista(itens) {
    contagem.textContent = itens.length
      ? `${itens.length} registro${itens.length > 1 ? "s" : ""}`
      : "";
    contarNaBarra(itens.length);

    if (itens.length === 0) {
      lista.replaceChildren(
        criar("p", "vazio", "Nada ainda. Arraste um .cfg com o .dat dele, ou um .cev, acima.")
      );
      return;
    }
    lista.replaceChildren(...itens.map(cartao));
  }

  /* A antessala: o que chegou sem o par e está esperando a outra metade.
   * Fica à vista de propósito — o pareamento é por nome, e dois registros
   * diferentes com o mesmo nome poderiam se juntar errado sem ninguém ver. */
  function desenharEspera(itens) {
    if (!espera) return;
    if (itens.length === 0) {
      espera.hidden = true;
      espera.replaceChildren();
      return;
    }

    const titulo = criar("div", "titulo-linha");
    titulo.append(criar("h2", null, "Esperando o par"));
    const limpar = criar("button", "remover", "esquecer todos");
    limpar.type = "button";
    limpar.addEventListener("click", async () => {
      await fetch("/api/aguardando", { method: "DELETE" });
      await carregarLista();
    });
    titulo.append(limpar);

    const ul = criar("ul", "espera-lista");
    for (const item of itens) {
      const li = criar("li");
      li.append(criar("span", "nome", item.nome));
      li.append(criar("span", "tem", `tem ${item.tem.join(", ")}`));
      /* So' o `.cfg` espera par: o `.cff` e o `.cev` ja' sao um registro
       * inteiro sozinhos e nunca chegam aqui. */
      const falta = item.tem.includes(".cfg") ? ".dat" : ".cfg";
      li.append(criar("span", "falta", `falta ${falta}`));
      ul.append(li);
    }

    espera.replaceChildren(titulo, ul);
    espera.hidden = false;
  }

  function cartao(item) {
    const el = criar("article", "registro");

    const cabecalho = criar("div", "registro-topo");
    const titulo = criar("h3");
    const link = criar("a", null, item.nome);
    // Abre nas ABAS: o registro entra numa aba nova, ao lado das que já
    // estão abertas. Ver `templates/abas.html`.
    link.href = `/abas?abrir=${encodeURIComponent(item.sha)}`;
    titulo.append(link);
    cabecalho.append(titulo);
    /* O SELO do tipo de falta, antes de abrir o registro. Procurar «aquela
       bifásica de terça» numa lista de quarenta arquivos é o que o acervo
       fazia mal: a classificação já foi feita na importação, e mostrá-la
       aqui não custa uma leitura a mais. Escolha dele, 20/10/2026. */
    if (item.falta_tipo) {
      // A cor é a das fases da falta; a confiança é o pontinho ao lado. O
      // hover vem pronto do servidor, igual ao da tira do registro.
      const selo = criar("b", `selo-da-falta ${item.falta_cor || ""}`,
                         item.falta_sigla || item.falta_tipo);
      selo.title = item.falta_dica || "o tipo da falta que o OscLab leu deste registro";
      const ponto = criar("i", `ponto-da-confianca ${item.falta_confianca || ""}`);
      ponto.title = selo.title;
      const caixa = criar("span", "selo-com-ponto");
      caixa.append(selo);
      // O TRIP: o relé disparou. Sem trip, nada (a ausência não afirma que
      // ele restringiu).
      if (item.falta_trip) {
        const raio = criar("i", "raio-do-trip", "TRIP");
        raio.title = selo.title;
        caixa.append(raio);
      }
      caixa.append(ponto);
      cabecalho.append(caixa);
    } else if (item.versao_do_resumo >= 2) {
      /* Vazio só depois que o classificador rodou: aí «sem falta» quer
         dizer «olhei e não achei», que é diferente de «não olhei». */
      const selo = criar("b", "selo-da-falta vazio", "sem falta");
      selo.title = "O OscLab não achou descontinuidade nas correntes deste registro.";
      cabecalho.append(selo);
    }

    const remover = criar("button", "botao-x remover-do-acervo", "×");
    remover.type = "button";
    remover.title = "Tirar este registro do acervo";
    remover.addEventListener("click", () => removerItem(item));
    cabecalho.append(remover);
    el.append(cabecalho);

    const onde = [item.estacao, item.equipamento].filter(Boolean).join(" · ");
    if (onde) el.append(criar("p", "registro-onde", onde));

    const fatos = criar("dl", "fatos");
    const par = (rotulo, valor) => {
      fatos.append(criar("dt", null, rotulo));
      fatos.append(criar("dd", null, valor));
    };
    par("canais", `${item.n_analogicos} analóg. · ${item.n_digitais} digitais`);
    par("amostras", numero(item.n_amostras));
    par("taxa", `${numero(item.taxa_hz)} Hz · ${numero(item.amostras_por_ciclo, 2)}/ciclo`);
    par("formato", item.formato || "—");
    if (item.inicio) par("início", item.inicio);
    if (item.disparo) par("disparo", item.disparo);
    el.append(fatos);

    if (item.arquivos && item.arquivos.length) {
      el.append(criar("p", "arquivos", item.arquivos.join("  ")));
    }

    /* Sem o `.hdr` (ou um `.cev`, que já traz tudo), este registro não tem
       lógica nem ajuste para mostrar — e o COMTRADE não os prevê. Dizer isto
       aqui, na hora do envio, é mais barato do que deixar descobrir no painel
       vazio lá dentro: ainda dá para arrastar o arquivo que falta. */
    const nomes = (item.arquivos || []).map((x) => x.toLowerCase());
    const temLogica = nomes.some((x) => x.endsWith(".hdr") || x.endsWith(".cev")
                                     || x.endsWith(".cff"));
    if (!temLogica) {
      el.append(criar("p", "sem-logica",
        "sem lógica/ajustes — o COMTRADE não os prevê; mande o .hdr junto "
        + "para o relatório do relé vir também"));
    }
    // Duas coisas diferentes, e é de propósito que só uma leva triângulo.
    //
    // O AVISO é do leitor: o que ele fez, deixou de fora ou não conseguiu
    // confirmar. O RELATO é do relé — a classificação do evento, a distância
    // que ele calculou. Carimbar `⚠` numa frase como "o relé classificou o
    // evento como AB T" ensina o usuário a ignorar o triângulo, e aí o aviso
    // que importa passa despercebido junto.
    for (const aviso of item.avisos || []) {
      const linha = criar("p", "aviso");
      linha.append(criar("span", "sinal-de-aviso", "⚠"),
                   criar("span", null, aviso));
      el.append(linha);
    }
    for (const relato of item.relatos || []) {
      el.append(criar("p", "relato", relato));
    }
    return el;
  }

  async function removerItem(item) {
    if (!window.confirm(`Tirar "${item.nome}" do acervo?`)) return;
    try {
      await fetch(`/api/acervo/${item.sha}`, { method: "DELETE" });
      await carregarLista();
    } catch (erro) {
      mostrarRecado([`Não consegui remover: ${erro.message}`], "ruim");
    }
  }

  // --- arrastar e soltar --------------------------------------------------

  for (const evento of ["dragenter", "dragover", "dragleave", "drop"]) {
    area.addEventListener(evento, (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
  }
  area.addEventListener("dragenter", () => area.classList.add("sobre"));
  area.addEventListener("dragover", () => area.classList.add("sobre"));
  area.addEventListener("dragleave", () => area.classList.remove("sobre"));
  area.addEventListener("drop", (e) => {
    area.classList.remove("sobre");
    enviar(e.dataTransfer.files);
  });

  botaoEscolher.addEventListener("click", () => escolher.click());
  escolher.addEventListener("change", () => {
    enviar(escolher.files);
    escolher.value = "";
  });

  carregarLista();
})();
