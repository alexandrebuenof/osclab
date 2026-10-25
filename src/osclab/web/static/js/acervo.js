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

    const dados = new FormData();
    for (const arquivo of arquivos) dados.append("arquivos", arquivo);

    mostrarRecado([`Enviando ${arquivos.length} arquivo(s)…`], "neutro");
    area.classList.add("ocupada");

    try {
      const resposta = await fetch("/api/acervo", { method: "POST", body: dados });
      const corpo = await resposta.json();
      relatar(corpo);
      await carregarLista();
    } catch (erro) {
      mostrarRecado([`Falha no envio: ${erro.message}`], "ruim");
    } finally {
      area.classList.remove("ocupada");
    }
  }

  function relatar(corpo) {
    const linhas = [];
    let tom = "bom";

    for (const item of corpo.aceitos || []) {
      linhas.push(`Entrou: ${item.nome} — ${item.n_analogicos} analógicos, ` +
                  `${item.n_amostras} amostras`);
    }
    for (const item of corpo.repetidos || []) {
      linhas.push(`Já estava no acervo: ${item.nome}`);
    }
    for (const linha of corpo.aguardando || []) {
      linhas.push(linha);
      if (tom === "bom") tom = "atencao";
    }
    for (const problema of corpo.problemas || []) {
      linhas.push(problema);
      tom = (corpo.aceitos || []).length ? "atencao" : "ruim";
    }
    if (linhas.length === 0) linhas.push("Nada foi enviado.");
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

  function desenharLista(itens) {
    contagem.textContent = itens.length
      ? `${itens.length} registro${itens.length > 1 ? "s" : ""}`
      : "";

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
      // O raio: o relé disparou. Sem trip, nada (a ausência não afirma que
      // ele restringiu).
      if (item.falta_trip) {
        const raio = criar("i", "raio-do-trip", "⚡︎");
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
