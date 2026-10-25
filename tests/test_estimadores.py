"""Os estimadores do fasor tirados dos manuais: dois ciclos, meio ciclo e pico
a pico (`dsp/fasor.ESTIMADORES`).

Resposta conhecida, como nos outros testes de DSP: numa senoide pura os três
têm que dar o eficaz exato — e cada um tem que se comportar como o manual diz
diante da contínua e do atraso.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.dsp import envoltoria
from osclab.dsp import fasor as fasor_mod

F0 = 60.0


def _senoide(taxa: float, ciclos: float, eficaz: float = 10.0, fase: float = 30.0,
             dc: float = 0.0) -> np.ndarray:
    t = np.arange(int(taxa * ciclos / F0)) / taxa
    return (eficaz * math.sqrt(2) * np.cos(2 * np.pi * F0 * t + math.radians(fase))
            + dc)


@pytest.mark.parametrize("taxa", [1920.0, 2000.0])
@pytest.mark.parametrize("qual", ["dois_ciclos", "meio_ciclo", "pico_a_pico"])
def test_numa_senoide_pura_os_tres_dao_o_eficaz(taxa, qual):
    n = fasor_mod.ciclo_em_amostras(taxa, F0)
    x = _senoide(taxa, 8)
    with fasor_mod.usando(qual):
        curva = envoltoria.fundamental(x, n)
        f = fasor_mod.no_instante(x, x.size - 1, n)
    assert abs(curva[-1] - 10.0) < 0.05
    assert f is not None and abs(f.fundamental - 10.0) < 0.05
    # O cursor e a curva dão o mesmo número, como no Fourier.
    assert abs(curva[-1] - f.fundamental) < 1e-6


@pytest.mark.parametrize("qual", ["dois_ciclos", "meio_ciclo"])
def test_o_angulo_dos_que_sao_fasor_e_o_do_fourier_numa_senoide(qual):
    n = fasor_mod.ciclo_em_amostras(1920.0, F0)
    x = _senoide(1920.0, 8, fase=30.0)
    ref = fasor_mod.no_instante(x, x.size - 1, n)
    with fasor_mod.usando(qual):
        f = fasor_mod.no_instante(x, x.size - 1, n)
    assert abs(f.angulo - ref.angulo) < 0.05


def test_o_pico_a_pico_ignora_a_continua():
    """A média dos dois picos cancela a contínua: o «Peak-to-Peak» da ABB."""
    n = fasor_mod.ciclo_em_amostras(1920.0, F0)
    x = _senoide(1920.0, 6, dc=7.0)
    with fasor_mod.usando("pico_a_pico"):
        assert abs(envoltoria.fundamental(x, n)[-1] - 10.0) < 0.05


def test_dois_ciclos_atrasa_um_ciclo_e_meio_ciclo_adianta_meio():
    """Num degrau de 0 para 10 A, quantas amostras até passar de 90 %."""
    taxa = 1920.0
    n = int(fasor_mod.ciclo_em_amostras(taxa, F0))
    x = _senoide(taxa, 10)
    x[:4 * n] = 0.0

    def chegada(qual):
        with fasor_mod.usando(qual):
            curva = envoltoria.fundamental(x, n)
        return int(np.argmax(np.nan_to_num(curva) > 9.0)) - 4 * n

    um, dois, meio = chegada("fourier"), chegada("dois_ciclos"), chegada("meio_ciclo")
    assert dois - um == pytest.approx(n, abs=2)
    assert um - meio == pytest.approx(n / 2, abs=2)


def test_nome_desconhecido_continua_virando_fourier():
    assert set(fasor_mod.ESTIMADORES) >= {"fourier", "cosseno", "dois_ciclos",
                                          "meio_ciclo", "pico_a_pico"}
    with fasor_mod.usando("qualquer"):
        assert fasor_mod.estimador() == "fourier"
