"""Testes do plano de impedância.

**Sem fixture de propósito.** O `tudo.py` pula em silêncio toda função que
peça fixture — 239 de 646 testes —, e um teste que nunca roda é pior que
teste nenhum: ele dá a sensação de cobertura sem a cobertura. Enquanto o
harness não aprender a montar as fixtures, o que se escreve aqui monta o
registro na mão.
"""

from __future__ import annotations

import cmath
import math
from datetime import datetime

import numpy as np

from osclab.formats.base import AnalogChannel, Record, SampleRate
from osclab.plot import impedancia


def _avisos(pacote) -> list[str]:
    """O texto inteiro de cada aviso — o curto da ficha mais o do hover.

    O aviso tem duas alturas desde 20/10/2026 (ver `impedancia._aviso`): a
    ficha do rodapé mostra o `curto` e guarda o `longo` no hover. O teste
    olha os dois juntos: o que importa é que a explicação EXISTA em algum
    lugar, não em qual dos dois campos ela caiu.
    """
    return [f"{a['curto']} {a['longo']}" for a in pacote["avisos"]]


# ---------------------------------------------------------------------------
# Um registro de mentirinha, igual ao das amostras fictícias
# ---------------------------------------------------------------------------

TAXA = 1920.0
F0 = 60.0
RTC, RTP = 120.0, 1200.0
ZL = complex(0.12, 0.48) * 42.0                     # 20,78 Ω ∠76° primários
Z0L = ZL * 3.0 * cmath.exp(1j * math.radians(-4))
K0 = (Z0L - ZL) / (3.0 * ZL)
P_FALTA = 0.62
VN = 138000 / math.sqrt(3)
T_FALTA = 0.1333


def _registro(com_falta: bool = True, lado_primario: bool = True) -> Record:
    """VA VB VC IA IB IC IN, com uma falta AN a 62 % da linha."""
    n = int(0.30 * TAXA)
    t = np.arange(n) / TAXA
    z_ate = (1.0 + K0) * ZL * P_FALTA
    ia_falta = cmath.rect(VN, 0) / (ZL * 0.15 + z_ate + 1.5)
    carga = cmath.rect(230.0, math.radians(-18))

    dados = np.zeros((7, n))
    w = 2 * math.pi * F0
    for k in range(n):
        na_falta = com_falta and t[k] >= T_FALTA
        v = [cmath.rect(VN, math.radians(a)) for a in (0, -120, 120)]
        i = [carga * cmath.exp(1j * math.radians(a)) for a in (0, -120, 120)]
        if na_falta:
            i[0] = ia_falta
            v[0] = ia_falta * z_ate + 1.5 * ia_falta
        for c, ph in enumerate(v + i):
            dados[c, k] = abs(ph) * math.sqrt(2) * math.sin(w * t[k] + cmath.phase(ph))
        dados[6, k] = dados[3, k] + dados[4, k] + dados[5, k]

    if not lado_primario:
        dados[:3] /= RTP
        dados[3:] /= RTC

    canais = []
    for idx, (nome, fase, unidade) in enumerate(
            [("VA", "A", "V"), ("VB", "B", "V"), ("VC", "C", "V"),
             ("IA", "A", "A"), ("IB", "B", "A"), ("IC", "C", "A"),
             ("IN", "N", "A")]):
        canais.append(AnalogChannel(
            index=idx, name=nome, phase=fase, unit=unidade,
            primary=(RTP if unidade == "V" else RTC), secondary=1.0, scaling="P"))
    return Record(
        source=None, format_name="teste", station="SE TESTE",
        device_id="SEL-451", line_frequency=F0,
        start_time=datetime(2026, 10, 15, 13, 0, 0),
        analog_channels=tuple(canais),
        sample_rates=(SampleRate(rate_hz=TAXA, last_sample=n),),
        analog=dados, time=t,
    )


AJUSTES = {
    "Z1MAG": "2.08", "Z1ANG": "75.96",
    "Z0MAG": "6.23", "Z0ANG": "71.96",
    "Z1MG": "1.66", "Z2MG": "2.49", "Z3MG": "4.16",
    "Z1P": "1.66", "Z2P": "2.49", "Z3P": "4.16",
    # Em CICLOS, como a SEL escreve: 18 ciclos são 0,30 s a 60 Hz.
    "Z1D": "0.00", "Z2D": "18.000", "Z3D": "60.000",
}

CANAIS_V = {"A": 0, "B": 1, "C": 2}
CANAIS_I = {"A": 3, "B": 4, "C": 5, "N": 6}


# ---------------------------------------------------------------------------
# Os ajustes
# ---------------------------------------------------------------------------

def test_parametros_sai_do_rele_quando_existe():
    r = impedancia.parametros_da_linha(AJUSTES)
    assert r is not None
    assert abs(r.modulo.valor - 2.08) < 1e-9
    assert r.modulo.origem == "lido"
    assert r.modulo.variavel == "Z1MAG"


def test_parametros_cai_na_modelagem_quando_o_arquivo_nao_traz():
    r = impedancia.parametros_da_linha({}, do_estudo=(2.078, 76.0))
    assert r is not None and r.modulo.origem == "modelagem"


def test_sem_parametros_nenhuma_devolve_none():
    assert impedancia.parametros_da_linha({}) is None


def test_k0_sai_de_z0_e_z1():
    achado = impedancia.k0_de(AJUSTES)
    assert achado is not None
    k0, origem, de = achado
    assert origem == "calculado" and "Z0" in de
    # (Z0 − Z1) / 3Z1 com Z0 ≈ 3·Z1 dá módulo perto de 2/3.
    assert 0.6 < abs(k0) < 0.75


