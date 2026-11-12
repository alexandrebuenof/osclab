"""Defeitos achados na caça de bugs de 11/11/2026, presos por teste.

Nasceram como `xfail(strict=True)` — o retrato do defeito — e perderam a
marca quando o conserto entrou (ramo `revisao-noite`): agora guardam a porta.
A lista completa fica em `docs-privados/caca-de-bugs-2026-11-11.md`.
"""

from __future__ import annotations

import pytest

from osclab.plot import catalogo, leitura, paineis, unidades
from tests import fabrica
from tests.test_potencia import _registro


def _potencia_ativa(registro):
    return next(x for x in catalogo.de_registro(registro, "arquivo", ())
                if x.id.startswith("w") and x.nome.startswith("P "))


def test_cursor_sobre_potencia_num_grafico_analogico_nao_derruba_a_leitura():
    """`P G1↔G2` num gráfico analógico + cursor = HTTP 500 na leitura.

    `catalogo._conjunto_do` faz `int(sinal.id[1:].split(":")[0])`, e o id de
    potência é `wG1:P:rms` — `int("G1")` levanta. A tabelinha do cursor fica
    vazia para o gráfico inteiro, não só para a linha da potência.
    """
    r = _registro("kV", 11.27, "A", 300 * 2 ** 0.5)
    p = _potencia_ativa(r)
    arranjo = paineis.de_json([{"id": "p1", "tipo": "analogico", "sinais": [p.id]}])
    i = len(r.time) // 2
    meio = float(r.time[i])
    lido = leitura.em(r, [(meio, 0, 0.0), (None, 0, 0.0)], layout=arranjo)
    linha = lido["cursores"][0]["sinais"][p.id]
    # O número da tabelinha é o da MESMA curva do gráfico, naquela amostra.
    escalas = unidades.por_unidade(r, "primario")
    curva = catalogo.serie(r, p, 0, r.n_samples, r.trechos, "primario", escalas)
    assert linha["valor"] == pytest.approx(float(curva[i]), rel=1e-3)
    assert linha["angulo"] is None


@pytest.fixture
def cliente_com_um_registro(tmp_path, monkeypatch):
    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    cfg = fabrica.escrever_comtrade(tmp_path / "rec", na=6, nd=4, n=400)
    dat = cfg.with_suffix(".dat")
    sha = acervo.guardar([(cfg.name, cfg.read_bytes()),
                          (dat.name, dat.read_bytes())]).aceitos[0].sha
    return create_app().test_client(), sha


@pytest.mark.parametrize("rota", [
    "/api/onda/{sha}?colunas=inf",
    "/api/onda/{sha}/leitura?t1=0.01&refere=inf",
    "/api/onda/{sha}?colunas=1e12",
    "/api/onda/{sha}/leitura?t1=0.01&passo1=1e300",
])
def test_infinito_na_url_nao_vira_500(cliente_com_um_registro, rota):
    cliente, sha = cliente_com_um_registro
    assert cliente.get(rota.format(sha=sha)).status_code < 500


def test_trilha_dos_eventos_com_largura_estranha(cliente_com_um_registro):
    cliente, sha = cliente_com_um_registro
    r = cliente.post(f"/api/eventos/{sha}/trilha", json={"largura": "abc"})
    assert r.status_code < 500


def test_nome_do_digital_nao_acumula_o_ied_a_cada_recarga():
    """Com duas oscilografias na aba, cada recarga (filtro, lado, zoom…)
    devolve `Digitais · IED A · IED A · …`. Os analógicos não acumulam porque
    o servidor refaz o nome deles pela unidade."""
    from tests.test_varios import _pacote

    primeiro = _pacote()
    arranjo = [{"id": p["id"], "tipo": p["tipo"], "nome": p["nome"],
                "sinais": p.get("sinais_pedidos") or [s["id"] for s in p.get("sinais") or []],
                "do_padrao": True}
               for p in primeiro["paineis"]]
    segundo = _pacote(paineis.de_json(arranjo))
    antes = [p["nome"] for p in primeiro["paineis"]]
    depois = [p["nome"] for p in segundo["paineis"]]
    assert depois == antes


def test_onda_js_nao_declara_a_mesma_funcao_duas_vezes_no_mesmo_nivel():
    """`function` sobe e a última declaração vence, sem erro nenhum — é o
    defeito mudo que o CLAUDE.md já registra (o `encaixar` do ímã). Clicar no
    nome de um gráfico chama `editarNome(nome, painel)`, mas quem roda é
    `editarNome(titulo)`: o Enter faz POST /api/acervo/<sha>/nome com o texto
    digitado e o registro inteiro passa a se chamar como o gráfico."""
    import re
    from collections import Counter
    from pathlib import Path

    pasta = Path(__file__).resolve().parents[1] / "src" / "osclab" / "web" / "static" / "js"
    repetidos = []
    for arquivo in sorted(pasta.glob("*.js")):
        js = arquivo.read_text(encoding="utf-8")
        # nível do IIFE: duas casas de recuo
        nomes = re.findall(r"^  (?:async )?function ([A-Za-z_$][\w$]*)\s*\(", js, flags=re.M)
        repetidos += [f"{arquivo.name}: {n}" for n, k in Counter(nomes).items() if k > 1]
    assert repetidos == []


