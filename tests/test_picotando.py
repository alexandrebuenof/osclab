"""O digital que PICOTA: muda centenas de vezes até o fim do registro.

O caso que motivou: num SEL-411L a supervisão da reatância do quadrilateral
de terra (ENX2AG/BG/CG) muda 400+ vezes num registro de 3 s, o tempo todo
depois da abertura (12/11/2026). O critério é de comportamento, nunca de
nome — por isso os nomes aqui são de propósito neutros ou de proteção.
"""

from __future__ import annotations

import numpy as np

from osclab.formats.base import Record, SampleRate, StatusChannel
from osclab.plot import digitais, janela, paineis

TAXA = 2000.0
N = 6000  # 3 s, como o registro que motivou


def _registro(linhas: dict[str, np.ndarray], sem_placa=frozenset()) -> Record:
    nomes = list(linhas)
    return Record(
        source=None, format_name="teste",
        status_channels=tuple(StatusChannel(index=i, name=n) for i, n in enumerate(nomes)),
        sample_rates=(SampleRate(rate_hz=TAXA, last_sample=N),),
        status=np.vstack([linhas[n] for n in nomes]).astype(np.int8),
        time=np.arange(N) / TAXA, digitais_sem_placa=frozenset(sem_placa))


def _degrau(*bordas: int) -> np.ndarray:
    """Liga e desliga nas amostras dadas (cada borda é uma transição)."""
    x = np.zeros(N, dtype=np.int8)
    for k, b in enumerate(bordas):
        x[b:] = (k + 1) % 2
    return x


def _picotando(inicio: int, periodo: int, fim: int = N) -> np.ndarray:
    x = np.zeros(N, dtype=np.int8)
    trecho = np.arange(fim - inicio)
    x[inicio:fim] = ((trecho // periodo) % 2).astype(np.int8)
    return x


def _casos() -> Record:
    return _registro({
        "TRIP": _degrau(200, 520),                                   # 2 transições
        "79CY": _degrau(600, 900, 1500, 1520, 2100, 2400),             # religamento, 6
        "PULSO": _degrau(N - 3, N - 1),                              # pulso no fim
        "ENX": _picotando(170, 6),                                   # ~970 transições
        "RAJADA": _picotando(200, 3, fim=1400),                      # 400, e para
        "MEDIO": _degrau(*range(4600, 6000, 70)),                    # 20: no limite
        "PARADO": np.zeros(N, dtype=np.int8),
    })


def test_conta_as_transicoes_sem_percorrer_amostra():
    por_nome = {r.nome: r for r in digitais.resumos(_casos())}
    assert por_nome["TRIP"].mudancas == 2
    assert por_nome["79CY"].mudancas == 6
    assert por_nome["PULSO"].mudancas == 2
    assert por_nome["PARADO"].mudancas == 0 and not por_nome["PARADO"].mudou
    assert por_nome["ENX"].mudancas > 900
    assert por_nome["TRIP"].amostra == 200


def test_so_o_que_muda_demais_ate_o_fim_picota():
    por_nome = {r.nome: r for r in digitais.resumos(_casos())}
    assert por_nome["ENX"].picota
    # Trip, religamento e pulso no fim nunca picotam — poucas transições.
    for nome in ("TRIP", "79CY", "PULSO", "PARADO"):
        assert not por_nome[nome].picota, nome
    # Muitas, mas parou no meio do registro: é parte do evento.
    assert por_nome["RAJADA"].mudancas > digitais.PICOTA_MUDANCAS
    assert not por_nome["RAJADA"].picota
    # Exatamente no limite não picota: o critério é «mais de».
    assert por_nome["MEDIO"].mudancas == digitais.PICOTA_MUDANCAS
    assert not por_nome["MEDIO"].picota


def test_o_picotando_sai_do_padrao_e_fica_na_busca():
    registro = _casos()
    nomes = {r.indice: r.nome for r in digitais.resumos(registro)}
    padrao = [nomes[k] for k in digitais.escolhidos_por_padrao(registro)]
    assert "ENX" not in padrao
    assert {"TRIP", "79CY", "PULSO", "RAJADA", "MEDIO"} <= set(padrao)
    digital = [p for p in paineis.padrao(registro)
               if p.tipo == paineis.DIGITAL][0]
    assert str(next(k for k, n in nomes.items() if n == "ENX")) not in digital.sinais


def test_o_pacote_manda_a_contagem_e_a_marca():
    pacote = janela.montar(_casos(), colunas=400)
    por_nome = {d["nome"]: d for d in pacote["digitais_disponiveis"]}
    assert por_nome["ENX"]["picota"] and por_nome["ENX"]["mudancas"] > 900
    assert not por_nome["TRIP"]["picota"] and por_nome["TRIP"]["mudancas"] == 2
    assert pacote["digitais_picotando"] == 1
    # «mudaram» é o que entra sozinho na tela: o picotando não conta ali.
    assert pacote["digitais_mudaram"] == 5


def test_sem_placa_vence_picotando():
    """O contador do 487E sem placa picota, mas a razão dele é outra."""
    registro = _registro({"IN317": _picotando(0, 1), "TRIP": _degrau(100, 300)},
                         sem_placa={"IN317"})
    r = {x.nome: x for x in digitais.resumos(registro)}["IN317"]
    assert r.sem_placa and not r.picota


def test_picota_decide_pelo_fim_do_registro():
    assert digitais.picota(21, 0.76, 0.0, 1.0)
    assert not digitais.picota(21, 0.74, 0.0, 1.0)
    assert not digitais.picota(20, 1.0, 0.0, 1.0)
    assert not digitais.picota(5000, None, 0.0, 1.0)
    # O início não é zero num registro real: a fração é da DURAÇÃO.
    assert digitais.picota(300, 10.8, 10.0, 11.0)
    assert not digitais.picota(300, 10.7, 10.0, 11.0)
