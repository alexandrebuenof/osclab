"""Os painéis: o que a tela mostra, na ordem em que mostra.

## O que mudou, e por quê

Até aqui um gráfico NASCIA de uma unidade do arquivo: os canais em ampères
viravam o gráfico de correntes, os em volts o de tensões, e os digitais um
bloco no fim. O arranjo era consequência do arquivo, e não escolha de quem
analisa.

Só que analisar um evento é, em boa parte, **montar a vista**: pôr `IA` e
`IA 60Hz` lado a lado para ver o atraso do filtro; separar as tensões de barra
das de linha; deixar quatro digitais perto das correntes e afastar os outros
trinta. Nada disso cabe num arranjo que o arquivo dita.

Então o gráfico virou **painel**: uma lista ordenada, cada item com um tipo,
um nome e os sinais dele. O arranjo do arquivo continua existindo — é o
`padrao()`, com que toda oscilografia abre —, mas agora ele é só o ponto de
partida.

## O nome e a ordem são da TELA; os sinais são do servidor

O servidor precisa saber que sinais cada painel tem, porque é ele que calcula
as séries e a escala vertical. **Não** precisa saber como o painel se chama nem
em que posição está: isso é rótulo e arrumação, e mandar essas coisas para o
servidor só criaria um segundo lugar onde elas podem divergir.

A exceção é o painel que o próprio servidor criou, no `padrao()`: ele nasce com
um nome (`Correntes (A)`), porque a tela não teria de onde tirar um melhor.
Depois disso o nome é do usuário, e o servidor devolve o que recebeu.

## Painel digital é painel

Poderia ser um bloco à parte, como era. Mas aí "mudar a ordem dos gráficos"
não poderia pôr digitais entre duas trincas de corrente — que é exatamente o
que se quer quando se está olhando um religamento: a corrente, o trip, a
corrente de novo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from osclab.formats.base import Record
from osclab.plot import digitais as digitais_mod
from osclab.plot import serie, unidades

ANALOGICO = "analogico"
DIGITAL = "digital"
TIPOS = (ANALOGICO, DIGITAL)


@dataclass(frozen=True)
class Painel:
    """Um gráfico da tela: o tipo, o nome e o que está dentro."""

    id: str
    tipo: str
    nome: str
    #: Analógico: ids do catálogo (`c0:instantaneo`, `v0:rms`, `q0:0:rms`).
    #: Digital: índices de canal digital, como texto.
    sinais: tuple[str, ...] = ()
    #: Só no analógico: `instantaneo` ou `rms`, e vale para os canais do IED
    #: que estão nele. Ver `plot/sinais.py`.
    medida: str = "instantaneo"
    #: Marca o painel cujo nome ainda é o que o servidor deu. Enquanto for
    #: verdade, o nome é recalculado a cada janela — é assim que ele acompanha
    #: a troca de primário para secundário. Renomear apaga a marca, e a partir
    #: daí o nome é do usuário e o servidor devolve o que recebeu.
    do_padrao: bool = False
    avisos: list[str] = field(default_factory=list)


def padrao(registro: Record, lado: str = "arquivo") -> list[Painel]:
    """O arranjo com que uma oscilografia abre.

    É o de sempre: um painel por unidade do arquivo, na ordem em que as
    unidades aparecem, e um painel com os digitais que mudaram. Quem abre um
    registro pela primeira vez não escolheu nada ainda, e a tela não pode
    esperar escolha para mostrar alguma coisa.
    """
    escalas = unidades.por_unidade(registro, lado)
    saida: list[Painel] = []
    por_unidade: dict[str, list[int]] = {}
    for canal in registro.analog_channels:
        por_unidade.setdefault(canal.unit.strip(), []).append(canal.index)

    for i, (unidade, indices) in enumerate(por_unidade.items(), start=1):
        _, mostrada = escalas.get(unidade, (1.0, unidade))
        saida.append(Painel(
            id=f"p{i}",
            tipo=ANALOGICO,
            nome=serie.titulo_do_grupo(mostrada),
            sinais=tuple(f"c{k}:instantaneo" for k in indices),
            do_padrao=True,
        ))

    escolhidos = digitais_mod.escolhidos_por_padrao(registro)
    if registro.status_channels:
        saida.append(Painel(
            id=f"p{len(saida) + 1}",
            tipo=DIGITAL,
            nome="Digitais",
            sinais=tuple(str(k) for k in escolhidos),
            do_padrao=True,
        ))
    return saida


def de_json(cru) -> list[Painel] | None:
    """Lê o arranjo que a tela mandou, ou `None` se ela não mandou nenhum.

    Tudo que não casar é ignorado em silêncio, como em todo dado que vem da
    tela: o servidor não confia nela. Um painel sem tipo conhecido some; um id
    repetido fica com o primeiro.
    """
    if not isinstance(cru, list):
        return None

    saida: list[Painel] = []
    vistos: set[str] = set()
    for i, item in enumerate(cru, start=1):
        if not isinstance(item, dict):
            continue
        tipo = str(item.get("tipo", "")).strip()
        if tipo not in TIPOS:
            continue
        identidade = str(item.get("id", "") or f"p{i}")
        if identidade in vistos:
            continue
        vistos.add(identidade)

        brutos = item.get("sinais")
        sinais = tuple(str(x) for x in brutos) if isinstance(brutos, list) else ()
        medida = str(item.get("medida", "instantaneo"))
        saida.append(Painel(
            id=identidade,
            tipo=tipo,
            nome=str(item.get("nome", "") or ""),
            sinais=sinais,
            medida=medida if medida in ("instantaneo", "rms") else "instantaneo",
            # A tela devolve esta marca para os painéis que nunca foram
            # renomeados, e o servidor então reescreve o nome deles. É o que
            # faz `Correntes (A)` virar `Correntes (kA)` quando se troca para
            # primário: o nome vem da unidade, e a unidade acabou de mudar.
            do_padrao=bool(item.get("do_padrao")),
        ))
    return saida


def indices_digitais(painel: Painel) -> list[int]:
    """Os índices de canal digital de um painel, ignorando o que não for."""
    saida = []
    for texto in painel.sinais:
        try:
            saida.append(int(texto))
        except (TypeError, ValueError):
            continue
    return saida
