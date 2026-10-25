"""Localização por sequência negativa: a conta da planilha LocDef_SeqNeg."""

from __future__ import annotations

import cmath
import math

import pytest

from osclab.basedados import linhas
from osclab.faultloc import seqneg


def _polar(m, a):
    return m * cmath.exp(1j * math.radians(a))


def test_o_caso_coxipo_da_planilha():
    """Os números da folha «LT COXIPO - BDURO»: m2 = 0,006230, 0,058 km."""
    r = seqneg.localizar(_polar(18062, 0), _polar(3566, 103),
                         _polar(17619, 0), _polar(141.6, 111.1),
                         complex(0.67, 3.759))
    assert r.m2 == pytest.approx(0.006230322, rel=1e-6)
    assert r.m == r.m2
    # A outra raiz é −2,76, fora da linha — e não os −704 milhões da planilha,
    # que usa B² onde deveria usar −B (célula C72).
    assert r.m1 == pytest.approx(-2.7643127, rel=1e-6)


def _sintetico(m, zl, zs, zr, i2f, giro_r):
    """Um curto em `m`: a fonte de sequência negativa é o ponto da falta."""
    ramo_s, ramo_r = zs + m * zl, zr + (1 - m) * zl
    i2s = i2f * ramo_r / (ramo_s + ramo_r)
    i2r = i2f - i2s
    g = cmath.exp(1j * math.radians(giro_r))
    return -i2s * zs, i2s, -i2r * zr * g, i2r * g


@pytest.mark.parametrize("m", [0.05, 0.4, 0.72, 0.95])
@pytest.mark.parametrize("giro", [0, 37, -120])
def test_acha_a_falta_sem_sincronismo(m, giro):
    """Girar o terminal R inteiro não muda a resposta: só módulos entram."""
    zl = complex(4, 20)
    v2s, i2s, v2r, i2r = _sintetico(m, zl, complex(2, 10), complex(5, 25),
                                    _polar(1000, -80), giro)
    assert seqneg.localizar(v2s, i2s, v2r, i2r, zl).m == pytest.approx(m, abs=1e-9)


def test_falta_externa_nao_tem_raiz_na_linha():
    zl = complex(4, 20)
    v2s, i2s, v2r, i2r = _sintetico(0.4, zl, complex(2, 10), complex(5, 25),
                                    _polar(1000, -80), 0)
    assert seqneg.localizar(v2s, i2s, v2r, -i2r, zl).m is None


def test_sem_corrente_nao_ha_conta():
    assert seqneg.localizar(1, 0, 1, 1, complex(1, 5)) is None


def test_linha_dos_ajustes_vai_a_primario():
    saida = seqneg.linha_dos_ajustes({"Z1MAG": "1", "Z1ANG": "90", "LL": "10"}, 200.0)
    assert saida["ok"]
    assert saida["x"] == pytest.approx(200.0)
    assert saida["km"] == 10


def test_linha_dos_ajustes_sem_relacao_e_recusada():
    saida = seqneg.linha_dos_ajustes({"Z1MAG": "1", "Z1ANG": "90", "LL": "10"}, None)
    assert not saida["ok"] and "RTP/RTC" in saida["motivo"]


def test_linha_digitada_nas_tres_formas():
    rx = seqneg.linha_digitada({"forma": "rx", "r": "2,6", "x": "14", "km": "40"}, None)
    pol = seqneg.linha_digitada({"forma": "pol", "mod": abs(complex(2.6, 14)),
                                 "ang": math.degrees(math.atan2(14, 2.6)), "km": 40}, None)
    km = seqneg.linha_digitada({"forma": "km", "rkm": 0.065, "xkm": 0.35, "km": 40}, None)
    for s in (rx, pol, km):
        assert s["ok"]
        assert s["r"] == pytest.approx(2.6) and s["x"] == pytest.approx(14)
    sec = seqneg.linha_digitada({"r": 1, "x": 5, "km": 3, "base": "sec"}, None)
    assert not sec["ok"]


class _Base:
    def __init__(self, pasta):
        self.pasta = pasta

    def gaveta(self, qual):
        destino = self.pasta / qual
        destino.mkdir(parents=True, exist_ok=True)
        return destino


def test_base_de_linhas_grava_le_e_casa_os_terminais(tmp_path):
    base = _Base(tmp_path)
    linhas.gravar(base, linhas.Linha("LT COXIPO - BDURO", "COXIPO", "BARRO DURO",
                                     0.67, 3.759, 9.29))
    lidas = linhas.listar(base)
    assert lidas[0].x1_ohm == pytest.approx(3.759)
    # Em qualquer ordem dos terminais, por trecho do texto do registro.
    achadas = linhas.procurar(base, ["UPC1 BARRO DURO SEL-451"], ["LT COXIPO I UPC1"])
    assert [x.nome for x in achadas] == ["LT COXIPO - BDURO"]
    assert linhas.procurar(base, ["SE ALFA"], ["SE BETA"]) == []


def test_no_411l_o_comprimento_e_o_llr_na_unidade_do_llunit():
    """O `LL 100.00` do 411L é padrão de fábrica oculto; vale o `LLR`."""
    base = {"Z1MAG": "1", "Z1ANG": "90", "LL": "100.00", "LLR": "2.54"}
    em_km = seqneg.linha_dos_ajustes({**base, "LLUNIT": "KM"}, 200.0)
    assert em_km["km"] == pytest.approx(2.54)
    em_milha = seqneg.linha_dos_ajustes({**base, "LLUNIT": "MI"}, 200.0)
    assert em_milha["km"] == pytest.approx(2.54 * 1.609344)
