"""O cabeçalho com uma linha por IED (`plot/cabecalho.py`, variante 22).

Fichas e itens SINTÉTICOS: nenhum registro real entra aqui.
"""

from __future__ import annotations

from osclab.plot import alinhamento, cabecalho


def _item(sha, *, estacao="SE LIRA", disparo="2026-10-24 03:00:00.145000",
          relogio="", **kw):
    base = {
        "sha": sha, "nome": f"REG_{sha}", "nome_do_arquivo": f"REG_{sha}",
        "estacao": estacao, "modelo": "REL-311", "formato": "comtrade-1999",
        "taxa_hz": 2000.0, "amostras_por_ciclo": 33.333, "n_amostras": 700,
        "n_analogicos": 6, "n_digitais": 1, "relacao_tc": "600 : 5",
        "relacao_tp": "138.000 : 115", "falta_tipo": "AG", "falta_sigla": "AG",
        "falta_cor": "fase-a", "falta_trip": True, "falta_confianca": "alta",
        "falta_dica": "", "falta_inicial": "", "classificacao_do_rele": "",
        "disparo": disparo, "inicio": disparo, "relogio": relogio,
    }
    base.update(kw)
    return base


def _ficha(letra, sha, **kw):
    f = {"letra": letra, "sha": sha, "apelido": "", "taxas_hz": [2000],
         "filtragem": "bruto"}
    f.update(kw)
    return f


def test_uma_oscilografia_nao_tem_referencia_nem_alinhamento():
    tab = cabecalho.montar([_ficha("A", "a")], {"a": _item("a")})
    assert tab["varios"] is False
    (a,) = tab["linhas"]
    assert a["referencia"] is False and a["alinhamento"] is None
    assert a["disparo"]["texto"] == "24/10/2026 03:00:00,145"
    assert a["taxa"] == "2.000 Hz"
    assert (a["medicao"]["tc"], a["medicao"]["tp"]) == ("TC 600 : 5", "TP 138.000 : 115")


def test_o_A_e_a_referencia_e_os_outros_trazem_o_delta_e_o_relogio_curto():
    fichas = [_ficha("A", "a"),
              _ficha("B", "b", alinhado_por="falta", precisao_ms=0.5,
                     relogio_ms=25.2, relogio_texto="25,2 ms à frente")]
    itens = {"a": _item("a"),
             "b": _item("b", estacao="SE ANTARES", disparo="2026-10-24 03:00:00.170000")}
    a, b = cabecalho.montar(fichas, itens)["linhas"]
    assert a["referencia"] and not b["referencia"]
    assert b["terminal"] == "SE ANTARES"
    # A data SEMPRE, e o Δ para o disparo do A embaixo.
    assert b["disparo"]["texto"] == "24/10/2026 03:00:00,170"
    assert b["disparo"]["delta"] == "+25,0 ms"
    assert not b["disparo"]["suspeito"]
    # Só o critério; a precisão vai para o hover.
    assert b["alinhamento"]["por"] == "início da falta"
    assert "0,50 ms" in b["alinhamento"]["por_dica"]
    assert b["alinhamento"]["relogio"] == "+25,2 ms"


def test_relogio_com_a_data_de_fabrica_ganha_o_aviso_sem_afirmar_a_causa():
    fichas = [_ficha("A", "a"), _ficha("B", "b", alinhado_por="falta")]
    itens = {"a": _item("a"), "b": _item("b", disparo="2000-01-01 00:14:22.310000")}
    b = cabecalho.montar(fichas, itens)["linhas"][1]
    assert b["disparo"]["texto"] == "01/01/2000 00:14:22,310"
    assert b["disparo"]["suspeito"]
    assert "pode ser também" in b["disparo"]["dica"]
    assert b["disparo"]["delta"].endswith("anos")


def test_o_arquivo_que_declara_sem_sincronismo_tambem_ganha_o_aviso():
    fichas = [_ficha("A", "a")]
    itens = {"a": _item("a", relogio="carimbos em UTC; relógio sem sincronismo")}
    a = cabecalho.montar(fichas, itens)["linhas"][0]
    assert a["disparo"]["suspeito"]


def test_o_rele_que_concorda_vira_um_visto_e_o_que_discorda_fica_escrito():
    tab = cabecalho.montar([_ficha("A", "a")], {"a": _item("a", classificacao_do_rele="AG T")})
    assert tab["linhas"][0]["falta"]["rele"]["texto"] == "✓ relé"
    tab = cabecalho.montar([_ficha("A", "a")], {"a": _item("a", classificacao_do_rele="BC T")})
    assert tab["linhas"][0]["falta"]["rele"]["classe"] == "conflita"


def test_taxa_que_nao_fecha_em_inteiro_sai_com_virgula():
    f = _ficha("A", "a", taxas_hz=[959.693])
    assert cabecalho.montar([f], {"a": _item("a")})["linhas"][0]["taxa"] == "959,693 Hz"


def test_relacoes_por_equipamento_vao_para_o_hover():
    rel = {"a": [{"equipamento": "TC BUC 69kV", "tipo": "TC", "relacao": "400 : 5"}]}
    tab = cabecalho.montar([_ficha("A", "a")], {"a": _item("a", relacao_tc="vários")}, rel)
    a = tab["linhas"][0]
    assert a["medicao"]["tc"] == "TC vários"
    assert "TC BUC 69kV: TC 400 : 5" in a["medicao"]["dica"]


def test_relogio_curto():
    c = alinhamento.relogio_curto
    assert c(None) == "—"
    assert c(25.2) == "+25,2 ms"
    assert c(-2345.0) == "−2,35 s"
    assert c(725_000.0) == "+12 min 5 s"
    assert c(-11_520_000.0) == "−3 h 12 min"
    assert c(-5 * 86_400_000.0 - 7_200_000.0) == "−5 d 2 h"
    assert c(-26.8 * 365.25 * 86_400_000.0) == "−26,8 anos"


def test_sem_subestacao_declarada_o_terminal_e_o_nome_do_registro():
    fichas = [_ficha("A", "a"), _ficha("B", "b", alinhado_por="falta")]
    itens = {"a": _item("a", estacao=""), "b": _item("b", estacao="")}
    a, b = cabecalho.montar(fichas, itens)["linhas"]
    assert (a["terminal"], b["terminal"]) == ("REG_a", "REG_b")
    assert a["terminal_e_nome"] and b["terminal_e_nome"]
