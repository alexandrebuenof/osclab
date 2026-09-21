"""Os pontos de atração magnética: onde o cursor gruda.

## O problema que o ímã resolve

Medir tempo de trip é pôr um cursor no instante em que a proteção partiu e o
outro no instante em que o disjuntor abriu. Os dois instantes existem no
arquivo com precisão de uma amostra — e a mão, no mouse, erra por cinco ou dez
pixels. A 20 amostras por ciclo, dez pixels de erro podem ser meia amostra ou
quatro ciclos, conforme o zoom; e o número que sai daí vai para o laudo.

O ímã tira a mão da conta: o cursor gruda no ponto **notável** mais próximo, e
ponto notável é sempre uma amostra de verdade.

## Os três tipos, e por que exatamente estes

* **Transição de digital** — o instante em que um bit mudou. É o mais exato dos
  três (não há dúvida sobre qual amostra é) e é o que sustenta as medidas mais
  comuns do ofício: trip, abertura do disjuntor, religamento.
* **Pico de um sinal analógico** — a crista e o vale de cada semiciclo, os
  dois na mesma lista: o pico negativo de uma corrente é tão pico quanto o
  positivo. Serve para a corrente de pico da falta, e para responder "a falta
  pegou no pico da tensão?", que decide o quanto de componente contínua vai
  haver.
* **Passagem por zero** — a amostra mais próxima de cada cruzamento. É o outro
  lado da mesma pergunta: o ângulo de incidência da falta sai da distância
  entre o início dela e a passagem por zero da tensão.
* **Início da perturbação** — onde o registro deixou de repetir o ciclo
  anterior. É um só, e é um PALPITE (ver abaixo).

## Nunca se interpola

A passagem por zero verdadeira cai entre duas amostras; o pico verdadeiro de
uma senoide amostrada a 16 pontos por ciclo também. Este módulo devolve sempre
a **amostra** mais próxima do ponto notável, nunca um instante interpolado —
pela mesma razão que o cursor sempre cai numa amostra (ver `plot/leitura.py`):
entre duas amostras não existe medida, existe palpite.

## Por que os pontos são afinados por coluna de pixel

Num registro de 500 mil amostras há dez mil picos. Oferecer todos não ajuda
ninguém: não se consegue mirar num pico que não está desenhado. Então sobra no
máximo um ponto por coluna de pixel — o mesmo critério com que a onda é
reduzida (`plot/serie.py`). Ampliando, os outros voltam a aparecer.
"""

from __future__ import annotations

import numpy as np

from osclab.dsp import fasor
from osclab.formats.base import Record

#: Quantas vezes o ruído de regime permanente um degrau precisa passar para
#: contar como perturbação. Cinco é folgado de propósito: um falso "início da
#: falta" põe o cursor num lugar que não é nada, e quem confere acredita.
VEZES_O_RUIDO = 5.0

#: Por quantas amostras seguidas o degrau tem que se manter. Uma amostra
#: sozinha acima do limiar é ruído impulsivo — um chaveamento na fonte, um
#: pico no conversor A/D —, não é o começo de uma falta.
AMOSTRAS_SEGUIDAS = 3

#: Piso do limiar, como fração do maior valor absoluto do canal. Existe para o
#: canal QUIETO: ali a mediana do ruído é zero, e sem piso qualquer bit do
#: conversor A/D seria "infinitas vezes" o ruído.
PISO_DO_CANAL = 0.02


def afinar(amostras: np.ndarray, i0: int, i1: int, colunas: int) -> list[int]:
    """No máximo um ponto por coluna de pixel, dentro de `[i0, i1)`.

    Mira é feita com o mouse, e o mouse não distingue duas amostras que caem no
    mesmo pixel. Oferecer as duas só faria o ímã escolher uma delas por um
    critério que ninguém vê.
    """
    if amostras.size == 0 or i1 <= i0:
        return []
    dentro = amostras[(amostras >= i0) & (amostras < i1)]
    if dentro.size == 0:
        return []
    largura = max(int(colunas), 1)
    coluna = ((dentro - i0) * largura) // max(i1 - i0, 1)
    # `np.unique` sobre a coluna devolve o índice do PRIMEIRO de cada coluna,
    # que é o que se quer: à esquerda do pixel, onde o traço começa.
    _, primeiros = np.unique(coluna, return_index=True)
    return [int(x) for x in dentro[np.sort(primeiros)]]


def transicoes(registro: Record, indice: int) -> np.ndarray:
    """As amostras em que um canal digital mudou de estado.

    Todas elas, e não só a primeira (que é o que `digitais.resumos` guarda para
    ordenar a tela): um religamento tem trip, abertura, fechamento e às vezes
    um segundo trip, e o ímã tem que grudar em cada um deles.
    """
    dados = registro.status
    if dados.size == 0 or not (0 <= indice < dados.shape[0]):
        return np.empty(0, dtype=np.int64)
    linha = dados[indice].astype(np.int16)
    if linha.size < 2:
        return np.empty(0, dtype=np.int64)
    # `+1` porque `diff[k]` compara `k` com `k+1`: a mudança é em `k+1`.
    return np.flatnonzero(np.diff(linha) != 0) + 1


