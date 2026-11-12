"""A relação de TC/TP DIGITADA: do canal, por grupo, gravada com o registro.

Decisão do Alexandre em 11/11/2026: a relação que a calculadora deixava digitar
só para uma conta passou a ser do CANAL. Digita-se por grupo (vale para as três
fases e para o resíduo do vão sem relação declarada) e por canal (vence o
grupo); a escolha do usuário vence o arquivo, como no vínculo de fase; e vale
em tudo que usa o registro — nunca em outro registro.

O registro é o alimentador de `casos_calculadora`: correntes 600/5, tensões
13800/115 e o neutro medido «Current IN» SEM relação declarada (0, 0).
"""

from __future__ import annotations

import numpy as np
import pytest

from osclab import paths
from osclab.formats import relacoes
from osclab.library import acervo
from osclab.plot import conversao
from tests import casos_calculadora as cc


@pytest.fixture(autouse=True)
def acervo_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")


def _guardar(pasta, outro=False):
    if outro:
        from tests.fabrica import escrever_comtrade
        cfg = escrever_comtrade(pasta, nome="OUTRO", n=64)
    else:
        pasta.mkdir(parents=True, exist_ok=True)
        cfg = cc.alimentador(pasta)
    dat = cfg.with_suffix(".dat")
    return acervo.guardar([(cfg.name, cfg.read_bytes()),
                           (dat.name, dat.read_bytes())]).aceitos[0].sha


@pytest.fixture
def sha(tmp_path):
    return _guardar(tmp_path / "a")


def _canal(registro, nome):
    return next(c for c in registro.analog_channels if c.name == nome)


def _grupo_das_correntes(registro):
    from osclab.formats import conjuntos
    return next(c.nome for c in conjuntos.de_registro(registro) if c.grandeza == "I")


# --- o texto -------------------------------------------------------------------

@pytest.mark.parametrize("texto, par", [
    ("600/5", (600.0, 5.0)), ("600:5", (600.0, 5.0)), (" 13800 / 115 ", (13800.0, 115.0)),
    ("120", (120.0, 1.0)), ("34,5/0,115", (34.5, 0.115)), (240, (240.0, 1.0)),
])
def test_le_a_relacao_como_se_escreve(texto, par):
    assert relacoes.ler_texto(texto) == par


@pytest.mark.parametrize("texto", ["", "  ", "0", "600/0", "-5", "abc", "600/5/1", None])
def test_o_que_nao_e_relacao_vira_apagar(texto):
    assert relacoes.ler_texto(texto) is None


# --- gravar, ler, apagar -----------------------------------------------------------

def test_a_relacao_digitada_fica_gravada_AO_LADO_do_registro(sha):
    reg = acervo.ler(sha)
    grupo = _grupo_das_correntes(reg)
    acervo.gravar_relacoes(sha, {"grupos": {grupo: "1200/5"}, "canais": {"6": "100"}})
    assert paths.relacoes_do_registro(sha).is_file()
    assert paths.relacoes_do_registro(sha).parent == acervo._raiz() / sha
    lidas = acervo.relacoes(sha)
    assert lidas["grupos"] == {grupo: (1200.0, 5.0)}
    assert lidas["canais"] == {6: (100.0, 1.0)}


def test_vazio_apaga_e_sem_nada_o_arquivo_some(sha):
    grupo = _grupo_das_correntes(acervo.ler(sha))
    acervo.gravar_relacoes(sha, {"grupos": {grupo: "1200/5"}})
    acervo.gravar_relacoes(sha, {"grupos": {grupo: ""}})
    assert acervo.relacoes(sha) == {"grupos": {}, "canais": {}}
    assert not paths.relacoes_do_registro(sha).exists()
    # e a do arquivo volta a valer
    assert _canal(acervo.ler(sha), "Current IA").primary == 600


# --- grupo, canal e arquivo ---------------------------------------------------------

