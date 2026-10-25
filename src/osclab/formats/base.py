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
    #: A fase que o USUÁRIO escolheu para este canal, quando corrigiu o que o
    #: programa deduziu. Vence `phase` e a dedução pelo nome: o engenheiro que
    #: olhou o arquivo sabe mais que a nossa expressão regular. `"-"` é a
    #: escolha explícita de "nenhuma" — diferente de `""`, que é "não mexeram".
    phase_escolhida: str = ""
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


@dataclass(frozen=True)
class Trecho:
    """Um pedaço do registro com taxa de amostragem constante, já resolvido.

    `SampleRate` é o que o arquivo declara — e declara em índice de 1, contando
    a ÚLTIMA amostra de cada trecho. Isto aqui é o que o resto do programa usa:
    início e fim em índice de 0, com o fim exclusivo, como toda fatia de Python.

    A tradução mora num lugar só de propósito. Errar o `+1` de um índice de 1
    para um de 0 desloca a janela do fasor em uma amostra — 18° a 20 amostras
    por ciclo — e nada na tela denuncia.
    """

    inicio: int
    fim: int                       # exclusivo
    taxa_hz: float

    @property
    def n_amostras(self) -> int:
        return max(self.fim - self.inicio, 0)


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
    #: O fuso em que os CARIMBOS estão, em horas a partir do UTC (`-4` em
    #: Cuiabá), como o `time_code` do COMTRADE 2013 declara. `None` quando o
    #: arquivo não declara. A tela MOSTRA a hora como o arquivo escreveu;
    #: este campo serve só para ALINHAR dois registros pela hora.
    fuso_horas: float | None = None

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

    # --- correções do usuário --------------------------------------------
    #: Trincas que o USUÁRIO corrigiu: `{"I*W": {"A": 0, "B": 1, "C": 2}}`.
    #:
    #: Quais três canais formam um conjunto trifásico é deduzido do nome deles,
    #: e nome de canal cada fabricante escreve como quer. Quando a dedução erra,
    #: 3I0, I1, I2 e a localização de falta erram junto — e saem na unidade
    #: certa, na ordem de grandeza certa, sem nada na tela denunciando.
    #:
    #: A chave é o NOME do conjunto (`formats/conjuntos.py`), não a posição
    #: dele: a posição é o que o `q{i}` dos arranjos salvos usa, e amarrar a
    #: correção a ela faria uma correção mudar o alvo de outra. Vem do acervo,
    #: gravado ao lado do registro: quem corrigiu uma trinca corrigiu para
    #: sempre.
    trincas_escolhidas: dict = field(default_factory=dict)

    #: Os VÍNCULOS de potência que o usuário fez: que trinca de corrente
    #: pertence ao mesmo vão de que trinca de tensão.
    #:
    #: `{"I*W": {"com": "V*Y", "base": "fase"}, "V*Y": {"com": "I*W", ...}}`,
    #: gravado nos dois sentidos — vincular G1 a G3 vincula G3 a G1.
    #:
    #: **O programa não deduz isto.** Dois vãos de uma subestação podem ter
    #: correntes e tensões com nomes parecidos, e casar o par errado produz
    #: uma potência na unidade certa, na ordem de grandeza certa, e errada —
    #: o tipo de erro que não se vê no gráfico. Quem sabe qual TC pertence a
    #: qual TP é quem leu o unifilar.
    #:
    #: `base` diz se as tensões daquele vínculo são de FASE (fase-neutro) ou
    #: de LINHA, porque a conta muda: em fase sai potência por fase e total;
    #: em linha só sai o total, pelo método dos dois wattímetros, já que não
    #: há referência de neutro para repartir.
    #:
    #: A chave é o NOME do conjunto, não a posição — mesma razão de
    #: `trincas_escolhidas`.
    vinculos_de_potencia: dict = field(default_factory=dict)

    #: Os NOMES dos digitais que o relé grava e a placa dele não tem (ver
    #: `formats/ajustes.digitais_sem_placa`). Ficam fora da tela padrão e
    #: marcados na busca: o que está nesses bits não é entrada nenhuma.
    digitais_sem_placa: frozenset = field(default_factory=frozenset)

    # --- diagnóstico ------------------------------------------------------
    filtering: Filtering = Filtering.DESCONHECIDO
    filtering_source: FilteringSource = FilteringSource.DEDUZIDO
    #: Avisos do LEITOR: o que o programa fez, deixou de fora ou não conseguiu
    #: confirmar. Nunca interrompem a leitura, e é só isto que a tela marca com
    #: triângulo — ver `relatos`.
    notes: tuple[str, ...] = ()
    #: O que o RELÉ concluiu sozinho e gravou no arquivo: a classificação do
    #: evento, a distância que ele calculou para a falta.
    #:
    #: Ficavam junto dos avisos, e carimbar `⚠` numa frase como "o relé
    #: classificou o evento como AB T" ensina o usuário a ignorar o triângulo —
    #: o aviso que aparece no caso normal deixa de ser lido. São informação do
    #: arquivo, não coisa que deu errado.
    relatos: tuple[str, ...] = ()
    #: A classificação do evento que o RELÉ gravou, só a sigla — `AG T`,
    #: `AB`, `3PH`. O «T» solto da SEL é TRIP, não terra. Vem do campo `EVENT` do `.CEV`; nos formatos que não a
    #: trazem fica vazia, que é o estado normal de um COMTRADE.
    #:
    #: Separada de `relatos` porque ali ela é uma FRASE, boa de ler e ruim de
    #: comparar. A tela põe esta sigla ao lado da que o OscLab concluiu, e
    #: comparar duas frases para saber se conflitam seria análise de texto
    #: onde cabe um campo.
    classificacao_do_rele: str = ""

    # --- derivados --------------------------------------------------------

    @property
    def n_samples(self) -> int:
        return int(self.time.size)

    @property
    def duration(self) -> float:
        """Duração do registro em segundos."""
        return float(self.time[-1] - self.time[0]) if self.n_samples > 1 else 0.0

    @property
    def trechos(self) -> tuple[Trecho, ...]:
        """Os pedaços de taxa constante, em índices de 0 e fim exclusivo.

        **A norma permite mais de um, e isso não é exótico**: é comum o relé
        gravar a 96 amostras por ciclo durante a falta e a 16 no pré e no
        pós-falta, para o arquivo não ficar gigante.

        Quem calcula fasor, envoltória ou componente simétrica precisa desta
        lista, e não de um número só. Uma janela de "um ciclo" tem um tamanho
        em cada trecho, e uma janela que atravessa a fronteira não é um ciclo
        de coisa nenhuma — o resultado sairia confiante e errado.

        Quando o arquivo não declara taxa (`nrates = 0`, que é o que um GE 850
        gera), ela sai do próprio vetor de tempo e vale para o registro inteiro.
        """
        n = self.n_samples
        if n == 0:
            return ()

        declarados = [r for r in self.sample_rates if r.rate_hz > 0]
        if not declarados:
            dt = float(self.time[1] - self.time[0]) if n > 1 else 0.0
            return (Trecho(0, n, 1.0 / dt if dt > 0 else 0.0),)

        saida: list[Trecho] = []
        inicio = 0
        for taxa in declarados:
            # `last_sample` conta em base 1 e é inclusivo; aqui o fim é
            # exclusivo em base 0 — os dois acabam com o mesmo número.
            fim = min(max(int(taxa.last_sample), inicio), n)
            if fim > inicio:
                saida.append(Trecho(inicio, fim, float(taxa.rate_hz)))
            inicio = fim

        if not saida:
            return (Trecho(0, n, float(declarados[0].rate_hz)),)
        if saida[-1].fim < n:
            # Arquivo que declara menos amostras do que gravou: o último trecho
            # cobre o resto, em vez de deixar um pedaço sem taxa nenhuma.
            ultimo = saida[-1]
            saida[-1] = Trecho(ultimo.inicio, n, ultimo.taxa_hz)
        return tuple(saida)

    @property
    def taxa_variavel(self) -> bool:
        """Há mais de uma taxa neste registro? A tela precisa avisar."""
        return len({t.taxa_hz for t in self.trechos}) > 1

    @property
    def base_rate_hz(self) -> float:
        """Taxa do PRIMEIRO trecho, em Hz.

        Serve para identificar o registro (a tira, o acervo, o diagnóstico de
        bruto × filtrado). **Não serve para calcular fasor** num registro de
        taxa variável — para isso existe `trechos`.
        """
        return self.trechos[0].taxa_hz if self.trechos else 0.0

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
