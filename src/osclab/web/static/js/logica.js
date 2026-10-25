/* O painel de LÓGICA E AJUSTES, na tela da onda.
 *
 * Painel SECO: o que está na tela é o que está dentro do arquivo. Não passa
 * pelo dicionário, não traduz nome, não converte valor — decisão dele,
 * 19/10/2026. Os ajustes vêm PRIMEIRO, a lógica depois, porque é nessa ordem
 * que se lê um relé: antes de entender a equação se quer saber com que número
 * ela foi comparada.
 *
 * Flutuante e não modal de propósito: o pedido era «ver a lógica ao mesmo
 * tempo que os sinais». Janela modal apaga a tela atrás, e a tela atrás é
 * metade do assunto. Por isso arrasta pela barra, estica pelo canto, e lembra
 * onde ficou.
 *
 * Arquivo à parte do `onda.js` pelo mesmo motivo do dicionário: isto não
 * desenha nem mede nada.
 */
(() => {
  "use strict";

  const chave = document.getElementById("logica");
  const painel = document.getElementById("painel-da-logica");
  const barra = document.getElementById("barra-da-logica");
  const deOnde = document.getElementById("de-onde-a-logica");
  const campo = document.getElementById("busca-da-logica");
  const corpo = document.getElementById("corpo-da-logica");
  if (!chave || !painel) return;

  const sha = document.body.dataset.sha || "";
  const LEMBRANCA = "osclab:painel-da-logica";
  const MINIMO = { largura: 280, altura: 180 };

  let estado = null;      /* o que o servidor respondeu, ou null até responder */

  const criar = (tag, classe, texto) => {
    const el = document.createElement(tag);
    if (classe) el.className = classe;
    if (texto !== undefined) el.textContent = texto;
    return el;
  };

  /* ------------------------------------------------------------------ chave */

  /* Cinza e CLICÁVEL quando não há nada para mostrar — mesma regra do
     dicionário. O clique diz por que está vazio, e «por que está vazio» é
     informação técnica aqui: COMTRADE não prevê ajuste nenhum. */
  function pintarChave() {
    const tem = !!(estado && estado.tem);
    chave.classList.toggle("sem-logica", !tem);
    chave.title = tem
      ? "Os ajustes e a lógica que vieram dentro do arquivo (" + estado.de + ")."
      : "Este registro não trouxe ajustes — clique para saber por quê.";
  }

  async function carregar() {
    try {
      const r = await fetch("/api/logica/" + encodeURIComponent(sha));
      estado = await r.json();
    } catch (erro) {
      estado = { tem: false, motivo: "não deu para falar com o programa",
                 ajustes: [], logica: [] };
    }
    pintarChave();
  }

  /* ----------------------------------------------------------------- pintar */

  const OPERADORES = /^(AND|OR|NOT|NAND|NOR|XOR|R_TRIG|F_TRIG)$/i;

  /* Parte o valor em pedaços para dar cor aos operadores e grifar o que foi
     procurado. O TEXTO não muda: é o mesmo que veio no arquivo, letra por
     letra — só ganha cor. */
  function escrever(destino, texto, alvo) {
    const pedacos = [];
    if (alvo) {
      const baixo = texto.toLowerCase();
      let i = 0;
      for (;;) {
        const onde = baixo.indexOf(alvo, i);
        if (onde < 0) { pedacos.push([texto.slice(i), false]); break; }
        if (onde > i) pedacos.push([texto.slice(i, onde), false]);
        pedacos.push([texto.slice(onde, onde + alvo.length), true]);
        i = onde + alvo.length;
      }
    } else {
      pedacos.push([texto, false]);
    }

    pedacos.forEach(([trecho, grifado]) => {
      if (!trecho) return;
      if (grifado) { destino.append(criar("mark", null, trecho)); return; }
      /* Fora do grifo, os operadores ganham cor para a equação longa poder
         ser lida de relance: `IN104 OR IN102 AND NOT 52A`. */
      trecho.split(/([A-Za-z_]+)/).forEach((t) => {
        if (!t) return;
        destino.append(OPERADORES.test(t) ? criar("span", "op", t)
                                          : document.createTextNode(t));
      });
    });
  }

  function grupo(titulo, pares, alvo, total) {
    const bloco = criar("section", "grupo-da-logica");
    const cabeca = criar("h4", "titulo-do-grupo", titulo);
    cabeca.append(criar("span", "conta",
      alvo ? pares.length + " de " + total : String(total)));
    bloco.append(cabeca);

    if (!pares.length) {
      bloco.append(criar("p", "nada-no-grupo",
        alvo ? "nada aqui com «" + campo.value.trim() + "»"
             : "o arquivo não trouxe nenhum"));
      return bloco;
    }

    pares.forEach(([nome, valor], i) => {
      const linha = criar("div", "linha-da-logica" + (i % 2 ? " par" : ""));
      const esq = criar("div", "nome");
      escrever(esq, nome, alvo);
      const dir = criar("div", "valor");
      escrever(dir, valor, alvo);
      linha.append(esq, dir);
      bloco.append(linha);
    });
    return bloco;
  }

  function pintar() {
    corpo.replaceChildren();
    /* Campo de busca sem nada para buscar é um convite a digitar e não achar
       nada. Some quando o arquivo não trouxe ajuste. */
    campo.hidden = !(estado && estado.tem);
    if (!estado || !estado.tem) {
      const vazio = criar("div", "logica-vazia");
      vazio.append(criar("p", null,
        (estado && estado.motivo ? "Nada para mostrar: " + estado.motivo + "."
                                 : "Nada para mostrar.") +
        " O leitor continua funcionando igual — ajuste e lógica são um extra " +
        "que o arquivo traz, ou não."));
      vazio.append(criar("p", "miudo",
        "Quem garante os dois é o .CEV da SEL, no bloco SETTINGS do fim. " +
        "O COMTRADE puro não prevê ajuste nenhum; às vezes o .HDR traz."));
      corpo.append(vazio);
      return;
    }

    const alvo = campo.value.trim().toLowerCase();
    const filtrar = (lista) => lista.filter(([n, v]) => !alvo ||
      (n + " " + v).toLowerCase().includes(alvo));

    /* AJUSTES primeiro. A ordem é dele, 19/10/2026. */
    corpo.append(grupo("Ajustes", filtrar(estado.ajustes), alvo,
                       estado.ajustes.length));
    corpo.append(grupo("Lógica", filtrar(estado.logica), alvo,
                       estado.logica.length));

    const pe = criar("p", "pe-da-logica");
    pe.append(criar("span", null, "do arquivo " + estado.de));
    corpo.append(pe);
  }

  /* --------------------------------------------------------- abrir e fechar */

  function lembrar() {
    try {
      localStorage.setItem(LEMBRANCA, JSON.stringify({
        x: painel.offsetLeft, y: painel.offsetTop,
        l: painel.offsetWidth, a: painel.offsetHeight,
      }));
    } catch (erro) { /* segue sem lembrar */ }
  }

  function dentroDaTela(x, y, l, a) {
    /* Um painel que o usuário arrastou até sair da tela e some para sempre é
       um painel perdido. Deixa sempre a barra alcançável. */
    const folga = 40;
    return {
      x: Math.max(-(l - folga * 2), Math.min(x, window.innerWidth - folga)),
      y: Math.max(0, Math.min(y, window.innerHeight - folga)),
    };
  }

  function posicionar() {
    let guardado = null;
    try { guardado = JSON.parse(localStorage.getItem(LEMBRANCA) || "null"); }
    catch (erro) { guardado = null; }

    const largura = Math.max(MINIMO.largura,
      Math.min(guardado && guardado.l || 440, window.innerWidth - 24));
    const altura = Math.max(MINIMO.altura,
      Math.min(guardado && guardado.a || 480, window.innerHeight - 110));
    painel.style.width = largura + "px";
    painel.style.height = altura + "px";

    /* Nasce no canto direito, ABAIXO da fileira de chaves: começar colado no
       topo tapava «menu», «ajuda» e «tema» — as três que ficam logo ao lado
       da chave que acabou de ser clicada. */
    const bruto = guardado
      ? { x: guardado.x, y: guardado.y }
      : { x: window.innerWidth - largura - 18, y: 150 };
    const posto = dentroDaTela(bruto.x, bruto.y, largura, altura);
    painel.style.left = posto.x + "px";
    painel.style.top = posto.y + "px";
  }

  function abrir() {
    deOnde.textContent = estado && estado.tem ? estado.de : "";
    posicionar();
    painel.hidden = false;
    pintar();
    if (!campo.hidden) { campo.focus(); campo.select(); }
    chave.classList.add("escolhido");
  }

  function fechar() {
    painel.hidden = true;
    chave.classList.remove("escolhido");
  }

  chave.addEventListener("click", () => (painel.hidden ? abrir() : fechar()));
  document.getElementById("fechar-logica").addEventListener("click", fechar);
  campo.addEventListener("input", pintar);

  /* Esc fecha, mas só quando o foco está DENTRO do painel: a tecla é dos
     outros também, e roubar Esc da tela toda quebraria a janela de busca. */
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape" || painel.hidden) return;
    if (!painel.contains(ev.target)) return;
    ev.stopPropagation();
    fechar();
  });

  /* ------------------------------------------------------------- arrastar */

  let pegada = null;

  /* Os ouvintes do arrasto ficam na JANELA, e não na barra, e isso é
     medido: com `setPointerCapture` na barra o Chrome devolvia a captura
     (`lostpointercapture`) depois de dois movimentos, e o painel andava 25
     dos 300 pixels pedidos. Na janela não há captura para perder — e o
     ponteiro pode sair da barra, que é exatamente o que acontece ao
     arrastar depressa. */
  const arrastar = (ev) => {
    if (!pegada) return;
    ev.preventDefault();
    const posto = dentroDaTela(ev.clientX - pegada.x, ev.clientY - pegada.y,
                               painel.offsetWidth, painel.offsetHeight);
    painel.style.left = posto.x + "px";
    painel.style.top = posto.y + "px";
  };

  const soltar = () => {
    if (!pegada) return;
    pegada = null;
    barra.classList.remove("arrastando");
    window.removeEventListener("pointermove", arrastar);
    window.removeEventListener("pointerup", soltar);
    window.removeEventListener("pointercancel", soltar);
    lembrar();
  };

  barra.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest("button")) return;
    /* Sem isto o Chrome começa um ARRASTO NATIVO no texto da barra: dispara
       `dragstart`, cancela o ponteiro (`pointercancel`) e o painel para no
       primeiro movimento — andava 25 dos 300 pixels pedidos. Medido em
       19/10/2026. */
    ev.preventDefault();
    pegada = { x: ev.clientX - painel.offsetLeft,
               y: ev.clientY - painel.offsetTop };
    barra.classList.add("arrastando");
    window.addEventListener("pointermove", arrastar);
    window.addEventListener("pointerup", soltar);
    window.addEventListener("pointercancel", soltar);
  });

  /* O canto de esticar é o `resize: both` do CSS — o navegador desenha e mede
     melhor do que qualquer alça nossa. Só precisamos ouvir para lembrar. */
  if (window.ResizeObserver) {
    let primeira = true;
    new ResizeObserver(() => {
      if (primeira) { primeira = false; return; }
      if (!painel.hidden) lembrar();
    }).observe(painel);
  }

  window.addEventListener("resize", () => {
    if (painel.hidden) return;
    const posto = dentroDaTela(painel.offsetLeft, painel.offsetTop,
                               painel.offsetWidth, painel.offsetHeight);
    painel.style.left = posto.x + "px";
    painel.style.top = posto.y + "px";
  });

  chave.classList.add("sem-logica");
  carregar();
})();
