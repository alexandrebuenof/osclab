"""O DICIONÁRIO: um nome de sinal de relé, uma descrição.

## O que ela guarda, e o que ela NÃO guarda

Guarda **digitais** — o bit que liga e desliga: `51P1T`, `TRIP`, `52A`,
`PHPIOC-TRIP`. Não guarda ajuste (`51P1P = 3,5 A`), que é valor numérico e
pede outras colunas (grandeza, base). Decisão do Alexandre, 19/10/2026: aqui o
objetivo é só pôr uma descrição em cada sinal.

## O arquivo

```
<base>/dicionario/dicionario.csv
fabricante;modelo;sinal;descricao;categoria
SEL;351;51P1T;trip temporizado da sobrecorrente de fase, estágio 1;trip
```

Ponto-e-vírgula e UTF-8 **com BOM**: é o par que faz o Excel brasileiro abrir
o arquivo já nas colunas certas e com os acentos no lugar. Sem o BOM, «estágio»
chega como «estÃ¡gio» na primeira vez que alguém abre o arquivo com dois
cliques — e aí a tabela volta corrompida.

## A regra conservadora

`descricao` e `categoria` podem ficar vazios, e isso não é um defeito: é a regra que
ele pediu. Quem não tem certeza deixa em branco, e o leitor mostra o nome cru
do arquivo. Inventar significado é pior do que não ter nenhum — numa análise de
ocorrência, um digital descrito errado manda a conclusão para o lado errado.

`categoria` existe para o programa **agrupar e colorir** os digitais na tela (os
trips juntos, as partidas juntas) em vez de listá-los na ordem em que o relé
gravou. Também só se classifica o que tem certeza.

## A chave

Um verbete é identificado por `(fabricante, modelo, sinal)`, comparados sem
olhar maiúscula: o mesmo `51P1T` quer dizer coisas diferentes num SEL-351 e num
SEL-411L, e o modelo é o que separa os dois.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, replace
from pathlib import Path

#: As categorias que o programa entende, e o teste que cada uma passou:
#: «ao olhar um registro, eu quero esses sinais juntos e nessa cor?».
#:
#: * `trip` — o relé mandou abrir. É o que se procura primeiro.
#: * `partida` — um elemento viu e começou a contar. É o que EXPLICA o trip, e
#:   a distância entre os dois é o tempo medido.
#: * `bloqueio` — impediu alguém de atuar: 86, LOP, torque control, bloqueio
#:   por oscilação. Responde a pergunta mais difícil da análise, que não é
#:   «por que atuou» e sim «por que NÃO atuou».
#: * `estado` — não age, É: 52A, religador pronto, local/remoto.
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
    "", "trip", "partida", "bloqueio", "estado", "io", "auxiliar")

COLUNAS = ("fabricante", "modelo", "sinal", "descricao", "categoria")

ARQUIVO = "dicionario.csv"


@dataclass(frozen=True)
class Verbete:
    """Um sinal digital de um modelo de relé."""

    fabricante: str
    modelo: str
    sinal: str
    descricao: str = ""
    categoria: str = ""

    @property
    def chave(self) -> tuple[str, str, str]:
        return (self.fabricante.strip().upper(),
                self.modelo.strip().upper(),
                self.sinal.strip().upper())

    def como_dicionario(self) -> dict:
        return {
            "fabricante": self.fabricante,
            "modelo": self.modelo,
            "sinal": self.sinal,
            "descricao": self.descricao,
            "categoria": self.categoria,
        }


def _caminho(base) -> Path:
    from osclab.basedados.pasta import PASTA_DO_DICIONARIO
    return base.gaveta(PASTA_DO_DICIONARIO) / ARQUIVO


def _limpo(valor) -> str:
    return str(valor if valor is not None else "").strip()


def _categoria_valida(valor: str) -> str:
    """Categoria que o programa não conhece vira vazio — e não erro.

    Uma base montada por outra equipe pode trazer uma palavra que ainda não
    existe aqui. Recusar o arquivo inteiro por causa de uma célula seria
    bloquear; ficar sem a categoria é só não classificar aquele sinal.
    """
    valor = _limpo(valor).lower()
    return valor if valor in CATEGORIAS else ""


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
    for linha in csv.reader(io.StringIO(texto), delimiter=sep):
        if not linha or not any(_limpo(c) for c in linha):
            continue
        celulas = [_limpo(c) for c in linha] + ["", "", "", "", ""]
        if celulas[0].lower() == "fabricante" and celulas[2].lower() == "sinal":
            continue  # o cabeçalho
        if not celulas[2]:
            continue  # sem sinal não há verbete
        saida.append(Verbete(
            fabricante=celulas[0], modelo=celulas[1], sinal=celulas[2],
            descricao=celulas[3], categoria=_categoria_valida(celulas[4]),
        ))
    return saida


def gravar(base, verbetes) -> Path:
    """Reescreve o arquivo inteiro. É pequeno; não vale um banco."""
    arquivo = _caminho(base)
    buraco = io.StringIO()
    escritor = csv.writer(buraco, delimiter=";", lineterminator="\n")
    escritor.writerow(COLUNAS)
    for v in verbetes:
        escritor.writerow([v.fabricante, v.modelo, v.sinal, v.descricao, v.categoria])
    arquivo.write_text(buraco.getvalue(), encoding="utf-8-sig")
    return arquivo


def anotar(base, fabricante: str, modelo: str, sinal: str,
           descricao: str | None = None, categoria: str | None = None) -> Verbete:
    """Cria ou corrige um verbete.

    `descricao` e `categoria` em `None` querem dizer «não mexa»; em `""`, «apague» —
    a diferença importa, porque apagar uma descrição errada é uma operação
    legítima e frequente.
    """
    fabricante, modelo, sinal = _limpo(fabricante), _limpo(modelo), _limpo(sinal)
    if not sinal:
        raise ValueError("um verbete precisa do nome do sinal")
    novos = listar(base)
    alvo = Verbete(fabricante, modelo, sinal).chave
    achado = None
    for i, v in enumerate(novos):
        if v.chave == alvo:
            achado = replace(
                v,
                descricao=v.descricao if descricao is None else _limpo(descricao),
                categoria=v.categoria if categoria is None else _categoria_valida(categoria),
            )
            novos[i] = achado
            break
    if achado is None:
        achado = Verbete(fabricante, modelo, sinal,
                         _limpo(descricao or ""), _categoria_valida(categoria or ""))
        novos.append(achado)
    gravar(base, novos)
    return achado


def remover(base, fabricante: str, modelo: str, sinal: str) -> bool:
    alvo = Verbete(_limpo(fabricante), _limpo(modelo), _limpo(sinal)).chave
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
    e ela não tem.
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
        # Linha de fora sem descrição não apaga a descrição que você escreveu.
        junto = replace(
            antigo,
            descricao=v.descricao or antigo.descricao,
            categoria=v.categoria or antigo.categoria,
        )
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
               "MITSUBISHI", "NARI", "ERLPHASE", "BECKWITH")


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


def identificar(equipamento: str) -> tuple[str, str]:
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


def descrever(base, fabricante: str, modelo: str, sinal: str) -> Verbete | None:
    """O verbete de um sinal, do mais específico para o mais genérico.

    Três degraus, e o primeiro que casar vence:

    1. `fabricante` + `modelo` — só naquele modelo;
    2. `fabricante` sozinho — qualquer relé da marca;
    3. os dois vazios — qualquer relé.

    Vazio quer dizer «vale para todos», e é por isso que o verbete comum não
    precisa ser cadastrado quatro vezes para a família inteira. Quando nada
    casa, volta `None` — e o leitor mostra o nome cru, que é o caminho normal:
    o dicionário nasce vazio.
    """
    fab, mod, sin = _limpo(fabricante).upper(), _limpo(modelo).upper(), _limpo(sinal).upper()
    if not sin:
        return None
    degraus = [(fab, mod), (fab, ""), ("", "")] if fab else [("", "")]
    verbetes = listar(base)
    for alvo_fab, alvo_mod in degraus:
        for v in verbetes:
            if v.sinal.strip().upper() != sin:
                continue
            if v.fabricante.strip().upper() == alvo_fab and \
               v.modelo.strip().upper() == alvo_mod:
                return v
    return None


def aplicaveis(base, equipamento: str) -> list[dict]:
    """Os verbetes que valem para este equipamento, um por sinal.

    Para cada sinal do dicionário, resolve os três degraus e devolve só o
    vencedor — com a `origem` dizendo em que degrau ele venceu. É o que a
    tela de consulta mostra: dois verbetes do mesmo sinal, um genérico e um
    do modelo, confundiriam quem está procurando o significado.
    """
    fabricante, modelo = identificar(equipamento)
    saida = []
    vistos = set()
    for v in listar(base):
        sinal = v.sinal.strip().upper()
        if not sinal or sinal in vistos:
            continue
        vistos.add(sinal)
        vence = descrever(base, fabricante, modelo, v.sinal)
        if vence is None:
            continue
        if vence.modelo.strip():
            origem = "deste modelo"
        elif vence.fabricante.strip():
            origem = "de todo " + vence.fabricante.strip()
        else:
            origem = "de qualquer relé"
        item = vence.como_dicionario()
        item["origem"] = origem
        saida.append(item)
    saida.sort(key=lambda x: x["sinal"].upper())
    return saida


def para_os_sinais(base, equipamento: str, sinais) -> dict:
    """O que o dicionário sabe sobre uma lista de sinais de um registro.

    Devolve `{sinal: {descricao, categoria}}` só com os que ele conhece — os
    que não estão no dicionário simplesmente não aparecem, e a tela trata a
    ausência como o estado normal.
    """
    fabricante, modelo = identificar(equipamento)
    achados = {}
    for sinal in sinais:
        v = descrever(base, fabricante, modelo, sinal)
        if v is None:
            continue
        achados[sinal] = {"descricao": v.descricao, "categoria": v.categoria}
    return achados
