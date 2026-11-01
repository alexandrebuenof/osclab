"""A fotografia do banco: a ferramenta, e a regressão contra a última foto.

A regressão só roda com as duas variáveis apontando para dado real:

    set OSCLAB_AMOSTRAS=D:\\Oscilografias
    set OSCLAB_FOTOGRAFIA=...\\docs-privados\\fotografia\\banco.jsonl

e reprova se QUALQUER coisa que o programa conclui de um registro mudou. Uma
diferença esperada (o conserto que se fez) se aceita tirando a foto de novo —
que é a decisão consciente que este teste existe para forçar.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parents[1] / "tools" / "fotografia.py"
_spec = importlib.util.spec_from_file_location("fotografia", _CAMINHO)
fotografia = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fotografia)


def test_comparar_acha_cada_campo_que_mudou_e_o_registro_que_sumiu():
    antes = {"a.cfg": {"arquivo": "a.cfg", "fases": ["A", "B"], "falta": {"tipo": "AG"}},
             "b.cfg": {"arquivo": "b.cfg", "fases": ["A"]}}
    depois = {"a.cfg": {"arquivo": "a.cfg", "fases": ["A", "N"], "falta": {"tipo": "AG"}},
              "c.cfg": {"arquivo": "c.cfg", "fases": ["C"]}}
    dif = fotografia.comparar(antes, depois)
    assert ("a.cfg", "fases", ["A", "B"], ["A", "N"]) in dif
    assert ("b.cfg", "registro", True, False) in dif
    assert ("c.cfg", "registro", False, True) in dif
    assert not any(campo == "falta" for _, campo, _, _ in dif)


def test_a_parte_da_falta_que_mudou_sai_com_o_nome_dela():
    antes = {"a.cfg": {"falta": {"tipo": "AG", "inicial": "AG", "instante": 10}}}
    depois = {"a.cfg": {"falta": {"tipo": "ABC", "inicial": "AG", "instante": 10}}}
    assert fotografia.comparar(antes, depois) == [("a.cfg", "falta.tipo", "AG", "ABC")]


def test_campo_que_a_foto_antiga_nao_tinha_nao_e_mudanca():
    antes = {"a.cfg": {"formato": "x", "falta": {"tipo": "AG"}}}
    depois = {"a.cfg": {"formato": "x", "falta": {"tipo": "AG", "inicial": "AG"},
                        "rele": "AG T", "concorda": True}}
    assert fotografia.comparar(antes, depois) == []


def test_registro_que_passou_a_dar_erro_conta_tudo():
    antes = {"a.cfg": {"formato": "x"}}
    depois = {"a.cfg": {"erro": "não abre"}}
    dif = fotografia.comparar(antes, depois)
    assert ("a.cfg", "erro", None, "não abre") in dif
    assert ("a.cfg", "formato", "x", None) in dif


def test_a_sigla_do_rele_vem_do_hdr_do_mesmo_registro(tmp_path):
    from tests.fabrica import escrever_comtrade

    cfg = escrever_comtrade(tmp_path, nome="evento")
    (tmp_path / "evento.HDR").write_text("Event: BG T\n", encoding="utf-8")
    (tmp_path / "outro.hdr").write_text("Event: AB\n", encoding="utf-8")
    assert fotografia.foto_de(cfg)["rele"] == "BG T"


def test_cfg_sem_dat_nao_e_oscilografia(tmp_path):
    (tmp_path / "pyvenv.cfg").write_text("home = x", encoding="utf-8")
    (tmp_path / "x.cfg").write_text("", encoding="utf-8")
    (tmp_path / "x.dat").write_text("", encoding="utf-8")
    (tmp_path / "y.CEV").write_text("", encoding="utf-8")
    assert [p.name for p in fotografia.arquivos(tmp_path)] == ["x.cfg", "y.CEV"]


def test_registro_que_nao_abre_entra_na_foto_como_erro(tmp_path):
    ruim = tmp_path / "ruim.CEV"
    ruim.write_text("=>", encoding="utf-8")
    assert "erro" in fotografia.foto_de(ruim)


_AMOSTRAS = os.environ.get("OSCLAB_AMOSTRAS", "").strip()
_BASE = os.environ.get("OSCLAB_FOTOGRAFIA", "").strip()


@pytest.mark.skipif(not (_AMOSTRAS and _BASE and Path(_BASE).is_file()),
                    reason="defina OSCLAB_AMOSTRAS e OSCLAB_FOTOGRAFIA (a última foto)")
def test_nada_que_o_programa_conclui_do_banco_mudou_sem_ninguem_ver(tmp_path):
    agora = tmp_path / "agora.jsonl"
    fotografia.tirar(Path(_AMOSTRAS), agora)
    dif = fotografia.comparar(fotografia.carregar(Path(_BASE)), fotografia.carregar(agora))
    assert not dif, (f"{len(dif)} diferença(s) contra a última foto — confira cada uma e, "
                     f"se for o esperado, tire a foto de novo. Primeiras: {dif[:5]}")
