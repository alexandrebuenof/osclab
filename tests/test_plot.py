"""A matemática do desenho: escalas, marcações e redução de amostras.

É aqui que mora o erro que ninguém vê. Um eixo com escala errada desenha uma
onda de forma perfeita com o número errado ao lado; uma redução ingênua apaga o
pico da falta e mostra uma falta menor do que foi. Nenhum dos dois dá erro
nenhum na tela — só dá resposta errada.
"""

from __future__ import annotations

import numpy as np
import pytest

from osclab.formats import fases, registry
from osclab.formats.base import AnalogChannel
from osclab.plot import escala, janela, leitura, navegacao, serie, unidades
from tests.fabrica import PICO, escrever_comtrade

# ---------------------------------------------------------------------------
# Marcações de eixo: números redondos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("intervalo,alvo,esperado", [
    (1.0, 5, 0.2),
    (10.0, 5, 2.0),
    (100.0, 5, 20.0),
    (7.0, 5, 2.0),
    (0.05, 5, 0.01),
    (13500.0, 5, 5000.0),
])
def test_o_passo_e_sempre_redondo(intervalo, alvo, esperado):
    assert escala.passo_bonito(intervalo, alvo) == pytest.approx(esperado)


def test_marcacoes_ficam_dentro_da_faixa():
    marcas = escala.marcacoes(-100.0, 100.0, alvo=4)
    assert marcas
    assert all(-100.0 <= m <= 100.0 for m in marcas)


def test_o_zero_sai_exatamente_zero():
    """`-0.0` e `1.1e-17` viram "-0" e "0,00000000000000001" na tela."""
    marcas = escala.marcacoes(-1.0, 1.0, alvo=4)
    zeros = [m for m in marcas if abs(m) < 1e-12]
    assert zeros == [0.0]
    assert not any(str(m).startswith("-0.0") for m in zeros)


def test_marcacoes_de_faixa_invalida():
    assert escala.marcacoes(5.0, 5.0) == []
    assert escala.marcacoes(10.0, 1.0) == []
    assert escala.marcacoes(float("nan"), 1.0) == []


# ---------------------------------------------------------------------------
# Faixa vertical
# ---------------------------------------------------------------------------

def test_sinal_alternado_fica_simetrico():
    """Uma corrente de -6743 a +6735 tem que ficar simétrica: senão a linha do
    zero sai do meio, e é ela a referência para ler defasagem."""
    base, topo = escala.faixa(-6743.0, 6735.0)
    assert base == pytest.approx(-topo)
    assert topo > 6743.0


def test_sinal_sempre_positivo_comeca_no_zero():
    """A tensão de bateria (133 a 135 V) numa faixa simétrica viraria uma linha
    reta colada no topo, sem informação nenhuma."""
    base, topo = escala.faixa(133.0, 135.0)
    assert base == 0.0
    assert topo > 135.0


def test_sinal_sempre_negativo():
    base, topo = escala.faixa(-50.0, -10.0)
    assert topo == 0.0
    assert base < -50.0


@pytest.mark.parametrize("intervalo,esperado", [
    (13000.0, 0),
    (100.0, 0),
    (10.0, 1),
    (1.0, 2),
    (0.01, 4),
])
def test_casas_decimais_acompanham_a_grandeza(intervalo, esperado):
    assert escala.casas_decimais(intervalo) == esperado


# ---------------------------------------------------------------------------
# Redução: o pico não pode sumir
# ---------------------------------------------------------------------------

def test_o_pico_sobrevive_a_reducao():
    """O teste mais importante deste arquivo.

    Um pico isolado no meio de 10.000 amostras, reduzidas para 100 colunas:
    pegar uma amostra a cada 100 teria 1% de chance de encontrá-lo.
    """
    t = np.arange(10_000) / 10_000.0
    v = np.zeros((1, 10_000))
    v[0, 4_321] = 9_999.0                      # o pico da falta
    v[0, 7_777] = -8_888.0                     # e o vale

    r = serie.reduzir(t, v, colunas=100)

    assert r.reduzido
    assert r.valores.max() == pytest.approx(9_999.0)
    assert r.valores.min() == pytest.approx(-8_888.0)


