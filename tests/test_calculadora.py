"""A calculadora além da onda: fasor, funções, nomes padronizados e modelos.

A gramática da onda já tem os testes dela (`test_contas.py`). Aqui fica o que
entrou com a gaveta (variante 10, 11/11/2026), contra registros sintéticos de
resposta CONHECIDA (`tests/casos_calculadora.py`): o Zap AG do alimentador foi
construído para dar 1,2 + j3,6 Ω.
"""

from __future__ import annotations

import cmath
import math

import numpy as np
import pytest

from osclab.plot import calculadora, catalogo, contas
from tests import casos_calculadora as cc


@pytest.fixture(scope="module")
def alimentador(tmp_path_factory):
    return cc.ler(cc.alimentador(tmp_path_factory.mktemp("alimentador")))


@pytest.fixture(scope="module")
def trafo(tmp_path_factory):
    return cc.ler(cc.trafo(tmp_path_factory.mktemp("trafo")))


def _conta(expressao, dominio="onda", **extra):
    cru = {"id": "x1", "nome": "c", "expressao": expressao, "dominio": dominio, **extra}
    return contas.de_json([cru])[0]


def _analise(registro, expressao, dominio="onda", **extra):
    return calculadora.analisar_conta(
        _conta(expressao, dominio, **extra), registro, contas._do_catalogo(registro)
    )


def _amostra(registro, t):
    return int(np.argmin(np.abs(registro.time - t)))


K0 = {"k0": {"mod": 0.68, "ang": -4, "origem": "digitado"}}


# --- o domínio fasor --------------------------------------------------------


def test_o_ZAP_AG_com_k0_da_a_impedancia_que_o_registro_foi_construido_para_dar(alimentador):
    a = _analise(alimentador, "[VA] / ([IA] + {k0} * [3I0])", "fasor", parametros=K0)
    assert a.vale and a.unidade_escrita == "Ω" and a.giro == 0
    z = calculadora.serie_fasor(alimentador, a, "secundario")[_amostra(alimentador, cc.T_FALTA)]
    assert abs(z - cc.ZAP) / abs(cc.ZAP) < 0.005


def test_impedancia_NAO_MUDA_entre_primario_e_secundario_quando_RTP_e_RTC_sao_iguais(
    alimentador,
):
    """13800/115 = 120 = 600/5: a conversão vem ANTES da conta, nas duas folhas."""
    a = _analise(alimentador, "[VA] / [IA]", "fasor")
    i = _amostra(alimentador, cc.T_FALTA)
    z_sec = calculadora.serie_fasor(alimentador, a, "secundario")[i]
    z_pri = calculadora.serie_fasor(alimentador, a, "primario")[i]
    assert abs(z_sec - z_pri) < 1e-9 * abs(z_sec)


def test_com_o_DISJUNTOR_ABERTO_a_impedancia_vira_buraco_e_nao_numero_enorme(alimentador):
    """Tensão sobre corrente ZERO dá um número enorme e plausível. Abaixo de 2 %
    do maior módulo que o denominador teve, o resultado é NaN — e a nota diz."""
    a = _analise(alimentador, "[VA] / [IA]", "fasor")
    z = calculadora.serie_fasor(alimentador, a, "secundario")
    assert np.isnan(z[_amostra(alimentador, 0.30)])
    assert np.isfinite(z[_amostra(alimentador, cc.T_FALTA)])
    assert any(x.startswith("onde o de baixo") for x in a.avisos)


def test_o_GIRO_diz_se_o_angulo_e_absoluto_ou_contra_a_referencia(alimentador):
    assert _analise(alimentador, "[VA] / [IA]", "fasor").giro == 0
    assert _analise(alimentador, "[VA] * conj([IA])", "fasor").giro == 0
    v1 = _analise(alimentador, "([VA] + a * [VB] + a^2 * [VC]) / 3", "fasor")
    assert v1.giro == 1
    # V1 na pré-falta, contra a tensão A: módulo da fase, ângulo ~0.
    lido = calculadora.valores(
        alimentador,
        [_conta("([VA] + a * [VB] + a^2 * [VC]) / 3", "fasor")],
        "secundario",
        [cc.T_PRE, None],
    )[0]["celulas"][0]
    assert lido["valor"].startswith("66,4") and lido["angulo"] in ("0,0°", "−0,0°")
    assert "ref." in lido["qual"]


def test_somar_giros_diferentes_e_AVISO_nao_erro(alimentador):
    a = _analise(alimentador, "[VA] + [VA] * conj([IA])", "fasor")
    assert a.vale and a.giro is None
    assert any("gira" in x for x in a.avisos)