def test_a_do_GRUPO_vale_para_as_tres_fases_e_VENCE_a_do_arquivo(sha):
    grupo = _grupo_das_correntes(acervo.ler(sha))
    acervo.gravar_relacoes(sha, {"grupos": {grupo: "1200/5"}})
    reg = acervo.ler(sha)
    for nome in ("Current IA", "Current IB", "Current IC"):
        c = _canal(reg, nome)
        assert (c.primary, c.secondary) == (1200.0, 5.0)
        assert c.relacao_digitada and c.relacao_do_arquivo == (600.0, 5.0)
    # as tensões são outro grupo: não mudam
    v = _canal(reg, "Voltage A-G")
    assert (v.primary, v.secondary, v.relacao_digitada) == (13800, 115, False)


def test_a_do_grupo_chega_ao_RESIDUO_do_vao_sem_relacao_declarada(sha):
    grupo = _grupo_das_correntes(acervo.ler(sha))
    acervo.gravar_relacoes(sha, {"grupos": {grupo: "1200/5"}})
    neutro = _canal(acervo.ler(sha), "Current IN")
    assert (neutro.primary, neutro.secondary) == (1200.0, 5.0) and neutro.relacao_digitada


def test_a_do_grupo_NAO_troca_a_relacao_DECLARADA_do_residuo(tmp_path):
    """O neutro costuma ser um toroide com outra relação: trocar uma relação
    que o arquivo declara por uma digitada para as FASES seria decidir por ele."""
    from dataclasses import replace
    reg = cc.ler(cc.alimentador(tmp_path))
    reg.analog_channels = tuple(replace(c, primary=100.0, secondary=1.0)
                                if c.name == "Current IN" else c
                                for c in reg.analog_channels)
    grupo = _grupo_das_correntes(reg)
    relacoes.aplicar(reg, {"grupos": {grupo: (1200.0, 5.0)}, "canais": {}})
    neutro = _canal(reg, "Current IN")
    assert (neutro.primary, neutro.secondary, neutro.relacao_digitada) == (100.0, 1.0, False)


def test_a_do_CANAL_vence_a_do_grupo(sha):
    reg = acervo.ler(sha)
    grupo = _grupo_das_correntes(reg)
    ib = _canal(reg, "Current IB").index
    acervo.gravar_relacoes(sha, {"grupos": {grupo: "1200/5"}, "canais": {str(ib): "800/5"}})
    reg = acervo.ler(sha)
    assert (_canal(reg, "Current IB").primary, _canal(reg, "Current IB").secondary) == (800, 5)
    assert _canal(reg, "Current IA").primary == 1200


def test_sem_nada_digitado_vale_o_ARQUIVO(sha):
    reg = acervo.ler(sha)
    ia = _canal(reg, "Current IA")
    assert (ia.primary, ia.secondary, ia.relacao_digitada) == (600, 5, False)
    assert conversao.relacao(_canal(reg, "Current IN")) == 0.0


def test_OUTRO_registro_nao_e_afetado(sha, tmp_path):
    outro = _guardar(tmp_path / "b", outro=True)
    assert outro != sha
    antes = [(c.primary, c.secondary) for c in acervo.ler(outro).analog_channels]
    grupo = _grupo_das_correntes(acervo.ler(sha))
    acervo.gravar_relacoes(sha, {"grupos": {grupo: "1200/5"}, "canais": {"0": "999"}})
    depois = acervo.ler(outro).analog_channels
    assert [(c.primary, c.secondary) for c in depois] == antes
    assert not any(c.relacao_digitada for c in depois)
    assert not paths.relacoes_do_registro(outro).exists()


# --- vale em tudo -----------------------------------------------------------------

def test_a_conversao_para_PRIMARIO_usa_a_digitada(sha):
    reg = acervo.ler(sha)
    neutro = _canal(reg, "Current IN")
    bruto = reg.analog[neutro.index]
    _, lado, convertido = conversao.converter(bruto, neutro, "primario")
    assert not convertido and lado == "secundario"      # sem relação: não converte

    acervo.gravar_relacoes(sha, {"canais": {str(neutro.index): "120"}})
    reg = acervo.ler(sha)
    neutro = _canal(reg, "Current IN")
    valores, lado, convertido = conversao.converter(
        reg.analog[neutro.index], neutro, "primario")
    assert convertido and lado == "primario"
    assert np.allclose(valores, 120 * bruto)


