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


@pytest.mark.xfail(strict=True, reason=(
    "falta entre 1 e 2 ciclos do começo não é achada pelo detector de início "
    "(analysis/falta.py): corrigir mexe no caso «registro que já começa num "
    "transitório», em aberto com o Alexandre — ver tests/test_varredura.py"))
def test_pre_falta_de_pouco_mais_de_um_ciclo():
    """A falta 1,2 ciclo depois do começo do registro tem de ser achada."""
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


@pytest.mark.parametrize("local,quem", [("barraR", "IED B"), ("barraS", "IED A"),
                                        ("externaR", "IED B"), ("externaS", "IED A")])
@pytest.mark.parametrize("formato", ["COMTRADE 2000 Hz", ".CEV 8 a/c"])
def test_trifasica_externa_nao_vira_resultado(local, quem, formato):
    """Era o D2: a direção incremental (ΔV1/ΔI1) subtraía o fasor da
    pré-falta do fasor da falta SEM desfazer o giro de 60 Hz (o fasor contínuo
    dá uma volta por ciclo), e decidia pela fase do ciclo — a ABC na barra de
    R saía «laço 100,3 km» como resultado."""
    cen = _cenario(local=local, tipo="ABC")
    fa, fb = FORMATOS[formato]
    p = _localizar(cen, fa, fb, abre_s=None, abre_r=None, extingue=0.075)
    assert p["resultado"] is None
    assert quem in p["direcao"] and "PARA TRÁS" in p["direcao"]


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


# ---------------------------------------------------------------------------
# Takagi e a seq. negativa distribuída (25/10/2026)
# ---------------------------------------------------------------------------

#: O quanto o Takagi do programa se afasta do Takagi sobre os fasores exatos.
#: Medido na varredura de 25/10/2026 (COMTRADE 2000 Hz e .CEV de 8 a/c, Rf
#: 0–50 Ω, δ 0/20°, SIR 0,2–4): 0,02 km típico, 0,44 km no pior.
TOL_IMPL_TAKAGI = 0.5
#: A seq. negativa DISTRIBUÍDA tem erro inerente zero (é a linha do gerador);
#: o que sobra é DSP: 0,30 km p95 e 0,32 km no pior numa LT de 250 km.
TOL_DISTRIBUIDA = 0.4


def _takagi_ideal(cen: rede.Cenario, laco: str) -> float:
    """Takagi sobre os fasores exatos: `Im{V·ΔI*} / Im{Z1·I·ΔI*}` no IED A."""
    pos, pre = rede.regime(cen, True), rede.regime(cen, False)
    k = {"A": 0, "B": 1, "C": 2}
    z1, z0 = cen.linha.Z1, cen.linha.Z0

    def do_laco(V, i):
        if laco.endswith("N"):
            return V[k[laco[0]]], i[k[laco[0]]] + (z0 - z1) / (3 * z1) * i.sum()
        return V[k[laco[0]]] - V[k[laco[1]]], i[k[laco[0]]] - i[k[laco[1]]]
    v, i = do_laco(pos["VS"], pos["IS"])
    di = i - do_laco(pre["VS"], pre["IS"])[1]
    return (v * di.conjugate()).imag / (z1 * i * di.conjugate()).imag * cen.linha.km


@pytest.mark.parametrize("tipo", ["AG", "BC", "ABC"])
@pytest.mark.parametrize("m", [0.5, 0.9])
@pytest.mark.parametrize("rf", [10.0, 50.0])
def test_takagi_com_rf_e_carga(tipo, m, rf):
    """Um terminal, Rf de 10 a 50 Ω e carga (δ = 20°). O programa reproduz o
    Takagi dentro de `TOL_IMPL_TAKAGI`, e o Takagi fica mais perto da falta
    que o laço pela reatância — é para isso que ele existe. O resultado
    continua sendo o laço (a preferência não mudou), mas a discordância
    entre os dois aparece no aviso quando passa do limite."""
    cen = _cenario(m=m, tipo=tipo, rf=rf, delta=20.0)
    p = _localizar(cen, so_a=True)
    tk, laco = _km(p, "takagi"), _km(p, "laco")
    assert abs(tk - _takagi_ideal(cen, p["laco"])) <= TOL_IMPL_TAKAGI
    assert abs(tk - cen.km_verdadeiro) < abs(laco - cen.km_verdadeiro)
    assert p["resultado"]["metodo"] == "laco"
    limite = max(ldl.DISCORDANCIA_MINIMA_KM, ldl.DISCORDANCIA_DA_LT * cen.linha.km)
    assert ("discordam" in p["aviso"]) == (abs(tk - laco) > limite)


LT_250 = rede.Linha(250.0, complex(0.08, 0.49), complex(0.35, 1.50), 9.2e-9, 6.2e-9)


def _com_capacitancia(cen: rede.Cenario) -> dict:
    """A linha com `b1`/`b0` em µS da linha inteira, como se digitaria."""
    p = cen.parametros()
    p["b1"] = rede.W * cen.linha.c1 * cen.linha.km * 1e6
    p["b0"] = rede.W * cen.linha.c0 * cen.linha.km * 1e6
    return p


@pytest.mark.parametrize("tipo,m,rf", [("AG", 0.1, 0.0), ("BC", 0.9, 25.0), ("AG", 0.7, 25.0)])
def test_linha_longa_com_capacitancia_usa_a_distribuida(tipo, m, rf):
    """LT de 250 km a 138 kV. A concentrada erra 2,7 a 5,4 km (a corrente capacitiva
    entra inteira na falta); com a capacitância declarada, a distribuída
    acerta dentro do erro de DSP. Sem capacitância, cai na concentrada."""
    cen = _cenario(linha=LT_250, m=m, tipo=tipo, rf=rf, delta=20.0)
    sim = _simulado(cen)
    reg_a = rede.gravar(sim, "S", COMTRADE_A, nome="SE ALFA")
    reg_b = rede.gravar(sim, "R", COMTRADE_B, nome="SE BETA")
    d = alinhamento.deslocamento(reg_a, reg_b, "falta")["d"]
    com = ldl.montar(reg_a, reg_b, d, _com_capacitancia(cen), None)
    sem = ldl.montar(reg_a, reg_b, d, cen.parametros(), None)
    assert com["metodos"]["seqneg"]["modelo"] == "distribuída"
    assert sem["metodos"]["seqneg"]["modelo"] == "concentrada"
    assert com["resultado"]["metodo"] == "seqneg"
    assert abs(com["resultado"]["km"] - cen.km_verdadeiro) <= TOL_DISTRIBUIDA
    assert abs(_km(sem, "seqneg") - cen.km_verdadeiro) > 2.0      # 2,7 a 5,4 km
