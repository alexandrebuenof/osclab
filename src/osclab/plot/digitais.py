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

## O digital que PICOTA (12/11/2026)

Um SEL-411L grava a supervisão da reatância do quadrilateral de terra
(`ENX2AG`, `ENX2BG`, `ENX2CG`), e ela liga e desliga mais de 400 vezes num
registro de 3 s — o tempo todo depois da abertura. Na tela padrão isso é
uma faixa listrada que não conta nada sobre o evento e tira o olho do trip.

O critério é de COMPORTAMENTO, nunca de nome nem de fabricante: mais de
`PICOTA_MUDANCAS` transições E ainda mudando no último quarto do registro
(`PICOTA_FIM`). Medido nos registros reais de teste (sete fabricantes): 98 %
dos digitais que mudam mudam até 6 vezes; o sinal de proteção de verdade que
mais mudou foi o bloqueio por harmônico do 87 numa energização (51
transições, até o fim de um registro de 1 s). As supervisões que picotam vão
de 415 a 486, e o fator de potência adiantado/atrasado da medição
(`LD_DPF*`, `LG_DPF*`) de 32 a 42. Daí 20 (decidido pelo Alexandre em
12/11/2026): o dobro do maior trip/52/79/partida (10), abaixo do fator de
potência — e o bloqueio por harmônico do 87 numa energização vai junto para
o «+ sinal», de propósito. O picotando não some: fica no «+ sinal», num bloco próprio, com
o número de mudanças ao lado.
"""

from __future__ import annotations

import threading
import weakref
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
    #: O relé grava este canal, mas a placa dele não tem esta entrada/saída
    #: (`Record.digitais_sem_placa`). O que muda ali não é sinal de nada.
    sem_placa: bool = False
    #: Quantas vezes o canal mudou de estado no registro inteiro.
    mudancas: int = 0
    #: Muda o tempo todo, até o fim do registro (ver `picota`). Fica fora da
    #: tela padrão e vai para o bloco «picotando» do «+ sinal».
    picota: bool = False


#: Acima de quantas transições um digital pode estar picotando. Ver o
#: cabeçalho do módulo para a medição que deu este número.
PICOTA_MUDANCAS = 20
#: E a última transição tem que cair depois desta fração da duração: quem
#: picotou só durante a falta e parou faz parte da história dela.
PICOTA_FIM = 0.75


def picota(mudancas: int, ultima: float | None, inicio: float, fim: float) -> bool:
    """O digital muda demais E continua mudando até o fim do registro?

    `ultima` é o instante da última transição; `inicio` e `fim`, os do
    registro. As duas condições juntas: muitas mudanças que pararam no meio
    são um evento, e poucas até o fim também.
    """
    if mudancas <= PICOTA_MUDANCAS or ultima is None or fim <= inicio:
        return False
    return ultima >= inicio + PICOTA_FIM * (fim - inicio)


def _transicoes(dados: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Por canal: quantas transições, a amostra da primeira e a da última.

    Tudo de uma vez sobre a matriz, sem percorrer amostra. Canal parado tem
    contagem 0 e as duas amostras -1.
    """
    linhas = dados.shape[0] if dados.ndim == 2 else 0
    if linhas == 0 or dados.shape[1] < 2:
        vazio = np.zeros(linhas, dtype=np.int64)
        return vazio, vazio - 1, vazio - 1
    muda = dados[:, 1:] != dados[:, :-1]
    contagem = muda.sum(axis=1).astype(np.int64)
    # `+1`: `muda[k]` compara `k` com `k+1`, e a mudança acontece em `k+1`.
    primeira = np.argmax(muda, axis=1) + 1
    ultima = muda.shape[1] - np.argmax(muda[:, ::-1], axis=1)
    parado = contagem == 0
    primeira[parado] = -1
    ultima[parado] = -1
    return contagem, primeira, ultima


#: `resumos` já feitos, por registro aberto:
#: `id → (referência fraca, impressão, resumos)`. A referência fraca solta a
#: entrada junto com o registro — o servidor não segura registro nenhum por
#: causa disto (ver `acervo.ler`). A impressão (`_impressao`) refaz a conta
#: se alguém trocou a matriz, o tempo ou os canais do objeto.
_FEITOS: dict[int, tuple[weakref.ref, tuple, tuple[Resumo, ...]]] = {}
_TRAVA_DOS_FEITOS = threading.Lock()


