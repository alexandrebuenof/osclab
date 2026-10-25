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
import re
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
    #: A relacao de transformacao declarada no arquivo, por grandeza. Vem de
    #: `primary`/`secondary` de CADA canal analogico, e so' aparece quando
    #: todos os canais daquela grandeza declaram a mesma: num registro com
    #: dois vaos, mostrar a de um deles como se fosse do arquivo inteiro seria
    #: o erro silencioso de sempre. Discordando, fica "varios".
    relacao_tc: str = ""
    relacao_tp: str = ""
    #: O modelo do equipamento, DEDUZIDO do que o arquivo declara em
    #: `rec_dev_id`. Ver `_modelo`.
    modelo: str = ""
    # --- o que o OscLab concluiu sobre o evento ---------------------------
    #: O tipo da falta que o classificador leu: `AG`, `BCG`, `ABC`… Vazio
    #: quando não há falta neste registro — e vazio AQUI quer dizer «olhei e
    #: não achei», porque o campo só existe depois de o classificador rodar.
    #: Ver `analysis/falta.py`.
    falta_tipo: str = ""
    #: `alta` quando corrente e tensão concordam, `media` com uma pista só,
    #: `baixa` quando as duas discordam. É a cor do selo na tela.
    falta_confianca: str = ""
    #: As evidências, em português. Vão para o painel, não para o cartão.
    falta_porques: tuple[str, ...] = ()
    falta_discordancias: tuple[str, ...] = ()
    #: O laço que o plano de impedância deve abrir — `AN`, `BC`…
    falta_laco: str = ""
    #: Na falta EVOLUTIVA, o tipo do começo; `falta_tipo` é o do fim. Vazio
    #: quando ela não mudou.
    falta_inicial: str = ""
    #: A sigla que o RELÉ gravou, para a tela pôr ao lado da nossa. Vazia nos
    #: formatos que não a trazem, que é o normal do COMTRADE.
    classificacao_do_rele: str = ""
    #: O digital de trip que subiu (`TRIP`, `MAIN : Gen. trip command`), ou
    #: `T na sigla do relé` quando só a classificação da SEL o diz. Vazio:
    #: nenhum trip à vista — o que NÃO prova que o relé restringiu.
    trip_sinal: str = ""
    #: Em quantos ms depois do início da falta ele subiu; `None` sem os dois.
    trip_ms: float | None = None

    #: Que versao do resumo gravou este `meta.json`.
    #:
    #: `meta.json` e' CACHE, e o cabecalho deste arquivo ja' dizia que ele pode
    #: ser refeito a qualquer momento. Faltava quem percebesse QUANDO refazer:
    #: ate' agora, um campo novo (TC, TP, modelo) nascia vazio para sempre nos
    #: registros ja' no acervo, e so' aparecia em quem reenviasse o arquivo.
    #: Com o numero aqui, `obter` refaz o resumo sozinho quando ele e' mais
    #: velho que esta versao -- e vazio volta a querer dizer "o arquivo nao
    #: declara", que e' o unico significado que ele pode ter.
    versao_do_resumo: int = 0

    def como_dicionario(self) -> dict:
        saida = asdict(self)
        # A classe de cor do selo sai daqui, e não do Jinja nem do JS: as
        # duas telas que mostram o selo (a tira do registro e o cartão do
        # acervo) leem a MESMA chave, e a regra mora num lugar só.
        saida["falta_cor"] = cor_da_falta(self.falta_tipo)
        saida["falta_dica"] = dica_da_falta(self)
        # O raio ao lado do selo: só se acende com trip à vista.
        saida["falta_trip"] = bool(self.trip_sinal)
        # O que o selo ESCREVE: `AB → ABG` na evolutiva. A cor é a do fim.
        saida["falta_sigla"] = (f"{self.falta_inicial} → {self.falta_tipo}"
                                if self.falta_inicial else self.falta_tipo)
        return saida


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


