"""A matemática do fasor, contra respostas conhecidas.

Um fasor errado não dá erro nenhum: ele devolve um número plausível, com a
unidade certa, e some dentro do relatório. Por isso cada teste aqui monta um
sinal de resposta SABIDA e confere o número, em vez de comparar com outra
implementação — que poderia estar errada junto.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.dsp import fasor


def senoide(amplitude: float, graus: float, por_ciclo: int = 20,
            ciclos: int = 4, dc: float = 0.0) -> np.ndarray:
    """`amplitude * cos(ωt + fase) + dc`, amostrada em `por_ciclo`.

    A amostra do índice 0 fica em t=0, então o fasor do ciclo que termina na
    amostra `k` tem ângulo `graus` referido àquele instante.
    """
    n = por_ciclo * ciclos
    t = np.arange(n) / por_ciclo                       # em ciclos
    return amplitude * np.cos(2 * np.pi * t + math.radians(graus)) + dc


# ---------------------------------------------------------------------------
# O básico: amplitude e ângulo
# ---------------------------------------------------------------------------

def test_o_modulo_e_eficaz_e_nao_amplitude():
    """Conferido contra o SIGRA: a coluna "Fundamental" dele é eficaz.

    Implementar como amplitude daria √2 de diferença — erro que se procura por
    horas, porque o gráfico continua parecendo certo.
    """
    sinal = senoide(amplitude=100.0, graus=0.0)
    f = fasor.no_instante(sinal, i=len(sinal) - 1, por_ciclo=20)
    assert f.fundamental == pytest.approx(100.0 / math.sqrt(2.0), rel=1e-9)


@pytest.mark.parametrize("graus", [0.0, 30.0, 90.0, -120.0, 179.0, -179.0])
def test_o_angulo_sai_referido_ao_cursor(graus):
    """A referência do ângulo é o ÚLTIMO ponto da janela, não o primeiro.

    Sem isso, o ângulo dependeria do tamanho da janela — e um registro a 32
    amostras/ciclo discordaria de um a 20 no mesmo instante.
    """
    por_ciclo = 20
    sinal = senoide(100.0, graus, por_ciclo=por_ciclo)
    # A amostra 3*por_ciclo cai exatamente em t = 3 ciclos, ou seja, na mesma
    # posição da onda que t = 0: o ângulo tem que ser o mesmo.
    f = fasor.no_instante(sinal, i=3 * por_ciclo, por_ciclo=por_ciclo)
    assert fasor.em_relacao_a(f.angulo, 0.0) == pytest.approx(graus, abs=1e-6)


def test_o_angulo_anda_com_o_cursor():
    """Uma amostra adiante a 20 por ciclo são 18° a mais."""
    por_ciclo = 20
    sinal = senoide(100.0, 0.0, por_ciclo=por_ciclo)
    a = fasor.no_instante(sinal, i=2 * por_ciclo, por_ciclo=por_ciclo)
    b = fasor.no_instante(sinal, i=2 * por_ciclo + 1, por_ciclo=por_ciclo)
    assert fasor.em_relacao_a(b.angulo, a.angulo) == pytest.approx(18.0, abs=1e-6)


def test_defasagem_de_120_graus_entre_fases():
    """O caso que sustenta as componentes simétricas do 0.4b."""
    por_ciclo = 20
    i = 3 * por_ciclo
    fa = fasor.no_instante(senoide(100.0, 0.0), i, por_ciclo)
    fb = fasor.no_instante(senoide(100.0, -120.0), i, por_ciclo)
    fc = fasor.no_instante(senoide(100.0, 120.0), i, por_ciclo)

    assert fasor.em_relacao_a(fb.angulo, fa.angulo) == pytest.approx(-120.0, abs=1e-6)
    assert fasor.em_relacao_a(fc.angulo, fa.angulo) == pytest.approx(120.0, abs=1e-6)


# ---------------------------------------------------------------------------
# A janela termina no cursor
# ---------------------------------------------------------------------------

def test_a_janela_e_o_ciclo_que_ACABOU_de_passar():
    """O relé só conhece o passado: o módulo leva um ciclo inteiro para subir.

    Sinal de 10 A que vira 100 A na amostra 40. Meio ciclo depois do degrau, a
    janela ainda tem metade de cada nível — o módulo tem que estar no meio do
    caminho, nunca já no valor final.
    """
    por_ciclo = 20
    sinal = np.concatenate([senoide(10.0, 0.0, ciclos=2),
                            senoide(100.0, 0.0, ciclos=2)])

    antes = fasor.no_instante(sinal, i=39, por_ciclo=por_ciclo)
    meio = fasor.no_instante(sinal, i=49, por_ciclo=por_ciclo)
    depois = fasor.no_instante(sinal, i=59, por_ciclo=por_ciclo)

    assert antes.fundamental == pytest.approx(10.0 / math.sqrt(2), rel=1e-6)
    assert depois.fundamental == pytest.approx(100.0 / math.sqrt(2), rel=1e-6)
    # No meio: nem o antigo, nem o novo.
    assert antes.fundamental < meio.fundamental < depois.fundamental


def test_nao_ha_fasor_sem_um_ciclo_inteiro_antes():
    """Meia janela daria um número plausível e errado — a pior espécie."""
    sinal = senoide(100.0, 0.0, por_ciclo=20)
    assert fasor.no_instante(sinal, i=10, por_ciclo=20) is None
    assert fasor.no_instante(sinal, i=19, por_ciclo=20) is not None


# ---------------------------------------------------------------------------
# DC, harmônicos e o RMS verdadeiro
# ---------------------------------------------------------------------------

def test_a_dc_nao_contamina_a_fundamental():
    """Falta assimétrica tem DC de decaimento. A DFT de um ciclo inteiro a
    rejeita — e é por isso que a janela precisa ser de um ciclo EXATO."""
    sinal = senoide(100.0, 0.0, dc=40.0)
    f = fasor.no_instante(sinal, i=59, por_ciclo=20)
    assert f.fundamental == pytest.approx(100.0 / math.sqrt(2), rel=1e-9)
    assert f.dc == pytest.approx(40.0, rel=1e-9)


def test_a_dc_percentual_segue_a_convencao_do_sigra():
    """Conferido com o registro real: DC% é relativa à fundamental EFICAZ.

        Current IC C | Fundamental 2,3449 A | Extremum 3,7229 A | DC 16,9 %
        2,3449 × √2 = 3,316 de pico, + 16,9 % × 2,3449 = 3,712 ≈ 3,7229
    """
    eficaz = 2.3449
    sinal = senoide(eficaz * math.sqrt(2), 0.0, dc=0.169 * eficaz)
    f = fasor.no_instante(sinal, i=59, por_ciclo=20)
    assert f.dc_percentual == pytest.approx(16.9, abs=0.1)
    assert f.maximo == pytest.approx(3.71, abs=0.02)


def test_o_rms_verdadeiro_inclui_o_que_a_fundamental_nao_ve():
    """Em senoide pura os dois coincidem; com harmônico, não. A diferença é o
    aviso de que o fasor sozinho não conta a história."""
    puro = fasor.no_instante(senoide(100.0, 0.0), i=59, por_ciclo=20)
    assert puro.rms == pytest.approx(puro.fundamental, rel=1e-9)
    # A distorção é PERCENTUAL e sai de uma raiz de diferença de quadrados, que
    # amplifica o resíduo do ponto flutuante: 1e-4 % já é zero para qualquer uso.
    assert puro.distorcao == pytest.approx(0.0, abs=1e-4)

    # Fundamental de 100 com terceiro harmônico de 30 (30 %).
    t = np.arange(80) / 20.0
    com_harmonico = 100 * np.cos(2 * np.pi * t) + 30 * np.cos(2 * np.pi * 3 * t)
    f = fasor.no_instante(com_harmonico, i=59, por_ciclo=20)

    assert f.fundamental == pytest.approx(100.0 / math.sqrt(2), rel=1e-9)
    assert f.rms > f.fundamental
    assert f.distorcao == pytest.approx(30.0, abs=0.5)


def test_o_extremo_e_o_pico_real_da_janela():
    sinal = senoide(100.0, 0.0, dc=40.0)
    f = fasor.no_instante(sinal, i=59, por_ciclo=20)
    assert f.maximo == pytest.approx(140.0, rel=1e-6)
    assert f.minimo == pytest.approx(-60.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Bordas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("taxa,nominal,esperado", [
    (1200.0, 60.0, 20), (960.0, 60.0, 16), (1920.0, 60.0, 32),
    (5760.0, 60.0, 96), (1000.0, 50.0, 20), (0.0, 60.0, 0),
])
def test_amostras_por_ciclo(taxa, nominal, esperado):
    assert fasor.amostras_por_ciclo(taxa, nominal) == esperado


def test_janela_curta_demais_nao_vira_fasor():
    assert fasor.de_janela(np.array([1.0, 2.0])) is None


def test_janela_com_buraco_nao_vira_fasor():
    """Canal saturado ou amostra perdida: melhor não responder."""
    ruim = senoide(100.0, 0.0)[:20].copy()
    ruim[5] = np.nan
    assert fasor.de_janela(ruim) is None


def test_sinal_zerado_nao_divide_por_zero():
    f = fasor.de_janela(np.zeros(20))
    assert f.fundamental == 0.0
    assert f.dc_percentual == 0.0
    assert f.distorcao == 0.0


@pytest.mark.parametrize("bruto,referencia,esperado", [
    (10.0, 0.0, 10.0),
    (190.0, 0.0, -170.0),
    (-190.0, 0.0, 170.0),
    (180.0, 0.0, 180.0),        # +180 fica +180, não vira -180
    (-180.0, 0.0, 180.0),
    (30.0, 120.0, -90.0),
    (0.0, None, 0.0),
])
def test_normalizacao_do_angulo(bruto, referencia, esperado):
    assert fasor.em_relacao_a(bruto, referencia) == pytest.approx(esperado)