def test_k0_pronto_do_rele_tem_precedencia():
    achado = impedancia.k0_de({**AJUSTES, "K0M": "0.75", "K0A": "-3"})
    assert achado is not None and achado[1] == "lido"
    assert abs(abs(achado[0]) - 0.75) < 1e-9


def test_k0_da_zona_1_e_lido_em_par_e_z0f_nao_e_k0():
    """O 311C só escreve `k0M1`/`k0A1`; o 4xx escreve os dois pares. Módulo e
    ângulo saem do MESMO par. E `Z0F` é o limiar do 32G, em ohm."""
    achado = impedancia.k0_de({"K0M1": "0.83", "K0A1": "5.55", "K0A": "-40"})
    assert achado[1] == "lido" and achado[2] == "K0M1 ∠ K0A1"
    assert abs(achado[0] - 0.83 * cmath.exp(1j * math.radians(5.55))) < 1e-9
    assert impedancia.k0_de({"Z0F": "0.50", "Z0FA": "75"}) is None


def test_sem_z0_nao_se_inventa_k0():
    """Sem compensação, a falta à terra sai mais longe do que é — e isso
    tem de virar aviso, não um número plausível."""
    assert impedancia.k0_de({"Z1MAG": "2.08", "Z1ANG": "76"}) is None


def test_zonas_lidas_trazem_a_variavel_do_rele():
    zonas = impedancia.zonas_de(AJUSTES, impedancia.parametros_da_linha(AJUSTES), "AN")
    assert [z.nome for z in zonas] == ["Z1", "Z2", "Z3"]
    assert all(z.alcance.origem == "lido" for z in zonas)
    assert zonas[0].alcance.variavel == "Z1MG"       # laço de TERRA
    # O atraso da SEL é em CICLOS: ler como segundo mostraria 18 s.
    assert zonas[0].tempo == "inst." and zonas[1].tempo == "18 ciclos (0,30 s)"


def test_laco_de_fase_usa_a_variavel_de_fase():
    zonas = impedancia.zonas_de(AJUSTES, impedancia.parametros_da_linha(AJUSTES), "AB")
    assert zonas[0].alcance.variavel == "Z1P"


def test_sem_ajuste_as_zonas_sao_sugeridas_e_dizem_isso():
    rep = impedancia.parametros_da_linha({}, do_estudo=(2.078, 76.0))
    zonas = impedancia.zonas_de({}, rep, "AN")
    assert [z.alcance.origem for z in zonas] == ["sugerido"] * 3
    assert abs(zonas[0].alcance.valor - 2.078 * 0.80) < 1e-6
    assert abs(zonas[1].alcance.valor - 2.078 * 1.20) < 1e-6


def test_sem_parametros_nao_ha_zona_sugerida():
    """Sugerir 80 % de coisa nenhuma seria inventar duas vezes."""
    assert impedancia.zonas_de({}, None, "AN") == []


# ---------------------------------------------------------------------------
# A trajetória
# ---------------------------------------------------------------------------

def _z_na_falta(laco: str = "AN", k0=None, registro=None):
    r = registro if registro is not None else _registro()
    achado = impedancia.k0_de(AJUSTES)
    idx, R, X = impedancia.trajetoria(
        r, CANAIS_V, CANAIS_I, laco,
        (k0 if k0 is not None else (achado[0] if achado else None)),
        0, r.analog.shape[1] - 1, CANAIS_I["N"])
    # Bem dentro da falta, longe do transitório do filtro.
    alvo = int(0.25 * TAXA)
    k = int(np.argmin(np.abs(idx - alvo)))
    return complex(R[k], X[k])


def test_a_falta_cai_onde_foi_posta():
    """62 % da linha, com o desvio do arco — o teste que justifica o módulo."""
    z = _z_na_falta()
    pct = abs(z) / abs(ZL) * 100.0
    assert 60.0 < pct < 68.0, pct
    # o arco puxa o ângulo para baixo do ângulo da linha
    assert 65.0 < math.degrees(math.atan2(z.imag, z.real)) < 76.0


def test_sem_k0_a_falta_parece_mais_longe():
    """É o erro que o aviso de «sem Z0MAG» existe para impedir."""
    com = abs(_z_na_falta())
    sem = abs(_z_na_falta(k0=0j))
    assert sem > com * 1.4, (sem, com)


def test_secundario_da_a_mesma_leitura_dividida_pela_relacao():
    primario = abs(_z_na_falta())
    secundario = abs(_z_na_falta(registro=_registro(lado_primario=False)))
    assert abs(secundario - primario / (RTP / RTC)) < primario * 0.01


def test_sem_falta_a_impedancia_fica_na_carga():
    z = _z_na_falta(registro=_registro(com_falta=False))
    assert abs(z) > abs(ZL) * 5


def test_corrente_de_fuga_nao_vira_impedancia():
    """Depois da abertura sobram miliampères; V/I dispara para o infinito."""
    r = _registro()
    r.analog[3:, int(0.25 * TAXA):] *= 0.001
    idx, R, X = impedancia.trajetoria(r, CANAIS_V, CANAIS_I, "AN",
                                      impedancia.k0_de(AJUSTES)[0],
                                      0, r.analog.shape[1] - 1, CANAIS_I["N"])
    depois = [k for k, n in enumerate(idx) if n > int(0.27 * TAXA)]
    assert depois and all(not math.isfinite(R[k]) for k in depois)


def test_laco_de_fase_sem_falta_entre_fases_fica_longe():
    z = _z_na_falta(laco="BC")
    assert abs(z) > abs(ZL) * 3


def test_a_trajetoria_nao_passa_do_maximo_de_pontos():
    r = _registro()
    idx, _, _ = impedancia.trajetoria(r, CANAIS_V, CANAIS_I, "AN", 0j,
                                      0, r.analog.shape[1] - 1)
    assert idx.size <= impedancia.MAXIMO_DE_PONTOS


