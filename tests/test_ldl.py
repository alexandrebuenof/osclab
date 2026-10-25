"""A LDL no tempo: seq. negativa e laço da falta, com os dois terminais.

As oscilografias são de uma rede RESOLVIDA: duas fontes, a linha entre elas e
a falta, nas três sequências — a mesma conta que a maquete do painel usa e que
foi conferida em Python (a tensão no ponto da falta sai igual pelos dois lados,
e V_falta = Rf·I_falta). Sem fixture, como o `test_falta`.
"""

from __future__ import annotations

import cmath
import math
from datetime import datetime

import numpy as np
import pytest

from osclab.basedados import linhas
from osclab.faultloc import ldl, seqneg
from osclab.formats.base import AnalogChannel, Record, SampleRate

TAXA = 1920.0
F0 = 60.0
L_KM = 60.0
Z1KM, Z0KM = complex(0.08, 0.40), complex(0.30, 1.20)
Z1L, Z0L = Z1KM * L_KM, Z0KM * L_KM
T_FALTA, T_ABRE, DURACAO = 0.100, 0.200, 0.300
A = cmath.exp(2j * math.pi / 3)


def _fases(z0, z1, z2):
    return (z0 + z1 + z2, z0 + A * A * z1 + A * z2, z0 + A * z1 + A * A * z2)


def _rede(m, rf, tipo, delta=15.0, forca_r=1.0):
    """Os fasores de fase dos dois terminais: pré-falta e falta.

    Sequências 0/1/2; fonte S forte, fonte R `forca_r` vezes mais fraca; carga
    pelo ângulo `delta` entre as fontes.
    """
    zl = {0: Z0L, 1: Z1L, 2: Z1L}
    zs = {0: complex(0.6, 5), 1: complex(1, 8), 2: complex(1, 8)}
    fonte_r = {0: complex(1.2, 10), 1: complex(2, 16), 2: complex(2, 16)}
    zr = {k: v * forca_r for k, v in fonte_r.items()}
    vb = 79674.0
    es, er = cmath.rect(vb, math.radians(delta)), complex(vb * 0.98, 0)
    il = (es - er) / (zs[1] + zl[1] + zr[1])
    v1_pre = es - zs[1] * il
    vf = v1_pre - m * zl[1] * il
    za = {k: zs[k] + m * zl[k] for k in zl}
    zb = {k: zr[k] + (1 - m) * zl[k] for k in zl}
    zth = {k: za[k] * zb[k] / (za[k] + zb[k]) for k in zl}
    if tipo == "AG":
        i = vf / (zth[0] + zth[1] + zth[2] + 3 * rf)
        i_f = {0: i, 1: i, 2: i}
    else:   # BC
        i = vf / (zth[1] + zth[2] + rf)
        i_f = {0: 0j, 1: i, 2: -i}
    i_s = {k: i_f[k] * zb[k] / (za[k] + zb[k]) for k in zl}
    i_r = {k: i_f[k] * za[k] / (za[k] + zb[k]) for k in zl}
    i_s[1] += il
    i_r[1] -= il
    v_s = {0: -zs[0] * i_s[0], 1: es - zs[1] * i_s[1], 2: -zs[2] * i_s[2]}
    v_r = {0: -zr[0] * i_r[0], 1: er - zr[1] * i_r[1], 2: -zr[2] * i_r[2]}
    v1r_pre = er + zr[1] * il
    return {
        "S": {"pre_v": _fases(0, v1_pre, 0), "pre_i": _fases(0, il, 0),
              "v": _fases(v_s[0], v_s[1], v_s[2]), "i": _fases(i_s[0], i_s[1], i_s[2])},
        "R": {"pre_v": _fases(0, v1r_pre, 0), "pre_i": _fases(0, -il, 0),
              "v": _fases(v_r[0], v_r[1], v_r[2]), "i": _fases(i_r[0], i_r[1], i_r[2])},
    }


