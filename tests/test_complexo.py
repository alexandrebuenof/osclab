"""O plano complexo: a trajetória do fasor e as duas referências.

O que se prende aqui é o que o plano tem de NOVO: o desgiro pelo tempo, a
referência fixa × dinâmica e a morte da referência. O fasor em si é o da
envoltória, que já tem os seus testes — e há um aqui que confere o plano
contra a leitura do cursor, que é o número que a tabelinha do fasorial mostra.
"""

from __future__ import annotations

import cmath
import math

import numpy as np

from osclab.plot import complexo, janela, leitura, paineis
from tests.test_catalogo import PICO, trifasico


def plano(sinais, *, referencia="", fixa=True):
    return paineis.Painel(id="pc", tipo=paineis.COMPLEXO, nome="",
                          sinais=tuple(sinais), referencia=referencia,
                          referencia_fixa=fixa)


def pacote_do_plano(registro, painel):
    pacote = janela.montar(registro, colunas=200, layout=[painel])
    return pacote["paineis"][0]


def ponto(painel_montado, identidade, k):
    trilha = painel_montado["trajetorias"][identidade]
    re, im = trilha["re"][k], trilha["im"][k]
    return None if re is None else complex(re, im)


def test_fasor_parado_vira_um_ponto_so_no_eficaz_e_no_angulo_da_referencia():
    """Em regime a 60 Hz exatos, todo ponto depois do primeiro ciclo é o
    MESMO: módulo eficaz e ângulo contado a partir da VA."""
    r = trifasico(defasagens=(-30.0, -150.0, 90.0))
    p = pacote_do_plano(r, plano(["c0:instantaneo"]))
    pontos = [ponto(p, "c0:instantaneo", k) for k in range(40, 600, 37)]
    for z in pontos:
        assert abs(abs(z) - PICO / math.sqrt(2)) < 1e-4 * PICO
        assert abs(math.degrees(cmath.phase(z)) - (-30.0)) < 1e-3
    # O primeiro ciclo não tem janela: sem ponto, e não um zero.
    assert ponto(p, "c0:instantaneo", 0) is None


def test_a_referencia_padrao_e_a_tensao_da_fase_A_e_vem_escrita():
    p = pacote_do_plano(trifasico(), plano(["c0:instantaneo"]))
    assert p["zero"]["id"] == "c3:instantaneo"
    assert p["zero"]["nome"] == "Voltage A-G"
    assert p["zero"]["fixa"] is True
    assert p["tipo"] == "complexo"


def test_a_dinamica_da_o_mesmo_angulo_da_leitura_do_cursor():
    """Com a referência dinâmica, o ângulo do plano é o MESMO que a leitura
    do cursor (e portanto o fasorial) mostra no mesmo instante. Duas contas
    do mesmo fasor é como a tabela e o desenho divergem."""
    r = trifasico(defasagens=(-40.0, -160.0, 80.0), amplitudes=(PICO, 0.7 * PICO, 1.2 * PICO))
    p = pacote_do_plano(r, plano(["c0:instantaneo", "c1:instantaneo"], fixa=False))
    for k in (60, 211, 444):
        t = float(r.time[k])
        lido = leitura.em(r, [(t, 0, 0.0)],
                          layout=[paineis.Painel(id="f", tipo=paineis.FASORIAL, nome="",
                                                 sinais=("c0:instantaneo", "c1:instantaneo"))])
        sinais = lido["cursores"][0]["sinais"]
        for identidade in ("c0:instantaneo", "c1:instantaneo"):
            z = ponto(p, identidade, k)
            assert abs(abs(z) - sinais[identidade]["fundamental"]) < 1e-4 * PICO
            dif = math.degrees(cmath.phase(z)) - sinais[identidade]["angulo"]
            assert abs((dif + 180) % 360 - 180) < 1e-3


def _fora_de_60(freq_da_rede: float, n=1200, taxa=1200.0):
    """Um registro gravado como 60 Hz, com a rede em outra frequência."""
    r = trifasico(n=n, taxa=taxa, freq=freq_da_rede)
    r.line_frequency = 60.0
    return r


def test_fora_de_60_hz_a_fixa_gira_e_a_dinamica_fica_parada():
    """É o losango do SynchroWave: 0,5 Hz de desvio giram o fasor 180° por
    segundo na referência FIXA. Na dinâmica a referência gira junto, e o
    ângulo entre as duas não muda."""
    r = _fora_de_60(60.5)
    fixo = pacote_do_plano(r, plano(["c0:instantaneo", "c3:instantaneo"]))
    movel = pacote_do_plano(r, plano(["c0:instantaneo", "c3:instantaneo"], fixa=False))
    a, b = 100, 1100
    dt = float(r.time[b] - r.time[a])
    giro = math.degrees(cmath.phase(ponto(fixo, "c3:instantaneo", b)
                                    / ponto(fixo, "c3:instantaneo", a)))
    esperado = (0.5 * 360.0 * dt + 180) % 360 - 180
    assert abs(giro - esperado) < 1.0
    # Na dinâmica a VA é sempre 0°, e a IA fica parada em relação a ela.
    assert abs(math.degrees(cmath.phase(ponto(movel, "c3:instantaneo", b)))) < 1e-3
    ia_a = ponto(movel, "c0:instantaneo", a)
    ia_b = ponto(movel, "c0:instantaneo", b)
    assert abs(math.degrees(cmath.phase(ia_b / ia_a))) < 0.5


