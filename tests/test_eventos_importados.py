"""As listas de eventos IMPORTADAS (SER, .eev, texto) e a trilha.

Os textos têm a FORMA dos arquivos de relé e conteúdo inventado.
"""

from __future__ import annotations

from datetime import date, datetime

from osclab.formats import eventos
from osclab.plot import eventos as eventos_plot

EEV = (
    "Source, Date/Time, Event, CauseOfEvent, EventCode, F1 Ia (A),F1 Ia Angle (°)\r\n"
    "RX1, Nov 5 2026 08:14:25.462000, 12, TRIP BUS 1 OP (Trip Bus 1 Trip OP), 00c60101, "
    "2400.1,-89.4\r\n"
    "RX1, Nov 5 2026 08:14:25.403000, 11, PARTIDA FASE A On (VO 1), 00000601, 2100.0,-92.0\r\n"
    "Source, Date/Time, Event, CauseOfEvent, EventCode, F1 Ia (A),F1 Ia Angle (°)\r\n"
    "RX2, Nov 4 2026 23:59:59.999999, 7, Setting Change, 00000000, 50.0,-90.0\r\n"
)

SER = """\
SEL-311C                       Date: 11/05/26    Time: 10:14:55.000
LT TESTE

#      DATE      TIME          ELEMENT               STATE

3      11/05/26  10:14:25.460  TRIP                  Asserted
2      11/05/26  10:14:25.404  51G1                  Asserted
1      11/05/26  10:14:25.403  50P1                  Asserted
"""


def test_eev_le_os_blocos_a_causa_e_as_medidas():
    lista = eventos.de_eev(EEV, "x.eev")
    assert lista is not None and lista.tempo == "absoluto"
    assert lista.fontes == ("RX1", "RX2")
    assert lista.colunas_extras == ("F1 Ia (A)", "F1 Ia Angle (°)")
    trip, partida, ajuste = lista.eventos
    assert trip.descricao == "TRIP BUS 1 OP" and trip.operando == "Trip Bus 1 Trip OP"
    assert partida.descricao == "PARTIDA FASE A" and partida.valor == "On"
    assert ajuste.descricao == "Setting Change" and ajuste.operando == ""
    assert trip.quando == datetime(2026, 11, 5, 8, 14, 25, 462000)
    assert ajuste.quando.microsecond == 999999
    assert trip.extras == ("2400.1", "-89.4") and trip.linha == 2


def test_texto_qualquer_nao_vira_eev():
    assert eventos.de_eev(SER) is None


def test_ser_pula_o_cabecalho_e_a_data_ambigua_e_sugerida_pela_do_registro():
    lista = eventos.de_texto_com_hora(SER, "ser.txt", referencia=date(2026, 11, 5))
    assert lista is not None and len(lista.eventos) == 3       # o «Date:» do topo não entra
    assert lista.ordem_da_data == "MDA" and lista.origem_da_ordem == "sugerido"
    assert lista.eventos[0].descricao == "TRIP" and lista.eventos[0].valor == "Asserted"
    assert lista.eventos[0].quando == datetime(2026, 11, 5, 10, 14, 25, 460000)
    maio = eventos.de_texto_com_hora(SER, "ser.txt", referencia=date(2026, 5, 11))
    assert maio.ordem_da_data == "DMA"
    digitada = eventos.de_texto_com_hora(SER, "ser.txt", referencia=date(2026, 5, 11),
                                         ordem="MDA")
    assert digitada.origem_da_ordem == "digitado"


def test_dia_maior_que_doze_decide_sozinho():
    texto = "Nº;Fecha;Hora;Suceso;Estado\n" + "\n".join(
        f"{k};25/10/2026;10:00:0{k}.000;Arranque {k};Activado" for k in range(1, 5))
    lista = eventos.de_texto_com_hora(texto, "s.txt")
    assert lista.ordem_da_data == "DMA" and lista.origem_da_ordem == "lido"
    assert lista.eventos[0].numero == "1" and lista.eventos[0].valor == "Activado"


