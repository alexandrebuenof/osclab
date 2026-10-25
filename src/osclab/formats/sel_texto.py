"""Leitor do relatório de evento da SEL em TEXTO (o «EVE» do SEL-321).

## Por que este leitor existe

Os SEL-321 do parque salvam o relatório de evento com extensão `.CEV`, mas não
é o CEV comprimido (CSV com soma de verificação): é o relatório como ele sai
no terminal, em colunas de texto. Apareceu no banco de oscilografias do parque
em 24/10/2026 — seis arquivos que nenhum leitor aceitava.

## A forma do arquivo

```
LT EXEMPLO                              Date: 04/15/24    Time: 18:18:08.455
FID=SEL-321-1-R422-...
    CURRENTS (pri)             VOLTAGES (kV pri)     RELAY ELEMENTS  OUT   IN
                                                    ZZZZZZO  555566L 1357 1357
                                                    ABCABCO 3111077O &&&& &&&&
   IR     IA     IB     IC     VA      VB      VC   BCAGGGS 2NQPPNQP 2468 2468
     0   -241    410   -169    71.9   -68.4    -3.3 ....... ....L... .... 1...
   ... (quatro linhas por ciclo, um bloco por ciclo)
Event:  AG    Location:   +6.05    Frequency:    60.1
Targets: INST EN G
GROUP 1
RELID =SEL-321   Z1MAG = 0.67   Z1ANG = 76.10 ...      <- os ajustes
```

**O nome de cada elemento está escrito na VERTICAL**, nas três linhas acima
dos nomes analógicos: a coluna `Z`/`A`/`B` é `ZAB`, a ` `/`3`/`2` é `32`, a
`1`/`&`/`2` do grupo OUT é `OUT1&2`. Cada coluna vira um digital: ponto é
desligado, qualquer outro caractere é ligado. O relé usa letras e números
para dizer QUAL zona ou estágio (`2`, `L`, `H`) — isso se perde aqui, e o
nome do digital continua dizendo o elemento.

**As amostras seguem a convenção do CEV**, que é o mesmo relatório escrito de
outro jeito: o par de amostras a um quarto de ciclo dá o valor EFICAZ, e por
isso corrente e tensão são multiplicadas por raiz de 2 (ver `cev.py`, item 1).

**O relatório não marca a amostra do disparo.** A hora do cabeçalho vira a da
primeira amostra, e a tela diz isso num aviso.
"""

from __future__ import annotations

import contextlib
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
from osclab.formats.cev import RMS_PARA_INSTANTANEO, _decodificar