def picos(valores: np.ndarray) -> np.ndarray:
    """As amostras de máximo e de mínimo local — a crista **e** o vale.

    Os dois juntos porque os dois são "pico": o pico negativo de uma corrente é
    tão pico quanto o positivo, e numa onda com componente contínua eles ficam
    em alturas diferentes — é justamente a diferença entre eles que mede a
    assimetria. Quem procura o pico da falta não sabe de antemão se ele caiu na
    crista ou no vale.

    Um trecho sem curva (o primeiro ciclo de uma envoltória, por exemplo) vem
    com `NaN`, e `NaN` não é pico de nada — as comparações com ele dão `False`
    sozinhas, que é o comportamento certo aqui.
    """
    v = np.asarray(valores, dtype=np.float64)
    if v.size < 3:
        return np.empty(0, dtype=np.int64)

    subida = np.diff(v)
    # O sinal da inclinação, com os trechos planos herdando o sinal anterior:
    # um topo achatado (canal saturado) é um pico só, e não vários.
    inclinacao = np.sign(subida)
    for _ in range(int(np.log2(max(inclinacao.size, 2))) + 1):
        zerados = inclinacao == 0
        if not zerados.any():
            break
        inclinacao[zerados] = np.roll(inclinacao, 1)[zerados]

    troca = np.flatnonzero(np.diff(inclinacao) != 0) + 1
    if troca.size == 0:
        return np.empty(0, dtype=np.int64)
    # Onde havia `NaN` a inclinação é `NaN` e a comparação já deixou de fora.
    return troca[np.isfinite(v[troca])].astype(np.int64)


def passagens_por_zero(valores: np.ndarray) -> np.ndarray:
    """As amostras mais próximas de cada passagem por zero.

    ## Por que "mais próxima" e não a passagem em si

    A passagem verdadeira quase nunca cai numa amostra: a 16 amostras por ciclo
    ela cai, em média, a um terço de amostra da vizinha. Interpolar daria um
    instante mais exato no papel e um cursor que aponta para onde não há
    medida — e este programa não põe cursor entre amostras (ver
    `plot/leitura.py`). Então das duas amostras que cercam a passagem devolve-se
    **a que está mais perto do zero**, que é a que menos mente.

    ## Para que serve

    É o que dá o **ângulo de incidência** da falta: comparar o instante em que
    a falta começou com a passagem por zero da tensão diz em que ponto do ciclo
    ela pegou — e isso decide quanta componente contínua vai haver, que por sua
    vez decide se o TC satura.

    Uma curva que não muda de sinal — uma envoltória de RMS, por exemplo — não
    tem passagem nenhuma, e a lista sai vazia. É o certo: RMS não passa por
    zero, e oferecer um ponto ali seria inventar um.
    """
    v = np.asarray(valores, dtype=np.float64)
    if v.size < 2:
        return np.empty(0, dtype=np.int64)

    # `NaN` não tem sinal; trata-se como zero para que nenhuma "passagem"
    # nasça na borda de um trecho sem curva.
    limpo = np.where(np.isfinite(v), v, 0.0)
    sinal = np.sign(limpo)

    # Amostra que é exatamente zero JÁ É a passagem: não há par para escolher.
    exatos = np.flatnonzero((limpo == 0.0) & np.isfinite(v))

    # Entre vizinhos de sinais opostos há uma passagem; fica a mais perto do
    # zero dos dois.
    troca = np.flatnonzero(sinal[:-1] * sinal[1:] < 0)
    if troca.size:
        esquerda = np.abs(limpo[troca]) <= np.abs(limpo[troca + 1])
        escolhidas = np.where(esquerda, troca, troca + 1)
    else:
        escolhidas = np.empty(0, dtype=np.int64)

    juntas = np.unique(np.concatenate([exatos, escolhidas]).astype(np.int64))
    return juntas[np.isfinite(v[juntas])] if juntas.size else juntas


