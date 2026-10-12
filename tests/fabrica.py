"""Fábrica de arquivos COMTRADE sintéticos para os testes.

Por que sintéticos e não os arquivos reais da distribuidora: uma oscilografia de
verdade identifica instalação, data e comportamento da rede, e este repositório
é público. Além disso um arquivo sintético tem resposta CONHECIDA — dá para
afirmar "a senoide tinha 100 A de pico, o leitor tem que devolver 100 A", o que
um arquivo real nunca permite.

Os arquivos reais continuam sendo testados, mas por fora: ver
`test_comtrade_reais.py`.

Cada variação aqui existe porque apareceu num arquivo real do parque:

* `revisao="2001"` — um MiCOM da Schneider escreve um ano que não é edição
  nenhuma da norma.
* `nrates=0` — um GE 850 não declara taxa; o tempo vem do carimbo por amostra.
* `timemult=False` — a Schneider não escreve a última linha.
* `crlf=False` — o GE grava com fim de linha do Unix.
* `lixo_no_fim` — o SEL-TWFL fecha o `.dat` com 64 bytes `0x1A`.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

PICO = 100.0          #: pico da senoide gerada, em unidade de engenharia
ESCALA = 0.01         #: fator `a` de cada canal — o leitor tem que aplicá-lo


def _instantes(n: int, taxa: float,
               taxas: list[tuple[float, int]] | None) -> np.ndarray:
    """Os instantes de cada amostra, em segundos.

    Com `taxas`, o passo muda de trecho para trecho — e tanto os carimbos do
    arquivo quanto a própria onda saem DAQUI. Gerar a onda com uma taxa fixa e
    carimbar com outra faria o arquivo mentir sobre si mesmo, e o teste passaria
    a testar a mentira.
    """
    if not taxas:
        return np.arange(n) / taxa

    passos, anterior = [], 0
    for hz, ate in taxas:
        passos.extend([1.0 / hz] * (min(int(ate), n) - anterior))
        anterior = min(int(ate), n)
    passos.extend([passos[-1]] * (n - len(passos)))
    return np.concatenate(([0.0], np.cumsum(passos)[:-1]))


def _senoides(na: int, freq: float, t: np.ndarray) -> np.ndarray:
    """(na, n) senoides defasadas de 120°, com `PICO` de amplitude.

    A defasagem é NEGATIVA: B atrasa 120° de A, C atrasa 240°. É a sequência
    ABC, que é a do sistema. Com o sinal trocado a fábrica gerava ACB — um
    registro em que toda a corrente aparece na sequência NEGATIVA, e qualquer
    conferência de componentes simétricas contra ele sairia de cabeça para
    baixo sem dar erro nenhum.
    """
    fases = np.deg2rad(-np.arange(na) * 120.0)
    return PICO * np.sin(2 * np.pi * freq * t[None, :] + fases[:, None])


def _digitais(nd: int, n: int) -> np.ndarray:
    """(nd, n) de 0/1. O canal k liga quando o bit k do índice da amostra liga.

    Padrão escolhido para o teste poder conferir o desempacotamento bit a bit
    sem precisar de tabela: é a própria contagem binária.
    """
    idx = np.arange(n)
    return ((idx[None, :] >> np.arange(nd)[:, None]) & 1).astype(np.int8)


#: Os terminais de corrente de um relé, na ordem em que ele os grava. São
#: letras porque é assim num SEL (`IAW`, `IAX`); a fábrica só precisa de um
#: sufixo que não seja dígito — ver `nome_de_canal`.
TERMINAIS = "WXYZ"


def nome_de_canal(k: int) -> str:
    """O nome do canal `k` no arquivo: `IAW`, `IBW`, `ICW`, `IAX`, ...

    **Por que não `CH1`, `CH2`, `CH3`.** Era o que a fábrica escrevia, e o nome
    de um canal não é enfeite: é de onde `formats/conjuntos.py` deduz a que
    equipamento o canal pertence — tirando a letra da fase do nome e juntando
    quem sobrou igual. De `CH1`, `CH2`, `CH3` sobram três nomes DIFERENTES,
    então nenhuma trinca fechava, e todo registro sintético exercitava um
    caminho que nenhum arquivo de relé percorre. O defeito só apareceu quando a
    lista do OscLab passou a depender da trinca: treze testes caíram de uma vez,
    e nenhum deles era sobre o que estava sendo mudado.

    Um relé nomeia os terminais em ordem alfabética, e é isso que se imita aqui:
    a cada três canais o sufixo anda uma letra, de modo que `na=6` sai com duas
    trincas — um transformador — e `na=3` com uma.
    """
    return f"I{'ABC'[k % 3]}{TERMINAIS[(k // 3) % len(TERMINAIS)]}"


def escrever_comtrade(
    pasta: Path,
    *,
    nome: str = "teste",
    revisao: str = "1999",
    tipo: str = "BINARY",
    na: int = 3,
    nd: int = 4,
    n: int = 128,
    taxa: float = 960.0,
    freq: float = 60.0,
    nrates: int = 1,
    timemult: bool = True,
    crlf: bool = True,
    codec: str = "utf-8",
    estacao: str = "SE TESTE",
    equipamento: str = "IED-TESTE",
    lixo_no_fim: int = 0,
    escala_primaria: bool = False,
    taxas: list[tuple[float, int]] | None = None,
) -> Path:
    """Escreve um par `.cfg`/`.dat` e devolve o caminho do `.cfg`."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    cfg_path = pasta / f"{nome}.cfg"
    dat_path = pasta / f"{nome}.dat"

    instantes = _instantes(n, taxa, taxas)
    analog = _senoides(na, freq, instantes)
    digital = _digitais(nd, n)
    crus = np.rint(analog / ESCALA).astype(np.int64)

    ps = "P" if escala_primaria else "S"
    linhas = [
        f"{estacao},{equipamento},{revisao}",
        f"{na + nd},{na}A,{nd}D",
    ]
    for k in range(na):
        # An,id,ph,ccbm,uu,a,b,skew,min,max,primary,secondary,PS
        linhas.append(
            f"{k + 1},{nome_de_canal(k)},{'ABC'[k % 3]},,A,"
            f"{ESCALA},0,0,-32767,32767,600.0,5.0,{ps}"
        )
    for k in range(nd):
        linhas.append(f"{k + 1},D{k + 1},,,0")
    linhas.append(f"{freq}")
    # `taxas` escreve VÁRIOS trechos, que é o que a norma permite e o que um relé
    # faz ao gravar a falta a 96 amostras/ciclo e o resto a 16.
    if taxas:
        linhas.append(f"{len(taxas)}")
        linhas.extend(f"{hz},{ate}" for hz, ate in taxas)
    else:
        linhas.append(f"{nrates}")
        # Mesmo com nrates = 0 existe uma linha de taxa — com samp = 0.
        linhas.append(f"{taxa if nrates else 0},{n}")
    linhas.append("01/02/2026,03:04:05.000000")
    linhas.append("01/02/2026,03:04:05.050000")
    linhas.append(tipo)
    if timemult:
        linhas.append("1.0")
    if revisao == "2013":
        linhas.append("0,-4")
        linhas.append("0,0")

    fim = "\r\n" if crlf else "\n"
    cfg_path.write_bytes(fim.join(linhas).encode(codec) + fim.encode(codec))

    carimbos = np.rint(instantes * 1e6).astype(np.int64)

    if tipo == "ASCII":
        partes = []
        for i in range(n):
            campos = [str(i + 1), str(int(carimbos[i]))]
            campos += [str(int(crus[k, i])) for k in range(na)]
            campos += [str(int(digital[k, i])) for k in range(nd)]
            partes.append(",".join(campos))
        dat_path.write_bytes(fim.join(partes).encode("ascii") + fim.encode("ascii"))
        return cfg_path

    formato = {"BINARY": "<h", "BINARY32": "<i", "FLOAT32": "<f"}[tipo]
    palavras = (nd + 15) // 16
    buf = bytearray()
    for i in range(n):
        buf += struct.pack("<II", i + 1, int(carimbos[i]))
        for k in range(na):
            valor = float(analog[k, i] / ESCALA) if tipo == "FLOAT32" else int(crus[k, i])
            buf += struct.pack(formato, valor)
        for w in range(palavras):
            palavra = 0
            for bit in range(16):
                canal = w * 16 + bit
                if canal < nd and digital[canal, i]:
                    palavra |= 1 << bit
            buf += struct.pack("<H", palavra)
    buf += b"\x1a" * lixo_no_fim
    dat_path.write_bytes(bytes(buf))
    return cfg_path