def test_reducao_devolve_dois_pontos_por_coluna():
    t = np.arange(1000) / 1000.0
    v = np.random.default_rng(0).normal(size=(3, 1000))
    r = serie.reduzir(t, v, colunas=100)
    assert r.valores.shape[0] == 3
    assert r.valores.shape[1] == r.tempo.size
    assert r.valores.shape[1] <= 100 * 2


def test_tempo_da_reducao_nao_anda_para_tras():
    t = np.arange(5000) / 5000.0
    v = np.zeros((1, 5000))
    r = serie.reduzir(t, v, colunas=300)
    assert np.all(np.diff(r.tempo) >= 0)


def test_poucas_amostras_nao_sao_reduzidas():
    """Reduzir 40 amostras para 900 colunas seria inventar informação."""
    t = np.arange(40) / 40.0
    v = np.zeros((2, 40))
    r = serie.reduzir(t, v, colunas=900)
    assert not r.reduzido
    assert r.valores.shape == (2, 40)


def test_reducao_de_registro_vazio():
    r = serie.reduzir(np.empty(0), np.empty((0, 0)), colunas=100)
    assert r.amostras_na_janela == 0


def test_recorte_por_tempo():
    from osclab.formats.base import Record
    r = Record(source="x", format_name="t", time=np.arange(1000) / 1000.0)
    i0, i1 = serie.recortar(r, 0.2, 0.3)
    assert i0 == 200
    assert 300 <= i1 <= 302
    assert serie.recortar(r, None, None) == (0, 1000)


@pytest.mark.parametrize("unidade,esperado", [
    ("A", "Correntes (A)"),
    ("kV", "Tensões (kV)"),
    ("V", "Tensões (V)"),
    ("Hz", "Frequência (Hz)"),
    ("xyz", "xyz"),
    ("", "sem unidade"),
])
def test_titulo_do_grupo(unidade, esperado):
    assert serie.titulo_do_grupo(unidade) == esperado


# ---------------------------------------------------------------------------
# Fase: declarada, deduzida ou desconhecida
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nome,esperado", [
    ("IAW", "A"), ("IBW", "B"), ("ICX", "C"),      # SEL
    ("VAY", "A"), ("VBZ", "B"),
    ("TC BUC 69kV:I A", "A"),                       # Siemens
    ("TC EXT 34-5kV:I B", "B"),
    ("Current IA", "A"), ("Current IC", "C"),       # Schneider
    ("Voltage A-G", "A"),
    ("TC BUC 69kV:3I0", "N"),                       # residual
    ("Current IN", "N"),
    ("Voltage VNG", "N"),
    ("TC H0 NEUTRO:Ix", "N"),
    ("VDC1", ""), ("FREQ", ""), ("", ""),           # não dá para saber
])
def test_deduz_a_fase_do_nome(nome, esperado):
    assert fases.deduzir(nome) == esperado


def test_a_fase_declarada_tem_prioridade():
    canal = AnalogChannel(index=0, name="IAW", unit="A", phase="C")
    fase, origem = fases.da_canal(canal)
    assert fase == "C"
    assert origem == fases.OrigemDaFase.DECLARADA


def test_g_e_e_viram_n():
    """GE usa G, outros usam E; tudo é o mesmo neutro."""
    for letra in ("G", "E", "N", "0"):
        canal = AnalogChannel(index=0, name="X", unit="A", phase=letra)
        assert fases.da_canal(canal)[0] == "N"


def test_quando_nao_da_para_saber_diz_que_nao_sabe():
    canal = AnalogChannel(index=0, name="VDC1", unit="V", phase="")
    fase, origem = fases.da_canal(canal)
    assert fase == ""
    assert origem == fases.OrigemDaFase.DESCONHECIDA


def test_a_deducao_se_declara_como_deducao():
    """A tela precisa poder dizer "deduzi isto", em vez de afirmar."""
    canal = AnalogChannel(index=0, name="TC BUC 69kV:I A", unit="A", phase="")
    fase, origem = fases.da_canal(canal)
    assert fase == "A"
    assert origem == fases.OrigemDaFase.DEDUZIDA


# ---------------------------------------------------------------------------
# O pacote que vai para a tela
# ---------------------------------------------------------------------------

