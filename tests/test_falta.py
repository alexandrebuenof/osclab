"""Testes do classificador de falta.

Sem fixture, pelo mesmo motivo do `test_impedancia`: o `tudo.py` pula em
silêncio quem pede fixture, e teste que não roda é pior que teste nenhum.

Os registros são sintéticos e cobrem os **onze** tipos. Um classificador que
só foi visto acertar numa falta monofásica não foi visto acertar.
"""

from __future__ import annotations

import cmath
import math
from datetime import datetime

import numpy as np

from osclab.analysis import falta
from osclab.formats.base import AnalogChannel, Record, SampleRate

TAXA = 1920.0
F0 = 60.0
VN = 138000 / math.sqrt(3)
CARGA = 230.0
T_FALTA = 0.100
T_ABRE = 0.200
T_EVOLUI = 0.150
DURACAO = 0.280

CANAIS_V = {"A": 0, "B": 1, "C": 2}
CANAIS_I = {"A": 3, "B": 4, "C": 5}


def _registro(fases: str = "A", terra: bool = True, *,
              corrente_de_falta: float = 3000.0,
              afunda_para: float = 0.45,
              com_tensao: bool = True,
              abre: bool = True,
              resistiva: bool = False,
              evolui_para: tuple[str, bool] | None = None) -> Record:
    """VA VB VC IA IB IC, com a falta pedida.

    `fases` são as letras envolvidas (`"A"`, `"BC"`, `"ABC"`). `terra` acende
    a componente de sequência zero — numa bifásica pura ela tem de sumir, e é
    isso que o teste da terra precisa ver.
    """
    n = int(DURACAO * TAXA)
    t = np.arange(n) / TAXA
    envolvidas = set(fases)
    dados = np.zeros((6, n))
    w = 2 * math.pi * F0
    ang = {"A": 0.0, "B": -120.0, "C": 120.0}

    fases_0, terra_0 = fases, terra
    for k in range(n):
        # A evolutiva: em T_EVOLUI a falta passa a ser `evolui_para`.
        if evolui_para is not None:
            fases, terra = evolui_para if t[k] >= T_EVOLUI else (fases_0, terra_0)
            envolvidas = set(fases)
        na_falta = T_FALTA <= t[k] < (T_ABRE if abre else DURACAO + 1)
        aberto = abre and t[k] >= T_ABRE
        for j, fase in enumerate(("A", "B", "C")):
            v = cmath.rect(VN, math.radians(ang[fase]))
            i = cmath.rect(CARGA, math.radians(ang[fase] - 18))
            if na_falta and fase in envolvidas:
                modulo = corrente_de_falta * (0.35 if resistiva else 1.0)
                if not terra and len(envolvidas) == 2:
                    # Numa bifásica SEM terra as duas correntes são
                    # exatamente opostas — é isso que faz 3I0 ir a zero
                    # sozinho, sem ninguém zerá-lo na mão. As duas saem do
                    # ÂNGULO DA PRIMEIRA, e não cada uma do seu: baseadas no
                    # próprio ângulo de fase elas ficariam a 60°, não a 180°,
                    # e o 3I0 apareceria onde não deve.
                    ordenadas = sorted(envolvidas)
                    base = ang[ordenadas[0]] - 78
                    giro = 180.0 if fase == ordenadas[1] else 0.0
                    i = cmath.rect(modulo, math.radians(base + giro))
                else:
                    i = cmath.rect(modulo, math.radians(ang[fase] - 78))
                v = cmath.rect(VN * (0.99 if resistiva else afunda_para),
                               math.radians(ang[fase] - 4))
            if aberto:
                i = i * 0.003
                v = cmath.rect(VN, math.radians(ang[fase]))
            dados[j, k] = abs(v) * math.sqrt(2) * math.sin(w * t[k] + cmath.phase(v))
            dados[3 + j, k] = abs(i) * math.sqrt(2) * math.sin(w * t[k] + cmath.phase(i))

    canais = []
    for idx, (nome, fase, unidade) in enumerate(
            [("VA", "A", "V"), ("VB", "B", "V"), ("VC", "C", "V"),
             ("IA", "A", "A"), ("IB", "B", "A"), ("IC", "C", "A")]):
        canais.append(AnalogChannel(index=idx, name=nome, phase=fase,
                                    unit=unidade, scaling="P"))
    if not com_tensao:
        dados = dados[3:]
        canais = [AnalogChannel(index=i, name=c.name, phase=c.phase,
                                unit=c.unit, scaling="P")
                  for i, c in enumerate(canais[3:])]
    return Record(
        source=None, format_name="teste", station="SE TESTE",
        line_frequency=F0, start_time=datetime(2026, 10, 15, 13, 0, 0),
        analog_channels=tuple(canais),
        sample_rates=(SampleRate(rate_hz=TAXA, last_sample=n),),
        analog=dados, time=t,
    )


