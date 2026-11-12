"""O «refinar» da seq. negativa de dois terminais (`faultloc/refino.py`,
`plot/refino.py`): alinhamento automático e manual, a segunda opinião pela
correlação de |I2|, V2/I2 no instante, o km, o caminho do terminal sem tensão,
e o pacote da tela.

As faltas saem do mini-EMTP dos testes (`tests/rede_de_falta.py`), gravadas
como um relé gravaria — e o km conferido contra a mesma conta sobre os fasores
EXATOS (`rede_de_falta.seqneg_ideal`).
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from osclab import paths
from osclab.faultloc import refino as rf
from osclab.library import acervo
from osclab.plot import refino as prf
from tests import rede_de_falta as rede

KM = 100.0
CENARIO = rede.Cenario(linha=rede.LT_100, m=0.615, tipo="AG", rf=4.0, delta=12.0)
LINHA = {"r": rede.LT_100.Z1.real, "x": rede.LT_100.Z1.imag, "km": KM}


@pytest.fixture(scope="module")
def simulacao():
    return rede.simular(CENARIO, abre_s=0.062, abre_r=0.068)


def _gravar(sim, lado, **formato):
    return rede.gravar(sim, lado, rede.Formato(tipo="comtrade", escala="S", **formato),
                       nome=f"SE {lado}")


@pytest.fixture(scope="module")
def par_bom(simulacao):
    """B com o relógio 25 ms adiantado e a pré-falta 25 ms mais curta: o
    automático (pelo início da falta) acha o d verdadeiro de −25 ms."""
    a = _gravar(simulacao, "S", taxa=2000.0, seed=1)
    b = _gravar(simulacao, "R", taxa=2000.0, seed=2, pre_s=0.075, erro_relogio_s=0.025)
    return rf.lado(a, "A", "SE S"), rf.lado(b, "B", "SE R")


@pytest.fixture(scope="module")
def par_tardio(simulacao):
    """B começa a gravar 6 ms antes da falta: o detector de B não acha o
    início, e o automático cai no disparo (que é 40 ms depois do de A)."""
    a = _gravar(simulacao, "S", taxa=1200.0, seed=3)
    b = rede.gravar(simulacao, "R", rede.Formato(tipo="comtrade", escala="S", taxa=1200.0,
                                                 seed=4, pre_s=0.006, erro_relogio_s=0.8),
                    trip_s=0.065, nome="SE R")
    return rf.lado(a, "A", "SE S"), rf.lado(b, "B", "SE R")


def _sem_tensao(registro):
    """O registro só com as três correntes — o relé de corrente, sem TP."""
    canais = tuple(dataclasses.replace(c, index=k)
                   for k, c in enumerate(registro.analog_channels[3:]))
    return dataclasses.replace(registro, analog_channels=canais, analog=registro.analog[3:])


def _meio_do_plato(a, b, d):
    curva = rf.curva_km(a, b, d, LINHA, "A", None)
    assert curva is not None and curva["plato"]
    return (curva["plato"][0] + curva["plato"][1]) / 2.0


# ---------------------------------------------------------------------------
# O alinhamento
# ---------------------------------------------------------------------------

def test_o_automatico_acha_o_deslocamento_verdadeiro_e_a_correlacao_concorda(par_bom):
    a, b = par_bom
    al = rf.alinhar(a, b, "auto", None)
    assert al["modo"] == "auto"
    assert al["d"] == pytest.approx(-0.025, abs=a.passo)
    assert al["confere"] is not None and not al["confere"]["discorda"]
    # a correlação erra pouco (as aberturas são 6 ms diferentes), mas dentro
    # do ¼ de ciclo que não vira aviso
    assert abs(al["confere"]["d"] - (-0.025)) < 0.25 / 60.0


def test_a_correlacao_acha_o_d_quando_o_automatico_erra(par_tardio):
    a, b = par_tardio
    al = rf.alinhar(a, b, "auto", None)
    verdadeiro = 0.006 - 0.1
    assert abs(al["d"] - verdadeiro) > 0.02          # o automático erra
    assert al["confere"]["discorda"]
    # a correlação acerta dentro do ¼ de ciclo que ela mesma usa para avisar
    assert al["confere"]["d"] == pytest.approx(verdadeiro, abs=0.25 / 60.0)


def test_o_manual_por_numero_cai_numa_amostra_de_B(par_bom):
    a, b = par_bom
    al = rf.alinhar(a, b, "manual", {"d": -0.02512})
    assert al["modo"] == "manual"
    assert al["d"] / b.passo == pytest.approx(round(al["d"] / b.passo), abs=1e-9)
    assert al["d"] == pytest.approx(-0.025, abs=b.passo)


def test_o_manual_por_dois_pontos_e_tB_menos_tA_nas_amostras(par_bom):
    a, b = par_bom
    al = rf.alinhar(a, b, "manual", {"ta": 0.10011, "tb": 0.07502})
    ta, tb = al["manual"]["marcas"]["ta"], al["manual"]["marcas"]["tb"]
    assert ta in a.registro.time and tb in b.registro.time
    assert al["d"] == pytest.approx(tb - ta)
    # uma marca só é guardada, mas não alinha: vale o automático
    meia = rf.alinhar(a, b, "manual", {"ta": 0.1})
    assert meia["manual"]["marcas"] == {"ta": pytest.approx(0.1, abs=a.passo), "tb": None}
    assert meia["d"] == pytest.approx(meia["auto"]["d"])


def test_o_automatico_ignora_o_manual(par_bom):
    a, b = par_bom
    al = rf.alinhar(a, b, "auto", {"d": 0.5})
    assert al["d"] == pytest.approx(al["auto"]["d"])


# ---------------------------------------------------------------------------
# A leitura e o km
# ---------------------------------------------------------------------------

def test_o_km_no_plato_bate_com_a_conta_sobre_os_fasores_exatos(par_bom):
    a, b = par_bom
    d = rf.alinhar(a, b, "auto", None)["d"]
    t = _meio_do_plato(a, b, d)
    ler = rf.leitura(a, b, d, t, LINHA, "A", None)
    ideal = rede.seqneg_ideal(CENARIO)
    assert ler["km"]["km"] == pytest.approx(ideal, abs=0.5)
    assert ler["km"]["pct"] == pytest.approx(ler["km"]["km"] / KM * 100.0)
    # a partir de B é o complemento
    de_b = rf.leitura(a, b, d, t, LINHA, "B", None)["km"]["km"]
    assert de_b == pytest.approx(KM - ler["km"]["km"])
    # o que se lê é o MESMO terminal: V2 a 0°, e o ângulo é o de I2 contra ele
    assert ler["A"]["origem"] == {"v2": "lido", "i2": "lido", "ang": "lido"}
    assert ler["A"]["v2"] > 0 and ler["A"]["i2"] > 0


def test_a_mediana_do_plato_nao_depende_de_um_instante(par_bom):
    a, b = par_bom
    d = rf.alinhar(a, b, "auto", None)["d"]
    curva = rf.curva_km(a, b, d, LINHA, "A", None)
    assert curva["mediana"] == pytest.approx(rede.seqneg_ideal(CENARIO), abs=0.5)
    assert curva["km"].shape == a.registro.time.shape
    # antes da falta não há número (I2 ≈ 0 nos dois lados)
    antes = a.registro.time < curva["plato"][0] - 0.05
    assert np.isnan(curva["km"][antes]).all()


def test_mal_alinhado_o_km_sai_errado_e_alinhado_volta(par_tardio):
    a, b = par_tardio
    al = rf.alinhar(a, b, "auto", None)
    certo = rf.curva_km(a, b, al["confere"]["d"], LINHA, "A", None)["mediana"]
    assert certo == pytest.approx(rede.seqneg_ideal(CENARIO), abs=0.5)
    errado = rf.curva_km(a, b, al["d"], LINHA, "A", None)["mediana"]
    assert errado is None or abs(errado - certo) > 1.0


def test_o_digitado_vale_no_lugar_do_lido_e_diz_a_origem(par_bom):
    a, b = par_bom
    d = rf.alinhar(a, b, "auto", None)["d"]
    t = _meio_do_plato(a, b, d)
    ler = rf.leitura(a, b, d, t, LINHA, "A", {"B": {"i2": "123,5"}})
    assert ler["B"]["i2"] == 123.5 and ler["B"]["origem"]["i2"] == "digitado"
    assert ler["B"]["lido"]["i2"] != 123.5


def test_terminal_sem_tensao_pede_V2_e_a_impedancia_de_fonte_resolve(simulacao):
    a = rf.lado(_gravar(simulacao, "S", taxa=2000.0, seed=5), "A", "SE S")
    b = rf.lado(_sem_tensao(_gravar(simulacao, "R", taxa=2000.0, seed=6)), "B", "SE R")
    assert b.v2 is None and b.i2 is not None and "tensão" in b.aviso
    d = rf.alinhar(a, b, "auto", None)["d"]
    assert rf.curva_km(a, b, d, LINHA, "A", None) is None      # sem V2 de B, não há curva
    z2f = CENARIO.fonte(CENARIO.sir_r)[0]          # a fonte atrás de R, como no gerador
    dig = {"B": {"z2f_mod": f"{abs(z2f):.4f}", "z2f_ang": f"{math.degrees(np.angle(z2f)):.2f}"}}
    plato = rf.curva_km(a, b, d, LINHA, "A", dig)["plato"]
    t = (plato[0] + plato[1]) / 2.0
    sem = rf.leitura(a, b, d, t, LINHA, "A", None)
    assert sem["km"]["km"] is None and "V2 de B" in sem["km"]["motivo"]
    com = rf.leitura(a, b, d, t, LINHA, "A", dig)
    assert com["B"]["origem"]["v2"] == "fonte"
    # o V2 tirado da fonte não enxerga a capacitância da linha nem o resto da
    # rede: erra ~1 km numa linha de 100 km, contra 0,1 km do V2 medido
    assert com["km"]["km"] == pytest.approx(rede.seqneg_ideal(CENARIO), abs=1.5)
    # e a curva usa −Z2f·I2 amostra a amostra
    mediana = rf.curva_km(a, b, d, LINHA, "A", dig)["mediana"]
    assert mediana == pytest.approx(rede.seqneg_ideal(CENARIO), abs=1.5)


def test_sem_linha_nao_ha_km_e_diz_por_que(par_bom):
    a, b = par_bom
    ler = rf.leitura(a, b, 0.0, 0.15, None, "A", None)
    assert ler["km"] == {"km": None, "motivo": "falta o parâmetro da linha"}
    assert rf.curva_km(a, b, 0.0, None, "A", None) is None


# ---------------------------------------------------------------------------
# O pacote da tela
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def registros(simulacao):
    return (_gravar(simulacao, "S", taxa=2000.0, seed=7),
            _gravar(simulacao, "R", taxa=2000.0, seed=8, pre_s=0.075, erro_relogio_s=0.025))


def test_trifasico_e_corrente_primeiro_e_tres_fases_pelo_vinculo(registros):
    a, b = registros
    p = prf.montar(a, "SE S", b, "SE R", {"linha": LINHA})
    assert [g["id"] for g in p["graficos"]] == ["A-I", "B-I", "A-V", "B-V"]
    for g in p["graficos"]:
        assert [s["fase"] for s in g["series"]] == ["A", "B", "C"]
        # o canal de cada fase é o do VÍNCULO: o nome termina na letra dela
        assert all(s["nome"][1] == s["fase"] for s in g["series"])


def test_monofasico_mostra_a_fase_escolhida_de_A_e_de_B(registros):
    a, b = registros
    for fase in "ABC":
        p = prf.montar(a, "SE S", b, "SE R", {"vista": "mono", "fase": fase})
        assert [g["id"] for g in p["graficos"]] == ["mono-I", "mono-V"]
        for g in p["graficos"]:
            assert g["titulo"].endswith(f"fase {fase}")
            assert [(s["terminal"], s["fase"]) for s in g["series"]] == [
                ("A", fase), ("B", fase)]
            assert all(s["nome"][1] == fase for s in g["series"])


def test_a_sequencia_troca_cada_grafico_pela_negativa_dele(registros):
    a, b = registros
    tri = prf.montar(a, "SE S", b, "SE R", {"seq": True})
    assert [[s["nome"] for s in g["series"]] for g in tri["graficos"]] == [
        ["I2 A"], ["I2 B"], ["V2 A"], ["V2 B"]]
    assert all("env" in g["series"][0] and "fase" not in g["series"][0]
               for g in tri["graficos"])
    mono = prf.montar(a, "SE S", b, "SE R", {"seq": True, "vista": "mono", "fase": "B"})
    assert [[s["nome"] for s in g["series"]] for g in mono["graficos"]] == [
        ["I2 A", "I2 B"], ["V2 A", "V2 B"]]


def test_b_cai_em_t_menos_d_em_todo_sinal_dele(registros):
    """O registro de B anda INTEIRO: o mesmo d em todas as fases, corrente e
    tensão — não existe deslocamento por fase."""
    a, b = registros
    pa = prf.montar(a, "SE S", b, "SE R", {"de": 0.05, "ate": 0.2, "colunas": 100000})
    outro = {"d": pa["alinhamento"]["d"] + 0.005}
    pm = prf.montar(a, "SE S", b, "SE R", {"de": 0.05, "ate": 0.2, "colunas": 100000,
                                            "modo": "manual", "manual": outro})
    dd = pm["alinhamento"]["d"] - pa["alinhamento"]["d"]
    for ga, gm in zip(pa["graficos"], pm["graficos"], strict=True):
        if ga["terminal"] != "B":
            continue
        for sa, sm in zip(ga["series"], gm["series"], strict=True):
            # o mesmo valor aparece dd segundos antes na tela
            i = len(sa["t"]) // 2
            j = int(np.argmin(np.abs(np.array(sm["t"]) - (sa["t"][i] - dd))))
            assert sm["onda"][j] == pytest.approx(sa["onda"][i])


def test_com_zoom_cada_ponto_e_uma_amostra(registros):
    a, b = registros
    largo = prf.montar(a, "SE S", b, "SE R", {"colunas": 100})
    assert not largo["graficos"][0]["series"][0]["amostras"]      # reduzido
    perto = prf.montar(a, "SE S", b, "SE R", {"de": 0.10, "ate": 0.11, "colunas": 1000})
    assert all(s["amostras"] for g in perto["graficos"] for s in g["series"])


def test_os_numeros_vem_escritos_e_o_alinhamento_diz_a_correlacao(registros):
    a, b = registros
    p = prf.montar(a, "SE S", b, "SE R", {"linha": LINHA, "t1": 0.15})
    c1 = p["cursores"]["t1"]
    assert c1["km"]["txt"]["km"].count(",") == 1
    assert p["alinhamento"]["txt"]["usado"].startswith("−25,")
    assert p["alinhamento"]["confere"]["discorda"] is False
    assert p["km_curva"]["txt"]["mediana"] != "—"


def test_a_linha_do_pedido_e_conferida():
    assert prf.linha_do_pedido(None) is None
    assert prf.linha_do_pedido({"r": 1, "x": None, "km": 10}) is None
    assert prf.linha_do_pedido({"r": 1, "x": 5, "km": 0}) is None
    assert prf.linha_do_pedido({"r": 1, "x": 5, "km": 10, "perfil": [[0, 0], [10, 1]]}) == {
        "r": 1.0, "x": 5.0, "km": 10.0, "b1": None, "perfil": [[0.0, 0.0], [10.0, 1.0]]}


# ---------------------------------------------------------------------------
# As rotas
# ---------------------------------------------------------------------------

def _comtrade(pasta, nome, registro):
    """O `Record` num COMTRADE 1999 ASCII, com os nomes e as relações dele."""
    n = registro.analog.shape[1]
    linhas = [f"{nome},REL,1999", f"{len(registro.analog_channels) + 1},"
              f"{len(registro.analog_channels)}A,1D"]
    fatores = []
    for k, c in enumerate(registro.analog_channels):
        a = float(np.max(np.abs(registro.analog[k]))) / 30000 or 1.0
        fatores.append(a)
        linhas.append(f"{k + 1},{c.name},{c.phase},,{c.unit},{a:.9g},0,0,-32767,32767,"
                      f"{c.primary:g},{c.secondary:g},{c.scaling}")
    linhas.append("1,TRIP,,,0")
    fmt = lambda x: x.strftime("%d/%m/%Y,%H:%M:%S.%f")  # noqa: E731
    linhas += ["60", "1", f"{registro.sample_rates[0].rate_hz:g},{n}", fmt(registro.start_time),
               fmt(registro.trigger_time), "ASCII", "1"]
    (pasta / f"{nome}.cfg").write_bytes(("\r\n".join(linhas) + "\r\n").encode("latin-1"))
    dat = [",".join([str(k + 1), str(int(round(registro.time[k] * 1e6))),
                     *[str(int(round(registro.analog[j, k] / fatores[j])))
                       for j in range(len(fatores))],
                     str(int(registro.status[0, k]))]) for k in range(n)]
    (pasta / f"{nome}.dat").write_bytes(("\r\n".join(dat) + "\r\n").encode("latin-1"))
    return [(f"{nome}.{e}", (pasta / f"{nome}.{e}").read_bytes()) for e in ("cfg", "dat")]


def test_a_rota_e_a_pagina(tmp_path, monkeypatch, cliente, registros):
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    a, b = registros
    origem = tmp_path / "origem"
    origem.mkdir()
    r = acervo.guardar(_comtrade(origem, "LADO_A", a) + _comtrade(origem, "LADO_B", b))
    assert len(r.aceitos) == 2, r.problemas
    sha_a, sha_b = (x.sha for x in sorted(r.aceitos, key=lambda x: x.nome))
    pagina = cliente.get(f"/refino/{sha_a}?com={sha_b}")
    assert pagina.status_code == 200 and b"refino.js" in pagina.data
    assert cliente.get(f"/refino/{sha_a}?com=nada").status_code == 404
    resposta = cliente.post(f"/api/onda/{sha_a}/refino",
                            json={"b": sha_b, "linha": LINHA, "t1": 0.15})
    assert resposta.status_code == 200
    p = resposta.get_json()
    assert [g["id"] for g in p["graficos"]] == ["A-I", "B-I", "A-V", "B-V"]
    assert p["cursores"]["t1"]["km"]["km"] is not None
    assert cliente.post(f"/api/onda/{sha_a}/refino", json={"b": "nada"}).status_code == 404


def test_a_paleta_do_refino_e_a_do_css_e_passa_no_validador():
    import re

    from tests.test_web import _paleta_do_repositorio
    paleta = _paleta_do_repositorio()
    texto = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")
    corte = texto.index('\n:root[data-tema="escuro"] {')
    cor = re.compile(r"(--(?:refino-[a-z]+|cursor-[12]))\s*:\s*(#[0-9a-f]{6})")
    for tema, pedaco in (("claro", texto[:corte]), ("escuro", texto[corte:])):
        do_css = dict(cor.findall(pedaco))
        for grupo in (paleta.REFINO, paleta.REFINO_COM_FASES):
            cores = grupo[tema]["cores"]
            assert {k: do_css[k] for k in cores if k in do_css} == {
                k: v for k, v in cores.items() if k in do_css}, tema
            reprovacoes, _ = paleta.conferir(cores, grupo[tema]["fundo"])
            assert not reprovacoes, (tema, reprovacoes)
        cores = paleta.REFINO[tema]["cores"]
        assert {k: do_css[k] for k in cores} == cores


# ---------------------------------------------------------------------------
# O manual do refino vale no painel localizador (decidido em 11/11/2026)
# ---------------------------------------------------------------------------

def test_o_deslocamento_do_painel_e_o_automatico_sem_pedido_e_o_manual_na_grade(par_bom):
    _, b = par_bom
    reg_b = b.registro
    assert rf.deslocamento_do_painel(reg_b, -0.02, None) == {
        "d": -0.02, "manual": False, "auto": -0.02}
    for lixo in ("abc", float("nan"), float("inf"), [1]):
        assert rf.deslocamento_do_painel(reg_b, -0.02, lixo)["manual"] is False
    e = rf.deslocamento_do_painel(reg_b, -0.02, -0.0943)
    assert e["manual"] and e["auto"] == -0.02
    assert e["d"] == pytest.approx(rf.no_grid(-0.0943, b.passo))
    # a mesma grade que o refino usa para o mesmo número
    assert e["d"] == pytest.approx(rf.alinhar(*par_bom, "manual", {"d": -0.0943})["d"])


def test_o_km_do_painel_com_o_manual_e_o_km_da_janela(par_tardio):
    """O mesmo `d` nos dois: a mediana da seq. negativa no painel é a do
    refino, e o automático errado deixa de valer no painel também."""
    from osclab.faultloc import ldl

    a, b = par_tardio
    al = rf.alinhar(a, b, "auto", None)
    pedido = al["confere"]["d"] + 0.3 * b.passo     # fora da grade, de propósito
    janela = rf.alinhar(a, b, "manual", {"d": pedido})
    painel = rf.deslocamento_do_painel(b.registro, al["d"], pedido)
    assert painel["d"] == janela["d"]
    km_janela = rf.curva_km(a, b, janela["d"], LINHA, "A", None)["mediana"]
    pacote = ldl.montar(a.registro, b.registro, painel["d"], LINHA, None)
    km_painel = pacote["metodos"]["seqneg"]["km"]
    assert km_painel == pytest.approx(km_janela, abs=1e-6)
    assert km_painel == pytest.approx(rede.seqneg_ideal(CENARIO), abs=0.5)
    # e no instante: o cursor do painel lê o mesmo km que o cursor da janela
    t = _meio_do_plato(a, b, janela["d"])
    cursor = ldl.montar(a.registro, b.registro, painel["d"], LINHA, t)["cursor"]
    lido = rf.leitura(a, b, janela["d"], t, LINHA, "A", None)
    assert cursor["km"]["seqneg"] == pytest.approx(lido["km"]["km"], abs=1e-6)


def test_a_rota_do_painel_usa_o_manual_do_refino_e_diz(tmp_path, monkeypatch, cliente,
                                                        par_tardio):
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    a, b = par_tardio
    origem = tmp_path / "origem"
    origem.mkdir()
    r = acervo.guardar(_comtrade(origem, "LADO_A", a.registro)
                       + _comtrade(origem, "LADO_B", b.registro))
    assert len(r.aceitos) == 2, r.problemas
    sha_a, sha_b = (x.sha for x in sorted(r.aceitos, key=lambda x: x.nome))
    d = rf.alinhar(a, b, "auto", None)["confere"]["d"]
    corpo = {"registros": [{"sha": sha_b}], "fonte": "manual",
             "manual": {"km": KM, "forma": "rx", "r": LINHA["r"], "x": LINHA["x"]}}
    sem = cliente.post(f"/api/onda/{sha_a}/localizar", json=corpo).get_json()
    assert sem["alinhado_a_mao"] is None
    com = cliente.post(f"/api/onda/{sha_a}/localizar",
                       json=dict(corpo, refino={"b": sha_b, "d": d})).get_json()
    m = com["alinhado_a_mao"]
    assert m and m["d"] == pytest.approx(d) and m["txt"]["d"]
    assert com["metodos"]["seqneg"]["km"] == pytest.approx(rede.seqneg_ideal(CENARIO), abs=0.5)
    # o manual de OUTRO B não vale para este
    outro = cliente.post(f"/api/onda/{sha_a}/localizar",
                         json=dict(corpo, refino={"b": "outro", "d": d})).get_json()
    assert outro["alinhado_a_mao"] is None
