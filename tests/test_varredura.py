"""Os detectores contra o evento em QUALQUER posição do registro.

A lição do CLAUDE.md («A falta vem ANTES do disparo, e todo sintético a
injetava depois»): um detector que depende de ONDE o evento está tem de ser
testado com o evento varrido pelo registro inteiro — no começo, antes, em
cima e depois do disparo, perto do fim —, e com as formas de taxa que os
arquivos reais têm (uma só, várias, `nrates = 0`). Um sintético com a falta
sempre no mesmo lugar confirma a suposição de quem o escreveu.
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pytest

from osclab.analysis import falta
from osclab.formats.base import AnalogChannel, Record, SampleRate, StatusChannel
from osclab.plot import imas

F0 = 60.0
CICLO = 1.0 / F0
DURACAO = 0.5
VN, CARGA, FALTA_A = 7967.0, 180.0, 3000.0
CANAIS_V = {"A": 0, "B": 1, "C": 2}
CANAIS_I = {"A": 3, "B": 4, "C": 5}


def _instantes(trechos: list[tuple[float, float]]) -> tuple[np.ndarray, list[SampleRate]]:
    """`[(taxa, até_t), …]` → vetor de tempo e as `SampleRate` (base 1)."""
    partes, taxas, t0, n = [], [], 0.0, 0
    for taxa, ate in trechos:
        t = np.arange(t0, ate - 1e-12, 1.0 / taxa)
        partes.append(t)
        n += t.size
        taxas.append(SampleRate(rate_hz=taxa, last_sample=n))
        t0 = t[-1] + 1.0 / taxa
    return np.concatenate(partes), taxas


def _registro(t_falta: float | None, *, dur: float = 0.1, t_trip: float | None = None,
              trechos=((1920.0, DURACAO),), sem_taxa: bool = False) -> Record:
    """VA VB VC IA IB IC e um TRIP. Falta AG de `dur` s a partir de `t_falta`
    (antes de 0 = o registro já começa dentro dela); depois, o disjuntor abre."""
    t, taxas = _instantes(list(trechos))
    w = 2 * math.pi * F0
    na_falta = (np.zeros(t.size, bool) if t_falta is None
                else (t >= t_falta) & (t < t_falta + dur))
    aberto = np.zeros(t.size, bool) if t_falta is None else t >= t_falta + dur
    dados = np.zeros((6, t.size))
    for k, desloc in enumerate((0.0, -2 * math.pi / 3, 2 * math.pi / 3)):
        v = VN * math.sqrt(2) * np.sin(w * t + desloc)
        i = CARGA * math.sqrt(2) * np.sin(w * t + desloc - math.radians(18))
        if k == 0:
            v = np.where(na_falta, 0.45 * v, v)
            i = np.where(na_falta, FALTA_A * math.sqrt(2) * np.sin(w * t - math.radians(78)), i)
        dados[k], dados[3 + k] = v, np.where(aberto, 0.003 * i, i)
    trip = np.zeros(t.size, np.int8)
    if t_trip is not None:
        trip[t >= t_trip] = 1
    canais = tuple(AnalogChannel(index=i, name=n, phase=f, unit=u, scaling="P")
                   for i, (n, f, u) in enumerate([("VA", "A", "V"), ("VB", "B", "V"),
                                                  ("VC", "C", "V"), ("IA", "A", "A"),
                                                  ("IB", "B", "A"), ("IC", "C", "A")]))
    if sem_taxa:
        taxas = [SampleRate(rate_hz=0.0, last_sample=t.size)]
    return Record(source=None, format_name="teste", station="SE TESTE", line_frequency=F0,
                  start_time=datetime(2026, 10, 25, 12, 0, 0), analog_channels=canais,
                  status_channels=(StatusChannel(index=0, name="TRIP"),),
                  sample_rates=tuple(taxas), analog=dados, status=trip[None, :], time=t)


def _amostra(r: Record, t: float) -> int:
    return int(np.argmin(np.abs(r.time - t)))


def _em_ciclos(r: Record, n: int | None, t: float) -> float:
    return math.inf if n is None else abs(r.time[n] - t) / CICLO


#: 0,03 s = 1,8 ciclo de pré-falta: o detector tira o piso de ruído do 2.º
#: ciclo e começa a busca no 3.º, então uma falta ali enche o próprio piso e
#: some. Corrigir mexe no caso «registro que já começa num transitório», que
#: está em aberto com o Alexandre (25/10/2026) — medido no banco: piso pela
#: mediana pega esta falta, mas muda 23 registros reais e piora dois contra o
#: tipo que o relé escreveu. Fica documentado até a decisão.
PRECOCE = pytest.param(0.03, marks=pytest.mark.xfail(
    strict=True, reason="falta entre 1 e 2 ciclos do começo: ver «falta já em curso»"))
POSICOES = [PRECOCE, 0.08, 0.15, 0.25, 0.33]


@pytest.mark.parametrize("t_falta", POSICOES)
@pytest.mark.parametrize("onde_trip", ["depois", "antes", "nenhum"])
def test_a_falta_e_achada_onde_estiver_e_o_disparo_nao_influi(t_falta, onde_trip):
    """O disparo vem DEPOIS da falta (o normal), ANTES (outro evento) ou nem
    vem: o início e o tipo não podem depender disso."""
    t_trip = {"depois": t_falta + 0.035, "antes": t_falta - 0.02, "nenhum": None}[onde_trip]
    r = _registro(t_falta, t_trip=t_trip)
    v = falta.classificar(r, CANAIS_I, CANAIS_V)
    assert v.tipo == "AG", (t_falta, onde_trip, v.porques)
    assert _em_ciclos(r, v.instante, t_falta) < 0.5
    assert _em_ciclos(r, v.fim, t_falta + 0.1) < 2.0
    n = imas.inicio_da_perturbacao(r)
    assert n is not None and _em_ciclos(r, n, t_falta) < 1.0


def test_falta_perto_do_fim_sem_abertura_ainda_classifica():
    r = _registro(DURACAO - 0.06, dur=1.0)
    v = falta.classificar(r, CANAIS_I, CANAIS_V)
    assert v.tipo == "AG" and v.fim is None


def test_registro_so_de_carga_nao_inventa_falta_em_posicao_nenhuma():
    r = _registro(None, t_trip=0.2)
    assert falta.classificar(r, CANAIS_I, CANAIS_V).tipo == ""


def test_registro_que_comeca_dentro_da_falta_nao_inventa_tipo_errado():
    """Sem pré-falta não há descontinuidade de entrada. O detector pode não
    achar nada — o que ele não pode é dizer um tipo que não é o da falta.
    (Achar a falta já em curso é a pendência «falta já em curso».)"""
    r = _registro(-0.05, dur=0.2, t_trip=0.02)
    v = falta.classificar(r, CANAIS_I, CANAIS_V)
    assert v.tipo in ("", "AG"), v.porques


@pytest.mark.parametrize("t_falta", POSICOES)
def test_sem_taxa_declarada_a_falta_e_achada_igual(t_falta):
    """`nrates = 0` (SEL-751, 311C): a taxa sai do vetor de tempo."""
    r = _registro(t_falta, t_trip=t_falta + 0.035, sem_taxa=True)
    v = falta.classificar(r, CANAIS_I, CANAIS_V)
    assert v.tipo == "AG" and _em_ciclos(r, v.instante, t_falta) < 0.5


@pytest.mark.parametrize("t_falta", [0.15, 0.25, 0.33])
def test_taxa_multipla_falta_no_trecho_rapido(t_falta):
    """O relé grava a falta a 96/ciclo e o resto a 16. Aqui: 960 Hz até 0,1 s
    e 1920 Hz depois, com a falta inteira no trecho de 1920 Hz."""
    r = _registro(t_falta, t_trip=t_falta + 0.035,
                  trechos=((960.0, 0.1), (1920.0, DURACAO)))
    v = falta.classificar(r, CANAIS_I, CANAIS_V)
    assert v.tipo == "AG", v.porques
    assert _em_ciclos(r, v.instante, t_falta) < 0.5
