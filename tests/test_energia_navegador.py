"""A energia do «+ sinal» pedida quando ele abre, NUM NAVEGADOR DE VERDADE.

Desde 14/11/2026 a barrinha de energia de cada sinal não é mais feita ao abrir
o registro (era ~30 % da abertura de um registro de ondas viajantes): a tela a
pede ao abrir o «+ sinal». O servidor de teste ATRASA a conta de propósito, em
passos de 0,2 s que anunciam o progresso, e `tests/navegador/energia.mjs`
confere que o catálogo abre na hora, mostra a barra de progresso, recebe as
barrinhas sem perder a busca e não pede de novo ao reabrir.

Pula quando não há Node ou Chrome na máquina — é teste da tela, não do
domínio (o domínio está em `tests/test_leveza.py` e `tests/test_progresso.py`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from tests.fabrica import escrever_comtrade
from tests.test_calculadora_navegador import CHROMES, RAIZ, _porta_livre

#: Quantos passos de 0,2 s a conta da energia leva a mais.
PASSOS_DO_ATRASO = 10


@pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)
def test_a_energia_chega_depois_do_catalogo_abrir(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths, progresso
    from osclab.library import acervo
    from osclab.plot import catalogo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    cfg = escrever_comtrade(tmp_path / "REG", nome="REG", na=6, nd=8, n=6000,
                            taxa=2000.0, degraus=True)
    r = acervo.guardar([(p.name, p.read_bytes()) for p in (cfg, cfg.with_suffix(".dat"))])
    sha = r.aceitos[0].sha
    acervo._abertos.clear()

    original = catalogo.energia_das_linhas

    def atrasada(*a, **k):
        for passo in range(PASSOS_DO_ATRASO):
            time.sleep(0.2)
            progresso.avancar(passo + 1, PASSOS_DO_ATRASO + 1)
        return original(*a, **k)
    monkeypatch.setattr(catalogo, "energia_das_linhas", atrasada)

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            ["node", str(RAIZ / "tests" / "navegador" / "energia.mjs"),
             f"http://127.0.0.1:{porta}", sha, fotos, str(_porta_livre())],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
    finally:
        servidor.shutdown()
        acervo._abertos.clear()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