def resumos(registro: Record) -> tuple[Resumo, ...]:
    """Todos os digitais, os que mudaram primeiro.

    A ordenação põe na frente quem mudou, por instante; depois os parados, na
    ordem do arquivo. Assim a lista serve às duas coisas: desenhar o começo dela
    e buscar dentro dela inteira.

    **Feito uma vez por registro aberto** (12/11/2026). O resumo é do registro
    INTEIRO e não depende da janela, mas era refeito a cada pedido de janela —
    a cada entalhe da roda e a cada arrasto. Num SEL-411L com 3968 digitais e
    6000 amostras, `_transicoes` (dois `argmax` sobre a matriz inteira) eram
    0,95 s dos 1,15 s do pedido; com duas oscilografias na aba (o painel
    localizador), o dobro. A roda que pede uma janela a cada 70 ms com o
    servidor levando 2 s por resposta é a roda «quebrada» do localizador. O
    registro que `acervo.ler` entrega é o mesmo objeto enquanto a pasta não
    muda, e ninguém pode alterá-lo — então guardar pelo objeto é seguro.
    """
    chave, impressao = id(registro), _impressao(registro)
    with _TRAVA_DOS_FEITOS:
        achado = _FEITOS.get(chave)
        if achado is not None and achado[0]() is registro and achado[1] == impressao:
            return achado[2]
    feitos = _resumos(registro)
    try:
        ref = weakref.ref(registro, lambda _r, k=chave: _FEITOS.pop(k, None))
    except TypeError:            # objeto sem referência fraca: só não se guarda
        return feitos
    with _TRAVA_DOS_FEITOS:
        _FEITOS[chave] = (ref, impressao, feitos)
    return feitos


def _impressao(registro: Record) -> tuple:
    dados, tempo = registro.status, registro.time
    return (id(dados), getattr(dados, "shape", None), id(tempo), getattr(tempo, "shape", None),
            id(registro.status_channels),
            frozenset(getattr(registro, "digitais_sem_placa", None) or ()))


def _resumos(registro: Record) -> tuple[Resumo, ...]:
    dados = registro.status
    tempo = registro.time
    saida: list[Resumo] = []
    sem_placa = getattr(registro, "digitais_sem_placa", frozenset())
    contagem, primeiras, ultimas = _transicoes(dados)
    inicio = float(tempo[0]) if tempo.size else 0.0
    fim = float(tempo[-1]) if tempo.size else 0.0

    for canal in registro.status_channels:
        k = canal.index
        tem = k < contagem.size
        mudancas = int(contagem[k]) if tem else 0
        amostra = int(primeiras[k]) if mudancas else None
        ultima = int(ultimas[k]) if mudancas else None
        fora_da_placa = canal.name in sem_placa
        instante_ultima = (float(tempo[ultima]) if ultima is not None
                           and ultima < tempo.size else None)
        saida.append(Resumo(
            indice=k,
            nome=canal.name,
            mudou=amostra is not None,
            amostra=amostra,
            instante=float(tempo[amostra]) if amostra is not None
            and amostra < tempo.size else None,
            inicial=int(dados[k, 0]) if tem and dados.shape[1] else 0,
            sem_placa=fora_da_placa,
            mudancas=mudancas,
            picota=not fora_da_placa and picota(mudancas, instante_ultima,
                                                inicio, fim),
        ))

    # `not r.mudou` primeiro: `False` ordena antes de `True`, então quem mudou
    # sobe. O índice desempata e mantém a ordem do arquivo entre os parados.
    return tuple(sorted(saida, key=lambda r: (not r.mudou,
                                              r.instante if r.instante is not None
                                              else float("inf"),
                                              r.indice)))


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

    A única exceção são os digitais que a placa do relé NÃO TEM
    (`Resumo.sem_placa`): o 487E grava IN317–IN324 sem placa para eles, e um
    contador de amostras pisca nesses bits. Não é sinal — fica de fora, e a
    busca os mostra marcados.

    A segunda são os que PICOTAM (`Resumo.picota`, 12/11/2026): mudam
    centenas de vezes até o fim do registro. Vão para o bloco «picotando» do
    «+ sinal», com o número de mudanças ao lado.
    """
    escolhidos = [r.indice for r in resumos(registro)
                  if r.mudou and not r.sem_placa and not r.picota]
    return escolhidos if limite is None else escolhidos[:limite]
