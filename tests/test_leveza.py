"""O custo de um gesto é da JANELA, não do registro inteiro (12/11/2026).

Pedido de janela (roda, arrasto, filtro) e leitura do cursor refaziam a cada
vez contas que são do REGISTRO INTEIRO: a presença de sinal de cada canal, a
energia de cada linha do catálogo, o início da perturbação, as transições
dos digitais, o prefixo k. Num registro de um milhão de amostras por canal
eram 7 s por entalhe da roda. Agora elas são lembradas no registro
(`base.lembrado`), e estes testes prendem isso — e prendem que a resposta é
a MESMA de antes, que a impressão das amostras pega quem as altera no lugar,
e que o pacote seguinte não repete o que a tela já tem (`janela.sem_repetir`).
"""

from __future__ import annotations

import json

import numpy as np

from osclab.analysis import presenca
from osclab.formats import conjuntos, registry
from osclab.plot import catalogo, digitais, imas, janela, leitura, serie, unidades
from tests.fabrica import escrever_comtrade


def _registro(tmp_path, **kw):
    kw.setdefault("na", 6)
    kw.setdefault("nd", 12)
    kw.setdefault("n", 2400)
    kw.setdefault("taxa", 1200.0)
    return registry.read(escrever_comtrade(tmp_path, degraus=True, **kw))


def _contar(monkeypatch, modulo, nome):
    contagem = {"n": 0}
    original = getattr(modulo, nome)

    def contado(*a, **k):
        contagem["n"] += 1
        return original(*a, **k)
    monkeypatch.setattr(modulo, nome, contado)
    return contagem


def test_as_contas_do_registro_inteiro_sao_feitas_uma_vez(tmp_path, monkeypatch):
    r = _registro(tmp_path)
    contas = {nome: _contar(monkeypatch, modulo, nome) for modulo, nome in (
        (presenca, "_alternados"), (presenca, "_sem_sinal"), (conjuntos, "_medir_ondas"),
        (imas, "_inicio_da_perturbacao"), (digitais, "_trocas"), (digitais, "_resumos"),
        (unidades, "_por_unidade"))}
    primeiro = janela.montar(r, colunas=600)
    for zoom in (0.5, 0.25):
        meio = (primeiro["de"] + primeiro["ate"]) / 2
        janela.montar(r, de=meio - zoom / 2, ate=meio + zoom / 2, colunas=600)
    janela.montar(r, colunas=600, filtro=True)
    for nome, c in contas.items():
        assert c["n"] == 1, f"{nome} foi feita {c['n']} vezes em quatro pedidos"


def test_abrir_nao_calcula_a_energia_do_catalogo(tmp_path, monkeypatch):
    """A energia (a barrinha do «+ sinal») era ~30 % da abertura de um registro
    gigante. Desde 14/11/2026 nem a janela nem a leitura do cursor a fazem: só
    `janela.energia`, que a tela pede ao abrir o «+ sinal» — e uma vez só."""
    r = _registro(tmp_path)
    c = _contar(monkeypatch, catalogo, "energia_das_linhas")
    primeiro = janela.montar(r, colunas=600)
    assert "energia" not in primeiro
    janela.montar(r, colunas=600, filtro=True, de=0.2, ate=0.9)
    leitura.em(r, [(0.5, 0, 0.0), (None, 0, 0.0)])
    assert c["n"] == 0
    for _ in range(3):
        janela.energia(r)
    assert c["n"] == 1


def test_a_energia_pedida_e_a_mesma_de_quando_ia_no_pacote(tmp_path):
    """`janela.energia` dá EXATAMENTE o campo `energia` que o pacote da janela
    levava até 13/11/2026 — a mesma conta, com o lado resolvido igual e as
    contas do usuário dentro."""
    from osclab.plot import contas as contas_mod
    from osclab.plot import conversao
    r = _registro(tmp_path)
    contas = contas_mod.de_json([{"id": "x1", "nome": "SOMA",
                                  "expressao": "[IAW] + [IBW]"}])
    for lado, natural in (("arquivo", conversao.lado_natural(r)),
                          ("primario", "primario"), ("secundario", "secundario")):
        for cs in (None, contas):
            antes = {k: [round(f, 4) for f in v] for k, v in
                     catalogo.energia(r, natural, cs).items()}
            r.__dict__.pop("_lembrados", None)
            assert janela.energia(r, lado=lado, contas=cs) == antes
            assert antes
    assert "SOMA" in janela.energia(r, contas=contas)


