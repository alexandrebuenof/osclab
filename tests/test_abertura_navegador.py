"""A barra de progresso da ABERTURA num navegador de verdade (14/11/2026).

Sobe o servidor num acervo TEMPORÁRIO com quatro sintéticos: um RÁPIDO e
três «LENTO», cujo diagnóstico bruto × filtrado o servidor de teste atrasa
de propósito em passos de 0,2 s — anunciando o progresso a cada passo, como
a conta de verdade faz canal a canal. Roda `tests/navegador/abertura.mjs`:
o rápido não mostra barra; o lento mostra, ela anda e some; «+ adicionar
oscilografia» com um lento mostra a barra na tira dos IEDs.

Pula quando não há Node ou Chrome na máquina — é teste da tela, não do
domínio (o domínio está em `tests/test_progresso.py`). As fotos ficam numa
pasta temporária; `OSCLAB_FOTOS=<pasta>` as guarda.
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

sem_navegador = pytest.mark.skipif(
    not shutil.which("node") or not any(Path(c).exists() for c in CHROMES),
    reason="sem Node ou Chrome nesta máquina",
)

#: Quantos passos de 0,2 s o diagnóstico de um registro «LENTO» leva a mais.
PASSOS_DO_ATRASO = 12


@sem_navegador
def test_a_barra_de_progresso_da_abertura(tmp_path, monkeypatch):
    from werkzeug.serving import make_server

    from osclab import paths, progresso
    from osclab.analysis import filtragem
    from osclab.library import acervo
    from osclab.web.server import create_app

    for nome in ("LIBRARY_DIR", "CACHE_DIR", "CONFIG_DIR"):
        monkeypatch.setattr(paths, nome, tmp_path / nome.lower())
    shas = {}
    for nome, n in (("RAPIDO", 600), ("LENTO1", 6000), ("LENTO2", 6000), ("LENTO3", 6000)):
        cfg = escrever_comtrade(tmp_path / nome, nome=nome, equipamento=nome, na=6, nd=8,
                                n=n, taxa=2000.0, degraus=True)
        r = acervo.guardar([(p.name, p.read_bytes()) for p in (cfg, cfg.with_suffix(".dat"))])
        assert len(r.aceitos) == 1, r.problemas
        shas[nome] = r.aceitos[0].sha
    acervo._abertos.clear()

    original = filtragem.diagnosticar

    def atrasado(registro):
        if registro.device_id.startswith("LENTO"):
            for k in range(PASSOS_DO_ATRASO):
                time.sleep(0.2)
                progresso.avancar(k + 1, PASSOS_DO_ATRASO)
        return original(registro)
    monkeypatch.setattr(filtragem, "diagnosticar", atrasado)

    porta = _porta_livre()
    servidor = make_server("127.0.0.1", porta, create_app(), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    fotos = os.environ.get("OSCLAB_FOTOS") or str(tmp_path / "fotos")
    try:
        r = subprocess.run(
            ["node", str(RAIZ / "tests" / "navegador" / "abertura.mjs"),
             f"http://127.0.0.1:{porta}", shas["RAPIDO"], shas["LENTO1"], shas["LENTO2"],
             shas["LENTO3"], fotos, str(_porta_livre())],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
        )
    finally:
        servidor.shutdown()
        acervo._abertos.clear()
    if r.returncode == 77:
        pytest.skip("sem Chrome")
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-2000:]
