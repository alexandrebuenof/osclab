"""Comissionamento em massa: o banco inteiro contra o gabarito do próprio relé.

Uso:

    python tools/comissionar.py tirar    PASTA SAIDA.csv [--ignorar PADRAO ...]
    python tools/comissionar.py comparar ANTES.csv DEPOIS.csv [--folga 0.2]

`tirar` roda as conferências de `tests/conferencias.py` — as MESMAS do
`tests/test_comissionamento.py` — sobre cada oscilografia da pasta (um `.cfg`
com `.dat` ao lado, um `.cff` ou um `.CEV`) e grava uma linha por coisa
conferida: registro, conferência, item, valor do relé, valor nosso, erro,
tolerância, veredito (`confere`, `diverge`, `não se aplica`, `erro`) e motivo.
Depois casa os registros do mesmo disparo em dois formatos e confere os pares.

`comparar` lista o que PIOROU entre duas rodadas — conferia e passou a
divergir, abria e deixou de abrir, ou o erro cresceu além da folga —
separado do que melhorou e do que só mudou de aplicabilidade. Sai com código
1 quando algo piorou.

## Um processo por registro

Um SEL-487E tem 5760 digitais e a matriz de estados passa de dezenas de MB; o
coletor de lixo do Python não devolve isso ao sistema a tempo de quinhentos
registros seguidos. Cada registro roda num processo próprio, e um registro que
derruba o processo (ou estoura o tempo) vira uma linha `erro` — o placar dos
outros continua. Cada linha é gravada com `flush`: interrompido, o que já foi
fica.

## O placar tem dado real

Nome de subestação, de equipamento, data do evento. Fica em `docs-privados/`,
fora do git. Este script não tem dado nenhum e vai no repositório.
"""

from __future__ import annotations

import csv
import fnmatch
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PRINCIPAIS = (".cfg", ".cff", ".cev")
COLUNAS = ("registro", "equipamento", "conferencia", "item", "rele", "nosso", "erro",
           "unidade", "tolerancia", "veredito", "motivo")
LEITURA = "0 leitura"
TEMPO_MAXIMO = 900          # s por registro

#: O erro só «cresceu» se passou do anterior por mais que isto, relativo…
FOLGA_RELATIVA = 0.2
#: …e por mais que isto, na unidade da conferência (%, °, amostras).
FOLGA_ABSOLUTA = 0.05


def _e_oscilografia(caminho: Path) -> bool:
    """Um `.cfg` só é COMTRADE com o `.dat` irmão (ver o comissionamento)."""
    if caminho.suffix.lower() != ".cfg":
        return True
    return any(caminho.with_suffix(e).is_file() for e in (".dat", ".DAT", ".Dat"))


def arquivos(pasta: Path) -> list[Path]:
    return sorted(p for p in pasta.rglob("*")
                  if p.suffix.lower() in PRINCIPAIS and p.is_file() and _e_oscilografia(p))


# ---------------------------------------------------------------------------
# O que roda DENTRO do processo de um registro
# ---------------------------------------------------------------------------

def _caminho_do_pacote() -> None:
    for pasta in (RAIZ / "src", RAIZ):
        if str(pasta) not in sys.path:
            sys.path.insert(0, str(pasta))


def conferir_um(caminho: Path) -> dict:
    """As conferências de UM registro, e a chave para casá-lo com o par.
    Nunca levanta: o próprio «não abre» é linha do placar."""
    _caminho_do_pacote()
    from osclab.formats import registry
    from tests import conferencias as C

    try:
        registro = registry.read(caminho)
    except Exception as exc:
        return {"equipamento": "", "evento": None, "linhas": [C.Linha(
            LEITURA, veredito=C.ERRO,
            motivo=f"não abre: {type(exc).__name__}: {str(exc)[:200]}").como_dict()]}
    leitura = C.Linha(LEITURA, veredito=C.CONFERE, motivo=(
        f"{registro.format_name}; {len(registro.analog_channels)} A / "
        f"{len(registro.status_channels)} D; {registro.n_samples} amostras"))
    linhas = [leitura, *C.todas(caminho, registro)]
    return {"equipamento": (registro.device_id or "").strip(),
            "evento": C.chave_de_evento(registro),
            "linhas": [x.como_dict() for x in linhas]}