def _registro(tmp_path, **kw):
    return registry.read(escrever_comtrade(tmp_path, **kw))


def test_a_janela_tem_tudo_que_a_tela_precisa(tmp_path):
    pacote = janela.montar(_registro(tmp_path, na=3, n=256, taxa=960.0))
    assert pacote["grupos"]
    grupo = pacote["grupos"][0]
    assert grupo["titulo"] == "Correntes (A)"
    assert len(grupo["canais"]) == 3
    assert grupo["marcacoes"]
    assert len(pacote["tempo"]) == len(grupo["canais"][0]["serie"])


def test_as_fases_chegam_na_tela(tmp_path):
    pacote = janela.montar(_registro(tmp_path, na=3))
    assert [c["fase"] for c in pacote["grupos"][0]["canais"]] == ["A", "B", "C"]


def test_a_amplitude_chega_certa_na_tela(tmp_path):
    """O que a tela desenha tem que ser o que o relé registrou."""
    pacote = janela.montar(_registro(tmp_path, na=1, n=960, taxa=960.0))
    serie_json = pacote["grupos"][0]["canais"][0]["serie"]
    assert max(abs(v) for v in serie_json) == pytest.approx(PICO, rel=0.02)


def test_a_janela_recorta(tmp_path):
    registro = _registro(tmp_path, n=1000, taxa=1000.0)
    pacote = janela.montar(registro, de=0.2, ate=0.3)
    assert pacote["de"] == pytest.approx(0.2, abs=1e-3)
    assert pacote["ate"] == pytest.approx(0.3, abs=1e-3)
    assert pacote["amostras_na_janela"] < 120


def test_o_instante_do_disparo_vai_junto(tmp_path):
    pacote = janela.montar(_registro(tmp_path, n=128, taxa=960.0))
    assert pacote["disparo_s"] == pytest.approx(0.05, abs=1e-6)


def test_grupos_separados_por_unidade(tmp_path):
    """Corrente e tensão nunca no mesmo eixo — escalas diferentes."""
    cfg = escrever_comtrade(tmp_path, na=2, n=64)
    texto = cfg.read_text(encoding="utf-8").replace(
        "2,CH2,B,,A,", "2,CH2,B,,kV,")
    cfg.write_text(texto, encoding="utf-8")
    pacote = janela.montar(registry.read(cfg))
    assert {g["unidade"] for g in pacote["grupos"]} == {"A", "kV"}


# ---------------------------------------------------------------------------
# Primário × secundário
# ---------------------------------------------------------------------------

def test_converte_para_primario(tmp_path):
    """A fábrica escreve relação 600/5 = 120 em cada canal.

    O pico secundário de 100 A vira 12 000 A primários — que passam do limiar e
    saem em kA. Por isso a comparação leva o divisor do grupo.
    """
    registro = _registro(tmp_path, na=1, n=128)
    secundario = janela.montar(registro, lado="secundario")
    primario = janela.montar(registro, lado="primario")

    pico_s = max(abs(v) for v in secundario["grupos"][0]["canais"][0]["serie"])
    pico_p = max(abs(v) for v in primario["grupos"][0]["canais"][0]["serie"])
    divisor = primario["grupos"][0]["divisor"]

    assert pico_p * divisor == pytest.approx(pico_s * 120.0, rel=0.01)
    assert primario["grupos"][0]["canais"][0]["convertido"] is True
    assert primario["grupos"][0]["canais"][0]["lado"] == "primario"


def test_o_lado_do_arquivo_nao_converte_nada(tmp_path):
    registro = _registro(tmp_path, na=1, escala_primaria=True)
    pacote = janela.montar(registro, lado="arquivo")
    canal = pacote["grupos"][0]["canais"][0]
    assert canal["convertido"] is False
    assert canal["lado"] == "primario"


def test_lado_invalido_cai_no_lado_natural_do_registro(tmp_path):
    """A tela só oferece primário e secundário. Quem não pediu nada — ou pediu
    besteira — recebe o lado em que o registro já está, para abrir uma
    oscilografia nunca converter nada sem o usuário mandar."""
    pacote = janela.montar(_registro(tmp_path), lado="chutando")
    assert pacote["lado_pedido"] == "secundario"        # a fábrica escreve `S`


