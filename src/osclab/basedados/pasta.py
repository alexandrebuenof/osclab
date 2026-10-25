"""Onde a base mora, como ela nasce e qual delas está ativa.

## A estrutura no disco

```
<base>/
├── base.json          nome, versão do formato, quando nasceu
├── digitais/
│   └── digitais.csv   o dicionário dos sinais digitais
├── linhas/            parâmetros de linha e KMZ (módulo de linhas)
└── registros/         o histórico de oscilografias
```

O `base.json` é o que faz uma pasta ser uma base: é por ele que o programa
reconhece uma base que veio de outra pessoa, e é nele que mora a **versão do
formato** — sem ela, uma base montada hoje viraria um enigma quando o formato
mudar. O nome das pastas é curto, minúsculo e sem acento de propósito: é esse
nome que o programa procura sozinho, e acento em nome de pasta já atravessou
três sistemas de arquivos diferentes dando problema em dois.

## Onde ela nasce, e por que não dentro do programa

Em `paths.BASE_PADRAO`, que fica na pasta de DADOS do usuário — a mesma que
guarda o acervo e que uma atualização do programa nunca toca. Base dentro da
pasta do programa é a estrutura que perde o trabalho catalogado na primeira
atualização copiada por cima.

O usuário pode apontar para outra pasta (um pen-drive, um compartilhamento da
equipe): `escolher()` aceita qualquer caminho que tenha um `base.json` dentro.
A camada de equipe — uma base da regional que vale para todos, com a sua
vencendo por cima — é o passo seguinte, e não está aqui.

## O que fica FORA da base

`paths.BASES_FILE` guarda qual base está ativa, quais já foram abertas e quais
gavetas estão ligadas. Isso é preferência **desta máquina**: a base viaja num
`.zip` para outra regional e não leva junto a opinião de quem a montou sobre
quais gavetas consultar.

## Habilitar e desabilitar

Desligar uma gaveta não apaga nada — só faz o programa parar de consultá-la.
É a regra de diagnóstico do projeto aplicada à base: avisa, nunca bloqueia.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from osclab import paths

#: Versão do formato da base. Sobe quando o que está gravado muda de forma —
#: é o que permite abrir uma base antiga sabendo o que esperar dela.
FORMATO = 1

#: O arquivo que faz uma pasta ser uma base.
MARCA = "base.json"

#: A pasta do dicionário, dentro da base. Curta e sem acento, como as outras:
#: é por ela que o programa acha o dicionário numa base que veio de fora.
PASTA_DO_DICIONARIO = "dicionario"

#: O nome da pasta da base, quando o usuário não dá nenhum.
#:
#: O nome era FIXO até 19/10/2026 — ele soltou, para caber mais de uma base na
#: mesma pasta mãe (`base-subestacoes` e `base-linhas` colidiriam com um nome
#: só). Quem identifica uma base continua sendo o `base.json` lá dentro, e não
#: o nome da pasta: `escolher()` já funcionava assim.
#:
#: O que o nome livre custou, e que a tela precisa dizer:
#:
#: 1. Quem receber uma base de outra pessoa vai procurar uma pasta
#:    «database» — com nome inventado, é preciso dizer qual é.
#: 2. O `.gitignore` barra `/database/`; não há linha que barre um nome que
#:    ainda não foi inventado, e o repositório é público. Por isso o
#:    diagnóstico da tela acende vermelho para uma base dentro da pasta do
#:    programa.
#:
#: As gavetas por dentro (`dicionario`, `linhas`) continuam com nome TRAVADO:
#: é por elas que o programa acha as coisas numa base que veio de fora, e
#: soltá-las não traz ganho nenhum.
NOME_PADRAO = "database"

#: O que um nome de pasta não pode ter. A tela diagnostica antes e deixa
#: criar assim mesmo — avisa, nunca bloqueia —, mas barra de pasta no nome
#: não é nome ruim: é outro caminho, e criaria a base noutro lugar.
SEPARADORES = ("/", "\\")


@dataclass(frozen=True)
class Gaveta:
    """Uma das três divisões da base."""

    id: str
    nome: str
    dizer: str
    #: O que o programa passa a fazer quando ela está desligada. É o texto que
    #: a tela mostra junto da chave — desligar sem saber o que muda é o que
    #: faz alguém desligar e depois achar que o programa quebrou.
    sem: str
    #: Já dá para editar pelo programa? As duas últimas chegam com os módulos
    #: que as usam; a pasta já nasce, para a base não mudar de forma depois.
    editavel: bool = False


GAVETAS: tuple[Gaveta, ...] = (
    # DICIONÁRIO é o nome oficial, escolhido por ele em 19/10/2026. Não é
    # «sinais digitais» nem «wordbits»: é um dicionário, e a tela que o usa é
    # de consulta — procura-se um nome e lê-se o que ele quer dizer.
    Gaveta(
        "dicionario", "Dicionário",
        "o nome e o significado de cada sinal digital, por fabricante e modelo",
        "os digitais aparecem com o nome cru do arquivo",
        editavel=True,
    ),
    Gaveta(
        "linhas", "Linhas e estruturas",
        "parâmetros das linhas e os KMZ das estruturas",
        "a localização de falta pede os parâmetros na tela, a cada cálculo",
    ),
    # A gaveta dos REGISTROS — o histórico de oscilografias — continua para
    # depois: ela chega com o módulo que a usa.
)

IDS = tuple(g.id for g in GAVETAS)


class ErroDaBase(Exception):
    """O pedido não dá para atender, e a tela precisa dizer por quê."""


# ---------------------------------------------------------------------------
# A base em si
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Base:
    """Uma base de dados no disco."""

    pasta: Path
    nome: str
    formato: int = FORMATO
    criada: str = ""

    @property
    def existe(self) -> bool:
        return (self.pasta / MARCA).is_file()

    def gaveta(self, qual: str) -> Path:
        """A pasta de uma gaveta. Cria se faltar — uma base que veio de uma
        versão mais antiga não tem as gavetas que nasceram depois."""
        destino = self.pasta / qual
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    def como_dicionario(self) -> dict:
        return {
            "pasta": str(self.pasta),
            "nome": self.nome,
            "formato": self.formato,
            "criada": self.criada,
            "existe": self.existe,
            "futura": self.formato > FORMATO,
        }


def _ler_marca(caminho: Path) -> Base | None:
    """Lê o `base.json` de uma pasta. `None` se ali não houver uma base."""
    arquivo = Path(caminho) / MARCA
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    return Base(
        pasta=Path(caminho),
        nome=str(dados.get("nome") or Path(caminho).name),
        formato=int(dados.get("formato") or 1),
        criada=str(dados.get("criada") or ""),
    )


def apelido(nome: str) -> str:
    """«Base da Regional Norte» -> `base-da-regional-norte`.

    Sem acento, sem espaço e minúsculo: é o nome da pasta, e ele atravessa
    pen-drive, compartilhamento de rede e o `.zip` que vai para outra regional.
    """
    limpo = unicodedata.normalize("NFD", str(nome or ""))
    limpo = "".join(c for c in limpo if unicodedata.category(c) != "Mn")
    limpo = re.sub(r"[^a-zA-Z0-9]+", "-", limpo).strip("-").lower()
    return limpo or "base"


# ---------------------------------------------------------------------------
# O que esta máquina lembra
# ---------------------------------------------------------------------------

def _ler_lembranca() -> dict:
    try:
        dados = json.loads(paths.BASES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    if not isinstance(dados, dict):
        dados = {}
    dados.setdefault("ativa", "")
    dados.setdefault("conhecidas", [])
    dados.setdefault("habilitadas", {})
    return dados


def _gravar_lembranca(dados: dict) -> None:
    paths.BASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.BASES_FILE.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def _lembrar(caminho: Path, ativa: bool = True) -> None:
    dados = _ler_lembranca()
    texto = str(Path(caminho))
    conhecidas = [c for c in dados["conhecidas"] if c != texto]
    dados["conhecidas"] = [texto, *conhecidas][:20]
    if ativa:
        dados["ativa"] = texto
    _gravar_lembranca(dados)


def ativa() -> Base | None:
    """A base em uso, ou `None` se ainda não houver nenhuma.

    Uma base cuja pasta sumiu (o pen-drive que não está aqui) continua sendo a
    ativa, e volta daqui com `existe=False`: a tela avisa e deixa procurar, em
    vez de esquecê-la sozinha — esquecer seria decidir pelo dono.
    """
    dados = _ler_lembranca()
    caminho = dados.get("ativa") or ""
    if not caminho:
        return None
    base = _ler_marca(Path(caminho))
    if base is not None:
        return base
    return Base(pasta=Path(caminho), nome=Path(caminho).name, criada="")


def habilitadas() -> dict:
    """Quais gavetas o programa consulta. O que nunca foi mexido vem ligado."""
    guardado = _ler_lembranca().get("habilitadas") or {}
    return {g.id: bool(guardado.get(g.id, True)) for g in GAVETAS}


def habilitar(qual: str, ligada: bool) -> dict:
    if qual not in IDS:
        raise ErroDaBase(f"não existe gaveta «{qual}»")
    dados = _ler_lembranca()
    marcas = dict(dados.get("habilitadas") or {})
    marcas[qual] = bool(ligada)
    dados["habilitadas"] = marcas
    _gravar_lembranca(dados)
    return habilitadas()


def usa(qual: str) -> bool:
    """O programa pode consultar esta gaveta agora?

    É a pergunta que o resto do programa faz — e ela junta as duas condições
    (existe base, e a gaveta está ligada) num lugar só, para nenhum chamador
    esquecer metade.
    """
    base = ativa()
    return bool(base and base.existe and habilitadas().get(qual, True))


# ---------------------------------------------------------------------------
# Criar, escolher
# ---------------------------------------------------------------------------

def dentro_do_programa(caminho: str | Path) -> bool:
    """Este caminho está dentro da pasta do programa?

    Importa porque é a única pergunta que separa uma base segura de uma base
    que some: atualizar o OscLab é copiar a pasta dele por cima, e o que
    estiver ali dentro vai junto.
    """
    return paths.is_within(Path(caminho), paths.PROJECT_ROOT)


def recomendado() -> Path:
    """Onde a base DEVERIA nascer.

    Hoje o lançador aponta `OSCLAB_DATA_DIR` para a própria pasta do programa,
    então o «ao lado do acervo» cairia exatamente no lugar errado. Enquanto for
    assim, a recomendação é uma pasta na área do usuário, que atualização
    nenhuma alcança.
    """
    if dentro_do_programa(paths.DATA_DIR):
        return Path.home() / "OscLab"
    return paths.DATA_DIR


def criar(nome: str = "", onde: str | Path | None = None) -> Base:
    """Cria uma base nova e a deixa ativa.

    `onde` é a pasta MÃE e `nome` é a pasta da base dentro dela: a base nasce
    em `<onde>/<nome>`. Vazio, `nome` vira «database». Sem `onde`, nasce ao
    lado do acervo, em `paths.DATA_DIR`.

    O nome é o mesmo no disco e na tela — um nome só é mais fácil de guardar
    do que dois, e é ele que distingue duas bases na lista.
    """
    if onde:
        mae = Path(onde).expanduser()
        if not mae.is_absolute():
            raise ErroDaBase("o caminho precisa ser completo, começando no disco")
        if mae.exists() and not mae.is_dir():
            raise ErroDaBase(f"«{mae}» é um arquivo, não uma pasta")
        if not mae.is_dir():
            # A pasta mãe pode ainda não existir: a tela mostra o caminho
            # inteiro antes de criar, e recusar aqui seria um beco sem saída
            # para quem digitou uma pasta nova em vez de escolher uma pronta.
            try:
                mae.mkdir(parents=True, exist_ok=True)
            except OSError as erro:
                raise ErroDaBase(f"não consegui criar «{mae}»: {erro}") from erro
    else:
        # Sem escolha, vai para a recomendada — e a recomendada pode ainda não
        # existir, porque é uma pasta que o programa está propondo criar.
        mae = recomendado()
        try:
            mae.mkdir(parents=True, exist_ok=True)
        except OSError as erro:
            raise ErroDaBase(f"não consegui criar «{mae}»: {erro}") from erro
    nome = str(nome or "").strip() or NOME_PADRAO
    if any(sep in nome for sep in SEPARADORES):
        raise ErroDaBase(
            "o nome é o da pasta, não um caminho — tire as barras dele")
    if nome in (".", ".."):
        raise ErroDaBase("esse nome não serve para uma pasta")

    destino = mae / nome
    ja = _ler_marca(destino)
    if ja is not None:
        # Já era uma base. Ativar é o que a pessoa queria; criar por cima
        # apagaria o trabalho de alguém.
        _lembrar(destino)
        return ja
    if destino.exists() and any(destino.iterdir()):
        raise ErroDaBase(
            f"a pasta «{destino}» já existe e tem coisa dentro — "
            "escolha outro nome ou aponte para ela em «escolher»")

    destino.mkdir(parents=True, exist_ok=True)
    base = Base(pasta=destino, nome=nome, formato=FORMATO,
                criada=datetime.now().isoformat(timespec="seconds"))
    (destino / MARCA).write_text(json.dumps({
        "nome": base.nome,
        "formato": base.formato,
        "criada": base.criada,
        "gavetas": list(IDS),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for g in GAVETAS:
        base.gaveta(g.id)
    _lembrar(destino)
    return base


def escolher(caminho: str | Path) -> Base:
    """Passa a usar uma base que já existe no disco."""
    alvo = Path(str(caminho or "").strip()).expanduser()
    if not str(alvo).strip():
        raise ErroDaBase("diga o caminho da base")
    if not alvo.is_dir():
        raise ErroDaBase(f"não encontrei a pasta «{alvo}»")
    base = _ler_marca(alvo)
    if base is None:
        raise ErroDaBase(
            f"«{alvo}» não é uma base: falta o {MARCA} dentro dela")
    if base.formato > FORMATO:
        # Não recusa: a base é mais nova que o programa, e o que ele souber
        # ler ele lê. Quem avisa é a tela.
        pass
    _lembrar(alvo)
    return base


def conhecidas() -> list[dict]:
    """As bases que esta máquina já abriu, a ativa primeiro."""
    dados = _ler_lembranca()
    saida = []
    for caminho in dados["conhecidas"]:
        base = _ler_marca(Path(caminho))
        if base is None:
            base = Base(pasta=Path(caminho), nome=Path(caminho).name)
        item = base.como_dicionario()
        item["ativa"] = str(Path(caminho)) == str(dados.get("ativa") or "")
        saida.append(item)
    return saida


# ---------------------------------------------------------------------------
# O resumo que as telas pedem
# ---------------------------------------------------------------------------

def contagem(base: Base | None, qual: str) -> int:
    """Quantos itens tem uma gaveta. Zero quando ainda não há nada."""
    if base is None or not base.existe:
        return 0
    if qual == PASTA_DO_DICIONARIO:
        from osclab.basedados import digitais
        return len(digitais.listar(base))
    pasta = base.pasta / qual
    if not pasta.is_dir():
        return 0
    return sum(1 for _ in pasta.iterdir() if not _.name.startswith("."))


def estado() -> dict:
    """Tudo que a tela da base e o menu precisam saber, numa viagem só."""
    base = ativa()
    gavetas = []
    marcas = habilitadas()
    for g in GAVETAS:
        gavetas.append({
            "id": g.id,
            "nome": g.nome,
            "dizer": g.dizer,
            "sem": g.sem,
            "editavel": g.editavel,
            "ligada": marcas[g.id],
            "itens": contagem(base, g.id),
        })
    return {
        "tem": bool(base and base.existe),
        "base": base.como_dicionario() if base else None,
        "gavetas": gavetas,
        "conhecidas": conhecidas(),
        "onde_nasce": str(recomendado()),
        "pasta_do_programa": str(paths.PROJECT_ROOT),
        "arriscado": dentro_do_programa(recomendado()),
        "nome_padrao": NOME_PADRAO,
        "formato": FORMATO,
    }
