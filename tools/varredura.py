"""Caça a bugs: cada registro de uma pasta passa por TODAS as rotas da tela.

Uso:

    python tools/varredura.py PASTA SAIDA.jsonl [--lote 40] [--sem TWFL] [--sem OUTRO]

Cada registro é enviado a um acervo TEMPORÁRIO e pedido como a tela pede: a
janela (padrão, primário, secundário, filtro de 60 Hz, estimador cosseno,
ampliada, andando), um arranjo com TODOS os tipos de painel, a leitura dos
dois cursores, a calculadora (contas que valem e que não valem), a
localização de falta (automática e digitada de quatro jeitos), a lógica, o
dicionário e a exportação. Cada achado vira uma linha do JSONL:

    exceção          a rota levantou — o servidor devolveria 500
    HTTP 4xx/5xx     resposta de erro onde não devia
    JSON inválido    NaN ou Infinity no pacote: o navegador recusa e a tela fica em branco
    painel com erro  o pacote veio, mas um painel diz que não conseguiu
    lento            mais de 5 s numa rota
    não aceito       o acervo recusou o arquivo (o motivo vai junto)

## Por que existe

Os testes sintéticos provam a matemática; o banco de oscilografias prova que
o programa ABRE o que o parque grava. Esta varredura achou, na primeira vez
(01/11/2026), um `.CEV` vazio recusado com a mensagem errada e o SEL-TWFL
levando minutos por rota — e confirmou zero exceção nos outros 549 registros.

## Cuidados

- O acervo, o cache e a escolha da base vão para uma pasta temporária
  (`OSCLAB_DATA_DIR`): **o acervo de verdade não é tocado**. A base de dados
  ativa da máquina é só LIDA (a localização procura linha nela).
- `--lote N` roda N registros por processo: um processo só para o banco
  inteiro esgotou a memória da máquina. Cada lote devolve a memória ao sair.
- O JSONL tem caminho de arquivo real: grave-o fora do git (`docs-privados/`).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EXTENSOES = {".cfg", ".cev"}
LENTO_S = 5.0


def principais(pasta: Path, sem: list[str]):
    for p in sorted(pasta.rglob("*")):
        if any(s.upper() in str(p).upper() for s in sem):
            continue
        if p.is_file() and p.suffix.lower() in EXTENSOES:
            yield p


def _json_estrito(texto: str):
    def recusa(c):
        raise ValueError(f"constante {c} no JSON")

    return json.loads(texto, parse_constant=recusa)


class Varredura:
    def __init__(self):
        from osclab.web.server import create_app

        app = create_app()
        app.testing = True
        self.c = app.test_client()
        self.achados: list[dict] = []

    def anotar(self, arquivo, rota, tipo, **mais):
        self.achados.append({"arquivo": arquivo, "rota": rota, "tipo": tipo, **mais})

    def pedir(self, arquivo, rotulo, metodo, url, **kw):
        t0 = time.perf_counter()
        try:
            r = getattr(self.c, metodo)(url, **kw)
        except Exception as exc:
            self.anotar(
                arquivo,
                rotulo,
                "exceção",
                erro=f"{type(exc).__name__}: {exc}"[:300],
                onde=traceback.format_exc().splitlines()[-3:],
            )
            return None
        dt = time.perf_counter() - t0
        if dt > LENTO_S:
            self.anotar(arquivo, rotulo, "lento", s=round(dt, 1))
        if not (r.is_json or (r.mimetype or "").startswith("text/")):
            # Arquivo (a exportação devolve um .zip): só o status interessa.
            if r.status_code >= 400:
                self.anotar(arquivo, rotulo, f"HTTP {r.status_code}")
            return {}
        texto = r.get_data(as_text=True)
        if r.status_code >= 500:
            self.anotar(arquivo, rotulo, f"HTTP {r.status_code}", erro=texto[:300])
            return None
        try:
            dado = _json_estrito(texto) if r.is_json or texto[:1] in "{[" else None
        except ValueError as exc:
            self.anotar(arquivo, rotulo, "JSON inválido", erro=str(exc)[:200])
            return None
        if r.status_code >= 400:
            self.anotar(arquivo, rotulo, f"HTTP {r.status_code}", erro=texto[:300])
        return dado

    def registro(self, principal: Path) -> None:
        nome = str(principal)
        irmaos = [
            p
            for p in principal.parent.iterdir()
            if p.is_file() and p.stem.lower() == principal.stem.lower()
        ]
        # O conteúdo em memória: nenhum arquivo do banco fica aberto se a rota
        # levantar no meio do envio.
        enviados = [(io.BytesIO(p.read_bytes()), p.name) for p in irmaos]
        env = self.pedir(
            nome,
            "enviar",
            "post",
            "/api/acervo",
            data={"arquivos": enviados},
            content_type="multipart/form-data",
        )
        if not env:
            return
        itens = env.get("aceitos") or env.get("repetidos") or []
        if not itens:
            self.anotar(
                nome,
                "enviar",
                "não aceito",
                erro=json.dumps(env.get("problemas"), ensure_ascii=False)[:300],
            )
            return
        sha = itens[0].get("sha256") or itens[0].get("sha")
        base = f"/api/onda/{sha}"

        j = self.pedir(nome, "janela padrão", "get", base + "?colunas=900")
        if not j:
            return
        inicio, fim = j.get("de"), j.get("ate")
        for rot, q in (
            ("primário", "lado=primario"),
            ("secundário", "lado=secundario"),
            ("filtro 60Hz", "filtro=1"),
            ("estimador cosseno", "estimador=cosseno"),
        ):
            self.pedir(nome, f"janela {rot}", "get", f"{base}?colunas=900&{q}")
        if inicio is not None and fim is not None:
            meio = (inicio + fim) / 2
            self.pedir(
                nome, "janela ampliada", "get", f"{base}?colunas=900&zoom=0.02&foco={meio}"
            )
            self.pedir(
                nome,
                "janela andando",
                "get",
                f"{base}?colunas=900&de={inicio}&ate={fim}&andar={(fim - inicio) * 0.3}",
            )

        # Um arranjo com TODOS os tipos de painel, a partir dos sinais do padrão.
        paineis = j.get("paineis") or []

        def ids(p):
            return [s["id"] if isinstance(s, dict) else str(s) for s in (p.get("sinais") or [])]

        sinais = [s for p in paineis if p.get("tipo") == "analogico" for s in ids(p)]
        arranjo = [
            dict(
                id=p.get("id"),
                tipo=p.get("tipo"),
                nome=p.get("nome"),
                sinais=ids(p),
                medida=p.get("medida") or "instantaneo",
            )
            for p in paineis
        ]
        from osclab.plot import paineis as paineis_mod

        for i, tipo in enumerate(
            t for t in paineis_mod.TIPOS if t not in ("analogico", "digital")
        ):
            arranjo.append({"id": f"x{i}", "tipo": tipo, "nome": tipo, "sinais": sinais[:6]})
        arranjo.append(
            {
                "id": "rms",
                "tipo": "analogico",
                "nome": "rms",
                "sinais": sinais[:6],
                "medida": "rms",
            }
        )
        corpo = {"paineis": arranjo}
        j2 = self.pedir(
            nome, "janela todos os painéis", "post", base + "?colunas=900", json=corpo
        )
        for p in (j2 or {}).get("paineis") or []:
            if p.get("erro"):
                self.anotar(
                    nome,
                    f"painel {p.get('tipo')}",
                    "painel com erro",
                    erro=str(p["erro"])[:200],
                )

        if inicio is not None and fim is not None:
            t1, t2 = inicio + (fim - inicio) * 0.25, inicio + (fim - inicio) * 0.75
            for rot, q in (
                ("", ""),
                (" primário", "&lado=primario"),
                (" filtro", "&filtro=1"),
                (" refere 0", "&refere=0"),
                (" passo", "&passo1=1&ciclos2=1"),
            ):
                self.pedir(
                    nome,
                    "leitura" + rot,
                    "post",
                    f"{base}/leitura?t1={t1}&t2={t2}{q}",
                    json=corpo,
                )
            self.pedir(
                nome,
                "leitura nas pontas",
                "post",
                f"{base}/leitura?t1={inicio}&t2={fim}",
                json=corpo,
            )

        primeiro = next(
            (
                s.get("nome")
                for p in paineis
                if p.get("tipo") == "analogico"
                for s in (p.get("sinais") or [])
                if isinstance(s, dict) and s.get("familia") == "canal"
            ),
            None,
        )
        contas = (
            [f"[{primeiro}] * 2", f"[{primeiro}] / [{primeiro}]", f"sqrt([{primeiro}])"]
            if primeiro
            else []
        ) + ["1 +", "[NAO EXISTE]", "(((("]
        for expr in contas:
            self.pedir(
                nome, f"conta {expr[:20]}", "post", f"{base}/conta", json={"expressao": expr}
            )

        meio = (inicio + fim) / 2 if inicio is not None and fim is not None else None
        manual = {
            "forma": "rx",
            "r": "4.8",
            "x": "24",
            "r0": "18",
            "x0": "72",
            "km": "60",
            "b1": "200",
        }
        for rot, c in (
            ("auto", {"fonte": "auto"}),
            ("manual", {"fonte": "manual", "manual": manual}),
            ("manual secundário", {"fonte": "manual", "manual": dict(manual, base="sec")}),
            (
                "manual km",
                {
                    "fonte": "manual",
                    "manual": {
                        "forma": "km",
                        "rkm": "0.08",
                        "xkm": "0.4",
                        "km": "60",
                        "b1km": "3",
                    },
                },
            ),
            ("manual vazio", {"fonte": "manual", "manual": {}}),
        ):
            if meio is not None:
                c = dict(c, t=meio)
            self.pedir(nome, f"localizar {rot}", "post", f"{base}/localizar", json=c)
        self.pedir(nome, "lógica", "get", f"/api/logica/{sha}")
        self.pedir(nome, "dicionário", "get", f"/api/dicionario/{sha}")
        self.pedir(nome, "exportar", "get", f"/api/acervo/{sha}/exportar")


def um_lote(pasta: Path, saida: Path, sem: list[str], pular: int, quantos: int | None) -> int:
    """Roda `quantos` registros (depois de pular `pular`) NESTE processo."""
    tmp = Path(tempfile.mkdtemp(prefix="osclab_varredura_"))
    os.environ["OSCLAB_DATA_DIR"] = str(tmp)
    if (RAIZ / "bases.json").exists():  # a base ativa da máquina, só para ler
        shutil.copy(RAIZ / "bases.json", tmp / "bases.json")
    sys.path.insert(0, str(RAIZ / "src"))
    v = Varredura()
    n = 0
    try:
        with open(saida, "a", encoding="utf-8") as f:
            for k, p in enumerate(principais(pasta, sem)):
                if k < pular:
                    continue
                if quantos is not None and n >= quantos:
                    break
                antes = len(v.achados)
                try:
                    v.registro(p)
                except Exception as exc:
                    v.anotar(
                        str(p),
                        "varredura",
                        "exceção",
                        erro=f"{type(exc).__name__}: {exc}"[:300],
                    )
                for a in v.achados[antes:]:
                    f.write(json.dumps(a, ensure_ascii=False) + "\n")
                f.flush()
                n += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return n


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pasta", type=Path)
    ap.add_argument("saida", type=Path)
    ap.add_argument("--lote", type=int, default=40, help="registros por processo (padrão 40)")
    ap.add_argument("--sem", action="append", default=[], help="pula caminhos com este texto")
    ap.add_argument("--pular", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--so-este-lote", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.so_este_lote:
        return 0 if um_lote(a.pasta, a.saida, a.sem, a.pular, a.lote) >= 0 else 1
    total = sum(1 for _ in principais(a.pasta, a.sem))
    a.saida.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    for pular in range(0, total, a.lote):
        # Um processo por lote: a memória volta ao sistema a cada um.
        subprocess.call(
            [
                sys.executable,
                __file__,
                str(a.pasta),
                str(a.saida),
                "--lote",
                str(a.lote),
                "--pular",
                str(pular),
                "--so-este-lote",
                *sum((["--sem", s] for s in a.sem), []),
            ]
        )
        print(f"  {min(pular + a.lote, total)} de {total} registros", flush=True)
    achados = [
        json.loads(linha)
        for linha in a.saida.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]
    tipos: dict[str, int] = {}
    for x in achados:
        tipos[x["tipo"]] = tipos.get(x["tipo"], 0) + 1
    print(
        f"{total} registros em {time.perf_counter() - t0:.0f} s; achados: {tipos or 'nenhum'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
