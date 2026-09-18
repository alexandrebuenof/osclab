"""Leitor COMTRADE — IEEE C37.111 / IEC 60255-24.

Cobre o que os arquivos reais do parque da distribuidora trouxeram, que é mais
do que a norma sozinha faria supor:

* **Edições 1991, 1999 e 2013** — e qualquer outro ano no terceiro campo da
  primeira linha. Um relé MiCOM da Schneider escreve `2001` ali, que não existe
  como edição. Recusar o arquivo por causa disso seria transformar uma
  esquisitice do fabricante num arquivo ilegível, então o ano só decide quais
  campos OPCIONAIS procurar.
* **`.cfg` + `.dat` separados** e **`.cff`** (arquivo único da edição 2013).
* **ASCII, BINARY (16 bits), BINARY32 e FLOAT32.**
* **`nrates = 0`** — nesse caso a taxa é desconhecida e o tempo vem dos
  carimbos de cada amostra dentro do `.dat`. É o que um GE 850 gera.
* **`timemult` ausente** — a Schneider simplesmente não escreve a linha.
* **Fim de linha LF ou CRLF**, e codificação que não é UTF-8 (nomes de
  subestação com acento vêm em cp1252).

## A ordem das linhas do `.cfg`

```
1              nome_da_subestacao , id_do_equipamento , ano_da_edicao
2              total , NA , ND                    (ex.: 686,14A,672D)
3..2+NA        canais analogicos
..             canais digitais
               frequencia nominal
               nrates
nrates ou 1    taxa , ultima_amostra
               data/hora da primeira amostra
               data/hora do disparo
               ASCII | BINARY | BINARY32 | FLOAT32
(opcional)     timemult
(2013)         time_code , local_code
(2013)         tmq_code , leapsec
```

## O detalhe que mais estraga resultado

Os valores no `.dat` são inteiros crus do conversor A/D. Cada canal traz um
fator `a` e um deslocamento `b`, e o valor em unidade de engenharia é
`a * cru + b`. Errar isso não dá erro nenhum: dá um gráfico com a forma certa e
a amplitude errada. Por isso a conversão acontece aqui, e um `Record` nunca
carrega inteiro cru.
"""

from __future__ import annotations

import re
from datetime import datetime
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

#: Valor que a norma reserva para "amostra ausente" no formato ASCII.
AUSENTE_ASCII = 99999

#: Tipos de dado que sabemos ler, e o dtype numpy de cada amostra analógica.
TIPOS = {
    "ASCII": None,
    "BINARY": np.dtype("<i2"),
    "BINARY32": np.dtype("<i4"),
    "FLOAT32": np.dtype("<f4"),
}


# ---------------------------------------------------------------------------
# Leitura de texto
# ---------------------------------------------------------------------------

def _decodificar(bruto: bytes) -> str:
    """Bytes de um `.cfg` viram texto.

    A norma não fixa codificação. Na prática aparecem UTF-8 (às vezes com BOM) e
    cp1252 — nomes de subestação com acento. `cp1252` nunca falha, então serve de
    último recurso: um acento errado é muito melhor do que um arquivo que não
    abre.
    """
    for codec in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return bruto.decode(codec)
        except UnicodeDecodeError:
            continue
    return bruto.decode("cp1252", errors="replace")


def _linhas(texto: str) -> list[str]:
    """Linhas sem o `\\r` do CRLF e sem linhas vazias no fim."""
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while linhas and not linhas[-1].strip():
        linhas.pop()
    return linhas


def _campos(linha: str) -> list[str]:
    return [c.strip() for c in linha.split(",")]


def _float(texto: str, padrao: float = 0.0) -> float:
    try:
        return float(texto)
    except (TypeError, ValueError):
        return padrao


def _int(texto: str, padrao: int = 0) -> int:
    try:
        return int(float(texto))
    except (TypeError, ValueError):
        return padrao


def _data_hora(linha: str) -> datetime | None:
    """`dd/mm/aaaa,hh:mm:ss.ssssss` — a ordem que a norma manda.

    Devolve `None` quando a linha não é uma data reconhecível, em vez de
    estourar: um carimbo de tempo ruim não deve impedir alguém de olhar as
    formas de onda.
    """
    partes = _campos(linha)
    if len(partes) < 2:
        return None
    data, hora = partes[0], partes[1]
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$", data)
    if not m:
        return None
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if ano < 100:
        ano += 2000
    h = re.match(r"^\s*(\d{1,2}):(\d{1,2}):(\d{1,2})(?:\.(\d{1,6}))?\s*$", hora)
    if not h:
        return None
    micro = int((h.group(4) or "0").ljust(6, "0"))
    try:
        return datetime(ano, mes, dia, int(h.group(1)), int(h.group(2)),
                        int(h.group(3)), micro)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# O .cfg