def conferir_par(a: Path, b: Path) -> dict:
    _caminho_do_pacote()
    from osclab.formats import registry
    from tests import conferencias as C

    try:
        linhas = C.mesmo_evento(registry.read(a), registry.read(b))
    except Exception as exc:
        linhas = [C.Linha(C.MESMO_EVENTO, veredito=C.ERRO,
                          motivo=f"{type(exc).__name__}: {str(exc)[:200]}")]
    return {"linhas": [x.como_dict() for x in linhas]}


# ---------------------------------------------------------------------------
# O processo que coordena
# ---------------------------------------------------------------------------

def _filho(*argumentos: str) -> dict:
    """Roda este script num processo novo e devolve o JSON que ele imprime."""
    ambiente = dict(os.environ, PYTHONIOENCODING="utf-8",
                    PYTHONPATH=os.pathsep.join([str(RAIZ / "src"), str(RAIZ)]))
    try:
        r = subprocess.run([sys.executable, "-W", "ignore", __file__, *argumentos],
                           env=ambiente, stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=TEMPO_MAXIMO)
    except subprocess.TimeoutExpired:
        return {"falha": f"passou de {TEMPO_MAXIMO} s"}
    if r.returncode != 0:
        cauda = r.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["?"]
        return {"falha": f"processo saiu com {r.returncode}: {cauda[0][:200]}"}
    try:
        return json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"falha": "o processo não devolveu resultado"}


def _escrever(escritor, saida, registro: str, equipamento: str, linhas) -> None:
    for x in linhas:
        escritor.writerow({"registro": registro, "equipamento": equipamento,
                           **{k: ("" if x.get(k) is None else x.get(k))
                              for k in COLUNAS[2:]}})
    saida.flush()


def _linha_de_falha(conferencia: str, motivo: str) -> dict:
    return {"conferencia": conferencia, "veredito": "erro", "motivo": motivo}


def tirar(pasta: Path, destino: Path, ignorar: tuple[str, ...] = (),
          avisar=print) -> int:
    lista = arquivos(pasta)
    eventos: dict[str, dict] = {}
    inicio = time.time()
    with open(destino, "w", encoding="utf-8-sig", newline="") as saida:
        escritor = csv.DictWriter(saida, COLUNAS, delimiter=";")
        escritor.writeheader()
        for i, caminho in enumerate(lista, 1):
            nome = str(caminho.relative_to(pasta))
            padrao = next((p for p in ignorar if fnmatch.fnmatch(nome.upper(), p.upper())),
                          None)
            if padrao is not None:
                _escrever(escritor, saida, nome, "", [{
                    "conferencia": LEITURA, "veredito": "não se aplica",
                    "motivo": f"ignorado (--ignorar {padrao}); não foi lido"}])
                continue
            resultado = _filho("_um", str(caminho))
            if "falha" in resultado:
                resultado = {"linhas": [_linha_de_falha(LEITURA, resultado["falha"])]}
            _escrever(escritor, saida, nome, resultado.get("equipamento", ""),
                      resultado["linhas"])
            if resultado.get("evento"):
                eventos[nome] = resultado["evento"]
            avisar(f"\r{i}/{len(lista)} {time.time() - inicio:.0f} s", end="",
                   file=sys.stderr)
        avisar(file=sys.stderr)

        _caminho_do_pacote()
        from tests import conferencias as C

        for a, b in C.pares_do_mesmo_evento(eventos):
            resultado = _filho("_par", str(pasta / a), str(pasta / b))
            if "falha" in resultado:
                resultado = {"linhas": [_linha_de_falha(C.MESMO_EVENTO,
                                                        resultado["falha"])]}
            _escrever(escritor, saida, f"{a} | {b}", "", resultado["linhas"])
    return len(lista)


# ---------------------------------------------------------------------------
# Comparar duas rodadas
# ---------------------------------------------------------------------------

def carregar(caminho: Path) -> dict[tuple, dict]:
    """`{(registro, conferência, item): linha}`. Item repetido ganha um número
    para não engolir a linha anterior."""
    saida: dict[tuple, dict] = {}
    with open(caminho, encoding="utf-8-sig", newline="") as fh:
        for linha in csv.DictReader(fh, delimiter=";"):
            chave = (linha["registro"], linha["conferencia"], linha["item"])
            n = 1
            while chave in saida:
                n += 1
                chave = (linha["registro"], linha["conferencia"], f"{linha['item']} #{n}")
            saida[chave] = linha
    return saida


def _erro(linha: dict) -> float | None:
    try:
        return abs(float(linha["erro"]))
    except (TypeError, ValueError, KeyError):
        return None


