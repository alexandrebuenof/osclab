"""O painel «localizador de faltas»: o número do relé e o arrumador do painel.

A conta dos métodos é a de `faultloc/ldl.py` e tem os testes dela
(`test_ldl.py`); aqui se testa o que é deste painel — ler a distância que o
PRÓPRIO relé calculou, em cada formato do parque, e entregar à tela tudo em
km e em % da linha, porque o JavaScript não decide número.
"""

from __future__ import annotations

import pytest

from osclab import paths
from osclab.faultloc import ldl, rele
from osclab.library import acervo
from osclab.plot import localizador, paineis
from tests.fabrica import escrever_cev
from tests.test_ldl import LINHA, _rede, _registro

# ---------------------------------------------------------------------------
# O número do relé, formato por formato (levantado no banco em 09/11/2026)
# ---------------------------------------------------------------------------


def _cev(campos: dict, ajustes: str = "") -> str:
    nomes = ",".join(f'"{n}"' for n in campos)
    valores = ",".join(campos.values())
    return ('"FID","RID","SID","1234"\n"FID=SEL-421-R100"\n"MONTH","DAY","YEAR"\n11,5,2026\n'
            f"{nomes}\n{valores}\n" + ajustes)


def test_sel_cev_le_o_location_sem_unidade_e_diz_que_presumiu():
    achado = rele.do_cev(_cev({"EVENT_NUM": "1", "EVENT": '"BG T"', "LOCATION": "14.63"},
                              "LL      = 137.00\n"), "x.cev")
    assert (achado.valor, achado.campo, achado.unidade, achado.presumido) == \
        (14.63, "LOCATION", None, True)
    assert achado.km == 14.63


def test_sel_411l_prefere_o_baseado_em_impedancia_e_le_a_milha():
    """O 411L não tem LOCATION; o valor vem com `(SE)` e, às vezes, com a unidade."""
    achado = rele.do_cev(_cev({"EVENT": '"ABC"', "FLM": '"SE"', "TW_LOCATION": '"$$$$.$$(mi)"',
                               "Z_BASED_LOCATION": '"305.08(SE)"'}))
    assert (achado.valor, achado.campo, achado.unidade) == (305.08, "Z_BASED_LOCATION", None)
    em_milha = rele.do_cev(_cev({"Z_BASED_LOCATION": '"10.00(mi)"'}))
    assert em_milha.unidade == "mi" and em_milha.km == pytest.approx(16.09344)
    pelo_ajuste = rele.do_cev(_cev({"Z_BASED_LOCATION": '"10.00(SE)"'}, 'LLUNIT  := "MI"\n'))
    assert pelo_ajuste.unidade == "mi"


def test_sem_distancia_calculada_nao_ha_numero():
    """`$$$$.$$` é o relé dizendo que não calculou: ausência, nunca zero."""
    assert rele.do_cev(_cev({"EVENT": '"AB T"', "LOCATION": "$$$$.$$"})) is None
    sem = "15 | 20:11:36 | 0.884 | 004.022 FT_DA Fault location | Not measured"
    assert rele.do_texto(sem) is None


def test_hdr_da_sel_e_do_411l_e_do_twfl():
    sel = "Event: BC                Location:  -12.76     Time Source: OTHER"
    assert rele.do_texto(sel).valor == -12.76
    z = rele.do_texto("TW Location: $$$$.$$(mi) Z-Based Location: 2.54(ME) From: LOCAL"
                      '\n"LLUNIT",MI')
    assert (z.valor, z.unidade, z.campo) == (2.54, "mi", "Z-Based Location")
    tw = rele.do_texto('"L1_Fault_Location","112.576(km)"\n"L1_Fault_Location_Method","SE TW"')
    assert (tw.valor, tw.unidade) == (112.576, "km")
    assert rele.do_texto("Event:  CG T  Location:  +17.31   Frequency: 60.0").valor == 17.31


def test_micom_le_o_km_e_o_percentual_da_fault_log():
    achado = rele.do_texto(
        "12 | 20:11:36.355 | 0.884 | 004.022 FT_DA Fault location       | 10.3 km\n"
        "13 | 20:11:36.355 | 0.884 | 004.027 FT_DA Fault locat. percent | 69.31 %\n")
    assert (achado.valor, achado.unidade, achado.percentual) == (10.3, "km", 69.31)
    assert achado.campo == "FT_DA Fault location"


def test_o_cev_vem_antes_do_hdr(tmp_path):
    (tmp_path / "a.cev").write_text(_cev({"LOCATION": "20.59"}), encoding="cp1252")
    (tmp_path / "a.hdr").write_text("Event: AG  Location:  99.99", encoding="cp1252")
    achado = rele.do_registro(tmp_path, ["a.hdr", "a.cev"])
    assert (achado.valor, achado.arquivo) == (20.59, "a.cev")
    assert rele.do_registro(tmp_path, ["nada.cfg"]) is None


