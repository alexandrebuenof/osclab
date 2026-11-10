/* O envio de oscilografia para o acervo — UM caminho só, para toda tela.
 *
 * A página de Arquivos (arrastar e soltar) e os menus da tela de oscilografia
 * («+ adicionar oscilografia» e «+ nova aba») mandam os arquivos pela mesma
 * rota (`POST /api/acervo`) e leem a mesma resposta. Quem pareia `.cfg` com
 * `.dat`, guarda o órfão na antessala e reconhece o registro repetido é o
 * servidor (`library/acervo.guardar`); aqui só se manda, se conta o progresso
 * e se traduz a resposta em frases. Duas cópias disto divergiriam na primeira
 * mudança da regra — e a divergência apareceria como «num lugar sobe, no
 * outro não».
 *
 * Exposto em `window.osclabEnvio`.
 */
(() => {
  "use strict";

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  /** Manda os arquivos e devolve a resposta do servidor.
   *
   * `fetch` não diz quanto já subiu; o XMLHttpRequest diz, pelo
   * `upload.onprogress`. `aoProgresso(fracao)` recebe de 0 a 1 do pedido
   * inteiro; `aoLer()` avisa que o último byte subiu e o que sobra de espera
   * é o servidor abrindo e conferindo os arquivos. */
  function enviar(arquivos, { aoProgresso, aoLer } = {}) {
    const dados = new FormData();
    for (const arquivo of arquivos) dados.append("arquivos", arquivo);
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/acervo");
      xhr.upload.onprogress = (ev) => {
        if (aoProgresso && ev.lengthComputable && ev.total) aoProgresso(ev.loaded / ev.total);
      };
      xhr.upload.onload = () => { aoProgresso?.(1); aoLer?.(); };
      xhr.onload = () => {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch (_e) {
          reject(new Error(`o servidor respondeu ${xhr.status} sem um relatório legível`));
        }
      };
      xhr.onerror = () => reject(new Error("o servidor não respondeu"));
      xhr.send(dados);
    });
  }

  /** A resposta do envio em frases, e o tom delas (`bom`, `atencao`, `ruim`). */
  function relato(corpo) {
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
    return { linhas, tom };
  }

  /** Os registros que a resposta deixou PRONTOS para abrir: os que entraram
   *  e os que já estavam lá (registro repetido abre o que existe). */
  function prontos(corpo) {
    const vistos = new Set();
    return [...(corpo.aceitos || []), ...(corpo.repetidos || [])]
      .filter((x) => x && x.sha && !vistos.has(x.sha) && vistos.add(x.sha));
  }

  /* O `<input type="file">` dos menus mora no CORPO da página, e não dentro
     do menu: o menu pode fechar com o explorador de arquivos aberto, e um
     campo que saiu da página não tem garantia de entregar a escolha. As
     extensões aceitas vêm do servidor (`acervo.EXTENSOES`), no `data-aceita`
     do `<body>` — a regra mora num lugar só. */
  let campo = null;
  function escolherArquivos() {
    if (!campo) {
      campo = criar("input");
      campo.type = "file";
      campo.multiple = true;
      campo.hidden = true;
      campo.accept = document.body.dataset.aceita || "";
      document.body.append(campo);
    }
    return new Promise((resolve) => {
      const pronto = (lista) => {
        campo.onchange = campo.oncancel = null;
        resolve(lista);
      };
      campo.onchange = () => { const l = [...campo.files]; campo.value = ""; pronto(l); };
      campo.oncancel = () => pronto([]);
      campo.click();
    });
  }

  /* O recado que fica DEPOIS do menu fechar: o que entrou, o que ficou na
     antessala, o que não era oscilografia. Some sozinho, ou num clique. */
  let recadoAberto = null;
  function recado(linhas, tom) {
    recadoAberto?.remove();
    const caixa = criar("div", `recado-do-envio ${tom}`);
    caixa.setAttribute("role", "status");
    for (const t of linhas) caixa.append(criar("p", null, t));
    caixa.title = "clique para fechar";
    caixa.addEventListener("click", () => caixa.remove());
    document.body.append(caixa);
    recadoAberto = caixa;
    setTimeout(() => caixa.remove(), tom === "bom" ? 6000 : 15000);
  }

  /** O item «enviar do computador…» de um menu de registros.
   *
   * Escolhe os arquivos, sobe com o progresso escrito no próprio item e, com
   * o registro no acervo, chama `aoChegar(itens, corpo)`, que decide o que
   * fazer com ele (pôr nesta aba, abrir numa nova) e pode devolver frases a
   * acrescentar ao recado. Sem registro pronto — só o `.cfg`, arquivo que
   * não é oscilografia —, o recado diz por quê e nada mais acontece. */
  function itemDeEnvio({ explicacao, aoChegar }) {
    const b = criar("button", "opcao-de-registro enviar-do-computador");
    b.type = "button";
    const nome = criar("span", "nome-do-registro");
    nome.append(criar("span", "icone-mascara icone-de-envio"), " enviar do computador…");
    const sub = criar("span", "sub-do-registro", explicacao);
    b.append(nome, sub);
    b.title = "Abre o explorador de arquivos. O que subir fica salvo no acervo, "
            + "como na página Arquivos: .cfg com .dat, .cff, .cev, e o .hdr junto "
            + "para ver a lógica e os ajustes.";
    let ocupado = false;
    b.addEventListener("click", async () => {
      if (ocupado) return;
      const arquivos = await escolherArquivos();
      if (!arquivos.length) return;
      ocupado = true;
      b.classList.add("enviando");
      sub.textContent = "enviando 0 %";
      let corpo;
      try {
        corpo = await enviar(arquivos, {
          aoProgresso: (f) => { sub.textContent = `enviando ${Math.floor(f * 100)} %`; },
          aoLer: () => { sub.textContent = "lendo e conferindo…"; },
        });
      } catch (erro) {
        ocupado = false;
        b.classList.remove("enviando");
        sub.textContent = explicacao;
        recado([`Falha no envio: ${erro.message}`], "ruim");
        return;
      }
      ocupado = false;
      b.classList.remove("enviando");
      sub.textContent = explicacao;
      const { linhas, tom } = relato(corpo);
      const itens = prontos(corpo);
      if ((corpo.aguardando || []).length) {
        linhas.push("O que ficou esperando o par está na antessala da página "
                    + "Arquivos: mande a outra metade e o registro se forma sozinho.");
      }
      const extra = itens.length ? (aoChegar(itens, corpo) || []) : [];
      recado([...linhas, ...extra], tom);
    });
    return b;
  }

  window.osclabEnvio = { enviar, relato, prontos, recado, itemDeEnvio };
})();