def _classificar(fases="A", terra=True, **kw) -> falta.Veredito:
    r = _registro(fases, terra, **kw)
    if kw.get("com_tensao") is False:
        return falta.classificar(r, {"A": 0, "B": 1, "C": 2})
    return falta.classificar(r, CANAIS_I, CANAIS_V)


# ---------------------------------------------------------------------------
# Os onze tipos
# ---------------------------------------------------------------------------

def test_monofasicas():
    for fase in ("A", "B", "C"):
        v = _classificar(fase, terra=True)
        assert v.tipo == f"{fase}G", (fase, v.tipo, v.porques)
        assert v.fases == (fase,) and v.terra


def test_bifasicas_sem_terra():
    for par in ("AB", "BC", "CA"):
        v = _classificar(par, terra=False)
        assert set(v.fases) == set(par), (par, v.fases, v.porques)
        assert not v.terra, (par, v.porques)
        # Na ordem do ofício: `CA`, e não `AC`. Ver `falta._nome`.
        assert v.tipo == par, (par, v.tipo)


def test_bifasicas_com_terra():
    for par in ("AB", "BC", "CA"):
        v = _classificar(par, terra=True)
        assert set(v.fases) == set(par), (par, v.fases, v.porques)
        assert v.terra, (par, v.porques)
        assert v.tipo.endswith("G")


def test_trifasica_sem_terra():
    v = _classificar("ABC", terra=False)
    assert set(v.fases) == {"A", "B", "C"}
    assert not v.terra, v.porques


def test_trifasica_com_terra_tambem_e_reconhecida_como_trifasica():
    v = _classificar("ABC", terra=True)
    assert set(v.fases) == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# O que separa cada pista
# ---------------------------------------------------------------------------

def test_a_terra_sai_do_3i0_superposto_e_nao_do_absoluto():
    """Numa bifásica pura as duas correntes se cancelam e 3I0 não sobe."""
    v = _classificar("AB", terra=False)
    assert not v.terra
    assert any("3I0" in p and "sem terra" in p for p in v.porques), v.porques


def test_falta_resistiva_e_classificada_pela_corrente_mesmo_sem_afundar():
    """A tensão mal cai; a corrente é quem elege a fase."""
    v = _classificar("B", terra=True, resistiva=True)
    assert v.fases == ("B",) and v.terra
    assert any("quase não afundou" in p for p in v.porques), v.porques


def test_sem_trinca_de_tensao_o_veredito_sai_da_corrente_e_diz_isso():
    v = _classificar("C", terra=True, com_tensao=False)
    assert v.fases == ("C",)
    assert v.confianca == "media"
    assert any("Sem trinca de tensão" in d for d in v.discordancias)


def test_com_as_duas_pistas_concordando_a_confianca_e_alta():
    v = _classificar("A", terra=True)
    assert v.confianca == "alta", v.porques


# ---------------------------------------------------------------------------
# Onde começa e onde acaba
# ---------------------------------------------------------------------------

def test_o_instante_da_falta_cai_no_lugar():
    v = _classificar("A")
    assert v.instante is not None
    erro_em_ciclos = abs(v.instante - T_FALTA * TAXA) / (TAXA / F0)
    assert erro_em_ciclos < 0.5, (v.instante, erro_em_ciclos)


def test_a_abertura_e_encontrada():
    v = _classificar("A")
    assert v.fim is not None
    erro_em_ciclos = abs(v.fim - T_ABRE * TAXA) / (TAXA / F0)
    assert erro_em_ciclos < 2.0, (v.fim, erro_em_ciclos)


