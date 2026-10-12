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
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path

from osclab import paths
from osclab.formats import registry
from osclab.formats.base import FormatError, Record

#: O que faz parte de um registro. O resto é ignorado.
EXTENSOES = {".cfg", ".cff", ".dat", ".hdr", ".inf", ".cev"}

#: As que sozinhas já formam um registro — `.cev` entra aqui porque um relatório
#: de evento da SEL é um arquivo só, e não um par como o COMTRADE clássico.
#: A ordem importa: é a ordem em que o principal do grupo é escolhido.
PRINCIPAIS = (".cff", ".cev", ".cfg")

#: A única que sozinha NÃO forma um registro: `.cfg` precisa do `.dat`.
PRECISA_DE_PAR = {".cfg": ".dat"}


@dataclass(frozen=True)
class Item:
    """Um registro no acervo, com o resumo já calculado."""

    sha: str
    #: Como o registro se chama NA TELA. É o nome do arquivo, até alguém
    #: renomeá-lo aqui dentro — ver `apelido`.
    nome: str
    #: Como ele se chama no DISCO. Os dois são iguais enquanto ninguém
    #: renomeia, e a tela mostra este quando são diferentes: o arquivo na pasta
    #: continua com o nome que o relé deu, e quem for procurá-lo lá precisa
    #: saber disso.
    nome_do_arquivo: str = ""
    arquivos: tuple[str, ...] = ()
    adicionado_em: str = ""

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
    #: O que o LEITOR avisa: o que ele fez, deixou de fora ou nao conseguiu
    #: confirmar. E' so' isto que a tela marca com triangulo.
    avisos: tuple[str, ...] = ()
    #: O que o RELE' concluiu sozinho e gravou no arquivo. Informacao, nao
    #: aviso -- ver `formats/base.py`.
    relatos: tuple[str, ...] = ()
    #: O que o arquivo diz do RELOGIO: em que fuso estao os carimbos, qual e'
    #: a hora local da instalacao e quanto o rele' confia no proprio relogio.
    #:
    #: Fica no cabecalho ao lado do disparo porque a hora sozinha NAO se
    #: interpreta: no parque, o SEL-421 carimba em UTC e o SIPROTEC carimba em
    #: hora local, e o mesmo curto aparece com quatro horas de diferenca.
    relogio: str = ""

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
    """O arquivo da pasta que abre o registro, na precedencia de `PRINCIPAIS`.

    A ordem e' a de `PRINCIPAIS`, e nao a da pasta: se um dia caírem um `.cff` e
    um `.cfg` no mesmo lugar, o que manda e' o formato, nao o alfabeto.
    """
    for extensao in PRINCIPAIS:
        for arquivo in sorted(pasta.iterdir()):
            if arquivo.suffix.lower() == extensao:
                return arquivo
    return None


