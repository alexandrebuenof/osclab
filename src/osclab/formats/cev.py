"""Leitor CEV — o relatório de evento comprimido da SEL.

## Por que este leitor existe

A metade FILTRADA de uma oscilografia SEL quase nunca sai em COMTRADE. O que o
relé entrega é o `.CEV`: **um arquivo só**, ASCII, com cabeçalho, amostras,
digitais e até os ajustes do relé dentro. Sem ele não dá para comparar o que o
nosso filtro faz com o que o filtro do relé fez — que é exatamente a conferência
que este marco precisa.

## A forma do arquivo

Pares de linhas — uma de nomes, a seguinte de valores — e **o último campo de
toda linha é uma soma de verificação em hexadecimal**:

```
1  "FID","RID","SID","03E2"
2  "FID=SEL-451-5-R316-...","UPC1 ALIMENTADOR 11","SE BARRO DURO","125d"
3  "MONTH","DAY","YEAR","HOUR","MIN","SEC","MSEC","0ACA"
4  1,19,2026,13,36,57,649,"0475"
5  "EVENT_NUM","EVENT","LOCATION","FREQ","NFREQ","SAM/CYC_A",...   (128 campos)
6  10795,"AB T",$$$$.$$,60.00,60,8,8,60.125,...                    (128 campos)
7  "IA(A)","IB(A)",...,"ANA01",...,"TRIG","TLED_1 TLED_2 ...","3CC5"
8  -46,-11,57,0,0.57,...,' ',"61e00000...","50D3"                  (uma amostra)
...
   "SETTINGS","02E1"          <- daqui para baixo são os ajustes do relé
```

A soma de verificação é a soma dos bytes ASCII da linha **até a última vírgula,
inclusive**, módulo `0x10000`. Conferida e anotada; nunca recusa o arquivo — um
byte trocado num campo que não usamos não é motivo para o engenheiro ficar sem
a oscilografia.

## Três coisas que não estão escritas em lugar nenhum e custam caro

**1. As amostras vêm em RMS, não em valor instantâneo.**

Esta é a armadilha. A coluna `VA(kV)` oscila como uma senoide, mas o pico dela
não é o pico da tensão: é o **valor eficaz**. Medido no par bruto/filtrado do
mesmo evento do mesmo relé:

    COMTRADE bruto   VAY  pico = 11,355 kV
    CEV filtrado     VA   pico =  8,030 kV        11,355 / 8,030 = 1,4141 = raiz(2)

E a própria coluna `V1M` do arquivo — a sequência positiva que o relé calculou —
vale 8,069 kV, encostada no pico da senoide de `VA`. Num sistema de 13,8 kV, a
tensão de fase eficaz é 7,97 kV: bate com 8,07 e não bate com 11,35.

Por isso as colunas de onda são multiplicadas por raiz de 2 na leitura. Um
`Record` do OscLab carrega valor instantâneo, sempre, venha do formato que vier
— senão o botão de RMS da tela devolveria o valor dividido por raiz de 2 e o
gráfico do filtrado apareceria 41 % menor que o do bruto, sem nada denunciar.

**2. A hora do cabeçalho é a do DISPARO, não a da primeira amostra.**

A linha `MONTH..MSEC` é o instante do disparo, e a amostra disparada é a que traz
`>` na coluna `TRIG`. O início sai da conta. Conferido contra o COMTRADE do mesmo
evento: o CEV dá início às 13:36:57,5469 e o COMTRADE declara 13:36:57,5472 —
0,3 ms, dentro do milissegundo em que o cabeçalho é arredondado.

**3. As colunas `ANAnn` não são canais de onda.**

São as grandezas que o relé mediu ele mesmo, amostra a amostra, e os nomes delas
estão nos campos `ERAQ01..ERAQ20` do cabeçalho grande: `V1M`, `V1A`, `3V2M`,
`3V2A`, `3V0M`, `3V0A`, `LI1M`, `LI1A`, `L3I2M`, `L3I2A`, `LIGM`, `LIGA`, `DC1`,
`FREQ`. Magnitude e ângulo já em eficaz e em grau — **a referência do próprio
relé para as nossas componentes de sequência**. Não levam raiz de 2 nenhuma.

## Os digitais

O penúltimo campo de cada amostra é uma tira de hexadecimal; o mesmo campo, na
linha 7, traz os nomes separados por espaço. Um bit por nome, do mais
significativo para o menos, na ordem em que os nomes aparecem — 148 dígitos
hexadecimais para 592 nomes, exato.

Conferido contra o COMTRADE bruto do mesmo evento: o `TRIP` sobe em +331,25 ms
no CEV e em +331,5 ms no COMTRADE, e desce em +531,25 e +531,5 ms. A diferença é
menor que o intervalo entre duas amostras do CEV (2,08 ms). Ordem de bit,
amostra do disparo e base de tempo, todas confirmadas por um arquivo que este
leitor nem toca.
"""

