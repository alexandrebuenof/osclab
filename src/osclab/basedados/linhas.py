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
import unicodedata
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
    #: O código da linha (`69LT70`) e o trecho (`1/2`), quando a base tem —
    #: é o que junta os trechos de uma linha com derivação.
    codigo: str = ""
    trecho: str = ""

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
                           b1, b0, str(cru.get("codigo") or "").strip(),
                           str(cru.get("trecho") or "").strip()))
    return saida


#: `.15g` e não `g`: este guarda só seis algarismos, e o R/X digitado com mais
#: voltava da base arredondado.
def _texto_do_numero(v) -> str:
    return "" if v is None else f"{v:.15g}".replace(".", ",")


def _cru(caminho: Path) -> tuple[list[str], list[dict]]:
    """O arquivo como está: TODAS as colunas e TODAS as linhas, inclusive as
    sem parâmetro, que o `listar` deixa de fora."""
    try:
        texto = caminho.read_text(encoding="utf-8-sig")
    except OSError:
        return [], []
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    return list(leitor.fieldnames or []), list(leitor)


def gravar(base, linha: Linha) -> Path:
    """Acrescenta a linha, ou troca a de mesmo nome E mesmos terminais.

    Trabalha sobre o arquivo CRU. A versão anterior relia pelo `listar` e
    escrevia só as dez colunas que o programa conhece: a base montada do
    OnLiner tem 23 (código, trecho, condutor, GUID…), e a primeira gravação
    pela tela apagava as outras treze — e todas as linhas ainda sem parâmetro.
    Nada se perde: o que o programa não conhece volta como veio.
    """
    destino = _caminho(base)
    colunas, linhas_cruas = _cru(destino)
    colunas = colunas + [c for c in COLUNAS if c not in colunas]
    novo = {"nome": linha.nome, "terminal_s": linha.terminal_s,
            "terminal_r": linha.terminal_r, "r1_ohm": _texto_do_numero(linha.r1_ohm),
            "x1_ohm": _texto_do_numero(linha.x1_ohm),
            "comprimento_km": _texto_do_numero(linha.comprimento_km),
            "r0_ohm": _texto_do_numero(linha.r0_ohm), "x0_ohm": _texto_do_numero(linha.x0_ohm),
            "b1_us": _texto_do_numero(linha.b1_us), "b0_us": _texto_do_numero(linha.b0_us)}
    chave = lambda r: tuple(str(r.get(c) or "").strip().upper()  # noqa: E731
                            for c in ("nome", "terminal_s", "terminal_r"))
    trocou = False
    for r in linhas_cruas:
        if chave(r) == chave(novo):
            # Só o que veio PREENCHIDO troca: um Z0 em branco na tela não
            # apaga o Z0 que a base tinha. As outras colunas ficam como estão.
            r.update({c: v for c, v in novo.items() if v != ""})
            trocou = True
    if not trocou:
        linhas_cruas.append(novo)
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, colunas, delimiter=";", lineterminator="\n",
                              extrasaction="ignore", restval="")
    escritor.writeheader()
    escritor.writerows(linhas_cruas)
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

    # Pelas ENTRADAS (`entradas`), não pelos trechos: numa linha com
    # derivação nenhum trecho vai de uma ponta à outra, e com os dois
    # registros abertos a casagem respondia «nenhuma linha».
    saida = []
    for x in entradas(base):
        s, r = x["terminal_s"], x["terminal_r"]
        if (aparece(s, a) and aparece(r, b)) or (aparece(r, a) and aparece(s, b)):
            saida.append(x)
    return saida


def _palavras(texto) -> str:
    """O texto em maiúsculas, sem acento, com tudo que não é letra ou dígito
    virando espaço, e com espaço nas pontas — para casar por PALAVRA INTEIRA:
    `" MI "` está em `" LT MI NI "` e não está em `" TERMINAL "`."""
    t = unicodedata.normalize("NFD", str(texto or "").upper())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " " + " ".join("".join(c if c.isalnum() else " " for c in t).split()) + " "


def buscar(base, texto: str, textos_do_registro: list[str]) -> list[dict]:
    """A busca da janela «parâmetros» do localizador.

    Toda linha da base em que cada palavra digitada aparece (no nome ou num
    terminal, sem acento, como começo de palavra ou dentro dela — quem digita
    «verd» quer «RIO VERDE»). As SUGERIDAS vêm primeiro: as que têm um
    terminal escrito, como palavra inteira, no que o registro diz de si.

    Palavra inteira, e não trecho: por trecho, o terminal «MI» casava com o
    «TERMINAL» do nome do arquivo, e toda linha de nome curto virava sugerida
    (achado na maquete de 09/11/2026).
    """
    digitadas = _palavras(texto).split()
    registro = [_palavras(t) for t in textos_do_registro if t]
    saida = []
    for x in entradas(base):
        nomes = [x["terminal_s"], x["terminal_r"]] + ([x["tap"]] if x.get("tap") else [])
        alvo = _palavras(" ".join([x["nome"], *nomes]
                                  + [t["terminal_s"] + " " + t["terminal_r"]
                                     for t in x["trechos"]]))
        if any(p not in alvo for p in digitadas):
            continue
        casou = [t for t in nomes
                 if _palavras(t).strip() and any(_palavras(t) in r for r in registro)]
        saida.append({**x, "sugerida": bool(casou), "casou": casou})
    # Ordem alfabética SEM acento: pelo código do caractere, «ÁGUA BOA» ia
    # para depois de «SIGMA».
    saida.sort(key=lambda d: (not d["sugerida"], _palavras(d["nome"])))
    return saida


