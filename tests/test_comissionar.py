"""A rotina de comissionamento em massa (`tools/comissionar.py`), com dado
sintético: a comparação entre duas rodadas e o registro que não abre."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

from tests import fabrica

_CAMINHO = Path(__file__).resolve().parents[1] / "tools" / "comissionar.py"
_spec = importlib.util.spec_from_file_location("comissionar", _CAMINHO)
comissionar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(comissionar)


def _linha(registro, conferencia, veredito, erro="", item="", unidade="%"):
    return {"registro": registro, "equipamento": "", "conferencia": conferencia,
            "item": item, "rele": "", "nosso": "", "erro": erro, "unidade": unidade,
            "tolerancia": "3", "veredito": veredito, "motivo": ""}


def _gravar(caminho: Path, linhas) -> Path:
    with open(caminho, "w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, comissionar.COLUNAS, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)
    return caminho


def test_comparar_separa_o_que_piorou_do_que_melhorou(tmp_path):
    antes = _gravar(tmp_path / "antes.csv", [
        _linha("a.CEV", "2 fasor", "confere", "0.5", "módulo"),
        _linha("a.CEV", "6 trip", "diverge", "1", "T1", "amostras"),
        _linha("b.cfg", "1 resíduo", "confere", "0.10", "I*"),
        _linha("c.cfg", "1 resíduo", "confere", "0.10", "I*"),
        _linha("d.cfg", "0 leitura", "confere"),
        _linha("e.CEV", "4 colunas", "diverge", "14", "3V0M"),
        _linha("g.CEV", "3 falta", "confere", "1", "módulo"),
    ])
    depois = _gravar(tmp_path / "depois.csv", [
        _linha("a.CEV", "2 fasor", "diverge", "7.5", "módulo"),      # piorou
        _linha("a.CEV", "6 trip", "confere", "0", "T1", "amostras"),  # melhorou
        _linha("b.cfg", "1 resíduo", "confere", "0.40", "I*"),       # erro cresceu
        _linha("c.cfg", "1 resíduo", "confere", "0.11", "I*"),       # dentro da folga
        _linha("d.cfg", "0 leitura", "erro"),                         # deixou de abrir
        _linha("e.CEV", "4 colunas", "não se aplica", "", "3V0M"),    # critério
        _linha("f.CEV", "0 leitura", "confere"),                      # apareceu
    ])
    dif = comissionar.comparar(comissionar.carregar(antes), comissionar.carregar(depois))
    piorou = {(r, c) for (r, c, _), *_ in dif["piorou"]}
    melhorou = {(r, c) for (r, c, _), *_ in dif["melhorou"]}
    mudou = {(r, c) for (r, c, _), *_ in dif["mudou"]}
    # g.CEV: a linha que conferia SUMIU — conferência perdida, não detalhe
    assert piorou == {("a.CEV", "2 fasor"), ("b.cfg", "1 resíduo"), ("d.cfg", "0 leitura"),
                      ("g.CEV", "3 falta")}
    assert melhorou == {("a.CEV", "6 trip")}
    assert mudou == {("e.CEV", "4 colunas"), ("f.CEV", "0 leitura")}


def test_a_folga_vale_tambem_para_erro_pequeno(tmp_path):
    """0,01 % → 0,04 % quadruplica e não é regressão nenhuma: é ruído de
    quarta casa. A folga absoluta existe para isso."""
    antes = _gravar(tmp_path / "a.csv", [_linha("x", "1", "confere", "0.01", "i")])
    depois = _gravar(tmp_path / "d.csv", [_linha("x", "1", "confere", "0.04", "i")])
    dif = comissionar.comparar(comissionar.carregar(antes), comissionar.carregar(depois))
    assert not dif["piorou"]


def test_registro_que_nao_abre_vira_linha_de_erro_e_o_resto_continua(tmp_path):
    pasta = tmp_path / "banco"
    pasta.mkdir()
    (pasta / "truncado.CEV").write_bytes(b"\r\n=>\r\n")
    fabrica.escrever_comtrade(pasta, nome="bom")
    (pasta / "pyvenv.cfg").write_text("home = x", encoding="utf-8")   # não é COMTRADE
    saida = tmp_path / "placar.csv"
    n = comissionar.tirar(pasta, saida, avisar=lambda *a, **k: None)
    assert n == 2
    linhas = comissionar.carregar(saida)
    leitura = {r: x["veredito"] for (r, c, _), x in linhas.items() if c == "0 leitura"}
    assert leitura == {"truncado.CEV": "erro", "bom.cfg": "confere"}
    motivo = next(x["motivo"] for (r, c, _), x in linhas.items()
                  if r == "truncado.CEV")
    assert motivo.startswith("não abre")
    # o registro bom passou por todas as conferências, cada uma com veredito
    do_bom = [x for (r, _, _), x in linhas.items() if r == "bom.cfg"]
    assert len({x["conferencia"] for x in do_bom}) >= 9
    assert all(x["veredito"] in ("confere", "diverge", "não se aplica") for x in do_bom)


def test_ignorar_nao_le_o_registro_mas_deixa_a_linha(tmp_path):
    pasta = tmp_path / "banco"
    fabrica.escrever_comtrade(pasta / "TWFL", nome="onda")
    saida = tmp_path / "placar.csv"
    comissionar.tirar(pasta, saida, ignorar=("*TWFL*",), avisar=lambda *a, **k: None)
    linhas = list(comissionar.carregar(saida).values())
    assert len(linhas) == 1
    assert linhas[0]["veredito"] == "não se aplica"
    assert "ignorado" in linhas[0]["motivo"]