#: A versao do resumo que esta versao do programa grava. SOBE sempre que um
#: campo novo entra no `Item` -- e' o que faz o acervo inteiro se atualizar
#: sozinho na primeira vez que cada registro e' aberto.
#: Subiu para 2 em 20/10/2026, quando o resumo passou a trazer o tipo da
#: falta: sem subir, os registros já no acervo nasceriam sem selo para
#: sempre, e vazio deixaria de querer dizer «olhei e não achei».
#: Subiu para 3 em 21/10/2026: a bifásica C-A passou a se chamar `CA` (era
#: `AC`), e o selo gravado no resumo dos registros antigos ficaria velho.
#: E o mesmo 3 traz a classificação do relé lida do `.hdr` do COMTRADE.
#: 4 em 21/10/2026: a falta evolutiva (`falta_inicial`).
#: 5 em 22/10/2026: o modelo do SIPROTEC 5 («nº de série»).
#: 6 em 22/10/2026: o trip (`trip_sinal`, `trip_ms`), o raio do selo.
RESUMO_ATUAL = 6


def _so_o_numero(v: float) -> str:
    """`600.0` -> `600`; `11400.0` -> `11.400`; `11.4` -> `11,4`.

    Em pt-BR, e' o ponto que separa milhar: `11400 : 115` se le' errado, e
    relacao de TP e' justamente onde o milhar importa.
    """
    texto = f"{v:,.0f}" if float(v).is_integer() else f"{v:,.3f}".rstrip("0").rstrip(".")
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _relacao(canais) -> str:
    """A relacao declarada, quando ela e' UMA so'.

    Primario igual ao secundario quer dizer "nao declarada" -- e' o valor que o
    COMTRADE poe quando nao ha' relacao, e dividir um pelo outro daria 1:1,
    que nao e' relacao nenhuma, e' a falta dela.
    """
    vistas = {(c.primary, c.secondary) for c in canais
              if c.primary and c.secondary and c.primary != c.secondary}
    if not vistas:
        return ""
    if len(vistas) > 1:
        return "vários"
    primario, secundario = vistas.pop()
    return f"{_so_o_numero(primario)} : {_so_o_numero(secundario)}"


def relacoes_por_equipamento(registro: Record) -> list[dict]:
    """As relações de TC e TP, uma ficha por EQUIPAMENTO, quando há mais de uma.

    Com uma relação de TC e uma de TP a tira já diz tudo, e isto devolve `[]`.
    Com várias, cada ficha é o NOME que o próprio relé dá ao equipamento e a
    relação dele: `TC BUC 69kV` → `TC 400 : 5`, `TPBP 34-5kV` → `TP 34.500 : 115`.
    Maquete 5 de «relacoes-10», escolha dele em 22/10/2026.

    O nome é o que o arquivo escreve, e só isso:

    - com `:` no nome do canal (o SIPROTEC escreve `TC BUC 69kV:I A`), é o
      que vem antes dos dois-pontos;
    - sem ele (`IAS`, `IBS`, `ICS` da SEL), é o nome da TRINCA, a fase trocada
      por `*` (`I*S`) — o mesmo do editor de grupos;
    - canal solto, fora de trinca, fica com o próprio nome.

    Nunca emparelha TC com TP, nem diz alta ou baixa: a ficha afirma só o que o
    canal declara. Canais `1 : 1` não entram — é a falta de relação, não uma.
    """
    from osclab.formats import conjuntos

    if "vários" not in _relacoes(registro):
        return []

    do_conjunto: dict[int, str] = {}
    for cj in conjuntos.de_registro(registro):
        for indice in cj.canais.values():
            do_conjunto.setdefault(indice, cj.nome)

    fichas: dict[tuple, dict] = {}
    for indice, canal in enumerate(registro.analog_channels):
        if not (canal.primary and canal.secondary and canal.primary != canal.secondary):
            continue
        unidade = (canal.unit or "").strip().upper()
        if unidade.endswith("A"):
            tipo = "TC"
        elif unidade.endswith("V"):
            tipo = "TP"
        else:
            continue
        nome = canal.name or ""
        if ":" in nome:
            equipamento = nome.split(":", 1)[0].strip()
        else:
            equipamento = do_conjunto.get(indice, nome.strip())
        relacao = f"{_so_o_numero(canal.primary)} : {_so_o_numero(canal.secondary)}"
        chave = (equipamento, tipo, relacao)
        ficha = fichas.setdefault(chave, {"equipamento": equipamento, "tipo": tipo,
                                          "relacao": relacao, "canais": []})
        ficha["canais"].append(nome)
    return list(fichas.values())