def test_laco_desconhecido_levanta():
    try:
        impedancia.trajetoria(_registro(), CANAIS_V, CANAIS_I, "XY", 0j, 0, 10)
    except ValueError:
        return
    raise AssertionError("laço inválido devia levantar")


# ---------------------------------------------------------------------------
# A mho e a entrada nas zonas
# ---------------------------------------------------------------------------

def test_dentro_da_mho_e_a_circunferencia_que_passa_pela_origem():
    # O ponto do alcance está na borda; metade dele, no centro; o dobro, fora.
    alcance, ang = 2.0, 76.0
    ponta = (alcance * math.cos(math.radians(ang)), alcance * math.sin(math.radians(ang)))
    assert impedancia.dentro_da_zona(*ponta, alcance, ang)
    assert impedancia.dentro_da_zona(ponta[0] / 2, ponta[1] / 2, alcance, ang)
    assert not impedancia.dentro_da_zona(ponta[0] * 2, ponta[1] * 2, alcance, ang)
    assert impedancia.dentro_da_zona(0.0, 0.0, alcance, ang)      # a origem está dentro


def test_zona_de_alcance_zero_nao_pega_ninguem():
    assert not impedancia.dentro_da_zona(0.1, 0.1, 0.0, 76.0)


def test_entrada_na_zona_e_o_primeiro_instante_dentro():
    r = _registro()
    rep = impedancia.parametros_da_linha(AJUSTES)
    zonas = impedancia.zonas_de(AJUSTES, rep, "AN")
    idx, R, X = impedancia.trajetoria(r, CANAIS_V, CANAIS_I, "AN",
                                      impedancia.k0_de(AJUSTES)[0],
                                      0, r.analog.shape[1] - 1, CANAIS_I["N"])
    # em secundário, que é a base dos ajustes
    entradas = impedancia.entrada_nas_zonas(idx, R / (RTP / RTC), X / (RTP / RTC),
                                            zonas, rep.angulo.valor)
    assert entradas["Z1"] is not None
    # entrou DEPOIS da falta e dentro de poucos ciclos dela
    assert entradas["Z1"] >= int(T_FALTA * TAXA)
    assert entradas["Z1"] < int((T_FALTA + 0.05) * TAXA)


def test_a_zona_maior_pega_antes_ou_junto_da_menor():
    r = _registro()
    rep = impedancia.parametros_da_linha(AJUSTES)
    zonas = impedancia.zonas_de(AJUSTES, rep, "AN")
    idx, R, X = impedancia.trajetoria(r, CANAIS_V, CANAIS_I, "AN",
                                      impedancia.k0_de(AJUSTES)[0],
                                      0, r.analog.shape[1] - 1, CANAIS_I["N"])
    e = impedancia.entrada_nas_zonas(idx, R / 10.0, X / 10.0, zonas, rep.angulo.valor)
    assert e["Z3"] is not None and e["Z2"] is not None and e["Z1"] is not None
    assert e["Z3"] <= e["Z2"] <= e["Z1"]


# ---------------------------------------------------------------------------
# O pacote da tela
# ---------------------------------------------------------------------------

class _PainelFalso:
    id = "p1"
    nome = "Impedância"
    laco = "AN"
    vinculo = ""


def test_montar_devolve_pontos_zonas_e_parametros():
    r = _registro(lado_primario=False)
    pacote = impedancia.montar(
        r, _PainelFalso(), {"ajustes": [[k, v] for k, v in AJUSTES.items()]},
        "secundario", 0, r.analog.shape[1] - 1)
    assert pacote["tipo"] == "impedancia" and pacote["laco"] == "AN"
    assert pacote["pontos"] and pacote["parametros"]["modulo"] == 2.08
    assert [z["nome"] for z in pacote["zonas"]] == ["Z1", "Z2", "Z3"]
    assert pacote["zonas"][0]["variavel"] == "Z1MG"
    assert abs(pacote["zonas"][0]["pct"] - 1.66 / 2.08 * 100) < 0.01
    assert pacote["entradas"]["Z1"] is not None


def test_montar_sem_ajuste_avisa_que_a_zona_e_sugerida():
    r = _registro(lado_primario=False)
    pacote = impedancia.montar(r, _PainelFalso(), {"ajustes": []},
                               "secundario", 0, r.analog.shape[1] - 1)
    # Sem parâmetros não há zona nenhuma, e o aviso diz o que falta.
    assert pacote["zonas"] == []
    assert any("parâmetros" in a or "Z1MAG" in a for a in _avisos(pacote))


def test_montar_avisa_quando_o_lado_nao_bate_com_o_ajuste():
    """Traçado em primário e zona em secundário: dois desenhos certos no mesmo
    plano dando uma conclusão errada."""
    r = _registro(lado_primario=True)
    pacote = impedancia.montar(
        r, _PainelFalso(), {"ajustes": [[k, v] for k, v in AJUSTES.items()]},
        "primario", 0, r.analog.shape[1] - 1)
    assert any("RTP/RTC" in a for a in _avisos(pacote)), pacote["avisos"]


def test_montar_nunca_levanta_sem_trinca():
    vazio = Record(source=None, format_name="teste",
                   sample_rates=(SampleRate(rate_hz=TAXA, last_sample=0),))
    pacote = impedancia.montar(vazio, _PainelFalso(), {"ajustes": []},
                               "secundario", 0, 0)
    assert pacote["pontos"] == [] and pacote["avisos"]


# ---------------------------------------------------------------------------
# A amarração com o resto do programa
# ---------------------------------------------------------------------------

def test_o_tipo_entrou_na_lista_de_tipos():
    from osclab.plot import paineis
    assert paineis.IMPEDANCIA in paineis.TIPOS


