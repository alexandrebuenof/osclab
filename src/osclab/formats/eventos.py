"""A LISTA DE EVENTOS que o relé grava junto com a oscilografia.

Um digital de COMTRADE diz QUANDO um sinal mudou; a lista de eventos diz isso
e mais o que o relé chamou de cada coisa — partida, trip, abertura do
disjuntor, tempo morto — em texto, na ordem em que aconteceu. Com 582
digitais na tela a sequência de um evento se perde; 120 linhas em ordem são a
história dele. Plano em `docs/log-de-eventos.md`.

## De onde vem

Por enquanto, do que já vem DENTRO do registro: o `.hdr` da Schneider
(MiCOM P139, P437, P439…), que traz a lista inteira. Dois dialetos no parque,
os dois conferidos nos 125 `.hdr` do banco (02/11/2026):

    Easergy Studio («Fault log (FT_RC)»):
    Line  |     tAbs     | tRel (s) | xxx.yyy | Description                | Value
      1   | 21:09:37.344 | 0.000    | 113.007 | GOOSE Ext.Dev34 interm.pos | Present

    conversor SFD → COMTRADE, mais antigo:
        tAbs     |   tRel (s)   | Description                         | Value
    09:10:51.950 | 00:00:00.000 | 113.019 GOOSE  Ext.Dev37 interm.pos | Present

O `.txt` que acompanha o mesmo registro é o terceiro jeito de escrever a
mesma tabela (`tRel(s)` em segundos, o endereço junto da descrição), e o
leitor o entende também — é por ele que vai entrar a importação.

Por isso a tabela é lida pelas COLUNAS e não por posição: a primeira coluna
com cara de hora é o `tAbs`, a seguinte é o `tRel` (segundos ou
`hh:mm:ss.mmm`), o `xxx.yyy` é o endereço, more ele na coluna própria ou no
começo da descrição, e a última coluna é o valor.

## O tempo

O `tRel` conta do instante que o cabeçalho diz em «Reference time for tRel».
Nos 125 do banco é «Record start time», que é a primeira amostra do COMTRADE:
conferido no P439 de 30/01/2023, o `.cfg` começa às 21:09:37.344 e o evento
de tRel 0,000 traz esse mesmo tAbs. Uma referência que o programa não conhece
não vira palpite: a lista sai sem tempo (`referencia_conhecida = False`) e a
tela avisa em vez de pôr o cursor no lugar errado.

## O que NÃO se faz aqui

Nada se traduz, nada se classifica: a descrição vai como o relé escreveu.
É a mesma regra do painel de lógica — o que está na tela é o que está no
arquivo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: As seções da tabela de EVENTOS, como cada dialeto as titula.
_SECAO_EVENTOS = re.compile(r"^\s*(list of events|fault signals)\s*$", re.I)
#: As seções de DADOS medidos pelo relé (tipo, localização, corrente).
_SECAO_DADOS = re.compile(r"^\s*(measured data|measured fault data|fault data)\s*$", re.I)
_HORA = re.compile(r"^\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?$")
_SEGUNDOS = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_ENDERECO = re.compile(r"^\d{3}\.\d{3}$")
_ENDERECO_NA_FRENTE = re.compile(r"^(\d{3}\.\d{3})\s+(.*)$")
_REFERENCIA = re.compile(r"reference\s+time\s+for\s+trel\s*:?\s*(.+?)\s*$", re.I)
#: A única referência conhecida: a primeira amostra do registro.
_INICIO_DO_REGISTRO = re.compile(r"record(ing)?\s+start", re.I)
#: Quanto das linhas com hora tem de se deixar ler para a tabela valer.
#: Nos 250 `.hdr` do banco são todas.
MINIMO_LIDO = 0.8
#: O texto cru vai à tela até este tamanho: o `.hdr` maior do banco tem
#: 68 kB; um arquivo de dez megas travaria o painel.
LIMITE_DO_CRU = 400_000


@dataclass(frozen=True)
class Evento:
    """Uma linha da lista, como o relé escreveu."""

    #: Segundos desde a primeira amostra do registro (o eixo da tela).
    t: float
    #: O `tAbs` como veio, só a hora: o relé não escreve a data na linha.
    hora: str
    endereco: str
    descricao: str
    valor: str


@dataclass(frozen=True)
class Lista:
    eventos: tuple[Evento, ...] = ()
    #: O bloco de dados medidos (tipo da falta, localização…), na mesma forma.
    dados: tuple[Evento, ...] = ()
    #: O texto de «Reference time for tRel», como veio.
    referencia: str = ""
    referencia_conhecida: bool = True
    #: O arquivo de onde a lista saiu.
    de: str = ""
    avisos: tuple[str, ...] = field(default_factory=tuple)
    #: O arquivo como veio. Vai SEMPRE junto: é o que a tela mostra quando a
    #: tabela não foi reconhecida, e o botão «como veio» quando foi — a saída
    #: para o caso de o programa achar que entendeu e ter lido as colunas
    #: trocadas (pedido dele, 02/11/2026).
    cru: str = ""

    @property
    def reconhecida(self) -> bool:
        return bool(self.eventos)


def _segundos(texto: str) -> float | None:
    """`0.192` ou `00:00:00.192` em segundos; `None` se não for nenhum."""
    texto = texto.strip().replace(",", ".")
    if _SEGUNDOS.match(texto):
        return float(texto)
    if _HORA.match(texto):
        h, m, s = texto.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return None


def _linha(campos: list[str]) -> Evento | None:
    """Uma linha da tabela, ou `None` se ela não é linha de dado."""
    i = next((k for k, c in enumerate(campos) if _HORA.match(c)), None)
    if i is None or i + 2 >= len(campos):
        return None
    t = _segundos(campos[i + 1])
    if t is None:
        return None
    resto = campos[i + 2:]
    endereco = ""
    if len(resto) >= 3 and _ENDERECO.match(resto[0]):
        endereco, resto = resto[0], resto[1:]
    descricao = resto[0]
    valor = resto[-1] if len(resto) > 1 else ""
    if not endereco:
        achado = _ENDERECO_NA_FRENTE.match(descricao)
        if achado:
            endereco, descricao = achado.group(1), achado.group(2)
    return Evento(t=t, hora=campos[i], endereco=endereco,
                  descricao=descricao.rstrip(), valor=valor.strip())


def de_texto(texto: str, de: str = "") -> Lista | None:
    """A lista que um texto traz, ou `None` quando ele não traz nenhuma."""
    eventos: list[Evento] = []
    dados: list[Evento] = []
    referencia = ""
    secao = None
    com_hora = 0
    for bruta in texto.splitlines():
        achado = _REFERENCIA.search(bruta)
        if achado and not referencia:
            referencia = achado.group(1)
            continue
        if _SECAO_EVENTOS.match(bruta):
            secao = eventos
            continue
        if _SECAO_DADOS.match(bruta):
            secao = dados
            continue
        if secao is None or "|" not in bruta:
            continue
        campos = [c.strip() for c in bruta.split("|")]
        if secao is eventos and any(_HORA.match(c) for c in campos):
            com_hora += 1
        evento = _linha(campos)
        if evento is not None:
            secao.append(evento)
    # Linha com hora que não se deixou ler é sinal de dialeto que não
    # conhecemos: uma tabela pela metade, ou com colunas em outra ordem, é
    # pior que nenhuma — a tela mostra o arquivo como veio.
    if not eventos or len(eventos) < MINIMO_LIDO * com_hora:
        return None
    conhecida = not referencia or bool(_INICIO_DO_REGISTRO.search(referencia))
    avisos = () if conhecida else (
        f"o relé conta o tempo de «{referencia}», e o programa ainda não sabe "
        "onde isso cai no registro: os eventos ficam sem ligação com o cursor",)
    return Lista(eventos=tuple(eventos), dados=tuple(dados), referencia=referencia,
                 referencia_conhecida=conhecida, de=de, avisos=avisos,
                 cru=texto[:LIMITE_DO_CRU])


#: Onde procurar, na ordem: o `.hdr` vem no acervo junto com o registro.
_ONDE_PROCURAR = (".hdr", ".txt")


def do_registro(pasta: Path, arquivos) -> Lista | None:
    """A lista de eventos que veio com o registro.

    Sem tabela reconhecida, mas com um arquivo de texto ao lado, devolve a
    lista VAZIA com o arquivo cru: a tela mostra o texto como veio em vez de
    dizer que não há nada. `None` só quando não há arquivo de texto nenhum.
    """
    from osclab.formats.ajustes import _texto

    sem_tabela = None
    for extensao in _ONDE_PROCURAR:
        for arquivo in sorted(arquivos or ()):
            if not str(arquivo).lower().endswith(extensao):
                continue
            caminho = Path(pasta) / arquivo
            if not caminho.is_file():
                continue
            texto = _texto(caminho)
            try:
                lista = de_texto(texto, de=str(arquivo))
            except Exception:  # noqa: BLE001 — formato estranho vira texto cru, nunca erro
                lista = None
            if lista is not None:
                return lista
            if sem_tabela is None and texto.strip():
                sem_tabela = Lista(de=str(arquivo), cru=texto[:LIMITE_DO_CRU])
    return sem_tabela