@pytest.fixture
def cliente_isolado(tmp_path, monkeypatch):
    """Um cliente com TODO caminho de dado do usuário num diretório temporário
    — acervo, base, modelos da calculadora: os pedidos estranhos abaixo vão a
    rotas que gravam."""
    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR", "DATA_DIR", "BASE_PADRAO"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    monkeypatch.setattr(paths, "BASES_FILE", tmp_path / "bases.json")
    monkeypatch.setattr(paths, "MODELOS_DA_CALCULADORA", tmp_path / "modelos.json")
    cfg = fabrica.escrever_comtrade(tmp_path / "rec", na=6, nd=4, n=400)
    dat = cfg.with_suffix(".dat")
    sha = acervo.guardar([(cfg.name, cfg.read_bytes()),
                          (dat.name, dat.read_bytes())]).aceitos[0].sha
    return create_app(), sha


_ABREM_JANELA = {"/api/base/pasta-nativa"}


def _rotas_post(app, sha):
    for regra in app.url_map.iter_rules():
        if "POST" not in (regra.methods or ()) or not regra.rule.startswith("/api/"):
            continue
        if set(regra.arguments) - {"sha"}:
            continue
        # Abre o diálogo de pasta do SISTEMA (tkinter): numa suíte, travaria
        # esperando alguém clicar — e abriria uma janela na frente do usuário.
        if regra.rule in _ABREM_JANELA:
            continue
        yield regra.rule.replace("<sha>", sha)


@pytest.mark.parametrize("corpo", [[1, 2], "x", 3, None])
def test_corpo_que_nao_e_objeto_nao_vira_500_em_rota_nenhuma(cliente_isolado, corpo):
    """B08: `request.get_json(silent=True) or {}` devolvia a lista, e o `.get`
    da rota levantava. Toda rota POST passa por `_corpo()` agora."""
    app, sha = cliente_isolado
    cliente = app.test_client()
    ruins = []
    for rota in _rotas_post(app, sha):
        r = cliente.post(rota, json=corpo)
        if r.status_code >= 500:
            ruins.append((rota, r.status_code))
    assert ruins == []


def test_campos_de_tipo_errado_no_corpo_nao_viram_500(cliente_isolado):
    """B08: `"conta": "abc"` fazia `dict("abc")`; `"linha_base": ["a"]`, `.get`
    numa lista."""
    app, sha = cliente_isolado
    cliente = app.test_client()
    assert cliente.post(f"/api/onda/{sha}/calculadora/conferir",
                        json={"conta": "abc"}).status_code < 500
    assert cliente.post(f"/api/onda/{sha}/localizar",
                        json={"linha_base": ["a"]}).status_code < 500


def test_hdr_sozinho_diz_que_guardou_o_hdr(tmp_path, monkeypatch):
    """B07: o `.hdr` sozinho saía «guardei o .dat e estou esperando o .cfg».
    E B11: a mensagem com acento, e o nome como o arquivo o escreve."""
    from osclab import paths
    from osclab.library import acervo

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    r = acervo.guardar([("CLARO_LT3.hdr", b"qualquer coisa")])
    assert r.aceitos == [] and len(r.aguardando) == 1
    texto = r.aguardando[0]
    assert "guardei o .hdr" in texto and ".dat e estou" not in texto
    assert "o .cfg e o .dat" in texto
    assert "'CLARO_LT3'" in texto and "não dá" in texto

    r = acervo.guardar([("CLARO_LT3.dat", b"1,0,1")])
    assert "guardei o .dat e o .hdr e estou esperando o .cfg." in r.aguardando[0]


def test_potencia_nao_se_explica_como_componente_simetrica():
    """B12: o risquinho da coluna «onda» de `P G1↔G3` dizia «componente
    simétrica é fasor». A potência tem o texto dela, e ele vem ANTES do das
    componentes (as duas moram no mesmo bloco)."""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "src" / "osclab" / "web" / "static"
          / "js" / "onda.js").read_text(encoding="utf-8")
    corpo = js[js.index("function motivoDaAusencia("):]
    corpo = corpo[:corpo.index("\n  }\n")]
    assert (corpo.index("a potência sai dos fasores")
            < corpo.index("componente simétrica é fasor"))