def test_potencia_complexa_sai_em_VA_com_prefixo_do_REGISTRO(alimentador):
    lido = calculadora.valores(
        alimentador,
        [_conta("[VA] * conj([IA]) + [VB] * conj([IB]) + [VC] * conj([IC])", "fasor")],
        "primario",
        [cc.T_FALTA, None],
    )[0]
    assert lido["unidade"] == "MV·A"


def test_FP_e_real_e_fica_entre_menos_um_e_um(alimentador):
    a = _analise(alimentador, "re([VA] * conj([IA])) / mod([VA] * conj([IA]))", "fasor")
    assert a.real
    fp = np.real(calculadora.serie_fasor(alimentador, a, "secundario"))
    finitos = fp[np.isfinite(fp)]
    assert finitos.size and np.all(np.abs(finitos) <= 1 + 1e-9)


def test_no_fasor_o_eficaz_nao_tem_fasor_e_a_conta_diz_para_usar_o_canal(alimentador):
    a = _analise(alimentador, "[Current IA · RMS] / [IA]", "fasor")
    assert not a.vale and "use o canal" in a.erro


# --- funções de onda e o separador `;` --------------------------------------


def test_delta_e_zero_em_regime_e_salta_na_falta(alimentador):
    a = _analise(alimentador, "delta([IA])")
    y = contas.serie(alimentador, a, "secundario", 1.0)
    pre = np.abs(y[_amostra(alimentador, 0.04) : _amostra(alimentador, 0.095)])
    assert np.nanmax(pre) < 0.05 * 2.1 * math.sqrt(2)
    assert np.nanmax(np.abs(y[_amostra(alimentador, 0.10) : _amostra(alimentador, 0.12)])) > 20


def test_atrasar_leva_milissegundos_depois_de_ponto_e_virgula(alimentador):
    a = _analise(alimentador, "atrasar([IA]; 16,67)")
    assert a.vale, a.erro
    sem = _analise(alimentador, "atrasar([IA], 16)")
    assert not sem.vale  # a vírgula é a casa decimal, não separador


def test_derivada_e_integral_carregam_o_segundo_na_unidade(alimentador):
    assert _analise(alimentador, "deriv([IA])").unidade_escrita == "A/s"
    assert _analise(alimentador, "integ([IA])").unidade_escrita == "A·s"


def test_parametro_sem_valor_e_erro_que_diz_o_que_digitar(alimentador):
    a = _analise(alimentador, "[VA] / ([IA] + {k0} * [3I0])", "fasor")
    assert not a.vale and "{k0}" in a.erro


def test_o_k0_do_RELE_vem_com_a_origem():
    """Atalho: o campo continua sendo digitável, e a tela diz de onde veio."""
    z1, z0 = cmath.rect(5.0, math.radians(75)), cmath.rect(15.0, math.radians(72))
    ajustes = {"ajustes": [("Z1MAG", "5"), ("Z1ANG", "75"), ("Z0MAG", "15"), ("Z0ANG", "72")]}
    sug = calculadora.ajustes_sugeridos(ajustes)["k0"]
    esperado = (z0 - z1) / (3 * z1)
    assert abs(sug["mod"] - abs(esperado)) < 1e-3
    assert sug["origem"] == "calculado do relé"
    assert calculadora.ajustes_sugeridos({}) == {}


# --- nomes padronizados --------------------------------------------------------


def test_com_DUAS_trincas_IA_sozinho_e_ambiguo_e_a_conta_nao_escolhe(trafo):
    a = _analise(trafo, "[IA] + 1")
    assert not a.vale and "G1" in a.erro and "G2" in a.erro
    assert _analise(trafo, "[IA G1] - [IA G2]").vale


def test_IN_padronizado_e_o_RESIDUO_e_nao_o_neutro_medido(alimentador):
    """`[IN]` é a soma das fases em qualquer relé; o neutro medido entra pelo
    nome do canal dele."""
    assert calculadora.expandir("[IN]", alimentador) == "[IN G2]"
    assert calculadora.expandir("[IA]", alimentador) == "[Current IA]"


def test_a_tecla_insere_o_NOME_COMPLETO_do_canal_do_grupo_escolhido(trafo):
    n = calculadora.nomes(trafo)
    ia = next(t for t in n["fileira"] if t["base"] == "IA")
    assert ia["opcoes"] == {"G1": "TC BUC 69kV:I A", "G2": "TC EXT 13-8kV:I A"}
    in_ = next(t for t in n["fileira"] if t["base"] == "IN")
    assert in_["opcoes"] == {"G1": "IN G1", "G2": "IN G2"}
    assert [t["base"] for t in n["fileira"]] == list(calculadora.FILEIRA)
    # o seletor mostra o RADICAL do nome, como o relé escreve — nunca lado
    assert n["rotulos"]["G1"] == "TC BUC 69kV:I *"
    assert n["grupos"]["I"] == ["G1", "G2"] and n["grupos"]["V"] == ["G3"]