def inicio_da_perturbacao(registro: Record) -> int | None:
    """A amostra em que o registro deixou de repetir o ciclo anterior.

    ## A conta

    É a **grandeza incremental** que os relés usam há décadas: compara-se cada
    amostra com a mesma amostra do ciclo anterior,

        d[n] = x[n] − x[n−N]          N = amostras por ciclo

    Em regime permanente `d` é quase zero, porque um ciclo é igual ao seguinte.
    Quando a rede muda de estado, `d` salta. A conta não depende de amplitude,
    de fase nem de qual grandeza é o canal: depende só de o sinal ter deixado
    de se repetir.

    ## Por que não a derivada simples

    A derivada `x[n] − x[n−1]` também acusa mudança rápida, mas ela é GRANDE em
    toda passagem por zero de uma senoide saudável — é exatamente ali que a
    inclinação é máxima. O limiar teria que ficar acima da inclinação normal da
    onda, e aí só uma falta violenta passaria. Olhando um ciclo para trás em vez
    de uma amostra, a onda de regime se cancela sozinha e o limiar pousa em cima
    do RUÍDO, não do sinal. É a mesma ideia com uma referência muito melhor.

    ## O limiar sai do ruído do registro INTEIRO

    Nenhum limiar fixo serve: um canal pode estar em 5 A ou em 5 000 A. E ele
    não pode sair de uma janela escolhida à mão, porque **não se sabe de
    antemão onde é o regime permanente** — foi assim que a primeira versão
    errou. Ele sai da MEDIANA de `|d|` sobre o registro todo, que é um
    estimador de ruído honesto aqui por um motivo de domínio: `d` é perto de
    zero na pré-falta, **e também durante a falta sustentada** (um ciclo de
    falta é igual ao seguinte, depois que a DC decai) e no pós-falta. `d` só é
    grande nas TRANSIÇÕES, que são breves. A mediana ignora as transições e
    mede o resto.

    ## A falta acontece ANTES do disparo, sempre

    O relé dispara **por causa** da falta: o início dela está no trecho de
    pré-falta que o relé gravou, não depois do disparo. A primeira versão deste
    detector descartava qualquer candidato anterior ao disparo achando que era
    ruído, e calibrava o ruído numa janela que ia até o disparo — ou seja,
    jogava fora justamente a resposta certa e ainda calibrava em cima da falta.
    Num registro sintético com a falta injetada depois do disparo ele acertava;
    em registro de relé de verdade não achava nada. **O disparo não entra nesta
    conta.**

    ## Isto é um palpite, e a tela precisa dizer isso

    Um ponto de atração é uma conveniência: ele põe o cursor num lugar
    plausível, e quem lê decide se é aquilo mesmo. Não é um diagnóstico, e não
    entra em laudo nenhum sozinho — o detector de perturbação de verdade é o
    marco 0.5.
    """
    dados = registro.analog
    if dados.size == 0 or registro.n_samples < 4:
        return None

    trechos = registro.trechos
    por_ciclo = max((fasor.amostras_por_ciclo(t.taxa_hz, registro.line_frequency)
                     for t in trechos), default=0)
    # Precisa de pelo menos dois ciclos: um para a janela do `d` e um para
    # sobrar registro em que procurar.
    if por_ciclo < 2 or por_ciclo * 2 >= registro.n_samples:
        return None

    d = np.abs(dados[:, por_ciclo:] - dados[:, :-por_ciclo])
    if d.shape[1] < AMOSTRAS_SEGUIDAS:
        return None

    ruido = np.median(d, axis=1)
    # O piso evita disparar na poeira do conversor A/D de um canal quieto, onde
    # a mediana do ruído é zero e qualquer coisa seria "cinco vezes" ela.
    piso = np.maximum(ruido * VEZES_O_RUIDO,
                      np.max(np.abs(dados), axis=1) * PISO_DO_CANAL)

    primeiro = None
    for canal in range(d.shape[0]):
        onde = _primeira_sequencia(d[canal] > piso[canal], AMOSTRAS_SEGUIDAS)
        if onde is None:
            continue
        # `d[k]` compara a amostra `k + por_ciclo` com a `k`: o degrau aparece
        # na mais nova das duas, que é onde a perturbação de fato começou.
        amostra = onde + por_ciclo
        if primeiro is None or amostra < primeiro:
            primeiro = amostra
    return primeiro


def _amostras_de_pre_falta(registro: Record) -> int:
    """Quantas amostras vêm antes do disparo do relé."""
    if registro.trigger_time is not None and registro.start_time is not None:
        alvo = (registro.trigger_time - registro.start_time).total_seconds()
        return int(np.searchsorted(registro.time, alvo))
    return registro.n_samples // 3


def _primeira_sequencia(marcado: np.ndarray, quantas: int) -> int | None:
    """O começo da primeira corrida de `quantas` `True` seguidos."""
    if marcado.size < quantas:
        return None
    if quantas <= 1:
        achados = np.flatnonzero(marcado)
        return int(achados[0]) if achados.size else None
    # Soma móvel por soma acumulada: uma passada, sem laço em Python.
    acumulado = np.concatenate(([0], np.cumsum(marcado.astype(np.int32))))
    janelas = acumulado[quantas:] - acumulado[:-quantas]
    achados = np.flatnonzero(janelas == quantas)
    return int(achados[0]) if achados.size else None