def test_de_json_aceita_o_laco_e_peneira_o_que_nao_existe():
    from osclab.plot import paineis
    lidos = paineis.de_json([
        {"id": "p1", "tipo": "impedancia", "laco": "bc"},
        {"id": "p2", "tipo": "impedancia", "laco": "XY"},
        {"id": "p3", "tipo": "impedancia"},
    ])
    assert [p.laco for p in lidos] == ["BC", "AN", "AN"]


def test_janela_monta_o_painel_de_impedancia():
    """A trajetória tem de sair pela janela, que é de onde a tela a lê."""
    from osclab.plot import janela, paineis
    r = _registro(lado_primario=False)
    arranjo = [paineis.Painel(id="p1", tipo=paineis.IMPEDANCIA,
                              nome="Impedância", laco="AN")]
    pacote = janela.montar(
        r, layout=arranjo, lado="secundario",
        ajustes={"ajustes": [[k, v] for k, v in AJUSTES.items()]})
    painel = pacote["paineis"][0]
    assert painel["tipo"] == "impedancia"
    assert painel["pontos"] and painel["zonas"]
    assert painel["parametros"]["variavel"] == "Z1MAG"


def test_janela_sem_ajuste_nenhum_nao_derruba_a_tela():
    from osclab.plot import janela, paineis
    r = _registro(lado_primario=False)
    arranjo = [paineis.Painel(id="p1", tipo=paineis.IMPEDANCIA, nome="Z")]
    pacote = janela.montar(r, layout=arranjo, lado="secundario")
    painel = pacote["paineis"][0]
    assert painel["zonas"] == [] and painel["avisos"]


def test_em_primario_a_entrada_na_zona_e_convertida_antes_de_comparar():
    """Zona em secundário e traçado em primário: comparar sem converter daria
    «nunca entrou» para uma falta que entrou — errado e calado."""
    r = _registro(lado_primario=True)
    pacote = impedancia.montar(
        r, _PainelFalso(), {"ajustes": [[k, v] for k, v in AJUSTES.items()]},
        "primario", 0, r.analog.shape[1] - 1)
    assert pacote["entradas"]["Z1"] is not None
    assert any("primário" in a.lower() for a in _avisos(pacote))


def test_todo_aviso_tem_o_curto_e_o_longo():
    """A ficha do rodapé mostra o curto; o longo mora no hover.

    Um aviso só com o texto comprido volta a entupir o rodapé, que foi o
    defeito que esta separação resolveu. Um aviso só com o curto deixa o
    usuário sem o porquê.
    """
    r = _registro(lado_primario=True)
    pacote = impedancia.montar(
        r, _PainelFalso(), {"ajustes": [[k, v] for k, v in AJUSTES.items()]},
        "primario", 0, r.analog.shape[1] - 1)
    assert pacote["avisos"]
    for a in pacote["avisos"]:
        assert set(a) == {"curto", "longo", "tom"}, a
        assert a["curto"] and a["longo"] and a["tom"]
        # O curto é CURTO: ele divide a linha do rodapé com as outras fichas.
        assert len(a["curto"]) <= 46, a["curto"]
        assert len(a["longo"]) > len(a["curto"])


def test_o_k0_nao_vira_aviso():
    """Ele é a régua do laço de terra e vai na ficha dos parâmetros, junto do
    número que corrige. Como aviso, ocupava uma linha para dizer duas
    palavras."""
    r = _registro(lado_primario=False)
    sem_z0 = {k: v for k, v in AJUSTES.items() if not k.startswith("Z0")}
    pacote = impedancia.montar(
        r, _PainelFalso(), {"ajustes": [[k, v] for k, v in sem_z0.items()]},
        "secundario", 0, r.analog.shape[1] - 1)
    assert pacote["k0"] is None
    assert not any("k0" in a for a in _avisos(pacote)), pacote["avisos"]


def test_sem_relacao_declarada_o_veredito_e_vazio_e_dito():
    """Sem RTC/RTP não há como comparar bases — e isso vira traço, não zero."""
    r = _registro(lado_primario=True)
    canais = tuple(
        type(c)(index=c.index, name=c.name, unit=c.unit, phase=c.phase,
                primary=1.0, secondary=1.0, scaling="P")
        for c in r.analog_channels
    )
    sem = Record(source=None, format_name="teste", line_frequency=F0,
                 analog_channels=canais,
                 sample_rates=(SampleRate(rate_hz=TAXA, last_sample=r.analog.shape[1]),),
                 analog=r.analog, time=r.time)
    pacote = impedancia.montar(
        sem, _PainelFalso(), {"ajustes": [[k, v] for k, v in AJUSTES.items()]},
        "primario", 0, sem.analog.shape[1] - 1)
    assert set(pacote["entradas"].values()) == {None}
    assert any("o veredito, não" in a for a in _avisos(pacote))


# ---------------------------------------------------------------------------
# A BASE: onde dois desenhos certos dão uma conclusão errada
# ---------------------------------------------------------------------------

def test_a_relacao_sai_dos_ajustes_quando_o_arquivo_nao_declara():
    """Num `.CEV` a relação mora em `CTR`/`PTR`, não no cabeçalho do canal."""
    assert impedancia._relacao_dos_ajustes({"CTR": "120", "PTR": "1200"}) == 10.0
    assert impedancia._relacao_dos_ajustes({"CTRW": "80", "PTRW": "2000"}) == 25.0
    # `1` não é relação: é campo em branco.
    assert impedancia._relacao_dos_ajustes({"CTR": "1", "PTR": "1"}) is None
    assert impedancia._relacao_dos_ajustes({"CTR": "120"}) is None
    assert impedancia._relacao_dos_ajustes({}) is None


