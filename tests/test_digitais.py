"""Os canais digitais: o que entra na tela, em que ordem, e o que não some.

O teste que mais importa aqui é o do **pulso estreito**. Num registro de 500 mil
amostras reduzido para 900 colunas, um trip de duas amostras tem uma chance em
550 de sobreviver a uma redução ingênua — e um trip que sumiu da tela é o pior
defeito que um leitor de oscilografia pode ter.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from osclab.formats.base import Record, StatusChannel
from osclab.plot import digitais


def registro(*linhas: list[int], nomes: list[str] | None = None) -> Record:
    n = len(linhas[0]) if linhas else 0
    r = Record(source=Path("sintetico"), format_name="teste")
    r.status = np.array(linhas, dtype=np.int8)
    r.status_channels = tuple(
        StatusChannel(index=i, name=(nomes or [f"D{i + 1}" for i in range(len(linhas))])[i])
        for i in range(len(linhas))
    )
    r.time = np.arange(n) / 1200.0
    r.analog = np.zeros((0, n))
    return r


# ---------------------------------------------------------------------------
# Quem entra na tela
# ---------------------------------------------------------------------------

def test_so_entram_os_que_mudaram():
    """Um SEL-487E tem 5760 digitais. Digital parado o registro inteiro não
    conta nada sobre o evento — e era por falta deste critério que este marco
    ficou parado."""
    r = registro([0, 0, 0, 0], [0, 0, 1, 1], [1, 1, 1, 1])
    assert digitais.escolhidos_por_padrao(r) == [1]


def test_a_ordem_conta_a_historia_do_evento():
    """De cima para baixo, a sequência: partida, trip, abertura. A ordem do
    arquivo é a ordem em que alguém configurou o relé, e não diz nada."""
    r = registro(
        [0, 0, 0, 0, 0, 1],        # D1 muda por último
        [0, 1, 1, 1, 1, 1],        # D2 muda primeiro
        [0, 0, 0, 1, 1, 1],        # D3 no meio
        nomes=["ULTIMO", "PRIMEIRO", "MEIO"],
    )
    assert [x.nome for x in digitais.resumos(r)] == ["PRIMEIRO", "MEIO", "ULTIMO"]


def test_os_parados_ficam_no_fim_e_continuam_na_lista():
    """Escondido não é o mesmo que inexistente: num laudo, às vezes o que
    importa é provar que um sinal NÃO mudou."""
    r = registro([1, 1, 1, 1], [0, 0, 1, 1], nomes=["PARADO", "MUDOU"])
    achados = digitais.resumos(r)
    assert [x.nome for x in achados] == ["MUDOU", "PARADO"]
    assert achados[1].mudou is False
    assert achados[1].instante is None
    assert achados[1].inicial == 1        # começou em 1, e o laudo pode querer isso


def test_a_primeira_mudanca_aponta_a_amostra_CERTA():
    """`diff[k]` compara `k` com `k+1`; a mudança acontece em `k+1`. Errar esse
    `+1` desloca a ordem do evento em uma amostra e ninguém percebe."""
    r = registro([0, 0, 0, 1, 1])
    assert digitais.resumos(r)[0].amostra == 3


def test_por_padrao_nao_ha_limite_nenhum():
    """Todos os que mudaram entram. Um evento com quarenta digitais mexendo é
    um evento com quarenta digitais mexendo, e a tela tem que mostrá-lo
    inteiro: cortar nos primeiros N esconderia o religamento e o segundo
    trip, que são o fim da história."""
    linhas = [[i % 2 for i in range(40)] for _ in range(50)]
    assert len(digitais.escolhidos_por_padrao(registro(*linhas))) == 50


def test_o_limite_continua_a_um_argumento_de_distancia():
    """Para o registro esquisito — ruído em entrada binária — o corte existe.
    Quem o usar tem que dizer na tela quantos ficaram de fora."""
    linhas = [[i % 2 for i in range(40)] for _ in range(50)]
    assert len(digitais.escolhidos_por_padrao(registro(*linhas), limite=24)) == 24


def test_registro_sem_digital_nenhum_nao_quebra():
    r = Record(source=Path("x"), format_name="teste")
    r.time = np.arange(10) / 1200.0
    assert digitais.resumos(r) == ()
    assert digitais.escolhidos_por_padrao(r) == []
    assert digitais.tiras(r, 0, 10, 900, [0]) == []


# ---------------------------------------------------------------------------
# Reduzir sem perder o pulso
# ---------------------------------------------------------------------------

def test_um_pulso_de_duas_amostras_sobrevive_a_reducao():
    """O teste que justifica o módulo inteiro.

    50 mil amostras em 200 colunas: cada coluna cobre 250 amostras. Guardando
    o valor do meio, um pulso de duas amostras teria uma chance em 125 de
    aparecer. Guardando o MÁXIMO, ele sempre aparece — mais largo do que é, e
    isso é o certo.
    """
    linha = [0] * 50_000
    linha[31_000] = linha[31_001] = 1
    tira = digitais.tiras(registro(linha), 0, 50_000, 200, [0])[0]

    assert sum(tira["ligado"]) >= 1
    # E cai na coluna certa: 31 000 de 50 000 é 62 % do caminho.
    coluna = tira["ligado"].index(1)
    assert 0.60 < coluna / len(tira["ligado"]) < 0.64


def test_a_transicao_dentro_da_coluna_se_declara():
    """A tela precisa saber onde houve os dois estados na mesma coluna para
    não desenhar um degrau que não existe."""
    # A transição em 103 cai DENTRO da coluna que cobre 100..109. Pô-la em 100
    # exato faria a troca coincidir com a borda da coluna, e nenhuma coluna
    # teria os dois estados — o teste passaria a não testar nada.
    linha = [0] * 103 + [1] * 97
    tira = digitais.tiras(registro(linha), 0, 200, 20, [0])[0]
    assert any(tira["transicao"])


def test_sem_reducao_a_tira_e_a_propria_amostra():
    linha = [0, 1, 1, 0]
    tira = digitais.tiras(registro(linha), 0, 4, 900, [0])[0]
    assert tira["ligado"] == [0, 1, 1, 0]


def test_o_tempo_das_colunas_acompanha_as_tiras():
    """A tela desenha cada coluna no instante que o servidor mandou. Adivinhar
    por fração daria certo só com taxa de amostragem constante."""
    r = registro([0, 1] * 500)
    tira = digitais.tiras(r, 0, 1000, 137, [0])[0]
    tempo = digitais.tempo_das_colunas(r, 0, 1000, 137)
    assert len(tempo) == len(tira["ligado"])
    assert tempo == sorted(tempo)


def test_canal_pedido_que_nao_existe_e_ignorado_em_silencio():
    """A tela manda índices; o servidor não confia neles."""
    assert digitais.tiras(registro([0, 1]), 0, 2, 900, [0, 99, -3]) != []
    assert len(digitais.tiras(registro([0, 1]), 0, 2, 900, [0, 99, -3])) == 1