def _registro(lado: dict, *, atraso=0.0, giro=0.0, nome="SE ALFA", abre=True,
              fim=T_ABRE) -> Record:
    """VA VB VC IA IB IC no tempo. `atraso`: a falta cai `atraso` s mais tarde
    no relógio deste relé; `giro`: o relógio dele gira todos os ângulos.
    `abre=False`: quem eliminou a falta foi o OUTRO terminal, e a corrente
    deste volta à carga em `fim` em vez de ir a zero."""
    n = int((DURACAO + atraso) * TAXA)
    t = np.arange(n) / TAXA
    w = 2 * math.pi * F0
    g = cmath.exp(1j * math.radians(giro))
    falta = (t >= T_FALTA + atraso) & (t < fim + atraso)
    aberto = (t >= fim + atraso) & abre
    dados = np.zeros((6, n))
    for k in range(3):
        pares = ((lado["pre_v"][k], lado["v"][k]), (lado["pre_i"][k], lado["i"][k]))
        for j, (pre, fal) in enumerate(pares):
            pre, fal = pre * g, fal * g
            sen = lambda z: abs(z) * math.sqrt(2) * np.sin(w * t + cmath.phase(z))  # noqa: E731
            if j == 0:
                onda = np.where(falta, sen(fal), sen(pre))
            else:
                onda = np.where(falta, sen(fal), np.where(aberto, 0.003 * sen(pre), sen(pre)))
            dados[3 * j + k] = onda
    canais = tuple(AnalogChannel(index=i, name=nome_c, phase=fase, unit=u, scaling="P")
                   for i, (nome_c, fase, u) in enumerate(
                       [("VA", "A", "V"), ("VB", "B", "V"), ("VC", "C", "V"),
                        ("IA", "A", "A"), ("IB", "B", "A"), ("IC", "C", "A")]))
    return Record(source=None, format_name="teste", station=nome, line_frequency=F0,
                  start_time=datetime(2026, 10, 23, 9, 0, 0), analog_channels=canais,
                  sample_rates=(SampleRate(rate_hz=TAXA, last_sample=n),), analog=dados, time=t)


LINHA = {"r": Z1L.real, "x": Z1L.imag, "km": L_KM, "r0": Z0L.real, "x0": Z0L.imag}


def _painel(m=0.43, rf=0.0, tipo="AG", linha=LINHA, so_a=False, atraso=0.0, giro=0.0, **kw):
    rede = _rede(m, rf, tipo, **kw)
    a = _registro(rede["S"])
    b = None if so_a else _registro(rede["R"], atraso=atraso, giro=giro, nome="SE BETA")
    return ldl.montar(a, b, atraso, linha, None)


# ---------------------------------------------------------------------------
# A conta vetorizada é a mesma da planilha
# ---------------------------------------------------------------------------

def test_seqneg_vetor_e_a_conta_da_planilha():
    rnd = np.random.default_rng(7)
    n = 400
    z = lambda: rnd.normal(size=n) + 1j * rnd.normal(size=n)  # noqa: E731
    v2s, i2s, v2r, i2r = z() * 5000, z() * 300, z() * 5000, z() * 300
    zl = complex(4, 20)
    vet = ldl.seqneg_vetor(v2s, i2s, v2r, i2r, zl)
    for k in range(n):
        r = seqneg.localizar(complex(v2s[k]), complex(i2s[k]),
                             complex(v2r[k]), complex(i2r[k]), zl)
        esperado = np.nan if r is None or r.m is None else r.m
        if np.isnan(esperado):
            assert np.isnan(vet[k])
        else:
            assert vet[k] == pytest.approx(esperado, abs=1e-12)


# ---------------------------------------------------------------------------
# A falta sintética, nos dois métodos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("m", [0.1, 0.43, 0.85])
def test_falta_ag_franca_os_dois_metodos_acham(m):
    p = _painel(m=m, rf=0.0, delta=0.0)
    assert p["laco"] == "AN" and p["tipo"] == "AG"
    assert p["metodos"]["seqneg"]["km"] == pytest.approx(m * L_KM, abs=0.05)
    # Franca e sem carga, a reatância do laço é exata (a Rf é zero).
    assert p["metodos"]["laco"]["km"] == pytest.approx(m * L_KM, abs=0.05)
    assert p["resultado"]["metodo"] == "seqneg"