def esperado_analog(na: int, n: int, taxa: float, freq: float) -> np.ndarray:
    """O que o leitor tem que devolver, em unidade de engenharia."""
    return np.rint(_senoides(na, freq, _instantes(n, taxa, None)) / ESCALA) * ESCALA


def esperado_digital(nd: int, n: int) -> np.ndarray:
    return _digitais(nd, n)


# ---------------------------------------------------------------------------
# CEV — o relatório de evento comprimido da SEL
# ---------------------------------------------------------------------------
#
# Mesma razão dos sintéticos de COMTRADE: resposta conhecida e nenhum dado da
# distribuidora dentro de um repositório público.
#
# Duas coisas que só um sintético consegue afirmar, e que são exatamente onde o
# leitor de CEV pode errar em silêncio:
#
# * a amostra no arquivo é EFICAZ e o `Record` tem que sair em valor
#   instantâneo — aqui a senoide é escrita com `RMS_CEV` de amplitude e o
#   teste cobra `RMS_CEV * raiz(2)`;
# * o bit do digital é lido do mais significativo para o menos, na ordem dos
#   nomes — aqui o padrão é uma DIAGONAL, que um espelhamento de ordem não
#   consegue imitar.

RMS_CEV = 100.0       #: amplitude eficaz escrita no arquivo sintético
DC1_CEV = 125.0       #: valor da coluna `ANA03`, que não leva raiz de 2

