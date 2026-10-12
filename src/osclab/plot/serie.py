"""Reduzir um registro ao que cabe na tela, sem perder o pico.

## O erro que este módulo existe para evitar

Um registro tem 6000 amostras por canal e a tela tem 900 pixels de largura.
Alguém precisa descartar amostras. O jeito ingênuo — pegar uma a cada sete —
**apaga o pico da falta**: o instante de maior corrente tem uma chance em sete
de sobreviver, e o gráfico mostra uma falta menor do que foi.

O jeito certo, que todo oscilógrafo usa: dividir o eixo do tempo em uma coluna
por pixel e, em cada coluna, guardar o **mínimo e o máximo**. Desenhando os dois
sai um traço vertical que cobre exatamente o que aconteceu ali. Nenhum pico some,
e o volume de dados cai para duas amostras por pixel.

## E por que ela só entra quando a coluna está cheia

Porque reduzir move amostras no tempo: as da mesma coluna saem todas no instante
em que a coluna começa. Com a coluna cheia isso é meio pixel e ninguém vê; com
uma amostra e meia por coluna, é 10,8° de uma onda de 60 Hz, e o traço ondula.
Ver `LIMITE_SEM_REDUZIR`.

## Por que no servidor, e não no navegador

Porque aqui isto tem teste. E porque o navegador nunca precisa segurar 250 mil
pontos: ele pede a janela que está mostrando, do tamanho em pixels que tem.
Ampliar vira um pedido novo — em `localhost` isso custa milissegundos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from osclab.formats.base import Record
from osclab.plot import escala

#: Quantas amostras por coluna a redução espera antes de entrar.
#:
#: **A redução move amostras no tempo.** As que caem na mesma coluna são todas
#: desenhadas no instante em que a coluna começa — é o que permite um eixo de
#: tempo só para todos os canais. O deslocamento é sempre menor que uma coluna,
#: e é por isso que ele é invisível quando a coluna é estreita perto do ciclo.
#: Quando NÃO é, ele deforma a onda: medido num registro de 2000 Hz com 2000
#: amostras em 1550 colunas (1,29 amostra por coluna), a amostra atrasada é
#: desenhada 0,78 coluna antes da hora — **10,8° de onda**, com o ciclo
#: ocupando 26 px. O traço fica ondulado, e some ao ampliar: ampliando sobra
#: menos de uma amostra por coluna e nada é movido.
#:
#: Daí o limite ser 4, e não 1. Com menos de quatro amostras por coluna o
#: registro vai cru — são no máximo quatro pontos por pixel, que o traçador
#: desenha sem suar, e cada um no instante exato em que foi medido. Acima
#: disso, a coluna cobre um quarto de ciclo ou mais: o par mínimo-máximo vira
#: uma barra alta, as barras vizinhas se encostam, e o desenho já é uma FAIXA —
#: onde um deslocamento de meio pixel não tem como aparecer.
#:
#: O que a redução resolve continua valendo acima do limite: num registro de
#: 250 mil amostras, pegar uma a cada 160 apagaria o pico da falta.
LIMITE_SEM_REDUZIR = 4


@dataclass(frozen=True)
class Reducao:
    """O resultado: `tempo` e `valores` já prontos para desenhar."""

    tempo: np.ndarray            # (M,)
    valores: np.ndarray          # (C, M)
    reduzido: bool
    amostras_na_janela: int


def _fatias(n: int, colunas: int) -> np.ndarray:
    """Onde cada coluna começa, dentro de `n` amostras."""
    return np.unique(np.floor(np.linspace(0, n, colunas + 1)[:-1]).astype(np.int64))


def reduzir(tempo: np.ndarray, valores: np.ndarray, colunas: int) -> Reducao:
    """Reduz para `colunas` colunas, guardando mínimo e máximo de cada uma.

    `valores` é `(canais, amostras)`; a saída mantém o mesmo número de canais.
    """
    n = int(tempo.size)
    colunas = max(int(colunas), 1)

    if n == 0:
        return Reducao(tempo=tempo, valores=valores, reduzido=False,
                       amostras_na_janela=0)

    if n <= colunas * LIMITE_SEM_REDUZIR:
        return Reducao(tempo=tempo, valores=valores, reduzido=False,
                       amostras_na_janela=n)

    inicios = _fatias(n, colunas)
    minimos = np.minimum.reduceat(valores, inicios, axis=1)
    maximos = np.maximum.reduceat(valores, inicios, axis=1)

    # Dois pontos por coluna, no mesmo instante: o traço vertical que cobre o
    # que aconteceu naquele pixel. A ordem min-depois-max mantém a linha
    # contínua entre colunas vizinhas.
    saida_tempo = np.repeat(tempo[inicios], 2)
    saida = np.empty((valores.shape[0], inicios.size * 2), dtype=np.float64)
    saida[:, 0::2] = minimos
    saida[:, 1::2] = maximos

    return Reducao(tempo=saida_tempo, valores=saida, reduzido=True,
                   amostras_na_janela=n)


def recortar(registro: Record, de: float | None,
             ate: float | None) -> tuple[int, int]:
    """Índices das amostras dentro da janela `[de, ate]`, em segundos."""
    t = registro.time
    if t.size == 0:
        return (0, 0)
    inicio = 0 if de is None else int(np.searchsorted(t, de, side="left"))
    fim = t.size if ate is None else int(np.searchsorted(t, ate, side="right"))
    inicio = max(0, min(inicio, t.size - 1))
    fim = max(inicio + 1, min(fim, t.size))
    return (inicio, fim)


# ---------------------------------------------------------------------------
# Agrupar por unidade
# ---------------------------------------------------------------------------

#: Como chamar cada grupo na tela. O que não estiver aqui usa a própria unidade.
_TITULOS = {
    "A": "Correntes", "KA": "Correntes", "MA": "Correntes",
    "V": "Tensões", "KV": "Tensões", "MV": "Tensões",
    "HZ": "Frequência",
    "W": "Potência", "KW": "Potência", "MW": "Potência",
    "VAR": "Potência reativa", "KVAR": "Potência reativa",
}


def titulo_do_grupo(unidade: str) -> str:
    """`Correntes (A)`, `Tensões (kV)`.

    **Só a unidade.** O título já levou o apelido do conjunto — `Correntes [1]`,
    `Correntes [2]` num trafo. Saiu junto com o apelido dos canais: o nome do
    grupo agora aparece só no que sai de uma trinca (`3I0 G1`, `IN G1`), que é a
    única coisa sem nome de arquivo a herdar. Num trafo os dois painéis de
    corrente se chamam igual, e quem os distingue é o nome dos canais dentro
    deles — `IAW` num, `IAX` no outro; o grupo de cada um está no rodapé.
    """
    nome = _TITULOS.get(unidade.strip().upper())
    limpa = unidade.strip() or "sem unidade"
    return f"{nome} ({limpa})" if nome else limpa


def arredondar(v: np.ndarray, intervalo: float) -> list[float]:
    """Corta casas decimais que não cabem na tela, para o JSON não inchar."""
    casas = escala.casas_decimais(intervalo) + 2
    return [None if not math.isfinite(x) else round(float(x), casas) for x in v]
