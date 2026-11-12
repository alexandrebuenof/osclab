"""Canal de «Outros sinais» num registro JÁ FILTRADO, NUM NAVEGADOR DE VERDADE.

Num `.CEV` o canal mora na coluna do filtrado; o cartão de um canal sem fase
(`V1MEM`, `VS1`, `FREQ` de um SEL-411L) nascia com o interruptor apagado e as
três folhas riscadas, sem como pôr o canal na tela (12/11/2026). Roda
`tests/navegador/outros-filtrado.mjs` sobre um `.CEV` sintético.

Pula quando não há Node ou Chrome na máquina — é teste da tela, não do domínio.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from tests.fabrica import escrever_cev
from tests.test_calculadora_navegador import CHROMES, RAIZ, _porta_livre


@pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)
def test_canal_sem_fase_de_um_cev_entra_no_grafico(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    pasta = tmp_path / "registro"
    pasta.mkdir()
    cev = escrever_cev(pasta, por_ciclo=8, ciclos=12)
    sha = acervo.guardar([(cev.name, cev.read_bytes())]).aceitos[0].sha

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            ["node", str(RAIZ / "tests" / "navegador" / "outros-filtrado.mjs"),
             f"http://127.0.0.1:{porta}", sha, fotos, str(_porta_livre())],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
    finally:
        servidor.shutdown()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
