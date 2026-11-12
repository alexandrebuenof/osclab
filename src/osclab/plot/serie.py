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

from dataclasses import dataclass

import numpy as np

from osclab.formats.base import Record, lembrado_do_registro
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


# ---------------------------------------------------------------------------
# A pirâmide: mínimo e máximo por BLOCO, feitos uma vez por registro
# ---------------------------------------------------------------------------

#: Amostras por bloco da pirâmide de mínimos e máximos (`piramide`).
BLOCO = 64

#: A partir de quantas amostras por coluna a redução usa a pirâmide. Abaixo
#: disso a coluna tem poucos blocos inteiros, e as bordas — lidas amostra a
#: amostra — são quase a coluna toda.
COLUNA_PARA_PIRAMIDE = 4 * BLOCO


def piramide(registro: Record) -> tuple[np.ndarray, np.ndarray]:
    """`(mínimos, máximos)` de cada bloco de `BLOCO` amostras, por canal.

    Feita UMA vez por registro aberto (`base.lembrado_do_registro`) — uma
    passada pela matriz — e guardada: são `2/BLOCO` do tamanho dela (num
    registro de 12 canais × 3 milhões de amostras, 9 MB). Cada linha termina
    com um bloco-sentinela neutro (+∞ / −∞), para `reduceat` poder apontar o
    fim. É o que torna a redução de um pedido de janela proporcional às
    COLUNAS da tela e não às amostras dela (ver `reduzir_canal`).
    """
    def fazer():
        a = np.asarray(registro.analog)
        if a.ndim != 2:
            vazio = np.empty((0, 1))
            return vazio, vazio
        blocos = a.shape[1] // BLOCO
        corpo = a[:, :blocos * BLOCO].reshape(a.shape[0], blocos, BLOCO)
        minimos = np.empty((a.shape[0], blocos + 1), dtype=np.float64)
        maximos = np.empty((a.shape[0], blocos + 1), dtype=np.float64)
        minimos[:, :blocos] = corpo.min(axis=2)
        maximos[:, :blocos] = corpo.max(axis=2)
        minimos[:, blocos] = np.inf
        maximos[:, blocos] = -np.inf
        minimos.setflags(write=False)
        maximos.setflags(write=False)
        return minimos, maximos
    return lembrado_do_registro(registro, "serie.piramide", (BLOCO,), fazer)


