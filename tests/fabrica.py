"""Fábrica de arquivos COMTRADE sintéticos para os testes.

Por que sintéticos e não os arquivos reais da distribuidora: uma oscilografia de
verdade identifica instalação, data e comportamento da rede, e este repositório
é público. Além disso um arquivo sintético tem resposta CONHECIDA — dá para
afirmar "a senoide tinha 100 A de pico, o leitor tem que devolver 100 A", o que
um arquivo real nunca permite.

Os arquivos reais continuam sendo testados, mas por fora: ver
`test_comtrade_reais.py`.

Cada variação aqui existe porque apareceu num arquivo real do parque:

* `revisao="2001"` — um MiCOM da Schneider escreve um ano que não é edição
  nenhuma da norma.
* `nrates=0` — um GE 850 não declara taxa; o tempo vem do carimbo por amostra.
* `timemult=False` — a Schneider não escreve a última linha.
* `crlf=False` — o GE grava com fim de linha do Unix.
* `lixo_no_fim` — o SEL-TWFL fecha o `.dat` com 64 bytes `0x1A`.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

PICO = 100.0          #: pico da senoide gerada, em unidade de engenharia
ESCALA = 0.01         #: fator `a` de cada canal — o leitor tem que aplicá-lo


def _instantes(n: int, taxa: float,
               taxas: list[tuple[float, int]] | None) -> np.ndarray:
    """Os instantes de cada amostra, em segundos.

    Com `taxas`, o passo muda de trecho para trecho — e tanto os carimbos do
    arquivo quanto a própria onda saem DAQUI. Gerar a onda com uma taxa fixa e
    carimbar com outra faria o arquivo mentir sobre si mesmo, e o teste passaria
    a testar a mentira.
    """
    if not taxas:
        return np.arange(n) / taxa

    passos, anterior = [], 0
    for hz, ate in taxas:
        passos.extend([1.0 / hz] * (min(int(ate), n) - anterior))
        anterior = min(int(ate), n)
    passos.extend([passos[-1]] * (n - len(passos)))
    return np.concatenate(([0.0], np.cumsum(passos)[:-1]))


def _senoides(na: int, freq: float, t: np.ndarray) -> np.ndarray:
    """(na, n) senoides defasadas de 120°, com `PICO` de amplitude.

    A defasagem é NEGATIVA: B atrasa 120° de A, C atrasa 240°. É a sequência
    ABC, que é a do sistema. Com o sinal trocado a fábrica gerava ACB — um
    registro em que toda a corrente aparece na sequência NEGATIVA, e qualquer
    conferência de componentes simétricas contra ele sairia de cabeça para
    baixo sem dar erro nenhum.
    """
    fases = np.deg2rad(-np.arange(na) * 120.0)
    return PICO * np.sin(2 * np.pi * freq * t[None, :] + fases[:, None])


def _digitais(nd: int, n: int) -> np.ndarray:
    """(nd, n) de 0/1. O canal k liga quando o bit k do índice da amostra liga.

    Padrão escolhido para o teste poder conferir o desempacotamento bit a bit
    sem precisar de tabela: é a própria contagem binária.
    """
    idx = np.arange(n)
    return ((idx[None, :] >> np.arange(nd)[:, None]) & 1).astype(np.int8)


def escrever_comtrade(
    pasta: Path,
    *,
    nome: str = "teste",
    revisao: str = "1999",
    tipo: str = "BINARY",
    na: int = 3,
    nd: int = 4,
    n: int = 128,
    taxa: float = 960.0,
    freq: float = 60.0,
    nrates: int = 1,
    timemult: bool = True,
    crlf: bool = True,
    codec: str = "utf-8",
    estacao: str = "SE TESTE",
    equipamento: str = "IED-TESTE",
    lixo_no_fim: int = 0,
    escala_primaria: bool = False,
    taxas: list[tuple[float, int]] | None = None,
) -> Path:
    """Escreve um par `.cfg`/`.dat` e devolve o caminho do `.cfg`."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    cfg_path = pasta / f"{nome}.cfg"
    dat_path = pasta / f"{nome}.dat"

    instantes = _instantes(n, taxa, taxas)
    analog = _senoides(na, freq, instantes)
    digital = _digitais(nd, n)
    crus = np.rint(analog / ESCALA).astype(np.int64)

    ps = "P" if escala_primaria else "S"
    linhas = [
        f"{estacao},{equipamento},{revisao}",
        f"{na + nd},{na}A,{nd}D",
    ]
    for k in range(na):
        # An,id,ph,ccbm,uu,a,b,skew,min,max,primary,secondary,PS
        fase = "ABC"[k % 3]
        linhas.append(
            f"{k + 1},CH{k + 1},{fase},,A,{ESCALA},0,0,-32767,32767,600.0,5.0,{ps}"
        )
    for k in range(nd):
        linhas.append(f"{k + 1},D{k + 1},,,0")
    linhas.append(f"{freq}")
    # `taxas` escreve VÁRIOS trechos, que é o que a norma permite e o que um relé
    # faz ao gravar a falta a 96 amostras/ciclo e o resto a 16.
    if taxas:
        linhas.append(f"{len(taxas)}")
        linhas.extend(f"{hz},{ate}" for hz, ate in taxas)
    else:
        linhas.append(f"{nrates}")
        # Mesmo com nrates = 0 existe uma linha de taxa — com samp = 0.
        linhas.append(f"{taxa if nrates else 0},{n}")
    linhas.append("01/02/2026,03:04:05.000000")
    linhas.append("01/02/2026,03:04:05.050000")
    linhas.append(tipo)
    if timemult:
        linhas.append("1.0")
    if revisao == "2013":
        linhas.append("0,-4")
        linhas.append("0,0")

    fim = "\r\n" if crlf else "\n"
    cfg_path.write_bytes(fim.join(linhas).encode(codec) + fim.encode(codec))

    carimbos = np.rint(instantes * 1e6).astype(np.int64)

    if tipo == "ASCII":
        partes = []
        for i in range(n):
            campos = [str(i + 1), str(int(carimbos[i]))]
            campos += [str(int(crus[k, i])) for k in range(na)]
            campos += [str(int(digital[k, i])) for k in range(nd)]
            partes.append(",".join(campos))
        dat_path.write_bytes(fim.join(partes).encode("ascii") + fim.encode("ascii"))
        return cfg_path

    formato = {"BINARY": "<h", "BINARY32": "<i", "FLOAT32": "<f"}[tipo]
    palavras = (nd + 15) // 16
    buf = bytearray()
    for i in range(n):
        buf += struct.pack("<II", i + 1, int(carimbos[i]))
        for k in range(na):
            valor = float(analog[k, i] / ESCALA) if tipo == "FLOAT32" else int(crus[k, i])
            buf += struct.pack(formato, valor)
        for w in range(palavras):
            palavra = 0
            for bit in range(16):
                canal = w * 16 + bit
                if canal < nd and digital[canal, i]:
                    palavra |= 1 << bit
            buf += struct.pack("<H", palavra)
    buf += b"\x1a" * lixo_no_fim
    dat_path.write_bytes(bytes(buf))
    return cfg_path


def esperado_analog(na: int, n: int, taxa: float, freq: float) -> np.ndarray:
    """O que o leitor tem que devolver, em unidade de engenharia."""
    return np.rint(_senoides(na, freq, _instantes(n, taxa, None)) / ESCALA) * ESCALA


def esperado_digital(nd: int, n: int) -> np.ndarray:
    return _digitais(nd, n)
