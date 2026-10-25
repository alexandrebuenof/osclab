"""O estimador cosseno da SEL, ao lado do Fourier de um ciclo.

O que se prende aqui, com resposta conhecida:

* numa senoide pura os dois dão o MESMO fasor — módulo e ângulo — inclusive
  com taxa que não fecha número inteiro de amostras por ciclo (a quadratura cai
  entre duas amostras);
* com a exponencial decrescente da falta, o cosseno erra MENOS que o Fourier —
  é a razão de ele existir;
* o primeiro fasor válido sai em 1,25 ciclo, e não em 1;
* o cursor e a curva dão o mesmo número com o cosseno, como com o Fourier;
* fora de `usando` vale o Fourier, e nome desconhecido vira Fourier.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.dsp import envoltoria, fasor

F0 = 60.0


def _senoide(por_ciclo: float, ciclos: float = 6.0, amplitude: float = 100.0,
             fase: float = 0.4) -> tuple[np.ndarray, np.ndarray]:
    n = int(ciclos * por_ciclo)
    k = np.arange(n, dtype=np.float64)
    teta = 2 * math.pi * k / por_ciclo + fase
    return amplitude * np.cos(teta), teta


@pytest.mark.parametrize("por_ciclo", [8.0, 16.0, 20.0, 33.333333333333336])
def test_na_senoide_pura_cosseno_e_fourier_dao_o_mesmo_fasor(por_ciclo):
    x, teta = _senoide(por_ciclo)
    with fasor.usando("cosseno"):
        c = envoltoria.fasores(x, por_ciclo)
    f = envoltoria.fasores(x, por_ciclo)
    validos = np.isfinite(c)
    assert validos.sum() > 3 * por_ciclo
    # Com taxa que fecha, exato; a 33,3 por ciclo sobra o 0,003 % que a
    # janela de um ciclo de TEMPO já tem no Fourier (ver `pesos_do_ciclo`).
    tolerancia = 1e-6 if float(por_ciclo).is_integer() else 5e-3
    assert np.max(np.abs(np.abs(c[validos]) - 100.0)) < tolerancia
    assert np.max(np.abs(c[validos] - f[validos])) < 2 * tolerancia
    # O ângulo é o do instante de cada amostra, como no Fourier.
    erro = np.angle(c[validos] * np.exp(-1j * teta[validos]))
    assert np.max(np.abs(erro)) < tolerancia / 100


@pytest.mark.parametrize("por_ciclo", [16.0, 33.333333333333336])
def test_o_primeiro_fasor_do_cosseno_sai_em_um_ciclo_e_um_quarto(por_ciclo):
    x, _ = _senoide(por_ciclo)
    with fasor.usando("cosseno"):
        c = envoltoria.fasores(x, por_ciclo)
    f = envoltoria.fasores(x, por_ciclo)
    primeiro_c = int(np.argmax(np.isfinite(c)))
    primeiro_f = int(np.argmax(np.isfinite(f)))
    assert primeiro_c - primeiro_f == pytest.approx(por_ciclo / 4, abs=1.0)


@pytest.mark.parametrize("por_ciclo", [16.0, 33.333333333333336])
def test_com_a_exponencial_da_falta_o_cosseno_erra_menos(por_ciclo):
    # Falta com assimetria total: a DC começa igual ao pico e decai com
    # τ = 1,5 ciclo (X/R ≈ 9,4 — linha de transmissão).
    n = int(8 * por_ciclo)
    k = np.arange(n, dtype=np.float64)
    tau = 1.5 * por_ciclo
    x = 1000.0 * (np.cos(2 * math.pi * k / por_ciclo) - np.exp(-k / tau))
    with fasor.usando("cosseno"):
        c = np.abs(envoltoria.fasores(x, por_ciclo))
    f = np.abs(envoltoria.fasores(x, por_ciclo))
    trecho = slice(int(1.5 * por_ciclo), int(4 * por_ciclo))
    erro_c = np.max(np.abs(c[trecho] - 1000.0))
    erro_f = np.max(np.abs(f[trecho] - 1000.0))
    assert erro_c < erro_f / 2, (erro_c, erro_f)


@pytest.mark.parametrize("por_ciclo", [16.0, 33.333333333333336])
def test_cursor_e_curva_dao_o_mesmo_numero_com_o_cosseno(por_ciclo):
    n = int(6 * por_ciclo)
    k = np.arange(n, dtype=np.float64)
    x = 50 * np.cos(2 * math.pi * k / por_ciclo) + 30 * np.exp(-k / por_ciclo)
    with fasor.usando("cosseno"):
        curva = envoltoria.fundamental(x, por_ciclo)
        for i in (int(2 * por_ciclo), int(3.3 * por_ciclo), n - 1):
            no_cursor = fasor.no_instante(x, i, por_ciclo)
            assert no_cursor is not None
            assert no_cursor.fundamental == pytest.approx(curva[i], rel=1e-9)
        # Antes de 1,25 ciclo não há fasor: nem curva, nem cursor.
        assert fasor.no_instante(x, int(1.1 * por_ciclo), por_ciclo) is None


def test_fora_do_contexto_vale_fourier_e_nome_estranho_tambem():
    assert fasor.estimador() == "fourier"
    with fasor.usando("cosseno"):
        assert fasor.estimador() == "cosseno"
    assert fasor.estimador() == "fourier"
    with fasor.usando("mimico"):
        assert fasor.estimador() == "fourier"
    with fasor.usando(None):
        assert fasor.estimador() == "fourier"
