"""Defeitos achados na caça de bugs de 11/11/2026, presos por teste.

Cada teste aqui FALHA no código de hoje (`xfail(strict=True)`): é o retrato
do defeito, não a correção. Quando o conserto entrar, o `xfail` vira
`XPASS` e o pytest acusa — aí se tira a marca e o teste passa a guardar a
porta. A lista completa fica em `docs-privados/caca-de-bugs-2026-11-11.md`.
"""

from __future__ import annotations

import pytest

from osclab.plot import catalogo, leitura, paineis
from tests import fabrica
from tests.test_potencia import _registro


def _potencia_ativa(registro):
    return next(x for x in catalogo.de_registro(registro, "arquivo", ())
                if x.id.startswith("w") and x.nome.startswith("P "))


@pytest.mark.xfail(strict=True, raises=ValueError,
                   reason="B01: sinal de potência (w…) cai no caminho da "
                          "componente simétrica em leitura._linhas")
def test_cursor_sobre_potencia_num_grafico_analogico_nao_derruba_a_leitura():
    """`P G1↔G2` num gráfico analógico + cursor = HTTP 500 na leitura.

    `catalogo._conjunto_do` faz `int(sinal.id[1:].split(":")[0])`, e o id de
    potência é `wG1:P:rms` — `int("G1")` levanta. A tabelinha do cursor fica
    vazia para o gráfico inteiro, não só para a linha da potência.
    """
    r = _registro("kV", 11.27, "A", 300 * 2 ** 0.5)
    p = _potencia_ativa(r)
    arranjo = paineis.de_json([{"id": "p1", "tipo": "analogico", "sinais": [p.id]}])
    meio = float(r.time[len(r.time) // 2])
    assert leitura.em(r, [(meio, 0, 0.0), (None, 0, 0.0)], layout=arranjo)


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


@pytest.mark.xfail(strict=True, reason="B02: `_numero` deixa passar inf e "
                   "`int(inf)` levanta OverflowError (HTTP 500)")
@pytest.mark.parametrize("rota", [
    "/api/onda/{sha}?colunas=inf",
    "/api/onda/{sha}/leitura?t1=0.01&refere=inf",
])
def test_infinito_na_url_nao_vira_500(cliente_com_um_registro, rota):
    cliente, sha = cliente_com_um_registro
    assert cliente.get(rota.format(sha=sha)).status_code < 500


@pytest.mark.xfail(strict=True, reason="B03: `largura` não numérica → "
                   "float('abc') em trilha_dos_eventos (HTTP 500)")
def test_trilha_dos_eventos_com_largura_estranha(cliente_com_um_registro):
    cliente, sha = cliente_com_um_registro
    r = cliente.post(f"/api/eventos/{sha}/trilha", json={"largura": "abc"})
    assert r.status_code < 500


@pytest.mark.xfail(strict=True, reason="B04: o nome do painel DIGITAL do padrão "
                   "volta da tela e ganha mais um « · IED A» a cada pedido "
                   "(varios.montar_janela)")
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


@pytest.mark.xfail(strict=True, reason="B05: duas `function editarNome` no mesmo "
                   "escopo de onda.js — a do registro (linha ~15031) vence, e "
                   "renomear um GRÁFICO grava o apelido do REGISTRO")
def test_onda_js_nao_declara_a_mesma_funcao_duas_vezes_no_mesmo_nivel():
    """`function` sobe e a última declaração vence, sem erro nenhum — é o
    defeito mudo que o CLAUDE.md já registra (o `encaixar` do ímã). Clicar no
    nome de um gráfico chama `editarNome(nome, painel)`, mas quem roda é
    `editarNome(titulo)`: o Enter faz POST /api/acervo/<sha>/nome com o texto
    digitado e o registro inteiro passa a se chamar como o gráfico."""
    import re
    from collections import Counter
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "src" / "osclab" / "web"
          / "static" / "js" / "onda.js").read_text(encoding="utf-8")
    # nível do IIFE: duas casas de recuo
    nomes = re.findall(r"^  function ([A-Za-z_$][\w$]*)\s*\(", js, flags=re.M)
    repetidos = sorted(n for n, k in Counter(nomes).items() if k > 1)
    assert repetidos == []