def test_em_primario_as_ZONAS_mudam_de_base_e_a_trajetoria_nao():
    """O ajuste é secundário por definição; a medida não se reescreve.

    Sem isto a Z1 de 1,66 Ω secundário apareceria ao lado de uma trajetória
    de 9 Ω primários, e uma falta DENTRO da zona sairia fora dela — errada e
    calada, que é o defeito que este painel existe para não ter.
    """
    r = _registro(lado_primario=True)
    sem_relacao = tuple(
        type(c)(index=c.index, name=c.name, unit=c.unit, phase=c.phase,
                primary=1.0, secondary=1.0, scaling="P")
        for c in r.analog_channels
    )
    reg = Record(source=None, format_name="teste", line_frequency=F0,
                 analog_channels=sem_relacao,
                 sample_rates=(SampleRate(rate_hz=TAXA,
                                          last_sample=r.analog.shape[1]),),
                 analog=r.analog, time=r.time)
    ajustes = [[k, v] for k, v in AJUSTES.items()] + [["CTR", "120"], ["PTR", "1200"]]
    pacote = impedancia.montar(reg, _PainelFalso(), {"ajustes": ajustes},
                               "primario", 0, reg.analog.shape[1] - 1)
    por_nome = {z["nome"]: z for z in pacote["zonas"]}
    # A Z1 do relé é 1,66 Ω secundário; em primário são 16,6.
    assert abs(por_nome["Z1"]["alcance"] - 16.6) < 0.01, por_nome["Z1"]
    # O percentual da linha é o MESMO: ele não depende de base nenhuma.
    assert abs(por_nome["Z1"]["pct"] - 80.0) < 1.0
    assert abs(pacote["parametros"]["modulo"] - 20.8) < 0.1
    # E o veredito volta a existir, porque agora há uma régua só.
    assert pacote["entradas"]["Z1"] is not None
    assert any("RTP/RTC = 10" in a for a in _avisos(pacote))


def test_o_prefixo_do_canal_entra_na_conta():
    """`kV / A` é kΩ. Um plano em kΩ põe a falta mil vezes mais longe.

    O relé grava a tensão em `kV` e a corrente em `A`; dividir as amostras
    cruas uma pela outra dá milhares de ohms, e as zonas — que estão em ohms —
    ficariam num canto invisível do desenho.
    """
    r = _registro(lado_primario=True)
    em_kv = []
    dados = r.analog.copy()
    for c in r.analog_channels:
        if c.unit == "V":
            dados[c.index] = dados[c.index] / 1000.0
            em_kv.append(type(c)(index=c.index, name=c.name, unit="kV",
                                 phase=c.phase, primary=c.primary,
                                 secondary=c.secondary, scaling="P"))
        else:
            em_kv.append(c)
    reg = Record(source=None, format_name="teste", line_frequency=F0,
                 analog_channels=tuple(em_kv),
                 sample_rates=(SampleRate(rate_hz=TAXA,
                                          last_sample=dados.shape[1]),),
                 analog=dados, time=r.time)
    pacote = impedancia.montar(reg, _PainelFalso(),
                               {"ajustes": [[k, v] for k, v in AJUSTES.items()]},
                               "primario", 0, dados.shape[1] - 1)
    na_falta = [q for q in pacote["pontos"]
                if q["r"] is not None and q["t"] > T_FALTA + 0.02]
    assert na_falta, "a trajetória sumiu"
    modulo = math.hypot(na_falta[-1]["r"], na_falta[-1]["x"])
    # Em ohms primários a falta a 62 % de uma linha de 20,8 Ω fica na casa
    # da dezena. Em kΩ ela cairia para 0,0x — e o teste pega isso.
    assert 5.0 < modulo < 40.0, modulo


# ---------------------------------------------------------------------------
# O selo no acervo
# ---------------------------------------------------------------------------

def test_o_resumo_do_acervo_traz_o_tipo_da_falta():
    """O selo do cartão sai do `meta.json`, gravado na importação."""
    from osclab.library import acervo
    campos = {f for f in acervo.Item.__dataclass_fields__}
    assert {"falta_tipo", "falta_confianca", "falta_porques",
            "falta_laco", "classificacao_do_rele"} <= campos


def test_a_versao_do_resumo_subiu_para_refazer_os_antigos():
    """Sem subir, registro já no acervo nasceria sem selo para sempre."""
    from osclab.library import acervo
    assert acervo.RESUMO_ATUAL >= 2


def test_classificar_no_acervo_nunca_derruba_o_envio():
    from osclab.formats.base import Record
    from osclab.library import acervo
    vazio = Record(source=None, format_name="teste")
    saida = acervo._classificar(vazio)
    assert saida["falta_tipo"] == ""


# ---------------------------------------------------------------------------
# A terceira origem: o que o usuário digita
# ---------------------------------------------------------------------------

class _PainelComManuais(_PainelFalso):
    def __init__(self, manuais):
        self.manuais = manuais


def test_a_peneira_recusa_o_que_nao_e_ajuste():
    """A tela manda texto. Um alcance negativo ou um ângulo de 400°
    desenhariam uma característica impossível sem ninguém notar."""
    assert impedancia.manuais_de(None) == {}
    assert impedancia.manuais_de("8,00") == {}
    assert impedancia.manuais_de({"zl": {"modulo": -3, "angulo": 400}}) == {}
    assert impedancia.manuais_de({"zonas": {"Z1": {"alcance": 0}}}) == {}
    assert impedancia.manuais_de({"zonas": {"Z9": {"alcance": 5}}}) == {}
    # Vírgula decimal é como o brasileiro digita, e tem de passar.
    assert impedancia.manuais_de(
        {"zl": {"modulo": "2,08", "angulo": "76"}}
    ) == {"zl": {"modulo": 2.08, "angulo": 76.0, "base": "secundario"}}


