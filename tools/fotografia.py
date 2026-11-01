"""Fotografia de um banco de oscilografias, para pegar mudança SILENCIOSA.

Uso:

    python tools/fotografia.py tirar  PASTA  SAIDA.jsonl
    python tools/fotografia.py comparar ANTES.jsonl DEPOIS.jsonl

`tirar` lê cada oscilografia da pasta (um `.cfg` com `.dat` ao lado, um
`.cff` ou um `.CEV`) e grava, por registro, o que o programa CONCLUI dele: o
formato, a taxa, a hora, a fase deduzida de cada canal, as trincas, o tipo
(inicial e final) e o instante da falta, a sigla que o RELÉ escreveu e se ela
concorda com a nossa, e o disparo do relé. `comparar` lista, campo por campo, o
que mudou entre duas fotos.

## Tipo inicial e final

O relé grava UMA sigla, quase sempre a do começo da falta; a nossa, numa
evolutiva, termina noutra (`AG → ABC`). Comparando só o final, toda evolutiva
parecia discordância. Por isso a foto guarda os dois, e `concorda` usa a mesma
regra da tela (`falta.rele_concorda`). Separados, eles também separam os
alarmes: o `inicial` mudar é o classificador lendo outra falta; só o `tipo`
mudar é a regra da evolução que mexeu.

Campo que a foto ANTIGA não tinha não conta como mudança — é «sem
informação», e some na foto seguinte. A exceção é o registro que passou a dar
erro (ou deixou de dar): aí a foto inteira é outra, e tudo conta.

## Por que existe

Os defeitos mais caros deste projeto não deram erro: deram número plausível.
Uma trinca que deixa de fechar, uma fase lida como neutro, uma data trocada —
o programa continua abrindo e desenhando. A foto do banco antes e depois de
uma mudança mostra TUDO que ela mexeu, e cada diferença tem de ter
explicação: ou é o conserto que se queria, ou é estrago.

**A foto tem dado real (nome de SE, data do evento): fica fora do git**, em
`docs-privados/`. Este script não tem dado nenhum e vai no repositório.
"""

from __future__ import annotations

import gc
import json
import sys
from pathlib import Path

PRINCIPAIS = (".cfg", ".cff", ".cev")


def _e_oscilografia(caminho: Path) -> bool:
    """Um `.cfg` só é COMTRADE com o `.dat` irmão (ver o comissionamento)."""
    if caminho.suffix.lower() != ".cfg":
        return True
    return any(caminho.with_suffix(e).is_file() for e in (".dat", ".DAT", ".Dat"))


def arquivos(pasta: Path) -> list[Path]:
    return sorted(p for p in pasta.rglob("*")
                  if p.suffix.lower() in PRINCIPAIS and p.is_file() and _e_oscilografia(p))


def foto_de(caminho: Path) -> dict:
    """O que o programa conclui de UM registro. Nunca levanta."""
    from osclab.analysis import falta
    from osclab.formats import conjuntos, fases, registry

    try:
        r = registry.read(caminho)
    except Exception as exc:          # o próprio «não abre» é parte da foto
        return {"erro": f"{type(exc).__name__}: {str(exc)[:120]}"}
    vivos = [c for c in conjuntos.de_registro(r) if not c.sem_sinal]
    ci = next((c.canais for c in vivos if c.grandeza == "I" and not c.e_de_linha), None)
    cv = next((c.canais for c in vivos if c.grandeza == "V" and not c.e_de_linha), None)
    v = falta.classificar(r, ci, cv) if ci else None
    d = falta.disparo_do_rele(r)
    rele = sigla_do_rele(caminho, r)
    return {
        "formato": r.format_name,
        "amostras": int(r.n_samples),
        "taxas": [round(t.taxa_hz, 3) for t in r.trechos],
        "inicio": str(r.start_time),
        "fases": [fases.da_canal(c)[0] for c in r.analog_channels],
        "trincas": sorted([c.grandeza, c.nome, sorted(c.canais.items())]
                          for c in conjuntos.de_registro(r)),
        "falta": None if v is None else {"tipo": v.tipo, "inicial": v.tipo_inicial or v.tipo,
                                         "instante": v.instante, "fim": v.fim},
        "rele": rele,
        # Sem falta nossa, ou sem TIPO do relé (vazio, `TRIP`, `ER`): None.
        "concorda": (None if v is None or not v.tipo or not falta.e_tipo_de_falta(rele)
                     else falta.rele_concorda(v.tipo, v.tipo_inicial, rele)),
        "disparo": None if d is None else [d.sinal, d.amostra],
    }