def _relacoes(registro: Record) -> tuple[str, str]:
    """TC e TP, pela unidade de cada canal."""
    def da(letra: str):
        return [c for c in registro.analog_channels
                if (c.unit or "").strip().upper().endswith(letra)]
    return _relacao(da("A")), _relacao(da("V"))


#: O número de série que o SIPROTEC 5 grava no `rec_dev_id`: `BM` e dígitos.
_SERIE_SIPROTEC = re.compile(r"^BM\d{6,}$")


def _modelo(equipamento: str, registro: Record | None = None) -> str:
    """O modelo, deduzido do que o arquivo declara em `rec_dev_id`.

    A SEL grava a FID inteira ali
    (`FID=SEL-451-5-R316-V1-Z021012-D20160504`), e o modelo e' o que vem antes
    da revisao `-R<numero>`. Qualquer outro formato volta inteiro: dedutor que
    nao reconhece o que esta' lendo nao inventa -- devolve o que achou.

    O SIPROTEC 5 grava ali o NÚMERO DE SÉRIE (`BM2502009181`), e a tela o
    mostrava como se fosse modelo. Com os canais no jeito dele
    (`grupo de função:sinal`, `TC BUC 69kV:I A`), sai «SIPROTEC 5 · nº de série
    BM…»: a família se afirma, o modelo (7UT85? 7SJ82?) não — nada no arquivo
    o diz (22/10/2026).
    """
    texto = (equipamento or "").strip()
    if (registro is not None and _SERIE_SIPROTEC.match(texto)
            and any(":" in (c.name or "") for c in registro.analog_channels)):
        return f"SIPROTEC 5 · nº de série {texto}"
    if texto.upper().startswith("FID="):
        texto = texto[4:]
    achado = re.match(r"^([A-Za-z0-9\-]+?)-R\d", texto)
    return achado.group(1) if achado else texto


def _classificar(registro: Record, do_rele: str = "") -> dict:
    """O veredito do classificador, ou campos vazios quando não dá.

    Roda UMA vez, na importação, e fica no `meta.json`: é o que deixa o
    acervo mostrar o tipo da falta sem abrir quarenta arquivos. Nunca derruba
    o envio — um registro que o classificador não entende continua entrando.
    """
    vazio = {"falta_tipo": "", "falta_confianca": "", "falta_porques": (),
             "falta_discordancias": (), "falta_laco": "", "falta_inicial": "",
             **_trip(registro, do_rele, None)}
    try:
        from osclab.analysis import falta as falta_mod
        from osclab.formats import conjuntos

        achados = [c for c in conjuntos.de_registro(registro) if not c.sem_sinal]
        corrente = next((c for c in achados if c.grandeza == "I"), None)
        if corrente is None:
            return vazio
        tensao = next((c for c in achados if c.grandeza == "V"), None)
        v = falta_mod.classificar(registro, corrente.canais,
                                  tensao.canais if tensao else None)
        return {
            "falta_tipo": v.tipo,
            "falta_confianca": v.confianca,
            "falta_porques": tuple(v.porques),
            "falta_discordancias": tuple(v.discordancias),
            "falta_laco": v.laco if v.tipo else "",
            "falta_inicial": v.tipo_inicial,
            **_trip(registro, do_rele, v.instante if v.tipo else None),
        }
    except Exception:            # noqa: BLE001 — importar não pode falhar por isto
        return vazio