def comparar(antes: dict[tuple, dict], depois: dict[tuple, dict],
             folga: float = FOLGA_RELATIVA) -> dict[str, list]:
    """`{"piorou": [...], "melhorou": [...], "mudou": [...]}`, cada item
    `(chave, antes, depois, porquê)`.

    Piorou: deixou de conferir (passou a divergir ou a dar erro), ou o erro
    cresceu mais que a folga. Melhorou: o contrário. Mudou: linha que apareceu,
    sumiu ou passou a (ou deixou de) se aplicar — não é regressão por si. Mas
    uma linha que CONFERIA e passou a «não se aplica», ou sumiu, é conferência
    que se perdeu, e por isso vai para «piorou».
    """
    bons = {"confere"}
    ruins = {"diverge", "erro"}
    saida: dict[str, list] = {"piorou": [], "melhorou": [], "mudou": []}
    for chave in sorted(set(antes) | set(depois)):
        a, d = antes.get(chave), depois.get(chave)
        if a is None or d is None:
            if d is None and a["veredito"] in bons:
                # conferia e a linha sumiu: é conferência perdida, não detalhe
                saida["piorou"].append((chave, a["veredito"], None, "conferia e sumiu"))
            elif a is None and d["veredito"] in ruins:
                saida["piorou"].append((chave, None, d["veredito"], "apareceu falhando"))
            else:
                saida["mudou"].append((chave, a and a["veredito"], d and d["veredito"],
                                       "apareceu" if a is None else "sumiu"))
            continue
        va, vd = a["veredito"], d["veredito"]
        if va != vd:
            if va in bons:
                saida["piorou"].append((chave, va, vd, "deixou de conferir"))
            elif vd in bons:
                saida["melhorou"].append((chave, va, vd, "passou a conferir"))
            elif vd in ruins and va not in ruins:
                saida["piorou"].append((chave, va, vd, "passou a falhar"))
            else:
                # divergia e deixou de se aplicar, ou trocou um tipo de falha
                # pelo outro: não é conserto nem estrago, é critério — e quem
                # decide é quem lê o motivo.
                saida["mudou"].append((chave, va, vd, "mudou de aplicabilidade"))
            continue
        ea, ed = _erro(a), _erro(d)
        if ea is None or ed is None:
            continue
        limite = max(folga * ea, FOLGA_ABSOLUTA)
        if ed - ea > limite:
            saida["piorou"].append((chave, a["erro"], d["erro"],
                                    f"erro cresceu ({a['unidade']})"))
        elif ea - ed > limite:
            saida["melhorou"].append((chave, a["erro"], d["erro"],
                                      f"erro diminuiu ({a['unidade']})"))
    return saida


def placar(linhas: dict[tuple, dict]) -> dict[str, dict[str, int]]:
    """`{conferência: {veredito: quantas}}`."""
    saida: dict[str, dict[str, int]] = {}
    for (_, conferencia, _), linha in linhas.items():
        por = saida.setdefault(conferencia, {})
        por[linha["veredito"]] = por.get(linha["veredito"], 0) + 1
    return dict(sorted(saida.items()))


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "_um":
        print(json.dumps(conferir_um(Path(argv[1])), ensure_ascii=False))
        return 0
    if len(argv) == 3 and argv[0] == "_par":
        print(json.dumps(conferir_par(Path(argv[1]), Path(argv[2])), ensure_ascii=False))
        return 0
    if len(argv) >= 3 and argv[0] == "tirar":
        resto = argv[3:]
        ignorar = tuple(resto[i + 1] for i, x in enumerate(resto[:-1]) if x == "--ignorar")
        n = tirar(Path(argv[1]), Path(argv[2]), ignorar)
        for conferencia, por in placar(carregar(Path(argv[2]))).items():
            print(f"  {conferencia:44s} {por}")
        print(f"{n} registros conferidos em {argv[2]}")
        return 0
    if len(argv) >= 3 and argv[0] == "comparar":
        folga = float(argv[4]) if len(argv) == 5 and argv[3] == "--folga" else FOLGA_RELATIVA
        dif = comparar(carregar(Path(argv[1])), carregar(Path(argv[2])), folga)
        for grupo in ("piorou", "melhorou", "mudou"):
            print(f"{grupo}: {len(dif[grupo])}")
            for (registro, conferencia, item), a, d, porque in dif[grupo][:60]:
                print(f"  {conferencia} · {item} · {registro[-70:]}\n"
                      f"      {a} → {d}  ({porque})")
        return 1 if dif["piorou"] else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
