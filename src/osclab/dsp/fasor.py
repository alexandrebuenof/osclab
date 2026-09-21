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
from dataclasses import dataclass

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
    """Quantas amostras a janela de um ciclo tem, arredondado.

    Quase todo relé grava um número inteiro de amostras por ciclo — 16, 20, 32,
    96. Quando não é inteiro (taxa declarada que não é múltipla da nominal), o
    arredondamento espalha um pouco de erro da fundamental para os harmônicos
    vizinhos; ainda é a melhor resposta disponível sem reamostrar.
    """
    if taxa_hz <= 0 or frequencia_hz <= 0:
        return 0
    return int(round(taxa_hz / frequencia_hz))


def de_janela(amostras: np.ndarray) -> Fasor | None:
    """O fasor de UMA janela já recortada, cujo ÚLTIMO ponto é o cursor.

    `amostras` tem exatamente um ciclo. O ângulo sai referido ao último ponto.
    """
    n = int(amostras.size)
    if n < MINIMO_POR_CICLO or not np.all(np.isfinite(amostras)):
        return None

    # k conta PARA TRÁS a partir do cursor: k=0 é a amostra do cursor, k=1 a
    # anterior. É essa contagem que põe a referência do ângulo no cursor, e não
    # no começo da janela — sem ela, o ângulo dependeria do tamanho da janela.
    janela = amostras[::-1]
    k = np.arange(n)
    giro = np.exp(1j * 2.0 * np.pi * k / n)

    # O fator 2/n vem da DFT de sinal real: metade da energia da fundamental
    # está na raia positiva e metade na negativa.
    x = (2.0 / n) * np.dot(janela, giro)

    amplitude = float(abs(x))
    return Fasor(
        fundamental=amplitude / math.sqrt(2.0),
        angulo=float(np.degrees(np.angle(x))),
        rms=float(np.sqrt(np.mean(np.square(amostras)))),
        dc=float(np.mean(amostras)),
        minimo=float(amostras.min()),
        maximo=float(amostras.max()),
    )


def no_instante(sinal: np.ndarray, i: int, por_ciclo: int) -> Fasor | None:
    """O fasor do ciclo que TERMINA na amostra `i`.

    Devolve `None` quando não há um ciclo inteiro antes do cursor — no começo
    do registro, por exemplo. Inventar um fasor com meia janela daria um número
    plausível e errado, que é a pior espécie.
    """
    if por_ciclo < MINIMO_POR_CICLO:
        return None
    inicio = i - por_ciclo + 1
    if inicio < 0 or i >= sinal.size:
        return None
    return de_janela(np.asarray(sinal[inicio:i + 1], dtype=np.float64))


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
