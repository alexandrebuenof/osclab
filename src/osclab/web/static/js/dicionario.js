/* A consulta ao DICIONÁRIO, na tela da onda.
 *
 * Arquivo à parte do `onda.js` de propósito: isto não desenha nem mede nada,
 * só procura um nome e mostra o que está cadastrado. Misturar com as 12 mil
 * linhas que cuidam do desenho não acrescentaria nada e tiraria a chance de
 * ler esta tela inteira numa sentada.
 *
 * A descrição NÃO é escrita em mais lugar nenhum — decisão dele, 19/10/2026.
 * A tira continua com o nome cru; quem quer saber o que um sinal é, pergunta
 * aqui.
 */
(() => {
  "use strict";

  const chave = document.getElementById("dicionario");
  const janela = document.getElementById("janela-do-dicionario");
  const campo = document.getElementById("busca-do-dicionario");
  const achados = document.getElementById("achados-do-dicionario");
  const deQueRele = document.getElementById("de-que-rele");
  if (!chave || !janela) return;

  const sha = document.body.dataset.sha || "";
  let estado = null;      /* o que o servidor respondeu, ou null até responder */

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  /* A chave nasce CINZA e só acende quando há dicionário com verbete. Cinza e
     clicável: o clique diz o que falta. Botão apagado que não responde a nada
     é a tela discutindo com quem clicou. */
  function pintarChave() {
    const tem = !!(estado && estado.tem);
    chave.classList.toggle("sem-dicionario", !tem);
    chave.title = tem
      ? "Procurar o significado de um sinal digital deste relé."
      : "Nenhum dicionário para consultar — clique para saber por quê.";
  }

  async function carregar() {
    try {
      const r = await fetch("/api/dicionario/" + encodeURIComponent(sha));
      estado = await r.json();
    } catch (erro) {
      estado = { tem: false, motivo: "não deu para falar com o programa", verbetes: [] };
    }
    pintarChave();
  }

  function pintarAchados() {
    achados.replaceChildren();
    if (!estado || !estado.tem) {
      const vazio = criar("div", "dicionario-vazio");
      vazio.append(criar("p", null,
        (estado && estado.motivo ? "Não há o que consultar: " + estado.motivo + "."
                                 : "Não há o que consultar.") +
        " O leitor continua funcionando igual — os digitais aparecem com o nome " +
        "cru que veio no arquivo."));
      const ir = criar("a", "chave escolhido", "abrir a base de dados");
      ir.href = "/base";
      vazio.append(ir);
      achados.append(vazio);
      return;
    }

    const alvo = campo.value.trim().toLowerCase();
    const vistos = estado.verbetes.filter((v) => !alvo ||
      (v.sinal + " " + (v.descricao || "")).toLowerCase().includes(alvo));

    if (!vistos.length) {
      const nada = criar("div", "dicionario-vazio");
      nada.append(criar("p", null, alvo
        ? "«" + campo.value.trim() + "» não está no dicionário deste relé."
        : "O dicionário está vazio."));
      /* Procurou e não achou é o melhor momento de cadastrar: a dúvida é
         agora, e o nome já está digitado. */
      const ir = criar("a", "chave escolhido", "cadastrar na base");
      ir.href = "/base";
      nada.append(ir);
      achados.append(nada);
      return;
    }

    const lista = criar("div", "achados-lista");
    vistos.forEach((v, i) => {
      const l = criar("div", "achado-do-dicionario" + (i % 2 ? " par" : ""));
      const esq = criar("div");
      esq.append(criar("div", "sinal", v.sinal));
      esq.append(criar("div", "origem", v.origem || ""));
      l.append(esq);
      l.append(criar("div", "descricao" + (v.descricao ? "" : " vazia"),
                     v.descricao || "sem descrição"));
      l.append(criar("span", "tipinho " + (v.categoria || "sem-categoria"),
                     v.categoria || "sem categoria"));
      lista.append(l);
    });
    achados.append(lista);
    achados.append(criar("p", "conta-do-dicionario",
      vistos.length + " de " + estado.verbetes.length +
      (estado.fabricante ? " · " + estado.fabricante +
       (estado.modelo ? " " + estado.modelo : "") : " · relé não identificado")));
  }

  function abrir() {
    deQueRele.textContent = estado && estado.equipamento ? estado.equipamento : "";
    pintarAchados();
    if (!janela.open) janela.showModal();
    campo.focus();
    campo.select();
  }

  chave.addEventListener("click", abrir);
  campo.addEventListener("input", pintarAchados);
  document.getElementById("fechar-dicionario")
    .addEventListener("click", () => janela.close());

  chave.classList.add("sem-dicionario");
  carregar();
})();
