"""A gaveta da calculadora NUM NAVEGADOR DE VERDADE (Chrome sem janela).

O que nome comprido de canal poderia estragar só se vê com o CSS aplicado:
tecla que estica, lista que empurra a gaveta, visor que estoura. Este teste
sobe o servidor num acervo TEMPORÁRIO com os registros de
`tests/casos_calculadora.py` (o trafo tem `TC BUC 69kV:I A`, `87T:I diff.:phs A`
e `MAIN : Timer stage N elaps.`) e roda `tests/navegador/calculadora.mjs`, que
confere medidas e gestos nos dois temas.

Pula quando não há Node ou Chrome na máquina — é teste da tela, não do domínio.
As fotos ficam numa pasta temporária; `OSCLAB_FOTOS=<pasta>` as guarda.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from tests import casos_calculadora as cc

RAIZ = Path(__file__).resolve().parents[1]
CHROMES = (
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)
def test_a_gaveta_aguenta_nome_comprido_e_os_gestos(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    monkeypatch.setattr(paths, "MODELOS_DA_CALCULADORA", tmp_path / "modelos.json")
    shas = []
    for fazer in (cc.trafo, cc.alimentador):
        pasta = tmp_path / fazer.__name__
        pasta.mkdir()
        cfg = fazer(pasta)
        dat = cfg.with_suffix(".dat")
        shas.append(
            acervo.guardar([(cfg.name, cfg.read_bytes()), (dat.name, dat.read_bytes())])
            .aceitos[0]
            .sha
        )

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            [
                "node",
                str(RAIZ / "tests" / "navegador" / "calculadora.mjs"),
                f"http://127.0.0.1:{porta}",
                shas[0],
                shas[1],
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