#: As colunas de onda do CEV sintético, na ordem em que o arquivo as escreve.
COLUNAS_CEV = ("IA(A)", "IB(A)", "IC(A)", "VA(kV)", "VB(kV)", "VC(kV)",
               "FREQ(Hz)", "ANA01", "ANA02", "ANA03", "ANA04")

#: O que cada `ANAnn` se chama de verdade, nos campos `ERAQnn` do cabeçalho.
#: `ERAQ04` fica em branco DE PROPÓSITO: é a vaga não configurada, que o leitor
#: tem que jogar fora em vez de mostrar uma coluna vazia na tela.
ERAQ_CEV = ("V1M", "V1A", "DC1", "")


def _soma_cev(linha: str) -> str:
    """A soma de verificação de uma linha de CEV, em hexadecimal de 4 dígitos.

    Escrita aqui de novo, de propósito, em vez de importada do leitor: se as
    duas contas fossem a mesma função, um erro nela passaria despercebido nos
    dois lados ao mesmo tempo.
    """
    corte = linha.rfind(",")
    return f"{sum(linha[: corte + 1].encode('latin-1')) % 0x10000:04X}"


def _com_soma(campos: list[str]) -> str:
    """A linha pronta: os campos, a vírgula e a soma entre aspas."""
    corpo = ",".join(campos) + ","
    return corpo + f'"{_soma_cev(corpo)}"'


def esperado_digital_cev(nd: int, n: int) -> np.ndarray:
    """A diagonal: o digital `j` está em 1 só nas amostras `k` com `k % nd == j`."""
    k = np.arange(n)
    return np.array([(k % nd == j).astype(np.int8) for j in range(nd)])


def _tira_de_digitais(coluna: np.ndarray) -> str:
    """Os bits de uma amostra viram hexadecimal, do mais significativo ao menos."""
    bits = list(coluna)
    while len(bits) % 8:
        bits.append(0)
    octetos = [int("".join(str(b) for b in bits[i:i + 8]), 2)
               for i in range(0, len(bits), 8)]
    return "".join(f"{o:02X}" for o in octetos)


