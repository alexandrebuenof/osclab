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

#: Acima disso por coluna, a redução compensa. Abaixo, manda-se as amostras.
LIMITE_SEM_REDUZIR = 2


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
    nome = _TITULOS.get(unidade.strip().upper())
    limpa = unidade.strip() or "sem unidade"
    return f"{nome} ({limpa})" if nome else limpa


def arredondar(v: np.ndarray, intervalo: float) -> list[float]:
    """Corta casas decimais que não cabem na tela, para o JSON não inchar."""
    casas = escala.casas_decimais(intervalo) + 2
    return [None if not math.isfinite(x) else round(float(x), casas) for x in v]