def test_a_janela_marca_DIGITADO_e_tira_o_aviso_de_sem_relacao(sha):
    from osclab.plot import janela, paineis

    reg = acervo.ler(sha)
    neutro = _canal(reg, "Current IN")
    layout = [{"id": "p1", "tipo": "analogico", "nome": "x",
               "sinais": [f"c{neutro.index}:instantaneo"], "medida": "instantaneo"}]

    def o_neutro(registro):
        pacote = janela.montar(registro, colunas=200, lado="primario",
                               layout=paineis.de_json(layout))
        return next(s for p in pacote["paineis"] for s in p.get("sinais", [])
                    if s["indice"] == neutro.index), pacote

    antes, _ = o_neutro(reg)
    assert antes["lado"] == "secundario" and not antes["relacao_digitada"]

    acervo.gravar_relacoes(sha, {"canais": {str(neutro.index): "120"}})
    depois, pacote = o_neutro(acervo.ler(sha))
    assert depois["lado"] == "primario" and depois["relacao_digitada"]
    resumo = pacote["relacoes"]["canais"][str(neutro.index)]
    assert resumo == {"em_uso": "120", "origem": relacoes.DIGITADO,
                      "do_arquivo": "", "no_canal": "120"}


def test_o_resumo_diz_LIDO_do_arquivo_quando_ninguem_digitou(sha):
    resumo = relacoes.resumo(acervo.ler(sha))
    ia = _canal(acervo.ler(sha), "Current IA").index
    assert resumo["canais"][str(ia)]["origem"] == relacoes.LIDO
    assert resumo["canais"][str(ia)]["em_uso"] == "600:5"


def test_a_calculadora_le_a_digitada_do_registro_e_NAO_converte_duas_vezes(sha):
    """Conta antiga trazia a relação dentro dela (`relacoes`). Com a relação
    agora no canal, aplicar a da conta por cima converteria duas vezes."""
    from osclab.plot import calculadora, contas

    reg = acervo.ler(sha)
    neutro = _canal(reg, "Current IN")
    i = int(np.argmin(np.abs(reg.time - cc.T_FALTA)))

    def valor(registro, **extra):
        conta = contas.de_json([{"id": "x1", "nome": "c", "expressao": "[Current IN]",
                                 "dominio": "onda", **extra}])[0]
        a = calculadora.analisar_conta(conta, registro, contas._do_catalogo(registro))
        return contas.serie(registro, a, "primario", 1.0)[i], a

    cru, a = valor(reg)
    assert neutro.index in a.sem_relacao
    acervo.gravar_relacoes(sha, {"canais": {str(neutro.index): "120"}})
    reg = acervo.ler(sha)
    com, a = valor(reg, relacoes={str(neutro.index): 120})
    assert neutro.index not in a.sem_relacao
    assert abs(com - 120 * cru) < 1e-6 * abs(com)


def test_a_rota_grava_e_devolve_o_resumo(cliente, sha):
    reg = acervo.ler(sha)
    grupo = _grupo_das_correntes(reg)
    r = cliente.post(f"/api/onda/{sha}/relacoes", json={"grupos": {grupo: "1200/5"}})
    assert r.status_code == 200
    ia = str(_canal(reg, "Current IA").index)
    assert r.get_json()["relacoes"]["canais"][ia]["origem"] == relacoes.DIGITADO
    assert r.get_json()["relacoes"]["grupos"] == {grupo: "1200:5"}
    pacote = cliente.get(f"/api/onda/{sha}").get_json()
    assert pacote["relacoes"]["canais"][ia]["em_uso"] == "1200:5"
    assert cliente.post("/api/onda/naoexiste/relacoes", json={}).status_code == 404