def test_o_manual_entra_por_cima_e_o_resto_continua_do_rele():
    """Quem digitou só a Z1 fica com a Z2 do relé — e ela continua dizendo
    que veio do relé."""
    r = _registro(lado_primario=False)
    painel = _PainelComManuais({"zonas": {"Z1": {"alcance": 1.0}}})
    pacote = impedancia.montar(
        r, painel, {"ajustes": [[k, v] for k, v in AJUSTES.items()]},
        "secundario", 0, r.analog.shape[1] - 1)
    por_nome = {z["nome"]: z for z in pacote["zonas"]}
    assert por_nome["Z1"]["alcance"] == 1.0
    assert por_nome["Z1"]["origem"] == "digitado"
    assert por_nome["Z2"]["origem"] == "lido"
    assert por_nome["Z2"]["variavel"] == "Z2MG"


def test_mudar_a_linha_a_mao_recalcula_as_zonas_sugeridas():
    """A sugestão é % sobre o módulo. Sem isto, o usuário corrige a linha e
    as zonas continuam calculadas sobre a linha antiga."""
    r = _registro(lado_primario=False)
    # Sem ajuste nenhum no arquivo: as três zonas saem da sugestão.
    painel = _PainelComManuais({"zl": {"modulo": 5.0, "angulo": 80.0}})
    pacote = impedancia.montar(r, painel, {"ajustes": []},
                               "secundario", 0, r.analog.shape[1] - 1)
    por_nome = {z["nome"]: z for z in pacote["zonas"]}
    assert abs(por_nome["Z1"]["alcance"] - 4.0) < 1e-9      # 80 % de 5
    assert abs(por_nome["Z2"]["alcance"] - 6.0) < 1e-9      # 120 %
    assert por_nome["Z1"]["origem"] == "sugerido"
    assert pacote["parametros"]["origem"] == "digitado"


def test_uma_zona_que_o_arquivo_nao_traz_nasce_do_teclado():
    """COMTRADE puro, sem réplica: não há o que sobrescrever, e mesmo assim
    se quer desenhar a característica."""
    r = _registro(lado_primario=False)
    painel = _PainelComManuais({"zonas": {"Z1": {"alcance": 2.0,
                                                 "tempo": "inst."}}})
    pacote = impedancia.montar(r, painel, {"ajustes": []},
                               "secundario", 0, r.analog.shape[1] - 1)
    assert [z["nome"] for z in pacote["zonas"]] == ["Z1"]
    assert pacote["zonas"][0]["alcance"] == 2.0
    assert pacote["zonas"][0]["origem"] == "digitado"
    assert pacote["zonas"][0]["tempo"] == "inst."


def test_o_digitado_e_secundario_e_converte_junto_com_o_lido():
    """O defeito que este teste tranca: o valor digitado ficar em primário
    enquanto o lido converte — dois números na mesma coluna, bases
    diferentes, e o veredito saindo errado e calado."""
    r = _registro(lado_primario=True)
    painel = _PainelComManuais({"zonas": {"Z1": {"alcance": 1.0}}})
    pacote = impedancia.montar(
        r, painel, {"ajustes": [[k, v] for k, v in AJUSTES.items()]},
        "primario", 0, r.analog.shape[1] - 1)
    por_nome = {z["nome"]: z for z in pacote["zonas"]}
    relacao = RTP / RTC
    # Desenhado: 1,0 Ω secundário vira 1,0 × RTP/RTC primário.
    assert abs(por_nome["Z1"]["alcance"] - 1.0 * relacao) < 1e-6
    assert abs(por_nome["Z2"]["alcance"] - 2.49 * relacao) < 1e-6
    # O FORMULÁRIO segue o botão geral desde 22/10/2026: em primário ele
    # mostra primário, e diz isso (`base`). O digitado e o lido continuam na
    # MESMA base, que é o que este teste tranca.
    do_form = {z["nome"]: z for z in pacote["ajuste"]["zonas"]}
    assert pacote["ajuste"]["base"] == "primario"
    assert abs(do_form["Z1"]["alcance"] - 1.0 * relacao) < 1e-6
    assert abs(do_form["Z2"]["alcance"] - 2.49 * relacao) < 1e-6
    assert pacote["ajuste"]["relacao"] == relacao


def test_rtp_rtc_digitada_vale_para_zona_e_trajetoria():
    """A RTP/RTC corrigida à mão: as zonas vão ao primário com ela, e a
    trajetória em secundário é reescalada — senão zona e trajetória ficariam
    em réguas diferentes."""
    r = _registro(lado_primario=True)
    ajustes = {"ajustes": [[k, v] for k, v in AJUSTES.items()]}
    fim = r.analog.shape[1] - 1
    lida = RTP / RTC
    certo = impedancia.montar(r, _PainelComManuais({}), ajustes, "secundario", 0, fim)
    dobro = impedancia.montar(r, _PainelComManuais({"relacao": 2 * lida}), ajustes,
                              "secundario", 0, fim)
    assert dobro["ajuste"]["relacao"] == 2 * lida
    assert dobro["ajuste"]["relacao_lida"] == lida and dobro["ajuste"]["relacao_digitada"]
    # Secundário = primário ÷ relação: com o dobro dela, a trajetória cai à metade.
    xs_certo = [p["x"] for p in certo["pontos"]]
    xs_dobro = [p["x"] for p in dobro["pontos"]]
    assert xs_certo and all(abs(b - a / 2) < 1e-9 * max(1.0, abs(a))
                            for a, b in zip(xs_certo, xs_dobro, strict=True))
    em_pri = impedancia.montar(r, _PainelComManuais({"relacao": 2 * lida}), ajustes,
                               "primario", 0, fim)
    z1 = {z["nome"]: z for z in em_pri["zonas"]}["Z1"]
    assert abs(z1["alcance"] - 1.66 * 2 * lida) < 1e-6