from __future__ import annotations

import csv
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from osclab.formats.base import (
    AnalogChannel,
    Filtering,
    FilteringSource,
    FormatError,
    Record,
    SampleRate,
    StatusChannel,
)

#: A primeira linha de todo CEV, nos DOIS dialetos do parque. Específica o
#: bastante para não dar falso positivo em nenhum outro formato.
#:
#:     SEL-451, sem versão:   "FID","RID","SID",<soma>
#:     SEL-787, CEV_VER 2.0.1: "FID","CEV_VER",<soma>
#:
#: Os dois são listados na mão, e não trocados por um `"FID",.*`: um arquivo
#: que só começa com `FID` não é necessariamente um CEV, e o `sniff` de um
#: leitor que assume demais sequestra arquivo dos outros. Dialeto novo entra
#: aqui de propósito, olhado por alguém.
_ASSINATURA = re.compile(
    rb'^\s*"?FID"?\s*,\s*(?:"?RID"?\s*,\s*"?SID"?|"?CEV_VER"?)',
    re.IGNORECASE)

#: A que a soma de verificação é reduzida.
_MODULO = 0x10000

#: Unidades em que uma coluna de onda pode vir. Só elas recebem a raiz de 2:
#: `FREQ(Hz)` é um escalar em hertz e as colunas `ANAnn` não declaram unidade.
UNIDADES_DE_ONDA = frozenset({"A", "KA", "MA", "V", "KV", "MV"})

#: O fator que leva a amostra eficaz do CEV ao valor instantâneo do `Record`.
#: Ver o item 1 do cabeçalho deste arquivo.
RMS_PARA_INSTANTANEO = math.sqrt(2.0)

#: Até esta taxa, o relatório de evento da SEL é o FILTRADO. O relé grava o
#: filtrado a 4 ou 8 amostras por ciclo — não daria para gravar onda crua com
#: tão pouco — e o bruto a 16 ou mais.
#:
#: **A taxa é o único critério, e isto já esteve errado.** Havia aqui a
#: afirmação de que as amostras virem em valor eficaz seria a outra prova,
#: "porque só o relatório filtrado é escrito assim". O `.CEV` do SEL-787 do
#: parque derrubou isso: 16 amostras por ciclo, THD de 0,9 a 1,8 % em regime
#: (ou seja, onda CRUA — o filtrado dá ~0 %), e ainda assim escrito em eficaz.
#: Conferido contra o cabeçalho do próprio relé: com o ×√2 os sete canais
#: fecham dentro de 1,3 %; sem ele, erram 30 %.
#:
#: Ou seja: **o eficaz é do formato CEV, não do relatório filtrado.**
FILTRADO_ATE = 8

#: `IA(A)`, `VA(kV)`, `FREQ(Hz)` — a unidade vem colada no nome, entre parênteses.
_UNIDADE_NO_NOME = re.compile(r"^(?P<nome>.*?)\s*\(\s*(?P<unidade>[^)]*)\s*\)\s*$")

#: `ANA01` — coluna cujo nome de verdade está num campo `ERAQnn` do cabeçalho.
_COLUNA_ANA = re.compile(r"^ANA(\d+)$", re.IGNORECASE)

#: Onde os ajustes do relé começam. Dali para baixo o arquivo deixa de ser CSV.
_FIM_DOS_DADOS = "SETTINGS"


# ---------------------------------------------------------------------------
# Leitura de texto
# ---------------------------------------------------------------------------

def _decodificar(bruto: bytes) -> str:
    """Bytes para texto sem nunca estourar.

    Nome de subestação com acento vem em cp1252 nos arquivos da distribuidora.
    `latin-1` no fim é o que garante que nenhum byte derruba a leitura.
    """
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", errors="replace")


def _linhas(texto: str) -> list[str]:
    """As linhas, sem o fim de linha e sem as vazias do final."""
    cru = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while cru and not cru[-1].strip():
        cru.pop()
    return cru


