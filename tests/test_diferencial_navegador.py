"""A gaveta de ajustes do diferencial NUM NAVEGADOR DE VERDADE (Chrome sem janela).

Sobe o servidor num acervo TEMPORÁRIO com o trafo de `tests/casos_calculadora.py`
(duas trincas de corrente, nenhum ajuste no arquivo) e roda
`tests/navegador/diferencial.mjs`, que confere a variante 10 (12/11/2026):

* sem ajustes, a característica APAGADA no lugar do gráfico e o que falta numa
  linha abaixo dele — nada escrito por cima do desenho;
* a gaveta à direita, embaixo da barra de cima, com a coluna encolhendo;
* o grupo de cada lado só como «G1» — o radical só no hover (pedido dele);
* digitar o pickup muda a prévia ao vivo, e ao sair do campo ele vira
  «digitado» sem a gaveta fechar;
* clique fora não fecha (janela de edição), Esc fecha.

Pula quando não há Node ou Chrome na máquina — é teste da tela, não do domínio.
As fotos ficam numa pasta temporária; `OSCLAB_FOTOS=<pasta>` as guarda.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from tests import casos_calculadora as cc
from tests.test_calculadora_navegador import CHROMES, RAIZ, _porta_livre


@pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)
def test_gaveta_de_ajustes_do_diferencial(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    monkeypatch.setattr(paths, "MODELOS_DA_CALCULADORA", tmp_path / "modelos.json")
    pasta = tmp_path / "trafo"
    pasta.mkdir()
    cfg = cc.trafo(pasta)
    dat = cfg.with_suffix(".dat")
    guardado = acervo.guardar([(cfg.name, cfg.read_bytes()), (dat.name, dat.read_bytes())])
    sha = guardado.aceitos[0].sha

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            [
                "node",
                str(RAIZ / "tests" / "navegador" / "diferencial.mjs"),
                f"http://127.0.0.1:{porta}",
                sha,
                fotos,
                str(_porta_livre()),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
    finally:
        servidor.shutdown()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