def test_texto_sem_data_por_linha_vai_cru(tmp_path):
    caminho = tmp_path / "log.txt"
    caminho.write_text("OC#1 T+0000102ms CH17 ^ PART\nOC#2 T+0000161ms CH02 ^ TRIP\n",
                       encoding="utf-8")
    lista = eventos.ler_arquivo_de_eventos(caminho)
    assert not lista.reconhecida and "OC#1" in lista.cru


def test_deslocamento_le_e_escreve():
    assert eventos_plot.ler_deslocamento("+4:00") == 4.0
    assert eventos_plot.ler_deslocamento("−3:30") == -3.5
    assert abs(eventos_plot.ler_deslocamento("0:00:00,012") - 0.012 / 3600) < 1e-12
    assert eventos_plot.ler_deslocamento("abc") is None
    assert eventos_plot.texto_do_deslocamento(4.0) == "+4:00"
    assert eventos_plot.texto_do_deslocamento(-3.5) == "−3:30"


def test_importada_e_lida_do_texto_sem_gravar_nada():
    """Decisão de 11/11/2026: a lista importada vem no pedido, como texto."""
    lista = eventos.ler_texto_de_eventos(EEV, "x.eev")
    assert lista.reconhecida and lista.fontes == ("RX1", "RX2")
    ser = eventos.ler_texto_de_eventos(SER, "ser.txt", referencia=date(2026, 11, 5))
    assert ser.reconhecida and ser.ordem_da_data == "MDA"
    cru = eventos.ler_texto_de_eventos("sem data nem hora\nnada\n", "log.txt")
    assert not cru.reconhecida and "sem data" in cru.cru


def _pacote(letra, tempos, fonte="", gravacao=(0.0, 0.6)):
    return {"letra": letra, "tem": True, "gravacao": list(gravacao),
            "fontes": [{"nome": fonte}] if fonte else [],
            "eventos": [{"t": t, "fonte": fonte} for t in tempos]}


def test_trilha_conta_a_rajada_num_intervalo_so_e_o_evento_solto_continua_visivel():
    rajada = [0.162] * 20
    dist = eventos_plot.distribuicao([_pacote("A", rajada + [0.5])], 400)
    assert dist["total"] == 21 and dist["maximo"] == 20
    assert sum(dist["contagens"]) == 21
    soltos = [h for h, c in zip(dist["h"], dist["contagens"], strict=True) if c == 1]
    # linear: o maior intervalo vale 1, um evento contra vinte vale 1/20
    assert max(dist["h"]) == 1.0
    assert soltos and abs(soltos[0] - 1 / 20) < 1e-3


def test_trilha_de_varios_dias_escolhe_um_intervalo_largo_e_poucas_barras():
    dias = [-4 * 86400 + k * 300.0 for k in range(4000)] + [0.1, 0.2]
    dist = eventos_plot.distribuicao([_pacote("A", dias)], 600)
    assert dist["passo"] >= 3600 and len(dist["contagens"]) <= 600 // 4 + 2
    assert dist["total"] == 4002 and dist["passo_texto"].endswith("h")


def test_trilha_respeita_o_rele_escondido_e_separa_por_ied():
    a = _pacote("A", [0.1, 0.2], fonte="AL12")
    b = _pacote("B", [0.15], gravacao=(0.0, 0.6))
    dist = eventos_plot.distribuicao([a, b], 400, escondidos=["A|AL12"])
    assert dist["total"] == 1 and set(dist["pilhas"]) == {"B"}
    dist = eventos_plot.distribuicao([a, b], 400)
    assert set(dist["pilhas"]) == {"A", "B"}


def test_trilha_ampliada_conta_so_o_trecho_da_gravacao():
    dist = eventos_plot.distribuicao([_pacote("A", [-500.0, 0.1, 0.3, 900.0])], 400,
                                     faixa=(0.0, 0.6))
    assert dist["total"] == 2 and dist["passo"] <= 0.01
