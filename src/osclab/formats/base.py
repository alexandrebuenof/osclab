"""O contrato entre os leitores de formato e o resto do programa.

**Este é o arquivo mais importante do projeto.** Tudo o que vem depois — gráfico,
fasores, componentes simétricas, localização de falta, relatório — conversa com
um `Record`, nunca com um arquivo. Se o `Record` estiver certo, acrescentar um
formato novo é escrever um arquivo que cumpre este contrato. Se estiver errado,
cada formato novo empurra uma gambiarra para dentro do resto.

Por isso ele está aqui antes de existir um único leitor: é a decisão a ser
revisada com calma, não a ser descoberta no meio do primeiro COMTRADE.

Duas escolhas que valem explicação:

* **Metadados e amostras vivem separados.** Os canais são uma tupla de
  dataclasses; as amostras são UM array numpy de forma `(n_canais, n_amostras)`.
  Guardar as amostras dentro de cada canal pareceria mais organizado e seria um
  erro: todo cálculo desta ferramenta opera sobre as três fases ao mesmo tempo,
  e um array único é o que permite fazer isso vetorizado, em C, sem laço
  Python.
* **Os dados chegam em unidade de engenharia.** O leitor já aplicou os fatores
  de conversão do formato. Quem lê um `Record` recebe ampère e volt, nunca o
  inteiro cru do conversor A/D. Errar isso silenciosamente dá um gráfico bonito
  e completamente errado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


class FormatError(Exception):
    """Arquivo que nenhum leitor abre, ou que está corrompido.

    A mensagem é escrita para o engenheiro de proteção que abriu o arquivo, não
    para quem escreveu o leitor.
    """


class Filtering(StrEnum):
    """O registro traz o sinal cru ou o que o relé já filtrou?

    Nenhum formato declara isso num campo — é deduzido. Ver
    `osclab.analysis` (marco 0.5) para os indícios usados.
    """

    BRUTO = "bruto"
    FILTRADO = "filtrado"
    DESCONHECIDO = "desconhecido"


class FilteringSource(StrEnum):
    """De onde veio o veredito sobre `Filtering`.

    Existe para a tela poder dizer "deduzi isto" em vez de afirmar. Um palpite
    apresentado como certeza corromperia a localização de falta em silêncio.
    """

    DECLARADO = "declarado"   # o arquivo dizia
    DEDUZIDO = "deduzido"     # o programa concluiu
    USUARIO = "usuario"       # alguém corrigiu na tela


@dataclass(frozen=True)
class AnalogChannel:
    """Um canal analógico, já convertido para unidade de engenharia."""

    index: int
    name: str
    unit: str                      # "A", "kV", "V", ...
    phase: str = ""                # "A", "B", "C", "N" — vazio quando não se sabe
    component: str = ""            # equipamento monitorado, como o arquivo nomeia
    primary: float = 1.0           # relação do primário (TC/TP), quando declarada
    secondary: float = 1.0         # relação do secundário
    scaling: str = "S"             # "P" ou "S": em que lado os dados estão
    skew: float = 0.0              # atraso de amostragem deste canal, em segundos

    @property
    def is_primary(self) -> bool:
        return self.scaling.upper() == "P"


@dataclass(frozen=True)
class StatusChannel:
    """Um canal digital (estado de disjuntor, trip, recepção de teleproteção)."""

    index: int
    name: str
    phase: str = ""
    component: str = ""
    normal_state: int = 0


@dataclass(frozen=True)
class SampleRate:
    """Um trecho do registro com taxa constante.

    São vários porque a norma permite: é comum o registro ter uma taxa alta
    durante a falta e uma baixa no pré e no pós-falta.
    """

    rate_hz: float
    last_sample: int               # índice da última amostra nesta taxa


@dataclass
class Record:
    """Uma oscilografia, no formato interno único do OscLab."""

    # --- procedência ------------------------------------------------------
    source: Path
    format_name: str                                    # "comtrade", "cev", ...

    # --- identificação ----------------------------------------------------
    station: str = ""
    device_id: str = ""
    line_frequency: float = 60.0                        # Hz nominais

    # --- tempo ------------------------------------------------------------
    start_time: datetime | None = None
    trigger_time: datetime | None = None
    time_quality: str = ""                              # o que o arquivo diz do relógio

    # --- canais -----------------------------------------------------------
    analog_channels: tuple[AnalogChannel, ...] = ()
    status_channels: tuple[StatusChannel, ...] = ()
    sample_rates: tuple[SampleRate, ...] = ()

    # --- dados ------------------------------------------------------------
    #: (n_analogicos, n_amostras) em float64, JÁ em unidade de engenharia.
    analog: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))
    #: (n_digitais, n_amostras) em int8, valores 0 ou 1.
    status: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=np.int8))
    #: (n_amostras,) em segundos, relativo a `start_time`.
    time: np.ndarray = field(default_factory=lambda: np.empty(0))

    # --- diagnóstico ------------------------------------------------------
    filtering: Filtering = Filtering.DESCONHECIDO
    filtering_source: FilteringSource = FilteringSource.DEDUZIDO
    #: Avisos do leitor, para mostrar na tela. Nunca interrompem a leitura.
    notes: tuple[str, ...] = ()

    # --- derivados --------------------------------------------------------

    @property
    def n_samples(self) -> int:
        return int(self.time.size)

    @property
    def duration(self) -> float:
        """Duração do registro em segundos."""
        return float(self.time[-1] - self.time[0]) if self.n_samples > 1 else 0.0

    @property
    def base_rate_hz(self) -> float:
        """Taxa de amostragem do primeiro trecho, em Hz.

        A taxa declarada no arquivo tem prioridade, mas ela pode ser ZERO: é
        assim que o COMTRADE diz "a taxa varia, use o carimbo de cada amostra"
        (`nrates = 0`), e é o que um GE 850 gera. Nesse caso a taxa sai do
        próprio vetor de tempo — senão `samples_per_cycle` responderia 0 e todo
        o diagnóstico de bruto × filtrado iria por água abaixo.
        """
        if self.sample_rates and self.sample_rates[0].rate_hz > 0:
            return self.sample_rates[0].rate_hz
        if self.n_samples > 1:
            dt = float(self.time[1] - self.time[0])
            return 1.0 / dt if dt > 0 else 0.0
        return 0.0

    @property
    def samples_per_cycle(self) -> float:
        """Amostras por ciclo da frequência nominal.

        É o número que mais diz sobre o registro: 4 só serve para dado já
        filtrado, 16 ou mais aponta para sinal bruto.
        """
        if self.line_frequency <= 0:
            return 0.0
        return self.base_rate_hz / self.line_frequency

    @property
    def trigger_index(self) -> int | None:
        """Índice da amostra mais próxima do instante de disparo."""
        if self.trigger_time is None or self.start_time is None or self.n_samples == 0:
            return None
        offset = (self.trigger_time - self.start_time).total_seconds()
        return int(np.argmin(np.abs(self.time - offset)))

    def analog_by_name(self, name: str) -> np.ndarray:
        """As amostras do canal analógico com este nome. Sem distinguir maiúsculas."""
        alvo = name.strip().lower()
        for canal in self.analog_channels:
            if canal.name.strip().lower() == alvo:
                return self.analog[canal.index]
        raise KeyError(f"canal analogico '{name}' nao existe neste registro")


@runtime_checkable
class Reader(Protocol):
    """O que um módulo de formato precisa oferecer para entrar no registry.

    `sniff` olha o arquivo e responde se sabe abri-lo — pela assinatura do
    conteúdo, não só pela extensão, porque extensão é palpite e conteúdo é fato.
    """

    #: Nome curto, usado em `Record.format_name` e na tela.
    name: str
    #: Extensões típicas, em minúsculas e com ponto. Só ajuda a ordenar as tentativas.
    extensions: tuple[str, ...]

    def sniff(self, path: Path) -> bool: ...

    def read(self, path: Path) -> Record: ...