def test_falta_bc_usa_o_laco_fase_fase_sem_z0():
    linha = {k: v for k, v in LINHA.items() if k not in ("r0", "x0")}
    p = _painel(m=0.6, rf=0.0, tipo="BC", linha=linha, delta=0.0)
    assert p["laco"] == "BC"
    assert p["metodos"]["laco"]["km"] == pytest.approx(0.6 * L_KM, abs=0.05)
    assert p["metodos"]["seqneg"]["km"] == pytest.approx(0.6 * L_KM, abs=0.05)


def test_com_rf_e_carga_a_seqneg_nao_se_move_e_o_laco_sim():
    """O efeito de reatância: a Rf com carga entorta o laço, não a seq. negativa."""
    p = _painel(m=0.5, rf=15.0, delta=25.0)
    assert p["metodos"]["seqneg"]["km"] == pytest.approx(30.0, abs=0.05)
    assert abs(p["metodos"]["laco"]["km"] - 30.0) > 1.0


def test_laco_de_terra_sem_z0_diz_por_que_nao_calcula():
    linha = {k: v for k, v in LINHA.items() if k not in ("r0", "x0")}
    p = _painel(linha=linha)
    assert p["metodos"]["laco"]["km"] is None
    assert "Z0" in p["metodos"]["laco"]["motivo"]
    assert p["resultado"]["metodo"] == "seqneg"


def test_com_um_terminal_so_vale_o_laco():
    p = _painel(so_a=True, delta=0.0)
    assert p["metodos"]["seqneg"]["km"] is None
    assert "outro terminal" in p["metodos"]["seqneg"]["motivo"]
    assert p["resultado"]["metodo"] == "laco"


def test_relogio_de_b_atrasado_e_girado_nao_muda_a_seq_negativa():
    """B grava a falta 37 ms depois e com o ângulo girado 50°: alinhado pelo
    início da falta, a resposta é a mesma — só módulos entram."""
    p = _painel(m=0.43, atraso=0.0375, giro=50.0)
    assert p["metodos"]["seqneg"]["km"] == pytest.approx(0.43 * L_KM, abs=0.05)


def test_falta_eliminada_pelo_outro_terminal_acaba_o_plato_no_fim_dela():
    """A corrente volta à CARGA, sem abertura (o registro real do COXIPO): o
    platô não pode ir até o fim do arquivo, senão a conta lê a carga."""
    rede = _rede(0.43, 0.0, "AG", delta=0.0)
    a = _registro(rede["S"], abre=False)
    p = ldl.montar(a, _registro(rede["R"], abre=False, nome="SE BETA"), 0.0, LINHA, None)
    assert p["eventos"]["plato"][1] < T_ABRE
    assert p["metodos"]["seqneg"]["km"] == pytest.approx(0.43 * L_KM, abs=0.05)
    assert p["metodos"]["laco"]["km"] == pytest.approx(0.43 * L_KM, abs=0.05)


def test_falta_curta_de_dois_ciclos_e_meio_ainda_tem_plato():
    fim = T_FALTA + 2.6 / F0
    rede = _rede(0.43, 0.0, "AG", delta=0.0)
    p = ldl.montar(_registro(rede["S"], fim=fim), _registro(rede["R"], fim=fim, nome="SE BETA"),
                   0.0, LINHA, None)
    t0, t1 = p["eventos"]["plato"]
    assert T_FALTA + 1.0 / F0 < t0 < t1 < fim
    assert p["metodos"]["seqneg"]["km"] == pytest.approx(0.43 * L_KM, abs=0.1)


