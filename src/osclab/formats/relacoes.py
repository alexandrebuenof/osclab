"""A relação de TC/TP que o USUÁRIO digitou, por grupo e por canal.

## Por que existe

Sem relação declarada, não se converte — e isso aparece (ver
`plot/conversao.py`). Mas quem analisa às vezes SABE a relação que o arquivo
não diz: está no unifilar, na placa do TC, no ajuste do relé. O leitor é
universal (CLAUDE.md): o que o arquivo não disser vira campo para digitar,
nunca barreira.

## Onde a relação mora

A relação é do CANAL, não da conta nem da tela. Digitada uma vez, ela vale em
tudo que usa aquele registro — primário × secundário nos gráficos, tabelinha,
base do pu do fasorial, calculadora, localização de falta. Por isso ela é
aplicada no `Record` logo depois do leitor (`acervo._com_vinculos`), como a
correção de fase: quem lê `canal.primary` e `canal.secondary` já recebe o
número digitado, e nenhum consumidor precisa saber que ele existe.

Fica gravada num arquivo ao lado do registro (`paths.relacoes_do_registro`),
nunca no `meta.json` (que é cache) e nunca em outro registro.

## Grupo e canal

Digita-se por GRUPO (a trinca `G1`, chave estável = o nome do conjunto, como
em `trincas.json`): vale para as três fases. Vale também para o resíduo
medido do mesmo vão (o `N` do conjunto ou o residual pendurado nele) **só
quando o arquivo não declara a dele** — o neutro costuma ser um toroide com
outra relação, e trocar uma relação declarada por palpite de grupo seria o
programa decidindo pelo usuário. Por cima do grupo, a relação de um CANAL
vence: é a correção fina.

## A escolha do usuário vence o arquivo

Como no vínculo de fase: ele olhou a placa; o `.cfg` pode ter sido
parametrizado errado. Vazio apaga, e volta a valer o arquivo (ou nada).
"""

from __future__ import annotations

import math
import re
from dataclasses import replace

from osclab.formats.base import Record

#: Como a origem aparece na tela.
DIGITADO = "digitado"
LIDO = "lido do arquivo"
NENHUMA = ""

_NUMERO = r"\d+(?:[.,]\d+)?"
_PAR = re.compile(rf"^\s*({_NUMERO})\s*(?:[:/]\s*({_NUMERO}))?\s*$")


def ler_texto(texto) -> tuple[float, float] | None:
    """`"600/5"`, `"600:5"`, `"13800 / 115"`, `"120"` → `(primário, secundário)`.

    Um número só é a RELAÇÃO (`120` → `(120, 1)`). Vírgula decimal vale.
    Zero, negativo ou texto que não é número devolve `None` — quem chama trata
    como "apagar".
    """
    if isinstance(texto, (int, float)) and not isinstance(texto, bool):
        texto = str(texto)
    achado = _PAR.match(str(texto or ""))
    if not achado:
        return None
    p = float(achado.group(1).replace(",", "."))
    s = float(achado.group(2).replace(",", ".")) if achado.group(2) else 1.0
    if not (math.isfinite(p) and math.isfinite(s)) or p <= 0 or s <= 0:
        return None
    return p, s


