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

from osclab.analysis import presenca
from osclab.formats import conjuntos, registry
from osclab.plot import catalogo, digitais, imas, janela, unidades
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
        (unidades, "_por_unidade"), (catalogo, "energia_das_linhas"))}
    primeiro = janela.montar(r, colunas=600)
    for zoom in (0.5, 0.25):
        meio = (primeiro["de"] + primeiro["ate"]) / 2
        janela.montar(r, de=meio - zoom / 2, ate=meio + zoom / 2, colunas=600)
    janela.montar(r, colunas=600, filtro=True)
    for nome, c in contas.items():
        assert c["n"] == 1, f"{nome} foi feita {c['n']} vezes em quatro pedidos"


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