def reduzir_canal(registro: Record, canal: int, i0: int, i1: int,
                  colunas: int) -> np.ndarray | None:
    """O mínimo e o máximo de cada coluna da janela `[i0, i1)` de UM canal cru.

    O MESMO resultado de `reduzir` sobre as amostras do canal — mesmas
    colunas (`_fatias`), mesmo mínimo e máximo de cada uma, intercalados
    (mínimo, máximo) —, sem passar por elas: o miolo de cada coluna sai dos
    blocos inteiros da `piramide`, e só as duas pontas (menos de `BLOCO`
    amostras cada) são lidas amostra a amostra. O custo é das colunas, não
    da janela: num registro de ondas viajantes, milhões de amostras por canal.

    `None` quando a coluna é estreita demais para valer a pena
    (`COLUNA_PARA_PIRAMIDE`) ou quando nem há redução — aí vale `reduzir`.
    Os valores são os CRUS do arquivo: converter (TC/TP, prefixo) é
    multiplicar por um número positivo, e quem chama converte depois — o
    mínimo de cada coluna continua sendo a mesma amostra.
    """
    n = int(i1 - i0)
    colunas = max(int(colunas), 1)
    if n <= colunas * LIMITE_SEM_REDUZIR or n < colunas * COLUNA_PARA_PIRAMIDE:
        return None
    minimos_b, maximos_b = piramide(registro)
    x = registro.analog[canal]
    inicio = i0 + _fatias(n, colunas)
    fim = np.append(inicio[1:], i1)
    # Os blocos INTEIROS dentro de cada coluna: de `ba` (inclusive) a `bb`.
    ba = -(-inicio // BLOCO)
    bb = fim // BLOCO
    tem_miolo = ba < bb
    # As pontas: da borda da coluna até o primeiro bloco inteiro, e do fim do
    # último bloco inteiro até a outra borda. Sem bloco inteiro, a coluna
    # toda é uma ponta só.
    esq_fim = np.where(tem_miolo, ba * BLOCO, fim)
    dir_ini = np.where(tem_miolo, bb * BLOCO, fim)

    def pontas(reduzir, neutro, segmentos):
        saida = np.full(inicio.size, neutro, dtype=np.float64)
        de, ate = segmentos
        comp = ate - de
        cheios = comp > 0
        if not cheios.any():
            return saida
        de, comp = de[cheios], comp[cheios]
        # Os índices de todas as amostras das pontas, um segmento atrás do
        # outro, e o começo de cada segmento dentro dessa lista.
        partida = np.concatenate(([0], np.cumsum(comp)[:-1]))
        indices = np.repeat(de - partida, comp) + np.arange(int(comp.sum()))
        saida[cheios] = reduzir.reduceat(np.asarray(x[indices], dtype=np.float64), partida)
        return saida

    def lado(reduzir, neutro, blocos):
        esq = pontas(reduzir, neutro, (inicio, esq_fim))
        dir_ = pontas(reduzir, neutro, (dir_ini, fim))
        # O miolo: `reduceat` sobre os blocos, com as bordas intercaladas
        # (ba₀, bb₀, ba₁, bb₁…) — só os pares (ba, bb) interessam.
        miolo = np.full(inicio.size, neutro, dtype=np.float64)
        if tem_miolo.any():
            pares = np.empty(2 * int(tem_miolo.sum()), dtype=np.int64)
            pares[0::2] = ba[tem_miolo]
            pares[1::2] = bb[tem_miolo]
            miolo[tem_miolo] = reduzir.reduceat(blocos, pares)[0::2]
        return reduzir(reduzir(esq, miolo), dir_)

    saida = np.empty(2 * inicio.size, dtype=np.float64)
    saida[0::2] = lado(np.minimum, np.inf, minimos_b[canal])
    saida[1::2] = lado(np.maximum, -np.inf, maximos_b[canal])
    return saida


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


def titulo_do_eixo(unidades: list[str]) -> str:
    """O que se escreve no alto de um eixo, dadas as unidades dos sinais nele.

    Uma unidade só, e conhecida: ela. Qualquer outra coisa — unidades
    diferentes, ou um sinal sem unidade no meio de grandezas conhecidas — é
    eixo AMBÍGUO, e eixo ambíguo não leva título: `kV` em cima de uma régua
    onde também passa um número puro afirmaria que o número é kV. A unidade
    fica então só na tabelinha, em cada linha (`—` para a que não tem).
    """
    distintas = set(unidades)
    if len(distintas) != 1:
        return ""
    return next(iter(distintas)) or ""


def titular_eixos(painel: dict) -> None:
    """Escreve `titulo_do_eixo` no painel e `titulo` no eixo da direita.

    Sai dos sinais que estão DESENHADOS em cada eixo, e por isso é refeito
    quando outro IED acrescenta sinais ao painel (`varios._juntar_analogico`).
    Painel vazio conserva a unidade que tinha — não há o que ser ambíguo.
    """
    sinais_ = painel.get("sinais") or []
    por_eixo = {"esq": [], "dir": []}
    for s in sinais_:
        por_eixo[s.get("eixo", "esq")].append(s.get("unidade") or "")
    painel["titulo_do_eixo"] = (titulo_do_eixo(por_eixo["esq"]) if por_eixo["esq"]
                                else painel.get("unidade") or "")
    if painel.get("eixo_dir"):
        painel["eixo_dir"]["titulo"] = titulo_do_eixo(por_eixo["dir"])


def arredondar(v: np.ndarray, intervalo: float) -> list[float]:
    """Corta casas decimais que não cabem na tela, para o JSON não inchar."""
    casas = escala.casas_decimais(intervalo) + 2
    # `tolist()` primeiro: o `round` do Python sobre `float` puro é o mesmo
    # número de sempre, sem o custo de um escalar do numpy por amostra (era a
    # maior conta de um pedido de janela depois que as do registro inteiro
    # passaram a ser lembradas). `x - x` só não é zero para NaN e infinito.
    return [round(x, casas) if x - x == 0 else None
            for x in np.asarray(v, dtype=np.float64).tolist()]
