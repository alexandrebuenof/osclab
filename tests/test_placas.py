"""Os digitais que o relé grava e a placa dele não tem (`[IOBOARDS]` do `.hdr`).

O caso que motivou: um SEL-487E-3 (TR01 da SE Jangada, 24/10/2026) com a placa
da posição 2 de 8 entradas e 15 saídas grava IN301–IN324 e OUT301–OUT316, e
nos bits de IN317–IN324 sai um contador que avança a cada amostra.
"""

from __future__ import annotations

import numpy as np

from osclab.formats import ajustes
from osclab.formats.base import Record, SampleRate, StatusChannel
from osclab.plot import digitais

HDR = """MEDIA TR01_UPC2 - 34.5kV
[INFO]
RELAYTYPE=SEL-487E-3
[IOBOARDS]
INT4_E, , , 24, 8, 0, 0, 1
CFSINT7, , , 8, 15, 0, 0, 2
[G1]
"SID","SE JANGADA"
"""


def test_le_as_placas_por_serie():
    assert ajustes.placas_da_sel(HDR) == {2: (24, 8), 3: (8, 15)}


def test_sem_a_secao_nao_decide_nada():
    assert ajustes.placas_da_sel('"SID","SE X"\n') is None


def test_marca_so_o_que_a_placa_nao_tem(tmp_path):
    (tmp_path / "evento.hdr").write_text(HDR, encoding="utf-8")
    nomes = ["IN101", "IN124", "IN201", "IN224", "IN301", "IN308", "IN309", "IN324",
             "OUT208", "OUT315", "OUT316", "IN401", "TRIP", "OUT101"]
    fora = ajustes.digitais_sem_placa(tmp_path, ["evento.hdr"], nomes)
    # A série 100 é a placa principal: a seção não a descreve e ela nunca sai.
    # A série 400 não tem placa nenhuma.
    assert fora == {"IN309", "IN324", "OUT316", "IN401"}


def test_sem_hdr_nenhum_canal_e_marcado(tmp_path):
    assert ajustes.digitais_sem_placa(tmp_path, [], ["IN324"]) == frozenset()


def test_o_contador_nao_entra_na_tela_padrao_e_continua_na_busca():
    n = 64
    contador = ((np.arange(n) >> 0) & 1).astype(np.int8)
    trip = np.zeros(n, dtype=np.int8)
    trip[30:] = 1
    registro = Record(
        source=None, format_name="teste",
        status_channels=(StatusChannel(index=0, name="IN317"),
                         StatusChannel(index=1, name="TRIP")),
        sample_rates=(SampleRate(rate_hz=1920.0, last_sample=n),),
        status=np.vstack([contador, trip]), time=np.arange(n) / 1920.0,
        digitais_sem_placa=frozenset({"IN317"}))
    assert digitais.escolhidos_por_padrao(registro) == [1]
    por_nome = {r.nome: r for r in digitais.resumos(registro)}
    assert por_nome["IN317"].sem_placa and por_nome["IN317"].mudou
    assert not por_nome["TRIP"].sem_placa
