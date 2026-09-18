"""O acervo de oscilografias, endereçado por conteúdo.

Padrão herdado da PAC CT, e pela mesma razão prática: **o arquivo entra por um
lugar só**. Cada tela escolhe do acervo em vez de pedir upload de novo, e o que
uma ferramenta gera volta para cá.

## Por que por conteúdo, e não por nome

Todo fabricante exporta com o nome padrão dele. Dois registros de subestações
diferentes chegam como `FRA00045.cfg` e se atropelariam. A identidade aqui é o
sha256 do conteúdo, então:

* dois envios do mesmo registro são um só — não duplica;
* dois registros diferentes com o mesmo nome convivem em paz;
* o mesmo `.cfg` com um `.dat` diferente são registros diferentes, que é o
  comportamento certo: o par é que forma o evento.

## A estrutura no disco

```
<dados>/library/
└── <sha256>/
    ├── meta.json          resumo em cache, para a lista abrir rápido
    ├── REGISTRO.cfg       os arquivos, com o nome original
    ├── REGISTRO.dat
    └── REGISTRO.hdr       (quando veio)
```

Os arquivos ficam com o **nome original** de propósito: é assim que o leitor
acha o `.dat` a partir do `.cfg`, sem precisar de tabela nenhuma.

## O arquivo órfão fica esperando o par

Quase ninguém arrasta o `.cfg` e o `.dat` na mesma leva: manda um, vê que faltou,
manda o outro. Se cada envio fosse tratado isolado, o primeiro seria descartado e
o segundo reclamaria da mesma falta — que foi exatamente o que aconteceu no
primeiro teste de verdade.

Então um arquivo que chega sem o par vai para a **antessala** e espera. Quando o
outro metade chega, o par se forma sozinho e entra no acervo.

O pareamento na antessala é pelo nome base, então dois registros diferentes com o
mesmo nome — e todo fabricante exporta com o nome padrão dele — poderiam se
juntar errado. Duas defesas: o par só entra se **abrir** (um `.dat` de outro
registro não bate com o `.cfg`), e a antessala fica **visível na tela**, para
ninguém ser pareado sem saber.

## Um registro só entra se abrir

Depois de gravar, o acervo tenta ler. Se não abrir, a pasta é apagada e o erro
volta para a tela. Um acervo cheio de coisa quebrada seria pior do que um
acervo vazio: a pessoa só descobriria o problema no meio da análise.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from osclab import paths
from osclab.formats import registry
from osclab.formats.base import FormatError, Record

#: O que faz parte de um registro COMTRADE. O resto é ignorado.
EXTENSOES = {".cfg", ".cff", ".dat", ".hdr", ".inf"}

#: As que sozinhas já formam um registro.
PRINCIPAIS = {".cfg", ".cff"}


@dataclass(frozen=True)
class Item:
    """Um registro no acervo, com o resumo já calculado."""

    sha: str
    nome: str
    arquivos: tuple[str, ...]
    adicionado_em: str

    formato: str = ""
    estacao: str = ""
    equipamento: str = ""
    n_analogicos: int = 0
    n_digitais: int = 0
    n_amostras: int = 0
    taxa_hz: float = 0.0
    amostras_por_ciclo: float = 0.0
    frequencia: float = 60.0
    inicio: str = ""
    disparo: str = ""
    avisos: tuple[str, ...] = ()

    def como_dicionario(self) -> dict:
        return asdict(self)


@dataclass
class Resultado:
    """O que aconteceu num envio."""

    aceitos: list[Item]
    repetidos: list[Item]
    problemas: list[str]
    #: Arquivos guardados na antessala, esperando a outra metade do par.
    aguardando: list[str] = field(default_factory=list)

    @property
    def houve_algo(self) -> bool:
        return bool(self.aceitos or self.repetidos or self.problemas
                    or self.aguardando)


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

#: A antessala. O nome começa com "_" para nunca ser confundida com um sha256,
#: que é sempre hexadecimal — `obter()` recusa qualquer nome não alfanumérico.
ANTESSALA = "_aguardando"


def _raiz() -> Path:
    paths.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    return paths.LIBRARY_DIR


def _antessala() -> Path:
    pasta = _raiz() / ANTESSALA
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def nome_seguro(nome: str) -> str:
    """Só o nome do arquivo, sem caminho nenhum.

    O nome vem do navegador, então pode trazer `..\\..\\windows\\system32\\` ou
    barras de qualquer sistema. Ficar com o último pedaço é o que impede um
    envio de escrever fora da pasta do acervo.
    """
    limpo = nome.replace("\\", "/").split("/")[-1].strip()
    return limpo or "sem-nome"


def agrupar(nomes: Sequence[str]) -> dict[str, dict[str, str]]:
    """Agrupa os arquivos enviados por nome base.

    `REGISTRO.CFG` e `registro.dat` são o mesmo par: o Windows não distingue
    maiúsculas e os fabricantes exportam de qualquer jeito.
    """
    grupos: dict[str, dict[str, str]] = {}
    for nome in nomes:
        limpo = nome_seguro(nome)
        caminho = Path(limpo)
        grupos.setdefault(caminho.stem.lower(), {})[caminho.suffix.lower()] = limpo
    return grupos


def _sha_do_grupo(arquivos: dict[str, bytes]) -> str:
    """Impressão digital do conjunto: nomes e conteúdos, em ordem estável."""
    h = hashlib.sha256()
    for nome in sorted(arquivos, key=str.lower):
        h.update(Path(nome).suffix.lower().encode("utf-8"))
        h.update(b"\0")
        h.update(arquivos[nome])
        h.update(b"\0")
    return h.hexdigest()


def _principal(pasta: Path) -> Path | None:
    for arquivo in sorted(pasta.iterdir()):
        if arquivo.suffix.lower() in PRINCIPAIS:
            return arquivo
    return None


def _resumir(sha: str, nome: str, arquivos: list[str], registro: Record) -> Item:
    return Item(
        sha=sha,
        nome=nome,
        arquivos=tuple(sorted(arquivos)),
        adicionado_em=datetime.now().isoformat(timespec="seconds"),
        formato=registro.format_name,
        estacao=registro.station,
        equipamento=registro.device_id,
        n_analogicos=len(registro.analog_channels),
        n_digitais=len(registro.status_channels),
        n_amostras=registro.n_samples,
        taxa_hz=round(registro.base_rate_hz, 3),
        amostras_por_ciclo=round(registro.samples_per_cycle, 2),
        frequencia=registro.line_frequency,
        inicio=registro.start_time.isoformat(sep=" ") if registro.start_time else "",
        disparo=registro.trigger_time.isoformat(sep=" ") if registro.trigger_time else "",
        avisos=tuple(registro.notes),
    )


# ---------------------------------------------------------------------------
# A antessala: arquivos esperando o par
# ---------------------------------------------------------------------------

def aguardando() -> dict[str, dict[str, str]]:
    """O que está na antessala, agrupado por nome base."""
    pasta = _raiz() / ANTESSALA
    if not pasta.is_dir():
        return {}
    return agrupar([a.name for a in pasta.iterdir() if a.is_file()])


def _guardar_na_antessala(arquivos: dict[str, bytes]) -> None:
    pasta = _antessala()
    for nome, dados in arquivos.items():
        (pasta / nome).write_bytes(dados)


def _tirar_da_antessala(base: str) -> None:
    pasta = _raiz() / ANTESSALA
    if not pasta.is_dir():
        return
    for arquivo in list(pasta.iterdir()):
        if arquivo.is_file() and arquivo.stem.lower() == base:
            arquivo.unlink(missing_ok=True)


def esquecer_aguardando() -> int:
    """Esvazia a antessala. Devolve quantos arquivos saíram."""
    pasta = _raiz() / ANTESSALA
    if not pasta.is_dir():
        return 0
    arquivos = [a for a in pasta.iterdir() if a.is_file()]
    for arquivo in arquivos:
        arquivo.unlink(missing_ok=True)
    return len(arquivos)


# ---------------------------------------------------------------------------
# Guardar
# ---------------------------------------------------------------------------

def guardar(enviados: Sequence[tuple[str, bytes]]) -> Resultado:
    """Guarda os arquivos enviados, agrupando-os em registros.

    Devolve o que entrou, o que já existia e o que deu problema — nesta ordem de
    importância para quem está olhando a tela.
    """
    resultado = Resultado(aceitos=[], repetidos=[], problemas=[])
    if not enviados:
        resultado.problemas.append("Nenhum arquivo chegou.")
        return resultado

    conteudos = {nome_seguro(n): b for n, b in enviados}
    grupos = agrupar(list(conteudos))

    # Um arquivo que chegou antes e ficou esperando o par entra na conta agora.
    # O que veio AGORA tem prioridade: se alguém reenviar o .cfg corrigido, é o
    # novo que vale.
    na_espera = aguardando()
    pasta_espera = _raiz() / ANTESSALA
    for base, por_extensao in na_espera.items():
        alvo = grupos.setdefault(base, {})
        for extensao, nome in por_extensao.items():
            if extensao in alvo:
                continue
            arquivo = pasta_espera / nome
            if arquivo.is_file():
                alvo[extensao] = nome
                conteudos.setdefault(nome, arquivo.read_bytes())

    ignorados = sorted({
        Path(n).suffix.lower() or "(sem extensao)"
        for n in conteudos
        if Path(n).suffix.lower() not in EXTENSOES
    })
    if ignorados:
        resultado.problemas.append(
            f"Ignorei arquivos {', '.join(ignorados)} — nao fazem parte do "
            f"COMTRADE."
        )

    for base, por_extensao in sorted(grupos.items()):
        uteis = {e: n for e, n in por_extensao.items() if e in EXTENSOES}
        if not uteis:
            continue

        arquivos = {n: conteudos[n] for n in uteis.values()}

        principal = next((uteis[e] for e in (".cff", ".cfg") if e in uteis), None)
        se_falta = None
        if principal is None:
            se_falta = (f"'{base}': guardei o .dat e estou esperando o .cfg. "
                        f"Sem ele nao da' para saber o que cada numero significa "
                        f"— mande o .cfg e o par se forma sozinho.")
        elif ".cff" not in uteis and ".dat" not in uteis:
            se_falta = (f"'{base}': guardei o .cfg e estou esperando o .dat, que "
                        f"e' onde estao as amostras. Mande o .dat e o par se "
                        f"forma sozinho.")

        if se_falta is not None:
            _guardar_na_antessala(arquivos)
            resultado.aguardando.append(se_falta)
            continue

        sha = _sha_do_grupo(arquivos)
        pasta = _raiz() / sha

        existente = obter(sha)
        if existente is not None:
            _tirar_da_antessala(base)
            resultado.repetidos.append(existente)
            continue

        pasta.mkdir(parents=True, exist_ok=True)
        try:
            for nome, dados in arquivos.items():
                (pasta / nome).write_bytes(dados)
            registro = registry.read(pasta / principal)
        except (FormatError, OSError) as exc:
            shutil.rmtree(pasta, ignore_errors=True)
            resultado.problemas.append(f"'{base}': {exc}")
            continue

        item = _resumir(sha, Path(principal).stem, list(arquivos), registro)
        (pasta / "meta.json").write_text(
            json.dumps(item.como_dicionario(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _tirar_da_antessala(base)
        resultado.aceitos.append(item)

    return resultado


# ---------------------------------------------------------------------------
# Consultar
# ---------------------------------------------------------------------------

def obter(sha: str) -> Item | None:
    """O registro com esta impressão digital, ou `None`."""
    if not sha or not sha.isalnum():
        return None
    meta = _raiz() / sha / "meta.json"
    if not meta.is_file():
        return None
    try:
        dados = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    dados["arquivos"] = tuple(dados.get("arquivos", ()))
    dados["avisos"] = tuple(dados.get("avisos", ()))
    return Item(**dados)


def listar() -> list[Item]:
    """Tudo no acervo, do mais recente para o mais antigo."""
    itens = []
    for pasta in _raiz().iterdir():
        if pasta.is_dir() and pasta.name != ANTESSALA:
            item = obter(pasta.name)
            if item is not None:
                itens.append(item)
    return sorted(itens, key=lambda i: i.adicionado_em, reverse=True)


def caminho_principal(sha: str) -> Path | None:
    """O `.cfg` (ou `.cff`) deste registro, no disco."""
    if obter(sha) is None:
        return None
    return _principal(_raiz() / sha)


def ler(sha: str) -> Record:
    """Abre o registro. Levanta `FormatError` se ele sumiu ou quebrou."""
    caminho = caminho_principal(sha)
    if caminho is None:
        raise FormatError("Este registro nao esta' no acervo.")
    return registry.read(caminho)


def remover(sha: str) -> bool:
    """Tira o registro do acervo. Devolve se havia algo para tirar."""
    if obter(sha) is None:
        return False
    shutil.rmtree(_raiz() / sha, ignore_errors=True)
    return True