def _polar(r, x) -> dict:
    if r is None or x is None:
        return {"z1_mod": None, "z1_ang": None}
    return {"z1_mod": math.hypot(r, x), "z1_ang": math.degrees(math.atan2(x, r))}


def entradas(base) -> list[dict]:
    """O que a janela lista: UMA entrada por linha, e não por trecho.

    * `linha`: um trecho só, como sempre foi;
    * `3t`: linha de três terminais do `linhas-3t.csv` — o caminho A–B, com o
      TAP dito; os trechos dela ficam DENTRO da entrada;
    * `trechos`: linha em mais de um trecho, sem TAP confirmado — somada de
      ponta a ponta, com aviso, e com os trechos dentro.

    Nada some: todo trecho da base continua escolhível, dentro da entrada dele.
    """
    from osclab.basedados import tres_terminais as t3
    circuitos = {c.nome.upper(): c for c in t3.listar(base)}
    grupos: dict[str, list[Linha]] = {}
    for x in listar(base):
        grupos.setdefault(x.nome.upper(), []).append(x)
    saida = []
    for chave_, trechos in grupos.items():
        c = circuitos.get(chave_)
        lista = [{**t.como_dicionario(), **_polar(t.r1_ohm, t.x1_ohm)} for t in trechos]
        if c is not None:
            cam = t3.caminho_de_circuito(c)
            a, b, tap = c.perna("A"), c.perna("B"), c.perna("TAP")
            saida.append({
                "tipo": "3t", "nome": c.nome,
                "terminal_s": a.nome if a else trechos[0].terminal_s,
                "terminal_r": b.nome if b else trechos[-1].terminal_r,
                "tap": tap.nome if tap else "", "situacao": c.situacao, "papeis": c.papeis,
                "origem": c.origem, "nota": c.nota, "ponto": c.ponto,
                "comprimento_km": cam.get("km"), "r1_ohm": cam.get("r"),
                "x1_ohm": cam.get("x"), "r0_ohm": cam.get("r0"), "x0_ohm": cam.get("x0"),
                "b1_us": None, **_polar(cam.get("r"), cam.get("x")),
                "pernas": [{"nome": p.nome, "barra": p.barra, "papel": p.papel, "km": p.km,
                            "r1": p.r1, "x1": p.x1, "r0": p.r0, "x0": p.x0} for p in c.pernas],
                "motivo": "" if cam.get("ok") else cam.get("motivo", ""),
                "trechos": lista})
        elif len(trechos) > 1:
            cam = t3.caminho_de_trechos(trechos)
            saida.append({
                "tipo": "trechos", "nome": trechos[0].nome,
                "terminal_s": trechos[0].terminal_s, "terminal_r": trechos[-1].terminal_r,
                "pontos": [t.terminal_r for t in trechos[:-1]],
                "comprimento_km": cam["km"], "r1_ohm": cam["r"], "x1_ohm": cam["x"],
                "r0_ohm": cam.get("r0"), "x0_ohm": cam.get("x0"), "b1_us": None,
                **_polar(cam["r"], cam["x"]), "trechos": lista})
        else:
            saida.append({"tipo": "linha", **lista[0], "trechos": []})
    return saida


def escolhida(base, nome: str, terminal_s: str = "", terminal_r: str = "") -> Linha | None:
    """A linha que a tela escolheu, ou `None`.

    O NOME não basta: a base real repete o nome nos trechos de uma derivação
    («LD VARZEA GRANDE - POCONE» até o TAP e do TAP em diante, 20 km e 66 km).
    Com os terminais, vale o trecho exato; sem eles, só um nome que não se
    repete — escolher «o primeiro» de dois seria trocar de linha calado.
    """
    alvo = str(nome or "").strip().upper()
    if not alvo:
        return None
    mesmos = [x for x in listar(base) if x.nome.upper() == alvo]
    s, r = (str(t or "").strip().upper() for t in (terminal_s, terminal_r))
    if s or r:
        mesmos = [x for x in mesmos
                  if (x.terminal_s.upper(), x.terminal_r.upper()) == (s, r)]
    return mesmos[0] if len(mesmos) == 1 else None
