"""A gaveta das LINHAS: os parâmetros que a localização de falta usa.

Um arquivo `linhas.csv`, separado por `;`, uma linha de transmissão por linha:

    nome;terminal_s;terminal_r;r1_ohm;x1_ohm;comprimento_km
    LT COXIPO - BDURO;COXIPO;BARRO DURO;0,67;3,759;9,29

`r1_ohm` e `x1_ohm` são a impedância de sequência positiva da LINHA INTEIRA,
em ohm PRIMÁRIO. É o que se lê num estudo e o que a planilha LocDef_SeqNeg
pede. Vírgula ou ponto decimal, tanto faz — quem escreve é gente.

`r0_ohm` e `x0_ohm` (sequência zero, linha inteira, primário) são OPCIONAIS e
vêm no fim: a sequência negativa não usa Z0, mas o laço da falta de terra
precisa dele para o k0. Arquivo antigo, sem as duas colunas, continua valendo.

`b1_us` e `b0_us` (susceptância shunt de sequência positiva e zero, linha
inteira, µS primário) também são OPCIONAIS, depois de `x0_ohm`: com `b1_us`
a sequência negativa usa a linha DISTRIBUÍDA (`ldl.seqneg_distribuida`); sem
ela, a concentrada. A capacitância não se inventa.

A base é a PRIMEIRA fonte da localização (depois vêm os ajustes do IED A, os
do IED B e, por último, o que se digita na tela). Pedido dele, 22/10/2026.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path

ARQUIVO = "linhas.csv"
PASTA = "linhas"
COLUNAS = ("nome", "terminal_s", "terminal_r", "r1_ohm", "x1_ohm", "comprimento_km",
           "r0_ohm", "x0_ohm", "b1_us", "b0_us")


@dataclass(frozen=True)
class Linha:
    nome: str
    terminal_s: str
    terminal_r: str
    r1_ohm: float
    x1_ohm: float
    comprimento_km: float
    r0_ohm: float | None = None
    x0_ohm: float | None = None
    b1_us: float | None = None
    b0_us: float | None = None

    def como_dicionario(self) -> dict:
        return {c: getattr(self, c) for c in COLUNAS}


def _caminho(base) -> Path:
    return base.gaveta(PASTA) / ARQUIVO


def _numero(texto) -> float | None:
    try:
        valor = float(str(texto).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    # `nan` e `inf` passam no `float` e não são impedância de linha nenhuma.
    return valor if math.isfinite(valor) else None


def listar(base) -> list[Linha]:
    """Todas as linhas da base. Linha com número ilegível fica de fora."""
    try:
        texto = _caminho(base).read_text(encoding="utf-8-sig")
    except OSError:
        return []
    saida = []
    for cru in csv.DictReader(io.StringIO(texto), delimiter=";"):
        r, x, km = (_numero(cru.get("r1_ohm")), _numero(cru.get("x1_ohm")),
                    _numero(cru.get("comprimento_km")))
        nome = str(cru.get("nome") or "").strip()
        if not nome or r is None or x is None or not km or km <= 0:
            continue
        r0, x0 = _numero(cru.get("r0_ohm")), _numero(cru.get("x0_ohm"))
        if r0 is None or x0 is None:
            r0 = x0 = None
        b1, b0 = _numero(cru.get("b1_us")), _numero(cru.get("b0_us"))
        b1 = b1 if b1 is not None and b1 > 0 else None
        b0 = b0 if b0 is not None and b0 > 0 else None
        saida.append(Linha(nome, str(cru.get("terminal_s") or "").strip(),
                           str(cru.get("terminal_r") or "").strip(), r, x, km, r0, x0,
                           b1, b0))
    return saida


def gravar(base, linha: Linha) -> Path:
    """Acrescenta a linha, ou troca a de mesmo nome."""
    todas = [x for x in listar(base) if x.nome.upper() != linha.nome.upper()]
    todas.append(linha)
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(COLUNAS)
    # `.15g` e não `g`: este guarda só seis algarismos, e o R/X digitado com
    # mais voltava da base arredondado.
    numero = lambda v: "" if v is None else f"{v:.15g}".replace(".", ",")  # noqa: E731
    for x in todas:
        escritor.writerow([x.nome, x.terminal_s, x.terminal_r, numero(x.r1_ohm),
                           numero(x.x1_ohm), numero(x.comprimento_km),
                           numero(x.r0_ohm), numero(x.x0_ohm),
                           numero(x.b1_us), numero(x.b0_us)])
    destino = _caminho(base)
    destino.write_text(saida.getvalue(), encoding="utf-8")
    return destino


def _normal(texto: str) -> str:
    return " ".join(str(texto or "").upper().split())


def procurar(base, textos_a: list[str], textos_b: list[str]) -> list[Linha]:
    """As linhas cujos dois terminais aparecem, um em cada registro.

    `textos_a` e `textos_b` são o que cada registro diz de si: estação,
    equipamento, apelido, nome do arquivo. Casa por TRECHO de texto, em
    qualquer ordem dos terminais — quem é S na base não precisa ser o IED A.
    Devolve todas as que casarem: mais de uma é dúvida, e a tela pergunta.
    """
    a = [_normal(t) for t in textos_a if t]
    b = [_normal(t) for t in textos_b if t]

    def aparece(terminal: str, textos: list[str]) -> bool:
        alvo = _normal(terminal)
        return bool(alvo) and any(alvo in t for t in textos)

    saida = []
    for linha in listar(base):
        s, r = linha.terminal_s, linha.terminal_r
        if (aparece(s, a) and aparece(r, b)) or (aparece(r, a) and aparece(s, b)):
            saida.append(linha)
    return saida