def escrever_cev(
    pasta: Path,
    *,
    nome: str = "evento",
    por_ciclo: int = 8,
    ciclos: int = 4,
    disparo: int | None = 8,
    freq: float = 60.0,
    nd: int = 8,
    soma_certa: bool = True,
    crlf: bool = True,
    com_ajustes: bool = True,
    sam_cyc: bool = True,
    extensao: str = ".CEV",
    dialeto: str = "rid_sid",
) -> Path:
    """Escreve um CEV sintético e devolve o caminho.

    `disparo` é o índice da amostra que leva o `>` na coluna `TRIG`; `None`
    escreve um arquivo sem marca de disparo nenhuma.

    `dialeto` escolhe o cabeçalho, e os dois existem no parque:

        "rid_sid"  SEL-451, sem versão:    "FID","RID","SID"
        "cev_ver"  SEL-787, CEV_VER 2.0.1: "FID","CEV_VER"

    Só as duas primeiras linhas e os três primeiros campos do cabeçalho mudam.
    As colunas e as amostras são as mesmas de propósito: assim o teste do
    dialeto testa o DIALETO, e não uma segunda oscilografia inteira.
    """
    n = por_ciclo * ciclos
    t = np.arange(n) / (por_ciclo * freq)
    onda = [RMS_CEV * np.cos(2 * np.pi * freq * t - k * 2 * np.pi / 3)
            for k in range(3)]

    colunas: list[np.ndarray] = [*onda, *onda]          # 3 correntes + 3 tensões
    colunas.append(np.full(n, freq))                    # FREQ(Hz)
    colunas.append(np.full(n, RMS_CEV))                 # ANA01 = V1M
    colunas.append(np.zeros(n))                         # ANA02 = V1A
    colunas.append(np.full(n, DC1_CEV))                 # ANA03 = DC1
    colunas.append(np.full(n, np.nan))                  # ANA04 = vaga vazia

    digitais = esperado_digital_cev(nd, n)

    if dialeto == "cev_ver":
        # O 787 conta os canais no cabeçalho e não traz LOCATION nem SER_NUM.
        comeco = [("REC_NUM", "4"), ("NUM_CH_A", str(len(colunas))),
                  ("NUM_CH_D", str(nd))]
    else:
        comeco = [("EVENT_NUM", "1"), ("EVENT", '"AB T"'),
                  ("LOCATION", "$$$$.$$")]
    cabecalho = [
        *comeco,
        ("FREQ", f"{freq:.2f}"), ("NFREQ", f"{int(freq)}"),
        ("SAM/CYC_D", str(por_ciclo)),
        ("NUM_OF_CYC", f"{ciclos:.3f}"),
        *([] if dialeto == "cev_ver" else [("SER_NUM", '"0000000001"')]),
        ("PRIM_VAL", '"YES"'),
        *([("EVENT", '"ER Trigger"')] if dialeto == "cev_ver" else []),
        ("CTRW", "120"), ("PTRY", "120.0"),
        *[(f"ERAQ{i + 1:02d}", f'"{e}"' if e else '" "')
          for i, e in enumerate(ERAQ_CEV)],
        ("GROUP", "1"), ("BREAKER1", '"OPEN"'),
    ]
    if sam_cyc:
        cabecalho.insert(5, ("SAM/CYC_A", str(por_ciclo)))

    if dialeto == "cev_ver":
        identificacao = [_com_soma(['"FID"', '"CEV_VER"']),
                         _com_soma(['"FID=SEL-787-TESTE"', '"2.0.1"'])]
    else:
        identificacao = [
            _com_soma(['"FID"', '"RID"', '"SID"']),
            _com_soma(['"FID=SEL-000-TESTE"', '"BAIA DE TESTE"', '"SE TESTE"'])]
    linhas = [
        *identificacao,
        _com_soma(['"MONTH"', '"DAY"', '"YEAR"', '"HOUR"', '"MIN"',
                   '"SEC"', '"MSEC"']),
        _com_soma(["3", "14", "2026", "10", "20", "30", "500"]),
        _com_soma([f'"{c}"' for c, _ in cabecalho]),
        _com_soma([v for _, v in cabecalho]),
        _com_soma([*[f'"{c}"' for c in COLUNAS_CEV], '"TRIG"',
                   '"' + " ".join(f"D{j + 1:02d}" for j in range(nd)) + '"']),
    ]
    for k in range(n):
        valores = ["" if np.isnan(c[k]) else f"{c[k]:.4f}" for c in colunas]
        marca = ">" if disparo is not None and k == disparo else " "
        linha = _com_soma([*valores, marca,
                           f'"{_tira_de_digitais(digitais[:, k])}"'])
        if not soma_certa and k == 0:
            linha = linha[: linha.rfind(",") + 1] + '"0000"'
        linhas.append(linha)

    if com_ajustes:
        # O bloco de ajustes: um campo só, com quebras de linha dentro. Existe
        # no arquivo real e o leitor tem que parar nele, não engasgar.
        linhas.append(_com_soma(['"SETTINGS"']))
        linhas.append('"\nGroup 1\n\nZ1MAG   := 2.14     Z1ANG   := 68.86\n",'
                      '"0000"')

    fim = "\r\n" if crlf else "\n"
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{nome}{extensao}"
    # Em bytes, e nao `write_text`: no Windows o modo texto trocaria o `\n` do
    # caso `crlf=False` por `\r\n`, e o teste do fim de linha do Unix passaria
    # a testar exatamente o contrario do que diz o nome dele.
    caminho.write_bytes((fim.join(linhas) + fim).encode("latin-1"))
    return caminho
