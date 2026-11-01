"""O DICIONÁRIO: um nome de sinal de relé, uma descrição.

## O que ela guarda, e o que ela NÃO guarda

Guarda **digitais** — o bit que liga e desliga: `51P1T`, `TRIP`, `52A`,
`PHPIOC-TRIP`. Não guarda ajuste (`51P1P = 3,5 A`), que é valor numérico e
pede outras colunas (grandeza, base). Decisão do Alexandre, 19/10/2026: aqui o
objetivo é só pôr uma descrição em cada sinal.

## O arquivo

```
<base>/dicionario/dicionario.csv
fabricante;modelo;sinal;descricao;categoria;funcao;fase;estagio;fonte;referencia;instalacao
SEL;351;51P1T;trip temporizado da sobrecorrente de fase 1;trip;51;fases;1;manual;IM
SEL;751;50P2T;envio de seletividade lógica;comando;50;fases;2;digitado;;SE BUNGE AL12
```

Ponto-e-vírgula e UTF-8 **com BOM**: é o par que faz o Excel brasileiro abrir
o arquivo já nas colunas certas e com os acentos no lugar. Sem o BOM, «estágio»
chega como «estÃ¡gio» na primeira vez que alguém abre o arquivo com dois
cliques — e aí a tabela volta corrompida.

As colunas são lidas **pelo cabeçalho**, não pela posição: o arquivo de cinco
colunas de antes de 01/11/2026 continua valendo, e quem reordenar as colunas
no Excel não estraga nada. Sem cabeçalho, vale a ordem acima.

## A regra conservadora

Tudo além do `sinal` pode ficar vazio, e isso não é um defeito: é a regra que
ele pediu. Quem não tem certeza deixa em branco, e o leitor mostra o nome cru
do arquivo. Inventar significado é pior do que não ter nenhum — numa análise de
ocorrência, um digital descrito errado manda a conclusão para o lado errado.

`categoria` existe para o programa **agrupar e colorir** os digitais na tela (os
trips juntos, os pickups juntos) em vez de listá-los na ordem em que o relé
gravou. Também só se classifica o que tem certeza.

## A chave, e as duas camadas: o MODELO e a INSTALAÇÃO

Um verbete é identificado por `(fabricante, modelo, sinal, instalacao)`,
comparados sem olhar maiúscula: o mesmo `51P1T` quer dizer coisas diferentes
num SEL-351 e num SEL-411L, e o modelo é o que separa os dois.

A `instalacao` existe porque **o uso de um elemento é do ajuste, não do
modelo** (Alexandre, 01/11/2026): o segundo estágio do 50 de um alimentador
serve para enviar seletividade lógica, o de outro para bloquear o religamento
com HCL. O verbete com `instalacao` preenchida vale só para os registros
daquele relé e vence o do modelo. Vazia, vale para o modelo inteiro.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, fields, replace
from pathlib import Path

#: As categorias — o PAPEL do sinal na lógica — e o teste que cada uma passou:
#: «ao olhar um registro, eu quero esses sinais juntos e nessa cor?».
#:
#: * `trip` — o relé mandou abrir. É o que se procura primeiro.
#: * `pickup` — um elemento viu e começou a contar. É o que EXPLICA o trip, e
#:   a distância entre os dois é o tempo medido. (Era `partida` até
#:   01/11/2026; o arquivo antigo é lido assim mesmo — ver `_SINONIMOS`.)
#: * `bloqueio` — impediu alguém de atuar: 86, LOP, torque control, bloqueio
#:   por oscilação. Responde a pergunta mais difícil da análise, que não é
#:   «por que atuou» e sim «por que NÃO atuou».
#: * `teleprotecao` — o que vai e vem pelo canal com o outro terminal:
#:   permissivo e bloqueio enviados e recebidos, transferência de disparo,
#:   eco, bits espelhados. Numa linha, a pergunta «o outro lado mandou?» vem
#:   logo depois de «quem disparou?».
#: * `comando` — abertura ou fechamento que NÃO é a proteção: operador,
#:   telecomando, religamento. Separa «quem mandou abrir» do trip.
#: * `estado` — não age, É: 52A, religador pronto, local/remoto.
#: * `alarme` — a saúde do equipamento: autoteste, supervisão de TC/TP e de
#:   circuito de trip, falha de comunicação. Não explica a falta; explica por
#:   que o relé pode não ter visto.
#: * `io` — fio físico (IN101, OUT201). Fica à parte porque o significado
#:   deles é da INSTALAÇÃO, não do modelo.
#: * `auxiliar` — variável interna do relé: temporizador, latch, variável
#:   SELOGIC, gatilho de gravação. Não atua e não é fio; existe para a lógica
#:   funcionar. Na tela fica em tom discreto — é o que quase nunca se quer
#:   ver, e às vezes se precisa muito.
#:
#: Não há `outros`: uma gaveta de despejo compete com o vazio, e tudo que dá
#: dúvida acaba nela. Se um sinal real não couber em nenhuma destas, falta
#: outra categoria COM NOME, não um balde.
#:
#: O vazio é valor legítimo — é o «ainda não sei» —, e tem que sobreviver à
#: ida e volta do arquivo. A pendência de catalogação é a DESCRIÇÃO vazia,
#: não a categoria vazia: um verbete descrito e sem categoria está pronto,
#: só não vai ser colorido nem agrupado.
CATEGORIAS: tuple[str, ...] = (
    "", "trip", "pickup", "bloqueio", "teleprotecao", "comando", "estado",
    "alarme", "io", "auxiliar")

#: Nome antigo ou grafia comum → a categoria. Lido, nunca escrito: o arquivo
#: regravado já sai com o nome de hoje.
_SINONIMOS = {"partida": "pickup", "teleproteção": "teleprotecao",
              "telepro": "teleprotecao", "entrada/saída": "io", "e/s": "io"}

#: A FASE que o elemento olha. `fases` é o elemento de fase sem fase
#: específica (o `51P` da SEL olha as três); `N` é neutro e terra juntos —
#: a distinção residual × neutro medido está na DESCRIÇÃO, não aqui.
FASES: tuple[str, ...] = ("", "A", "B", "C", "AB", "BC", "CA", "N", "fases", "3F")

#: De onde veio o que está escrito. `manual`: conferido no manual do
#: fabricante. `ajuste`: lido do ajuste DAQUELE relé — a equação SELOGIC que
#: veio dentro da oscilografia (`TR := … + 50P3T`); é a prova mais forte do uso
#: de um elemento numa instalação. `deduzido`: o programa (ou o Claude) tirou
#: do nome do sinal, pelo padrão do fabricante — palpite bom, e palpite.
#: `digitado`: alguém escreveu pela tela. A tela mostra a origem, como em todo
#: o resto.
FONTES: tuple[str, ...] = ("", "manual", "ajuste", "deduzido", "digitado")

#: A força de cada fonte na importação: o que chega só corrige o que tem
#: fonte igual ou mais fraca. Vazio conta como digitado (era o único jeito de
#: escrever antes desta coluna existir).
_FORCA = {"deduzido": 1, "manual": 2, "ajuste": 3, "digitado": 4, "": 4}

#: As colunas, na ordem em que o arquivo é GRAVADO. As cinco primeiras são as
#: de antes de 01/11/2026, na mesma ordem.
COLUNAS = ("fabricante", "modelo", "sinal", "descricao", "categoria",
           "funcao", "fase", "estagio", "fonte", "referencia", "instalacao")

ARQUIVO = "dicionario.csv"


@dataclass(frozen=True)
class Verbete:
    """Um sinal digital de um modelo de relé — ou de UM relé, com `instalacao`."""

    fabricante: str
    modelo: str
    sinal: str
    descricao: str = ""
    categoria: str = ""
    #: A função de proteção, pelo número ANSI: `51`, `67`, `21`, `79`,
    #: `50BF`, `85`. Texto, porque `50BF` e `87L` não são números.
    funcao: str = ""
    fase: str = ""
    #: O estágio, a zona ou o nível: `1`, `2`, `3`.
    estagio: str = ""
    fonte: str = ""
    #: Onde conferir: manual e seção, norma, documento da instalação.
    referencia: str = ""
    #: O relé a que o verbete se restringe — o nome da SE e do vão como o
    #: registro os traz (`SE BUNGE AL12`). Vazio: o modelo inteiro.
    instalacao: str = ""

    @property
    def chave(self) -> tuple[str, str, str, str]:
        return (self.fabricante.strip().upper(),
                self.modelo.strip().upper(),
                self.sinal.strip().upper(),
                _normal(self.instalacao))

    def como_dicionario(self) -> dict:
        return {c: getattr(self, c) for c in COLUNAS}


#: Os campos que se editam (todos menos os da chave).
EDITAVEIS = tuple(f.name for f in fields(Verbete)
                  if f.name not in ("fabricante", "modelo", "sinal", "instalacao"))


def _caminho(base) -> Path:
    from osclab.basedados.pasta import PASTA_DO_DICIONARIO
    return base.gaveta(PASTA_DO_DICIONARIO) / ARQUIVO


def _limpo(valor) -> str:
    return str(valor if valor is not None else "").strip()


def _normal(texto) -> str:
    """Sem acento, maiúsculo, só letra e dígito separados por um espaço."""
    t = unicodedata.normalize("NFKD", _limpo(texto)).encode("ascii", "ignore").decode().upper()
    return " ".join(re.findall(r"[A-Z0-9]+", t))


def _categoria_valida(valor: str) -> str:
    """Categoria que o programa não conhece vira vazio — e não erro.

    Uma base montada por outra equipe pode trazer uma palavra que ainda não
    existe aqui. Recusar o arquivo inteiro por causa de uma célula seria
    bloquear; ficar sem a categoria é só não classificar aquele sinal.
    """
    valor = _limpo(valor).lower()
    valor = _SINONIMOS.get(valor, valor)
    return valor if valor in CATEGORIAS else ""


def _fase_valida(valor: str) -> str:
    v = _limpo(valor)
    if v.lower() in ("fases", "fase", "p"):
        return "fases"
    v = v.upper().replace("G", "N").replace("T", "N")   # terra e neutro, juntos
    return v if v in FASES else ""


def _fonte_valida(valor: str) -> str:
    v = _limpo(valor).lower()
    return v if v in FONTES else ""


def _validado(campo: str, valor) -> str:
    return {"categoria": _categoria_valida, "fase": _fase_valida,
            "fonte": _fonte_valida}.get(campo, _limpo)(valor)


def listar(base) -> list[Verbete]:
    """Todos os verbetes, na ordem em que estão no arquivo."""
    arquivo = _caminho(base)
    try:
        texto = arquivo.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    return _de_texto(texto)


def _de_texto(texto: str) -> list[Verbete]:
    saida: list[Verbete] = []
    # O separador vem do arquivo, não da nossa opinião: quem exporta do Excel
    # em outra região manda vírgula, e recusar isso é recusar o arquivo da
    # pessoa por um detalhe que o programa consegue ver sozinho.
    primeira = next((l for l in texto.splitlines() if l.strip()), "")
    sep = ";" if primeira.count(";") >= primeira.count(",") else ","
    ordem = list(COLUNAS)
    for linha in csv.reader(io.StringIO(texto), delimiter=sep):
        if not linha or not any(_limpo(c) for c in linha):
            continue
        celulas = [_limpo(c) for c in linha]
        # Só a linha que tem uma célula «sinal» pode ser cabeçalho: testar o
        # texto cru antes poupa a normalização de dezenas de milhares de
        # células num dicionário grande.
        if any(c.lower() == "sinal" for c in celulas):
            nomes = [_normal(c).lower().replace(" ", "") for c in celulas]
            if sum(n in COLUNAS for n in nomes) >= 2:
                # O CABEÇALHO decide a ordem. Coluna que o programa não
                # conhece é ignorada; coluna que falta fica vazia — inclusive
                # o `fabricante`, num CSV só de verbetes genéricos.
                ordem = [n if n in COLUNAS else "" for n in nomes]
                continue
        valores = dict(zip(ordem, celulas, strict=False))
        if not valores.get("sinal"):
            continue  # sem sinal não há verbete
        saida.append(Verbete(**{c: _validado(c, valores.get(c, "")) for c in COLUNAS}))
    return saida


def gravar(base, verbetes) -> Path:
    """Reescreve o arquivo inteiro. É pequeno; não vale um banco."""
    arquivo = _caminho(base)
    arquivo.write_text(como_csv(verbetes), encoding="utf-8-sig")
    return arquivo


def como_csv(verbetes) -> str:
    """O texto do arquivo — o mesmo que se grava e que se exporta."""
    buraco = io.StringIO()
    escritor = csv.writer(buraco, delimiter=";", lineterminator="\n")
    escritor.writerow(COLUNAS)
    for v in verbetes:
        escritor.writerow([getattr(v, c) for c in COLUNAS])
    return buraco.getvalue()


def anotar(base, fabricante: str, modelo: str, sinal: str,
           descricao: str | None = None, categoria: str | None = None,
           instalacao: str = "", **outros) -> Verbete:
    """Cria ou corrige um verbete.

    Cada campo em `None` (ou ausente) quer dizer «não mexa»; em `""`,
    «apague» — a diferença importa, porque apagar uma descrição errada é uma
    operação legítima e frequente. Os campos além de descrição e categoria
    (`funcao`, `fase`, `estagio`, `fonte`, `referencia`) vêm por nome.
    """
    fabricante, modelo, sinal = _limpo(fabricante), _limpo(modelo), _limpo(sinal)
    if not sinal:
        raise ValueError("um verbete precisa do nome do sinal")
    mudancas = {"descricao": descricao, "categoria": categoria}
    mudancas.update({k: v for k, v in outros.items() if k in EDITAVEIS})
    # Fase escrita e não reconhecida é ERRO, não apagamento: vazio aqui quer
    # dizer «apague», e `AG` apagaria a fase sem ninguém saber.
    fase = mudancas.get("fase")
    if fase is not None and _limpo(fase) and not _fase_valida(fase):
        raise ValueError(f"fase «{_limpo(fase)}» não reconhecida — use "
                         + ", ".join(f for f in FASES if f) + ", ou deixe vazio")
    mudancas = {k: _validado(k, v) for k, v in mudancas.items() if v is not None}
    novos = listar(base)
    alvo = Verbete(fabricante, modelo, sinal, instalacao=_limpo(instalacao)).chave
    achado = None
    for i, v in enumerate(novos):
        if v.chave == alvo:
            achado = replace(v, **mudancas)
            novos[i] = achado
            break
    if achado is None:
        achado = Verbete(fabricante, modelo, sinal, instalacao=_limpo(instalacao), **mudancas)
        novos.append(achado)
    gravar(base, novos)
    return achado


def remover(base, fabricante: str, modelo: str, sinal: str, instalacao: str = "") -> bool:
    alvo = Verbete(_limpo(fabricante), _limpo(modelo), _limpo(sinal),
                   instalacao=_limpo(instalacao)).chave
    atuais = listar(base)
    sobrando = [v for v in atuais if v.chave != alvo]
    if len(sobrando) == len(atuais):
        return False
    gravar(base, sobrando)
    return True


def importar(base, texto: str) -> dict:
    """Junta um CSV de fora ao que já existe.

    O que chega **acrescenta e corrige**, nunca apaga: a tabela de uma equipe
    inteira chegando por cima da sua não pode fazer sumir o que você catalogou
    e ela não tem. Pela mesma razão, o que VOCÊ digitou (`fonte = digitado`)
    não é trocado por uma dedução que chega de fora.
    """
    atuais = listar(base)
    por_chave = {v.chave: i for i, v in enumerate(atuais)}
    novos = 0
    mexidos = 0
    for v in _de_texto(texto or ""):
        i = por_chave.get(v.chave)
        if i is None:
            por_chave[v.chave] = len(atuais)
            atuais.append(v)
            novos += 1
            continue
        antigo = atuais[i]
        # Prova não é trocada por palpite: o que chega só mexe num verbete de
        # fonte igual ou mais fraca. O vazio é o verbete digitado antes de
        # existir a coluna — tão forte quanto o digitado.
        if _FORCA.get(v.fonte, 4) < _FORCA.get(antigo.fonte, 4):
            continue
        # Célula de fora vazia não apaga o que você escreveu.
        junto = replace(antigo, **{c: getattr(v, c) or getattr(antigo, c) for c in EDITAVEIS})
        if junto != antigo:
            atuais[i] = junto
            mexidos += 1
    gravar(base, atuais)
    return {"acrescentados": novos, "corrigidos": mexidos, "total": len(atuais)}


#: Os fabricantes que o programa reconhece no cabeçalho do registro. A lista
#: serve só para partir «SEL-351» em «SEL» e «351»; um equipamento que não
#: comece por nenhum deles fica sem fabricante, e aí só os verbetes genéricos
#: casam — que é o comportamento certo, e não um defeito.
FABRICANTES = ("SEL", "ABB", "SIEMENS", "GE", "SCHNEIDER", "AREVA", "ALSTOM",
               "HITACHI", "ZIV", "EFACEC", "PEXTRON", "REASON", "TOSHIBA",
               "MITSUBISHI", "NARI", "ERLPHASE", "BECKWITH", "INGETEAM", "NOJA")


#: A FID da SEL depois do modelo: `-R312-V0-Z106101-D20160115`.
_REVISAO_SEL = re.compile(r"-R\d.*$", re.IGNORECASE)
#: O modelo SEL sem a VARIANTE: `487E-3` → `487E`, `311C-1` → `311C`,
#: `451-5` → `451`, `411L-A` → `411L`. Os Relay Word bits são os da família;
#: a variante muda hardware e firmware, não o nome do bit.
_VARIANTE_SEL = re.compile(r"^(\d{3,4}[A-Z]?)(?:-[A-Z0-9]{1,2})?$", re.IGNORECASE)
#: Famílias que o cabeçalho escreve SEM a marca na frente.
_FAMILIAS = (
    (re.compile(r"^(P\d{3})\b", re.IGNORECASE), "SCHNEIDER"),   # MiCOM P439-655-704; F: …
    (re.compile(r"^(SIPROTEC\s*5)\b", re.IGNORECASE), "SIEMENS"),
)

#: Quando o campo do EQUIPAMENTO não diz quem é, os outros textos do registro
#: (estação, nome do arquivo) às vezes dizem. Medido no banco (01/11/2026):
#: o Ingeteam PL300 grava o NÚMERO do registro no equipamento (`56`) e o
#: modelo na estação (`P-056 -- UCL 9 -- PL300 - EH3126/I`) — ~95 registros;
#: o religador Ingeteam grava `RELIG` e o fabricante só aparece no nome do
#: arquivo (`…,RELIG,ENERGISA_M,Ingeteam.CFG`) — 129 registros. Nenhum dos
#: dois casava verbete de modelo nenhum.
_PELOS_OUTROS_TEXTOS = (
    (re.compile(r"\b(PL\s?\d{3})\b", re.IGNORECASE), "INGETEAM"),
    (re.compile(r"\bINGETEAM\b", re.IGNORECASE), "INGETEAM"),
    # O SIPROTEC 5 grava o NÚMERO DE SÉRIE no equipamento (`BM…`). Quem decide
    # que é ele é o ACERVO (`acervo._modelo`), que exige também a prova — os
    # canais no jeito do DIGSI 5 — e escreve «SIPROTEC 5 · nº de série BM…» no
    # modelo do item. Aqui só se lê essa conclusão: uma regra só, num lugar só.
    (re.compile(r"\bSIPROTEC\s*5\b", re.IGNORECASE), "SIEMENS"),
)


def identificar(equipamento: str, *outros: str) -> tuple[str, str]:
    """`identificar_equipamento`, e, se ele não reconhecer o fabricante, os
    OUTROS textos do registro (`_PELOS_OUTROS_TEXTOS`). Um padrão só de
    fabricante (`INGETEAM` no nome do arquivo) dá o fabricante e deixa o
    modelo vazio — é o degrau «de todo Ingeteam» do dicionário."""
    fab, mod = identificar_equipamento(equipamento)
    if fab:
        return fab, mod
    for texto in outros:
        for padrao, marca in _PELOS_OUTROS_TEXTOS:
            achado = padrao.search(texto or "")
            if achado:
                modelo = achado.group(1).upper().replace(" ", "") if padrao.groups else ""
                return marca, modelo
    return fab, mod


def identificar_equipamento(equipamento: str) -> tuple[str, str]:
    """«SEL-351» -> («SEL», «351»). «FRA-01» -> («», «FRA-01»).

    O COMTRADE declara o equipamento no cabeçalho do `.cfg`, e o `.CEV` no
    dele. Só que esse campo é texto livre: tanto vem «SEL-351» quanto vem o
    nome do vão. Então o que não for reconhecido vira MODELO, e o fabricante
    fica vazio — um palpite errado de fabricante casaria o verbete errado.

    A SEL grava a FID inteira (`FID=SEL-487E-3-R312-V0-…`): sem tirar o
    `FID=` e a revisão, NENHUM COMTRADE da SEL achava o fabricante, e o
    dicionário só casava verbetes genéricos (achado no banco de oscilografias,
    24/10/2026). O modelo sai sem a variante (`487E`, `311C`), e o MiCOM
    (`P439-655-704; F: …`) vira Schneider P439.
    """
    texto = _limpo(equipamento)
    if not texto:
        return ("", "")
    if texto.upper().startswith("FID="):
        texto = texto[4:].strip()
    alto = texto.upper()
    for marca in FABRICANTES:
        if alto == marca:
            return (marca, "")
        for sep in ("-", "_", " "):
            if alto.startswith(marca + sep):
                resto = texto[len(marca) + 1:].strip()
                if marca == "SEL":
                    resto = _REVISAO_SEL.sub("", resto)
                    variante = _VARIANTE_SEL.match(resto)
                    if variante:
                        resto = variante.group(1)
                return (marca, resto)
    for padrao, marca in _FAMILIAS:
        achado = padrao.match(texto)
        if achado:
            return (marca, achado.group(1).upper().replace("  ", " "))
    return ("", texto)


def instalacao_casa(instalacao: str, textos) -> bool:
    """O verbete de `instalacao` vale para este registro?

    Toda palavra da instalação tem de aparecer entre as palavras do que o
    registro diz de si — estação, equipamento, apelido. `SE BUNGE AL12` casa
    com a estação «SE Bunge» e o equipamento «AL12_UPC1». Palavra a palavra,
    e não trecho de texto, para `AL1` não casar com `AL12`.

    `AL-12`, `AL 12` e `AL12` são a mesma coisa dos DOIS lados: letras
    seguidas de número separado viram uma palavra só (`_juntadas`), na
    instalação e no registro.
    """
    alvo = _juntadas(_normal(instalacao).split())
    if not alvo:
        return True
    palavras = set()
    for t in textos:
        soltas = _normal(t).split()
        for p in soltas + _juntadas(soltas):
            palavras.add(p)
            palavras.update(re.findall(r"[A-Z]+\d+|\d+|[A-Z]+", p))   # AL12UPC1 → AL12, UPC1
    return all(p in palavras for p in alvo)


def _juntadas(palavras: list[str]) -> list[str]:
    """`['SE', 'AL', '12']` → `['SE', 'AL12']`: letras e o número logo depois."""
    saida: list[str] = []
    for p in palavras:
        if saida and p.isdigit() and saida[-1].isalpha():
            saida[-1] += p
        else:
            saida.append(p)
    return saida


def descrever(base, fabricante: str, modelo: str, sinal: str,
              textos_da_instalacao=(), verbetes=None) -> Verbete | None:
    """O verbete de um sinal, do mais específico para o mais genérico.

    Quatro degraus, e o primeiro que casar vence:

    0. o da INSTALAÇÃO — só para os registros daquele relé (`instalacao_casa`);
    1. `fabricante` + `modelo` — só naquele modelo;
    2. `fabricante` sozinho — qualquer relé da marca;
    3. os dois vazios — qualquer relé.

    Vazio quer dizer «vale para todos», e é por isso que o verbete comum não
    precisa ser cadastrado quatro vezes para a família inteira. Quando nada
    casa, volta `None` — e o leitor mostra o nome cru, que é o caminho normal:
    o dicionário nasce vazio.
    """
    sin = _limpo(sinal).upper()
    if not sin:
        return None
    if isinstance(verbetes, dict):          # o índice de `_por_sinal`
        candidatos = verbetes.get(sin, [])
    else:
        todos = listar(base) if verbetes is None else verbetes
        candidatos = [v for v in todos if v.sinal.strip().upper() == sin]
    return _resolver(candidatos, fabricante, modelo, textos_da_instalacao)


def _por_sinal(verbetes) -> dict[str, list[Verbete]]:
    """Os verbetes agrupados pelo sinal. Com o dicionário de milhares de
    verbetes, procurar cada sinal na lista inteira custava ~1 s por registro
    aberto (medido com 7158 verbetes, 01/11/2026)."""
    indice: dict[str, list[Verbete]] = {}
    for v in verbetes:
        indice.setdefault(v.sinal.strip().upper(), []).append(v)
    return indice


def _resolver(candidatos, fabricante: str, modelo: str,
              textos_da_instalacao=()) -> Verbete | None:
    """Os degraus de `descrever` sobre os verbetes de UM sinal."""
    fab, mod = _limpo(fabricante).upper(), _limpo(modelo).upper()
    textos = tuple(textos_da_instalacao or ())

    def de(v):
        return v.fabricante.strip().upper(), v.modelo.strip().upper()

    # Entre as instalações que casam, a mais ESPECÍFICA — a de mais palavras:
    # «SE BUNGE AL12» vence «SE BUNGE» nos registros do AL12, seja qual for a
    # ordem no arquivo.
    casam = [v for v in candidatos
             if v.instalacao and textos and instalacao_casa(v.instalacao, textos)
             and de(v)[0] in (fab, "") and de(v)[1] in (mod, "")]
    if casam:
        return max(casam, key=lambda v: len(_juntadas(_normal(v.instalacao).split())))
    degraus = [(fab, mod), (fab, ""), ("", "")] if fab else [("", "")]
    for alvo in degraus:
        for v in candidatos:
            if not v.instalacao and de(v) == alvo:
                return v
    return None


def _origem(v: Verbete) -> str:
    if v.instalacao:
        return "deste relé (" + v.instalacao + ")"
    if v.modelo.strip():
        return "deste modelo"
    if v.fabricante.strip():
        return "de todo " + v.fabricante.strip()
    return "de qualquer relé"


def aplicaveis(base, equipamento: str, textos_da_instalacao=()) -> list[dict]:
    """Os verbetes que valem para este equipamento, um por sinal.

    Para cada sinal do dicionário, resolve os degraus e devolve só o vencedor
    — com a `origem` dizendo em que degrau ele venceu. É o que a tela de
    consulta mostra: dois verbetes do mesmo sinal, um genérico e um do modelo,
    confundiriam quem está procurando o significado.
    """
    fabricante, modelo = identificar(equipamento, *textos_da_instalacao)
    saida = []
    for sinal, candidatos in _por_sinal(listar(base)).items():
        if not sinal:
            continue
        vence = _resolver(candidatos, fabricante, modelo, textos_da_instalacao)
        if vence is None:
            continue
        item = vence.como_dicionario()
        item["origem"] = _origem(vence)
        saida.append(item)
    saida.sort(key=lambda x: x["sinal"].upper())
    return saida


def para_os_sinais(base, equipamento: str, sinais, textos_da_instalacao=()) -> dict:
    """O que o dicionário sabe sobre uma lista de sinais de um registro.

    Devolve `{sinal: {descricao, categoria, …}}` só com os que ele conhece —
    os que não estão no dicionário simplesmente não aparecem, e a tela trata a
    ausência como o estado normal.
    """
    fabricante, modelo = identificar(equipamento, *textos_da_instalacao)
    indice = _por_sinal(listar(base))
    achados = {}
    for sinal in sinais:
        v = descrever(base, fabricante, modelo, sinal, textos_da_instalacao, indice)
        if v is None:
            continue
        achados[sinal] = {"descricao": v.descricao, "categoria": v.categoria,
                          "funcao": v.funcao, "fase": v.fase, "estagio": v.estagio,
                          "fonte": v.fonte, "origem": _origem(v)}
    return achados
