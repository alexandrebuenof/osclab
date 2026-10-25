"""Potência trifásica a partir dos fasores de 60 Hz.

O que este módulo calcula
=========================

Dado o fasor de cada tensão e de cada corrente de um vão — janela a janela,
como `dsp/envoltoria.calcular_fasores` os produz —, saem:

    P    potência ativa      [W]     o que faz trabalho
    Q    potência reativa    [var]   o que só circula
    S    potência aparente   [VA]    |P + jQ|
    FP   fator de potência   [—]     P / S

Por que FASORIAL, e não o produto das ondas
===========================================

O produto amostra a amostra `v(t)·i(t)` é uma coisa legítima e diferente: é
uma ONDA, com nível contínuo e ondulação de 120 Hz, e a média de um ciclo
dela **é** o P deste módulo. Já foi medido na calculadora: a DC de
`[VAY] × [IAW]` bate com `V·I·cos(θ)` com erro de 0,0000 %.

Mas Q e FP não existem naquele caminho. Os dois são ângulo entre dois
fasores, e o produto de duas ondas destrói o ângulo: ele cria soma e
diferença de frequências, e nada no resultado diz de onde veio a defasagem.
Quem quiser a onda da potência instantânea escreve `[VAY] × [IAW]` na
calculadora — ela continua lá, e é a única que mostra a ondulação de 120 Hz
que mede desequilíbrio.

Fase ou linha: por que a base muda a conta
==========================================

**Tensão de fase (fase-neutro).** Cada fase tem a tensão dela contra o mesmo
neutro, então a potência se reparte::

    S_fase = V_fase · conj(I_fase) / 2          (fasores de pico)
    S_3φ   = S_a + S_b + S_c

**Tensão de linha.** Não existe potência "da fase A": não há referência de
neutro para atribuir a ela. O que existe é o total, pelo método dos dois
wattímetros, que é exato para três fios — com ou sem desequilíbrio::

    S_3φ = (V_ab · conj(I_a) + V_cb · conj(I_c)) / 2,   V_cb = −V_bc

Repare que I_b não entra: num sistema a três fios ele é −(I_a + I_c), e a
informação dele já está nos outros dois. Isso é teorema de Blondel, não
simplificação nossa.

A divisão por 2 em ambas aparece porque os fasores aqui são de PICO, como
saem da DFT. Com fasores eficazes ela não existiria — e trocar as duas
convenções em silêncio é como uma potência sai com metade do valor sem nada
na tela denunciando.

Sinal e sentido
===============

O sinal de P segue a polaridade do TC como o arquivo a gravou. P positivo
significa fluxo no sentido que o TC chama de positivo, e nada aqui tenta
adivinhar se aquilo é "entrando" ou "saindo" do barramento — isso é o
unifilar que diz. O mesmo vale para Q: positivo é indutivo na convenção do
gerador, que é a que sai desta conta.
"""

from __future__ import annotations

import numpy as np

#: O que um vínculo produz, em cada base de tensão.
#:
#: Em LINHA não há potência por fase: sem referência de neutro, repartir o
#: total entre as três fases seria inventar três números que o registro não
#: contém. Ver o cabeçalho.
GRANDEZAS_POR_BASE = {
    "fase": ("P", "Q", "S", "FP", "Pa", "Pb", "Pc"),
    "linha": ("P", "Q", "S", "FP"),
}

#: A unidade de cada uma. O FP não tem — é razão entre dois VA.
UNIDADE = {"P": "W", "Pa": "W", "Pb": "W", "Pc": "W",
           "Q": "var", "S": "VA", "FP": ""}


def complexa_por_fase(tensoes, correntes) -> list[np.ndarray]:
    """`S_a, S_b, S_c` a partir dos fasores de PICO de cada fase.

    Cada entrada é um vetor de complexos, um por janela — é assim que
    `envoltoria.calcular_fasores` devolve, e é o que permite a potência
    acompanhar o registro inteiro sem laço nenhum em Python.
    """
    return [v * np.conj(i) / 2.0 for v, i in zip(tensoes, correntes)]


def complexa_trifasica(tensoes, correntes, base: str = "fase") -> np.ndarray:
    """`S_3φ` — complexa, com `P = real` e `Q = imag`.

    `tensoes` vem na ordem da trinca: em `fase`, (Va, Vb, Vc); em `linha`,
    (Vab, Vbc, Vca). `correntes` é sempre (Ia, Ib, Ic).
    """
    if base == "linha":
        v_ab, v_bc, _ = tensoes
        i_a, _, i_c = correntes
        # V_cb = −V_bc. O sinal trocado é o que faz os dois wattímetros
        # somarem em vez de se cancelarem; invertê-lo dá um número plausível
        # e errado, que é por que ele está escrito e não deduzido.
        return (v_ab * np.conj(i_a) + (-v_bc) * np.conj(i_c)) / 2.0
    return sum(complexa_por_fase(tensoes, correntes))


def fator_de_potencia(s: np.ndarray, piso: float = 1e-9) -> np.ndarray:
    """`P / |S|`, com `NaN` onde não há potência que sirva de denominador.

    `NaN` e não zero: num trecho sem corrente o fator de potência não é zero,
    ele não existe — e zero desenharia uma linha no gráfico dizendo "carga
    puramente reativa", que é uma afirmação que ninguém mediu.
    """
    modulo = np.abs(s)
    saida = np.full(modulo.shape, np.nan, dtype=np.float64)
    bons = np.isfinite(modulo) & (modulo > piso)
    saida[bons] = np.real(s)[bons] / modulo[bons]
    return saida


def serie(grandeza: str, tensoes, correntes, base: str = "fase") -> np.ndarray:
    """A série de uma das grandezas, janela a janela."""
    if grandeza in ("Pa", "Pb", "Pc"):
        if base != "fase":
            return np.full(np.shape(correntes[0]), np.nan)
        qual = ("Pa", "Pb", "Pc").index(grandeza)
        return np.real(complexa_por_fase(tensoes, correntes)[qual])
    total = complexa_trifasica(tensoes, correntes, base)
    if grandeza == "P":
        return np.real(total)
    if grandeza == "Q":
        return np.imag(total)
    if grandeza == "S":
        return np.abs(total)
    if grandeza == "FP":
        return fator_de_potencia(total)
    return np.full(np.shape(total), np.nan)
