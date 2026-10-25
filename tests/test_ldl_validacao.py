"""A LDL contra uma rede resolvida em FASE e gravada como um relé gravaria.

Amostra permanente da validação independente de 24–25/10/2026 (o relatório
inteiro, com as ~3 200 execuções, está fora do repositório). O gerador é o
`tests/rede_de_falta.py`; ele não usa nada do `test_ldl.py`, de propósito.

**As tolerâncias são o erro INERENTE de cada método**, medido na varredura —
não folga para o teste passar:

- `TOL_SEQNEG = 1,0 km` (1 % da LT de 100 km): é o pior caso da seq. negativa
  sobre os fasores EXATOS da linha com capacitância (0,17 % típico, 1,0 % no
  pior — a corrente capacitiva, que a equação não modela). Com o terminal
  remoto fraco (SIR 20) o inerente sobe e a medida foi 1,25 km: `TOL_FRACO`.
- `TOL_LACO = 0,6 km` para o laço com **Rf = 0**: inerente de 0,5 % (a mesma
  capacitância) mais 0,1 km de DSP. Com Rf o laço erra dezenas de km POR
  CONSTRUÇÃO (efeito de reatância com infeed e carga); aí o teste confere que o
  programa reproduz o método — `TOL_IMPL_*` contra o valor ideal — e não que
  ele acerta a falta.
- `TOL_IMPL_SEQNEG = 0,5 km` e `TOL_IMPL_LACO = 1,1 km`: o quanto o programa
  pode se afastar do próprio método aplicado aos fasores exatos. Medido na
  varredura: seq. negativa 0,04 km típico e 0,17 km no p95; laço 0,02 km e
  0,30 km (1,05 km com Rf de 25 Ω e infeed forte). O pior caso de todos —
  1,06 e 2,46 km — é o COMTRADE de 1200 Hz com anti-aliasing de 2ª ordem, onde
  a oscilação de alta frequência da entrada da falta se rebate para perto de
  60 Hz: é do registro, não da conta, e por isso os casos daqui usam 2000 Hz.

Os defeitos que ainda dão número errado SEM aviso estão aqui como
`xfail(strict=True)`: o dia em que forem corrigidos, o teste avisa.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest

from osclab.faultloc import ldl
from osclab.plot import alinhamento
from tests import rede_de_falta as rede

TOL_SEQNEG = 1.0
TOL_FRACO = 1.5
TOL_LACO = 0.6
TOL_IMPL_SEQNEG = 0.5
TOL_IMPL_LACO = 1.1

COMTRADE_A = rede.Formato()                                   # 2000 Hz, secundário
COMTRADE_B = rede.Formato(rtc=(1200.0, 5.0), fase_amostra=3, seed=1)
FORMATOS = {
    "COMTRADE 2000 Hz": (COMTRADE_A, COMTRADE_B),
    "COMTRADE 1200 Hz primário": (rede.Formato(taxa=1200.0, escala="P"),
                                  rede.Formato(taxa=1200.0, escala="P", fase_amostra=7,
                                               seed=1)),
    ".CEV 8 a/c": (rede.Formato("cev", 480.0), rede.Formato("cev", 480.0, fase_amostra=11,
                                                            seed=1)),
    ".CEV 4 a/c": (rede.Formato("cev", 240.0), rede.Formato("cev", 240.0, fase_amostra=23,
                                                            seed=1)),
    "COMTRADE × .CEV": (COMTRADE_A, rede.Formato("cev", 480.0, fase_amostra=5, seed=1)),
}


@functools.lru_cache(maxsize=8)
def _simulado(cen: rede.Cenario, **kw) -> dict:
    """Uma simulação por cenário: os formatos gravam a MESMA rede."""
    return rede.simular(cen, **kw)


def _localizar(cen, fmt_a=COMTRADE_A, fmt_b=COMTRADE_B, modo="falta", so_a=False, **kw):
    sim = _simulado(cen, **kw)
    reg_a = rede.gravar(sim, "S", fmt_a, nome="SE ALFA")
    reg_b = None if so_a else rede.gravar(sim, "R", fmt_b, nome="SE BETA")
    d = alinhamento.deslocamento(reg_a, reg_b, modo)["d"] if reg_b is not None else 0.0
    return ldl.montar(reg_a, reg_b, d, cen.parametros(), None)


def _km(pacote, metodo):
    return pacote["metodos"][metodo]["km"]


_cenario = rede.Cenario


# ---------------------------------------------------------------------------
# O gerador confere consigo mesmo
# ---------------------------------------------------------------------------

def test_o_emtp_chega_ao_regime_da_rede_nodal():
    """No tempo, depois de a DC morrer, a falta é o regime da admitância nodal.

    É a prova de que as duas resoluções da mesma lista de elementos batem; a
    validação mediu 0,008 % (o empenamento da regra trapezoidal a 12 kHz).
    """
    cen = _cenario(m=0.3, tipo="AG")
    sim = rede.simular(cen, abre_s=None, abre_r=None, duracao=0.6)
    n = int(round(rede.FS / rede.F0))
    janela = sim["x"][:, -n:]
    giro = np.exp(-1j * rede.W * sim["t"][-n:])
    fasor = (janela * giro).sum(axis=1) * np.sqrt(2) / n
    ref = rede.regime(cen)
    ideal = np.concatenate([ref["VS"], ref["IS"], ref["VR"], ref["IR"]])
    erro = np.abs(np.abs(fasor) - np.abs(ideal)) / np.abs(ideal)
    assert erro.max() < 1e-3


# ---------------------------------------------------------------------------
# Falta interna: a seq. negativa é o resultado, dentro do erro do método
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tipo", ["AG", "BC", "ABG"])
@pytest.mark.parametrize("m", [0.1, 0.5, 0.9])
def test_interna_franca(tipo, m):
    cen = _cenario(m=m, tipo=tipo)
    p = _localizar(cen)
    assert p["resultado"]["metodo"] == "seqneg"
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_SEQNEG
    assert abs(_km(p, "seqneg") - rede.seqneg_ideal(cen)) <= TOL_IMPL_SEQNEG
    assert abs(_km(p, "laco") - cen.km_verdadeiro) <= TOL_LACO


@pytest.mark.parametrize("formato", list(FORMATOS))
def test_formatos_do_mesmo_evento(formato):
    """COMTRADE (2000/1200 Hz, primário/secundário), .CEV de 8 e de 4 a/c e a
    mistura dos dois: a DSP não acrescenta erro que se meça."""
    cen = _cenario(m=0.25, tipo="AG", rf=5.0)
    fa, fb = FORMATOS[formato]
    p = _localizar(cen, fa, fb)
    assert p["resultado"]["metodo"] == "seqneg"
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_SEQNEG


@pytest.mark.parametrize("tipo,m,rf,delta", [("AG", 0.5, 25.0, 20.0), ("BC", 0.75, 10.0, 20.0)])
def test_rf_e_carga_nao_mexem_na_seqneg(tipo, m, rf, delta):
    """A seq. negativa ignora Rf e carga; o laço erra, e erra como o MÉTODO erra."""
    cen = _cenario(m=m, tipo=tipo, rf=rf, delta=delta)
    p = _localizar(cen)
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_SEQNEG
    laco = _km(p, "laco")
    assert abs(laco - rede.laco_ideal(cen, p["laco"])) <= TOL_IMPL_LACO


@pytest.mark.parametrize("sir_s,sir_r,tol", [(4.0, 0.2, TOL_SEQNEG), (1.0, 20.0, TOL_FRACO)])
def test_infeed_e_terminal_fraco(sir_s, sir_r, tol):
    cen = _cenario(m=0.3, tipo="AG", rf=25.0, sir_s=sir_s, sir_r=sir_r)
    p = _localizar(cen)
    assert p["resultado"]["metodo"] == "seqneg"
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= tol


@pytest.mark.parametrize("formato", ["COMTRADE 2000 Hz", ".CEV 8 a/c"])
@pytest.mark.parametrize("tipo,m,incidencia", [("AG", 0.1, 0.0), ("BC", 0.9, 0.0),
                                               ("AG", 0.5, 90.0)])
def test_componente_continua(tipo, m, incidencia, formato):
    """Fonte com X/R alto (88°). Entrando no zero da tensão a DC é a maior
    possível, e o platô de dois ciclos com a mediana a absorvem; em 90° quase
    não há DC — é o caso que pegou o gerador começando o .CEV com o filtro
    ainda enchendo."""
    cen = _cenario(m=m, tipo=tipo, sir_s=0.5, ang_fonte=88.0, delta=10.0)
    fa, fb = FORMATOS[formato]
    p = _localizar(cen, fa, fb, t_falta=rede.t_da_incidencia(incidencia, delta=10.0))
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_SEQNEG
    assert abs(_km(p, "laco") - cen.km_verdadeiro) <= TOL_LACO


@pytest.mark.parametrize("modo", ["falta", "disparo"])
def test_relogio_de_b_37_ms_adiantado(modo):
    """Alinhando pelo início da falta ou pelo disparo, o erro do relógio some."""
    cen = _cenario(m=0.75, tipo="BC")
    fb = rede.Formato(rtc=(1200.0, 5.0), fase_amostra=2, erro_relogio_s=0.037, seed=4)
    p = _localizar(cen, COMTRADE_A, fb, modo=modo)
    assert p["resultado"]["metodo"] == "seqneg"
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_SEQNEG


def test_relogio_pela_hora_nao_derruba_o_laco():
    """Pela HORA, 37 ms de erro deixam o platô comum curto ou vazio. O laço só
    precisa do IED A e continua valendo (era o defeito B4)."""
    cen = _cenario(m=0.75, tipo="BC")
    fb = rede.Formato(rtc=(1200.0, 5.0), fase_amostra=2, pre_s=0.05, erro_relogio_s=0.037,
                      seed=4)
    p = _localizar(cen, COMTRADE_A, fb, modo="hora")
    assert abs(_km(p, "laco") - cen.km_verdadeiro) <= TOL_LACO
    assert p["resultado"] is not None


def test_pre_falta_de_pouco_mais_de_um_ciclo():
    """A falta 1,2 ciclo depois do começo do registro ainda é achada (o piso de
    ruído pela mediana, 25/10/2026)."""
    cen = _cenario(m=0.3, tipo="AG", rf=10.0)
    fa = rede.Formato(pre_s=1.2 / 60)
    fb = rede.Formato(fase_amostra=3, pre_s=1.2 / 60, seed=1)
    p = _localizar(cen, fa, fb)
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_SEQNEG


def test_um_terminal_so_o_laco_e_o_resultado():
    cen = _cenario(m=0.6, tipo="CG")
    p = _localizar(cen, so_a=True)
    assert p["resultado"]["metodo"] == "laco"
    assert "outro terminal" in p["metodos"]["seqneg"]["motivo"]
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_LACO


# ---------------------------------------------------------------------------
# Trifásica: sem I2, o laço responde e a seq. negativa se recusa
# ---------------------------------------------------------------------------

def test_trifasica_resultado_pelo_laco():
    cen = _cenario(m=0.4, tipo="ABC")
    p = _localizar(cen)
    assert p["resultado"]["metodo"] == "laco"
    assert _km(p, "seqneg") is None
    assert "trifásica" in p["metodos"]["seqneg"]["motivo"]
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_LACO


# ---------------------------------------------------------------------------
# Falta externa: nenhum resultado, e o motivo diz «para trás»
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("local,tipo", [("barraR", "AG"), ("barraS", "AG"), ("externaR", "AG"),
                                        ("externaS", "AG"), ("externaR", "BC")])
def test_falta_externa_nao_vira_resultado(local, tipo):
    """Outro disjuntor elimina a falta (ela se extingue; S e R não abrem)."""
    cen = _cenario(local=local, tipo=tipo, rf=10.0)
    p = _localizar(cen, abre_s=None, abre_r=None, extingue=0.075)
    assert p["resultado"] is None
    assert "PARA TRÁS" in p["direcao"]
    for metodo in ldl.METODOS:
        assert "PARA TRÁS" in p["metodos"][metodo]["motivo"] or \
            p["metodos"][metodo]["km"] is None


def test_trifasica_interna_nao_e_recusada_pelo_32q_de_ruido():
    cen = _cenario(m=0.25, tipo="ABC")
    p = _localizar(cen)
    assert p["resultado"] is not None
    assert abs(p["resultado"]["km"] - cen.km_verdadeiro) <= TOL_LACO


@pytest.mark.xfail(strict=True, reason=(
    "DEFEITO: trifásica EXTERNA vira resultado. O 32Q precisa de I2, e na ABC "
    "`direcao_no_plato` devolve None (ldl.py:215-234, 541-548) — nada recusa. "
    "Na barra de R o laço dá ~100 km; na de S, ~0 km, como RESULTADO."))
def test_trifasica_externa_nao_vira_resultado():
    cen = _cenario(local="barraR", tipo="ABC")
    p = _localizar(cen, abre_s=None, abre_r=None, extingue=0.075)
    assert p["resultado"] is None


# ---------------------------------------------------------------------------
# Erros de instalação
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("defeito", ["troca_bc", "inverte_i"])
def test_fiacao_errada_em_b_nao_da_numero(defeito):
    """Fases B/C trocadas ou polaridade invertida no IED B: B passa a ver a
    falta «para trás» e nada vira resultado. (O motivo diz «falta externa»,
    que é a leitura do 32Q e não o diagnóstico — ver o relatório.)"""
    cen = _cenario(m=0.5, tipo="BC")
    fb = rede.Formato(fase_amostra=3, seed=1, **{defeito: True})
    p = _localizar(cen, COMTRADE_A, fb)
    assert p["resultado"] is None
    assert "IED B" in p["direcao"]


def test_tc_saturado_nao_da_numero_errado_sem_aviso():
    cen = _cenario(m=0.2, tipo="AG", sir_s=0.3, delta=10.0)
    fa = rede.Formato(saturacao=0.3, i_falta=rede.corrente_de_falta(cen))
    p = _localizar(cen, fa, COMTRADE_B)
    res = p["resultado"]
    assert res is None or p["aviso"] or abs(res["km"] - cen.km_verdadeiro) <= TOL_SEQNEG


def test_falta_curta_em_cev_nao_da_numero_errado():
    cen = _cenario(m=0.9, tipo="BC")
    fa, fb = FORMATOS[".CEV 8 a/c"]
    p = _localizar(cen, fa, fb, abre_s=None, abre_r=None, extingue=2.0 / 60)
    res = p["resultado"]
    assert res is None or abs(res["km"] - cen.km_verdadeiro) <= TOL_LACO
