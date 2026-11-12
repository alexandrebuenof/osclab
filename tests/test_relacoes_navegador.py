"""A relação de TC/TP digitada NUM NAVEGADOR DE VERDADE (Chrome sem janela).

Os três lugares onde se digita — o cartão do grupo em «editar grupos», o
campo ⚠ da calculadora e a coluna «relação» de «canais» — nunca tinham sido
clicados: os testes de `tests/test_relacoes.py` falam com o servidor direto.
Este sobe o servidor num acervo TEMPORÁRIO com o alimentador de
`tests/casos_calculadora.py` (o «Current IN» dele não declara relação) e roda
`tests/navegador/relacoes.mjs`, que digita em cada um e confere o que o
servidor gravou — e que reaberta a página o campo mostra o gravado.

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
def test_digitar_a_relacao_no_grupo_na_calculadora_e_em_canais(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    monkeypatch.setattr(paths, "MODELOS_DA_CALCULADORA", tmp_path / "modelos.json")
    pasta = tmp_path / "alimentador"
    pasta.mkdir()
    cfg = cc.alimentador(pasta)
    dat = cfg.with_suffix(".dat")
    sha = acervo.guardar([(cfg.name, cfg.read_bytes()),
                          (dat.name, dat.read_bytes())]).aceitos[0].sha

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            ["node", str(RAIZ / "tests" / "navegador" / "relacoes.mjs"),
             f"http://127.0.0.1:{porta}", sha, fotos, str(_porta_livre())],
            capture_output=True, text=True, encoding="utf-8", timeout=400,
        )
    finally:
        servidor.shutdown()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
    # E o que ficou no disco é o que o último passo gravou.
    assert acervo.relacoes(sha)["canais"]