def sigla_do_rele(caminho: Path, registro) -> str:
    """A sigla que o relé escreveu: no `.CEV` vem no cabeçalho; no COMTRADE,
    no `.hdr` irmão — o mesmo caminho do acervo (`acervo._resumir`)."""
    from osclab.formats import ajustes

    if registro.classificacao_do_rele:
        return registro.classificacao_do_rele.strip()
    raiz = caminho.stem.lower()
    irmaos = [p.name for p in caminho.parent.iterdir()
              if p.stem.lower() == raiz and p.suffix.lower() == ".hdr"]
    return ajustes.classificacao_no_hdr(caminho.parent, irmaos)


def tirar(pasta: Path, saida: Path) -> int:
    lista = arquivos(pasta)
    with open(saida, "w", encoding="utf-8") as out:
        for i, caminho in enumerate(lista, 1):
            linha = {"arquivo": str(caminho.relative_to(pasta)), **foto_de(caminho)}
            out.write(json.dumps(linha, ensure_ascii=False) + "\n")
            out.flush()                      # interrompido, o que já foi fica
            gc.collect()                     # 5760 digitais por 487E: memória
            print(f"\r{i}/{len(lista)}", end="", file=sys.stderr)
    print(file=sys.stderr)
    return len(lista)


def carregar(caminho: Path) -> dict[str, dict]:
    return {j["arquivo"]: j for j in
            map(json.loads, Path(caminho).read_text(encoding="utf-8").splitlines())}


def comparar(antes: dict[str, dict],
             depois: dict[str, dict]) -> list[tuple[str, str, object, object]]:
    """`(arquivo, campo, antes, depois)` de toda diferença, inclusive registro
    que apareceu ou sumiu."""
    saida = []
    for arquivo in sorted(set(antes) | set(depois)):
        a, d = antes.get(arquivo), depois.get(arquivo)
        if a is None or d is None:
            saida.append((arquivo, "registro", a is not None, d is not None))
            continue
        # Registro que passou a dar erro (ou deixou de dar): a foto inteira é
        # outra, e todo campo que sumiu ou apareceu é mudança de verdade.
        com_erro = "erro" in a or "erro" in d
        saida.extend((arquivo, *dif) for dif in _diferencas(a, d, "", com_erro))
    return saida


def _diferencas(a: dict, d: dict, prefixo: str, com_erro: bool):
    """`(campo, antes, depois)`; dicionário dentro de dicionário é comparado
    chave a chave (`falta.tipo`, `falta.inicial`), para o alarme dizer QUAL
    parte mudou."""
    for campo in sorted(set(a) | set(d)):
        nome = prefixo + campo
        if (campo not in a or campo not in d) and not com_erro:
            continue                  # a foto antiga não tinha este campo
        va, vd = a.get(campo), d.get(campo)
        if isinstance(va, dict) and isinstance(vd, dict):
            yield from _diferencas(va, vd, nome + ".", com_erro)
        elif va != vd:
            yield nome, va, vd


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "tirar":
        n = tirar(Path(argv[1]), Path(argv[2]))
        print(f"{n} registros fotografados em {argv[2]}")
        foto = carregar(Path(argv[2])).values()
        sim = sum(1 for j in foto if j.get("concorda") is True)
        nao = sum(1 for j in foto if j.get("concorda") is False)
        print(f"sigla do relé: {sim} concordam, {nao} discordam, "
              f"{n - sim - nao} sem sigla ou sem falta para comparar")
        return 0
    if len(argv) == 3 and argv[0] == "comparar":
        dif = comparar(carregar(Path(argv[1])), carregar(Path(argv[2])))
        por_campo: dict[str, int] = {}
        for _, campo, _, _ in dif:
            por_campo[campo] = por_campo.get(campo, 0) + 1
        print(f"{len(dif)} diferença(s): {por_campo or 'nenhuma'}")
        for arquivo, campo, a, d in dif[:40]:
            print(f"  {campo:8s} {arquivo[-60:]}\n           antes:  {str(a)[:150]}\n"
                  f"           depois: {str(d)[:150]}")
        return 1 if dif else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
