"""O «alinhar por» de 21/11/2026: a hora que trava quando não cabe, os
alertas da hora e do disparo, e o relógio por extenso.

Sem fixture, como o `test_falta` (de onde vem o registro sintético).
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

from osclab.plot import alinhamento
from tests.test_falta import _registro


def _outro(desvio: timedelta, *, disparo_s: float | None = None):
    """O mesmo evento, com o relógio do outro relé `desvio` adiantado."""
    a = _registro("A")
    b = dataclasses.replace(a, start_time=a.start_time + desvio)
    if disparo_s is not None:
        a = dataclasses.replace(a, trigger_time=a.start_time + timedelta(seconds=disparo_s))
        b = dataclasses.replace(b, trigger_time=b.start_time + timedelta(seconds=disparo_s))
    return a, b


def test_relogios_meses_em_desacordo_travam_a_hora_e_valem_o_seguinte():
    a, b = _outro(timedelta(days=-227, hours=-15))
    assert alinhamento.hora_cabe(a, b) is False
    desl = alinhamento.deslocamento(a, b, "hora")
    # Pela hora o B iria 227 dias para longe: vale o critério seguinte.
    assert desl["por"] != "hora"
    assert abs(desl["d"]) < 1.0
    assert desl["relogio_texto"] == "227 dias 15 h atrás"


def test_relogios_proximos_a_hora_vale_e_avisa_a_diferenca():
    a, b = _outro(timedelta(milliseconds=40))
    assert alinhamento.hora_cabe(a, b) is True
    desl = alinhamento.deslocamento(a, b, "hora")
    assert desl["por"] == "hora"
    assert "40,0 ms" in desl["aviso"]


def test_o_disparo_alinha_e_avisa_sem_bloquear():
    a, b = _outro(timedelta(0), disparo_s=0.05)
    desl = alinhamento.deslocamento(a, b, "disparo")
    assert desl["por"] == "disparo"
    assert "seq. negativa" in desl["aviso"]
    # E o início da falta não avisa nada.
    assert alinhamento.deslocamento(a, b, "falta")["aviso"] == ""


def test_o_relogio_por_extenso_escolhe_a_unidade_que_se_le():
    t = alinhamento.texto_do_relogio
    assert t(None) == ""
    assert t(40.0) == "40,0 ms à frente"
    assert t(-2345.0) == "2,35 s atrás"
    assert t(725_000.0) == "12 min 5 s à frente"
    assert t(-11_520_000.0) == "3 h 12 min atrás"
    assert t(86_400_000.0) == "1 dia 0 h à frente"


def test_a_tira_mostra_o_aviso_curto_e_o_inteiro_fica_no_hover():
    a, b = _outro(timedelta(milliseconds=40), disparo_s=0.05)
    hora = alinhamento.deslocamento(a, b, "hora")
    assert hora["aviso_curto"] == "relógios diferem 40,0 ms"
    assert alinhamento.deslocamento(a, b, "disparo")["aviso_curto"] == \
        "cada relé dispara num instante seu"
    assert alinhamento.deslocamento(a, b, "falta")["aviso_curto"] == ""
