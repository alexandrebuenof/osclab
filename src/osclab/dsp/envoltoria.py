"""A curva de fundamental e a de RMS ao longo do registro inteiro.

## O que estas curvas mostram

A onda instantânea responde "como era o sinal naquele microssegundo". Estas
respondem outra coisa: **de quanto foi a corrente**, ciclo a ciclo. São as duas
curvas que um relatório de falta usa, e são o que o relé enxerga.

Cada ponto é o fasor da janela de um ciclo que **termina ali** — a mesma
definição de `dsp/fasor.py`, ponto a ponto. Daí duas consequências que não são
defeito e precisam estar na tela:

* o primeiro ciclo do registro **não tem curva** (não há janela antes dele);
* depois do início da falta a curva leva **um ciclo inteiro** para subir.

Quem olhar só estas curvas vai errar o instante de início da falta em até um
ciclo. Elas dizem o valor, não a hora.

## Por que não se faz uma DFT por amostra

Um registro de 500 mil amostras a 96 por ciclo custaria 48 milhões de
multiplicações por canal — a cada gesto de zoom, para cada canal. O programa
travaria.

O que salva é que a janela deslizante é uma **soma móvel**, e soma móvel não
precisa ser refeita: calcula-se a soma acumulada uma vez e cada janela vira uma
subtração de dois números. A conta inteira cai para **uma passada pelo canal**,
o mesmo custo de desenhá-lo.

O truque que torna isso possível na DFT é separar o índice do cursor do índice
da amostra. Partindo da definição de `fasor.de_janela`, com `i` no cursor:

    X[i] = (2/n) · Σ_k  x[i-k] · e^{+j2πk/n}        , k = 0 .. n-1

Trocando a variável para `m = i-k`, o expoente se parte em dois fatores:

    X[i] = (2/n) · e^{+j2πi/n} · Σ_m  x[m] · e^{-j2πm/n}

O somatório agora **não depende de `i`** — é uma soma móvel de um sinal fixo.
O fator da frente é só um giro, aplicado no fim. Era isso que estava escondido.

## Precisão

Os expoentes usam `m % n` em vez de `m`. É o mesmo número (a exponencial tem
período `n`), mas mantém o argumento pequeno: sem isso, a 500 mil amostras o
argumento chega a 3 milhões de radianos e o seno perde dígitos justamente onde
o ângulo importa.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.dsp.fasor import (
    MINIMO_POR_CICLO,
    amostras_por_ciclo,
    ciclo_em_amostras,
    pesos_do_ciclo,
)


def _soma_movel(v: np.ndarray, n: int) -> np.ndarray:
    """Soma dos `n` valores que TERMINAM em cada posição do último eixo.

    Onde não há `n` valores antes, devolve `NaN` — e não zero. Zero seria um
    número, e número na tela é afirmação: diria "medi, e deu isso" no trecho em
    que não há o que medir.
    """
    acumulado = np.cumsum(v, axis=-1)
    zero = np.zeros(acumulado.shape[:-1] + (1,), dtype=acumulado.dtype)
    acumulado = np.concatenate((zero, acumulado), axis=-1)

    saida = np.full(v.shape, np.nan, dtype=acumulado.dtype)
    saida[..., n - 1:] = acumulado[..., n:] - acumulado[..., :v.shape[-1] - n + 1]
    return saida


def _valida(sinal: np.ndarray, por_ciclo: float) -> np.ndarray | None:
    """`None` quando não dá para calcular envoltória nenhuma."""
    if por_ciclo < MINIMO_POR_CICLO:
        return None
    if sinal.shape[-1] < pesos_do_ciclo(por_ciclo).size:
        return None
    return np.asarray(sinal, dtype=np.float64)


def media_do_ciclo(v: np.ndarray, por_ciclo: float) -> np.ndarray:
    """A média de `v` sobre a janela de UM CICLO que termina em cada amostra.

    É a primitiva de que TODAS as envoltórias saem: a contínua é ela sobre o
    sinal, o eficaz é a raiz dela sobre o quadrado, e o fasor é ela sobre o
    sinal girado. Uma implementação só — é assim que as três não divergem.

    Os pesos vêm de `fasor.pesos_do_ciclo`, que trata o caso da taxa que não
    fecha um número inteiro de amostras por ciclo. Ver lá o porquê.

    A conta é `O(n)` mesmo com a janela grande: os pesos são todos 1 no meio,
    então o miolo sai de uma soma acumulada e só as três pontas são tratadas
    uma a uma. Com 167 amostras por ciclo no SEL-TWFL, a diferença entre isso
    e uma convolução é de segundos.
    """
    pesos = pesos_do_ciclo(por_ciclo)
    largura = pesos.size
    n = v.shape[-1]
    saida = np.full(v.shape, np.nan, dtype=v.dtype if np.iscomplexobj(v)
                    else np.float64)
    if n < largura:
        return saida

    acumulado = np.concatenate(
        (np.zeros(v.shape[:-1] + (1,), dtype=v.dtype), np.cumsum(v, axis=-1)),
        axis=-1)
    # `i` percorre as posições em que a janela cabe inteira.
    i = np.arange(largura - 1, n)
    inicio = i - largura + 1                      # a amostra mais antiga dela

    if largura == int(round(por_ciclo)):
        # Taxa que fecha: soma retangular das `largura` amostras, como sempre.
        total = acumulado[..., i + 1] - acumulado[..., inicio]
    else:
        # O miolo (pesos 1) por soma acumulada, e as três pontas na mão.
        total = (acumulado[..., i] - acumulado[..., inicio + 2]
                 + pesos[0] * v[..., inicio]
                 + pesos[1] * v[..., inicio + 1]
                 + pesos[-1] * v[..., i])
    saida[..., largura - 1:] = total / float(por_ciclo)
    return saida


def fundamental(sinal: np.ndarray, por_ciclo: int) -> np.ndarray:
    """Valor EFICAZ da componente fundamental em cada amostra.

    Aceita um canal `(N,)` ou vários `(C, N)` — a conta é a mesma e roda
    vetorizada, que é o que permite desenhar oito canais sem laço em Python.

    É o número com que o relé decide atuar: o filtro dele joga fora DC e
    harmônicos de propósito. Confira contra `fasor.no_instante` — os dois têm
    que dar o mesmo valor em toda amostra, e há teste para isso.
    """
    return _fasor_deslizante(sinal, por_ciclo,
                             lambda x: np.abs(x) / math.sqrt(2.0))


def fasores(sinal: np.ndarray, por_ciclo: int) -> np.ndarray:
    """O fasor complexo `X[i]` em cada amostra, sem extrair nada dele.

    É o número de que `fundamental` toma o módulo e `filtrada` a parte real.
    Ele sai inteiro porque há conta que precisa do ÂNGULO ponto a ponto:
    componente simétrica é `Ia + a·Ib + a²·Ic`, e girar 120° é multiplicar por
    um complexo — não há como fazer isso com módulos.

    A amplitude é de PICO, como em `dsp/fasor`. Quem quiser eficaz divide por
    √2, e quem for somar fasores soma antes de dividir.
    """
    x = _valida(sinal, por_ciclo)
    if x is None:
        return np.full(np.shape(sinal), np.nan + 0j, dtype=np.complex128)

    n = float(por_ciclo)
    # O giro usa o índice ABSOLUTO, não `k % n`: com `n` fracionário a
    # exponencial não tem período inteiro, e o resto quebraria a soma móvel.
    # A 125 mil amostras o argumento chega a 4.700 radianos, que o float64
    # ainda carrega com 1e-12 rad de erro — bem abaixo do que se lê na tela.
    k = np.arange(x.shape[-1], dtype=np.float64)
    giro = np.exp(-2j * np.pi * k / n)

    return 2.0 * np.conj(giro) * media_do_ciclo(x.astype(np.complex128) * giro,
                                                n)


def _fasor_deslizante(sinal: np.ndarray, por_ciclo: int, extrair) -> np.ndarray:
    """O fasor `X[i]` em cada amostra, passado por `extrair`.

    `abs` dá a amplitude (e daí a fundamental eficaz); `real` dá a própria onda
    de 60 Hz. É o mesmo número complexo — só muda o que se lê dele.
    """
    x = _valida(sinal, por_ciclo)
    if x is None:
        return np.full(np.shape(sinal), np.nan, dtype=np.float64)
    return np.asarray(extrair(fasores(x, por_ciclo)), dtype=np.float64)


def filtrada(sinal: np.ndarray, por_ciclo: int) -> np.ndarray:
    """A onda de 60 Hz desenhada no tempo — a saída do filtro do relé.

    É a **parte real** do mesmo fasor de que `fundamental` toma o módulo: o
    valor instantâneo da senoide de 60 Hz vale `|X|·cos(φ)`, e isso é `Re(X)`
    por definição. Custa uma linha a mais, não uma conta a mais.

    Não é aproximação nem enfeite: `Re(X)` é exatamente a saída do filtro de
    Fourier de ciclo completo, que é o filtro que o relé roda por dentro. Quem
    olha esta curva está vendo o sinal com que o relé decidiu.

    **Ela atrasa até um ciclo nas transições.** No início da falta a senoide
    sobe depois da onda real, com a transição borrada. É assim no relé — e é
    por isso que esta vista não serve para achar o INSTANTE da falta.
    """
    return _fasor_deslizante(sinal, por_ciclo, np.real)


def rms(sinal: np.ndarray, por_ciclo: int) -> np.ndarray:
    """Valor eficaz VERDADEIRO da janela de um ciclo, em cada amostra.

    Inclui harmônicos e componente DC. É o que aquece o equipamento e o que um
    multímetro leria — e sobe acima da fundamental em toda falta assimétrica.
    """
    x = _valida(sinal, por_ciclo)
    if x is None:
        return np.full(np.shape(sinal), np.nan, dtype=np.float64)

    return np.sqrt(media_do_ciclo(np.square(x), float(por_ciclo)))


def continua(sinal: np.ndarray, por_ciclo: int) -> np.ndarray:
    """Componente contínua: a MÉDIA da janela de um ciclo, em cada amostra.

    Numa senoide pura a média de um ciclo é zero. O que sobra é a assimetria da
    falta — `i_dc(t) = I₀·e^(−t/τ)`, que existe porque a corrente não pode
    saltar num circuito indutivo e o curto pegou a onda fora do zero.

    **Esta é a única envoltória que traça uma grandeza física, e não um índice.**
    A DC é função do tempo de verdade; daqui se lê o τ, e τ é o que dimensiona
    saturação de TC e assimetria de disjuntor. Medido num curto do alimentador:
    τ = 6,5 ms, X/R = 2,5.

    **Sai com SINAL**, na unidade do canal. O SIGRA mostra a DC em percentual da
    fundamental e em módulo; esse número continua na tabelinha do cursor
    (`Fasor.dc_percentual`), que é onde ele funciona. Como CURVA a percentagem
    seria razão de duas envoltórias: explode quando o disjuntor abre e a
    fundamental vai a zero — nos arquivos do parque chega a 1491 %.

    **Ela atrasa meio ciclo e subestima o pico**, porque média de janela é média
    do passado: no maior valor de um curto real o estimador marcou 2890 A onde a
    exponencial ajustada dá 3585 A. **Isso não estraga o τ**: exponencial
    atrasada é a mesma exponencial escalada, `e^(−(t−δ)/τ) = e^(δ/τ)·e^(−t/τ)`,
    mesma inclinação.
    """
    x = _valida(sinal, por_ciclo)
    if x is None:
        return np.full(np.shape(sinal), np.nan, dtype=np.float64)

    return media_do_ciclo(x, float(por_ciclo))


#: As curvas que a tela sabe desenhar. `instantaneo` não está aqui porque não é
#: envoltória: é a própria amostra, e sai direto do registro.
#:
#: As quatro vistas da tela são a combinação de dois botões — filtro ligado ou
#: não, valor instantâneo ou eficaz:
#:
#:                   |  instantâneo   |  RMS
#:   filtro desligado|  instantaneo   |  rms
#:   filtro ligado   |  filtrado      |  fundamental
CURVAS = {"fundamental": fundamental, "rms": rms, "filtrado": filtrada,
          "dc": continua}


def calcular(sinal: np.ndarray, trechos, frequencia_hz: float,
             grandeza: str) -> np.ndarray:
    """A curva pedida, calculada TRECHO A TRECHO.

    Um registro pode mudar de taxa no meio — 96 amostras por ciclo na falta, 16
    no resto. Cada trecho tem então a sua própria janela de um ciclo, e cada um
    é calculado com a dele.

    **Nenhuma janela atravessa a fronteira entre dois trechos.** Uma janela com
    metade das amostras de um lado e metade do outro não é um ciclo de coisa
    nenhuma: o número sairia confiante e errado, que é a pior espécie. O preço
    é o primeiro ciclo de cada trecho ficar sem curva, exatamente como o
    primeiro ciclo do registro — e pela mesma razão.
    """
    funcao = CURVAS.get(grandeza)
    if funcao is None:
        return np.asarray(sinal, dtype=np.float64)
    return _por_trecho(sinal, trechos, frequencia_hz, funcao, np.float64)


def calcular_fasores(sinal: np.ndarray, trechos,
                     frequencia_hz: float) -> np.ndarray:
    """Como `calcular`, mas devolvendo o fasor complexo de cada amostra.

    Mesma regra dos trechos, e pela mesma razão: uma janela com metade das
    amostras de cada lado da fronteira não é um ciclo de coisa nenhuma.
    """
    return _por_trecho(sinal, trechos, frequencia_hz, fasores, np.complex128)


def _por_trecho(sinal, trechos, frequencia_hz, funcao, tipo):
    x = np.asarray(sinal, dtype=np.float64)
    saida = np.full(x.shape, np.nan, dtype=tipo)
    for trecho in trechos:
        # SEM arredondar: a janela é de um ciclo de TEMPO. Ver
        # `fasor.pesos_do_ciclo` para o que o arredondamento custava.
        n = ciclo_em_amostras(trecho.taxa_hz, frequencia_hz)
        fatia = (..., slice(trecho.inicio, trecho.fim))
        saida[fatia] = funcao(x[fatia], n)
    return saida
