"""A janela «parâmetros» do painel localizador: `faultloc/parametros.py`."""

import cmath
import math

import pytest

from osclab.faultloc import parametros as pm

#: Uma linha de 100 km, em primário: Z1 = 8 + j40 Ω, Z0 = 30 + j120 Ω, B1 300 µS.
LINHA = {"ok": True, "r": 8.0, "x": 40.0, "r0": 30.0, "x0": 120.0, "km": 100.0, "b1": 300.0}


def _num(txt: str) -> float:
    return float(txt.replace(",", "."))


def test_texto_com_cinco_significativos_e_virgula():
    assert pm.texto(40.7922) == "40,792"
    assert pm.texto(0.08) == "0,08"
    assert pm.texto(6743.21) == "6743,2"
    assert pm.texto(None) == "" and pm.texto(0) == "0"
    assert pm.texto_angulo(78.69) == "78,69"


def test_as_quatro_vistas_de_uma_linha():
    rtp_rtc = 120.0
    prim = pm.valores(LINHA, "prim", "ohm", rtp_rtc)
    assert prim["mod"] == pytest.approx(math.hypot(8, 40))
    assert prim["ang"] == pytest.approx(math.degrees(math.atan2(40, 8)))
    sec = pm.valores(LINHA, "sec", "ohm", rtp_rtc)
    assert sec["r"] == pytest.approx(8 / 120) and sec["x0"] == pytest.approx(1.0)
    # Admitância vai ao contrário da impedância.
    assert sec["b1"] == pytest.approx(300 * 120)
    por_km = pm.valores(LINHA, "prim", "km", rtp_rtc)
    assert por_km["r"] == pytest.approx(0.08) and por_km["b1"] == pytest.approx(3.0)
    # O ângulo, o k0 e o comprimento não mudam com a vista.
    for v in (sec, por_km):
        assert v["ang"] == pytest.approx(prim["ang"]) and v["km"] == 100.0
        assert v["k0mod"] == pytest.approx(prim["k0mod"])
    k0 = (complex(30, 120) - complex(8, 40)) / (3 * complex(8, 40))
    assert prim["k0mod"] == pytest.approx(abs(k0))
    assert prim["k0ang"] == pytest.approx(math.degrees(cmath.phase(k0)))


def test_sem_relacao_nao_ha_secundario_e_sem_km_nao_ha_por_km():
    assert pm.valores(LINHA, "sec", "ohm", None) is None
    assert pm.valores(dict(LINHA, km=None), "prim", "km", 120.0) is None
    f = pm.ficha(LINHA, None)
    assert f["sec"]["ohm"] is None and f["prim"]["ohm"]["r"] == "8"


def test_o_k0_gravado_pelo_rele_vence_o_calculado():
    gravado = 0.7 * cmath.exp(1j * math.radians(-5))
    v = pm.valores(LINHA, "prim", "ohm", None, gravado)
    assert v["k0mod"] == pytest.approx(0.7) and v["k0ang"] == pytest.approx(-5)


def test_digitado_se_completa_e_converte_de_volta():
    """O que se digita em secundário por km vira a mesma linha em primário, e
    a linha escrita de volta na vista dá os mesmos números."""
    m = {"forma": "km", "base": "sec", "km": "100", "rkm": str(0.08 / 120),
         "xkm": str(0.4 / 120), "r0km": "0,0025", "x0km": "0,01", "b1km": str(3 * 120)}
    lin = pm.digitado_parcial(m, 120.0)
    assert lin["r"] == pytest.approx(8) and lin["x"] == pytest.approx(40)
    assert lin["r0"] == pytest.approx(30) and lin["b1"] == pytest.approx(300)
    volta = pm.como_digitado(lin, "sec", "km", 120.0)
    assert volta["forma"] == "km" and _num(volta["xkm"]) == pytest.approx(0.4 / 120, rel=1e-4)
    em_ohm = pm.como_digitado(lin, "prim", "ohm", 120.0)
    assert em_ohm["forma"] == "rx" and em_ohm["r"] == "8" and em_ohm["km"] == "100"


