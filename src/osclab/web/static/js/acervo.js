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
        criar("p", "vazio", "Nada ainda. Arraste um .cfg e o .dat dele acima.")
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
      const falta = item.tem.includes(".cfg") || item.tem.includes(".cff")
        ? ".dat" : ".cfg";
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
    link.href = `/onda/${item.sha}`;
    titulo.append(link);
    cabecalho.append(titulo);
    const remover = criar("button", "remover", "remover");
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
    for (const aviso of item.avisos || []) {
      el.append(criar("p", "aviso", `aviso: ${aviso}`));
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
