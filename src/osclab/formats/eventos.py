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
from datetime import date, datetime
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
LIMITE_DO_CRU = 2_000_000   # o .eev da GE passa de 800 kB


@dataclass(frozen=True)
class Evento:
    """Uma linha da lista, como o relé escreveu."""

    #: Segundos desde a primeira amostra do registro (o eixo da tela).
    #: `None` numa lista de hora ABSOLUTA: ali o `t` só sai depois de casar
    #: a hora do evento com a do registro (`plot/eventos.py`).
    t: float | None
    #: O `tAbs` como veio, só a hora: o relé não escreve a data na linha.
    hora: str
    endereco: str
    descricao: str
    valor: str
    # --- listas que vêm À PARTE do registro (importadas na janela) ---------
    #: Data e hora absolutas, como lidas. Só nas listas de hora absoluta.
    quando: datetime | None = None
    #: A data como veio no arquivo (texto).
    data: str = ""
    #: O relé que gravou a linha, quando o arquivo junta vários (`.eev`).
    fonte: str = ""
    #: O número do evento, como o relé numerou.
    numero: str = ""
    #: O operando que causou o evento (`.eev`: o que vem entre parênteses).
    operando: str = ""
    #: A linha do arquivo de onde saiu (1 = primeira): liga a tabela ao texto.
    linha: int = 0
    #: As medidas que o relé gravou junto com o evento (`.eev`), na ordem de
    #: `Lista.colunas_extras`.
    extras: tuple[str, ...] = ()


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
    # --- como o leitor entendeu o arquivo ------------------------------------
    #: Como o leitor entendeu o arquivo, em palavras, para a tela dizer.
    formato: str = ""
    #: `relativo` (o `tRel` conta da primeira amostra) ou `absoluto` (data e
    #: hora de relógio, que precisam ser casadas com as do registro).
    tempo: str = "relativo"
    colunas_extras: tuple[str, ...] = ()
    #: Os relés que o arquivo junta, na ordem em que aparecem.
    fontes: tuple[str, ...] = ()
    #: A ordem da data: `DMA`, `MDA` ou `AMD`, e de onde ela saiu.
    ordem_da_data: str = ""
    origem_da_ordem: str = ""
    #: Quantas casas decimais de segundo o relé escreve (3 = ms, 6 = µs).
    casas: int = 3

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
    for n_linha, bruta in enumerate(texto.splitlines(), 1):
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
            secao.append(_com_linha(evento, n_linha))
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
                 cru=texto[:LIMITE_DO_CRU],
                 formato="lista de eventos do .hdr da Schneider (MiCOM)")


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


# ===========================================================================
# As listas que vêm À PARTE do registro (10/11/2026).
#
# Três portas, e nenhuma depende de reconhecer o fabricante para funcionar:
#
#   `.eev` da GE (EnerVista)   CSV com cabeçalho próprio; junta VÁRIOS relés
#                              num arquivo só e grava as medidas no instante
#                              de cada evento. Formato em docs/log-de-eventos.md.
#   texto com data e hora      SER da SEL, SUCESOS da Ingeteam, ou qualquer
#   em cada linha              outro: lido pelas COLUNAS (a que tem cara de
#                              data, a que tem cara de hora, a de estado), não
#                              pela posição — igual ao leitor da Schneider.
#   o resto                    vai como veio, sem ligação com o cursor.
#
# Hora de relógio NÃO é tempo da tela: o `t` dessas listas sai depois, em
# `plot/eventos.py`, casando a hora do evento com a do registro — com o fuso
# que o arquivo não declara virando campo para digitar.
# ===========================================================================

def _com_linha(evento: Evento, n: int) -> Evento:
    from dataclasses import replace
    return replace(evento, linha=n)


_MESES = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_QUANDO_GE = re.compile(
    r"^([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?$")
_CAUSA_GE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")
_ESTADO_NO_FIM = re.compile(r"^(.*\S)\s+(On|Off)$")


def _fracao(texto: str | None) -> int:
    """`.440664` → microssegundos."""
    return int((texto or "0").ljust(6, "0")[:6])


def eh_eev(texto: str) -> bool:
    cabeca = texto.lstrip("﻿")[:400]
    return cabeca.startswith("Source,") and "CauseOfEvent" in cabeca and "Date/Time" in cabeca