def test_registro_gravado_em_primario_abre_em_primario(tmp_path):
    cfg = escrever_comtrade(tmp_path, na=1, n=64)
    texto = cfg.read_text(encoding="utf-8").replace(
        "1,CH1,A,,A,0.01,0,0,-32767,32767,600.0,5.0,S",
        "1,CH1,A,,A,0.01,0,0,-32767,32767,600.0,5.0,P")
    cfg.write_text(texto, encoding="utf-8")
    assert janela.montar(registry.read(cfg))["lado_pedido"] == "primario"


def test_sem_relacao_declarada_nao_inventa(tmp_path):
    """Quando o arquivo não traz a relação, o valor fica como está — nunca
    convertido por um palpite."""
    cfg = escrever_comtrade(tmp_path, na=1, n=64)
    texto = cfg.read_text(encoding="utf-8").replace(
        "1,CH1,A,,A,0.01,0,0,-32767,32767,600.0,5.0,S",
        "1,CH1,A,,A,0.01,0,0,-32767,32767,0,0,S")
    cfg.write_text(texto, encoding="utf-8")
    pacote = janela.montar(registry.read(cfg), lado="primario")
    canal = pacote["grupos"][0]["canais"][0]
    assert canal["convertido"] is False
    assert canal["relacao"] == 0


# ---------------------------------------------------------------------------
# Navegação: zoom, arrasto e volta ao inteiro
# ---------------------------------------------------------------------------
#
# Todo teste daqui existe por causa de um jeito de a tela mentir: mostrar uma
# janela fora do registro, encolher até sobrar uma reta, ou mudar de largura
# sozinha no meio do arrasto.

