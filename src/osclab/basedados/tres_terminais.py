"""As linhas de TRÊS TERMINAIS: uma derivação (TAP) no meio de uma linha.

Decidido com o Alexandre em 09/11/2026. Na distribuidora a derivação quase
sempre é um TAP que desce para um trafo, sem proteção de distância: a
oscilografia é lida como de DOIS terminais, A e B, e o TAP é informação — onde
ele está e o aviso de que a conta só vale com o primário do trafo em delta
(sem fonte de sequência zero) e sem geração no ponto.

O arquivo é `linhas/linhas-3t.csv`, AO LADO do `linhas.csv`, que este módulo
nunca toca — nenhum parâmetro se perde. A carga inicial vem da topologia do
OnLiner (script de montagem); depois, quem escreve é o programa: o usuário
marca qual ponta é A, B ou TAP, e cadastra à mão a derivação que o OnLiner não
deixou reconhecer. Uma linha por circuito, com as três PERNAS, cada uma do
ponto de junção até um terminal:

    codigo;nome;ponto;situacao;papeis;origem;nota;
    t1_nome;t1_barra;t1_papel;t1_km;t1_r1;t1_x1;t1_r0;t1_x0;  (e t2_, t3_)

`situacao`: `certo` (a topologia confirma) ou `conferir`. `papeis`:
`deduzido` (A e B pelo nome da linha, TAP a terceira) ou `marcado` (o usuário
escolheu). `origem`: `onliner` ou `manual`.

A conta da localização usa o CAMINHO A–B: a impedância é a soma das duas
pernas, e a conversão de impedância em km segue o PERFIL das pernas — com
condutores diferentes, tratar a linha como uniforme errava 3,3 km numa falta
em cima do TAP de Alto Boa Vista–Confresa.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, replace
from pathlib import Path

from osclab.basedados import linhas as linhas_mod

ARQUIVO = "linhas-3t.csv"
PAPEIS = ("A", "B", "TAP")
COLUNAS = ["codigo", "nome", "ponto", "situacao", "papeis", "origem", "nota"]
for _k in (1, 2, 3):
    COLUNAS += [f"t{_k}_nome", f"t{_k}_barra", f"t{_k}_papel", f"t{_k}_km",
                f"t{_k}_r1", f"t{_k}_x1", f"t{_k}_r0", f"t{_k}_x0"]

#: O aviso de toda linha com derivação. A conta trata o TAP como carga: vale
#: com o primário do trafo em delta (sem fonte de sequência zero) e sem
#: geração no ponto — o caso comum no parque, dito por ele em 09/11/2026.
AVISO_DO_TAP = ("linha com derivação em {tap} (a {km} km de A): tratada como dois "
                "terminais — vale com o primário do trafo do TAP em delta e sem "
                "geração no ponto")
AVISO_DE_TRECHOS = ("linha em {n} trechos sem confirmação de TAP no ponto do meio "
                    "({pontos}): somados como dois terminais; marque o TAP em "
                    "«parâmetros» se houver")


@dataclass(frozen=True)
class Perna:
    """Do ponto de junção até um terminal."""

    nome: str
    barra: str
    papel: str
    km: float | None
    r1: float | None
    x1: float | None
    r0: float | None
    x0: float | None


@dataclass(frozen=True)
class Circuito:
    codigo: str
    nome: str
    ponto: str
    situacao: str
    papeis: str
    origem: str
    nota: str
    pernas: tuple[Perna, Perna, Perna]

    def perna(self, papel: str) -> Perna | None:
        achadas = [p for p in self.pernas if p.papel == papel]
        return achadas[0] if len(achadas) == 1 else None

    @property
    def papeis_validos(self) -> bool:
        return sorted(p.papel for p in self.pernas) == sorted(PAPEIS)


def _caminho(base) -> Path:
    return base.gaveta(linhas_mod.PASTA) / ARQUIVO


def _num(texto) -> float | None:
    return linhas_mod._numero(texto) if str(texto or "").strip() else None


def _de_linha(cru: dict) -> Circuito:
    pernas = tuple(Perna(
        str(cru.get(f"t{k}_nome") or "").strip(), str(cru.get(f"t{k}_barra") or "").strip(),
        str(cru.get(f"t{k}_papel") or "").strip().upper(), _num(cru.get(f"t{k}_km")),
        _num(cru.get(f"t{k}_r1")), _num(cru.get(f"t{k}_x1")), _num(cru.get(f"t{k}_r0")),
        _num(cru.get(f"t{k}_x0"))) for k in (1, 2, 3))
    return Circuito(*(str(cru.get(c) or "").strip() for c in COLUNAS[:7]), pernas)


def _para_linha(c: Circuito) -> dict:
    saida = {"codigo": c.codigo, "nome": c.nome, "ponto": c.ponto, "situacao": c.situacao,
             "papeis": c.papeis, "origem": c.origem, "nota": c.nota}
    n = linhas_mod._texto_do_numero
    for k, p in enumerate(c.pernas, start=1):
        saida.update({f"t{k}_nome": p.nome, f"t{k}_barra": p.barra, f"t{k}_papel": p.papel,
                      f"t{k}_km": n(p.km), f"t{k}_r1": n(p.r1), f"t{k}_x1": n(p.x1),
                      f"t{k}_r0": n(p.r0), f"t{k}_x0": n(p.x0)})
    return saida


def listar(base) -> list[Circuito]:
    colunas, cruas = linhas_mod._cru(_caminho(base))
    return [_de_linha(r) for r in cruas if str(r.get("nome") or "").strip()]


def de_nome(base, nome: str) -> Circuito | None:
    alvo = str(nome or "").strip().upper()
    return next((c for c in listar(base) if c.nome.upper() == alvo), None)


def gravar(base, circuito: Circuito) -> Path:
    """Troca o circuito de mesmo nome, ou acrescenta. As outras linhas do
    arquivo — e colunas que o programa não conheça — ficam como estavam."""
    destino = _caminho(base)
    colunas, cruas = linhas_mod._cru(destino)
    colunas = colunas + [c for c in COLUNAS if c not in colunas]
    novo = _para_linha(circuito)
    for r in cruas:
        if str(r.get("nome") or "").strip().upper() == circuito.nome.upper():
            r.update(novo)
            break
    else:
        cruas.append(novo)
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, colunas, delimiter=";", lineterminator="\n",
                              extrasaction="ignore", restval="")
    escritor.writeheader()
    escritor.writerows(cruas)
    destino.write_text(saida.getvalue(), encoding="utf-8")
    return destino


def remover_manual(base, nome: str) -> bool:
    """Tira um circuito cadastrado À MÃO (e só esses: o que veio do OnLiner
    não some por um clique — volta a ser deduzido marcando os papéis)."""
    destino = _caminho(base)
    colunas, cruas = linhas_mod._cru(destino)
    alvo = str(nome or "").strip().upper()
    ficam = [r for r in cruas if not (str(r.get("nome") or "").strip().upper() == alvo
                                      and str(r.get("origem") or "") == "manual")]
    if len(ficam) == len(cruas):
        return False
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, colunas, delimiter=";", lineterminator="\n",
                              extrasaction="ignore", restval="")
    escritor.writeheader()
    escritor.writerows(ficam)
    destino.write_text(saida.getvalue(), encoding="utf-8")
    return True


def marcar(base, nome: str, papeis: list[str]) -> Circuito:
    """Grava os papéis que o usuário escolheu (um A, um B, um TAP)."""
    c = de_nome(base, nome)
    if c is None:
        raise ValueError(f"«{nome}» não é linha de três terminais")
    papeis = [str(p or "").strip().upper() for p in papeis]
    if sorted(papeis) != sorted(PAPEIS):
        raise ValueError("cada papel uma vez: um A, um B e um TAP")
    pernas = tuple(replace(p, papel=q) for p, q in zip(c.pernas, papeis, strict=True))
    novo = replace(c, papeis="marcado", pernas=pernas)
    gravar(base, novo)
    return novo


def _soma(valores) -> float | None:
    valores = list(valores)
    return None if any(v is None for v in valores) else sum(valores)


def _perfil(pedacos: list[tuple[float | None, float | None]]) -> list[list[float]] | None:
    """`[[km acumulado, fração acumulada de X1], ...]`, de A para B.

    Pela REATÂNCIA: é a grandeza que os métodos de impedância medem com menos
    influência da resistência de falta.
    """
    if any(km is None or x is None for km, x in pedacos):
        return None
    total = sum(x for _, x in pedacos)
    if not total:
        return None
    perfil, km_acum, x_acum = [[0.0, 0.0]], 0.0, 0.0
    for km, x in pedacos:
        km_acum += km
        x_acum += x
        perfil.append([km_acum, x_acum / total])
    return perfil


def _numero_curto(v: float | None) -> str:
    return "?" if v is None else f"{v:.1f}".replace(".", ",")


def caminho_de_circuito(c: Circuito) -> dict:
    """A linha que entra na conta (A–B), no formato das fontes da localização."""
    a, b, tap = c.perna("A"), c.perna("B"), c.perna("TAP")
    if a is None or b is None or tap is None:
        return {"ok": False, "motivo": f"«{c.nome}»: marque um A, um B e um TAP"}
    r, x, km = _soma((a.r1, b.r1)), _soma((a.x1, b.x1)), _soma((a.km, b.km))
    if r is None or x is None or not km:
        return {"ok": False, "motivo": f"«{c.nome}»: falta parâmetro numa perna A ou B"}
    saida = {"ok": True, "r": r, "x": x, "km": km, "como": c.nome,
             "terminais": [a.nome, b.nome], "escolhida": True,
             "perfil": _perfil([(a.km, a.x1), (b.km, b.x1)]),
             "tap": {"nome": tap.nome, "km_de_a": a.km, "km": tap.km},
             "aviso": AVISO_DO_TAP.format(tap=tap.nome, km=_numero_curto(a.km))}
    r0, x0 = _soma((a.r0, b.r0)), _soma((a.x0, b.x0))
    if r0 is not None and x0 is not None:
        saida.update(r0=r0, x0=x0)
    return saida


def trechos_de(base, nome: str) -> list[linhas_mod.Linha]:
    """Os trechos de uma linha, na ordem do arquivo (que é a de A para B)."""
    alvo = str(nome or "").strip().upper()
    return [x for x in linhas_mod.listar(base) if x.nome.upper() == alvo]


def caminho_de_trechos(trechos: list[linhas_mod.Linha]) -> dict:
    """Os trechos somados, quando não se confirmou TAP nenhum no meio."""
    if not trechos:
        return {"ok": False, "motivo": "linha sem trechos na base"}
    r = sum(t.r1_ohm for t in trechos)
    x = sum(t.x1_ohm for t in trechos)
    km = sum(t.comprimento_km for t in trechos)
    pontos = [t.terminal_r for t in trechos[:-1]]
    saida = {"ok": True, "r": r, "x": x, "km": km, "como": trechos[0].nome,
             "terminais": [trechos[0].terminal_s, trechos[-1].terminal_r],
             "escolhida": True,
             "perfil": _perfil([(t.comprimento_km, t.x1_ohm) for t in trechos]),
             "aviso": AVISO_DE_TRECHOS.format(n=len(trechos), pontos=", ".join(pontos))}
    r0, x0 = _soma(t.r0_ohm for t in trechos), _soma(t.x0_ohm for t in trechos)
    if r0 is not None and x0 is not None:
        saida.update(r0=r0, x0=x0)
    return saida


def cadastrar(base, nome: str, ponto: int, tap: str, tap_km: float | None = None) -> Circuito:
    """O TAP que o OnLiner não deixou reconhecer, marcado à mão.

    `ponto` é o índice da junção entre trechos (0 = entre o 1º e o 2º). As
    pernas A e B saem da soma dos trechos de cada lado — os mesmos números da
    base; a perna do TAP leva só o nome e, se ele souber, o comprimento.
    """
    trechos = trechos_de(base, nome)
    if len(trechos) < 2:
        raise ValueError("só uma linha com mais de um trecho tem ponto no meio")
    if not 0 <= ponto < len(trechos) - 1:
        raise ValueError("ponto fora da linha")
    if not str(tap or "").strip():
        raise ValueError("diga o nome do TAP")

    def perna(lado, nome_t, papel):
        return Perna(nome_t, "", papel, _soma(t.comprimento_km for t in lado),
                     _soma(t.r1_ohm for t in lado), _soma(t.x1_ohm for t in lado),
                     _soma(t.r0_ohm for t in lado), _soma(t.x0_ohm for t in lado))
    c = Circuito(trechos[0].codigo, trechos[0].nome, trechos[ponto].terminal_r, "certo",
                 "marcado", "manual", "cadastrado à mão no programa",
                 (perna(trechos[: ponto + 1], trechos[0].terminal_s, "A"),
                  perna(trechos[ponto + 1:], trechos[-1].terminal_r, "B"),
                  Perna(str(tap).strip(), "", "TAP", tap_km, None, None, None, None)))
    gravar(base, c)
    return c


def resumo(base) -> dict:
    """Quantas linhas de três terminais, a conferir, e com trechos sem TAP
    confirmado — o aviso que a tela mostra."""
    circuitos = {c.nome.upper(): c for c in listar(base)}
    por_nome: dict[str, int] = {}
    for x in linhas_mod.listar(base):
        por_nome[x.nome.upper()] = por_nome.get(x.nome.upper(), 0) + 1
    sem = [n for n, k in por_nome.items() if k > 1 and n not in circuitos]
    return {"tres_terminais": len(circuitos),
            "conferir": sum(c.situacao != "certo" for c in circuitos.values()),
            "marcar": sum(not c.papeis_validos for c in circuitos.values()),
            "trechos_sem_tap": len(sem)}