def test_sem_taxa_declarada_a_taxa_sai_do_vetor_de_tempo():
    # SEL-751 e 311C escrevem `nrates = 0` no `.cfg`: o tempo vem do carimbo
    # de cada amostra. Lendo `sample_rates[0]` a taxa era 0 e faltas de 9 kA
    # saíam «nenhuma descontinuidade».
    r = _registro("A")
    r.sample_rates = (SampleRate(rate_hz=0.0, last_sample=r.n_samples),)
    v = falta.classificar(r, CANAIS_I, CANAIS_V)
    assert v.tipo == "AG", v.porques
    assert abs(v.instante - T_FALTA * TAXA) / (TAXA / F0) < 0.5


def test_sem_abertura_o_fim_e_none_e_a_falta_ainda_classifica():
    v = _classificar("A", abre=False)
    assert v.fim is None and v.tipo == "AG"


def test_registro_so_de_carga_nao_inventa_falta():
    n = int(0.2 * TAXA)
    t = np.arange(n) / TAXA
    dados = np.zeros((6, n))
    w = 2 * math.pi * F0
    for j, a in enumerate((0.0, -120.0, 120.0)):
        dados[j] = VN * math.sqrt(2) * np.sin(w * t + math.radians(a))
        dados[3 + j] = CARGA * math.sqrt(2) * np.sin(w * t + math.radians(a - 18))
    canais = tuple(AnalogChannel(index=i, name=n_, phase=p, unit=u, scaling="P")
                   for i, (n_, p, u) in enumerate(
                       [("VA", "A", "V"), ("VB", "B", "V"), ("VC", "C", "V"),
                        ("IA", "A", "A"), ("IB", "B", "A"), ("IC", "C", "A")]))
    r = Record(source=None, format_name="teste", line_frequency=F0,
               analog_channels=canais,
               sample_rates=(SampleRate(rate_hz=TAXA, last_sample=n),),
               analog=dados, time=t)
    v = falta.classificar(r, CANAIS_I, CANAIS_V)
    assert not v.houve_falta
    assert any("não tem falta" in p for p in v.porques), v.porques


# ---------------------------------------------------------------------------
# O laço que o plano de impedância deve abrir
# ---------------------------------------------------------------------------

def test_o_laco_da_monofasica_e_o_de_terra_daquela_fase():
    assert _classificar("B").laco == "BN"


def test_o_laco_da_bifasica_e_o_de_fase():
    assert _classificar("BC", terra=False).laco == "BC"
    assert _classificar("CA", terra=False).laco == "CA"


def test_sem_falta_o_laco_cai_no_padrao():
    vazio = falta.Veredito(tipo="", fases=(), terra=False)
    assert vazio.laco == "AN"


# ---------------------------------------------------------------------------
# A honestidade do veredito
# ---------------------------------------------------------------------------

def test_o_veredito_sempre_diz_em_que_se_apoiou():
    v = _classificar("A")
    assert v.porques and all(isinstance(p, str) and p for p in v.porques)


def test_nenhuma_conclusao_sem_evidencia_escrita():
    """Um veredito sem porquês seria um palpite com cara de medida."""
    for fases, terra in (("A", True), ("AB", False), ("ABC", False)):
        v = _classificar(fases, terra=terra)
        assert len(v.porques) >= 2, (fases, v.porques)


# ---------------------------------------------------------------------------
# Comparar com o que o relé gravou
# ---------------------------------------------------------------------------

def test_o_T_da_sel_e_trip_e_nao_terra():
    """`AB T` é «falta AB, com trip»: a terra vem dentro da sigla (`ABG T`).
    Conferido no alimentador de 21/09 (`AB T`, TRIP aceso, 3I0 superposto
    0 %) e no de 17/09 (`CA` sem T, e sem TRIP). Ler o T como terra punha
    todo AB nosso em conflito com o relé."""
    assert falta.mesmo_tipo("AG", "AG T")
    assert falta.mesmo_tipo("AB", "AB T")
    assert falta.mesmo_tipo("BCG", "BCG T")
    assert falta.mesmo_tipo("AN", "AG")
    assert falta.mesmo_tipo("ABC", "3PH")
    assert falta.mesmo_tipo("ABC", "ABC T")