#: A linha do cabeçalho: o nome do terminal, a data e a hora.
_CABECALHO = re.compile(
    r"^(?P<nome>.*?)\s+Date:\s*(?P<data>\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"Time:\s*(?P<hora>\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)", re.IGNORECASE)
_FID = re.compile(r"^\s*FID\s*=\s*(?P<fid>SEL-\S+)", re.IGNORECASE)
_EVENTO = re.compile(r"Event:\s*(?P<evento>[A-Z0-9 ]+?)\s{2,}Location:\s*(?P<local>\S+)"
                     r"(?:\s+Frequency:\s*(?P<freq>[\d.]+))?", re.IGNORECASE)
_ALVOS = re.compile(r"Targets:\s*(?P<alvos>.*?)(?:\s{2,}|$)", re.IGNORECASE)
_NUMERO = re.compile(r"^-?\d+(?:\.\d+)?$")

#: Quantas linhas do começo bastam para reconhecer o formato.
_OLHAR = 4096


def _assinatura(texto: str) -> bool:
    linhas = [x for x in texto.splitlines() if x.strip()][:6]
    return (any(_CABECALHO.match(x) for x in linhas)
            and any(_FID.match(x) for x in linhas))


class SelTextoReader:
    """O relatório de evento da SEL em texto. Registrado em `formats/__init__.py`."""

    name = "sel-texto"
    extensions = (".cev", ".eve", ".txt")

    def sniff(self, path: Path) -> bool:
        try:
            with open(path, "rb") as f:
                comeco = f.read(_OLHAR)
        except OSError:
            return False
        return _assinatura(_decodificar(comeco))

    def read(self, path: Path) -> Record:
        caminho = Path(path)
        texto = _decodificar(caminho.read_bytes())
        linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        nome = ""
        inicio = None
        fid = ""
        for linha in linhas[:12]:
            c = _CABECALHO.match(linha)
            if c and inicio is None:
                nome = c.group("nome").strip()
                inicio = _data_hora(c.group("data"), c.group("hora"))
            f = _FID.match(linha)
            if f and not fid:
                fid = f"FID={f.group('fid')}"

        # A linha dos nomes analógicos: a primeira com IA e VA.
        k = next((i for i, x in enumerate(linhas)
                  if re.search(r"\bIA\b", x) and re.search(r"\bVA\b", x)), None)
        if k is None or k < 3:
            raise FormatError(f"{caminho.name}: não achei a linha de títulos IA … VA.")
        titulos = linhas[k]
        # A linha dos grupos (`OUT`, `IN`) fica acima dos dois rótulos
        # verticais, com ou sem linha em branco no meio: procura-se a primeira
        # que os nomeie, em vez de confiar numa posição fixa — sem o prefixo,
        # `OUT1&2` e `IN1&2` saíam com o mesmo nome.
        grupo = next((linhas[i] for i in range(k - 3, max(k - 7, -1), -1)
                      if re.search(r"\b(OUT|IN)\b", linhas[i])), "")
        rotulos = [linhas[k - 2], linhas[k - 1], titulos]

        # Onde começam os elementos: na primeira coluna escrita das linhas de
        # rótulo vertical (as duas acima dos títulos).
        comeco_elem = min((len(x) - len(x.lstrip()) for x in (linhas[k - 2], linhas[k - 1])
                           if x.strip()), default=len(titulos))
        nomes_ana = titulos[:comeco_elem].split()

        # Os elementos: uma coluna por posição com algo escrito nos rótulos.
        largura = max(len(x) for x in rotulos)
        partes_grupo = [(m.start(), m.group()) for m in re.finditer(r"\S+", grupo)]
        colunas: list[tuple[int, str]] = []
        for p in range(comeco_elem, largura):
            pedacos = [x[p] if p < len(x) else " " for x in rotulos]
            if all(ch == " " for ch in pedacos):
                continue
            rotulo = "".join(ch for ch in pedacos if ch != " ")
            prefixo = _prefixo_do_grupo(partes_grupo, p)
            colunas.append((p, prefixo + rotulo))

        # As amostras: linha que começa com tantos números quantos são os
        # canais analógicos. Os blocos (separados por linha vazia) são ciclos.
        valores: list[list[float]] = []
        estados: list[list[int]] = []
        blocos: list[int] = []
        no_bloco = 0
        for linha in linhas[k + 1:]:
            if linha.strip().startswith("Event:"):
                break
            if not linha.strip():
                if no_bloco:
                    blocos.append(no_bloco)
                no_bloco = 0
                continue
            campos = linha[:comeco_elem].split()
            if len(campos) != len(nomes_ana) or not all(_NUMERO.match(c) for c in campos):
                continue
            valores.append([float(c) for c in campos])
            estados.append([0 if (p >= len(linha) or linha[p] in ". ") else 1
                            for p, _ in colunas])
            no_bloco += 1
        if no_bloco:
            blocos.append(no_bloco)
        if not valores:
            raise FormatError(f"{caminho.name}: nenhuma amostra no relatório.")

        por_ciclo = max(set(blocos), key=blocos.count) if blocos else 4
        evento = _EVENTO.search(texto)
        nominal = 60.0
        if evento and evento.group("freq"):
            nominal = 50.0 if abs(float(evento.group("freq")) - 50.0) < 3 else 60.0
        taxa = por_ciclo * nominal
        n = len(valores)
        bruto = np.asarray(valores, dtype=np.float64).T

        avisos = ["O relatório de texto não marca a amostra do disparo: o tempo conta "
                  "da primeira amostra, que leva a hora do cabeçalho.",
                  "Amostras vêm em eficaz; converti corrente e tensão para instantâneo (×√2)."]
        canais = []
        for i, nome_canal in enumerate(nomes_ana):
            unidade = "A" if nome_canal.upper().startswith("I") else "kV"
            bruto[i] *= RMS_PARA_INSTANTANEO
            canais.append(AnalogChannel(index=i, name=nome_canal, unit=unidade,
                                        component=nome, scaling="P"))

        relatos = []
        classificacao = ""
        if evento:
            classificacao = evento.group("evento").strip()
            relatos.append(f'Relé classificou o evento como "{classificacao}"')
            # `$$$$$$` quando o relé não calculou a distância: aí não se diz nada.
            with contextlib.suppress(ValueError):
                relatos.append(f"Relé calculou a falta a {float(evento.group('local')):g} "
                               f"unidade(s) (campo Location)")
        alvos = _ALVOS.search(texto)
        if alvos and alvos.group("alvos").strip():
            relatos.append(f"Alvos do relé: {alvos.group('alvos').strip()}")

        return Record(
            source=caminho,
            format_name="sel-texto",
            station=nome,
            device_id=fid,
            line_frequency=nominal,
            start_time=inicio,
            trigger_time=inicio,
            analog_channels=tuple(canais),
            status_channels=tuple(StatusChannel(index=j, name=rot, component=nome)
                                  for j, (_, rot) in enumerate(colunas)),
            sample_rates=(SampleRate(rate_hz=taxa, last_sample=n),),
            analog=bruto,
            status=np.asarray(estados, dtype=np.int8).T.reshape(len(colunas), n),
            time=np.arange(n, dtype=np.float64) / taxa,
            filtering=Filtering.FILTRADO if por_ciclo <= 8 else Filtering.DESCONHECIDO,
            filtering_source=(FilteringSource.DECLARADO if por_ciclo <= 8
                              else FilteringSource.DEDUZIDO),
            notes=tuple(avisos),
            relatos=tuple(relatos),
            classificacao_do_rele=classificacao,
        )


def _prefixo_do_grupo(partes: list[tuple[int, str]], posicao: int) -> str:
    """`OUT` ou `IN` quando a coluna está sob esse título; vazio nos elementos."""
    dono = ""
    for inicio, palavra in partes:
        if inicio <= posicao + 1:
            dono = palavra.upper()
    return dono if dono in ("OUT", "IN") else ""


def _data_hora(data: str, hora: str) -> datetime | None:
    """`04/15/24` e `18:18:08.455` (mês/dia/ano, como a SEL escreve)."""
    try:
        mes, dia, ano = (int(x) for x in data.split("/"))
        if ano < 100:
            ano += 2000
        h, m, s = hora.split(":")
        segundos = float(s)
        inteiro = int(segundos)
        return datetime(ano, mes, dia, int(h), int(m), inteiro,
                        int(round((segundos - inteiro) * 1e6)) % 1_000_000)
    except (ValueError, TypeError):
        return None


__all__ = ["SelTextoReader"]