# ---------------------------------------------------------------------------

class _Cfg:
    """O `.cfg` já interpretado. Estrutura interna — não sai deste módulo."""

    def __init__(self) -> None:
        self.station = ""
        self.device = ""
        self.revision = ""
        self.analogs: list[AnalogChannel] = []
        self.status: list[StatusChannel] = []
        self.escala: list[tuple[float, float]] = []   # (a, b) por canal analógico
        self.line_frequency = 60.0
        self.rates: list[SampleRate] = []
        self.start: datetime | None = None
        self.trigger: datetime | None = None
        self.file_type = "BINARY"
        self.timemult = 1.0
        self.time_code = ""
        self.avisos: list[str] = []

    @property
    def n_analog(self) -> int:
        return len(self.analogs)

    @property
    def n_status(self) -> int:
        return len(self.status)

    @property
    def n_samples(self) -> int:
        return self.rates[-1].last_sample if self.rates else 0


def _parse_cfg(texto: str) -> _Cfg:
    linhas = _linhas(texto)
    if len(linhas) < 4:
        raise FormatError("O .cfg tem linhas de menos para ser um COMTRADE.")

    cfg = _Cfg()

    # --- linha 1: subestação, equipamento, edição --------------------------
    c = _campos(linhas[0])
    cfg.station = c[0] if len(c) > 0 else ""
    cfg.device = c[1] if len(c) > 1 else ""
    cfg.revision = c[2] if len(c) > 2 else "1991"
    if cfg.revision not in ("1991", "1999", "2013"):
        cfg.avisos.append(
            f"O arquivo declara a edicao '{cfg.revision}', que nao e' uma edicao "
            f"da norma. Li como 1999."
        )

    # --- linha 2: quantos canais ------------------------------------------
    c = _campos(linhas[1])
    if len(c) < 3:
        raise FormatError("A segunda linha do .cfg nao traz a contagem de canais.")
    n_analog = _int(c[1].rstrip("Aa"))
    n_status = _int(c[2].rstrip("Dd"))
    if n_analog == 0 and n_status == 0:
        raise FormatError("O .cfg declara zero canais.")

    i = 2

    # --- canais analógicos -------------------------------------------------
    for k in range(n_analog):
        if i >= len(linhas):
            raise FormatError(
                f"O .cfg acaba antes de descrever os {n_analog} canais "
                f"analogicos declarados (parou no {k})."
            )
        c = _campos(linhas[i])
        i += 1
        # An, id, ph, ccbm, uu, a, b, skew, min, max, primary, secondary, PS
        cfg.analogs.append(AnalogChannel(
            index=k,
            name=c[1] if len(c) > 1 else f"A{k + 1}",
            unit=c[4] if len(c) > 4 else "",
            phase=c[2] if len(c) > 2 else "",
            component=c[3] if len(c) > 3 else "",
            primary=_float(c[10], 1.0) if len(c) > 10 else 1.0,
            secondary=_float(c[11], 1.0) if len(c) > 11 else 1.0,
            scaling=(c[12] or "S").upper() if len(c) > 12 else "S",
            skew=_float(c[7]) if len(c) > 7 else 0.0,
        ))
        cfg.escala.append((_float(c[5], 1.0) if len(c) > 5 else 1.0,
                           _float(c[6], 0.0) if len(c) > 6 else 0.0))

    # --- canais digitais ---------------------------------------------------
    for k in range(n_status):
        if i >= len(linhas):
            raise FormatError(
                f"O .cfg acaba antes de descrever os {n_status} canais digitais "
                f"declarados (parou no {k})."
            )
        c = _campos(linhas[i])
        i += 1
        # Dn, id, ph, ccbm, y
        cfg.status.append(StatusChannel(
            index=k,
            name=c[1] if len(c) > 1 else f"D{k + 1}",
            phase=c[2] if len(c) > 2 else "",
            component=c[3] if len(c) > 3 else "",
            normal_state=_int(c[4]) if len(c) > 4 else 0,
        ))

    def proxima() -> str:
        nonlocal i
        linha = linhas[i] if i < len(linhas) else ""
        i += 1
        return linha

    # --- frequência nominal ------------------------------------------------
    cfg.line_frequency = _float(proxima(), 60.0) or 60.0

    # --- taxas de amostragem -----------------------------------------------
    n_rates = _int(proxima())
    # Mesmo com nrates = 0 existe UMA linha de taxa, com samp = 0. É o jeito que
    # a norma tem de dizer "a taxa varia; use o carimbo de cada amostra".
    for _ in range(max(n_rates, 1)):
        c = _campos(proxima())
        if len(c) >= 2:
            cfg.rates.append(SampleRate(rate_hz=_float(c[0]),
                                        last_sample=_int(c[1])))
    if not cfg.rates:
        raise FormatError("O .cfg nao traz nenhuma linha de taxa de amostragem.")

    # --- carimbos de tempo -------------------------------------------------
    cfg.start = _data_hora(proxima())
    cfg.trigger = _data_hora(proxima())

    # --- tipo do arquivo de dados -----------------------------------------
    tipo = proxima().strip().upper()
    if tipo not in TIPOS:
        raise FormatError(
            f"Tipo de dado '{tipo}' desconhecido. "
            f"Este leitor entende: {', '.join(TIPOS)}."
        )
    cfg.file_type = tipo

    # --- opcionais: timemult e os campos de 2013 ---------------------------
    resto = [linhas[j] for j in range(i, len(linhas))]
    if resto:
        mult = _float(resto[0], 0.0)
        # A Schneider não escreve esta linha. Um `timemult` de 0 também não
        # significa nada, então nos dois casos vale 1.
        cfg.timemult = mult if mult > 0 else 1.0
    if len(resto) > 1:
        cfg.time_code = resto[1].strip()

    return cfg