# ---------------------------------------------------------------------------
# O arrumador do painel, em cima de uma localização sintética de verdade
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pacote():
    rede = _rede(0.43, 0.0, "AG")
    return ldl.montar(_registro(rede["S"]), _registro(rede["R"], nome="SE BETA"), 0.0,
                      LINHA, None)


def test_tudo_sai_em_km_e_em_porcentagem_da_linha(pacote):
    res = pacote["resultado"]
    p = localizador.montar(pacote, None, None, None, None)
    L = LINHA["km"]
    assert p["linha_km"] == L
    assert p["resultado"]["km"] == res["km"]
    assert p["resultado"]["pct"] == pytest.approx(res["km"] / L * 100)
    assert p["resultado"]["patrulha_km"] == pytest.approx([res["km"] - res["faixa"],
                                                           res["km"] + res["faixa"]])
    for m, par in p["metodos"].items():
        km = pacote["metodos"][m]["km"]
        assert par["km"] == km
        assert par["pct"] == (None if km is None else pytest.approx(km / L * 100))
    # As marcações em % vêm com o km em que caem: a tela só converte em pixel.
    for marca in p["marcas_pct"]:
        assert marca["km"] == pytest.approx(marca["rotulo"] * L / 100)


def test_os_dois_cursores_e_a_diferenca(pacote):
    plato = pacote["eventos"]["plato"]
    rede = _rede(0.43, 0.0, "AG")
    a, b = _registro(rede["S"]), _registro(rede["R"], nome="SE BETA")
    c1 = ldl.montar(a, b, 0.0, LINHA, plato[0] + 0.004)["cursor"]
    c2 = ldl.montar(a, b, 0.0, LINHA, plato[1] - 0.004)["cursor"]
    p = localizador.montar(pacote, c1, c2, None, None)
    m = pacote["resultado"]["metodo"]
    assert p["diferenca"]["km"][m] == pytest.approx(c2["km"][m] - c1["km"][m])
    assert p["cursor1"]["pct"][m] == pytest.approx(c1["km"][m] / LINHA["km"] * 100)
    sem = localizador.montar(pacote, c1, None, None, None)
    assert sem["cursor2"] is None and sem["diferenca"] is None


def test_o_rele_digitado_vence_o_lido_e_a_diferenca_e_contra_o_resultado(pacote):
    lido = rele.DoRele(20.0, None, "LOCATION", "x.cev")
    res_km = pacote["resultado"]["km"]
    p = localizador.montar(pacote, None, None, lido, None)
    r = p["rele"]
    assert (r["km"], r["origem"], r["presumido"]) == (20.0, "lido", True)
    assert p["rele"]["delta_km"] == pytest.approx(20.0 - res_km)
    p = localizador.montar(pacote, None, None, lido, 33.5)
    assert (p["rele"]["km"], p["rele"]["origem"]) == (33.5, "digitado")
    assert localizador.montar(pacote, None, None, None, None)["rele"] is None


def test_sem_linha_a_regua_sai_do_rele():
    """Sem Z1 nenhum método tem km, mas o relé tem o número dele."""
    sem_linha = {"metodos": {}, "resultado": None}
    p = localizador.montar(sem_linha, None, None, rele.DoRele(37.2, "km", "LOCATION", ""), None)
    assert p["linha_km"] is None and p["marcas_pct"] == []
    assert p["regua"]["min"] == 0 and p["regua"]["max"] >= 37.2
    assert localizador.montar(sem_linha, None, None, None, None)["regua"] is None


def test_o_painel_e_um_tipo_que_a_tela_pode_mandar():
    lidos = paineis.de_json([{"id": "t1", "tipo": "localizador", "nome": ""}])
    assert lidos[0].tipo == paineis.LOCALIZADOR
    assert localizador.esqueleto(lidos[0]) == {"id": "t1", "tipo": "localizador",
                                               "nome": "Localizador de faltas",
                                               "do_padrao": False}


# ---------------------------------------------------------------------------
# A rota: o bloco `painel` vai junto do pacote da localização
# ---------------------------------------------------------------------------


def test_a_rota_manda_o_bloco_do_painel_com_o_rele(tmp_path, monkeypatch, cliente):
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    caminho = escrever_cev(tmp_path / "origem", nome="EVENTO")
    texto = caminho.read_bytes().decode("cp1252").replace("$$$$.$$", "21.37")
    # A soma de verificação da linha muda; o leitor avisa e lê assim mesmo.
    sha = acervo.guardar([(caminho.name, texto.encode("cp1252"))]).aceitos[0].sha
    r = cliente.post(f"/api/onda/{sha}/localizar", json={"painel": True})
    assert r.status_code == 200
    rel = r.get_json()["painel"]["rele"]
    assert (rel["km"], rel["origem"], rel["campo"]) == (21.37, "lido", "LOCATION")
    r = cliente.post(f"/api/onda/{sha}/localizar", json={"painel": True, "rele_manual": 30})
    assert r.get_json()["painel"]["rele"]["origem"] == "digitado"
    # Sem o pedido do painel, o pacote é o de sempre da tela de localizar.
    assert "painel" not in cliente.post(f"/api/onda/{sha}/localizar", json={}).get_json()