def test_componentes_de_uma_trinca_equilibrada():
    """ABC equilibrado: I1 é a fase, I2 é zero e 3I0 é zero — no plano
    inteiro, não só num instante."""
    r = trifasico()
    p = pacote_do_plano(r, plano(["q0:0:rms", "q0:1:rms", "q0:2:rms"]))
    for k in range(40, 600, 53):
        assert abs(ponto(p, "q0:0:rms", k)) < 1e-4 * PICO
        assert abs(abs(ponto(p, "q0:1:rms", k)) - PICO / math.sqrt(2)) < 1e-4 * PICO
        assert abs(ponto(p, "q0:2:rms", k)) < 1e-4 * PICO


def test_a_referencia_dinamica_que_vai_a_zero_para_o_rastro_de_todos():
    """Uma corrente de referência que vai a zero (disjuntor aberto) não tem
    ângulo — e sem zero de ângulo, nenhum ponto. A tela diz até quando ela
    valeu, em vez de desenhar ângulo de ruído."""
    r = trifasico(n=900)
    r.analog[0, 500:] = 0.0
    p = pacote_do_plano(r, plano(["c3:instantaneo"], referencia="c0:instantaneo",
                                 fixa=False))
    ate = p["zero"]["ate"]
    assert ate is not None and float(r.time[500]) <= ate <= float(r.time[540])
    assert ponto(p, "c3:instantaneo", 800) is None
    assert ponto(p, "c3:instantaneo", 300) is not None
    # A fixa não morre: o ângulo dela é um só, o do começo.
    fixa = pacote_do_plano(r, plano(["c3:instantaneo"], referencia="c0:instantaneo"))
    assert fixa["zero"]["ate"] is None
    assert ponto(fixa, "c3:instantaneo", 800) is not None


def test_registro_longo_vai_com_passo_e_diz_qual():
    r = trifasico(n=25000, taxa=12000.0)
    p = pacote_do_plano(r, plano(["c0:instantaneo"]))
    assert p["passo"] == math.ceil(25000 / complexo.MAXIMO_DE_PONTOS)
    assert len(p["pontos"]["n"]) == len(p["trajetorias"]["c0:instantaneo"]["re"])
    assert len(p["pontos"]["n"]) <= complexo.MAXIMO_DE_PONTOS


def test_o_plano_de_um_registro_com_falta_marca_a_janela_que_a_atravessa():
    """A janela que tem pré-falta e falta misturadas é marcada, e os ciclos
    são contados a partir do início da perturbação."""
    r = trifasico(n=1200)
    r.analog[0, 600:] *= 5.0
    p = pacote_do_plano(r, plano(["c0:instantaneo"]))
    assert p["transicao"] is not None
    t0, t1 = p["transicao"]
    assert abs(t0 - float(r.time[600])) < 2.0 / 1200
    assert abs((t1 - t0) - 1 / 60) < 1e-9
    assert [c["ciclo"] for c in p["ciclos"][:3]] == [1, 2, 3]
    # A marca do primeiro ciclo cai um ciclo (20 amostras) depois do início.
    assert abs(p["ciclos"][0]["k"] - 620) <= 2


def test_a_tela_manda_fixa_e_o_servidor_le():
    cru = [{"id": "x", "tipo": "complexo", "sinais": ["c0:instantaneo"],
            "referencia": "c3:instantaneo", "fixa": False}]
    lido = paineis.de_json(cru)[0]
    assert lido.tipo == paineis.COMPLEXO
    assert lido.referencia_fixa is False
    assert paineis.de_json([{"id": "y", "tipo": "complexo"}])[0].referencia_fixa is True


def test_estacionario_atravessa_a_fronteira_entre_trechos_sem_salto():
    """Num registro de taxa variável o índice da DFT recomeça em cada trecho.
    Desgirado pelo tempo absoluto, o fasor não dá salto na fronteira."""
    from osclab.formats.base import SampleRate
    t1 = np.arange(600) / 1200.0
    t2 = t1[-1] + (np.arange(1, 1201) / 2400.0)
    t = np.concatenate([t1, t2])
    r = trifasico(n=t.size)
    r.time = t
    for i in range(6):
        fase = (0.0, -120.0, -240.0)[i % 3] + (-30.0 if i < 3 else 0.0)
        r.analog[i] = PICO * np.sin(2 * np.pi * 60 * t + math.radians(fase))
    r.sample_rates = (SampleRate(rate_hz=1200.0, last_sample=600),
                      SampleRate(rate_hz=2400.0, last_sample=1800))
    assert len(r.trechos) == 2
    p = pacote_do_plano(r, plano(["c0:instantaneo"]))
    antes, depois = ponto(p, "c0:instantaneo", 590), ponto(p, "c0:instantaneo", 1700)
    assert abs(math.degrees(cmath.phase(depois / antes))) < 0.5
    assert abs(abs(depois) - abs(antes)) < 1e-3 * PICO