def test_lembrar_nao_muda_a_resposta(tmp_path):
    """O pacote com as contas lembradas é idêntico ao feito do zero."""
    r = _registro(tmp_path)
    janela.montar(r, colunas=600)                      # lembra tudo
    lembrado = json.dumps(janela.montar(r, colunas=600, de=0.5, ate=1.2), sort_keys=True)
    r.__dict__.pop("_lembrados", None)                 # esquece tudo
    do_zero = json.dumps(janela.montar(r, colunas=600, de=0.5, ate=1.2), sort_keys=True)
    assert lembrado == do_zero


def test_alterar_as_amostras_no_lugar_refaz_a_conta(tmp_path):
    """Quem altera a matriz NO LUGAR (só os testes fazem isso) não pode
    receber a conta velha: a impressão das amostras entra na chave."""
    r = _registro(tmp_path)
    antes = unidades.por_unidade(r, "secundario")
    r.analog[:, :] *= 1000.0
    depois = unidades.por_unidade(r, "secundario")
    assert antes != depois


def test_o_pacote_seguinte_nao_repete_o_que_a_tela_ja_tem(tmp_path):
    r = _registro(tmp_path)
    inteiro = janela.sem_repetir(janela.montar(r, colunas=600), None)
    selo = inteiro["estaticos"]
    assert "digitais_disponiveis" in inteiro and "estaticos_omitidos" not in inteiro

    seguinte = janela.sem_repetir(janela.montar(r, colunas=600, de=0.5, ate=1.0), selo)
    assert seguinte["estaticos"] == selo
    assert sorted(seguinte["estaticos_omitidos"]) == sorted(janela.ESTATICOS)
    for campo in janela.ESTATICOS:
        assert campo not in seguinte

    # O que muda o conteúdo muda o selo, e aí vai tudo de novo.
    outro_lado = janela.sem_repetir(janela.montar(r, colunas=600, lado="primario"), selo)
    assert outro_lado["estaticos"] != selo
    assert "digitais_disponiveis" in outro_lado and "estaticos_omitidos" not in outro_lado


def test_o_selo_sem_a_tela_nao_tira_nada(tmp_path):
    r = _registro(tmp_path)
    pacote = janela.sem_repetir(janela.montar(r, colunas=600), "um-selo-qualquer")
    assert "estaticos_omitidos" not in pacote
    for campo in janela.ESTATICOS:
        assert campo in pacote


def test_a_piramide_reduz_igual_as_amostras(tmp_path):
    """`serie.reduzir_canal` (miolo pelos blocos, pontas amostra a amostra) dá
    coluna por coluna o mesmo mínimo e máximo de `serie.reduzir` sobre as
    amostras — com NaN no meio, coluna que começa e acaba no meio de um
    bloco, e janela que não começa no zero."""
    r = _registro(tmp_path, na=3, n=200_000, taxa=20_000.0)
    gerador = np.random.default_rng(11)
    r.analog = r.analog + gerador.normal(0.0, 3.0, r.analog.shape)
    r.analog[1, 50_000:50_003] = np.nan
    for i0, i1, colunas in ((0, 200_000, 700), (12_345, 187_001, 601), (99, 100_099, 300),
                            (0, 200_000, 1), (5, 70_005, 271)):
        cheia = serie.reduzir(r.time[i0:i1], r.analog[:, i0:i1], colunas).valores
        for canal in range(3):
            pela = serie.reduzir_canal(r, canal, i0, i1, colunas)
            assert pela is not None
            np.testing.assert_array_equal(pela, cheia[canal])


def test_a_piramide_nao_entra_em_coluna_estreita(tmp_path):
    r = _registro(tmp_path, na=3, n=20_000, taxa=20_000.0)
    assert serie.reduzir_canal(r, 0, 0, 20_000, 1300) is None     # 15 amostras por coluna


def test_sem_pico_nem_zero_pedidos_a_janela_nao_os_acha(tmp_path):
    """O ímã vem só com as transições: os picos e os zeros, que custam uma
    passada pela série cheia, só são achados quando pedidos. E as curvas
    saem iguais com e sem eles (com a pirâmide no caminho)."""
    r = _registro(tmp_path, na=3, n=200_000, taxa=20_000.0)
    todos = janela.montar(r, colunas=600)
    nenhum = janela.montar(r, colunas=600, atracoes="-")
    so_pico = janela.montar(r, colunas=600, atracoes="pico")
    for a, b, c in zip(todos["paineis"], nenhum["paineis"], so_pico["paineis"], strict=True):
        for sa, sb, sc in zip(a.get("sinais") or [], b.get("sinais") or [],
                              c.get("sinais") or [], strict=True):
            assert sa["picos"] and sa["zeros"]
            assert sb["picos"] == [] and sb["zeros"] == []
            assert sc["picos"] == sa["picos"] and sc["zeros"] == []
            assert sa["serie"] == sb["serie"] == sc["serie"]


