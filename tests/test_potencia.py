"""A potência de um vínculo: a conta, a base da tensão e a unidade.

O que se amarra aqui é o que não se vê no gráfico quando erra. Uma potência
sai sempre na unidade certa e na ordem de grandeza certa — o par errado, a
base errada e o prefixo errado produzem, os três, um número plausível. Por
isso cada um tem o seu teste com um valor esperado escrito à mão.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from osclab.dsp import potencia
from osclab.formats import conjuntos
from osclab.formats.base import AnalogChannel, Record
from osclab.plot import catalogo, unidades


def _fasores(modulo_eficaz, angulos, defasagem=0.0):
    """Três fasores de PICO, que é como a DFT os devolve."""
    pico = modulo_eficaz * math.sqrt(2.0)
    return [np.array([pico * np.exp(1j * (math.radians(a) + defasagem))])
            for a in angulos]


ABC = (0.0, -120.0, -240.0)


# --- a conta ---------------------------------------------------------------

def test_carga_equilibrada_bate_com_tres_vezes_v_i_cos():
    """`P = 3·V·I·cos(θ)` — a conta do primeiro dia de aula."""
    v = _fasores(7967.0, ABC)
    i = _fasores(100.0, ABC, math.radians(-36.87))
    esperado = 3 * 7967.0 * 100.0 * math.cos(math.radians(36.87))
    medido = potencia.serie("P", v, i)[0]
    assert abs(medido - esperado) / esperado < 1e-6


def test_reativa_e_fator_de_potencia():
    v = _fasores(7967.0, ABC)
    i = _fasores(100.0, ABC, math.radians(-36.87))
    q = potencia.serie("Q", v, i)[0]
    s = potencia.serie("S", v, i)[0]
    fp = potencia.serie("FP", v, i)[0]
    assert abs(q - 3 * 7967.0 * 100.0 * math.sin(math.radians(36.87))) < 1.0
    assert abs(s - 3 * 7967.0 * 100.0) < 1.0
    assert abs(fp - 0.8) < 1e-3


def test_por_fase_soma_o_trifasico():
    v = _fasores(7967.0, ABC)
    i = _fasores(100.0, ABC, math.radians(-36.87))
    partes = sum(potencia.serie(g, v, i)[0] for g in ("Pa", "Pb", "Pc"))
    assert abs(partes - potencia.serie("P", v, i)[0]) < 1e-6


# --- a base da tensão ------------------------------------------------------

def test_dois_wattimetros_batem_com_a_soma_por_fase():
    """Blondel: em três fios, duas medidas bastam — mesmo desequilibrado.

    É a afirmação que justifica oferecer potência trifásica a partir de
    tensão de LINHA. Se ela não valesse com desequilíbrio, o número sairia
    certo na carga e errado na falta, que é justamente quando se olha.
    """
    v = _fasores(7967.0, ABC)
    ia = np.array([140.0 * math.sqrt(2) * np.exp(1j * math.radians(-20.0))])
    ib = np.array([60.0 * math.sqrt(2) * np.exp(1j * math.radians(-155.0))])
    ic = -(ia + ib)                       # três fios: a soma é zero
    i = [ia, ib, ic]
    linha = [v[0] - v[1], v[1] - v[2], v[2] - v[0]]

    for grandeza in ("P", "Q"):
        por_fase = potencia.serie(grandeza, v, i)[0]
        dois = potencia.serie(grandeza, linha, i, base="linha")[0]
        assert abs(por_fase - dois) < abs(por_fase) * 1e-12


def test_em_linha_nao_existe_potencia_por_fase():
    """Sem referência de neutro não há como repartir — e `NaN` diz isso."""
    v = _fasores(7967.0, ABC)
    i = _fasores(100.0, ABC)
    linha = [v[0] - v[1], v[1] - v[2], v[2] - v[0]]
    assert np.isnan(potencia.serie("Pa", linha, i, base="linha")[0])


def test_fator_de_potencia_sem_corrente_e_nan():
    """`NaN` e não zero: sem potência o FP não existe, não vale zero."""
    v = _fasores(7967.0, ABC)
    i = [np.array([0j]) for _ in range(3)]
    assert np.isnan(potencia.serie("FP", v, i)[0])


# --- a unidade -------------------------------------------------------------

def _registro(unidade_v, pico_v, unidade_i, pico_i, n=400, taxa=1200.0):
    hz = 60.0
    t = np.arange(n) / taxa
    r = Record(source=Path("sintetico"), format_name="teste")
    r.line_frequency = hz
    nomes = [("IA", unidade_i), ("IB", unidade_i), ("IC", unidade_i),
             ("VA", unidade_v), ("VB", unidade_v), ("VC", unidade_v)]
    r.analog_channels = tuple(
        AnalogChannel(index=k, name=nome, unit=unidade, phase="")
        for k, (nome, unidade) in enumerate(nomes))
    r.analog = np.vstack([
        (pico_i if unidade == unidade_i else pico_v)
        * np.sin(2 * np.pi * hz * t + math.radians(ABC[k % 3]))
        for k, (_, unidade) in enumerate(nomes)])
    r.time = t
    r.status = np.zeros((0, n), dtype=np.int8)
    achados = conjuntos.de_registro(r)
    correntes = [c for c in achados if c.grandeza == "I"]
    tensoes = [c for c in achados if c.grandeza == "V"]
    if correntes and tensoes:
        r.vinculos_de_potencia = {
            correntes[0].nome: {"com": tensoes[0].nome, "base": "fase"},
            tensoes[0].nome: {"com": correntes[0].nome, "base": "fase"},
        }
    return r


def _p_do_registro(registro):
    escalas = unidades.por_unidade(registro, "arquivo")
    sinais = [x for x in catalogo.de_registro(registro, "arquivo", ())
              if x.id.startswith("w") and x.nome.startswith("P ")]
    if not sinais:
        return None, ""
    alvo = sinais[0]
    n = registro.analog.shape[1]
    serie = catalogo.serie(registro, alvo, 0, n, registro.trechos,
                           "arquivo", escalas)
    finitos = serie[np.isfinite(serie)]
    return float(np.median(finitos)), alvo.unidade_mostrada


def test_o_prefixo_sai_das_unidades_do_arquivo_e_da_grandeza():
    """`kV × A` é kVA pelo cabeçalho; MVA ou kVA, só as amostras dizem."""
    casos = [
        # (unidade V, pico V, unidade I, pico I, valor, unidade escrita)
        ("kV", 187.8, "A", 1000 * math.sqrt(2), 398.4, "MW"),
        ("kV", 11.27, "A", 300 * math.sqrt(2), 7.17, "MW"),
        ("V", 115 * math.sqrt(2), "A", 5 * math.sqrt(2), 1725.0, "W"),
        ("kV", 624.6, "A", 2000 * math.sqrt(2), 2.65, "GW"),
    ]
    for unidade_v, pico_v, unidade_i, pico_i, esperado, escrita in casos:
        valor, mostrada = _p_do_registro(
            _registro(unidade_v, pico_v, unidade_i, pico_i))
        assert mostrada == escrita, (unidade_v, unidade_i, mostrada)
        assert abs(valor - esperado) / esperado < 0.01, (unidade_v, valor)


def test_o_mesmo_sistema_declarado_de_dois_jeitos_da_o_mesmo_numero():
    """`kV × A` e `V × kA` são o mesmo vão. O número e a unidade têm que bater.

    É aqui que se erraria por mil sem nada na tela denunciando: a conversão
    não normaliza a unidade do arquivo, então o produto sai na unidade que o
    arquivo declarou — e só o prefixo acerta a escala.
    """
    em_kv = _p_do_registro(_registro("kV", 187.794, "A", 1000 * math.sqrt(2)))
    em_ka = _p_do_registro(_registro("V", 187794.0, "kA", 1.0 * math.sqrt(2)))
    assert em_kv[1] == em_ka[1] == "MW"
    assert abs(em_kv[0] - em_ka[0]) / em_kv[0] < 0.01


def test_sem_vinculo_nao_existe_potencia_nenhuma():
    """O programa não casa corrente com tensão sozinho. Ver o cabeçalho."""
    r = _registro("kV", 11.27, "A", 424.0)
    r.vinculos_de_potencia = {}
    assert _p_do_registro(r) == (None, "")


def test_unidade_que_o_arquivo_nao_declara_nao_vira_potencia():
    """Falha para o lado seguro: some, em vez de sair sem saber a unidade."""
    assert _p_do_registro(_registro("", 11270.0, "", 424.0)) == (None, "")