def _campos(linha: str) -> list[str]:
    """Os campos de uma linha, com as aspas do CSV já resolvidas."""
    try:
        return next(csv.reader([linha]))
    except (csv.Error, StopIteration):
        return []


def _soma_de_verificacao(linha: str) -> int | None:
    """A soma que o último campo da linha deveria trazer.

    Soma dos bytes ASCII até a última vírgula, **incluindo a vírgula**, módulo
    `0x10000`. Foi deduzida do arquivo e confere em todas as linhas dele.
    """
    corte = linha.rfind(",")
    if corte < 0:
        return None
    return sum(linha[: corte + 1].encode("latin-1", errors="replace")) % _MODULO


def _confere(linha: str, campos: list[str]) -> bool:
    """A soma de verificação da linha bate?"""
    esperada = _soma_de_verificacao(linha)
    if esperada is None or not campos:
        return True
    try:
        return int(campos[-1].strip().strip('"'), 16) == esperada
    except ValueError:
        return True   # campo que não é hexadecimal: não é uma soma, não julga


def _par(linhas: list[str], i: int) -> dict[str, str]:
    """O par nomes/valores das linhas `i` e `i+1`, sem a soma de verificação."""
    if i + 1 >= len(linhas):
        return {}
    nomes = _campos(linhas[i])
    valores = _campos(linhas[i + 1])
    # `strict=False` de proposito: um rele que escreve menos valores do que
    # nomes nao pode derrubar a leitura do arquivo inteiro.
    return {n.strip(): v.strip()
            for n, v in zip(nomes[:-1], valores[:-1], strict=False)}


def _float(texto: str) -> float:
    """O número, ou `NaN` quando o campo está vazio ou preenchido com `$`.

    O relé escreve `$$$$.$$` na distância da falta quando não calculou nenhuma,
    e deixa em branco as colunas `ANAnn` que ninguém configurou. As duas coisas
    são ausência de dado, que no `Record` é `NaN` — nunca zero, que seria uma
    medição de valor zero.
    """
    try:
        return float(texto)
    except (TypeError, ValueError):
        return math.nan


def _inteiro(texto: str, padrao: int = 0) -> int:
    try:
        return int(float(texto))
    except (TypeError, ValueError):
        return padrao


def _nome_e_unidade(coluna: str) -> tuple[str, str]:
    """`IA(A)` vira `("IA", "A")`; `ANA01` vira `("ANA01", "")`."""
    achou = _UNIDADE_NO_NOME.match(coluna.strip())
    if achou is None:
        return coluna.strip(), ""
    return achou.group("nome").strip(), achou.group("unidade").strip()


# ---------------------------------------------------------------------------
# O desenho das colunas
# ---------------------------------------------------------------------------

class _Colunas:
    """Onde está cada coisa numa linha de amostra.

    A posição não é fixa entre famílias de relé — um 351 tem menos colunas de
    onda que um 451 — então nada aqui é contado na mão. A coluna `TRIG` marca o
    fim das ondas; o campo seguinte é a tira de digitais; o último é a soma de
    verificação.
    """

    def __init__(self, cabecalho: list[str]) -> None:
        self.cabecalho = cabecalho
        self.total = len(cabecalho)
        self.soma = self.total - 1

        limpos = [c.strip().upper() for c in cabecalho]
        self.trigger = limpos.index("TRIG") if "TRIG" in limpos else None

        candidato = (self.trigger + 1) if self.trigger is not None else self.total - 2
        self.digitais: int | None = candidato
        if not (0 <= candidato < self.soma) or len(cabecalho[candidato].split()) < 2:
            # Sem uma lista de nomes separados por espaço ali, não há digitais.
            self.digitais = None

        if self.trigger is not None:
            self.fim_das_ondas = self.trigger
        elif self.digitais is not None:
            self.fim_das_ondas = self.digitais
        else:
            self.fim_das_ondas = self.soma

    @property
    def nomes_dos_digitais(self) -> list[str]:
        if self.digitais is None:
            return []
        return self.cabecalho[self.digitais].split()


# ---------------------------------------------------------------------------
# Digitais
# ---------------------------------------------------------------------------