def test_digitado_incompleto_fica_so_com_o_que_fecha():
    assert pm.digitado_parcial({"r": "8", "km": "50"}, None) == {"km": 50.0}
    # Por km sem comprimento não é linha; secundário sem relação não converte.
    assert pm.digitado_parcial({"forma": "km", "rkm": "1", "xkm": "2"}, None) == {}
    sec_sem_relacao = {"base": "sec", "r": "1", "x": "2", "km": "5"}
    assert pm.digitado_parcial(sec_sem_relacao, None) == {"km": 5.0}
    assert pm.como_digitado({"r": 1.0, "x": 2.0}, "prim", "km", None) is None


def test_tolerancias_modulo_angulo_e_comprimento():
    ref = pm.valores(LINHA, "prim", "ohm", None)
    quase = pm.valores(dict(LINHA, r=8.1, km=100.9), "prim", "ohm", None)
    d = pm.diferencas(quase, ref)
    assert not any(d.values())                       # 0,4 % e 0,9 km: dentro
    girado = 40.79 * cmath.exp(1j * math.radians(math.degrees(math.atan2(40, 8)) + 1.5))
    fora = pm.valores(dict(LINHA, r=girado.real, x=girado.imag, km=102.5), "prim", "ohm", None)
    d = pm.diferencas(fora, ref)
    assert d["ang"] and not d["mod"]
    assert d["r"] and d["x"]                          # R e X acompanham o Z
    assert d["km"]                                    # 2,5 km > 1 km e > 1 %
    # Linha longa: 1 % de 300 km são 3 km, e 2,5 km fica dentro.
    longa = pm.valores(dict(LINHA, km=300.0), "prim", "ohm", None)
    assert not pm.diferencas(pm.valores(dict(LINHA, km=302.5), "prim", "ohm", None),
                             longa)["km"]


def test_a_comparacao_e_contra_a_coluna_em_uso_e_por_km_e_outra_conta():
    """O mesmo Z total com outro comprimento é outro Z por km: em Ω a célula
    não fica vermelha, em Ω/km fica."""
    outra = dict(LINHA, km=110.0)
    c = pm.comparacao({"base": LINHA, "A": outra}, "base")
    assert c["ohm"]["A"]["km"] and not c["ohm"]["A"]["mod"]
    assert c["km"]["A"]["mod"] and c["km"]["A"]["r"]
    assert "base" not in c["ohm"]
    assert pm.comparacao({"base": LINHA}, None) == {}


def test_o_selo_so_sai_quando_o_rele_difere():
    rele = dict(LINHA, r=8.5, x=42.5, km=97.0)       # |Z1| +6 %, LL −3 km
    fontes = {"A": rele, "base": LINHA, "manual": {"ok": False}}
    blocos = pm.selo(fontes, "base", ["A"])
    assert len(blocos) == 1 and blocos[0]["com"] == "base"
    itens = {i["campo"]: i for i in blocos[0]["itens"]}
    assert itens["|Z1|"]["difere"] and itens["|Z1|"]["dif"] == "+6,3 %"
    assert itens["comprimento (LL)"]["difere"] and not itens["∠Z1"]["difere"]
    assert pm.selo({"A": LINHA, "base": LINHA}, "A", ["A"]) == []
    # Sem base e sem digitado não há com que comparar.
    sozinho = {"A": rele, "base": {"ok": False}, "manual": {"ok": False}}
    assert pm.selo(sozinho, "A", ["A"]) == []


def test_montar_traz_o_digitado_parcial_e_as_vistas_dele():
    fontes = {"A": dict(LINHA), "base": {"ok": False}, "B": {"ok": False},
              "manual": {"ok": False}}
    p = pm.montar(fontes, "A", ["A"], 120.0, {"r": "8", "x": "40"}, {})
    assert set(p["fichas"]) == {"A", "manual"}
    assert p["fichas"]["manual"]["prim"]["ohm"]["mod"] == pm.texto(math.hypot(8, 40))
    assert p["fichas"]["manual"]["prim"]["ohm"]["km"] == ""
    # Incompleto não entra na comparação (não está em uso, nem pode estar).
    assert "manual" not in p["comparacao"].get("ohm", {})
    assert p["digitado_em"]["sec"]["ohm"]["r"] == pm.texto(8 / 120)
    assert p["digitado_em"]["prim"]["km"] is None    # sem comprimento