def test_numero_fora_da_linha_nao_vira_resultado():
    """Corrente de A invertida: o laço sai negativo e é recusado com o motivo."""
    rede = _rede(0.43, 0.0, "AG", delta=0.0)
    for chave in ("i", "pre_i"):
        rede["S"][chave] = tuple(-x for x in rede["S"][chave])
    p = ldl.montar(_registro(rede["S"]), None, 0.0, LINHA, None)
    assert p["metodos"]["laco"]["fora"] is True
    motivo = p["metodos"]["laco"]["motivo"]
    # A corrente invertida também vira o 32Q: «para trás» é o motivo mais preciso.
    assert "fora da linha" in motivo or "PARA TRÁS" in motivo
    assert p["resultado"] is None
    assert p["cursor"]["A"]["frente"] is False


def test_sem_linha_nada_e_calculado():
    p = _painel(linha=None)
    assert p["resultado"] is None
    assert all("linha" in x["motivo"] for x in p["metodos"].values())


# ---------------------------------------------------------------------------
# O cursor 1: V2 na referência e a direção
# ---------------------------------------------------------------------------

def test_cursor_no_plato_ve_os_dois_para_frente():
    p = _painel(m=0.43, rf=5.0)
    c = p["cursor"]
    assert c["no_plato"]
    assert c["A"]["frente"] is True and c["B"]["frente"] is True
    # V2 na referência: I2 adiantada de V2 por 180° − ∠Z2 da fonte.
    esperado = 180 - math.degrees(cmath.phase(complex(1, 8)))
    assert c["A"]["ang"] == pytest.approx(esperado, abs=1.0)


def test_falta_atras_de_b_aparece_como_reversa():
    """Inverter a corrente de B é ver a falta do outro lado do TC dele."""
    rede = _rede(0.43, 5.0, "AG")
    for chave in ("i", "pre_i"):
        rede["R"][chave] = tuple(-x for x in rede["R"][chave])
    p = ldl.montar(_registro(rede["S"]), _registro(rede["R"], nome="SE BETA"), 0.0, LINHA, None)
    assert p["cursor"]["A"]["frente"] is True
    assert p["cursor"]["B"]["frente"] is False


def test_cursor_fora_do_plato_diz_que_esta_fora():
    p = ldl.montar(_registro(_rede(0.43, 0, "AG")["S"]), None, 0.0, LINHA, 0.05)
    assert p["cursor"]["no_plato"] is False
    # Antes da falta o laço mediria a CARGA: não há LDL ali, e o cursor diz isso.
    assert p["cursor"]["km"]["laco"] is None


def test_o_pacote_nao_tem_nan_que_o_json_nao_aceita():
    import json
    p = _painel(m=0.43, rf=5.0)
    json.dumps(p, allow_nan=False)


# ---------------------------------------------------------------------------
# O Z0 nas três fontes da linha
# ---------------------------------------------------------------------------

def test_base_de_linhas_guarda_e_le_o_z0(tmp_path):
    class Base:
        def gaveta(self, nome):
            pasta = tmp_path / nome
            pasta.mkdir(exist_ok=True)
            return pasta
    base = Base()
    linhas.gravar(base, linhas.Linha("LT X", "ALFA", "BETA", 4.8, 24.0, 60.0, 18.0, 72.0))
    lida = linhas.listar(base)[0]
    assert (lida.r0_ohm, lida.x0_ohm) == (18.0, 72.0)


def test_base_de_linhas_antiga_sem_z0_continua_valendo(tmp_path):
    class Base:
        def gaveta(self, nome):
            pasta = tmp_path / nome
            pasta.mkdir(exist_ok=True)
            return pasta
    base = Base()
    (tmp_path / "linhas" / "linhas.csv").parent.mkdir(exist_ok=True)
    (tmp_path / "linhas" / "linhas.csv").write_text(
        "nome;terminal_s;terminal_r;r1_ohm;x1_ohm;comprimento_km\n"
        "LT C;COXIPO;BARRO DURO;0,67;3,759;9,29\n",
        encoding="utf-8")
    lida = linhas.listar(base)[0]
    assert lida.r1_ohm == pytest.approx(0.67) and lida.r0_ohm is None


