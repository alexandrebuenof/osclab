"""Vários registros na mesma aba: alinhamento, ids com a letra, painéis e leitura.

Dois registros sintéticos do mesmo curto, como os dois terminais de uma linha:
o A grava a falta em 100 ms do início dele; o B, gravado a outra taxa e com o
relógio 2,3 ms adiantado, grava a mesma falta em 120 ms do início dele.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta

import numpy as np

from osclab.formats.base import AnalogChannel, Record, SampleRate, StatusChannel
from osclab.plot import alinhamento, janela, leitura, paineis, varios

F0 = 60.0


def _registro(taxa: float, t_falta: float | None, inicio: datetime,
              disparo: float = 0.050, sufixo: str = "W") -> Record:
    n = int(0.30 * taxa)
    t = np.arange(n) / taxa
    w = 2 * math.pi * F0
    linhas = []
    for k, fase in enumerate("ABC"):
        ang = (0.0, -2.094, 2.094)[k]
        amp = np.full(n, 100.0)
        if t_falta is not None and fase == "A":
            amp = np.where(t >= t_falta, 3000.0, 100.0)
        linhas.append((f"I{fase}{sufixo}", fase, amp * np.sin(w * t + ang)))
    canais = tuple(AnalogChannel(index=i, name=nome, unit="A", phase=fase,
                                 primary=600.0, secondary=5.0, scaling="P")
                   for i, (nome, fase, _) in enumerate(linhas))
    trip = np.zeros((1, n), dtype=np.uint8)
    if t_falta is not None:
        trip[0, t >= t_falta + 0.03] = 1
    return Record(
        source=None, format_name="teste", station="SE TESTE", line_frequency=F0,
        start_time=inicio, trigger_time=inicio + timedelta(seconds=disparo),
        analog_channels=canais,
        status_channels=(StatusChannel(index=0, name="TRIP"),),
        sample_rates=(SampleRate(rate_hz=taxa, last_sample=n),),
        analog=np.array([x[2] for x in linhas]), status=trip, time=t,
    )


INICIO = datetime(2026, 10, 22, 14, 52, 3)
A = _registro(2000.0, 0.100, INICIO)
# O mesmo evento: a falta aconteceu no mesmo instante ABSOLUTO, mas o relógio
# do B está 2,3 ms adiantado e o registro dele começa 20 ms antes.
B = _registro(1000.0, 0.120, INICIO - timedelta(seconds=0.020)
              + timedelta(seconds=0.0023), sufixo="X")


def test_alinhar_pela_falta_poe_as_duas_faltas_no_mesmo_instante():
    d = alinhamento.deslocamento(A, B, "falta")
    assert d["por"] == "falta"
    assert abs(d["d"] - 0.020) <= 0.001 + 1e-9          # uma amostra do B
    assert d["precisao_ms"] == 1.0                        # a amostra do mais lento
    # A diferença de relógio aparece SEMPRE: 2,3 ms, a menos de uma amostra.
    assert abs(d["relogio_ms"] - 2.3) <= 1.0


def test_sem_falta_num_deles_o_alinhamento_cai_para_o_disparo():
    sem_falta = _registro(1000.0, None, INICIO, disparo=0.070, sufixo="X")
    d = alinhamento.deslocamento(A, sem_falta, "falta")
    assert d["por"] == "disparo"
    assert abs(d["d"] - 0.020) < 1e-9


def test_alinhar_pela_hora_usa_o_carimbo_de_cada_arquivo():
    d = alinhamento.deslocamento(A, B, "hora")
    assert d["por"] == "hora"
    assert abs(d["d"] - (0.020 - 0.0023)) < 1e-9
    assert d["precisao_ms"] is None


def test_o_arranjo_padrao_e_um_conjunto_por_IED_com_a_letra_no_id():
    layout = varios.padrao([("A", A), ("B", B)])
    analogicos = [p for p in layout if p.tipo == paineis.ANALOGICO]
    digitais = [p for p in layout if p.tipo == paineis.DIGITAL]
    assert len(analogicos) == 2 and len(digitais) == 2
    assert all(not s.startswith("B|") for s in analogicos[0].sinais)
    assert all(s.startswith("B|") for s in analogicos[1].sinais)
    # Os digitais vêm no FIM, um por IED.
    assert layout[-2:] == digitais


def _pacote(layout=None):
    return varios.montar_janela(A, [(B, "terminal B", "shaB")], alinhar="falta",
                                montar=janela.montar, apelido_a="terminal A",
                                sha_a="shaA", de=0.0, ate=0.25, colunas=200,
                                layout=layout)


def test_a_janela_traz_os_sinais_do_B_no_tempo_da_aba():
    p = _pacote()
    do_b = [s for painel in p["paineis"] if painel["tipo"] == paineis.ANALOGICO
            for s in painel["sinais"] if s.get("ied") == "B"]
    assert do_b and all(s["id"].startswith("B|") for s in do_b)
    # O tempo do B foi trazido para o eixo da aba: o primeiro ponto dele é
    # o início da janela pedida, e não o início do registro B.
    assert abs(do_b[0]["tempo"][0] - 0.0) < 0.002
    assert any(x["ied"] == "B" and x["id"].startswith("B|") for x in p["catalogo"])
    assert [x["letra"] for x in p["ieds"]] == ["A", "B"]
    assert p["ieds"][1]["alinhado_por"] == "falta"
    nomes = [painel["nome"] for painel in p["paineis"]]
    assert any(n.endswith("· IED A") for n in nomes)
    assert any(n.endswith("· IED B") for n in nomes)


def test_um_painel_pode_misturar_sinais_dos_dois_IEDs():
    misto = paineis.Painel(id="p1", tipo=paineis.ANALOGICO, nome="",
                           sinais=("c0:instantaneo", "B|c0:instantaneo"))
    p = _pacote([misto])
    painel = p["paineis"][0]
    assert [s.get("ied", "A") for s in painel["sinais"]] == ["A", "B"]
    assert all(s["eixo"] == "esq" for s in painel["sinais"])
    # A escala cobre os dois: a falta de 3000 A dos dois cabe.
    assert painel["maximo"] >= 3000.0


def test_o_cursor_le_cada_registro_na_PROPRIA_amostra_do_mesmo_instante():
    layout = [paineis.Painel(id="p1", tipo=paineis.ANALOGICO, nome="",
                             sinais=("c0:instantaneo", "B|c0:instantaneo"))]
    t_a = 0.110                                     # 10 ms depois da falta no A
    r = varios.ler(A, [(B, "terminal B", "shaB")], [(t_a, 0, 0.0), (None, 0, 0.0)],
                   alinhar="falta", ler=leitura.em, layout=layout, lado="arquivo",
                   refere=None, filtro=False, contas=None)
    linhas = r["cursores"][0]["sinais"]
    assert "B|c0:instantaneo" in linhas and linhas["B|c0:instantaneo"]["ied"] == "B"
    d = alinhamento.deslocamento(A, B, "falta")["d"]
    i_b = int(np.argmin(np.abs(B.time - (r["cursores"][0]["t"] + d))))
    assert abs(linhas["B|c0:instantaneo"]["valor"] - B.analog[0, i_b]) < 1e-6


def test_um_painel_digital_mistura_tiras_dos_dois_IEDs_cada_uma_no_seu_tempo():
    digital = paineis.Painel(id="d1", tipo=paineis.DIGITAL, nome="Digitais",
                             sinais=("0", "B|0"))
    p = _pacote([digital])
    tiras = p["paineis"][0]["tiras"]
    assert [t.get("ied", "A") for t in tiras] == ["A", "B"]
    assert tiras[1]["id"] == "B|0" and tiras[1]["tempo"]
    assert "tempo" not in tiras[0]


def test_o_espectro_mistura_sinais_dos_dois_IEDs():
    espectro = paineis.Painel(id="h1", tipo=paineis.HARMONICOS, nome="",
                              sinais=("c0:instantaneo", "B|c0:instantaneo"))
    p = _pacote([espectro])
    assert [s.get("ied", "A") for s in p["paineis"][0]["sinais"]] == ["A", "B"]
    r = varios.ler(A, [(B, "terminal B", "shaB")], [(0.11, 0, 0.0), (None, 0, 0.0)],
                   alinhar="falta", ler=leitura.em, layout=[espectro], lado="arquivo",
                   refere=None, filtro=False, contas=None)
    assert r["cursores"][0]["sinais"]["B|c0:instantaneo"].get("harmonicos") is not None


# ---------------------------------------------------------------------------
# O plano alfa com um terminal em cada registro
# ---------------------------------------------------------------------------

def _terminal(taxa: float, inicio: datetime, sinal: float, sufixo: str,
              relogio: str = "relógio travado, operação normal",
              erro: float = 0.0, fuso: float | None = 0.0) -> Record:
    """Uma trinca com 300 A de carga atravessando e 4 kA de falta EXTERNA em
    100 ms (hora absoluta comum). O remoto vê a mesma corrente com o sinal
    trocado: ela entra por um terminal e sai pelo outro."""
    n = int(0.25 * taxa)
    t = np.arange(n) / taxa
    absoluto = (inicio - INICIO).total_seconds() + t       # o mesmo relógio
    w = 2 * math.pi * F0
    amp = np.where(absoluto >= 0.100, 4000.0, 300.0)
    linhas = [sinal * amp * np.sin(w * absoluto + ang - 0.4)
              for ang in (0.0, -2.094, 2.094)]
    canais = tuple(AnalogChannel(index=i, name=f"I{f}{sufixo}", unit="A", phase=f,
                                 primary=600.0, secondary=5.0, scaling="P")
                   for i, f in enumerate("ABC"))
    return Record(
        source=None, format_name="teste", station="SE TESTE", line_frequency=F0,
        # `erro`: o relógio do relé carimba o início fora da hora verdadeira.
        start_time=inicio + timedelta(seconds=erro),
        trigger_time=inicio + timedelta(seconds=erro + 0.05),
        analog_channels=canais, sample_rates=(SampleRate(rate_hz=taxa, last_sample=n),),
        analog=np.array(linhas), time=t, time_quality=relogio, fuso_horas=fuso,
    )


def _plano_entre(local_reg, remoto_reg, alinhar, **kw):
    alfa_painel = paineis.Painel(id="pa", tipo=paineis.ALFA, nome="",
                                 sinais=("A",), **kw)
    p = varios.montar_janela(local_reg, [(remoto_reg, "remoto", "shaR")],
                             alinhar=alinhar, montar=janela.montar,
                             de=0.0, ate=0.2, colunas=200, layout=[alfa_painel])
    return p["paineis"][0]


def test_alfa_com_terminal_em_outro_registro_e_relogio_sincronizado_fica_em_180():
    # O remoto começa 0,3 amostra depois: nenhuma amostra coincide, e a
    # correção fina de ângulo é o que segura os 180°.
    loc = _terminal(2000.0, INICIO, +1.0, "W")
    rem = _terminal(1000.0, INICIO + timedelta(seconds=0.0003), -1.0, "X")
    p = _plano_entre(loc, rem, "hora")
    assert p["entre_ieds"] and p["remoto"]["ied"] == "B"
    assert p["incerteza_graus"] < 0.1
    tr = p["trajetorias"]["A"]
    k = int(np.argmin(np.abs(np.asarray(p["pontos"]["t"]) - 0.150)))
    assert abs(tr["modulo"][k] - 1.0) < 1e-3
    assert abs(abs(tr["angulo"][k]) - 180.0) < 0.05
    assert tr["decisao"][k] == "restringe"


def test_sem_relogio_sincronizado_a_incerteza_e_de_uma_amostra_e_o_refino_corrige():
    loc = _terminal(2000.0, INICIO, +1.0, "W", relogio="")
    # O relógio do remoto carimba 0,7 ms adiantado: pela hora, o ângulo sai
    # 15° torto, e o painel diz que não sabe a precisão.
    rem = _terminal(1000.0, INICIO, -1.0, "X", relogio="", erro=0.0007)
    sem = _plano_entre(loc, rem, "hora")
    assert sem["incerteza_graus"] is None
    k0 = int(np.argmin(np.abs(np.asarray(sem["pontos"]["t"]) - 0.150)))
    assert abs(abs(sem["trajetorias"]["A"]["angulo"][k0]) - 180.0) > 10
    refinado = _plano_entre(loc, rem, "hora", refinar=True)
    assert refinado["refino"]["aplicado"]
    tr = refinado["trajetorias"]["A"]
    k = int(np.argmin(np.abs(np.asarray(refinado["pontos"]["t"]) - 0.150)))
    assert abs(abs(tr["angulo"][k]) - 180.0) < 0.5


def test_alinhar_pela_hora_leva_os_dois_carimbos_ao_UTC():
    # O mesmo instante: um relé carimba em UTC, o outro em hora local (−4).
    utc = _terminal(2000.0, INICIO, +1.0, "W", fuso=0.0)
    local = _terminal(1000.0, INICIO, -1.0, "X", fuso=-4.0)
    local = replace(local, start_time=local.start_time - timedelta(hours=4),
                    trigger_time=local.trigger_time - timedelta(hours=4))
    d = alinhamento.deslocamento(utc, local, "hora")
    assert abs(d["d"]) < 1e-6 and d["fuso_declarado"]
    assert abs(d["relogio_ms"]) < 1.0
    p = _plano_entre(utc, local, "hora")
    assert p["incerteza_graus"] < 0.1


def test_sem_fuso_declarado_nao_se_afirma_precisao_e_o_rodape_diz_por_que():
    a = _terminal(2000.0, INICIO, +1.0, "W", fuso=None)
    b = _terminal(1000.0, INICIO, -1.0, "X", fuso=None)
    p = _plano_entre(a, b, "hora")
    assert p["incerteza_graus"] is None
    assert "fuso" in p["rodape"][0]


def test_relogios_travados_de_fabricantes_diferentes_avisam_do_filtro_de_entrada():
    a = replace(_terminal(2000.0, INICIO, +1.0, "W"), device_id="SEL-421")
    b = replace(_terminal(1000.0, INICIO, -1.0, "X"), device_id="SIPROTEC 7SA87")
    p = _plano_entre(a, b, "hora")
    assert any("filtro de entrada" in linha for linha in p["rodape"])