def _trip(registro: Record, do_rele: str, inicio: int | None) -> dict:
    """O trip, pelos digitais; na falta deles, pelo «T» da sigla da SEL."""
    from osclab.analysis import falta as falta_mod

    try:
        achado = falta_mod.disparo_do_rele(registro)
    except Exception:            # noqa: BLE001 — importar não pode falhar por isto
        achado = None
    if achado is None:
        sinal = "T na sigla do relé" if falta_mod.trip_na_sigla(do_rele) else ""
        return {"trip_sinal": sinal, "trip_ms": None}
    ms = None
    tempo = registro.time
    if inicio is not None and max(inicio, achado.amostra) < tempo.size:
        ms = round(float(tempo[achado.amostra] - tempo[inicio]) * 1000.0, 1)
    return {"trip_sinal": achado.sinal, "trip_ms": ms}


def cor_da_falta(tipo: str) -> str:
    """A classe de cor do selo: as fases da falta, na ordem do ofício.

    `fase-c` numa CG, `fase-ca` numa CA ou CAG, `fase-abc` numa trifásica, e
    vazio sem falta. A terra não muda a cor — ela está escrita na sigla.
    Escolha dele, 21/10/2026 (maquete «selo da falta», esquema 2).
    """
    letras = frozenset(c for c in (tipo or "").upper() if c in "ABC")
    nomes = {frozenset("A"): "a", frozenset("B"): "b", frozenset("C"): "c",
             frozenset("AB"): "ab", frozenset("BC"): "bc", frozenset("CA"): "ca",
             frozenset("ABC"): "abc"}
    return f"fase-{nomes[letras]}" if letras in nomes else ""


_CONFIANCA = {
    "alta": "alta — corrente e tensão concordam",
    "media": "média — só uma das duas pistas",
    "baixa": "baixa — corrente e tensão discordam",
}


def dica_da_falta(item) -> str:
    """O hover do selo: o que o OscLab concluiu, com que confiança, e o que o
    relé gravou — ou que ele não gravou nada. Pedido dele, 21/10/2026.

    Uma frase por linha. Montada aqui, e não em cada tela, pela mesma razão
    da cor: a tira do registro e o cartão do acervo dizem a mesma coisa.
    """
    from osclab.analysis import falta as falta_mod

    linhas = []
    if item.falta_tipo:
        linhas.append(f"OscLab: {item.falta_inicial} evoluindo para {item.falta_tipo}"
                      if item.falta_inicial else f"OscLab: {item.falta_tipo}")
        linhas.extend(f"  {p}" for p in item.falta_porques)
        if item.falta_confianca in _CONFIANCA:
            linhas.append(f"Confiança: {_CONFIANCA[item.falta_confianca]}")
    else:
        linhas.append("OscLab: sem falta — nenhuma descontinuidade nas correntes")
    rele = (item.classificacao_do_rele or "").strip()
    if not rele:
        linhas.append("Relé: não informou o tipo da falta neste arquivo")
    else:
        linhas.append(f"Relé: {rele}" + ("  (o T solto é TRIP, não terra)"
                                         if rele.upper().endswith(" T") else ""))
        if not falta_mod.rele_concorda(item.falta_tipo, item.falta_inicial, rele):
            linhas.append("O relé DISCORDA do OscLab — vale olhar as duas pistas.")
    sinal = getattr(item, "trip_sinal", "")
    ms = getattr(item, "trip_ms", None)
    if sinal:
        linhas.append(f"⚡ Trip: {sinal}" + (f", {ms:.1f} ms depois do início da falta"
                                            .replace(".", ",") if ms is not None else ""))
    else:
        linhas.append("Sem trip à vista: nenhum digital de trip subiu neste registro")
    return "\n".join(linhas)