def test_sem_pedido_a_janela_e_o_registro_inteiro(tmp_path):
    r = _registro(tmp_path, n=256, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    assert navegacao.resolver(r) == (t0, t1)


def test_o_ponto_sob_o_cursor_nao_se_mexe(tmp_path):
    """O que faz o zoom parecer natural: a roda amplia em torno do cursor."""
    r = _registro(tmp_path, n=1024, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    foco = t0 + (t1 - t0) * 0.25

    de, ate = navegacao.ampliar(t0, t1, t0, t1, 0.5, foco, navegacao.passo(r))

    assert de < foco < ate
    # O cursor estava a 25% da largura; tem que continuar a 25%.
    assert (foco - de) / (ate - de) == pytest.approx(0.25, abs=1e-6)
    assert (ate - de) == pytest.approx((t1 - t0) * 0.5, rel=1e-6)


def test_zoom_no_meio_do_registro_nao_escapa_pelas_bordas(tmp_path):
    r = _registro(tmp_path, n=512, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    de, ate = navegacao.ampliar(t0, t1, t0, t1, 0.5, t0, navegacao.passo(r))
    assert de >= t0 and ate <= t1


def test_reduzir_demais_para_no_registro_inteiro(tmp_path):
    r = _registro(tmp_path, n=512, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    de, ate = navegacao.ampliar(t0, t1, t0, t1, 10.0, None, navegacao.passo(r))
    assert (de, ate) == (t0, t1)


def test_ampliar_demais_para_no_piso_de_amostras(tmp_path):
    """Ampliar até sobrar uma amostra desenharia uma reta — e reta parece
    sinal limpo."""
    r = _registro(tmp_path, n=2048, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    passo = navegacao.passo(r)

    de, ate = t0, t1
    for _ in range(60):
        de, ate = navegacao.ampliar(t0, t1, de, ate, 0.5, (de + ate) / 2, passo)

    assert (ate - de) == pytest.approx(navegacao.MINIMO_AMOSTRAS * passo, rel=1e-6)


def test_arrastar_nao_muda_a_largura_da_janela(tmp_path):
    r = _registro(tmp_path, n=1024, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    passo = navegacao.passo(r)
    de, ate = navegacao.ampliar(t0, t1, t0, t1, 0.25, (t0 + t1) / 2, passo)
    largura = ate - de

    novo = navegacao.deslocar(t0, t1, de, ate, largura * 0.5, passo)
    assert (novo[1] - novo[0]) == pytest.approx(largura, rel=1e-9)


def test_arrastar_ate_a_borda_desliza_e_para(tmp_path):
    """Na borda a janela para; nunca encolhe nem sai do registro."""
    r = _registro(tmp_path, n=1024, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    passo = navegacao.passo(r)
    de, ate = navegacao.ampliar(t0, t1, t0, t1, 0.25, (t0 + t1) / 2, passo)
    largura = ate - de

    novo = navegacao.deslocar(t0, t1, de, ate, (t1 - t0) * 10, passo)
    assert novo[1] == pytest.approx(t1)
    assert (novo[1] - novo[0]) == pytest.approx(largura, rel=1e-9)

    novo = navegacao.deslocar(t0, t1, de, ate, -(t1 - t0) * 10, passo)
    assert novo[0] == pytest.approx(t0)
    assert (novo[1] - novo[0]) == pytest.approx(largura, rel=1e-9)


def test_janela_invertida_e_aceita_de_cabeca_para_baixo(tmp_path):
    """Selecionar da direita para a esquerda é a mesma faixa."""
    r = _registro(tmp_path, n=256, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    meio = (t0 + t1) / 2
    a = navegacao.resolver(r, de=t0, ate=meio)
    b = navegacao.resolver(r, de=meio, ate=t0)
    assert a == pytest.approx(b)


def test_pedido_absurdo_nao_derruba_nada(tmp_path):
    r = _registro(tmp_path, n=256, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    for pedido in ({"de": -1e9, "ate": 1e9}, {"de": float("nan")},
                   {"zoom": 0.0}, {"zoom": float("inf")},
                   {"andar": float("nan")}):
        de, ate = navegacao.resolver(r, **pedido)
        assert t0 <= de < ate <= t1


def test_tudo_desfaz_o_zoom(tmp_path):
    r = _registro(tmp_path, n=512, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    meio = (t0 + t1) / 2
    assert navegacao.resolver(r, de=meio, ate=t1, tudo=True) == (t0, t1)


def test_o_gesto_se_aplica_sobre_a_janela_atual(tmp_path):
    """Zoom cumulativo: cada roda parte de onde a tela estava."""
    r = _registro(tmp_path, n=1024, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    meio = (t0 + t1) / 2
    de, ate = navegacao.resolver(r, de=t0, ate=meio, zoom=0.5, foco=meio)
    assert (ate - de) == pytest.approx((meio - t0) * 0.5, rel=1e-6)


def test_a_janela_leva_os_limites_do_registro_para_a_tela(tmp_path):
    """A tela precisa saber se ainda há para onde arrastar."""
    r = _registro(tmp_path, n=512, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    meio = (t0 + t1) / 2

    pacote = janela.montar(r)
    assert pacote["limite_de"] == pytest.approx(t0)
    assert pacote["limite_ate"] == pytest.approx(t1)
    assert pacote["inteiro"] is True

    pacote = janela.montar(r, de=meio, ate=t1)
    assert pacote["limite_de"] == pytest.approx(t0)
    assert pacote["inteiro"] is False


def test_a_janela_nunca_desenha_fora_do_registro(tmp_path):
    """Mesmo que alguém digite a janela na URL."""
    r = _registro(tmp_path, n=256, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    pacote = janela.montar(r, de=t1 + 5.0, ate=t1 + 9.0)
    assert pacote["de"] >= t0 and pacote["ate"] <= t1
    assert pacote["amostras_na_janela"] > 0


# ---------------------------------------------------------------------------
# Leitura dos cursores
# ---------------------------------------------------------------------------
#
# O erro que estes testes existem para impedir: ler o valor do TRAÇO em vez da
# amostra. O traço é mínimo e máximo por coluna de pixel — nenhum dos dois é o
# valor no instante, e a diferença só aparece em registro longo, justamente
# onde o engenheiro vai confiar no número.

def test_o_cursor_le_a_amostra_e_nao_o_traco(tmp_path):
    """Com o registro reduzido a 900 colunas, a leitura não pode mudar."""
    r = _registro(tmp_path, na=1, n=6000, taxa=960.0)
    instante = float(r.time[1234])

    (cursor,), _ = _ler(r, [(instante, 0)])
    assert cursor["amostra"] == 1234
    assert cursor["valores"][0]["valor"] == pytest.approx(
        float(r.analog[0, 1234]), rel=1e-9)


def test_o_cursor_encosta_na_amostra_mais_proxima(tmp_path):
    """Entre duas amostras não existe medida — existe palpite."""
    r = _registro(tmp_path, na=1, n=256, taxa=960.0)
    passo = float(r.time[1] - r.time[0])

    (cursor,), _ = _ler(r, [(float(r.time[10]) + passo * 0.4, 0)])
    assert cursor["amostra"] == 10

    (cursor,), _ = _ler(r, [(float(r.time[10]) + passo * 0.6, 0)])
    assert cursor["amostra"] == 11


def test_as_setas_andam_em_amostras(tmp_path):
    r = _registro(tmp_path, na=1, n=256, taxa=960.0)
    alvo = float(r.time[100])
    for passo in (-3, -1, 0, 1, 16):
        (cursor,), _ = _ler(r, [(alvo, passo)])
        assert cursor["amostra"] == 100 + passo


def test_andar_para_fora_do_registro_para_na_borda(tmp_path):
    r = _registro(tmp_path, na=1, n=64, taxa=960.0)
    (primeiro,), _ = _ler(r, [(float(r.time[0]), -50)])
    (ultimo,), _ = _ler(r, [(float(r.time[-1]), 50)])
    assert primeiro["amostra"] == 0
    assert ultimo["amostra"] == 63


def test_o_tempo_entre_cursores_sai_nas_duas_unidades(tmp_path):
    """Um ciclo inteiro a 60 Hz: 16,67 ms e 1,00 ciclo."""
    r = _registro(tmp_path, na=1, n=512, taxa=960.0)     # 16 amostras/ciclo
    a, b = float(r.time[100]), float(r.time[116])

    _, entre = _ler(r, [(a, 0), (b, 0)])
    assert entre["ms"] == pytest.approx(16.6667, abs=1e-3)
    assert entre["ciclos"] == pytest.approx(1.0, abs=1e-4)


def test_nao_se_calcula_frequencia_a_partir_do_intervalo(tmp_path):
    """`1/Δt` engana duas vezes: lê-se como a frequência do sistema, e a
    precisão não sustenta — a 16 amostras/ciclo, uma amostra são 6 % do
    período. Frequência medida exige muitos ciclos e implementação própria."""
    r = _registro(tmp_path, na=1, n=512, taxa=960.0)
    _, entre = _ler(r, [(float(r.time[100]), 0), (float(r.time[116]), 0)])
    assert "hz" not in entre


def test_cursor_para_tras_da_intervalo_negativo(tmp_path):
    """O sinal diz a ordem em que os cursores foram postos."""
    r = _registro(tmp_path, na=1, n=512, taxa=960.0)
    a, b = float(r.time[116]), float(r.time[100])
    _, entre = _ler(r, [(a, 0), (b, 0)])
    assert entre["ms"] < 0
    assert entre["ciclos"] == pytest.approx(-1.0, abs=1e-4)


def test_o_instante_do_cursor_tambem_sai_nas_duas_unidades(tmp_path):
    """A tela alterna a linha inteira entre ms e ciclos; as duas vêm daqui."""
    r = _registro(tmp_path, na=1, n=512, taxa=960.0)
    (cursor,), _ = _ler(r, [(float(r.time[132]), 0)])
    assert cursor["ciclos"] == pytest.approx(cursor["ms"] / 1000.0 * 60.0, abs=1e-4)


def test_um_cursor_so_nao_tem_intervalo(tmp_path):
    r = _registro(tmp_path, na=1, n=128)
    cursores, entre = _ler(r, [(float(r.time[10]), 0), (None, 0)])
    assert entre is None
    assert cursores[1] is None


def test_o_cursor_converte_para_primario(tmp_path):
    """A mesma conta do gráfico — senão o desenho e a leitura discordam."""
    r = _registro(tmp_path, na=1, n=64)
    instante = float(r.time[20])

    (arquivo,), _ = _ler(r, [(instante, 0)])
    (primario,), _ = _ler(r, [(instante, 0)], lado="primario")

    grupo = janela.montar(r, lado="primario")["grupos"][0]
    do_grafico = grupo["canais"][0]
    assert primario["valores"][0]["lado"] == "primario"
    assert primario["valores"][0]["valor"] * grupo["divisor"] == pytest.approx(
        arquivo["valores"][0]["valor"] * do_grafico["relacao"], rel=1e-6)


def test_o_tempo_do_cursor_e_em_relacao_ao_disparo(tmp_path):
    r = _registro(tmp_path, na=1, n=256, taxa=960.0)
    pacote = janela.montar(r)
    disparo = pacote["disparo_s"]
    alvo = float(r.time[50])

    (cursor,), _ = _ler(r, [(alvo, 0)])
    assert cursor["ms"] == pytest.approx((alvo - disparo) * 1000.0, abs=1e-6)


def _ler(registro, pedidos, lado="arquivo"):
    # Cada pedido do teste é (instante, passo); o passo em ciclos entra como 0.
    saida = leitura.em(registro, [(t, p, 0.0) for t, p in pedidos], lado=lado)
    return saida["cursores"], saida["entre"]


def test_shift_seta_anda_um_ciclo_inteiro(tmp_path):
    """Quantas amostras cabem num ciclo é conta do servidor, não da tela."""
    r = _registro(tmp_path, na=1, n=512, taxa=960.0)     # 16 amostras/ciclo
    alvo = float(r.time[100])
    saida = leitura.em(r, [(alvo, 0, 1.0), (alvo, 0, -2.0)])
    assert saida["amostras_por_ciclo"] == pytest.approx(16.0)
    assert saida["cursores"][0]["amostra"] == 116
    assert saida["cursores"][1]["amostra"] == 68


def test_as_casas_decimais_seguem_a_grandeza(tmp_path):
    """Uma casa fixa erra dos dois lados: sobra em 6743,2 A e falta em 0,3 A."""
    assert leitura.casas(6743.21) == 0
    assert leitura.casas(-152.7) == 1
    assert leitura.casas(12.345) == 2
    assert leitura.casas(2.35) == 3
    assert leitura.casas(0.31) == 4
    assert leitura.casas(None) == 1


@pytest.mark.parametrize("valor", [10.0, 100.0, 1000.0, 1.0, 0.1, 9999.0, 3.7])
def test_o_arredondamento_da_tabela_erra_menos_que_o_rele(valor):
    """O erro da tela tem que ser desprezível perto do erro do instrumento.

    Meia casa decimal é o erro de arredondamento, e ele é pior no começo de
    cada década. O relé erra da ordem de 0,5 %; o TC de proteção, 10 %. A tela
    fica uma ordem de grandeza abaixo do relé — deixa de aparecer na conta.
    """
    erro = 0.5 * 10.0 ** (-leitura.casas(valor)) / abs(valor)
    assert erro <= 0.0005                        # 0,05 %


def test_a_diferenca_entre_cursores_vem_do_servidor(tmp_path):
    """Afundamento e salto vão para o relatório — conta de relatório tem teste."""
    r = _registro(tmp_path, na=2, n=512, taxa=960.0)
    a, b = float(r.time[10]), float(r.time[42])

    saida = leitura.em(r, [(a, 0, 0.0), (b, 0, 0.0)])
    esperado = [vb["valor"] - va["valor"] for va, vb in
                zip(saida["cursores"][0]["valores"],
                    saida["cursores"][1]["valores"], strict=True)]

    assert [d["valor"] for d in saida["entre"]["valores"]] == pytest.approx(esperado)
    assert all("casas" in d for d in saida["entre"]["valores"])


def test_as_casas_do_tempo_vem_da_taxa_de_amostragem(tmp_path):
    """3 casas num registro a 1200 Hz prometem microssegundo onde não há: duas
    amostras vizinhas distam 0,833 ms."""
    assert leitura.casas_do_tempo(0.8333) == 1      # 1200 Hz
    assert leitura.casas_do_tempo(0.3125) == 1      # 3200 Hz
    assert leitura.casas_do_tempo(0.05) == 2        # 20 kHz
    assert leitura.casas_do_tempo(8.3333) == 0      # registro muito lento
    assert leitura.casas_do_tempo(0) == 3           # sem passo conhecido


def test_amostras_vizinhas_saem_diferentes_na_tela(tmp_path):
    """O critério da regra: a última casa mostrada tem que mudar de uma amostra
    para a seguinte, senão a tela junta duas medidas distintas."""
    r = _registro(tmp_path, na=1, n=256, taxa=1200.0)
    saida = leitura.em(r, [(float(r.time[100]), 0, 0.0), (float(r.time[101]), 0, 0.0)])
    casas = saida["casas_ms"]
    a = round(saida["cursores"][0]["ms"], casas)
    b = round(saida["cursores"][1]["ms"], casas)
    assert a != b


# ---------------------------------------------------------------------------
# Prefixo da unidade: A × kA, V × kV
# ---------------------------------------------------------------------------
#
# Em primário os números explodem: 230 kV dá pico fase-terra de 187 794 V, sete
# dígitos que não cabem na coluna nem no eixo. O prefixo resolve — desde que
# não fique mudando debaixo do usuário.

def test_secundario_nao_ganha_prefixo(tmp_path):
    """100 A de pico se lê melhor como 100 A do que como 0,1 kA."""
    r = _registro(tmp_path, na=1, n=128)
    pacote = janela.montar(r, lado="secundario")
    assert pacote["grupos"][0]["unidade"] == "A"
    assert pacote["grupos"][0]["divisor"] == 1.0


def test_primario_grande_ganha_o_k(tmp_path):
    """12 000 A primários passam do limiar."""
    r = _registro(tmp_path, na=1, n=128)
    grupo = janela.montar(r, lado="primario")["grupos"][0]
    assert grupo["unidade"] == "kA"
    assert grupo["divisor"] == 1000.0
    assert grupo["titulo"] == "Correntes (kA)"


def test_o_prefixo_nao_muda_com_o_zoom(tmp_path):
    """Ampliar a pré-falta não pode trocar o eixo de kA para A: unidade que
    pisca engana quem lê rápido."""
    r = _registro(tmp_path, na=1, n=1024, taxa=960.0)
    t0, t1 = navegacao.extensao(r)
    inteiro = janela.montar(r, lado="primario")["grupos"][0]
    pedaco = janela.montar(r, de=t0, ate=t0 + (t1 - t0) * 0.02,
                           lado="primario")["grupos"][0]
    assert pedaco["unidade"] == inteiro["unidade"]
    assert pedaco["divisor"] == inteiro["divisor"]


def test_o_cursor_usa_a_mesma_unidade_do_grafico(tmp_path):
    """Gráfico em kA e cursor em A no mesmo instante seria mentira das boas: o
    usuário acreditaria no que estivesse olhando."""
    r = _registro(tmp_path, na=1, n=128)
    grupo = janela.montar(r, lado="primario")["grupos"][0]
    (cursor,), _ = _ler(r, [(float(r.time[20]), 0)], lado="primario")
    assert cursor["valores"][0]["unidade"] == grupo["unidade"]


def test_unidade_ja_prefixada_no_arquivo_nao_vira_kk(tmp_path):
    """Alguns arquivos declaram o canal em kA; `kkA` não existe."""
    cfg = escrever_comtrade(tmp_path, na=1, n=64)
    texto = cfg.read_text(encoding="utf-8").replace(
        "1,CH1,A,,A,0.01,0,0,-32767,32767,600.0,5.0,S",
        "1,CH1,A,,kA,900.0,0,0,-32767,32767,1,1,P")
    cfg.write_text(texto, encoding="utf-8")
    grupo = janela.montar(registry.read(cfg))["grupos"][0]
    assert grupo["unidade"] == "kA"
    assert grupo["divisor"] == 1.0


def test_o_limiar_e_o_proprio_maximo_do_registro(tmp_path):
    r = _registro(tmp_path, na=1, n=64)
    canais = list(r.analog_channels)
    assert unidades.do_grupo(r, canais, "A", "arquivo") == (1.0, "A")
    assert unidades.do_grupo(r, canais, "A", "primario") == (1000.0, "kA")
    # Unidade de fora da lista nunca é tocada.
    assert unidades.do_grupo(r, canais, "Hz", "primario") == (1.0, "Hz")