def test_ajustes_trazem_o_z0_em_primario():
    ajustes = {"Z1MAG": "1", "Z1ANG": "90", "Z0MAG": "3", "Z0ANG": "90", "LL": "10"}
    s = seqneg.linha_dos_ajustes(ajustes, 200.0)
    assert s["x0"] == pytest.approx(600.0) and s["r0"] == pytest.approx(0.0, abs=1e-9)


def test_z0_digitado_na_mesma_forma_do_z1():
    digitado = {"forma": "rx", "r": 4.8, "x": 24, "r0": 18, "x0": 72, "km": 60}
    s = seqneg.linha_digitada(digitado, None)
    assert (s["r0"], s["x0"]) == (18, 72)
    sem = seqneg.linha_digitada({"forma": "rx", "r": 4.8, "x": 24, "km": 60}, None)
    assert "r0" not in sem


def test_fasor_do_seqneg_sai_do_trecho_e_nao_de_sample_rates():
    """`nrates = 0` (SEL-751, 311C): a taxa vem do vetor de tempo. Antes o
    fasor saía `None` e a LDL dizia «sem relação de TC/TP», que não era o caso."""
    r = _registro(_rede(0.43, 0.0, "AG")["S"])
    n = r.n_samples - 1
    esperado = seqneg._fasor(r, 0, n)
    r.sample_rates = (SampleRate(rate_hz=0.0, last_sample=r.n_samples),)
    assert esperado is not None and seqneg._fasor(r, 0, n) == pytest.approx(esperado)
    # Janela que atravessaria a fronteira entre dois trechos: não é um ciclo.
    taxa = r.trechos[0].taxa_hz
    r.sample_rates = (SampleRate(rate_hz=taxa, last_sample=n - 5),
                      SampleRate(rate_hz=taxa, last_sample=r.n_samples))
    assert seqneg._fasor(r, 0, n) is None


def test_tensao_so_em_delta_vira_aviso_e_nao_derruba_a_rota():
    """Com VAB/VBC/VCA a trinca de tensão não tem chave `A`: `ldl.terminal`
    levantava KeyError e a rota de localizar devolvia 500."""
    from dataclasses import replace
    r = _registro(_rede(0.43, 0.0, "AG")["S"])
    lacos = {0: ("VAB", "AB"), 1: ("VBC", "BC"), 2: ("VCA", "CA")}
    r.analog_channels = tuple(
        replace(c, name=lacos[c.index][0], phase=lacos[c.index][1]) if c.index in lacos else c
        for c in r.analog_channels)
    t = ldl.terminal(r)
    assert t.v is None and "entre fases" in t.aviso
    assert seqneg.fasores_de(r, r.n_samples - 1)["v2"] is None


def test_base_de_linhas_nao_arredonda_o_que_se_digitou(tmp_path):
    """`{v:g}` guardava seis algarismos: 3,7591234 voltava 3,75912."""
    class Base:
        def gaveta(self, nome):
            pasta = tmp_path / nome
            pasta.mkdir(exist_ok=True)
            return pasta
    base = Base()
    linhas.gravar(base, linhas.Linha("LT X", "ALFA", "BETA", 0.6712345, 3.7591234, 9.2912))
    lida = linhas.listar(base)[0]
    assert (lida.r1_ohm, lida.x1_ohm, lida.comprimento_km) == (0.6712345, 3.7591234, 9.2912)
    assert linhas._numero("nan") is None and linhas._numero("inf") is None


def test_um_terminal_vendo_para_tras_nao_vira_resultado():
    """A regra do cabeçalho do `ldl.py`: um terminal vendo a falta PARA TRÁS a
    põe fora da linha. O cursor mostrava isso e o resultado ignorava — falta
    na barra do outro terminal saía «55,5 km ± 0,3» (validação independente)."""
    rede = _rede(0.43, 5.0, "AG")
    for chave in ("i", "pre_i"):
        rede["R"][chave] = tuple(-x for x in rede["R"][chave])
    p = ldl.montar(_registro(rede["S"]), _registro(rede["R"], nome="SE BETA"), 0.0, LINHA, None)
    assert p["resultado"] is None
    assert "IED B" in p["direcao"]
    for m in ("seqneg", "laco"):
        info = p["metodos"][m]
        assert info["km"] is None or (info["fora"] and "PARA TRÁS" in info["motivo"]), m