def _resumir(sha: str, nome: str, arquivos: list[str], registro: Record) -> Item:
    tc, tp = _relacoes(registro)
    # O que o RELÉ concluiu: no `.CEV` vem no cabeçalho; no COMTRADE, só no
    # `.hdr` — quando o relé escreve (a SEL escreve).
    do_rele = registro.classificacao_do_rele
    if not do_rele:
        from osclab.formats import ajustes
        do_rele = ajustes.classificacao_no_hdr(_raiz() / sha, arquivos)
    return Item(
        **_classificar(registro, do_rele),
        classificacao_do_rele=do_rele,
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
        relacao_tc=tc,
        relacao_tp=tp,
        modelo=_modelo(registro.device_id, registro),
        versao_do_resumo=RESUMO_ATUAL,
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
        _gravar_resumo(pasta, item)
        _tirar_da_antessala(base)
        resultado.aceitos.append(item)

    return resultado


# ---------------------------------------------------------------------------
# Consultar
# ---------------------------------------------------------------------------

def _gravar_resumo(pasta: Path, item: Item) -> None:
    """O `meta.json` de um registro. Falhar aqui nao pode derrubar nada: ele e'
    cache, e sem ele a lista so' fica mais lenta."""
    try:
        (pasta / "meta.json").write_text(
            json.dumps(item.como_dicionario(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def _refazer_resumo(sha: str, item: Item) -> Item:
    """Refaz o resumo de um registro cujo `meta.json` e' de uma versao antiga.

    Le' o arquivo de novo -- e' o unico jeito de saber TC, TP e o que mais
    vier. Se a leitura falhar, devolve o resumo velho: um campo faltando e'
    melhor que uma tela que nao abre.

    Le' pelo CAMINHO, e nao por `ler(sha)`: `ler` passa por `obter`, que e'
    quem chama esta funcao -- a volta inteira era uma recursao infinita, e o
    registro com cache velho abria com erro 500. E' tambem o mesmo caminho que
    o `_absorver` usa quando o registro entra, logo o resumo refeito sai igual
    ao que teria saido na entrada.
    """
    try:
        principal = _principal(_raiz() / sha)
        if principal is None:
            return item
        registro = registry.read(principal)
    except (FormatError, OSError):
        return item
    novo = _resumir(sha, item.nome_do_arquivo or item.nome,
                    list(item.arquivos), registro)
    # O que e' decisao de quem usa nao se refaz a partir do arquivo.
    novo = replace(novo, adicionado_em=item.adicionado_em or novo.adicionado_em)
    _gravar_resumo(_raiz() / sha, novo)
    return novo


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
    # Cache velho se refaz sozinho. Ver `versao_do_resumo`.
    if item.versao_do_resumo < RESUMO_ATUAL:
        item = _refazer_resumo(sha, item)
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
#: O que se pode escolher para um canal: as fases, o neutro, os LACOS (`AB`,
#: `BC`, `CA` — a medicao entre duas fases, ver `formats/fases.LACOS`) e `-`
#: (explicitamente "nenhuma"). Uma lista so' para ler e para gravar.
ESCOLHAS_DE_FASE = ("A", "B", "C", "N", "AB", "BC", "CA", "-")


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
        # Os LACOS entram junto das fases: `AB`, `BC`, `CA` e' a medicao
        # entre duas fases, e o usuario precisa poder dize-la. Ver
        # `formats/fases.LACOS`.
        if texto in ESCOLHAS_DE_FASE:
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
        # A MESMA lista que `vinculos` le' (e a tela oferece): sem os lacos
        # aqui, escolher `AB` era apagado em silencio e a deducao voltava.
        if texto in ESCOLHAS_DE_FASE:
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

    A tela manda texto, e o servidor nao confia nela: vaga que nao existe some,
    e indice que nao e' inteiro tambem.

    Sao DUAS bases, e nunca as duas juntas: `A/B/C` quando o rele mediu contra
    o neutro, `AB/BC/CA` quando mediu entre fases. Uma correcao que trouxesse
    as duas montaria uma trinca que soma volt de fase com volt de linha -- e
    Fortescue sobre essa mistura devolve tres numeros plausiveis e sem
    significado nenhum. Vence a que vier COMPLETA; com as duas completas vence
    a de fase, a mesma regra de `formats/conjuntos._agrupar`.
    """
    if not isinstance(valor, dict):
        return {}

    def ler(vagas):
        saida: dict[str, int] = {}
        for fase in vagas:
            try:
                indice = int(valor[fase])
            except (KeyError, TypeError, ValueError):
                continue
            if indice >= 0:
                saida[fase] = indice
        return saida

    em_fase = ler(("A", "B", "C"))
    if len(em_fase) == 3:
        return em_fase
    em_delta = ler(("AB", "BC", "CA"))
    if len(em_delta) == 3:
        return em_delta
    return em_fase or em_delta


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


# ---------------------------------------------------------------------------
# Os vinculos de potencia: que trinca de corrente casa com que trinca de tensao
# ---------------------------------------------------------------------------
#
# A chave e' o NOME do conjunto, pela mesma razao de TRINCAS: a posicao e' o
# `q{i}` dos arranjos salvos, e amarrar a ela faria um vinculo mudar de alvo.
#
# Gravado nos DOIS sentidos. Vincular G1 a G3 e' a mesma afirmacao que
# vincular G3 a G1 -- sao o mesmo vao --, e guardar so' um lado obrigaria toda
# leitura a procurar nos dois.

POTENCIA = "potencia.json"

#: Em que base as tensoes de um vinculo estao. `fase` e' fase-neutro.
BASES_DE_TENSAO = ("fase", "linha")


def vinculos_de_potencia(sha: str) -> dict:
    """Os vinculos que o usuario fez neste registro. Vazio e' o normal."""
    arquivo = _raiz() / sha / POTENCIA
    if not arquivo.is_file():
        return {}
    try:
        cru = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    saida: dict = {}
    for chave, valor in (cru or {}).items():
        if not isinstance(valor, dict):
            continue
        com = str(valor.get("com") or "").strip()
        if not com:
            continue
        base = str(valor.get("base") or "fase")
        saida[str(chave)] = {"com": com,
                             "base": base if base in BASES_DE_TENSAO else "fase"}
    return saida


def gravar_vinculo_de_potencia(sha: str, pedido: dict) -> dict:
    """Cria ou apaga UM vinculo. Devolve o mapa inteiro que ficou gravado.

    `{"de": "I*W", "com": "V*Y", "base": "fase"}` cria; `com` vazio apaga o
    vinculo de `de` -- e apaga tambem o do outro lado, senao sobraria metade
    de um par apontando para o nada.
    """
    if obter(sha) is None:
        raise FormatError("Este registro nao esta' no acervo.")
    atuais = vinculos_de_potencia(sha)
    de = str((pedido or {}).get("de") or "").strip()
    if not de:
        raise FormatError("Nao disseram qual conjunto vincular.")
    com = str((pedido or {}).get("com") or "").strip()
    base = str((pedido or {}).get("base") or "fase")
    if base not in BASES_DE_TENSAO:
        base = "fase"

    # Apagar: tira os dois lados. Um vinculo e' um par, nao duas anotacoes.
    antigo = atuais.pop(de, None)
    if antigo and atuais.get(antigo["com"], {}).get("com") == de:
        atuais.pop(antigo["com"], None)
    if com:
        # Trocar de par desfaz o par ANTERIOR do outro lado, pelo mesmo
        # motivo: ninguem fica vinculado a quem nao o vincula de volta.
        velho = atuais.pop(com, None)
        if velho and atuais.get(velho["com"], {}).get("com") == com:
            atuais.pop(velho["com"], None)
        atuais[de] = {"com": com, "base": base}
        atuais[com] = {"com": de, "base": base}

    arquivo = _raiz() / sha / POTENCIA
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
    registro.vinculos_de_potencia = vinculos_de_potencia(sha)
    # As placas de E/S que o `.hdr` declara: os digitais que não existem no
    # relé, e que ele grava assim mesmo, não podem passar por entrada.
    from osclab.formats import ajustes as ajustes_mod
    try:
        pasta = pasta_do_registro(sha)
        registro.digitais_sem_placa = ajustes_mod.digitais_sem_placa(
            pasta, [p.name for p in Path(pasta).iterdir()],
            [c.name for c in registro.status_channels])
    except OSError:
        pass
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