def _resumir(sha: str, nome: str, arquivos: list[str], registro: Record) -> Item:
    return Item(
        sha=sha,
        nome=nome,
        nome_do_arquivo=nome,
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
        disparo=(registro.trigger_time.isoformat(sep=" ")
                 if registro.trigger_time else ""),
        avisos=tuple(registro.notes),
        relatos=tuple(registro.relatos),
        relogio=registro.time_quality,
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
            f"Ignorei arquivos {', '.join(ignorados)} — nao sao formato "
            f"de oscilografia que eu leia."
        )

    for base, por_extensao in sorted(grupos.items()):
        uteis = {e: n for e, n in por_extensao.items() if e in EXTENSOES}
        if not uteis:
            continue

        arquivos = {n: conteudos[n] for n in uteis.values()}

        principal = next((uteis[e] for e in PRINCIPAIS if e in uteis), None)
        se_falta = None
        if principal is None:
            se_falta = (f"'{base}': guardei o .dat e estou esperando o .cfg. "
                        f"Sem ele nao da' para saber o que cada numero significa "
                        f"— mande o .cfg e o par se forma sozinho.")
        else:
            par = PRECISA_DE_PAR.get(Path(principal).suffix.lower())
            if par is not None and par not in uteis:
                se_falta = (f"'{base}': guardei o .cfg e estou esperando o .dat, "
                            f"que e' onde estao as amostras. Mande o .dat e o "
                            f"par se forma sozinho.")

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
    # `relatos` e' mais novo que alguns `meta.json` ja' gravados. O cache pode
    # ser refeito a qualquer momento, mas nao pode QUEBRAR quem tem um antigo.
    dados["relatos"] = tuple(dados.get("relatos", ()))
    dados["relogio"] = dados.get("relogio", "")
    # Um `meta.json` gravado por uma versao MAIS NOVA pode trazer campo que
    # esta versao nao conhece. Ignorar o que sobra e' melhor que estourar: o
    # cache e' refazivel, o acervo do usuario nao.
    conhecidos = {c.name for c in fields(Item)}
    item = Item(**{k: v for k, v in dados.items() if k in conhecidos})
    # O `meta.json` é CACHE e pode ser refeito a qualquer momento; o apelido é
    # decisão humana e vive num arquivo só dele. Por isso ele é aplicado aqui,
    # na leitura, e não gravado no resumo.
    do_arquivo = item.nome_do_arquivo or item.nome
    escolhido = apelido(sha)
    return replace(item, nome=escolhido or do_arquivo,
                   nome_do_arquivo=do_arquivo)


def listar() -> list[Item]:
    """Tudo no acervo, do mais recente para o mais antigo."""
    itens = []
    for pasta in _raiz().iterdir():
        if pasta.is_dir() and pasta.name != ANTESSALA:
            item = obter(pasta.name)
            if item is not None:
                itens.append(item)
    return sorted(itens, key=lambda i: i.adicionado_em, reverse=True)


def pasta_do_registro(sha: str) -> Path:
    """A pasta deste registro no acervo, com os arquivos como entraram."""
    return _raiz() / sha


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
    return _com_vinculos(registry.read(caminho), sha)


# ---------------------------------------------------------------------------
# Os vinculos: canal do IED -> fase, corrigidos pelo usuario
# ---------------------------------------------------------------------------
#
# O vinculo canal -> fase e' deduzido do NOME do canal, e cada fabricante
# escreve esse nome como quer. Quando a deducao erra, tudo que vem depois erra
# junto -- conjunto trifasico, 3I0, V1, localizacao de falta -- e sai um numero
# na unidade certa, na ordem de grandeza certa, que ninguem contesta.
#
# Por isso a correcao do usuario e' GRAVADA ao lado do registro, e nao guardada
# na tela: quem corrigiu uma fase corrigiu para sempre, nao ate' fechar o
# navegador. Fica num arquivo separado, e nao no `meta.json`, porque `meta.json`
# e' cache -- pode ser refeito a qualquer momento -- e isto e' decisao humana.

VINCULOS = "vinculos.json"


def vinculos(sha: str) -> dict[int, str]:
    """As fases que o usuario corrigiu neste registro. Vazio e' o normal."""
    arquivo = _raiz() / sha / VINCULOS
    if not arquivo.is_file():
        return {}
    try:
        cru = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    saida: dict[int, str] = {}
    for chave, valor in (cru or {}).items():
        try:
            indice = int(chave)
        except (TypeError, ValueError):
            continue
        texto = str(valor or "").strip().upper()
        if texto in ("A", "B", "C", "N", "-"):
            saida[indice] = texto
    return saida


