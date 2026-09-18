"""Abre uma oscilografia e descreve o que encontrou, no terminal.

Existe porque a interface gráfica só chega no marco 0.3, e um leitor que
ninguém consegue apontar para um arquivo não dá para conferir. Também é o jeito
mais rápido de investigar um arquivo que o programa recusou.

    python app.py --ler "C:\\caminho\\registro.cfg"
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from osclab.formats import registry
from osclab.formats.base import FormatError, Record


def _rms(v: np.ndarray) -> float:
    """RMS ignorando amostras ausentes."""
    bons = v[np.isfinite(v)]
    return float(np.sqrt(np.mean(bons ** 2))) if bons.size else float("nan")


def descrever(r: Record) -> str:
    """O resumo do registro, em texto."""
    linhas: list[str] = []
    ad = linhas.append

    ad(f"Arquivo      : {Path(r.source).name}")
    ad(f"Formato      : {r.format_name}")
    ad(f"Subestacao   : {r.station or '(nao informada)'}")
    ad(f"Equipamento  : {r.device_id or '(nao informado)'}")
    ad("")
    ad(f"Canais       : {len(r.analog_channels)} analogicos, "
       f"{len(r.status_channels)} digitais")
    ad(f"Amostras     : {r.n_samples}")
    ad(f"Frequencia   : {r.line_frequency:g} Hz nominais")
    ad(f"Taxa         : {r.base_rate_hz:.1f} Hz  "
       f"({r.samples_per_cycle:.2f} amostras por ciclo)")
    ad(f"Duracao      : {r.duration * 1000:.2f} ms")
    if len(r.sample_rates) > 1:
        ad(f"               {len(r.sample_rates)} trechos com taxas diferentes")
    ad("")
    ad(f"Primeira amostra: {r.start_time or '(sem carimbo)'}")
    ad(f"Disparo         : {r.trigger_time or '(sem carimbo)'}"
       + (f"  -> amostra {r.trigger_index}" if r.trigger_index is not None else ""))
    if r.time_quality:
        ad(f"Qualidade do relogio: {r.time_quality}")

    if r.analog_channels:
        # A largura acompanha os nomes. Cortar em tamanho fixo escondia
        # informacao de verdade: a Siemens nao preenche o campo de fase e poe a
        # fase no FIM do nome ("TC BUC 69kV:I A"), que era justamente o pedaco
        # que sumia.
        largura = min(max(len(c.name) for c in r.analog_channels), 40)
        largura = max(largura, 4)
        ad("")
        ad("Canais analogicos")
        ad(f"  {'#':>3}  {'nome':<{largura}} {'un':<5} {'fase':<5} "
           f"{'escala':<11} {'minimo':>12} {'maximo':>12} {'RMS':>12}")
        for c in r.analog_channels:
            v = r.analog[c.index]
            ad(f"  {c.index + 1:>3}  {c.name[:largura]:<{largura}} "
               f"{c.unit[:5]:<5} {(c.phase or '-'):<5} "
               f"{'primario' if c.is_primary else 'secundario':<11} "
               f"{np.nanmin(v):12.3f} {np.nanmax(v):12.3f} {_rms(v):12.3f}")

    if r.status_channels:
        ad("")
        mudaram = [c for c in r.status_channels
                   if r.status[c.index].min() != r.status[c.index].max()]
        ad(f"Canais digitais  : {len(r.status_channels)} no total, "
           f"{len(mudaram)} mudaram de estado durante o registro")
        for c in mudaram[:20]:
            serie = r.status[c.index]
            primeira = int(np.argmax(serie != serie[0]))
            instante = r.time[primeira] * 1000 if r.n_samples else 0.0
            ad(f"  {c.name[:28]:<28} {serie[0]} -> {serie[primeira]} "
               f"em {instante:+.2f} ms")
        if len(mudaram) > 20:
            ad(f"  ... e mais {len(mudaram) - 20}")

    if r.notes:
        ad("")
        ad("Avisos do leitor")
        for nota in r.notes:
            ad(f"  - {nota}")

    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("uso: python app.py --ler <arquivo.cfg | arquivo.cff>")
        return 2
    # O Windows inclui as aspas quando o arquivo e' ARRASTADO para a janela, e
    # quem digita um caminho com espaco costuma po-las tambem. `nargs="+"` junta
    # os pedacos de um caminho digitado sem aspas; o strip cuida do resto.
    caminho = Path(" ".join(args).strip().strip('"').strip("'"))
    if not caminho.exists():
        print(f"[ERRO] Nao encontrei este arquivo:\n       {caminho}")
        print("       Confira se o caminho esta completo e se o arquivo "
              "continua la'.")
        return 1
    try:
        registro = registry.read(caminho)
    except FormatError as exc:
        print(f"[ERRO] {exc}")
        return 1
    print(descrever(registro))
    return 0
