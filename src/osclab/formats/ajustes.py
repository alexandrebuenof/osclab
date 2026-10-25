"""Os ajustes e a lógica que vêm DENTRO do arquivo de oscilografia.

## Onde eles estão

| | COMTRADE | `.CEV` (SEL) |
|---|---|---|
| **estado** da lógica, amostra a amostra | sim, nos canais digitais | sim |
| **a lógica em si** — ajustes e equações | **não está no padrão** | sim, no bloco `"SETTINGS"` |

No COMTRADE o padrão não prevê ajuste nenhum. O que existe é convenção de
fabricante: o `.HDR` é texto livre, e é nele que a SEL despeja o relatório de
evento. Quando vem, está lá; quando não vem, não há o que ler — e isso é
normal, não defeito.

No `.CEV` os dois estão garantidos no mesmo arquivo. O leitor de amostras para
no marcador `"SETTINGS"` (ver `cev.py`); daqui para baixo é o que este módulo
lê.

## Como se separa ajuste de lógica

Pela forma do lado direito do `:=`, e não por uma lista de nomes — lista de
nomes seria um catálogo por fabricante, e aí já seria o dicionário.

1. número puro (`3.50`) → **ajuste**;
2. expressão com `AND`/`OR`/`NOT` (ou `*`, `+`, `!`) → **lógica**;
3. mais de um termo → **lógica**;
4. um termo só: é um **canal digital deste registro**? Então é lógica
   (`OUT101 := TRIP`); se não, ajuste (`51P1C := U3`).

No que sobrar de dúvida, ajuste. Errar para o lado do ajuste não atrapalha
ninguém; errar para o lado da lógica põe um número onde se espera uma equação.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: `NOME := VALOR`, e também `NOME = VALOR`. O valor vai até o próximo
#: `NOME :=` da mesma linha — o SEL põe dois ajustes por linha — ou até o fim.
#: UM espaço basta para separar: com valor de oito caracteres a coluna encosta
#: (`VWDG1 := 138.000 VWDG2   := 34.500`, SEL-787), e exigindo dois o `VWDG2`
#: sumia dentro do valor do `VWDG1`. Mas com UM espaço só exige-se o `:=`:
#: o 751 escreve `ALIAS5 :=SV12 PROT_50G_50R SV12=1 SV12=0`, e ali `SV12=1`
#: é texto do apelido, não ajuste. `>=` não confunde: o `=` vem colado.
_PAR = re.compile(
    r"([A-Z0-9_#]{2,20})\s*:?=\s*(.*?)"
    r"(?=\s\s+[A-Z0-9_#]{2,20}\s*:?=|\s[A-Z0-9_#]{2,20}\s*:=|$)",
    re.IGNORECASE,
)

#: A linha que CONTINUA a anterior: no 4xx a de cima termina em `\`; no 311C
#: a de baixo vem recuada e começa por operador (`        + Z4GT`). Lida linha
#: a linha, a equação de trip saía cortada no meio.
_TERMINA_EM_BARRA = re.compile(r'\\\s*"?\s*,?\s*$')
_COMECA_POR_OPERADOR = re.compile(r"^\s+(?:[+*!(]|(?:AND|OR|NOT)(?![A-Z0-9_]))", re.IGNORECASE)

#: O marcador que abre o bloco no `.CEV`.
MARCADOR = "SETTINGS"

_OPERADORES = re.compile(r"\b(AND|OR|NOT)\b|[+*!()]")
_SO_NUMERO = re.compile(r"^-?[\d.,]+$")

#: Extensões que podem trazer o bloco, na ordem em que se procura.
_ONDE_PROCURAR = (".cev", ".hdr", ".inf", ".cff")


def _texto(caminho: Path) -> str:
    """Lê o arquivo sem nunca derrubar a tela por causa de um byte estranho."""
    for codec in ("utf-8-sig", "latin-1"):
        try:
            return caminho.read_text(encoding=codec, errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
    try:
        return caminho.read_text(encoding="latin-1", errors="replace")
    except OSError:
        return ""


def _bloco_do_cev(texto: str) -> str:
    """Do marcador `"SETTINGS"` para baixo. Vazio quando o arquivo não o traz.

    Alguns relés e algumas versões entregam o `.CEV` só com o cabeçalho. A
    ausência é normal: o leitor avisa e segue.
    """
    for i, linha in enumerate(texto.splitlines()):
        primeiro = linha.split(",")[0].strip().strip('"').upper()
        if primeiro == MARCADOR:
            return "\n".join(texto.splitlines()[i + 1:])
    # O relatório de evento em TEXTO do SEL-321, salvo como `.CEV`
    # (`formats/sel_texto.py`): não tem o marcador, e os ajustes vêm depois
    # da linha `Event: … Location: …`, no formato `NOME = valor`.
    for i, linha in enumerate(texto.splitlines()):
        if linha.strip().startswith("Event:") and "Location:" in linha:
            return "\n".join(texto.splitlines()[i + 1:])
    return ""


#: `"NOME",VALOR` — o formato de arquivo de ajustes do QuickSet, que a SEL
#: também despeja no `.HDR` do COMTRADE (`"Z1MAG",1.26`, `"BID1","DJ-37"`).
#: Sem ele o `.HDR` do SEL-421 entregava só os `KEY=VALOR` do `[INFO]` e as
#: equações embrulhadas em `"PROTSELn","X := ..."`: os parâmetros da linha e as
#: relações de TC/TP, que estavam escritos ali, não chegavam a ninguém (LT
#: COXIPO, 22/10/2026).
_PAR_CSV = re.compile(r'^"([A-Z0-9_#]{2,20})"\s*,\s*(.*)$', re.IGNORECASE)
#: E o `NOME,"VALOR"` do `.HDR` COMTRADE do SEL-311C — o nome SEM aspas.
#: Só com o valor entre aspas e o nome começando por letra: assim uma linha de
#: amostras (`1,0.5,...`) não vira ajuste. Sem isto saíam 3 pares de ~450.
_PAR_CSV_SEM_ASPAS = re.compile(r'^([A-Z][A-Z0-9_#]{1,19})\s*,\s*(".*)$', re.IGNORECASE)


def _juntar_continuacoes(texto: str) -> list[str]:
    """As linhas do texto com as equações continuadas já emendadas."""
    saida: list[str] = []
    emendar = False
    for linha in texto.splitlines():
        if saida and (emendar or (_COMECA_POR_OPERADOR.match(linha)
                                  and "=" not in linha)):
            saida[-1] = saida[-1].rstrip() + " " + linha.strip()
        else:
            saida.append(linha)
        emendar = bool(_TERMINA_EM_BARRA.search(saida[-1]))
        if emendar:
            saida[-1] = _TERMINA_EM_BARRA.sub("", saida[-1]).rstrip()
    return saida


def pares(texto: str) -> list[tuple[str, str]]:
    """Todos os `NOME := VALOR` do texto, na ordem em que aparecem.

    Vale também o `"NOME",VALOR` do arquivo de ajustes da SEL — menos quando o
    VALOR é ele mesmo um `X := ...`, que é como o QuickSet guarda as equações
    de SELOGIC (`"PROTSEL1","PSV60 := NOT IN101"`): ali o nome que importa é o
    de dentro, e quem o lê é o `_PAR` de sempre.
    """
    return [(nome, valor) for nome, valor, _ in _pares_com_forma(texto)]


def _pares_do_json(texto: str) -> list[tuple[str, str, bool]] | None:
    """O `.HDR` em JSON que o AcSELerator exporta («Export By Event»).

    `{"Settings": [{"Group", "Subgroup", "Name", "Value", ...}]}`: tudo já vem
    nomeado. O que é de grupo de lógica (`SELogic ...`) entra como equação; o
    resto como valor de campo, que pode ter espaço sem ser «mais de um termo».
    `None` quando o texto não é esse JSON — aí vale a leitura de sempre.
    """
    inicio = texto.lstrip()
    if not inicio.startswith("{"):
        return None
    try:
        dados = json.loads(inicio)
    except ValueError:
        return None
    lista = dados.get("Settings") if isinstance(dados, dict) else None
    if not isinstance(lista, list):
        return None
    achados: list[tuple[str, str, bool]] = []
    vistos: set[str] = set()
    for item in lista:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("Name") or "").strip().upper()
        if not nome or nome in vistos:
            continue
        vistos.add(nome)
        de_logica = "logic" in str(item.get("Group") or "").lower()
        achados.append((nome, str(item.get("Value") or "").strip(), not de_logica))
    return achados


def _pares_com_forma(texto: str) -> list[tuple[str, str, bool]]:
    """`pares`, dizendo de cada um se o valor veio ENTRE ASPAS no `"NOME",`.

    É o que separa `"SID","SE BARRO DURO"` — texto, com espaço — de uma
    equação. A regra de `eh_logica` toma espaço por «mais de um termo», o que
    é certo depois de um `:=` e errado num campo de texto entre aspas.
    """
    achados: list[tuple[str, str, bool]] = []
    vistos: set[str] = set()
    em_json = _pares_do_json(texto)
    if em_json is not None:
        return em_json
    for linha in _juntar_continuacoes(texto):
        csv = _PAR_CSV.match(linha.strip()) or _PAR_CSV_SEM_ASPAS.match(linha.strip())
        if csv and ":=" not in csv.group(2):
            nome = csv.group(1).strip().upper()
            cru = csv.group(2).strip().rstrip(",").strip()
            entre_aspas = cru.startswith('"')
            valor = cru.strip('"').strip()
            if nome not in vistos:
                vistos.add(nome)
                achados.append((nome, valor, entre_aspas))
            continue
        # O CEV embrulha o bloco num campo CSV: tira as aspas e as somas de
        # verificação do fim da linha, que não são ajuste de ninguém.
        limpa = linha.strip().strip('"').rstrip(",").rstrip('"')
        for nome, valor in _PAR.findall(limpa):
            nome = nome.strip().upper()
            valor = valor.strip().strip('"').strip()
            if not nome or nome in vistos:
                continue
            vistos.add(nome)
            achados.append((nome, valor, False))
    return achados


def eh_logica(valor: str, digitais: set[str] | None = None,
             texto: bool = False) -> bool:
    """Este lado direito é uma equação, ou um valor?

    `texto` diz que o valor veio entre aspas num `"NOME","VALOR"`: aí espaço
    é só espaço (`"SE BARRO DURO"`), e o que decide é o operador ou um único
    termo que seja canal digital. O comentário depois de `#` não conta.
    """
    v = (valor or "").strip()
    if not v:
        return False
    if _SO_NUMERO.match(v):
        return False
    if _OPERADORES.search(v):
        return True
    if texto:
        termo = v.split("#")[0].strip()
        return bool(digitais) and " " not in termo and termo.upper() in digitais
    if " " in v:
        return True
    return bool(digitais) and v.upper() in digitais


def separar(todos, digitais: set[str] | None = None) -> tuple[list, list]:
    """Parte a lista em (ajustes, lógica), preservando a ordem do arquivo.

    Aceita `(nome, valor)` ou `(nome, valor, entre_aspas)` — ver
    `_pares_com_forma`.
    """
    ajustes, logica = [], []
    for item in todos:
        nome, valor = item[0], item[1]
        texto = bool(item[2]) if len(item) > 2 else False
        (logica if eh_logica(valor, digitais, texto) else ajustes).append([nome, valor])
    return ajustes, logica


#: A linha em que o relé escreve o tipo do evento no `.hdr`. A SEL escreve
#: `Event: AB T` (o relatório em inglês) — e o relatório traduzido, `Tipo: AG
#: T`. `Event Number:` não casa: o nome do campo tem de vir colado nos
#: dois-pontos.
_EVENTO_NO_HDR = re.compile(r"(?im)^[ \t]*(?:event|tipo)[ \t]*:[ \t]*"
                            r"([A-Z0-9]+(?:[ \t]T\b)?)")


def classificacao_no_hdr(pasta: Path, arquivos) -> str:
    """O tipo da falta que o relé escreveu no `.hdr`, ou `""`.

    O `.cfg` do COMTRADE não tem campo para isso; quem escreve é o relé, em
    texto livre, no `.hdr` que vem junto — a SEL escreve, o SIPROTEC, o GE e
    o MiCOM do parque não. Só vale sigla de FASE: `Event: TRIG` ou `ER` (o
    relé disparou a oscilografia sem falta) não é tipo de falta nenhum.
    """
    for arquivo in sorted(arquivos or ()):
        if not arquivo.lower().endswith(".hdr"):
            continue
        caminho = Path(pasta) / arquivo
        if not caminho.is_file():
            continue
        achado = _EVENTO_NO_HDR.search(_texto(caminho))
        if not achado:
            continue
        sigla = achado.group(1).strip().upper()
        primeira = sigla.split()[0]
        de_fase = "3P" in primeira or any(c in "ABC" for c in primeira)
        if de_fase and set(primeira) <= set("ABCGN3PH"):
            return sigla
    return ""


#: Uma placa de E/S na seção `[IOBOARDS]` do `.hdr` da SEL:
#: `INT4_E, , , 24, 8, 0, 0, 1` — nome, dois campos vazios, ENTRADAS,
#: SAÍDAS, dois campos e a POSIÇÃO. A posição 1 é a série 200 (IN201…), a 2
#: a série 300; a placa principal (série 100) não aparece na seção.
_PLACA = re.compile(r"^\s*[A-Z0-9_]+\s*,[^,]*,[^,]*,\s*(\d+)\s*,\s*(\d+)\s*,"
                    r"[^,]*,[^,]*,\s*(\d+)\s*$", re.IGNORECASE)
_ENTRADA_OU_SAIDA = re.compile(r"^(IN|OUT)([2-9])(\d\d)$", re.IGNORECASE)


def placas_da_sel(texto: str) -> dict[int, tuple[int, int]] | None:
    """`{série: (entradas, saídas)}` das placas de E/S, ou `None` sem a seção.

    `{2: (24, 8), 3: (8, 15)}` quer dizer IN201–IN224 e OUT201–OUT208 na
    placa da posição 1, IN301–IN308 e OUT301–OUT315 na da posição 2.
    """
    linhas = texto.splitlines()
    for i, linha in enumerate(linhas):
        if linha.strip().upper() != "[IOBOARDS]":
            continue
        placas: dict[int, tuple[int, int]] = {}
        for seguinte in linhas[i + 1:]:
            if seguinte.strip().startswith("["):
                break
            achado = _PLACA.match(seguinte)
            if achado:
                entradas, saidas, posicao = (int(x) for x in achado.groups())
                placas[posicao + 1] = (entradas, saidas)
        return placas
    return None


def digitais_sem_placa(pasta: Path, arquivos, nomes) -> frozenset[str]:
    """Os digitais que o relé GRAVA e a placa dele NÃO TEM.

    Um SEL-487E-3 com uma placa de 8 entradas na posição 2 grava IN301 a
    IN324 assim mesmo — e nos bits de IN317–IN324 sai um contador que avança
    a cada amostra (TR01 da SE Jangada, 24/10/2026). Sem isto eles entravam na
    tela como «digitais que mudaram», piscando sem significar nada.

    Só decide com a seção `[IOBOARDS]` no `.hdr`; sem ela, nenhum. A placa
    principal (série 100) não aparece na seção e nunca é marcada.
    """
    for arquivo in sorted(arquivos or ()):
        if not arquivo.lower().endswith(".hdr"):
            continue
        caminho = Path(pasta) / arquivo
        if not caminho.is_file():
            continue
        placas = placas_da_sel(_texto(caminho))
        if placas is None:
            continue
        fora = set()
        for nome in nomes:
            achado = _ENTRADA_OU_SAIDA.match(str(nome).strip())
            if not achado:
                continue
            tipo = achado.group(1).upper()
            serie, numero = int(achado.group(2)), int(achado.group(3))
            entradas, saidas = placas.get(serie, (0, 0))
            if numero > (entradas if tipo == "IN" else saidas):
                fora.add(str(nome))
        return frozenset(fora)
    return frozenset()


def do_registro(pasta: Path, arquivos, digitais=None) -> dict:
    """O que este registro traz de ajuste e de lógica.

    `pasta` é a pasta do registro no acervo e `arquivos` os nomes como
    entraram. Procura o bloco no `.cev`, depois no `.hdr`, depois no `.inf`.
    """
    nomes = set(x.upper() for x in (digitais or ()))
    for extensao in _ONDE_PROCURAR:
        for arquivo in sorted(arquivos or ()):
            if not arquivo.lower().endswith(extensao):
                continue
            caminho = Path(pasta) / arquivo
            if not caminho.is_file():
                continue
            texto = _texto(caminho)
            bruto = _bloco_do_cev(texto) if extensao == ".cev" else texto
            if not bruto.strip():
                continue
            todos = _pares_com_forma(bruto)
            if not todos:
                continue
            ajustes, logica = separar(todos, nomes)
            return {
                "tem": True,
                "de": arquivo,
                "ajustes": ajustes,
                "logica": logica,
                "bruto": bruto.strip(),
                "motivo": "",
            }
    return {
        "tem": False,
        "de": "",
        "ajustes": [],
        "logica": [],
        "bruto": "",
        "motivo": ("o .CEV deste registro não traz o bloco de ajustes"
                   if any(a.lower().endswith(".cev") for a in (arquivos or ()))
                   # O .HDR pode vir SEM ajuste nenhum — o do SIPROTEC traz só
                   # estação, fuso e gatilho. Dizer «não veio .HDR» ali
                   # mandava procurar um arquivo que está no acervo.
                   else "este registro não traz ajustes — o COMTRADE não os "
                        "prevê, e o .HDR que veio junto não tem nenhum"
                   if any(a.lower().endswith(".hdr") for a in (arquivos or ()))
                   else "este registro não traz ajustes — o COMTRADE não os prevê, "
                        "e não veio .HDR com eles"),
    }
