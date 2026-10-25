"""Fasor de um ciclo: o que o relé enxerga num instante.

## O que um fasor responde

A tabelinha do cursor mostra o valor **instantâneo** — a onda passando ali
naquele microssegundo. Ele balança: `95,1 A`, uma amostra depois `88,2 A`, meio
ciclo depois `-95,1 A`. Ninguém pergunta isso.

Quando se pergunta "de quanto foi a corrente de falta", quer-se **um número**.
O fasor dá esse número: pega um ciclo da onda e responde qual senoide de 60 Hz
melhor a descreve — amplitude e ângulo. É a mesma conta que o relé faz por
dentro para decidir se atua.

## A janela termina no cursor, nunca é centrada

Decisão de 18/09/2026, e a razão é do domínio: **o relé só conhece o passado.**
Uma janela centrada usaria meio ciclo de amostras que, no instante da decisão,
ainda não existiam. O fasor da tela deixaria de ser comparável com o que o relé
calculou — e a tela passaria a "adivinhar" a falta meio ciclo antes de ela
aparecer na onda.

A consequência visível, e correta: depois do início da falta o módulo leva **um
ciclo inteiro** para subir. É assim no relé e é assim no SIGRA.

## Eficaz, não amplitude

`fundamental` é o valor **eficaz** da componente fundamental — amplitude
dividida por √2. Foi conferido contra o SIGRA nos números de um registro real:
a coluna "Fundamental" dele só fecha com a coluna "Extremum" lendo-se eficaz.

    Current IC C | Fundamental 2,3449 A | Extremum 3,7229 A | DC 16,9 %
    2,3449 × √2 = 3,316  (pico da fundamental)
    3,316 + 16,9 % × 2,3449 = 3,712  ≈  3,7229 medido pelo SIGRA

Implementar como amplitude daria √2 de diferença — um erro que se procura por
horas, porque o gráfico continua parecendo certo.

## O ângulo é absoluto aqui dentro

Este módulo devolve o ângulo referido a um cosseno no **instante do cursor**.
Quem escolhe a referência de tela (a fase A, ou o canal que o usuário clicou) é
`plot/leitura.py`, subtraindo. Guardar o absoluto é o que torna a troca de
referência barata — e é o que vai permitir, no marco 0.5, comparar ângulos de
dois registros diferentes na mesma base.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace

import numpy as np

#: Abaixo disto não há ciclo que se meça. Quatro amostras por ciclo é o piso do
#: que fabricante nenhum grava; menos que isso é arquivo estranho.
MINIMO_POR_CICLO = 4

#: Quanto da janela precisa ser fundamental para que um PERCENTUAL DELA
#: signifique alguma coisa.
#:
#: `DC %` e `THD` são os dois percentuais **da fundamental**. Quando a
#: fundamental some, o denominador some junto e o percentual estoura: num
#: registro real, um canal de corrente depois de o disjuntor abrir mostrou
#: `DC 5.484,9 %` — 0,15 A de offset do conversor A/D divididos por 0,0028 A de
#: fundamental. A conta estava certa e a informação era lixo.
#:
#: O critério olha a própria janela: a fundamental tem que ser pelo menos um
#: quarto do RMS dela. Abaixo disso o que está ali dentro não é um sinal de
#: 60 Hz — é ruído, offset parado ou transitório puro, e o resto da janela já
#: supera a fundamental em quase quatro vezes. Percentual de coisa nenhuma não
#: se mostra: mostra-se traço.
#:
#: O limite NÃO afeta `fundamental`, `rms`, `dc` nem `angulo`. Esses continuam
#: sendo medidas honestas, com unidade, em qualquer janela.
MINIMO_FUNDAMENTAL = 0.25


# ---------------------------------------------------------------------------
# O ESTIMADOR do fasor: Fourier de um ciclo ou cosseno da SEL
# ---------------------------------------------------------------------------

#: Os estimadores que o programa sabe usar. Fourier é o padrão: foi ele que se
#: conferiu contra o SIGRA e contra o gabarito dos relés. O cosseno é o da
#: linha SEL (AG2022-09, Eq. 3): a parte real do Fourier (o filtro cosseno) e,
#: como quadratura, ela mesma 1/4 de ciclo atrás. Rejeita muito melhor a
#: exponencial decrescente da falta — o seno é que vazava — e custa 1/4 de
#: ciclo a mais para o primeiro fasor válido.
ESTIMADORES = ("fourier", "cosseno", "dois_ciclos", "meio_ciclo", "pico_a_pico")

#: Os três de baixo vieram dos manuais do parque (22/10/2026):
#:
#: - `dois_ciclos` — Fourier com janela de DOIS ciclos, o «2-cycle filter» da
#:   sobrecorrente do SIPROTEC 5. Rejeita mais harmônico e inter-harmônico e
#:   atrasa um ciclo a mais. A Siemens não publica os coeficientes: esta é a
#:   DFT canônica de dois ciclos.
#: - `meio_ciclo` — Fourier de MEIO ciclo, o da distância rápida do RET670 e o
#:   da tensão no GE T60. Sobe em meio ciclo e oscila com a contínua e com os
#:   harmônicos pares, que meio ciclo não rejeita. É exato numa senoide pura.
#: - `pico_a_pico` — (máximo − mínimo do último ciclo) ÷ 2√2, o «Peak-to-Peak»
#:   da sobrecorrente ABB 615/620. Cancela a contínua, não rejeita harmônico e
#:   aguenta TC saturado. **Só dá MÓDULO**: o ângulo, as sequências e os planos
#:   continuam saindo do Fourier, e a tela diz isso no menu.

#: Qual vale NESTE pedido. É contexto e não argumento: o estimador muda o
#: fasor de tudo — cursor, curvas de 60 Hz, sequências, fasorial, complexo,
#: impedância — e passá-lo de mão em mão por quinze assinaturas é o jeito de
#: um caminho esquecer e calcular com o outro. O servidor abre o contexto por
#: pedido (`usando`); fora dele vale Fourier, e é o que os testes antigos usam.
_ESTIMADOR: ContextVar[str] = ContextVar("estimador_do_fasor", default="fourier")


def estimador() -> str:
    """O estimador em vigor: `fourier` ou `cosseno`."""
    return _ESTIMADOR.get()


@contextmanager
def usando(nome: str | None):
    """Calcula o que estiver dentro com o estimador `nome`.

    Nome desconhecido vira Fourier: um parâmetro estranho na URL não pode
    virar erro 500, e o padrão é o conferido.
    """
    marca = _ESTIMADOR.set(nome if nome in ESTIMADORES else "fourier")
    try:
        yield
    finally:
        _ESTIMADOR.reset(marca)


@dataclass(frozen=True)
class Fasor:
    """O que uma janela de um ciclo revela sobre um canal."""

    #: Valor eficaz da componente fundamental (mesma unidade do canal).
    fundamental: float
    #: Ângulo em graus, referido a um cosseno no instante do cursor.
    angulo: float
    #: Valor eficaz VERDADEIRO da janela: inclui harmônicos e componente DC.
    #: A diferença para `fundamental` é, por si só, um diagnóstico do registro.
    rms: float
    #: Componente contínua (média da janela), na unidade do canal.
    dc: float
    #: Maior e menor valor instantâneo dentro da janela.
    minimo: float
    maximo: float

    @property
    def serve_de_referencia(self) -> bool:
        """Há fundamental suficiente para um percentual dela significar algo?

        Ver `MINIMO_FUNDAMENTAL`. Quando é `False`, `dc_percentual` e
        `distorcao` devolvem `None` — a tela mostra traço em vez de um número
        de quatro dígitos que parece defeito do programa.
        """
        return self.rms > 0 and self.fundamental >= MINIMO_FUNDAMENTAL * self.rms

    @property
    def dc_percentual(self) -> float | None:
        """A DC como percentual da fundamental — a convenção do SIGRA.

        `None` quando não há fundamental que sirva de denominador. A DC em si
        (`dc`, na unidade do canal) continua valendo: é a média da janela, e
        média não depende de denominador nenhum.
        """
        if not self.serve_de_referencia:
            return None
        return 100.0 * self.dc / self.fundamental

    @property
    def distorcao(self) -> float | None:
        """Tudo que não é fundamental, em percentual DA FUNDAMENTAL (THD).

        Zero numa senoide pura. Alto em energização de trafo (harmônicos) e no
        primeiro ciclo de uma falta assimétrica (componente DC). É o número que
        avisa que o fasor sozinho não conta a história toda.

        Dividir pela fundamental, e não pelo RMS total, é a convenção do setor
        e a do SIGRA: "30 % de terceiro harmônico" quer dizer 30 % **da
        fundamental**. Pelo RMS total o mesmo sinal daria 28,7 %, e o número da
        tela discordaria do que está escrito no relatório de qualidade.

        `None` pela mesma razão do `dc_percentual`: sem fundamental não há de
        que ser percentual.
        """
        if not self.serve_de_referencia:
            return None
        sobra = max(self.rms**2 - self.fundamental**2, 0.0)
        return 100.0 * math.sqrt(sobra) / self.fundamental


def amostras_por_ciclo(taxa_hz: float, frequencia_hz: float) -> int:
    """Quantas amostras cabem num ciclo, ARREDONDADO para inteiro.

    É a conta de "andar um ciclo" com a tecla, de quantas amostras a janela
    ocupa na tela e de quanta margem carregar. Para MEDIR, ver
    `ciclo_em_amostras` e `pesos_do_ciclo`: lá a janela é de um ciclo de tempo,
    e o arredondamento daqui é justamente o que ela existe para não fazer.
    """
    if taxa_hz <= 0 or frequencia_hz <= 0:
        return 0
    return int(round(taxa_hz / frequencia_hz))


def ciclo_em_amostras(taxa_hz: float, frequencia_hz: float) -> float:
    """Um ciclo em amostras, SEM arredondar: 2000 Hz / 60 Hz = 33,3333."""
    if taxa_hz <= 0 or frequencia_hz <= 0:
        return 0.0
    return float(taxa_hz) / float(frequencia_hz)


#: Abaixo disto a parte fracionária é ruído de ponto flutuante, não taxa.
_FRACAO_DESPREZIVEL = 1e-9


def pesos_do_ciclo(por_ciclo: float) -> np.ndarray:
    """Os pesos da janela de UM CICLO DE TEMPO, da amostra mais antiga à do
    cursor. Somam exatamente `por_ciclo`.

    ## O problema que isto resolve

    Um SEL a 2000 Hz num sistema de 60 Hz grava **33,3333 amostras por ciclo**.
    A janela de 33 amostras é 0,99 ciclo, e a média de 0,99 ciclo de uma
    senoide **não é zero**: sobra 1,01 % do pico, girando a 60 Hz. Esse
    vazamento aparece como ondulação de 1,01 % no RMS e na fundamental — e
    **como o gráfico inteiro** na componente contínua, cujo valor verdadeiro é
    zero.

    Não é caso raro: 2000 Hz é a taxa de quase todo COMTRADE do parque
    (SEL-451, SEL-487E, SIPROTEC). Medido e conferido contra a teoria:

        taxa      am/ciclo   janela de 33   janela de um ciclo de tempo
        1200 Hz     20,000        0,000 %                     0,000 %
        2000 Hz     33,333        1,011 %                     0,001 %
        10000 Hz   166,667        0,200 %                     0,000 %

    ## Como

    A janela passa a ser um ciclo de TEMPO, integrado pela regra do trapézio,
    com a ponta fracionária interpolada entre as duas amostras que a cercam.
    Isso vira um conjunto de pesos fixos, e é por eles que a curva (soma móvel
    sobre o registro inteiro) e o cursor (uma janela só) continuam sendo **uma
    implementação, dois usos**.

    ## Quando a taxa FECHA, nada muda

    Com `por_ciclo` inteiro os pesos são todos 1 — o Fourier de ciclo cheio de
    sempre, que é o que o relé roda por dentro. Isto é deliberado: todo número
    já conferido contra o SIGRA e contra os relés saiu de arquivo com taxa
    inteira (o MiCOM a 20 amostras por ciclo, os `.CEV` a 4 e 8), e essa
    conferência continua valendo dígito a dígito.
    """
    n = float(por_ciclo)
    inteiro = int(math.floor(n + _FRACAO_DESPREZIVEL))
    fracao = n - inteiro
    if fracao < _FRACAO_DESPREZIVEL:
        return np.ones(inteiro, dtype=np.float64)

    # `inteiro + 2` amostras: as `inteiro + 1` que o trapézio cheio usa, mais a
    # anterior, de onde sai a interpolação da ponta fracionária.
    pesos = np.ones(inteiro + 2, dtype=np.float64)
    pesos[0] = fracao * fracao / 2.0
    pesos[1] = 0.5 + fracao * (2.0 - fracao) / 2.0
    pesos[-1] = 0.5
    return pesos


def de_janela(amostras: np.ndarray, por_ciclo: float | None = None,
              pesos: np.ndarray | None = None) -> Fasor | None:
    """O fasor de UMA janela já recortada, cujo ÚLTIMO ponto é o cursor.

    Sem `por_ciclo`, a janela É um ciclo e tem peso 1 em cada amostra — o
    Fourier de ciclo cheio de sempre. Com ele, a janela é de um ciclo de TEMPO
    e traz uma ou duas amostras a mais, ponderadas por `pesos_do_ciclo`; ver lá
    o porquê.

    O ângulo sai referido ao último ponto em qualquer um dos dois casos.
    """
    tamanho = int(amostras.size)
    if tamanho < MINIMO_POR_CICLO or not np.all(np.isfinite(amostras)):
        return None
    n = float(tamanho if por_ciclo is None else por_ciclo)
    if n < MINIMO_POR_CICLO:
        return None
    if pesos is None:
        pesos = (np.ones(tamanho) if por_ciclo is None
                 else pesos_do_ciclo(n))
    if pesos.size != tamanho:
        return None

    # k conta PARA TRÁS a partir do cursor: k=0 é a amostra do cursor, k=1 a
    # anterior. É essa contagem que põe a referência do ângulo no cursor, e não
    # no começo da janela — sem ela, o ângulo dependeria do tamanho da janela.
    # Com `n` fracionário ela também é o que faz a ponta interpolada girar o
    # tanto certo.
    janela = amostras[::-1]
    w = pesos[::-1]
    k = np.arange(tamanho)
    giro = np.exp(1j * 2.0 * np.pi * k / n)

    # O fator 2/n vem da DFT de sinal real: metade da energia da fundamental
    # está na raia positiva e metade na negativa.
    x = (2.0 / n) * np.dot(janela * w, giro)

    # O extremo é dos pontos que estão DENTRO do ciclo. Com janela fracionária
    # a amostra mais antiga fica de fora dele — ela entra só para interpolar a
    # ponta, e deixá-la mandar no "Extremum" esticaria a janela.
    dentro = janela[:int(math.floor(n + _FRACAO_DESPREZIVEL)) + 1]

    amplitude = float(abs(x))
    return Fasor(
        fundamental=amplitude / math.sqrt(2.0),
        angulo=float(np.degrees(np.angle(x))),
        rms=float(np.sqrt(np.dot(np.square(janela), w) / n)),
        dc=float(np.dot(janela, w) / n),
        minimo=float(dentro.min()),
        maximo=float(dentro.max()),
    )


def ordens_mediveis(por_ciclo: float) -> int:
    """Até que harmônico esta taxa de amostragem deixa medir.

    É o Nyquist da janela: com `n` amostras por ciclo, a maior raia que a DFT
    distingue é a de ordem `n/2`. Pedir além disso não dá erro — dá
    **aliasing**, que é pior: uma barra plausível no lugar errado.

    Na prática do parque: 2000 Hz a 60 Hz são 33,3 amostras/ciclo → até o 16º;
    um MiCOM a 1200 Hz são 20/ciclo → até o 10º; um `.CEV` a 4/ciclo não mede
    harmônico nenhum (devolve 1, que é só a fundamental).
    """
    return max(1, int(math.floor(float(por_ciclo) / 2.0)))


def espectro(amostras: np.ndarray, por_ciclo: float | None = None,
             pesos: np.ndarray | None = None, ate: int | None = None,
             ciclos: float = 1.0, fino: bool = False) -> np.ndarray | None:
    """O valor EFICAZ de cada harmônico de 1 até `ate`, na janela recortada.

    É a mesma DFT de `de_janela` — mesma janela, mesmos pesos, mesma referência
    no cursor — pedindo outras raias. `espectro(...)[0]` é, por construção,
    igual ao `fundamental` daquela janela, e há teste para isso: duas contas do
    mesmo número é como o espectro e o fasor passariam a discordar.

    **Sai do sinal BRUTO, e quem chama é que garante isso.** Rodar sobre a onda
    já filtrada em 60 Hz mediria o que o filtro deixou passar — ou seja, a
    fundamental e mais nada.

    ## O piso: com taxa fracionária, o espectro tem vazamento

    A janela de um ciclo de TEMPO (ver `pesos_do_ciclo`) é construída para
    zerar o vazamento da FUNDAMENTAL — e zera: a ponta fracionária é
    interpolada de primeira ordem, que basta para uma volta por ciclo. Um
    harmônico de ordem `h` dá `h` voltas na mesma janela, e ali a mesma
    interpolação já não fecha.

    Medido, senoide pura de 60 Hz, maior raia espúria acima da fundamental:

        taxa       am/ciclo    raia espúria    piso do THD
        1200 Hz      20,000        0,000 %        0,000 %
        1920 Hz      32,000        0,000 %        0,000 %
        2000 Hz      33,333        0,309 %        0,551 %

    Ou seja: **com taxa inteira o espectro é exato**; com a fracionária do SEL
    a 2000 Hz há um piso de meio por cento. É pequeno para proteção (ninguém
    age sobre 0,5 % de 5º harmônico) mas não é zero, e a tela não desenha
    barra abaixo desse piso — ver `RUIDO_DA_BARRA` em `web/static/js/onda.js`.

    ## Janela de mais de um ciclo

    Com `ciclos > 1`, `por_ciclo` passa a ser o comprimento da JANELA INTEIRA
    em amostras (`ciclos × amostras por ciclo`), e a raia do harmônico `h` do
    sistema mora no índice `h × ciclos` da janela — sete ciclos de 60 Hz dão
    sete voltas, e é a sétima raia da janela que é a fundamental do sistema.

    O teto continua saindo da TAXA (`por_ciclo / ciclos`), que é quem limita:
    janela longa dá mais resolução, não mais Nyquist.

    **E `ciclos` tem que ser INTEIRO.** Numa janela de 7,3 ciclos as raias não
    caem em cima dos múltiplos de 60 Hz e a fundamental escorre para as
    vizinhas: medido, uma senoide 100 % pura aparece com 3,67 % de harmônico e
    4,71 % de THD. Quem chama é que arredonda — ver `plot/leitura.py`.

    `None` quando a janela não presta (curta demais, com NaN) ou quando `ate`
    passa do que a taxa mede — ver `ordens_mediveis`.
    """
    tamanho = int(amostras.size)
    if tamanho < MINIMO_POR_CICLO or not np.all(np.isfinite(amostras)):
        return None
    n = float(tamanho if por_ciclo is None else por_ciclo)
    if n < MINIMO_POR_CICLO:
        return None
    if pesos is None:
        pesos = np.ones(tamanho) if por_ciclo is None else pesos_do_ciclo(n)
    if pesos.size != tamanho:
        return None

    teto = ordens_mediveis(n / max(float(ciclos), 1.0))
    quantas = teto if ate is None else min(int(ate), teto)
    if quantas < 1:
        return None

    # k conta para trás a partir do cursor, como em `de_janela`: é o que põe a
    # referência no cursor. Aqui o giro é de `h` voltas por ciclo em vez de uma.
    janela = (amostras[::-1] * pesos[::-1]).astype(np.float64)
    k = np.arange(tamanho)
    if fino:
        # TODAS as raias da janela, e não só as dos múltiplos de 60 Hz: numa
        # janela de 5 ciclos a resolução é 12 Hz, e o que cai entre dois
        # harmônicos (inter-harmônico, batimento) só aparece aqui. A raia `m`
        # é a ordem `m / ciclos`. Com 1 ciclo é o mesmo que sem `fino`.
        ordens = np.arange(1, quantas * int(round(ciclos)) + 1, dtype=np.float64)
    else:
        ordens = np.arange(1, quantas + 1, dtype=np.float64) * float(ciclos)
    giro = np.exp(1j * 2.0 * np.pi * np.outer(ordens, k) / n)
    x = (2.0 / n) * (giro @ janela)
    return np.abs(x) / math.sqrt(2.0)


def regime_da_janela(janela: np.ndarray,
                     anterior: np.ndarray | None) -> float:
    """Quanto esta janela difere da ANTERIOR, de 0 a 1.

    Zero quer dizer que o ciclo se repetiu: a DFT de um ciclo supõe
    exatamente isso, e aí ela mede o que promete. Perto de 1 quer dizer que a
    janela pegou o sinal mudando de patamar — energização, início de falta — e
    que a diferença entre o antes e o depois escorre para TODAS as raias, com
    a forma lisa de 1/h.

    `anterior` é a janela de mesmo tamanho um ciclo atrás. Sem ela — o cursor
    está no primeiro ciclo do arquivo — devolve 0: não se pode comparar com o
    que não foi gravado, e avisar por falta de dado seria pior que calar.

    ## Por que a comparação é com o ciclo ANTERIOR

    A primeira versão disto comparava as duas METADES da mesma janela, e
    estava errada. Num inrush a corrente é unipolar: os dois meios-ciclos
    têm eficazes muito diferentes o tempo todo, e não porque haja transição —
    é a forma de onda. O aviso ficava aceso do começo ao fim do registro, e
    aviso que nunca apaga é aviso que ninguém lê. Medido naquela versão, com
    a constante de tempo do inrush:

        tau do inrush      em que ciclo o aviso apagava
          40 ms                   6
         100 ms                  12
         250 ms                  29
         500 ms                  nunca

    Comparar com o ciclo anterior separa as duas coisas. A assimetria some da
    conta — ela é igual nos dois ciclos —, e o que sobra é só o que MUDOU:

        ciclos após o evento       0,5    1      2      3     10     30
        falta franca, 1 → 8 pu    0,82   0,87   0,01   0,00   0,00   0,00
        inrush, tau = 40 ms       1,00   1,00   0,20   0,15   0,01   0,00
        inrush, tau = 500 ms      1,00   1,00   0,02   0,02   0,02   0,01
        inrush, tau = 2 s         1,00   1,00   0,00   0,01   0,01   0,01
        senoide pura              0,00   0,00   0,00   0,00   0,00   0,00
        40 % de 3ª + 20 % de 5ª   0,00   0,01   0,00   0,01   0,01   0,01

    Duas leituras importam aí. A penúltima linha e a última: distorção
    verdadeira de 44 % não move este número — ele não mede harmônico, mede se
    a janela tem direito de medir harmônico. E a coluna do ciclo 2: em todos
    os transitórios o aviso já apagou, porque a janela tem um ciclo de largura
    e a essa altura ela já não toca o evento.

    ## O limiar

    `LIMIAR_DE_REGIME = 0,30`. Acima dele só ficam as janelas que tocam a
    transição (0,82 a 1,00); o maior valor fora delas é 0,20, e o maior em
    regime é 0,01.

    **Isto é AVISO, nunca bloqueio.** As barras continuam desenhadas: na
    janela da transição o 2º harmônico ainda é informação de verdade, e quem
    analisa é que decide. Ver a regra do projeto em `plot/contas.py`.
    """
    if anterior is None or janela.size < 4 or anterior.size < 4:
        return 0.0
    if not np.all(np.isfinite(janela)) or not np.all(np.isfinite(anterior)):
        return 0.0
    agora = float(np.sqrt(np.mean(janela.astype(np.float64) ** 2)))
    antes = float(np.sqrt(np.mean(anterior.astype(np.float64) ** 2)))
    maior = max(agora, antes)
    if maior <= 0.0:
        return 0.0
    return abs(agora - antes) / maior


#: A partir de quanto a janela deixa de estar em regime — ver
#: `regime_da_janela`, que traz a medição que escolheu este número.
LIMIAR_DE_REGIME = 0.30


def distorcao_do_espectro(eficazes: np.ndarray) -> float | None:
    """O THD a partir das barras: `√(Σ h≥2) / h1`, em percentual.

    **Não é o mesmo número de `Fasor.distorcao`**, e a diferença é informação:
    aquele é "tudo que não é fundamental" (inclui DC, ruído e o que está acima
    do teto de ordens); este é a soma das raias que o desenho mostra. O da tela
    tem que ser este, senão o usuário soma as barras e não fecha com o número.
    """
    if eficazes is None or eficazes.size < 2:
        return None
    base = float(eficazes[0])
    if base <= 0:
        return None
    sobra = float(np.sqrt(np.sum(np.square(eficazes[1:]))))
    return 100.0 * sobra / base


def no_instante(sinal: np.ndarray, i: int, por_ciclo: float) -> Fasor | None:
    """O fasor do ciclo que TERMINA na amostra `i`.

    Devolve `None` quando não há um ciclo inteiro antes do cursor — no começo
    do registro, por exemplo. Inventar um fasor com meia janela daria um número
    plausível e errado, que é a pior espécie.

    **A janela é a MESMA de `envoltoria`**, pesos inclusive: é o que faz a
    curva e o cursor darem o mesmo número, e há teste para isso.
    """
    if por_ciclo < MINIMO_POR_CICLO:
        return None
    pesos = pesos_do_ciclo(por_ciclo)
    inicio = i - pesos.size + 1
    if inicio < 0 or i >= sinal.size:
        return None
    f = de_janela(np.asarray(sinal[inicio:i + 1], dtype=np.float64),
                  por_ciclo, pesos)
    qual = estimador()
    if f is None or qual == "fourier":
        return f
    from osclab.dsp import envoltoria  # aqui: envoltoria importa este módulo
    if qual == "pico_a_pico":
        # Só o MÓDULO muda: o ângulo segue o Fourier (o pico a pico não tem
        # ângulo), e o menu do filtro diz isso.
        pp = envoltoria.pico_a_pico(np.asarray(sinal[inicio:i + 1],
                                               dtype=np.float64), por_ciclo)[-1]
        return replace(f, fundamental=float(pp)) if np.isfinite(pp) else None
    # COSSENO, DOIS CICLOS e MEIO CICLO: módulo e ângulo saem do mesmo caminho
    # das curvas (`envoltoria.fasores`), com a história que cada um pede — 1/4
    # de ciclo a mais no cosseno, um ciclo a mais nos dois ciclos. RMS, DC e
    # extremos continuam da janela de um ciclo: são medidas da janela, não do
    # estimador.
    recuo = (int(math.ceil(por_ciclo)) + 1 if qual == "dois_ciclos"
             else 0 if qual == "meio_ciclo"
             else int(math.ceil(por_ciclo / 4.0)) + 1)
    if inicio - recuo < 0:
        return None
    x = envoltoria.fasores(np.asarray(sinal[inicio - recuo:i + 1],
                                      dtype=np.float64), por_ciclo)[-1]
    if not np.isfinite(x):
        return None
    return replace(f, fundamental=float(abs(x)) / math.sqrt(2.0),
                   angulo=float(np.degrees(np.angle(x))))


def em_relacao_a(angulo: float, referencia: float | None) -> float:
    """O ângulo medido a partir de `referencia`, normalizado em (-180, 180].

    Ângulo absoluto não existe na prática: todo fasor é relativo a alguma
    coisa. Aqui é onde a escolha do usuário — a fase A, ou o canal que ele
    clicou — vira o zero da tela.
    """
    bruto = angulo - (referencia or 0.0)
    # O laço do módulo, feito na mão para o -180 virar +180 e não o contrário:
    # o eixo R-X e a comparação com o SIGRA ficam mais legíveis assim.
    while bruto <= -180.0:
        bruto += 360.0
    while bruto > 180.0:
        bruto -= 360.0
    return bruto