def _numero(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def como_texto(par) -> str:
    """`(600, 5)` → `"600:5"`; `(120, 1)` → `"120"`. Vazio sem par."""
    if not par:
        return ""
    p, s = par
    return _numero(p) if s == 1 else f"{_numero(p)}:{_numero(s)}"


def limpar(cru) -> dict:
    """`{"grupos": {chave: (p, s)}, "canais": {indice: (p, s)}}` a partir do
    JSON gravado ou do pedido da tela. O que não se lê some."""
    saida: dict = {"grupos": {}, "canais": {}}
    if not isinstance(cru, dict):
        return saida
    for chave, valor in (cru.get("grupos") or {}).items():
        par = _par_de(valor)
        if par and str(chave).strip():
            saida["grupos"][str(chave)] = par
    for chave, valor in (cru.get("canais") or {}).items():
        try:
            indice = int(chave)
        except (TypeError, ValueError):
            continue
        par = _par_de(valor)
        if par and indice >= 0:
            saida["canais"][indice] = par
    return saida


def _par_de(valor):
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        try:
            p, s = float(valor[0]), float(valor[1])
        except (TypeError, ValueError):
            return None
        return (p, s) if p > 0 and s > 0 and math.isfinite(p / s) else None
    return ler_texto(valor)


def declarada_no_arquivo(canal) -> bool:
    """O arquivo declara uma relação de verdade? `p == s` (o 1:1 que o
    COMTRADE escreve por falta de relação) e zero não contam."""
    p, s = float(canal.primary or 0.0), float(canal.secondary or 0.0)
    return p > 0 and s > 0 and p != s


def _alvos(registro: Record, digitadas: dict) -> dict[int, tuple[float, float]]:
    """Canal → relação digitada que vale para ele: grupo, depois canal."""
    alvos: dict[int, tuple[float, float]] = {}
    grupos = digitadas.get("grupos") or {}
    if grupos:
        from osclab.formats import conjuntos

        lista = conjuntos.de_registro(registro)
        pendurados = conjuntos.residuais_soltos(registro)
        canais = {c.index: c for c in registro.analog_channels}
        for posicao, conj in enumerate(lista):
            par = grupos.get(conj.nome)
            if not par:
                continue
            for indice in conj.abc:
                alvos[indice] = par
            residuos = [conj.canais["N"]] if "N" in conj.canais else []
            residuos += [i for i, p in pendurados.items() if p == posicao]
            for indice in residuos:
                c = canais.get(indice)
                if c is not None and not declarada_no_arquivo(c):
                    alvos[indice] = par
    alvos.update(digitadas.get("canais") or {})
    return alvos


def aplicar(registro: Record, digitadas: dict) -> Record:
    """Põe as relações digitadas (já limpas: ver `limpar`) nos canais.

    O canal guarda a do arquivo em `relacao_do_arquivo`, para a tela poder
    dizer o que foi trocado pelo quê. Devolve o registro.
    """
    limpas = {"grupos": dict((digitadas or {}).get("grupos") or {}),
              "canais": dict((digitadas or {}).get("canais") or {})}
    registro.relacoes_digitadas = limpas
    alvos = _alvos(registro, limpas)
    if not alvos:
        return registro
    registro.analog_channels = tuple(
        replace(c, primary=alvos[c.index][0], secondary=alvos[c.index][1],
                relacao_digitada=True,
                relacao_do_arquivo=(float(c.primary or 0.0), float(c.secondary or 0.0)))
        if c.index in alvos else c
        for c in registro.analog_channels
    )
    return registro


def para_json(digitadas: dict) -> dict:
    """O formato gravado: `{"grupos": {"I*W": [600, 5]}, "canais": {"3": [120, 1]}}`."""
    saida: dict = {}
    if digitadas.get("grupos"):
        saida["grupos"] = {k: list(v) for k, v in sorted(digitadas["grupos"].items())}
    if digitadas.get("canais"):
        saida["canais"] = {str(k): list(v) for k, v in sorted(digitadas["canais"].items())}
    return saida


def resumo(registro: Record) -> dict:
    """O que a tela precisa para mostrar e editar: por canal e por grupo.

    Por canal: a relação EM USO, a origem dela (digitado ou lido do arquivo),
    a do arquivo e a que foi digitada NO CANAL (a do grupo não conta aqui: é
    a que se edita na linha do grupo).
    """
    digitadas = getattr(registro, "relacoes_digitadas", None) or {}
    no_canal = digitadas.get("canais") or {}
    canais = {}
    for c in registro.analog_channels:
        digitada = bool(getattr(c, "relacao_digitada", False))
        do_arquivo = (getattr(c, "relacao_do_arquivo", ()) if digitada
                      else (float(c.primary or 0.0), float(c.secondary or 0.0)))
        arquivo_vale = (len(do_arquivo) == 2 and do_arquivo[0] > 0
                        and do_arquivo[1] > 0 and do_arquivo[0] != do_arquivo[1])
        em_uso = ((c.primary, c.secondary) if digitada
                  else (do_arquivo if arquivo_vale else None))
        canais[str(c.index)] = {
            "em_uso": como_texto(em_uso),
            "origem": DIGITADO if digitada else (LIDO if arquivo_vale else NENHUMA),
            "do_arquivo": como_texto(do_arquivo) if arquivo_vale else "",
            "no_canal": como_texto(no_canal.get(c.index)),
        }
    grupos = {k: como_texto(v) for k, v in (digitadas.get("grupos") or {}).items()}
    return {"canais": canais, "grupos": grupos}