def de_eev(texto: str, de: str = "") -> Lista | None:
    """O registrador de eventos da GE, exportado pelo EnerVista (`.eev`).

    Um bloco por relé, cada um com o seu cabeçalho; dentro do bloco, do mais
    NOVO para o mais velho. Cada linha: relé, data e hora com microssegundo,
    número do evento, a causa (`NOME On (operando)`), um código hexadecimal e
    as medidas do relé naquele instante. Nada disso diz o fuso.
    """
    if not eh_eev(texto):
        return None
    eventos: list[Evento] = []
    extras: tuple[str, ...] = ()
    fontes: list[str] = []
    ilegiveis = 0
    for n, bruta in enumerate(texto.lstrip("﻿").splitlines(), 1):
        if not bruta.strip():
            continue
        campos = [c.strip() for c in bruta.split(",")]
        if campos[0] == "Source":
            extras = tuple(campos[5:])
            continue
        if len(campos) < 5:
            ilegiveis += 1
            continue
        achado = _QUANDO_GE.match(campos[1])
        mes = _MESES.get(achado.group(1).lower()) if achado else None
        if not achado or not mes:
            ilegiveis += 1
            continue
        _, dia, ano, h, m, seg, fr = achado.groups()
        quando = datetime(int(ano), mes, int(dia), int(h), int(m), int(seg), _fracao(fr))
        causa = campos[3]
        operando = ""
        c = _CAUSA_GE.match(causa)
        if c:
            causa, operando = c.group(1), c.group(2)
        valor = ""
        e = _ESTADO_NO_FIM.match(causa)
        if e:
            causa, valor = e.group(1), e.group(2)
        fonte = campos[0]
        if fonte not in fontes:
            fontes.append(fonte)
        data_txt, _, hora_txt = campos[1].rpartition(" ")
        eventos.append(Evento(
            t=None, hora=hora_txt, endereco=campos[4], descricao=causa, valor=valor,
            quando=quando, data=data_txt, fonte=fonte, numero=campos[2],
            operando=operando, linha=n, extras=tuple(campos[5:5 + len(extras)])))
    if not eventos or ilegiveis > (1 - MINIMO_LIDO) * (len(eventos) + ilegiveis):
        return None
    avisos = ("o .eev não diz o fuso da hora: o deslocamento até o registro é "
              "sugerido ou digitado, nunca lido",)
    return Lista(eventos=tuple(eventos), de=de, avisos=avisos, cru=texto[:LIMITE_DO_CRU],
                 formato="registrador de eventos da GE, exportado pelo EnerVista (.eev)",
                 tempo="absoluto", colunas_extras=extras, fontes=tuple(fontes), casas=6)


# --- texto qualquer, com data e hora em cada linha -------------------------

_DATA_LIVRE = re.compile(r"(?<![\d:])(\d{1,4})[/.-](\d{1,2})[/.-](\d{2,4})(?![\d:])")
_HORA_LIVRE = re.compile(r"(?<![\d.])(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?(?![\d])")
#: Os estados que um relé escreve na coluna de valor. Lista de PALAVRAS, não
#: de fabricantes: serve a quem nunca vimos.
_ESTADOS = re.compile(
    r"^(asserted|deasserted|on|off|set|reset|start|end|pickup|dropout|"
    r"activado|desactivado|activo|inactivo|activada|desactivada|alarma|"
    r"ativado|desativado|ativo|inativo|aberto|fechado|abierto|cerrado|"
    r"open|closed?|present|absent|normal|0|1)$", re.I)
_CABECA_DE_COLUNAS = re.compile(r"\b(date|time|fecha|hora|data)\b", re.I)


def _separar(linha: str) -> list[str]:
    for sep in (";", "\t", "|"):
        if sep in linha:
            return [c.strip() for c in linha.split(sep)]
    return [c.strip() for c in re.split(r"\s{2,}", linha.strip())]


def _data(trinca: tuple[str, str, str], ordem: str) -> date:
    a, b, c = (int(x) for x in trinca)
    if ordem == "AMD":
        ano, mes, dia = a, b, c
    elif ordem == "MDA":
        mes, dia, ano = a, b, c
    else:
        dia, mes, ano = a, b, c
    if ano < 100:
        ano += 2000
    return date(ano, mes, dia)


def _ordem_da_data(trincas: list[tuple[str, str, str]], referencia: date | None):
    """`(ordem, origem)` da data. Ano de quatro dígitos na frente decide;
    um número maior que 12 decide; senão a data é AMBÍGUA, e a escolha é a
    que cai mais perto da data do registro — sugerida, nunca afirmada."""
    if any(len(a) == 4 for a, _, _ in trincas):
        return "AMD", "lido"
    if any(int(a) > 12 for a, _, _ in trincas):
        return "DMA", "lido"
    if any(int(b) > 12 for _, b, _ in trincas):
        return "MDA", "lido"
    if referencia is None:
        return "DMA", "sugerido"
    melhor = None
    for ordem in ("DMA", "MDA"):
        try:
            d = _data(trincas[0], ordem)
        except ValueError:
            continue
        dist = abs((d - referencia).days)
        if melhor is None or dist < melhor[0]:
            melhor = (dist, ordem)
    return (melhor[1] if melhor else "DMA"), "sugerido"


def _nome_do_formato(texto: str) -> str:
    cabeca = texto[:4000].upper()
    if "ELEMENT" in cabeca and "STATE" in cabeca:
        return "texto com data e hora por linha (colunas de um SER da SEL)"
    if "SUCESO" in cabeca:
        return "texto com data e hora por linha (colunas de SUCESOS da Ingeteam)"
    return "texto com data e hora por linha"


