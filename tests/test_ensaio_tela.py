"""Os defeitos de TELA do ensaio geral da 1.0.0 (15/11/2026), conferidos na
própria função do `onda.js`, rodada pelo Node.

São funções puras de geometria e de escrita — onde pôr um rótulo, como
escrever um número —, e um teste de navegador inteiro para cada uma seria
caro e frágil. Aqui o trecho da função é recortado do arquivo e rodado com
os vizinhos de que ela precisa (o `ctx`, os cursores) postos à mão.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from osclab import paths

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="sem Node no PATH")

JS = (paths.STATIC_DIR / "js" / "onda.js").read_text(encoding="utf-8")
CSS = (paths.STATIC_DIR / "css" / "osclab.css").read_text(encoding="utf-8")


def _funcao(nome: str) -> str:
    """O texto de `function nome(...) {...}`, do nível de dentro do IIFE."""
    achado = re.search(rf"\n  function {nome}\(.*?\n  }}\n", JS, re.S)
    assert achado, nome
    return achado.group(0)


def _rodar(codigo: str):
    saida = subprocess.run([NODE, "-e", codigo], capture_output=True, text=True,
                           encoding="utf-8", timeout=60, check=True)
    return json.loads(saida.stdout)


def test_o_que_arredonda_a_zero_sai_sem_sinal():
    """«-0,0000» na tabelinha (pendência 8): o sinal de um número que a tela
    escreve como zero não diz lado nenhum."""
    achado = re.search(r"  const _formatadores = new Map\(\);\n  const formatar = .*?\n  };\n",
                       JS, re.S)
    assert achado
    numeros = [-0.00001, -0.0, 0.0, -0.5, 1234.5, None]
    saida = _rodar(achado.group(0) + f"""
        const v = {json.dumps(numeros)};
        console.log(JSON.stringify(v.map((x) => formatar(x, 4))));""")
    assert saida == ["0,0000", "0,0000", "0,0000", "-0,5000", "1.234,5000", "—"]
    # O mesmo no número do localizador.
    assert 'signDisplay: "negative" });' in JS


def test_o_100_da_LT_vai_para_o_lado_em_que_a_trajetoria_nao_passa():
    """Pendência 5: numa falta perto do fim da linha a trajetória desce pela
    ponta dela, e o rótulo à direita ficava debaixo do traço medido."""
    funcao = _funcao("ladoLivreDoRotulo")
    # Ponta da linha em (100, 100) px; X e Y identidade.
    pela_direita = [{"r": 100 + k, "x": 100} for k in range(0, 80, 2)]
    pela_esquerda = [{"r": 100 - k, "x": 100} for k in range(0, 80, 2)]
    longe = [{"r": 10, "x": 10}, {"r": 12, "x": 12}]
    saida = _rodar(funcao + f"""
        const X = (r) => r, Y = (x) => x;
        console.log(JSON.stringify([
          ladoLivreDoRotulo({json.dumps(pela_direita)}, X, Y, 100, 100, 60, 7),
          ladoLivreDoRotulo({json.dumps(pela_esquerda)}, X, Y, 100, 100, 60, 7),
          ladoLivreDoRotulo({json.dumps(longe)}, X, Y, 100, 100, 60, 7),
          ladoLivreDoRotulo([], X, Y, 100, 100, 60, 7)]));""")
    assert saida == [-1, 1, 1, 1]
    assert "ladoLivreDoRotulo(painel.pontos" in JS


def test_o_plato_nao_cai_debaixo_da_etiqueta_do_cursor():
    """Pendência 4: com o cursor no platô o «1» tapava a palavra. Ela vai
    para o lado do colchete; sem lugar, fica só o colchete."""
    funcao = _funcao("lugarDoPlato")
    casos = {
        "sem cursor": [None, None],
        "cursor no meio": [300, None],
        "dois cursores, um de cada lado do meio": [300, 185],
    }
    saida = _rodar(funcao + f"""
        const ETIQUETA = {{ largura: 15, altura: 13 }};
        const ctx = {{ measureText: (t) => ({{ width: 36 }}) }};
        const casos = {json.dumps(casos)};
        const r = {{}};
        let cursores;
        for (const [nome, c] of Object.entries(casos)) {{
          cursores = c;
          r[nome] = lugarDoPlato(ctx, (t) => t, 0, 1000, 200, 400);
        }}
        // Colchete encostado nas bordas e cursor no meio: não há lugar.
        cursores = [200, null];
        r["sem lugar"] = lugarDoPlato(ctx, (t) => t, 0, 400, 2, 398);
        console.log(JSON.stringify(r));""")
    assert saida["sem cursor"] == {"x": 300, "alinhar": "center"}
    assert saida["cursor no meio"] == {"x": 194, "alinhar": "right"}
    assert saida["dois cursores, um de cada lado do meio"] == {"x": 406, "alinhar": "left"}
    assert saida["sem lugar"] is None


def test_o_angulo_do_I_remoto_tem_linha_propria_no_plano_alfa():
    """Pendência 6: «0,173 ∠ 18…» — a coluna cortava o ângulo."""
    assert 'linha("∠ I remoto"' in JS
    assert "` ∠ ${formatar(tr.rem_ang" not in JS


def test_o_traco_do_rele_sem_numero_nao_mora_na_caixa_de_botoes():
    """Pendência 9: a `.lado` genérica é o grupo de botões (inline-flex, da
    altura de uma chave); na legenda o «—» ficava pequeno e no alto."""
    bloco = re.search(r"\.legenda \.lado \{\s*display: inline;\s*height: auto;\s*\}", CSS)
    assert bloco
    assert ".legenda li.pl-sem .lado { font-style: italic; font-size: 12.5px; }" in CSS