def test_o_digitado_em_PRIMARIO_vira_secundario_antes_de_valer():
    """Quem digitou com a tela em primário digitou primário: o servidor
    divide por RTP/RTC, e a zona fica igual à digitada em secundário."""
    r = _registro(lado_primario=True)
    relacao = RTP / RTC
    em_pri = _PainelComManuais({"zonas": {"Z1": {"alcance": 1.0 * relacao,
                                                 "base": "primario"}}})
    em_sec = _PainelComManuais({"zonas": {"Z1": {"alcance": 1.0}}})
    aj = {"ajustes": [[k, v] for k, v in AJUSTES.items()]}
    a = impedancia.montar(r, em_pri, aj, "secundario", 0, r.analog.shape[1] - 1)
    b = impedancia.montar(r, em_sec, aj, "secundario", 0, r.analog.shape[1] - 1)
    za = {z["nome"]: z for z in a["zonas"]}["Z1"]["alcance"]
    zb = {z["nome"]: z for z in b["zonas"]}["Z1"]["alcance"]
    assert abs(za - zb) < 1e-9 and abs(zb - 1.0) < 1e-9


def test_o_painel_leva_os_manuais_da_tela_ate_o_modulo():
    """O caminho inteiro: `paineis.de_json` peneira e `Painel.manuais` leva."""
    from osclab.plot import paineis
    arranjo = paineis.de_json([{
        "id": "p1", "tipo": "impedancia", "laco": "BN",
        "manuais": {"zl": {"modulo": "3,0", "angulo": 70},
                    "zonas": {"Z1": {"alcance": 2.4}, "Z9": {"alcance": 9}}},
    }])
    assert arranjo[0].manuais == {
        "zl": {"modulo": 3.0, "angulo": 70.0, "base": "secundario"},
        "zonas": {"Z1": {"alcance": 2.4, "base": "secundario"}}}


def test_sem_manuais_o_painel_fica_com_dicionario_vazio():
    from osclab.plot import paineis
    arranjo = paineis.de_json([{"id": "p1", "tipo": "impedancia"}])
    assert arranjo[0].manuais == {}


def test_a_relacao_do_registro_sai_dos_canais_DO_LACO_e_nao_da_bateria():
    """LT COXIPO, 22/10/2026: TC 240/1 e TP 1200/1 declarados, e mais dois
    canais de tensão de bateria (`VDC1`, `V`, 1/1). Procurando a relação no
    registro inteiro, «volt» tinha duas relações, nenhuma era escolhida, e o
    plano em primário deixava as zonas em secundário — trajetória cinco vezes
    maior que a régua das zonas. A relação sai dos canais que entram em V/I."""
    r = _registro(lado_primario=True)
    bateria = AnalogChannel(index=7, name="VDC1", phase="", unit="V",
                            primary=1.0, secondary=1.0, scaling="P")
    com = Record(source=None, format_name="teste", line_frequency=F0,
                 analog_channels=r.analog_channels + (bateria,),
                 sample_rates=r.sample_rates,
                 analog=np.vstack([r.analog, np.full(r.analog.shape[1], 125.0)]),
                 time=r.time)
    v = {"A": 0, "B": 1, "C": 2}
    i = {"A": 3, "B": 4, "C": 5}
    assert impedancia._relacao_do_registro(com) is None        # o defeito
    assert impedancia._relacao_do_registro(com, v, i) == RTP / RTC
    pacote = impedancia.montar(
        com, _PainelFalso(), {"ajustes": [[k, v_] for k, v_ in AJUSTES.items()]},
        "primario", 0, com.analog.shape[1] - 1)
    assert pacote["comparavel"]
    assert not any("sem régua comum" in a for a in _avisos(pacote))



# ---------------------------------------------------------------------------
# Mho, quadrilateral, direção — o que o relé diz que usa (22/10/2026)
# ---------------------------------------------------------------------------

SEL_421 = {
    "Z1MAG": "1.26", "Z1ANG": "71.17",
    "E21MP": "3", "E21XP": "N", "E21MG": "3", "E21XG": "3",
    "Z1MP": "1.00", "Z2MP": "2.50", "Z3MP": "2.50",
    "Z1MG": "1.00", "Z2MG": "2.50", "Z3MG": "2.50",
    "XG1": "1.00", "RG1": "4.00", "XG2": "2.50", "RG2": "6.50",
    "XG3": "2.50", "RG3": "6.50", "XP1": "6.24", "RP1": "12.48",
    "Z1PD": "0.000", "Z2PD": "24.000", "Z3PD": "60.000",
    "DIR3": "R",
}


def test_o_laco_de_FASE_le_o_Z1MP_e_nao_a_zona_de_terra():
    """No SEL-421 a mho de fase é `Z1MP`; pegar `Z1MG` desenhava a zona de
    terra num laço de fase (LT COXIPO)."""
    zonas = impedancia.zonas_de(SEL_421, None, "BC")
    assert [z.alcance.variavel for z in zonas] == ["Z1MP", "Z2MP", "Z3MP"]
    assert zonas[1].tempo == "24 ciclos (0,40 s)"


def test_a_zona_3_reversa_e_desenhada_no_terceiro_quadrante():
    zonas = impedancia.zonas_de(SEL_421, None, "BC")
    z3 = zonas[2]
    assert z3.direcao == "R" and z3.direcao_variavel == "DIR3"
    g = impedancia.geometria_mho(z3.alcance.valor, 71.17, z3.direcao)
    assert g["centro"][0] < 0 and g["centro"][1] < 0


