"""As equações desenhadas da janela «? métodos» (variante 06, 12/11/2026).

A tela só pinta a árvore; o que a equação diz, os símbolos e a conta «neste
registro» saem de `faultloc/equacoes.py` — por isso são testados aqui.
"""
from __future__ import annotations

import json
import re

import pytest

from osclab.faultloc import equacoes, ldl
from tests.test_ldl import L_KM, _painel

TIPOS = {"v", "n", "o", "p", "txt", "fn", "d", "frac", "r"}


def _nos(no):
    yield no
    if no["t"] == "r":
        for x in no["x"]:
            yield from _nos(x)
    elif no["t"] in ("fn", "d"):
        yield from _nos(no["x"])
    elif no["t"] == "frac":
        yield from _nos(no["a"])
        yield from _nos(no["b"])


def _profundidade_de_fracao(no, dentro=0):
    """Quantas frações estão empilhadas uma dentro da outra, no máximo."""
    aqui = dentro + (no["t"] == "frac")
    filhos = {"r": lambda: no["x"], "fn": lambda: [no["x"]], "d": lambda: [no["x"]],
              "frac": lambda: [no["a"], no["b"]]}.get(no["t"], lambda: [])()
    return max([aqui, *(_profundidade_de_fracao(f, aqui) for f in filhos)])


def test_todo_metodo_tem_uma_equacao_principal():
    for metodo in ldl.METODOS:
        eqs = equacoes.EQUACOES[metodo]
        assert [e["papel"] for e in eqs].count("principal") == 1, metodo


def test_a_arvore_so_tem_nos_que_a_tela_sabe_pintar():
    for metodo, eqs in equacoes.EQUACOES.items():
        for e in eqs:
            for no in _nos(e["arvore"]):
                assert no["t"] in TIPOS, (metodo, no)
                if no["t"] == "d":
                    assert no["k"] in ("abs", "par", "chave")


def test_todo_simbolo_das_equacoes_diz_o_que_e():
    for metodo, eqs in equacoes.EQUACOES.items():
        for e in eqs:
            for i in equacoes.ids(e["arvore"]):
                assert i in equacoes.SIMBOLOS, (metodo, i)


def test_nenhuma_fracao_dentro_de_fracao():
    """A forma escolhida para o laço: `m = Im{Z_laço} / X1L`, e
    `Z_laço = V_laço / I_laço` numa auxiliar — uma fração de cada vez."""
    for metodo, eqs in equacoes.EQUACOES.items():
        for e in eqs:
            assert _profundidade_de_fracao(e["arvore"]) <= 1, (metodo, e["texto"])


def test_o_texto_corrido_e_a_mesma_equacao():
    laco = equacoes.EQUACOES["laco"]
    assert laco[0]["texto"] == "m = (Im{Zlaço}) / (X1L)"
    assert laco[1]["texto"] == "Zlaço = (Vlaço) / (Ilaço)"
    seq = equacoes.EQUACOES["seqneg"][0]["texto"]
    assert seq == "|V2S − m·Z2L·I2S| = |V2R − (1 − m)·Z2L·I2R|"
    assert "ΔI*" in equacoes.EQUACOES["takagi"][0]["texto"]


def test_neste_registro_e_a_conta_com_os_numeros():
    conta = equacoes.neste(56.444, 137.0)
    assert " ".join(equacoes.texto(conta).split()) == "d = m·L = 0,4120 × 137,0 km = 56,44 km"
    assert equacoes.neste(None, 137.0) is None
    assert equacoes.neste(10.0, None) is None


def test_o_pacote_leva_as_equacoes_e_o_numero_em_cada_metodo():
    p = _painel(m=0.43, rf=0.0)
    seq = p["metodos"]["seqneg"]
    assert seq["km"] is not None
    assert seq["m"] == pytest.approx(seq["km"] / L_KM)
    assert seq["km_txt"] == f"{seq['km']:.2f}".replace(".", ",")
    assert seq["m_txt"] == f"{seq['m']:.4f}".replace(".", ",")
    assert seq["equacoes"] == equacoes.EQUACOES["seqneg"]
    assert seq["quantos"] == "dois terminais"
    assert p["metodos"]["laco"]["quantos"] == "um terminal"
    # A conta «neste registro» fecha com o km do método.
    numeros = [x["x"] for x in _nos(seq["neste"]) if x["t"] == "n"]
    assert numeros == [seq["m_txt"], f"{L_KM:.1f}".replace(".", ","), seq["km_txt"]]
    # Só os símbolos que o método usa; e o `d` e o `L` da conta.
    assert set(seq["simbolos"]) == {"m", "V2S", "V2R", "I2S", "I2R", "Z2L", "d", "L"}
    assert "IED A" in seq["simbolos"]["V2S"]
    assert p["terminais_da_ajuda"] == {"s": "S · IED A", "r": "R · IED B",
                                      "r_de_um": "R · não entra"}
    # O texto antigo continua indo: é o hover da legenda do painel.
    assert p["metodos"]["laco"]["como"] == ldl.COMO_CALCULA["laco"]
    # A frase do laço perdeu a fórmula, que agora é desenhada.
    assert "k0 = (" not in p["metodos"]["laco"]["detalhe"]
    json.dumps(p, allow_nan=False)


def test_com_um_ied_so_nao_existe_ied_a():
    """Nunca «IED A» com uma oscilografia só."""
    p = _painel(m=0.43, rf=0.0, so_a=True)
    texto = json.dumps({k: p[k] for k in ("terminais_da_ajuda",)}, ensure_ascii=False)
    texto += json.dumps([p["metodos"][m]["simbolos"] for m in p["metodos"]], ensure_ascii=False)
    assert "IED" not in texto
    assert p["terminais_da_ajuda"]["s"] == "S · este relé"


def test_metodo_sem_numero_nao_tem_conta():
    p = _painel(m=0.43, rf=0.0, so_a=True)
    seq = p["metodos"]["seqneg"]
    assert seq["km"] is None
    assert seq["neste"] is None and seq["m"] is None and seq["km_txt"] is None


def test_anexar_nao_mexe_no_pacote_guardado():
    original = {"km_linha": 100.0, "terminais": [{}],
                "metodos": {"laco": {"km": 40.0, "como": "x", "detalhe": "y"}}}
    copia = json.loads(json.dumps(original))
    saida = equacoes.anexar(original)
    assert original == copia
    assert saida["metodos"]["laco"]["m_txt"] == "0,4000"


def test_o_simbolo_com_letra_grega_casa_com_o_id():
    """`Iφ`, `ΔI`: o id tem de ser o mesmo que a árvore gera."""
    todos = {i for eqs in equacoes.EQUACOES.values() for e in eqs
             for i in equacoes.ids(e["arvore"])}
    assert {"Iφ", "ΔI", "Ipré", "Zlaço"} <= todos
    assert all(re.fullmatch(r"\S+", i) for i in todos)