def test_sem_sequencia_negativa_ela_nao_localiza_e_o_laco_assume():
    """Trifásica: I2 é ruído. Simulado aqui com I2 artificialmente pequena —
    a falta BC com a corrente de B equilibrada pela carga não serve; basta
    conferir a guarda com o limiar."""
    rede = _rede(0.43, 0.0, "BC")
    a, b = _registro(rede["S"]), _registro(rede["R"], nome="SE BETA")
    normal = ldl.montar(a, b, 0.0, LINHA, None)
    assert normal["metodos"]["seqneg"]["km"] is not None
    antes = ldl.MINIMO_I2_SOBRE_I1
    try:
        ldl.MINIMO_I2_SOBRE_I1 = 10.0          # nenhuma falta passa
        p = ldl.montar(a, b, 0.0, LINHA, None)
    finally:
        ldl.MINIMO_I2_SOBRE_I1 = antes
    assert p["metodos"]["seqneg"]["km"] is None and "I2" in p["metodos"]["seqneg"]["motivo"]
    assert p["resultado"]["metodo"] == "laco"


def test_bhaskara_estavel_nao_perde_algarismos():
    """Com A pequeno a forma `(−B ± √Δ)/2A` dava 0,50526 onde a resposta é
    0,5: a raiz certa saía de uma subtração de dois números quase iguais."""
    z = complex(4.0, 40.0)
    # Rede simétrica (Z2 iguais nas pontas) e falta no meio: A ≈ 0.
    zf = complex(1.0, 8.0)
    i2 = 1.0 / (zf + 0.5 * z)
    v2s = -zf * i2
    r = seqneg.localizar(v2s, i2, v2s, i2, z)
    assert r is not None and r.m == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Takagi e a seq. negativa distribuída (25/10/2026)
# ---------------------------------------------------------------------------

def test_distribuida_sem_capacitancia_e_a_concentrada():
    """Com B → 0 a equação do telegrafista vira a queda `m·Z·I`, e o Newton
    para na raiz concentrada."""
    z = complex(10.0, 50.0)
    zs, zr, m = complex(3.0, 30.0), complex(5.0, 40.0), 0.3
    # Rede concentrada em sequência negativa: a falta injeta I2 nas duas pontas.
    zs_lado, zr_lado = zs + m * z, zr + (1 - m) * z
    i2s = zr_lado / (zs_lado + zr_lado)                # o divisor de corrente
    i2r = zs_lado / (zs_lado + zr_lado)
    v2s, v2r = -zs * i2s, -zr * i2r
    arr = lambda x: np.array([x])  # noqa: E731
    m0 = ldl.seqneg_vetor(arr(v2s), arr(i2s), arr(v2r), arr(i2r), z)
    assert m0[0] == pytest.approx(m, abs=1e-9)
    md = ldl.seqneg_distribuida(arr(v2s), arr(i2s), arr(v2r), arr(i2r), z, 1e-12, m0)
    assert md[0] == pytest.approx(m, abs=1e-6)