# ---------------------------------------------------------------------------
# O .dat
# ---------------------------------------------------------------------------

def _tempo_das_taxas(cfg: _Cfg, n: int) -> np.ndarray | None:
    """Tempo de cada amostra a partir das taxas declaradas.

    Devolve `None` quando alguma taxa é zero — aí o tempo tem que vir dos
    carimbos do `.dat`.
    """
    if any(r.rate_hz <= 0 for r in cfg.rates):
        return None
    t = np.empty(n, dtype=np.float64)
    inicio, t0 = 0, 0.0
    for r in cfg.rates:
        fim = min(r.last_sample, n)
        if fim <= inicio:
            continue
        t[inicio:fim] = t0 + np.arange(fim - inicio) / r.rate_hz
        t0 = t[fim - 1] + 1.0 / r.rate_hz
        inicio = fim
    if inicio < n:                      # o .dat tem mais amostras do que o .cfg diz
        ultima = cfg.rates[-1].rate_hz
        t[inicio:] = t0 + np.arange(n - inicio) / ultima
    return t


def _desempacotar_digitais(palavras: np.ndarray, n_status: int) -> np.ndarray:
    """Palavras de 16 bits viram uma matriz (n_canais, n_amostras) de 0 e 1.

    O bit 0 da primeira palavra é o canal digital 1. Tudo vetorizado: um laço
    Python aqui custaria segundos num registro de meio milhão de amostras.
    """
    if n_status == 0 or palavras.size == 0:
        return np.empty((n_status, palavras.shape[0]), dtype=np.int8)
    bits = (palavras[:, :, None] >> np.arange(16)) & 1        # (amostras, palavras, 16)
    bits = bits.reshape(palavras.shape[0], -1)[:, :n_status]  # (amostras, canais)
    return bits.T.astype(np.int8)