def test_a_lista_traz_o_nome_do_relé_e_o_padronizado_ao_lado(trafo):
    sinais = {s["escrever"]: s["padrao"] for s in calculadora.nomes(trafo)["sinais"]}
    assert sinais["TC EXT 13-8kV:I B"] == "IB G2"
    assert sinais["87T:I diff.:phs A"] == ""


def test_expandir_e_generalizar_fazem_o_caminho_de_ida_e_volta(trafo):
    ida = calculadora.expandir("[IA G1] - [IA G2]", trafo)
    assert ida == "[TC BUC 69kV:I A] - [TC EXT 13-8kV:I A]"
    volta = calculadora.generalizar(ida, trafo)
    assert volta["expressao"] == "[IA] - [IA#2]" and not volta["presos"]


# --- TC sem relação declarada ---------------------------------------------------


def test_canal_SEM_relacao_avisa_e_a_relacao_digitada_vale_para_a_conta(alimentador):
    a = _analise(alimentador, "[Current IN] - ([IA] + [IB] + [IC])")
    assert any("Current IN" in x for x in a.avisos)
    indice = next(c.index for c in alimentador.analog_channels if c.name == "Current IN")
    so_neutro = _analise(alimentador, "[Current IN]", relacoes={str(indice): 120})
    i = _amostra(alimentador, cc.T_FALTA)
    sem = contas.serie(alimentador, _analise(alimentador, "[Current IN]"), "primario", 1.0)[i]
    com = contas.serie(alimentador, so_neutro, "primario", 1.0)[i]
    assert abs(com - 120 * sem) < 1e-6 * abs(com)


# --- modelos ----------------------------------------------------------------------


def test_cada_modelo_diz_se_CABE_no_registro(alimentador, trafo):
    def por_id(r):
        return {m["id"]: m for m in calculadora.modelos(r, "arquivo")["modelos"]}

    no_alimentador, no_trafo = por_id(alimentador), por_id(trafo)
    assert no_alimentador["zag"]["cabe"]
    assert (
        not no_alimentador["dif"]["cabe"]
        and "segunda trinca" in no_alimentador["dif"]["motivo"]
    )
    assert no_trafo["dif"]["cabe"]
    # já com os nomes COMPLETOS, que é o que o visor mostra
    assert "[Current IA]" in no_alimentador["zag"]["instanciada"]


def test_o_modelo_do_usuario_mora_FORA_do_registro(monkeypatch, tmp_path):
    from osclab import paths

    monkeypatch.setattr(paths, "MODELOS_DA_CALCULADORA", tmp_path / "modelos.json")
    calculadora.guardar_modelo(
        {"id": "u1", "nome": "Vab", "expressao": "[VA] - [VB]", "dominio": "onda"}
    )
    assert (tmp_path / "modelos.json").exists()
    assert [m["id"] for m in calculadora.modelos_do_usuario()] == ["u1"]
    calculadora.apagar_modelo("u1")
    assert calculadora.modelos_do_usuario() == []


# --- o defeito do main: conta do usuário + filtro de 60 Hz --------------------------


def test_conta_do_usuario_com_FILTRO_aceso_nao_quebra_a_janela(alimentador):
    """O id da conta tem DUAS partes (`x1:instantaneo`) e caía num `split` de
    três em `catalogo.efetivo`: a janela inteira dava erro 500 com o filtro
    aceso. O par dela é `x1:filtrado`."""
    lista = (_conta("[IA] * 2"),)
    por_id = {s.id: s for s in catalogo.de_registro(alimentador, "arquivo", lista)}
    assert catalogo.efetivo("x1:instantaneo", "instantaneo", True, por_id).id == "x1:filtrado"
    assert (
        catalogo.efetivo("x1:instantaneo", "instantaneo", False, por_id).id == "x1:instantaneo"
    )


def test_a_conta_de_FASOR_entra_no_catalogo_como_UMA_linha_de_modulo(alimentador):
    lista = (_conta("[VA] / ([IA] + {k0} * [3I0])", "fasor", parametros=K0),)
    dela = [
        s
        for s in catalogo.de_registro(alimentador, "secundario", lista)
        if s.familia == "conta"
    ]
    assert [s.id for s in dela] == ["x1:instantaneo"]
    assert dela[0].unidade == "Ω" and dela[0].dominio == "modulo"