def _desempacotar(tiras: list[str], quantos: int) -> np.ndarray:
    """A tira de hexadecimal de cada amostra vira `(n_digitais, n_amostras)`.

    Um bit por nome, do mais significativo para o menos, na ordem dos nomes —
    que é exatamente a ordem que `np.unpackbits` produz. Ver o cabeçalho deste
    arquivo para a conferência contra o COMTRADE do mesmo evento.
    """
    if quantos <= 0 or not tiras:
        return np.empty((max(quantos, 0), len(tiras)), dtype=np.int8)

    saida = np.zeros((quantos, len(tiras)), dtype=np.int8)
    for coluna, tira in enumerate(tiras):
        limpa = tira.strip()
        if len(limpa) % 2:
            limpa += "0"          # nibble solto no fim: completa, nunca descarta
        try:
            bytes_ = bytes.fromhex(limpa)
        except ValueError:
            continue              # amostra corrompida fica em zero, o resto vive
        bits = np.unpackbits(np.frombuffer(bytes_, dtype=np.uint8))
        n = min(quantos, bits.size)
        saida[:n, coluna] = bits[:n]
    return saida


# ---------------------------------------------------------------------------
# O leitor
# ---------------------------------------------------------------------------

class CevReader:
    """Leitor CEV. Uma instância é registrada em `formats/__init__.py`."""

    name = "cev"
    extensions = (".cev",)

    def sniff(self, path: Path) -> bool:
        """Este arquivo é um CEV?

        A primeira linha de um CEV é sempre `"FID","RID","SID",<soma>`. Nenhum
        outro formato do parque começa assim, e olhar 256 bytes basta.
        """
        try:
            with open(path, "rb") as f:
                comeco = f.read(256)
        except OSError:
            return False
        return bool(_ASSINATURA.match(comeco))

    def read(self, path: Path) -> Record:
        caminho = Path(path)
        if not caminho.is_file():
            raise FormatError(f"arquivo nao encontrado: {caminho}")

        linhas = _linhas(_decodificar(caminho.read_bytes()))
        if len(linhas) < 8:
            raise FormatError(
                f"{caminho.name} comeca como um CEV mas acaba na linha "
                f"{len(linhas)} — falta o cabecalho ou as amostras."
            )

        identificacao = _par(linhas, 0)
        relogio = _par(linhas, 2)
        cabecalho = _par(linhas, 4)

        colunas = _Colunas(_campos(linhas[6]))
        if colunas.total < 2:
            raise FormatError(
                f"Nao entendi a linha de titulos das colunas de {caminho.name}."
            )

        avisos: list[str] = []
        amostras, tiras, disparo_em, erradas = self._ler_amostras(linhas, colunas)
        if not amostras:
            raise FormatError(
                f"{caminho.name} tem cabecalho de CEV mas nenhuma amostra."
            )
        if erradas:
            avisos.append(
                f"Soma de verificação não bateu em {erradas} linha(s) — o "
                f"arquivo pode ter sido alterado depois de sair do relé."
            )

        n = len(amostras)
        por_ciclo = _inteiro(cabecalho.get("SAM/CYC_A", ""), 0)
        taxa = self._taxa(cabecalho, caminho)

        canais, dados, avisos_dos_canais = self._analogicos(
            colunas, cabecalho, identificacao, amostras
        )
        avisos.extend(avisos_dos_canais)

        nomes = colunas.nomes_dos_digitais
        digitais = _desempacotar(tiras, len(nomes))
        status = tuple(
            StatusChannel(index=i, name=nome, component=identificacao.get("RID", ""))
            for i, nome in enumerate(nomes)
        )

        tempo = np.arange(n, dtype=np.float64) / taxa
        instante_do_disparo = self._disparo(relogio)
        if disparo_em is None:
            inicio = instante_do_disparo
            if instante_do_disparo is not None:
                avisos.append(
                    "Nenhuma amostra traz a marca do disparo; usei a hora do "
                    "cabeçalho como a da primeira amostra."
                )
        elif instante_do_disparo is not None:
            inicio = instante_do_disparo - timedelta(seconds=disparo_em / taxa)
        else:
            inicio = None

        relatos = self._noticias_do_rele(cabecalho)

        return Record(
            source=caminho,
            format_name="cev",
            station=identificacao.get("SID", ""),
            device_id=identificacao.get("FID", ""),
            line_frequency=float(_inteiro(cabecalho.get("NFREQ", "60"), 60)),
            start_time=inicio,
            trigger_time=instante_do_disparo,
            analog_channels=canais,
            status_channels=status,
            sample_rates=(SampleRate(rate_hz=taxa, last_sample=n),),
            analog=dados,
            status=digitais,
            time=tempo,
            # DECLARADO, e não deduzido: quem diz é o FORMATO. Um CEV a 4 ou
            # 8 amostras por ciclo é o relatório de evento filtrado da SEL, e
            # filtrar de novo só acrescentaria mais um ciclo de atraso.
            #
            # A dedução por harmônico (`analysis/filtragem.py`) não resolve
            # isto sozinha: ela foi calibrada para um COMTRADE binário de 16
            # bits, e o CEV imprime a corrente com três algarismos (`-46`,
            # `57`). Essa precisão de impressão vira 0,46 % de distorção
            # aparente — acima do limiar de ruído — e o veredito saía
            # DESCONHECIDO com o botão do filtro solto.
            filtering=(Filtering.FILTRADO if 0 < por_ciclo <= FILTRADO_ATE
                       else Filtering.DESCONHECIDO),
            filtering_source=(FilteringSource.DECLARADO
                              if 0 < por_ciclo <= FILTRADO_ATE
                              else FilteringSource.DEDUZIDO),
            notes=tuple(avisos),
            relatos=tuple(relatos),
        )

    # -- pedaços da leitura -------------------------------------------------

    @staticmethod
    def _ler_amostras(
        linhas: list[str], colunas: _Colunas
    ) -> tuple[list[list[str]], list[str], int | None, int]:
        """As linhas de amostra, a tira de digitais de cada uma e onde disparou.

        Para no marcador `SETTINGS`: dali para baixo o arquivo traz os ajustes
        do relé num campo só, com quebras de linha dentro, e não é mais CSV.
        """
        amostras: list[list[str]] = []
        tiras: list[str] = []
        disparo_em: int | None = None
        erradas = 0

        for linha in linhas[7:]:
            if not linha.strip():
                continue
            campos = _campos(linha)
            if campos and campos[0].strip().strip('"').upper() == _FIM_DOS_DADOS:
                break
            if len(campos) != colunas.total:
                break
            if not _confere(linha, campos):
                erradas += 1
            if (colunas.trigger is not None
                    and ">" in campos[colunas.trigger]
                    and disparo_em is None):
                disparo_em = len(amostras)
            amostras.append(campos)
            if colunas.digitais is not None:
                tiras.append(campos[colunas.digitais])

        return amostras, tiras, disparo_em, erradas

    @staticmethod
    def _taxa(cabecalho: dict[str, str], caminho: Path) -> float:
        """A taxa de amostragem em hertz.

        A taxa sai do nominal (`NFREQ`), não da frequência medida (`FREQ`): o
        `Record` usa a taxa para montar o eixo de tempo, e um eixo que muda de
        escala porque a rede oscilou 0,01 Hz seria pior que inútil.
        """
        por_ciclo = _inteiro(cabecalho.get("SAM/CYC_A", ""), 0)
        nominal = float(_inteiro(cabecalho.get("NFREQ", "60"), 60)) or 60.0
        if por_ciclo <= 0:
            raise FormatError(
                f"{caminho.name} nao declara quantas amostras por ciclo gravou "
                f"(campo SAM/CYC_A). Sem isso nao ha' eixo de tempo."
            )
        return por_ciclo * nominal

    @staticmethod
    def _analogicos(
        colunas: _Colunas,
        cabecalho: dict[str, str],
        identificacao: dict[str, str],
        amostras: list[list[str]],
    ) -> tuple[tuple[AnalogChannel, ...], np.ndarray, list[str]]:
        """Os canais analógicos e a matriz `(n_canais, n_amostras)`.

        Aqui mora a multiplicação por raiz de 2 — só nas colunas de onda, e só
        nas que declaram unidade de corrente ou de tensão. Ver o item 1 do
        cabeçalho deste arquivo.
        """
        equipamento = identificacao.get("RID", "")
        primario = cabecalho.get("PRIM_VAL", "").strip().strip('"').upper() == "YES"
        avisos: list[str] = []

        # --- 1. o que cada coluna é -----------------------------------------
        rotulos: list[str] = []          # o título como está no arquivo
        nomes: list[str] = []            # o nome que vai para a tela
        unidades: list[str] = []
        for i in range(colunas.fim_das_ondas):
            rotulo = colunas.cabecalho[i].strip()
            nome, unidade = _nome_e_unidade(rotulo)
            ana = _COLUNA_ANA.match(nome)
            if ana is not None:
                # `ANA07` não é um canal: é a grandeza que o relé chamou de
                # `LI1M` no campo `ERAQ07`. Sem esse nome a coluna não diz nada.
                nome = cabecalho.get(f"ERAQ{int(ana.group(1)):02d}", "").strip() or nome
            rotulos.append(rotulo)
            nomes.append(nome)
            unidades.append(unidade)

        if not nomes:
            return (), np.empty((0, len(amostras))), avisos

        # --- 2. os valores ---------------------------------------------------
        crus = np.empty((len(nomes), len(amostras)), dtype=np.float64)
        for i in range(len(nomes)):
            crus[i] = [_float(a[i]) for a in amostras]

        # --- 3. fora as colunas que o relé não configurou --------------------
        # Uma coluna `ANAnn` sem nome no `ERAQnn` E sem um número sequer é uma
        # vaga vazia do relatório, não um canal que ficou mudo. Deixá-la entrar
        # enche o buscador de sinais com seis linhas que nunca terão dado.
        vazia = [
            _COLUNA_ANA.match(nomes[i]) is not None and not np.isfinite(crus[i]).any()
            for i in range(len(nomes))
        ]
        if any(vazia):
            avisos.append(
                f"{sum(vazia)} coluna(s) sem nada dentro ficaram de fora — "
                f"vagas que o relé não configurou."
            )
        ficam = [i for i in range(len(nomes)) if not vazia[i]]

        # --- 4. nomes repetidos ----------------------------------------------
        # O 451 escreve `FREQ` duas vezes: a coluna de onda `FREQ(Hz)` e a
        # grandeza `ERAQ14`. São medidas diferentes com o mesmo nome. Quem
        # desempata é a coluna `ANAnn`, que ganha o próprio título entre
        # parênteses — outro nome do arquivo, não um inventado por nós. A
        # coluna de onda fica com o nome limpo, que é o que o engenheiro espera
        # ver no gráfico.
        quantas: dict[str, int] = {}
        for i in ficam:
            quantas[nomes[i]] = quantas.get(nomes[i], 0) + 1

        canais: list[AnalogChannel] = []
        dados = np.empty((len(ficam), len(amostras)), dtype=np.float64)
        houve_raiz = False
        for destino, i in enumerate(ficam):
            nome = nomes[i]
            if quantas[nome] > 1 and _COLUNA_ANA.match(rotulos[i]) is not None:
                nome = f"{nome} ({rotulos[i]})"
            fator = (RMS_PARA_INSTANTANEO
                     if unidades[i].upper() in UNIDADES_DE_ONDA else 1.0)
            houve_raiz = houve_raiz or fator != 1.0
            dados[destino] = crus[i] * fator
            canais.append(AnalogChannel(
                index=destino,
                name=nome,
                unit=unidades[i],
                component=equipamento,
                scaling="P" if primario else "S",
            ))

        if houve_raiz:
            avisos.append(
                "Amostras vêm em eficaz; converti corrente e tensão para "
                "instantâneo (×√2)."
            )

        return tuple(canais), dados, avisos

    @staticmethod
    def _disparo(relogio: dict[str, str]) -> datetime | None:
        """A hora do cabeçalho — que é a do DISPARO, não a da primeira amostra."""
        try:
            return datetime(
                year=int(relogio["YEAR"]),
                month=int(relogio["MONTH"]),
                day=int(relogio["DAY"]),
                hour=int(relogio["HOUR"]),
                minute=int(relogio["MIN"]),
                second=int(relogio["SEC"]),
                microsecond=_inteiro(relogio.get("MSEC", "0")) * 1000,
            )
        except (KeyError, ValueError):
            return None

    @staticmethod
    def _noticias_do_rele(cabecalho: dict[str, str]) -> list[str]:
        """O que o RELÉ concluiu sozinho, para a tela mostrar como informação.

        Não são avisos. Já foram, e carimbar `⚠` em "o relé classificou o
        evento como AB T" ensina o usuário a ignorar o triângulo.
        """
        recado: list[str] = []
        evento = cabecalho.get("EVENT", "").strip().strip('"')
        if evento:
            recado.append(f'Relé classificou o evento como "{evento}"')
        distancia = _float(cabecalho.get("LOCATION", ""))
        if math.isfinite(distancia):
            recado.append(f"Relé calculou a falta a {distancia:g} unidade(s) "
                          f"(campo LOCATION)")
        return recado