def test_a_quadrilateral_so_existe_onde_o_rele_a_habilita():
    """Fase: `E21XP = N` — o `XP1` que sobrou no arquivo não é ajuste vigente.
    Terra: `E21XG = 3`, as três vêm lidas."""
    fase = impedancia.zonas_de(SEL_421, None, "BC")
    terra = impedancia.zonas_de(SEL_421, None, "AN")
    assert all(z.x is None and z.usa_quad is False for z in fase)
    assert [z.x.valor for z in terra] == [1.0, 2.5, 2.5]
    assert all(z.usa_mho and z.usa_quad for z in terra)
    info = impedancia.caracteristica_de(SEL_421, "AN")
    assert info["mho"] == 3 and info["quad"] == 3 and info["lida"]


def test_a_falta_reversa_entra_na_zona_reversa():
    """Ponto a 1,2 Ω ∠−110°: fora das zonas à frente, dentro da Z3 reversa."""
    import cmath
    zonas = impedancia.zonas_de(SEL_421, None, "BC")
    z = cmath.rect(1.2, math.radians(-110))
    entradas = impedancia.entrada_nas_zonas(
        np.array([0]), np.array([z.real]), np.array([z.imag]), zonas, 71.17)
    assert entradas["Z1"] is None and entradas["Z2"] is None
    assert entradas["Z3"] == 0


def test_com_AMBAS_a_zona_entra_pela_quadrilateral_tambem():
    """Ponto com muita resistência: fora da mho de terra, dentro da quad."""
    zonas = impedancia.zonas_de(SEL_421, None, "AN")
    r_, x_ = np.array([3.0]), np.array([0.5])
    so_mho = impedancia.entrada_nas_zonas(np.array([0]), r_, x_, zonas, 71.17, "mho")
    ambas = impedancia.entrada_nas_zonas(np.array([0]), r_, x_, zonas, 71.17, "ambas")
    assert so_mho["Z1"] is None and ambas["Z1"] == 0


def test_sem_taxa_declarada_a_trajetoria_nao_sai_vazia():
    """SEL-751 e 311C escrevem `nrates = 0`: a taxa sai do vetor de tempo.
    Lendo `sample_rates[0]` (que vale 0) o plano saía sem ponto nenhum."""
    r = _registro()
    esperado = impedancia.trajetoria(r, CANAIS_V, CANAIS_I, "AN", K0,
                                     0, r.analog.shape[1] - 1, CANAIS_I["N"])
    r.sample_rates = (SampleRate(rate_hz=0.0, last_sample=r.n_samples),)
    achado = impedancia.trajetoria(r, CANAIS_V, CANAIS_I, "AN", K0,
                                   0, r.analog.shape[1] - 1, CANAIS_I["N"])
    assert achado[0].size == esperado[0].size > 0
    np.testing.assert_allclose(achado[1], esperado[1], equal_nan=True)


def test_a_janela_da_trajetoria_nao_atravessa_a_fronteira_dos_trechos():
    r = _registro()
    meio = r.n_samples // 2
    r.sample_rates = (SampleRate(rate_hz=TAXA, last_sample=meio),
                      SampleRate(rate_hz=TAXA, last_sample=r.n_samples))
    idx, R, _ = impedancia.trajetoria(r, CANAIS_V, CANAIS_I, "AN", K0,
                                      0, r.analog.shape[1] - 1, CANAIS_I["N"])
    ciclo = int(TAXA / F0)
    cruzam = (idx >= meio) & (idx < meio + ciclo - 1)
    assert cruzam.any() and not np.isfinite(R[cruzam]).any()


def test_a_relacao_dos_sel_4xx_e_lida_por_terminal():
    """421/451/411L escrevem `CTRW` e `PTRY`: sem esses nomes, o `.CEV` de um
    4xx ficava sem régua comum embora a relação estivesse no arquivo."""
    assert impedancia._relacao_dos_ajustes({"CTRW": "160", "PTRY": "1200"}) == 1200 / 160


def test_habilitacao_de_zona_pelos_nomes_do_311c_e_do_321():
    """O 311C escreve `E21P` (não `E21MP`); o 321 `PMHOZ`/`GMHOZ`/`QUADZ`."""
    assert impedancia.caracteristica_de({"E21P": "3"}, "AB")["mho"] == 3
    assert impedancia.caracteristica_de({"PMHOZ": "2"}, "BC")["mho"] == 2
    terra = impedancia.caracteristica_de({"GMHOZ": "3", "QUADZ": "2"}, "AN")
    assert (terra["mho"], terra["quad"]) == (3, 2)
    # O nome do 4xx, quando existe, continua mandando.
    assert impedancia.caracteristica_de({"E21MP": "4", "E21P": "1"}, "AB")["mho"] == 4


def test_com_uma_tensao_e_varias_correntes_o_nome_correspondente_decide():
    """O 87L da SEL grava `IA` (a do 21) e os terminais `IAL`, `IAX`. Com uma
    tensão só, a corrente do plano é a de nome correspondente (`I*` ↔ `V*`)
    — e nada de adivinhar quando não há uma só que corresponda."""
    nomes = ["IA", "IB", "IC", "IAL", "IBL", "ICL", "VA", "VB", "VC"]
    canais = tuple(AnalogChannel(index=i, name=n, unit="A" if n[0] == "I" else "kV",
                                 phase="", component="LD TESTE - UPC1")
                   for i, n in enumerate(nomes))
    r = Record(source=None, format_name="teste", station="", line_frequency=60.0,
               start_time=None, analog_channels=canais,
               analog=np.ones((9, 10)), time=np.arange(10) / 1200.0)
    corrente, tensao = impedancia._par_unico(r)
    assert corrente is not None and corrente.abc == (0, 1, 2) and tensao.abc == (6, 7, 8)