# --- as rotas -------------------------------------------------------------------


@pytest.fixture
def no_acervo(tmp_path, monkeypatch):
    """O alimentador guardado num acervo TEMPORÁRIO; devolve (cliente, sha)."""
    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    monkeypatch.setattr(paths, "MODELOS_DA_CALCULADORA", tmp_path / "modelos.json")
    cfg = cc.alimentador(tmp_path)
    r = acervo.guardar(
        [
            (cfg.name, cfg.read_bytes()),
            (cfg.with_suffix(".dat").name, cfg.with_suffix(".dat").read_bytes()),
        ]
    )
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client(), r.aceitos[0].sha


def test_a_JANELA_com_conta_e_filtro_aceso_responde_200(no_acervo):
    """O defeito do main pela rota: era erro 500 e a tela não desenhava."""
    cliente, sha = no_acervo
    corpo = {
        "paineis": [
            {
                "id": "p1",
                "tipo": "analogico",
                "nome": "Correntes",
                "medida": "instantaneo",
                "sinais": ["c3:instantaneo", "x1:instantaneo"],
            }
        ],
        "contas": [{"id": "x1", "nome": "dobro", "expressao": "[IA] * 2"}],
    }
    r = cliente.post(f"/api/onda/{sha}?colunas=300&filtro=1", json=corpo)
    assert r.status_code == 200
    ids = [s.get("id_efetivo") for p in r.get_json()["paineis"] for s in p.get("sinais", [])]
    assert "x1:filtrado" in ids


def test_conferir_devolve_a_expressao_com_os_NOMES_COMPLETOS_e_o_valor(no_acervo):
    cliente, sha = no_acervo
    r = cliente.post(
        f"/api/onda/{sha}/calculadora/conferir",
        json={
            "conta": {
                "nome": "Zap",
                "expressao": "[VA] / ([IA] + {k0} * [3I0])",
                "dominio": "fasor",
                "parametros": K0,
            },
            "lado": "secundario",
            "t1": cc.T_FALTA,
            "contas": [],
        },
    ).get_json()
    assert r["vale"] and r["unidade"] == "Ω"
    assert r["expandida"] == "[Voltage A-G] / ([Current IA] + {k0} * [3I0 G2])"
    assert r["valores"]["celulas"][0]["valor"].startswith("3,79")
    assert r["t"] and len(r["t"]) == len(r["y"])  # a prévia


def test_modelos_e_nomes_numa_ida_so(no_acervo):
    cliente, sha = no_acervo
    r = cliente.get(f"/api/onda/{sha}/calculadora/modelos").get_json()
    assert {"modelos", "nomes", "sugeridos"} <= set(r)
    assert [t["base"] for t in r["nomes"]["fileira"]] == list(calculadora.FILEIRA)
    g = cliente.post(
        f"/api/onda/{sha}/calculadora/modelos",
        json={"nome": "Vab", "expressao": "[VA] - [VB]", "dominio": "onda"},
    ).get_json()
    assert [m["nome"] for m in g["modelos"]] == ["Vab"]


def test_as_cores_da_calculadora_sao_as_do_CSS_e_passam_no_validador():
    """`tools/paleta.py` carrega a marca do domínio e o visor; se o CSS mudar
    e ele não, ele passa a aprovar cores que ninguém está usando."""
    import re

    from osclab import paths
    from tests.test_web import _paleta_do_repositorio

    paleta = _paleta_do_repositorio()
    texto = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")
    corte = texto.index('\n:root[data-tema="escuro"] {')
    cor = re.compile(r"(--calc-[a-z-]+)\s*:\s*(#[0-9a-f]{6})")
    claro, escuro = dict(cor.findall(texto[:corte])), dict(cor.findall(texto[corte:]))
    escuro = {**claro, **escuro}  # o escuro herda o que não redefine
    for tema, do_css in (("claro", claro), ("escuro", escuro)):
        for grupo in (paleta.CALCULADORA, paleta.VISOR):
            cores = grupo[tema]["cores"]
            assert {k: do_css[k] for k in cores} == cores, tema
            reprovacoes, _ = paleta.conferir(cores, grupo[tema]["fundo"])
            assert not reprovacoes, (tema, reprovacoes)
    assert paleta.VISOR["claro"]["fundo"] == claro["--calc-visor-fundo"]
    assert paleta.VISOR["escuro"]["fundo"] == escuro["--calc-visor-fundo"]