def gravar_vinculos(sha: str, escolhas: dict) -> dict[int, str]:
    """Grava as correcoes de fase. Devolve o que ficou gravado.

    Escolha vazia TIRA o vinculo (volta a valer a deducao); `"-"` e' a escolha
    explicita de "este canal nao e' fase nenhuma". Os dois sao coisas
    diferentes e a tela precisa poder dizer as duas.
    """
    if obter(sha) is None:
        raise FormatError("Este registro nao esta' no acervo.")
    atuais = vinculos(sha)
    for chave, valor in (escolhas or {}).items():
        try:
            indice = int(chave)
        except (TypeError, ValueError):
            continue
        texto = str(valor or "").strip().upper()
        if texto in ("A", "B", "C", "N", "-"):
            atuais[indice] = texto
        else:
            atuais.pop(indice, None)

    arquivo = _raiz() / sha / VINCULOS
    if atuais:
        arquivo.write_text(json.dumps({str(k): v for k, v in sorted(atuais.items())},
                                      ensure_ascii=False, indent=2),
                           encoding="utf-8")
    elif arquivo.is_file():
        arquivo.unlink()
    return atuais


# ---------------------------------------------------------------------------
# O apelido: como o registro se chama NA TELA
# ---------------------------------------------------------------------------
#
# Todo fabricante exporta com o nome padrao dele, e
# `UPC1 ALIMENTADOR 11SEL-451-521_09_202613_36_57_649_000` nao diz a ninguem
# que evento e' aquele. Quem analisa quer chamar o registro de "curto na
# SE Barra do Garcas, 19/01" -- e quer que esse nome esteja la' na proxima vez
# que abrir, e no relatorio.
#
# **O arquivo no disco nao muda.** O acervo guarda os arquivos com o nome
# original de proposito: e' assim que o leitor acha o `.dat` a partir do `.cfg`,
# e e' assim que o registro continua sendo o que o rele' gravou. O apelido e'
# uma camada por cima, num arquivo separado -- como os vinculos e as trincas,
# e pelo mesmo motivo: `meta.json` e' cache, isto e' decisao humana.
#
# Quem quiser o arquivo COM o nome novo exporta (`web/server.py`), e ai' a
# copia sai renomeada sem que o original seja tocado.

APELIDO = "apelido.json"

#: Teto do apelido. Nao e' limitacao de disco: um nome que nao cabe na barra do
#: titulo deixa de ser nome e vira paragrafo.
APELIDO_MAXIMO = 120


def apelido(sha: str) -> str:
    """Como o usuario chamou este registro, ou `""` se nao chamou de nada."""
    arquivo = _raiz() / sha / APELIDO
    if not arquivo.is_file():
        return ""
    try:
        cru = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str((cru or {}).get("nome", "")).strip()[:APELIDO_MAXIMO]


def gravar_apelido(sha: str, nome: str) -> str:
    """Grava o apelido. Devolve o nome que ficou valendo.

    Apelido vazio APAGA o apelido e devolve o nome do arquivo: e' assim que se
    desfaz, sem precisar lembrar qual era o nome original.
    """
    item = obter(sha)
    if item is None:
        raise FormatError("Este registro nao esta' no acervo.")
    # Uma linha so', e sem os caracteres que estragam nome de arquivo na
    # exportacao -- o apelido vira nome de arquivo la'.
    limpo = " ".join(str(nome or "").split())
    for proibido in '\\/:*?"<>|':
        limpo = limpo.replace(proibido, "-")
    limpo = limpo.strip(" .")[:APELIDO_MAXIMO]

    arquivo = _raiz() / sha / APELIDO
    if limpo and limpo != item.nome_do_arquivo:
        arquivo.write_text(json.dumps({"nome": limpo}, ensure_ascii=False,
                                      indent=2), encoding="utf-8")
        return limpo
    if arquivo.is_file():
        arquivo.unlink()
    return item.nome_do_arquivo