def _ler_binario(bruto: bytes, cfg: _Cfg) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Amostras de um `.dat` binário.

    Sobra de bytes no fim é comum e quase sempre inofensiva: o `.dat` de um
    SEL-TWFL termina com 64 bytes `0x1A` (o antigo fim-de-arquivo do DOS) para
    fechar o bloco. Por isso o critério de erro não é "sobrou byte", e sim
    "nao ha' amostras completas suficientes para o que o .cfg declarou" — que é
    o sintoma de verdade de um `.cfg` e um `.dat` de registros diferentes.
    """
    na, nd = cfg.n_analog, cfg.n_status
    palavras = (nd + 15) // 16
    registro = np.dtype([
        ("n", "<u4"),
        ("t", "<u4"),
        ("a", TIPOS[cfg.file_type], (na,)),
        ("d", "<u2", (palavras,)),
    ])
    completas = len(bruto) // registro.itemsize
    declaradas = cfg.n_samples

    if completas == 0 or (declaradas and completas < declaradas):
        raise FormatError(
            f"O .dat nao bate com o .cfg.\n"
            f"       O .cfg descreve {na} canais analogicos e {nd} digitais, o "
            f"que da' {registro.itemsize} bytes por amostra, e declara "
            f"{declaradas} amostras\n"
            f"       ({declaradas * registro.itemsize} bytes). O .dat tem "
            f"{len(bruto)} bytes, que dao para {completas} amostras.\n"
            f"       Quase sempre isso e' um .cfg e um .dat de registros "
            f"diferentes, ou uma copia incompleta."
        )

    usar = declaradas if declaradas else completas
    arr = np.frombuffer(bruto, dtype=registro, count=usar)

    # A primeira coluna de cada amostra e' o NUMERO da amostra, que a norma manda
    # ser sequencial. Isso e' uma assinatura barata e forte: lido com o tamanho
    # de registro errado, o campo vira lixo e para de crescer.
    #
    # Sem esta conferencia, um .dat de OUTRO registro passa despercebido sempre
    # que o tamanho por amostra der a mesma divisao — e o resultado e' um grafico
    # perfeitamente desenhado de um evento que nao e' o que se esta' analisando.
    numeros = arr["n"].astype(np.int64)
    if numeros.size > 1 and not np.all(np.diff(numeros) > 0):
        raise FormatError(
            f"O .cfg e o .dat nao sao do mesmo registro.\n"
            f"       Li o .dat como {na} canais analogicos e {nd} digitais (o que "
            f"o .cfg descreve), e a numeracao\n"
            f"       das amostras saiu fora de ordem — sinal de que o .dat e' de "
            f"outro evento.\n"
            f"       Confira se os dois arquivos vieram da mesma exportacao."
        )

    if completas > usar:
        cfg.avisos.append(
            f"O .dat tem {completas} amostras completas e o .cfg declara {usar}; "
            f"usei as {usar} declaradas."
        )
    return arr["a"], arr["d"], arr["t"]


def _ler_ascii(texto: str, cfg: _Cfg) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    na, nd = cfg.n_analog, cfg.n_status
    linhas = [ln for ln in _linhas(texto) if ln.strip()]
    if not linhas:
        raise FormatError("O .dat em ASCII esta vazio.")
    tabela = np.genfromtxt(linhas, delimiter=",", dtype=np.float64,
                           invalid_raise=False, usemask=False)
    if tabela.ndim == 1:
        tabela = tabela.reshape(1, -1)
    if tabela.shape[1] < 2 + na + nd:
        raise FormatError(
            f"O .dat em ASCII tem {tabela.shape[1]} colunas, mas o .cfg pede "
            f"{2 + na + nd} (numero da amostra, tempo, {na} analogicos, "
            f"{nd} digitais)."
        )
    carimbos = np.nan_to_num(tabela[:, 1]).astype(np.int64)
    analog = tabela[:, 2:2 + na]
    analog[analog == AUSENTE_ASCII] = np.nan
    digital = tabela[:, 2 + na:2 + na + nd].T
    return analog, digital, carimbos


# ---------------------------------------------------------------------------
# .cff — o arquivo único da edição 2013
# ---------------------------------------------------------------------------

_MARCA_CFF = re.compile(rb"---\s*file\s+type\s*:\s*([A-Za-z0-9]+)[^\r\n]*---[^\S\r\n]*\r?\n",
                        re.IGNORECASE)


def _partir_cff(bruto: bytes) -> tuple[str, bytes, str]:
    """Separa um `.cff` em (texto do cfg, bytes do dat, tipo do dat).

    As seções são separadas por linhas `--- file type: XXX ---`. A seção DAT
    pode ser binária, então o corte é feito sobre os bytes e nunca sobre texto
    decodificado.
    """
    marcas = list(_MARCA_CFF.finditer(bruto))
    if not marcas:
        raise FormatError("Este .cff nao tem as marcas '--- file type: ... ---'.")
    secoes: dict[str, bytes] = {}
    for k, m in enumerate(marcas):
        fim = marcas[k + 1].start() if k + 1 < len(marcas) else len(bruto)
        secoes[m.group(1).upper().decode("ascii")] = bruto[m.end():fim]
    if "CFG" not in secoes or "DAT" not in secoes:
        raise FormatError(
            f"O .cff tem as secoes {sorted(secoes)} — faltam CFG e/ou DAT."
        )
    return _decodificar(secoes["CFG"]), secoes["DAT"], ""


# ---------------------------------------------------------------------------
# O leitor
# ---------------------------------------------------------------------------

class ComtradeReader:
    """Leitor COMTRADE. Uma instância é registrada em `formats/__init__.py`."""

    name = "comtrade"
    extensions = (".cfg", ".cff")

    def sniff(self, path: Path) -> bool:
        """Este arquivo é um COMTRADE?

        Olha o conteúdo, não a extensão: `.cfg` é usado por meio mundo. A
        assinatura procurada é a segunda linha, `total,NNa,NNd` — específica o
        bastante para não dar falso positivo e barata o bastante para rodar em
        qualquer arquivo.
        """
        try:
            with open(path, "rb") as f:
                comeco = f.read(4096)
        except OSError:
            return False
        if _MARCA_CFF.search(comeco):
            return True
        linhas = _linhas(_decodificar(comeco))
        if len(linhas) < 2:
            return False
        return bool(re.match(r"^\s*\d+\s*,\s*\d+\s*[Aa]\s*,\s*\d+\s*[Dd]\s*$",
                             linhas[1]))

    def read(self, path: Path) -> Record:
        caminho = Path(path)
        if not caminho.is_file():
            raise FormatError(f"arquivo nao encontrado: {caminho}")

        bruto = caminho.read_bytes()
        if _MARCA_CFF.search(bruto[:4096]):
            texto_cfg, dados, _ = _partir_cff(bruto)
            origem_dat = caminho
        else:
            texto_cfg = _decodificar(bruto)
            dat = _achar_dat(caminho)
            if dat is None:
                raise FormatError(
                    f"Achei o {caminho.name} mas nao o .dat correspondente.\n"
                    f"       Um COMTRADE sao dois arquivos: o .cfg descreve os "
                    f"canais e o .dat traz as amostras.\n"
                    f"       Copie os dois para a mesma pasta, com o mesmo nome."
                )
            dados = dat.read_bytes()
            origem_dat = dat

        cfg = _parse_cfg(texto_cfg)

        if cfg.file_type == "ASCII":
            analog_cru, digital, carimbos = _ler_ascii(_decodificar(dados), cfg)
        else:
            analog_cru, digital, carimbos = _ler_binario(dados, cfg)

        n = analog_cru.shape[0] if analog_cru.ndim == 2 else len(carimbos)

        # --- conversão para unidade de engenharia --------------------------
        a = np.array([e[0] for e in cfg.escala], dtype=np.float64)
        b = np.array([e[1] for e in cfg.escala], dtype=np.float64)
        analog = (analog_cru.T.astype(np.float64) * a[:, None] + b[:, None]
                  if cfg.n_analog else np.empty((0, n)))

        # --- digitais -------------------------------------------------------
        if cfg.file_type == "ASCII":
            status = np.nan_to_num(digital).astype(np.int8)
        else:
            status = _desempacotar_digitais(digital, cfg.n_status)

        # --- tempo ----------------------------------------------------------
        tempo = _tempo_das_taxas(cfg, n)
        avisos = list(cfg.avisos)
        if tempo is None:
            tempo = carimbos.astype(np.float64) * cfg.timemult * 1e-6
            avisos.append(
                "O .cfg nao declara a taxa de amostragem (nrates = 0); o tempo "
                "veio do carimbo de cada amostra."
            )
        if origem_dat != caminho:
            pass  # o .dat veio de um arquivo separado — normal, não é aviso

        return Record(
            source=caminho,
            format_name=f"comtrade-{cfg.revision}",
            station=cfg.station,
            device_id=cfg.device,
            line_frequency=cfg.line_frequency,
            start_time=cfg.start,
            trigger_time=cfg.trigger,
            time_quality=cfg.time_code,
            analog_channels=tuple(cfg.analogs),
            status_channels=tuple(cfg.status),
            sample_rates=tuple(cfg.rates),
            analog=analog,
            status=status,
            time=tempo,
            filtering=Filtering.DESCONHECIDO,
            filtering_source=FilteringSource.DEDUZIDO,
            notes=tuple(avisos),
        )


def _achar_dat(cfg_path: Path) -> Path | None:
    """O `.dat` que acompanha este `.cfg`.

    O Windows não distingue maiúsculas, mas o Linux sim — e os arquivos que a
    distribuidora exporta vêm ora `.DAT`, ora `.dat`. Procurar as duas grafias
    aqui evita um "arquivo nao encontrado" que só acontece num sistema.
    """
    for sufixo in (".dat", ".DAT", ".Dat"):
        candidato = cfg_path.with_suffix(sufixo)
        if candidato.is_file():
            return candidato
    # Última tentativa: varrer a pasta ignorando maiúsculas.
    alvo = cfg_path.stem.lower() + ".dat"
    for vizinho in cfg_path.parent.iterdir():
        if vizinho.is_file() and vizinho.name.lower() == alvo:
            return vizinho
    return None