def test_distribuida_acha_a_falta_numa_linha_com_capacitancia():
    """A linha resolvida pela equação do telegrafista, com a falta a 20 % de S:
    a distribuída acha 0,2; a concentrada não (a corrente capacitiva)."""
    z, b = complex(20.0, 122.5), 860e-6           # 250 km a 138 kV
    gl, zc = cmath.sqrt(z * 1j * b), cmath.sqrt(z / (1j * b))
    m, zs, zr = 0.2, complex(5.0, 60.0), complex(8.0, 45.0)

    def no_ponto(trecho, zfonte, i_t):
        # V = −Zfonte·I na barra; desce a linha `trecho` pu pelo telegrafista.
        return (-zfonte * i_t * cmath.cosh(gl * trecho)
                - zc * i_t * cmath.sinh(gl * trecho))
    # I2S = 1; I2R é o que põe a MESMA tensão no ponto da falta pelos dois lados.
    i2s = 1.0 + 0j
    i2r = no_ponto(m, zs, i2s) / no_ponto(1 - m, zr, 1.0)
    v2s, v2r = -zs * i2s, -zr * i2r
    arr = lambda x: np.array([x])  # noqa: E731
    m0 = ldl.seqneg_vetor(arr(v2s), arr(i2s), arr(v2r), arr(i2r), z)
    md = ldl.seqneg_distribuida(arr(v2s), arr(i2s), arr(v2r), arr(i2r), z, b, m0)
    assert md[0] == pytest.approx(m, abs=1e-6)
    assert abs(m0[0] - m) > 1e-3


def test_takagi_ignora_rf_quando_delta_i_esta_em_fase_com_a_falta():
    """Laço de fase com a corrente de falta em fase com ΔI (rede homogênea):
    o laço pela reatância erra com a carga; o Takagi, não."""
    z, m, rf = complex(10.0, 50.0), 0.4, 20.0
    carga = 300.0 + 0j
    i_f = 1500.0 * cmath.exp(-1j * math.radians(70))
    di = 0.6 * i_f                                     # o pedaço que vem de S
    i = carga + di
    v = m * z * i + rf * i_f
    arr = lambda x: np.array([x, x])  # noqa: E731
    v_d = {"A": arr(v), "B": arr(0j), "C": arr(0j)}
    i_d = {"A": np.array([carga, i]), "B": arr(0j), "C": arr(0j)}
    tk = ldl.takagi_vetor(v_d, i_d, "AB", z, None, 0)
    assert tk[1] == pytest.approx(m, abs=1e-9)
    assert abs(ldl.laco_vetor(v_d, i_d, "AB", z, None)[1] - m) > 0.01


def test_takagi_sem_pre_falta_diz_por_que():
    assert ldl.takagi_vetor({}, {}, "AB", complex(1, 5), None, None) is None


def test_capacitancia_digitada_e_da_base(tmp_path):
    total = seqneg.linha_digitada({"forma": "rx", "r": 4.8, "x": 24, "km": 60,
                                   "b1": "200", "b0": "120"}, None)
    assert (total["b1"], total["b0"]) == (200.0, 120.0)
    por_km = seqneg.linha_digitada({"forma": "km", "rkm": 0.08, "xkm": 0.4, "km": 60,
                                    "b1km": 3.4}, None)
    assert por_km["b1"] == pytest.approx(204.0) and "b0" not in por_km
    sec = seqneg.linha_digitada({"forma": "rx", "r": 1, "x": 5, "km": 3, "base": "sec",
                                 "b1": 120}, 120.0)
    assert sec["b1"] == pytest.approx(1.0)              # admitância divide
    assert "b1" not in seqneg.linha_digitada({"forma": "rx", "r": 1, "x": 5, "km": 3}, None)
    assert ldl.linha_com_z0(total)["b1"] == 200.0

    class Base:
        def gaveta(self, nome):
            pasta = tmp_path / nome
            pasta.mkdir(exist_ok=True)
            return pasta
    base = Base()
    linhas.gravar(base, linhas.Linha("LT X", "ALFA", "BETA", 4.8, 24.0, 60.0, 18.0, 72.0,
                                     204.0, 130.0))
    linhas.gravar(base, linhas.Linha("LT Y", "GAMA", "DELTA", 4.8, 24.0, 60.0))
    lidas = {x.nome: x for x in linhas.listar(base)}
    assert (lidas["LT X"].b1_us, lidas["LT X"].b0_us) == (204.0, 130.0)
    assert lidas["LT Y"].b1_us is None