def test_desempacotar_um_byte_por_bit_da_os_mesmos_bits():
    """`comtrade._desempacotar_digitais` com `unpackbits` dá os mesmos 0/1 do
    deslocamento antigo (que gastava 8 bytes por bit, duas vezes)."""
    from osclab.formats import comtrade

    gerador = np.random.default_rng(5)
    for n_status in (1, 15, 16, 17, 250):
        palavras = gerador.integers(0, 2**16, size=(321, (n_status + 15) // 16)).astype("<u2")
        antigo = ((palavras[:, :, None] >> np.arange(16)) & 1).reshape(321, -1)[:, :n_status].T
        novo = comtrade._desempacotar_digitais(palavras, n_status)
        assert novo.dtype == np.int8 and novo.shape == (n_status, 321)
        np.testing.assert_array_equal(novo, antigo.astype(np.int8))


# ---------------------------------------------------------------------------
# Abrir: a fundamental de cada canal medida UMA vez (15/11/2026)
# ---------------------------------------------------------------------------

def _sujo(tmp_path):
    """Um sintético com rede suja (bruto), falta no meio, trinca morta,
    magnitude e um buraco de NaN — o que a abertura mede de verdade."""
    import dataclasses

    from osclab.analysis import filtragem
    base = _registro(tmp_path, na=9)
    a = base.analog.copy()
    n = a.shape[1]
    t = np.arange(n) / base.base_rate_hz
    gerador = np.random.default_rng(3)
    a += 2.0 * np.sin(2 * np.pi * 180 * t) + gerador.normal(0, 0.05, a.shape)
    a[:3, n // 2:] *= 5
    a[6:9] = 0.4 + gerador.normal(0, 0.003, (3, n))
    a[3] = np.abs(a[3]) + 50
    a[4, 100:130] = np.nan
    return filtragem.aplicar(dataclasses.replace(base, analog=a))


def _medidas(r):
    return (str(r.filtering), presenca.alternados(r), presenca.sem_sinal(r),
            conjuntos._ondas(r), imas.inicio_da_perturbacao(r),
            repr(unidades.por_unidade(r, "arquivo")))


def test_abrir_mede_a_fundamental_de_cada_canal_uma_vez(tmp_path, monkeypatch):
    """O diagnóstico bruto × filtrado, a presença de sinal e as trincas mediam
    a MESMA fundamental de cada canal: três por canal. O diagnóstico deixa o
    resumo guardado pela matriz, e o registro corrigido pelo acervo (outro
    `Record`, a mesma matriz) o lê."""
    import dataclasses

    from osclab.dsp import envoltoria
    c = _contar(monkeypatch, envoltoria, "fundamental")
    r = _registro(tmp_path, na=9)
    assert c["n"] == 9
    corrigido = dataclasses.replace(r, analog_channels=tuple(r.analog_channels))
    presenca.alternados(corrigido)
    presenca.sem_sinal(corrigido)
    conjuntos._ondas(corrigido)
    assert c["n"] == 9


def test_o_resumo_guardado_e_o_mesmo_do_feito_do_zero(tmp_path):
    """O que sai com os resumos e os extremos lembrados pela matriz é
    idêntico ao feito do zero, sobre uma CÓPIA da matriz (sem lembrado)."""
    import dataclasses
    r = _sujo(tmp_path)
    assert str(r.filtering) == "bruto"
    lembrado = _medidas(r)
    zero = dataclasses.replace(r, analog=r.analog.copy())
    assert _medidas(zero) == lembrado
    assert lembrado[4] is not None and lembrado[2]


def test_alterar_a_matriz_no_lugar_refaz_o_resumo(tmp_path):
    r = _sujo(tmp_path)
    por_ciclo = r.base_rate_hz / r.line_frequency
    antes = presenca.resumo_do_canal(r, 0, por_ciclo)
    r.analog[0, :] *= 3.0
    depois = presenca.resumo_do_canal(r, 0, por_ciclo)
    assert depois.maior_fundamental != antes.maior_fundamental


def test_o_mesmo_giro_nao_muda_a_fundamental():
    from osclab.dsp import envoltoria
    gerador = np.random.default_rng(5)
    x = gerador.normal(0, 1, (3, 5000))
    for n in (20.0, 2000.0 / 60.0):
        soltos = [envoltoria.fundamental(x[k], n) for k in range(3)]
        with envoltoria.mesmo_giro():
            juntos = [envoltoria.fundamental(x[k], n) for k in range(3)]
        for a, b in zip(soltos, juntos, strict=True):
            assert a.tobytes() == b.tobytes()