def test_vereditos_diferentes_conflitam():
    assert not falta.mesmo_tipo("AG", "AB T")
    assert not falta.mesmo_tipo("ABG", "AB T")     # terra muda o veredito
    assert not falta.mesmo_tipo("BCG", "BC T")
    assert not falta.mesmo_tipo("BC", "CA")


def test_sigla_vazia_nao_e_conflito():
    """Ausência não é discordância: um COMTRADE sem classificação do relé
    não pode acender aviso nenhum."""
    assert falta.mesmo_tipo("AG", "")
    assert falta.mesmo_tipo("", "AG T")
    assert falta.mesmo_tipo("", "")


def test_a_ordem_das_letras_nao_importa():
    assert falta.mesmo_tipo("BC", "CB")
    assert falta.mesmo_tipo("CAG", "ACG")


def test_a_bifasica_c_a_se_escreve_CA():
    """O relé grava `CA`, o laço do plano se chama `CA` e é assim que se
    fala. `AC` era a ordem alfabética das letras, não a do ofício."""
    assert falta._nome(("A", "C"), False) == "CA"
    assert falta._nome(("A", "C"), True) == "CAG"
    assert falta._nome(("A", "B"), False) == "AB"
    assert falta._nome(("B", "C"), True) == "BCG"
    assert falta._nome(("A", "B", "C"), False) == "ABC"


# ---------------------------------------------------------------------------
# O selo: a cor das fases e o que o relé escreveu no .hdr
# ---------------------------------------------------------------------------

def test_a_cor_do_selo_sai_das_fases_e_ignora_a_terra():
    from osclab.library.acervo import cor_da_falta
    assert cor_da_falta("CG") == "fase-c"
    assert cor_da_falta("CA") == "fase-ca"
    assert cor_da_falta("CAG") == "fase-ca"
    assert cor_da_falta("AB") == "fase-ab"
    assert cor_da_falta("ABCG") == "fase-abc"
    assert cor_da_falta("") == ""


def test_o_hdr_da_sel_traz_o_tipo_do_evento(tmp_path):
    """O `.cfg` não tem campo para o tipo da falta; a SEL escreve no `.hdr`,
    em inglês (`Event:`) ou no relatório traduzido (`Tipo:`)."""
    from osclab.formats import ajustes
    (tmp_path / "x.hdr").write_text(
        "Event: AB T              Location: $$$$.$$\n"
        "Event Number: 10795      Shot 3P: 0\n", encoding="latin-1")
    assert ajustes.classificacao_no_hdr(tmp_path, ["x.cfg", "x.hdr"]) == "AB T"
    (tmp_path / "y.hdr").write_text("Tipo: AG T           Localização: 62.4 %\n",
                                    encoding="latin-1")
    assert ajustes.classificacao_no_hdr(tmp_path, ["y.hdr"]) == "AG T"


def test_hdr_sem_tipo_de_falta_nao_inventa_um(tmp_path):
    """O SIPROTEC escreve só quem disparou; `Event: TRIG` não é fase."""
    from osclab.formats import ajustes
    (tmp_path / "s.hdr").write_text("Station Name: SE X\nTrigger name: Web\n",
                                    encoding="utf-8")
    (tmp_path / "t.hdr").write_text("Event: TRIG\n", encoding="utf-8")
    assert ajustes.classificacao_no_hdr(tmp_path, ["s.hdr"]) == ""
    assert ajustes.classificacao_no_hdr(tmp_path, ["t.hdr"]) == ""


# ---------------------------------------------------------------------------
# A falta evolutiva
# ---------------------------------------------------------------------------

def test_bifasica_que_pega_a_terra_e_evolutiva():
    v = _classificar("AB", False, evolui_para=("AB", True))
    assert v.tipo_inicial == "AB"
    assert v.tipo == "ABG"
    assert v.sigla == "AB → ABG"
    # O laço é o do FIM: é o que o relé viu ao disparar.
    assert v.laco == "AB"
    assert any("Evolutiva" in p for p in v.porques)


def test_o_instante_da_evolucao_cai_perto_de_onde_ela_aconteceu():
    v = _classificar("AB", False, evolui_para=("AB", True))
    meio_ciclo = TAXA / F0 / 2
    assert abs(v.evolucao - T_EVOLUI * TAXA) <= 1.5 * meio_ciclo