def de_texto_com_hora(texto: str, de: str = "", referencia: date | None = None,
                      ordem: str = "") -> Lista | None:
    """Qualquer texto em que cada evento é UMA linha com data e hora.

    Se houver uma linha de títulos (`DATE`, `TIME`, `Fecha`, `Hora`…), só o
    que vem depois dela conta — o cabeçalho do SER também tem data e hora e
    não é evento. `ordem` (`DMA`, `MDA`, `AMD`) é a escolha do usuário; vazio
    deduz.
    """
    linhas = texto.lstrip("﻿").splitlines()
    inicio = 0
    for i, bruta in enumerate(linhas):
        if len(_CABECA_DE_COLUNAS.findall(bruta)) >= 2 and not _HORA_LIVRE.search(bruta):
            inicio = i + 1
            break
    crus = []
    com_hora = 0
    for n, bruta in enumerate(linhas[inicio:], inicio + 1):
        h = _HORA_LIVRE.search(bruta)
        if not h:
            continue
        com_hora += 1
        d = _DATA_LIVRE.search(bruta)
        if not d:
            continue
        resto = bruta[:d.start()] + "  " + bruta[d.end():h.start()] + "  " + bruta[h.end():]
        campos = [c for c in _separar(resto) if c]
        numero = ""
        if campos and campos[0].isdigit():
            numero, campos = campos[0], campos[1:]
        valor = ""
        for k in range(len(campos) - 1, -1, -1):
            if _ESTADOS.match(campos[k]):
                valor = campos.pop(k)
                break
        if not campos:
            continue
        crus.append((n, d, h, numero, "  ".join(campos), valor))
    if len(crus) < 3 or len(crus) < MINIMO_LIDO * com_hora:
        return None
    trincas = [c[1].groups() for c in crus]
    if ordem in ("DMA", "MDA", "AMD"):
        origem = "digitado"
    else:
        ordem, origem = _ordem_da_data(trincas, referencia)
    eventos = []
    casas = 3
    for n, d, h, numero, descricao, valor in crus:
        try:
            dia = _data(d.groups(), ordem)
        except ValueError:
            continue
        hh, mm, ss, fr = h.groups()
        casas = max(casas, len(fr or ""))
        quando = datetime(dia.year, dia.month, dia.day, int(hh), int(mm), int(ss), _fracao(fr))
        eventos.append(Evento(t=None, hora=h.group(0), endereco="", descricao=descricao,
                              valor=valor, quando=quando, data=d.group(0), numero=numero,
                              linha=n))
    if len(eventos) < MINIMO_LIDO * len(crus):
        return None
    avisos = ["o arquivo não diz o fuso da hora: o deslocamento até o registro é "
              "sugerido ou digitado, nunca lido"]
    return Lista(eventos=tuple(eventos), de=de, avisos=tuple(avisos), cru=texto[:LIMITE_DO_CRU],
                 formato=_nome_do_formato(texto), tempo="absoluto", ordem_da_data=ordem,
                 origem_da_ordem=origem, casas=min(casas, 6))


def ler_texto_de_eventos(texto: str, nome: str, referencia: date | None = None,
                         ordem: str = "") -> Lista:
    """Uma lista IMPORTADA pela janela de eventos, já como texto: `.eev`,
    tabela da Schneider, texto com hora — ou cru. Decisão de 11/11/2026: o
    arquivo importado NÃO é gravado; a tela o guarda enquanto a aba estiver
    aberta e o manda no corpo de cada pedido."""
    texto = (texto or "")[:LIMITE_DO_CRU]
    for ler, argumentos in ((de_eev, (texto, nome)), (de_texto, (texto, nome)),
                            (de_texto_com_hora, (texto, nome, referencia, ordem))):
        try:
            lista = ler(*argumentos)
        except Exception:  # noqa: BLE001 — formato estranho vira texto cru, nunca erro
            lista = None
        if lista is not None:
            return lista
    return Lista(de=nome, cru=texto)


def ler_arquivo_de_eventos(caminho: Path, nome: str = "", referencia: date | None = None,
                           ordem: str = "") -> Lista:
    """Um arquivo de eventos importado: `.eev`, tabela da Schneider, texto com
    hora, ou cru.

    Nunca levanta: arquivo que nenhum leitor entende volta como `Lista`
    vazia com o texto, e a tela o mostra como veio.
    """
    from osclab.formats.ajustes import _texto

    texto = _texto(Path(caminho))
    nome = nome or Path(caminho).name
    leitores = (lambda: de_eev(texto, nome),
                lambda: de_texto(texto, nome),
                lambda: de_texto_com_hora(texto, nome, referencia, ordem))
    for ler in leitores:
        try:
            lista = ler()
        except Exception:  # noqa: BLE001 — formato estranho vira texto cru, nunca erro
            lista = None
        if lista is not None:
            return lista
    return Lista(de=nome, cru=texto[:LIMITE_DO_CRU])
