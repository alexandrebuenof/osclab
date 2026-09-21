"""Componentes simétricas: a transformação de Fortescue.

## O que elas respondem

Três fases desequilibradas sempre podem ser escritas como a soma de três
conjuntos equilibrados:

* **sequência positiva** (`I1`) — o sistema girando no sentido normal. É o que
  existe sozinho quando está tudo equilibrado;
* **sequência negativa** (`I2`) — gira ao contrário. Só aparece com
  desequilíbrio: falta entre fases, fase aberta, carga desbalanceada;
* **sequência zero** (`I0`) — as três em fase, somando em vez de se cancelar.
  É a corrente que volta pela terra.

Por isso elas dizem o **tipo da falta** de relance, que nenhuma leitura de fase
isolada diz: `3I0` alto é falta para a terra; `I2` alto sem `3I0` é falta entre
fases; `I2` com `3I0` é fase-fase-terra.

## Por que `3I0` e não `I0`

`I0` é a média das três; `3I0` é a soma. A norma e os relés trabalham com a
soma, porque é ela que circula fisicamente pelo neutro — é o número que se
compara com o ajuste do elemento de terra. Mostrar `I0` obrigaria o engenheiro
a multiplicar por três de cabeça toda vez.

Para tensão vale o mesmo: `3V0` é o que aparece nos ajustes.

## Sobre a referência do ângulo

As três entradas têm que ser fasores do **mesmo instante**, com o ângulo na
mesma referência — e são: `dsp/fasor.py` devolve o ângulo referido ao cursor,
antes de qualquer referência de tela. Misturar referências aqui giraria uma
fase em relação às outras e o desequilíbrio apareceria do nada.
"""

from __future__ import annotations

import cmath

import numpy as np

#: O operador `a` de Fortescue: giro de 120°. `a² ` gira 240°, e `1 + a + a² = 0`
#: — é essa identidade que faz a sequência zero ser exatamente a parte que não
#: se cancela.
A = cmath.exp(2j * cmath.pi / 3)


def de_fasores(a: complex, b: complex, c: complex) -> tuple[complex, complex, complex]:
    """`(3·zero, positiva, negativa)` a partir das três fases.

    Aceita números complexos ou arrays do numpy — a conta é a mesma, e é assim
    que a curva ao longo do tempo sai sem laço em Python.

    A sequência zero já sai **multiplicada por três**: é a soma que circula
    pelo neutro e é ela que se compara com o ajuste do relé.
    """
    return (a + b + c,
            (a + A * b + A**2 * c) / 3.0,
            (a + A**2 * b + A * c) / 3.0)


def equilibrio(positiva, negativa) -> float | np.ndarray:
    """`|I2| / |I1|` em percentual — o quanto o sistema está desequilibrado.

    Zero num sistema perfeitamente equilibrado. É o critério que os relés de
    sequência negativa usam, e o número que separa uma falta entre fases de um
    curto trifásico: o trifásico é equilibrado e não gera negativa.

    Devolve `0` onde não há positiva de que ser percentual — pela mesma razão
    que `DC %` e `THD` se recusam a existir sem fundamental.
    """
    p, n = np.abs(positiva), np.abs(negativa)
    with np.errstate(divide="ignore", invalid="ignore"):
        saida = np.where(p > 0, 100.0 * n / p, 0.0)
    return saida if isinstance(saida, np.ndarray) and saida.ndim else float(saida)