def test_monofasica_que_vira_bifasica_terra_e_evolutiva():
    v = _classificar("A", True, evolui_para=("AB", True))
    assert v.sigla == "AG → ABG"


def test_falta_que_nao_muda_nao_e_evolutiva():
    for fases, terra in (("A", True), ("BC", False), ("CA", True), ("ABC", False)):
        v = _classificar(fases, terra)
        assert v.tipo_inicial == "", (fases, terra, v.porques)
        assert v.sigla == v.tipo


def test_falta_que_PERDE_fase_nao_vira_evolutiva():
    # Perder fase no fim é TC saturando ou arco apagando, não falta nova.
    v = _classificar("AB", True, evolui_para=("A", True))
    assert v.tipo_inicial == ""
    assert v.tipo == "ABG"


def test_o_rele_concorda_com_o_comeco_ou_com_o_fim_da_evolutiva():
    assert falta.rele_concorda("ABG", "AB", "AB T")
    assert falta.rele_concorda("ABG", "AB", "ABG T")
    assert not falta.rele_concorda("ABG", "AB", "BC")
    assert not falta.rele_concorda("ABG", "", "AB T")


# ---------------------------------------------------------------------------
# O relé disparou? (o raio do selo, 22/10/2026)
# ---------------------------------------------------------------------------

def _com_digitais(nomes_e_linhas) -> Record:
    from osclab.formats.base import StatusChannel
    canais = tuple(StatusChannel(index=i, name=nome)
                   for i, (nome, _) in enumerate(nomes_e_linhas))
    status = np.array([linha for _, linha in nomes_e_linhas], dtype=np.int8)
    return Record(source=None, format_name="teste",
                  status_channels=canais, status=status)


def test_o_primeiro_trip_que_SOBE_e_o_disparo():
    r = _com_digitais([
        ("MAIN : General starting", [0, 1, 1, 1, 1, 1]),
        ("MAIN : Gen. trip command", [0, 0, 0, 1, 1, 0]),
        ("TRIP", [0, 0, 0, 0, 1, 1]),
    ])
    d = falta.disparo_do_rele(r)
    assert d == falta.Disparo(sinal="MAIN : Gen. trip command", amostra=3)


def test_o_trip_geral_ganha_do_trip_externo_que_subiu_antes():
    r = _com_digitais([
        ("MAIN : Parallel trip EXT", [0, 1, 1, 1, 1]),
        ("MAIN : Gen. trip command", [0, 0, 0, 1, 1]),
    ])
    assert falta.disparo_do_rele(r).sinal == "MAIN : Gen. trip command"


def test_siprotec_chama_o_trip_de_operate():
    r = _com_digitais([("LT3 CIMAG:21:Z 1:Operate:general", [0, 0, 1, 1])])
    assert falta.disparo_do_rele(r).amostra == 2


def test_ingeteam_chama_o_trip_de_disparo_e_o_geral_ganha():
    r = _com_digitais([
        ("Disparo 50/51 Fase A", [0, 1, 1, 1, 1]),
        ("Disparo general", [0, 0, 1, 1, 1]),
        ("50BF-Arr./Disp.Fallo int (BF)", [1, 0, 0, 0, 0]),
    ])
    assert falta.disparo_do_rele(r) == falta.Disparo(sinal="Disparo general", amostra=2)


def test_trip_ja_aceso_destravamento_e_bloqueio_nao_sao_disparo():
    r = _com_digitais([
        ("TRIP", [1, 1, 1, 0]),            # aceso desde o início: outro evento
        ("ULTRIP", [0, 1, 1, 1]),          # SEL: destrava o trip
        ("Trip blocked", [0, 1, 1, 1]),
    ])
    assert falta.disparo_do_rele(r) is None


def test_o_T_solto_da_sigla_da_sel_e_trip():
    assert falta.trip_na_sigla("AB T")
    assert falta.trip_na_sigla("AG T")
    assert not falta.trip_na_sigla("CA")
    assert not falta.trip_na_sigla("ER Trigger")
    assert not falta.trip_na_sigla("")
