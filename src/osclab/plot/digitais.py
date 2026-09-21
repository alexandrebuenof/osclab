"""Os canais digitais: quais mostrar, em que ordem, e como reduzi-los.

## Por que este módulo existe

Um SEL-487E grava **5760 canais digitais**. Mostrar todos é impossível e
mostrar os primeiros N é arbitrário. Foi por isso que este marco ficou parado:
faltava um critério, e qualquer critério inventado seria pior que nenhum.

O critério é o do ofício: **só interessa o que mudou.** Um digital parado o
registro inteiro não conta nada sobre o evento — o disjuntor estava fechado
antes e continuou fechado, a função estava habilitada e continuou. Num evento
real mudam algumas dezenas, e essas são exatamente as que se quer ver.

Os parados não somem do programa: eles ficam disponíveis para busca, e o
usuário acrescenta na tela o que precisar conferir. Escondido não é o mesmo que
inexistente — num laudo, às vezes o que importa é provar que um sinal **não**
mudou.

## A ordem conta a história

Ordenados pelo **instante da primeira mudança**, de cima para baixo, a tela lê
como a sequência do evento: partida, trip, abertura do disjuntor, religamento.
A ordem do arquivo é a ordem em que alguém configurou o relé, e não tem relação
nenhuma com o que aconteceu.

## Reduzir digital não é reduzir analógico

Num analógico, a coluna de pixel guarda mínimo e máximo para o pico não sumir.
Num digital o risco é o mesmo com outra cara: **um pulso de duas amostras no
meio de um registro de 500 mil**. Guardando o máximo da coluna, um pulso
estreito continua marcando a coluna inteira — fica mais largo do que é, e isso
é o certo: some se fosse fiel à largura, e um trip que sumiu da tela é pior que
um trip gordo demais.

O mínimo vai junto para a tela saber onde houve **transição dentro da coluna** e
não desenhar um degrau que não existe.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from osclab.formats.base import Record


@dataclass(frozen=True)
class Resumo:
    """O que se sabe de um canal digital antes de desenhar qualquer coisa."""

    indice: int
    nome: str
    #: Mudou de estado em algum momento do registro?
    mudou: bool
    #: Índice da amostra da primeira mudança, ou `None`.
    amostra: int | None
    #: O instante dela em segundos, ou `None`. É por ele que se ordena.
    instante: float | None
    #: Como o canal começou o registro: 0 ou 1.
    inicial: int


def resumos(registro: Record) -> tuple[Resumo, ...]:
    """Todos os digitais, os que mudaram primeiro.

    A ordenação põe na frente quem mudou, por instante; depois os parados, na
    ordem do arquivo. Assim a lista serve às duas coisas: desenhar o começo dela
    e buscar dentro dela inteira.
    """
    dados = registro.status
    tempo = registro.time
    saida: list[Resumo] = []

    for canal in registro.status_channels:
        linha = dados[canal.index] if canal.index < dados.shape[0] else np.empty(0)
        amostra = _primeira_mudanca(linha)
        saida.append(Resumo(
            indice=canal.index,
            nome=canal.name,
            mudou=amostra is not None,
            amostra=amostra,
            instante=float(tempo[amostra]) if amostra is not None
            and amostra < tempo.size else None,
            inicial=int(linha[0]) if linha.size else 0,
        ))

    # `not r.mudou` primeiro: `False` ordena antes de `True`, então quem mudou
    # sobe. O índice desempata e mantém a ordem do arquivo entre os parados.
    return tuple(sorted(saida, key=lambda r: (not r.mudou,
                                              r.instante if r.instante is not None
                                              else float("inf"),
                                              r.indice)))


def _primeira_mudanca(linha: np.ndarray) -> int | None:
    """Índice da amostra em que o canal mudou pela primeira vez, ou `None`."""
    if linha.size < 2:
        return None
    diferentes = np.flatnonzero(np.diff(linha.astype(np.int16)) != 0)
    # `+1`: `diff[k]` compara `k` com `k+1`, e a mudança acontece em `k+1`.
    return int(diferentes[0]) + 1 if diferentes.size else None


def _fatias(n: int, colunas: int) -> np.ndarray:
    return np.unique(np.floor(np.linspace(0, n, colunas + 1)[:-1]).astype(np.int64))


def tempo_das_colunas(registro: Record, i0: int, i1: int,
                      colunas: int) -> list[float]:
    """O instante em que cada coluna de pixel começa.

    Vai junto com as tiras para a tela não ter que adivinhar onde cada coluna
    cai no eixo. Adivinhar por fração daria certo só enquanto a taxa de
    amostragem fosse constante — e ela não é, num registro de taxa múltipla.
    """
    if i1 <= i0:
        return []
    inicios = _fatias(i1 - i0, max(colunas, 1))
    return [round(float(registro.time[i0 + int(k)]), 9) for k in inicios]


def tiras(registro: Record, i0: int, i1: int, colunas: int,
          indices: list[int]) -> list[dict]:
    """As tiras prontas para desenhar, na ordem em que `indices` vier.

    Cada coluna de pixel devolve `ligado` (houve 1 ali dentro) e `mudou` (houve
    os dois estados na mesma coluna). Ver o cabeçalho para por que o máximo, e
    não a amostra do meio.
    """
    dados = registro.status
    saida: list[dict] = []
    if dados.size == 0 or i1 <= i0:
        return saida

    nomes = {c.index: c.name for c in registro.status_channels}
    for indice in indices:
        if not (0 <= indice < dados.shape[0]):
            continue
        pedaco = dados[indice, i0:i1].astype(np.int16)
        inicios = _fatias(pedaco.size, max(colunas, 1))
        if pedaco.size <= inicios.size:
            ligado, minimo = pedaco, pedaco
        else:
            ligado = np.maximum.reduceat(pedaco, inicios)
            minimo = np.minimum.reduceat(pedaco, inicios)

        saida.append({
            "indice": indice,
            "nome": nomes.get(indice, f"D{indice + 1}"),
            "ligado": [int(v) for v in ligado],
            "transicao": [bool(a != b) for a, b in zip(ligado, minimo, strict=True)],
        })
    return saida


def escolhidos_por_padrao(registro: Record, limite: int | None = None) -> list[int]:
    """Os digitais que aparecem sozinhos ao abrir: **todos** os que mudaram.

    Sem corte por padrão, e isso é escolha, não descuido: quem abre uma
    oscilografia quer a sequência inteira do evento na tela. Cortar nos
    primeiros N esconderia justamente o que veio depois — o religamento, o
    rearme, o segundo trip — e esconder sem dizer é o que este programa não
    faz.

    `limite` continua existindo para um registro esquisito (um relé com ruído
    em entrada binária pode ter centenas mudando). Quem o usar tem que dizer
    na tela quantos ficaram de fora.
    """
    escolhidos = [r.indice for r in resumos(registro) if r.mudou]
    return escolhidos if limite is None else escolhidos[:limite]