# ---------------------------------------------------------------------------
# As trincas: quais tres canais formam um conjunto trifasico
# ---------------------------------------------------------------------------
#
# Quais tres canais formam uma trinca sai do NOME deles, e nome de canal cada
# fabricante escreve como quer. Quando a deducao erra, 3I0, I1, I2 e a
# localizacao de falta erram junto -- na unidade certa, na ordem de grandeza
# certa, sem nada na tela denunciando.
#
# A chave e' o NOME do conjunto (`I*W`, `CURRENT I*`), e nao a posicao dele: a
# posicao e' o `q{i}` que os arranjos salvos usam, e amarrar a correcao a ela
# faria uma correcao mudar o alvo de outra.

TRINCAS = "trincas.json"


def trincas(sha: str) -> dict[str, dict[str, int]]:
    """As trincas que o usuario corrigiu neste registro. Vazio e' o normal."""
    arquivo = _raiz() / sha / TRINCAS
    if not arquivo.is_file():
        return {}
    try:
        cru = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    saida: dict[str, dict[str, int]] = {}
    for chave, valor in (cru or {}).items():
        limpo = _fases_validas(valor)
        if limpo:
            saida[str(chave)] = limpo
    return saida


def _fases_validas(valor) -> dict[str, int]:
    """`{"A": 3, "B": 4, "C": 5}` a partir do que a tela mandou.

    A tela manda texto, e o servidor nao confia nela: fase que nao e' A, B ou C
    some, e indice que nao e' inteiro tambem.
    """
    if not isinstance(valor, dict):
        return {}
    saida: dict[str, int] = {}
    for fase in ("A", "B", "C"):
        try:
            indice = int(valor[fase])
        except (KeyError, TypeError, ValueError):
            continue
        if indice >= 0:
            saida[fase] = indice
    return saida


def gravar_trincas(sha: str, escolhas: dict) -> dict[str, dict[str, int]]:
    """Grava as correcoes de trinca. Devolve o que ficou gravado.

    Escolha vazia para um conjunto APAGA a correcao dele, e a deducao volta a
    valer. E' como se desfaz, e por isso nao ha' botao de apagar em separado.
    """
    if obter(sha) is None:
        raise FormatError("Este registro nao esta' no acervo.")
    atuais = trincas(sha)
    for chave, valor in (escolhas or {}).items():
        limpo = _fases_validas(valor)
        if limpo:
            atuais[str(chave)] = limpo
        else:
            atuais.pop(str(chave), None)

    arquivo = _raiz() / sha / TRINCAS
    if atuais:
        arquivo.write_text(json.dumps(dict(sorted(atuais.items())),
                                      ensure_ascii=False, indent=2),
                           encoding="utf-8")
    elif arquivo.is_file():
        arquivo.unlink()
    return atuais


def _com_vinculos(registro: Record, sha: str) -> Record:
    """Aplica ao registro a correcao de fase que o usuario gravou.

    Mora aqui porque e' decisao humana gravada ao lado do registro, e precisa
    chegar ao `Record` antes de qualquer conta -- senao metade do programa
    veria a correcao e a outra metade nao.

    Ja houve uma segunda correcao aqui: o apelido que o usuario dava a cada
    trinca (`alta`, `baixa`), gravado em `rotulos.json`. Ela existia para
    CONSERTAR um palpite do programa, de quando a tela dizia qual era a alta.
    O programa nao palpita mais -- diz `[1]`, `[2]` e mostra de que canais
    aquilo saiu --, entao nao ha' o que consertar. O que sobraria era anotacao
    pessoal, que pertence ao relatorio e nao ao nome do canal.
    """
    registro.trincas_escolhidas = trincas(sha)
    escolhas = vinculos(sha)
    if not escolhas:
        return registro
    registro.analog_channels = tuple(
        replace(c, phase_escolhida=escolhas.get(c.index, c.phase_escolhida))
        for c in registro.analog_channels
    )
    return registro


def remover(sha: str) -> bool:
    """Tira o registro do acervo. Devolve se havia algo para tirar."""
    if obter(sha) is None:
        return False
    shutil.rmtree(_raiz() / sha, ignore_errors=True)
    return True
