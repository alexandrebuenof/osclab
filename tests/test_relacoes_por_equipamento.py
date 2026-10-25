"""TC e TP por EQUIPAMENTO, no lugar do «vários» da tira de fatos.

Maquete 5 de «relacoes-10», escolha dele em 22/10/2026 (o emparelhamento por
lado, que veio antes, ele recusou). Registros sintéticos montados aqui mesmo:
nomes no jeito do SIPROTEC (`equipamento:sinal`) e no jeito da SEL (só a letra
do terminal).
"""

from __future__ import annotations

import numpy as np

from osclab.formats.base import AnalogChannel, Record, SampleRate
from osclab.library import acervo


def _registro(canais_def, device_id: str = "") -> Record:
    canais = tuple(
        AnalogChannel(index=i, name=nome, phase=fase, unit=unidade,
                      primary=prim, secondary=sec, scaling="S")
        for i, (nome, fase, unidade, prim, sec) in enumerate(canais_def))
    n = 200
    t = np.arange(n) / 2000.0
    dados = np.vstack([np.sin(2 * np.pi * 60 * t + i) for i in range(len(canais))])
    return Record(source=None, format_name="teste", line_frequency=60.0,
                  device_id=device_id, analog_channels=canais,
                  sample_rates=(SampleRate(rate_hz=2000.0, last_sample=n),),
                  analog=dados, time=t)


def _trinca(prefixo, sufixo, unidade, prim, sec):
    return [(f"{prefixo}{f}{sufixo}", f, unidade, prim, sec) for f in "ABC"]


SIEMENS = ([(f"TC BUC 69kV:I {f}", f, "A", 400, 5) for f in "ABC"]
           + [("TC BUC 69kV:3I0", "", "A", 400, 5)]
           + [(f"TC EXT 34-5kV:I {f}", f, "A", 800, 5) for f in "ABC"]
           + [("TC X0 NEUTRO:Ix", "", "A", 1600, 5)]
           + [(f"TPBP 69kV:V {f}", f, "V", 69000, 115) for f in "ABC"]
           + [(f"TPBP 34-5kV:V {f}", f, "V", 34500, 115) for f in "ABC"]
           + [("PTD1:87T:General:I diff.:phs A", "A", "I/IrObj", 0.01, 0.01)])


def test_um_TC_e_um_TP_continuam_como_sempre():
    r = _registro(_trinca("I", "W", "A", 240, 1) + _trinca("V", "Y", "V", 1200, 1)
                  + [("VDC1", "", "V", 1, 1)])
    assert acervo.relacoes_por_equipamento(r) == []


def test_no_siprotec_o_rotulo_e_o_nome_antes_dos_dois_pontos():
    fichas = acervo.relacoes_por_equipamento(_registro(SIEMENS))
    pares = [(f["equipamento"], f"{f['tipo']} {f['relacao']}") for f in fichas]
    assert pares == [("TC BUC 69kV", "TC 400 : 5"), ("TC EXT 34-5kV", "TC 800 : 5"),
                     ("TC X0 NEUTRO", "TC 1.600 : 5"), ("TPBP 69kV", "TP 69.000 : 115"),
                     ("TPBP 34-5kV", "TP 34.500 : 115")]
    # O 3I0 do mesmo equipamento entra na ficha dele, e não vira outra.
    assert len(fichas[0]["canais"]) == 4


def test_na_sel_o_rotulo_e_o_nome_da_trinca():
    """Sem nome de equipamento no arquivo, vale o da trinca (`I*S`), o mesmo do
    editor de grupos. Nenhum TC é posto ao lado de TP nenhum."""
    r = _registro(_trinca("I", "S", "A", 40, 1) + _trinca("I", "T", "A", 120, 1)
                  + _trinca("V", "V", "V", 1200, 1) + _trinca("V", "Z", "V", 300, 1))
    pares = [(f["equipamento"], f"{f['tipo']} {f['relacao']}")
             for f in acervo.relacoes_por_equipamento(r)]
    assert pares == [("I*S", "TC 40 : 1"), ("I*T", "TC 120 : 1"),
                     ("V*V", "TP 1.200 : 1"), ("V*Z", "TP 300 : 1")]


def test_o_modelo_do_siprotec_e_familia_e_numero_de_serie():
    """O SIPROTEC grava o NÚMERO DE SÉRIE onde a SEL grava a FID. Mostrá-lo
    como modelo era errado, e escrever «7UT85» seria palpite."""
    r = _registro(SIEMENS, device_id="BM2502009181")
    assert acervo._modelo(r.device_id, r) == "SIPROTEC 5 · nº de série BM2502009181"
    # Sem os canais no jeito do SIPROTEC, não se afirma família nenhuma.
    outro = _registro(_trinca("I", "W", "A", 240, 1), device_id="BM2502009181")
    assert acervo._modelo(outro.device_id, outro) == "BM2502009181"
    # E a SEL continua como era.
    assert acervo._modelo("FID=SEL-421-4-R325-V0-Z026014-D20180329") == "SEL-421-4"
