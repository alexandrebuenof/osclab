"""O plano de impedância: a trajetória do laço e as zonas do relé.

## O que ele mostra

Um ponto por instante, no plano R × X, com a impedância que o relé mediu
naquele laço. A trajetória sai da carga — longe, no primeiro quadrante —,
mergulha para dentro das zonas quando a falta começa e foge para o infinito
quando o disjuntor abre. É de um olhar que se lê **a que distância ficou a
falta** e **em que zona ela caiu**.

## Os seis laços, e por que a conta é diferente em dois deles

Um relé de distância não mede "a impedância": mede a de um LAÇO, e são seis.

    laço de FASE   (AB, BC, CA)    Z = (Vx − Vy) / (Ix − Iy)
    laço de TERRA  (AN, BN, CN)    Z = Vx / (Ix + k0 · 3I0)

O `k0` da conta de terra é o fator de compensação de sequência zero:

    k0 = (Z0 − Z1) / (3 · Z1)

Sem ele a impedância de uma falta à terra sai **maior** do que é, e a falta
parece mais longe do que está — num sistema com Z0/Z1 ≈ 3 o erro passa de
60 %. Por isso, quando os ajustes não trazem `Z0MAG`/`Z0ANG`, este módulo
**não inventa um k0**: ele diz que não tem, e a tela avisa que a leitura do
laço de terra está sem compensação.

## De onde vem cada número, e por que isso vai escrito

Três origens, e a tela desenha cada uma de um jeito:

| origem | de onde veio |
|---|---|
| `lido` | do bloco `SETTINGS` do `.CEV`, ou do `.HDR` |
| `sugerido` | padrão nosso sobre os parâmetros da linha — 80 %, 120 %, 200 % |
| `digitado` | o usuário escreveu |

O caso perigoso não é ficar sem zona: é uma zona **inventada parecer uma zona
lida do relé**. Um gráfico com a Z1 em 80 % desenhada igual a uma Z1 lida leva
a concluir que o relé atuou certo quando ninguém leu ajuste nenhum. Por isso a
origem viaja com o número até a tela, campo por campo.

## A unidade é a dos canais

`Z = V / I`, então o plano sai na mesma base em que os canais estão: com o
cabeçalho em secundário, ohms secundários — que é como o relé enxerga e como
os ajustes dele estão escritos. Em primário, ohms primários. Quem troca é o
botão `lado` da tela, e o painel repete o que recebeu em vez de converter de
novo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from osclab.dsp import fasor as fasor_mod
from osclab.formats import conjuntos
from osclab.formats.base import Record

#: Os seis laços. `fases` são as letras envolvidas; `terra` diz qual conta.
LACOS: dict[str, tuple[str, ...]] = {
    "AN": ("A",), "BN": ("B",), "CN": ("C",),
    "AB": ("A", "B"), "BC": ("B", "C"), "CA": ("C", "A"),
}

#: A sugestão padrão de alcance, em % dos parâmetros da linha, quando o arquivo
#: não traz ajuste. **A confirmar com a proteção** — está aqui para a tela ter
#: o que desenhar, não para valer como ajuste.
SUGESTAO = {"Z1": 80.0, "Z2": 120.0, "Z3": 200.0}
SUGESTAO_TEMPO = {"Z1": "inst.", "Z2": "0,30 s", "Z3": "1,00 s"}

#: Quantos pontos a trajetória tem, no máximo. Mais que isso não cabe em
#: pixel nenhum e só faz o navegador desenhar por cima de si mesmo.
MAXIMO_DE_PONTOS = 600

#: Abaixo desta corrente a divisão V/I é ruído dividido por ruído: depois que
#: o disjuntor abre sobram miliampères de fuga, e a impedância deles dispara
#: para milhões de ohms. Fração da maior corrente do laço no registro.
PISO_DA_CORRENTE = 0.02


@dataclass(frozen=True)
class Numero:
    """Um valor com a origem dele. A origem vai para a tela junto do número."""

    valor: float
    origem: str                 # "lido" | "sugerido" | "digitado"
    #: A variável do relé de onde saiu (`Z1MG`), quando foi lida. É isso que
    #: quem for conferir no QuickSet procura — «lido» não ajuda ninguém.
    variavel: str = ""


@dataclass(frozen=True)
class Zona:
    """Uma zona de distância, pronta para desenhar."""

    nome: str
    alcance: Numero             # em ohms, na base dos canais
    tempo: str                  # como o relé escreve: "inst.", "0,30 s"
    tempo_origem: str = "lido"
    tempo_variavel: str = ""
    #: `F` olha para a frente, `R` para trás (`DIR3 := R` na SEL). A zona
    #: reversa é a mesma figura espelhada na origem — no 3º quadrante.
    direcao: str = "F"
    direcao_origem: str = "padrão"
    direcao_variavel: str = ""
    #: A QUADRILATERAL: alcance reativo e resistivo (`XG1`/`RG1` na terra da
    #: SEL, `XP1`/`RP1` na fase). `None` quando o relé não tem e ninguém
    #: digitou.
    x: Numero | None = None
    r: Numero | None = None
    #: O relé usa a forma nesta zona? Sai de `E21MP`/`E21XP` (fase) ou
    #: `E21MG`/`E21XG` (terra): três zonas mho e nenhuma quadrilateral de fase,
    #: por exemplo. `None` quando o arquivo não diz.
    usa_mho: bool | None = None
    usa_quad: bool | None = None

    def para_json(self, zl_modulo: float, angulo: float = 80.0) -> dict:
        pct = (self.alcance.valor / zl_modulo * 100.0) if zl_modulo > 0 else None
        mho = geometria_mho(self.alcance.valor, angulo, self.direcao)
        quad = (geometria_quad(self.x.valor, self.r.valor, angulo, self.direcao)
                if self.x is not None and self.r is not None else None)
        return {
            "nome": self.nome,
            "alcance": self.alcance.valor,
            "pct": pct,
            "origem": self.alcance.origem,
            "variavel": self.alcance.variavel,
            "tempo": self.tempo,
            "tempo_origem": self.tempo_origem,
            "tempo_variavel": self.tempo_variavel,
            "direcao": self.direcao,
            "direcao_origem": self.direcao_origem,
            "direcao_variavel": self.direcao_variavel,
            "x": None if self.x is None else self.x.valor,
            "x_origem": None if self.x is None else self.x.origem,
            "x_variavel": "" if self.x is None else self.x.variavel,
            "r": None if self.r is None else self.r.valor,
            "r_origem": None if self.r is None else self.r.origem,
            "r_variavel": "" if self.r is None else self.r.variavel,
            "usa_mho": self.usa_mho,
            "usa_quad": self.usa_quad,
            # A GEOMETRIA vai pronta: a tela converte ohm em pixel e pinta.
            "mho": mho,
            "quad": quad,
        }


# ---------------------------------------------------------------------------
# A geometria das duas características
# ---------------------------------------------------------------------------

def geometria_mho(alcance: float, angulo: float, direcao: str = "F") -> dict:
    """A mho auto-polarizada: o círculo que passa pela origem e tem o vetor de
    alcance como DIÂMETRO. Reversa, o mesmo círculo espelhado na origem."""
    sinal = -1.0 if direcao == "R" else 1.0
    a = math.radians(angulo)
    return {"centro": [sinal * alcance / 2.0 * math.cos(a),
                       sinal * alcance / 2.0 * math.sin(a)],
            "raio": alcance / 2.0}


def geometria_quad(x_alcance: float, r_alcance: float, angulo: float,
                   direcao: str = "F") -> list[list[float]]:
    """A quadrilateral, SIMPLIFICADA: reta de reatância em `X`, os dois
    limites resistivos em `±R` inclinados no ângulo da linha, e o eixo R como
    fundo. O relé de verdade inclina a reta de cima (correção de carga, `TANG`)
    e põe o fundo no elemento direcional — aqui não, e a tela diz isso.
    Reversa, a mesma figura espelhada na origem."""
    passo = x_alcance / math.tan(math.radians(angulo)) if angulo else 0.0
    pontos = [[-r_alcance, 0.0], [r_alcance, 0.0],
              [r_alcance + passo, x_alcance], [-r_alcance + passo, x_alcance]]
    if direcao == "R":
        pontos = [[-a, -b] for a, b in pontos]
    return pontos


def _dentro_do_poligono(r: float, x: float, poligono) -> bool:
    dentro = False
    n = len(poligono)
    for i in range(n):
        r1, x1 = poligono[i]
        r2, x2 = poligono[(i + 1) % n]
        if (x1 > x) != (x2 > x):
            corte = r1 + (x - x1) * (r2 - r1) / (x2 - x1)
            if r < corte:
                dentro = not dentro
    return dentro


@dataclass(frozen=True)
class Parametros:
    """Os parâmetros da linha: o vetor `ZL` que serve de régua ao plano."""

    modulo: Numero
    angulo: Numero

    def para_json(self) -> dict:
        return {
            "modulo": self.modulo.valor, "angulo": self.angulo.valor,
            "origem": self.modulo.origem, "variavel": self.modulo.variavel,
            "variavel_angulo": self.angulo.variavel,
        }


# ---------------------------------------------------------------------------
# Os ajustes que vêm do arquivo
# ---------------------------------------------------------------------------

def _numero_do_ajuste(ajustes: dict[str, str], *nomes: str) -> tuple[float, str] | None:
    """O primeiro dos `nomes` que existir, com o nome da variável que casou."""
    for nome in nomes:
        bruto = ajustes.get(nome.upper())
        if bruto is None:
            continue
        try:
            return float(str(bruto).replace(",", ".").strip()), nome.upper()
        except ValueError:
            continue
    return None


def _texto_do_ajuste(ajustes: dict[str, str], *nomes: str) -> tuple[str, str] | None:
    for nome in nomes:
        bruto = ajustes.get(nome.upper())
        if bruto is not None and str(bruto).strip():
            return str(bruto).strip(), nome.upper()
    return None


def como_dicionario(ajustes) -> dict[str, str]:
    """Os pares do `formats/ajustes` viram `{NOME: valor}`, caixa alta."""
    saida: dict[str, str] = {}
    for par in ajustes or ():
        try:
            nome, valor = par[0], par[1]
        except (TypeError, IndexError, KeyError):
            continue
        saida[str(nome).strip().upper()] = str(valor).strip()
    return saida


def parametros_da_linha(ajustes: dict[str, str],
                     do_estudo: tuple[float, float] | None = None) -> Parametros | None:
    """`ZL`, do relé (`Z1MAG`/`Z1ANG`) ou da modelagem, nessa ordem.

    Do RELÉ primeiro, e não da modelagem: o plano existe para conferir o que o
    relé fez, e os parâmetros dele são a régua contra a qual os alcances dele foram
    escritos. A modelagem entra quando o arquivo não traz ajuste — e quando os
    dois existem, quem compara é a tela, que sabe dizer o que uma razão de
    exatamente RTP/RTC significa.
    """
    do_rele = _numero_do_ajuste(ajustes, "Z1MAG")
    angulo = _numero_do_ajuste(ajustes, "Z1ANG")
    if do_rele is not None and angulo is not None:
        return Parametros(Numero(do_rele[0], "lido", do_rele[1]),
                       Numero(angulo[0], "lido", angulo[1]))
    if do_estudo is not None:
        return Parametros(Numero(float(do_estudo[0]), "modelagem", ""),
                       Numero(float(do_estudo[1]), "modelagem", ""))
    return None


def k0_de(ajustes: dict[str, str]) -> tuple[complex, str, str] | None:
    """`(k0, origem, como foi obtido)`, ou `None` quando não dá para calcular.

    Dois caminhos, nesta ordem:

    1. o relé já traz o fator pronto — `k0M1`/`k0A1` (o da zona 1; no 311C é
       o único que existe) ou `k0M`/`k0A` (zonas 2 em diante no 4xx) — e
       usa-se como está;
    2. o relé traz `Z0MAG`/`Z0ANG` e a conta sai de `(Z0 − Z1) / (3 · Z1)`.

    Módulo e ângulo saem do MESMO par: o `k0M1` de uma zona com o `k0A` de
    outra seria um número que nenhum ajuste escreveu. E `Z0F` não entra: na
    SEL ele é o limiar do direcional de terra (32G), em ohm, e não fator de
    compensação nenhum (levantamento do banco e dos manuais, 24/10/2026).

    Sem nenhum dos dois **não se inventa**: uma falta à terra lida sem
    compensação sai mais longe do que é, e um número errado sem aviso é pior
    que número nenhum.
    """
    for modulo, angulo in (("K0M1", "K0A1"), ("K0M", "K0A")):
        pronto = _numero_do_ajuste(ajustes, modulo)
        pronto_ang = _numero_do_ajuste(ajustes, angulo)
        if pronto is not None and pronto_ang is not None:
            k0 = pronto[0] * complex(math.cos(math.radians(pronto_ang[0])),
                                     math.sin(math.radians(pronto_ang[0])))
            return k0, "lido", f"{pronto[1]} ∠ {pronto_ang[1]}"

    z1 = _numero_do_ajuste(ajustes, "Z1MAG")
    z1a = _numero_do_ajuste(ajustes, "Z1ANG")
    z0 = _numero_do_ajuste(ajustes, "Z0MAG")
    z0a = _numero_do_ajuste(ajustes, "Z0ANG")
    if None in (z1, z1a, z0, z0a):
        return None
    zz1 = z1[0] * complex(math.cos(math.radians(z1a[0])), math.sin(math.radians(z1a[0])))
    zz0 = z0[0] * complex(math.cos(math.radians(z0a[0])), math.sin(math.radians(z0a[0])))
    if abs(zz1) <= 0:
        return None
    return (zz0 - zz1) / (3.0 * zz1), "calculado", "(Z0 − Z1) / 3Z1"


def _contagem(ajustes: dict[str, str], nome: str) -> int | None:
    """`E21MP := 3` → 3; `N` → 0; ausente → `None`."""
    bruto = ajustes.get(nome)
    if bruto is None:
        return None
    texto = str(bruto).strip().upper()
    if texto in ("N", "NO", "OFF", "0"):
        return 0
    try:
        return int(float(texto))
    except ValueError:
        return None


def caracteristica_de(ajustes: dict[str, str], laco: str) -> dict:
    """Que formas o relé usa NESTE laço, e de onde se sabe.

    Na SEL, quantas zonas mho e quantas quadrilaterais estão habilitadas, por
    tipo de laço: `E21MP`/`E21XP` (fase), `E21MG`/`E21XG` (terra). No
    COXIPO: fase 3 mho e nenhuma quadrilateral; terra 3 de cada — as duas
    rodando em paralelo, e a zona atua se o ponto entrar em qualquer uma.
    """
    terra = laco.upper().endswith("N")
    # O nome muda com a família (banco do parque, 24/10/2026): o 4xx escreve
    # `E21MP`; o 311C, que não tem quadrilateral de fase, `E21P`; o 321,
    # `PMHOZ`/`GMHOZ`/`QUADZ`. O primeiro que existir vale.
    nomes_mho = ("E21MG", "GMHOZ") if terra else ("E21MP", "E21P", "PMHOZ")
    nomes_quad = ("E21XG", "QUADZ") if terra else ("E21XP",)
    nome_mho = next((n for n in nomes_mho if n in ajustes), nomes_mho[0])
    nome_quad = next((n for n in nomes_quad if n in ajustes), nomes_quad[0])
    mho, quad = _contagem(ajustes, nome_mho), _contagem(ajustes, nome_quad)
    partes = [f"{n} = {ajustes[n]}" for n in (nome_mho, nome_quad) if n in ajustes]
    return {"mho": mho, "quad": quad, "lida": bool(partes),
            "variaveis": " · ".join(partes)}


def _atraso(ajustes: dict[str, str], frequencia: float, *nomes: str):
    """O atraso da zona, como texto, e a variável. A SEL escreve em CICLOS
    (`Z2PD := 24.000` são 0,40 s a 60 Hz): ler como segundo mostraria 24 s."""
    achado = _texto_do_ajuste(ajustes, *nomes)
    if achado is None:
        return None
    texto, variavel = achado
    if texto.upper() == "OFF":
        return "desligada", variavel
    try:
        ciclos = float(texto.replace(",", "."))
    except ValueError:
        return texto, variavel
    if ciclos <= 0:
        return "inst.", variavel
    segundos = ciclos / (frequencia or 60.0)
    return (f"{ciclos:g} ciclos ({segundos:.2f} s)".replace(".", ","), variavel)


def zonas_de(ajustes: dict[str, str], parametros: Parametros | None,
             laco: str, frequencia: float = 60.0) -> list[Zona]:
    """As três zonas: lidas quando o arquivo traz, sugeridas quando não traz.

    O nome da variável depende do LAÇO: num laço de terra a SEL escreve
    `Z1MG/Z2MG/Z3MG`, num de fase `Z1MP/Z2MP/Z3MP` (no SEL-421; outras famílias
    `Z1P`). Mostrar a variável certa é o que deixa conferir no QuickSet sem
    adivinhar — e pegar a variável do outro laço desenharia a zona de terra
    num laço de fase, como acontecia (LT COXIPO, 22/10/2026).

    Zona com o alcance `OFF` está DESLIGADA no relé: não entra, e não vira
    sugestão — sugerir uma zona que o relé desligou desenharia uma
    característica que ele não tem.
    """
    de_terra = laco.upper().endswith("N")
    forma = caracteristica_de(ajustes, laco)
    saida: list[Zona] = []
    for n in (1, 2, 3):
        nome = f"Z{n}"
        candidatas = ((f"Z{n}MG", f"Z{n}G") if de_terra
                      else (f"Z{n}MP", f"Z{n}P", f"Z{n}PP"))
        if any(str(ajustes.get(c, "")).strip().upper() == "OFF" for c in candidatas):
            continue
        lido = _numero_do_ajuste(ajustes, *candidatas)
        tempo = _atraso(ajustes, frequencia,
                        *((f"Z{n}GD", f"Z{n}D", f"{nome}DELAY") if de_terra
                          else (f"Z{n}PD", f"Z{n}D", f"{nome}DELAY")))
        if lido is not None:
            alcance = Numero(lido[0], "lido", lido[1])
        elif parametros is not None:
            alcance = Numero(parametros.modulo.valor * SUGESTAO[nome] / 100.0,
                             "sugerido", "")
        else:
            continue
        if tempo is not None:
            texto, variavel = tempo
            origem = "lido"
        else:
            texto, variavel, origem = SUGESTAO_TEMPO[nome], "", "sugerido"
        # A direção: a SEL só escreve para a Z3 em diante (`DIR3`); Z1 e Z2
        # são sempre à frente.
        direcao, dir_origem, dir_var = "F", "padrão", ""
        achado = _texto_do_ajuste(ajustes, f"DIR{n}")
        if achado is not None and achado[0].upper() in ("F", "R"):
            direcao, dir_origem, dir_var = achado[0].upper(), "lido", achado[1]
        # A quadrilateral: alcance reativo e resistivo do laço.
        nx, nr = ((f"XG{n}", f"RG{n}") if de_terra else (f"XP{n}", f"RP{n}"))
        lx, lr = _numero_do_ajuste(ajustes, nx), _numero_do_ajuste(ajustes, nr)
        quad_x = Numero(lx[0], "lido", lx[1]) if lx else None
        quad_r = Numero(lr[0], "lido", lr[1]) if lr else None
        usa_mho = None if forma["mho"] is None else n <= forma["mho"]
        usa_quad = None if forma["quad"] is None else n <= forma["quad"]
        if usa_quad is False:
            # O relé não tem quadrilateral nesta zona: um `XP1` que sobrou no
            # arquivo não é ajuste vigente, e desenhá-lo como lido mentiria.
            quad_x = quad_r = None
        saida.append(Zona(nome, alcance, texto, origem, variavel,
                          direcao, dir_origem, dir_var, quad_x, quad_r,
                          usa_mho, usa_quad))
    return saida


# ---------------------------------------------------------------------------
# O que o usuário digitou por cima
# ---------------------------------------------------------------------------
#
# A terceira origem. As outras duas — `lido` e `sugerido` — saem do arquivo;
# esta sai do teclado, e por isso tem de passar por uma peneira antes de
# virar desenho: a tela manda texto, e um alcance negativo ou um ângulo de
# 400° desenhariam uma característica impossível sem ninguém notar.
#
# **O valor digitado é SECUNDÁRIO**, como todo ajuste de distância. É o que
# está escrito no relé, e é o que se confere no QuickSet — então é também o
# que se digita aqui. A conversão para primário é feita depois, junto com a
# dos valores lidos, pelo `_em_primario`: digitado e lido percorrem o mesmo
# caminho, que é o que impede os dois de divergirem de base.

#: Teto do ângulo dos parâmetros da linha. Uma linha é indutiva: o ângulo
#: vive entre 0° e 90°, e deixar passar 400° só serviria para desenhar uma
#: zona apontando para o lugar errado.
ANGULO_MAXIMO = 90.0


def _positivo(bruto) -> float | None:
    """Um número finito e maior que zero, ou `None`."""
    try:
        v = float(str(bruto).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def _angulo_valido(bruto) -> float | None:
    try:
        v = float(str(bruto).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or not -ANGULO_MAXIMO <= v <= ANGULO_MAXIMO:
        return None
    return v


def _base(cru) -> str:
    """Em que base o número foi DIGITADO. O formulário mostra a base do botão
    geral; quem digitou em primário digitou primário, e o servidor converte
    para secundário antes de usar — o ajuste do relé é secundário."""
    return "primario" if str(cru or "").lower() == "primario" else "secundario"


def em_secundario(manuais: dict, relacao: float | None) -> dict:
    """Os manuais com tudo em ohms SECUNDÁRIOS.

    Item digitado em primário é dividido por RTP/RTC. Sem relação conhecida
    não há como: ele fica como veio, e quem chama avisa.
    """
    if not manuais:
        return manuais
    saida: dict = {}
    zl = manuais.get("zl")
    if zl:
        zl = dict(zl)
        if zl.get("base") == "primario" and relacao and "modulo" in zl:
            zl["modulo"] = zl["modulo"] / relacao
        saida["zl"] = zl
    zonas = manuais.get("zonas")
    if zonas:
        novas = {}
        for nome, item in zonas.items():
            item = dict(item)
            if item.get("base") == "primario" and relacao:
                for campo in ("alcance", "x", "r"):
                    if campo in item:
                        item[campo] = item[campo] / relacao
            novas[nome] = item
        saida["zonas"] = novas
    return saida


def manuais_de(cru) -> dict:
    """O que a tela digitou, peneirado. Fora do formato, vira vazio."""
    if not isinstance(cru, dict):
        return {}
    saida: dict = {}

    # A RTP/RTC corrigida à mão: quando a do arquivo está errada, a análise
    # inteira (zona × trajetória) erra junto, sem nada denunciando.
    relacao = _positivo(cru.get("relacao"))
    if relacao is not None:
        saida["relacao"] = relacao

    zl = cru.get("zl")
    if isinstance(zl, dict):
        limpo = {}
        modulo = _positivo(zl.get("modulo"))
        angulo = _angulo_valido(zl.get("angulo"))
        if modulo is not None:
            limpo["modulo"] = modulo
        if angulo is not None:
            limpo["angulo"] = angulo
        if limpo:
            limpo["base"] = _base(zl.get("base"))
            saida["zl"] = limpo

    zonas = cru.get("zonas")
    if isinstance(zonas, dict):
        limpas: dict[str, dict] = {}
        for nome in SUGESTAO:
            z = zonas.get(nome)
            if not isinstance(z, dict):
                continue
            item: dict = {}
            for campo in ("alcance", "x", "r"):
                valor = _positivo(z.get(campo))
                if valor is not None:
                    item[campo] = valor
            tempo = str(z.get("tempo") or "").strip()[:24]
            if tempo:
                item["tempo"] = tempo
            if str(z.get("direcao") or "").upper() in ("F", "R"):
                item["direcao"] = str(z["direcao"]).upper()
            if item:
                item["base"] = _base(z.get("base"))
                limpas[nome] = item
        if limpas:
            saida["zonas"] = limpas
    return saida


def com_manuais_nos_parametros(base: Parametros | None,
                               manual: dict | None) -> Parametros | None:
    """Os parâmetros da linha com o que o usuário digitou por cima.

    Por CIMA, e não no lugar: quem digitou só o módulo fica com o ângulo do
    arquivo, e o campo que ele não tocou continua dizendo que veio do relé.
    Sem base, os dois são obrigatórios — inventar um ângulo seria a mesma
    coisa que o módulo `k0` que este arquivo se recusa a inventar.
    """
    if not manual:
        return base
    modulo = manual.get("modulo")
    angulo = manual.get("angulo")
    if base is None:
        if modulo is None or angulo is None:
            return None
        return Parametros(Numero(modulo, "digitado", ""),
                          Numero(angulo, "digitado", ""))
    return Parametros(
        base.modulo if modulo is None else Numero(modulo, "digitado", ""),
        base.angulo if angulo is None else Numero(angulo, "digitado", ""))


def com_manuais_nas_zonas(zonas: list[Zona], manual: dict | None) -> list[Zona]:
    """As zonas com o que o usuário digitou por cima, na ordem Z1, Z2, Z3.

    Uma zona que o arquivo não traz e o usuário digitou **nasce aqui**: é o
    caso do COMTRADE puro, em que não há ajuste nenhum para sobrescrever e
    mesmo assim se quer desenhar a característica.
    """
    if not manual:
        return zonas
    por_nome = {z.nome: z for z in zonas}
    for nome in SUGESTAO:
        item = manual.get(nome)
        if not item:
            continue
        base = por_nome.get(nome)
        alcance = item.get("alcance")
        tempo = item.get("tempo")
        mx, mr, md = item.get("x"), item.get("r"), item.get("direcao")
        if base is None:
            if alcance is None and (mx is None or mr is None):
                continue
            por_nome[nome] = Zona(
                nome, Numero(alcance or 0.0, "digitado" if alcance else "sugerido", ""),
                tempo or SUGESTAO_TEMPO[nome],
                "digitado" if tempo else "sugerido", "",
                md or "F", "digitado" if md else "padrão", "",
                None if mx is None else Numero(mx, "digitado", ""),
                None if mr is None else Numero(mr, "digitado", ""))
            continue
        from dataclasses import replace as _replace
        por_nome[nome] = _replace(
            base,
            alcance=base.alcance if alcance is None else Numero(alcance, "digitado", ""),
            tempo=base.tempo if tempo is None else tempo,
            tempo_origem=base.tempo_origem if tempo is None else "digitado",
            tempo_variavel="" if tempo is not None else base.tempo_variavel,
            direcao=base.direcao if md is None else md,
            direcao_origem=base.direcao_origem if md is None else "digitado",
            direcao_variavel=base.direcao_variavel if md is None else "",
            x=base.x if mx is None else Numero(mx, "digitado", ""),
            r=base.r if mr is None else Numero(mr, "digitado", ""),
        )
    return [por_nome[n] for n in SUGESTAO if n in por_nome]


def _tempo_legivel(bruto: str) -> str:
    """`0.00` vira `inst.`; `0.30` vira `0,30 s`."""
    try:
        v = float(str(bruto).replace(",", ".").strip())
    except ValueError:
        return str(bruto).strip()
    if v <= 0:
        return "inst."
    return f"{v:.2f} s".replace(".", ",")


# ---------------------------------------------------------------------------
# A trajetória
# ---------------------------------------------------------------------------

def _fasores_do_canal(amostras: np.ndarray, indices: np.ndarray,
                      ciclos: np.ndarray) -> np.ndarray:
    """O fasor complexo em cada um dos `indices`, como número complexo.

    A janela é a MESMA da tabelinha e da curva (`dsp/fasor.de_janela`): um
    ciclo de tempo, com a ponta interpolada. Calcular de outro jeito aqui faria
    o plano discordar da leitura do cursor no mesmo instante — e aí não haveria
    como saber qual dos dois está certo.

    `ciclos` é o ciclo em amostras de CADA índice (o do trecho dele), e `nan`
    onde a janela atravessaria a fronteira entre dois trechos.
    """
    # `no_instante` e não `de_janela`: é ele que obedece ao estimador
    # escolhido no menu do filtro (Fourier ou cosseno).
    saida = np.full(indices.size, np.nan + 0j, dtype=np.complex128)
    for k, n in enumerate(indices):
        if not np.isfinite(ciclos[k]):
            continue
        f = fasor_mod.no_instante(amostras, int(n), float(ciclos[k]))
        if f is None:
            continue
        saida[k] = f.fundamental * complex(math.cos(math.radians(f.angulo)),
                                           math.sin(math.radians(f.angulo)))
    return saida


def indices_da_trajetoria(i0: int, i1: int,
                          maximo: int = MAXIMO_DE_PONTOS) -> np.ndarray:
    """Os instantes em que a impedância é calculada, dentro da janela."""
    total = max(int(i1) - int(i0) + 1, 0)
    if total <= 0:
        return np.empty(0, dtype=np.int64)
    if total <= maximo:
        return np.arange(int(i0), int(i1) + 1, dtype=np.int64)
    return np.linspace(int(i0), int(i1), maximo, dtype=np.int64)


def trajetoria(registro: Record, canais_v: dict[str, int],
               canais_i: dict[str, int], laco: str, k0: complex | None,
               i0: int, i1: int,
               residual: int | None = None,
               amostras=None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(indices, R, X)` da impedância do laço.

    `canais_v` e `canais_i` são `{"A": idx, "B": idx, "C": idx}`. `residual` é
    o canal de `IN` quando o arquivo traz um; sem ele, `3I0` sai da soma das
    três fases, que é a mesma coisa quando as três existem.

    `amostras(canal)` é de onde saem os números. O padrão é a amostra crua do
    arquivo; quem chama de verdade manda a versão JÁ convertida para o lado
    pedido e JÁ sem prefixo — ver `_amostras_em_ohm` e o porquê que está lá.
    """
    letras = LACOS.get(laco.upper())
    if letras is None:
        raise ValueError(f"laço desconhecido: {laco}")

    indices = indices_da_trajetoria(i0, i1)
    if indices.size == 0:
        return (indices, np.empty(0), np.empty(0))

    # O ciclo de cada índice sai do TRECHO dele (`Record.trechos`), não de
    # `sample_rates[0]`: este vale 0 num `.cfg` com `nrates = 0` (SEL-751,
    # 311C — o plano saía vazio) e erra a janela na taxa múltipla. Onde a
    # janela atravessaria a fronteira de dois trechos fica `nan`: metade de
    # cada lado não é um ciclo de coisa nenhuma.
    ciclos = np.full(indices.size, np.nan)
    for trecho in registro.trechos:
        por_ciclo = fasor_mod.ciclo_em_amostras(trecho.taxa_hz, registro.line_frequency)
        if por_ciclo < fasor_mod.MINIMO_POR_CICLO:
            continue
        largura = fasor_mod.pesos_do_ciclo(por_ciclo).size
        dentro = ((indices < trecho.fim)
                  & (indices - trecho.inicio + 1 >= largura))
        ciclos[dentro] = por_ciclo
    if not np.isfinite(ciclos).any():
        return (np.empty(0, dtype=np.int64), np.empty(0), np.empty(0))

    crua = amostras or (lambda canal: registro.analog[canal])

    def fasores(canal: int) -> np.ndarray:
        return _fasores_do_canal(crua(canal), indices, ciclos)

    if len(letras) == 2:
        x, y = letras
        v = fasores(canais_v[x]) - fasores(canais_v[y])
        i = fasores(canais_i[x]) - fasores(canais_i[y])
    else:
        x = letras[0]
        v = fasores(canais_v[x])
        i = fasores(canais_i[x])
        if k0 is not None:
            if residual is not None:
                tres_i0 = fasores(residual)
            else:
                tres_i0 = (fasores(canais_i["A"]) + fasores(canais_i["B"])
                           + fasores(canais_i["C"]))
            i = i + k0 * tres_i0

    # O PISO: depois que o disjuntor abre sobram miliampères, e V/I dispara.
    # Sem isto a trajetória termina num traço até o infinito que domina o
    # desenho e esconde a falta, que é o que se foi olhar.
    modulo = np.abs(i)
    maior = float(np.nanmax(modulo)) if modulo.size and np.isfinite(modulo).any() else 0.0
    vivo = modulo > maior * PISO_DA_CORRENTE if maior > 0 else np.zeros_like(modulo, bool)

    z = np.full(indices.size, np.nan + 0j, dtype=np.complex128)
    np.divide(v, i, out=z, where=vivo & np.isfinite(v) & (modulo > 0))
    z[~vivo] = np.nan + 0j
    return indices, z.real, z.imag


def dentro_da_zona(r: float, x: float, alcance: float, angulo: float) -> bool:
    """O ponto está dentro da mho de diâmetro `alcance` no ângulo `angulo`?

    A mho auto-polarizada é a circunferência que passa pela origem e tem o
    vetor de alcance como DIÂMETRO. Estar dentro dela é estar a menos de meio
    alcance do centro.
    """
    if not (math.isfinite(r) and math.isfinite(x)) or alcance <= 0:
        return False
    cr = alcance / 2.0 * math.cos(math.radians(angulo))
    cx = alcance / 2.0 * math.sin(math.radians(angulo))
    return math.hypot(r - cr, x - cx) <= alcance / 2.0 + 1e-9


def entrada_nas_zonas(indices: np.ndarray, r: np.ndarray, x: np.ndarray,
                      zonas: list[Zona], angulo: float,
                      forma: str = "mho") -> dict[str, int | None]:
    """O primeiro instante em que a trajetória entra em cada zona.

    É o número que interessa: «entrou na Z1 no ciclo 2» responde, sozinho, se a
    atuação foi coerente com o alcance ajustado.

    `forma` é a característica em vista: `mho`, `quad` ou `ambas` — com as
    duas, entrar em qualquer uma conta, que é como o relé decide. A zona
    REVERSA é testada com o ponto espelhado na origem.
    """
    saida: dict[str, int | None] = {}
    for zona in zonas:
        poligono = (geometria_quad(zona.x.valor, zona.r.valor, angulo, "F")
                    if zona.x is not None and zona.r is not None else None)
        usar_mho = forma in ("mho", "ambas") and zona.alcance.valor > 0
        usar_quad = forma in ("quad", "ambas") and poligono is not None
        espelho = -1.0 if zona.direcao == "R" else 1.0
        achado = None
        for k in range(indices.size):
            rr, xx = espelho * float(r[k]), espelho * float(x[k])
            if not (math.isfinite(rr) and math.isfinite(xx)):
                continue
            if ((usar_mho and dentro_da_zona(rr, xx, zona.alcance.valor, angulo))
                    or (usar_quad and _dentro_do_poligono(rr, xx, poligono))):
                achado = int(indices[k])
                break
        saida[zona.nome] = achado
    return saida


# ---------------------------------------------------------------------------
# O pacote que vai para a tela
# ---------------------------------------------------------------------------

def _relacao_do_registro(registro: Record, canais_v=None,
                         canais_i=None) -> float | None:
    """`RTP / RTC` quando o arquivo declara as duas relações.

    É o número que transforma ohm primário em ohm secundário, e o único que
    deixa afirmar que uma divergência é troca de base e não erro de estudo.

    Lida dos canais DO LAÇO (`canais_v`, `canais_i`), quando vêm: são eles que
    entram em V/I. Olhar o registro inteiro misturava a relação do TP com a
    da tensão de bateria (`VDC1`, `V`, 1/1) — duas relações diferentes para
    «volt», nenhuma escolhida, e o plano em primário deixava as zonas em
    secundário com o aviso de «sem régua comum», num arquivo que declara
    240/1 e 1200/1 com todas as letras (LT COXIPO, 22/10/2026).
    """
    def relacao(grandeza: str, indices) -> float | None:
        canais = (registro.analog_channels if indices is None
                  else [registro.analog_channels[i] for i in indices])
        valores = {
            float(c.primary) / float(c.secondary)
            for c in canais
            if c.unit.strip().upper().endswith(grandeza)
            and getattr(c, "secondary", 0) and float(c.secondary) != 0
        }
        return valores.pop() if len(valores) == 1 else None

    def do_laco(canais):
        return None if not canais else list(canais.values())

    rtp = relacao("V", do_laco(canais_v))
    rtc = relacao("A", do_laco(canais_i))

    # `1` não é relação: é o que fica no campo quando o arquivo não declara
    # nada. Tratá-lo como relação faria o plano afirmar que primário e
    # secundário são a mesma coisa — e o veredito da zona sairia errado e
    # calado, que é justamente o que esta função existe para impedir. É a
    # mesma peneira que `plot/fasorial.py` aplica à base do pu.
    if not rtp or not rtc or rtp <= 1.0 or rtc <= 1.0:
        return None
    return rtp / rtc


#: Onde o relé escreve as relações. `CTR`/`PTR` é a SEL; os outros nomes
#: aparecem em arquivos de outros fabricantes e em exportações traduzidas.
#: Os SEL-4xx nomeiam a relação POR TERMINAL: TC em `CTRW`/`CTRX`, TP em
#: `PTRY`/`PTRZ` (421, 451, 411L — levantamento do banco, 24/10/2026). O
#: terminal principal (W, Y) vem antes; o certo, um dia, é escolher o terminal
#: da trinca que está no plano (`IAW` → W, `VAY` → Y).
NOMES_DA_RTC = ("CTR", "CTRW", "RTC", "CT_RATIO", "CTRX")
NOMES_DA_RTP = ("PTR", "PTRW", "RTP", "PT_RATIO", "PTRY", "PTRZ")


def _relacao_dos_ajustes(ajustes: dict[str, str]) -> float | None:
    """`RTP / RTC` lida dos AJUSTES do relé.

    Num `.CEV` as colunas vêm em primário e o cabeçalho do canal não declara
    relação nenhuma — ela mora nos ajustes, como `CTR` e `PTR`. Sem olhar
    aqui, o plano de um registro SEL fica sem jeito de pôr zona e trajetória
    na mesma base, embora o número esteja escrito no mesmo arquivo.
    """
    def numero(nomes) -> float | None:
        for nome in nomes:
            bruto = ajustes.get(nome)
            if bruto is None:
                continue
            try:
                valor = float(str(bruto).replace(",", ".").strip())
            except ValueError:
                continue
            # `1` não é relação: é o que fica no campo quando ninguém
            # declarou nada. Mesma peneira de `_relacao_do_registro`.
            if valor > 1.0:
                return valor
        return None

    rtp, rtc = numero(NOMES_DA_RTP), numero(NOMES_DA_RTC)
    if not rtp or not rtc:
        return None
    return rtp / rtc


def relacao_rtp_rtc(registro: Record, ajustes: dict[str, str]) -> float | None:
    """`RTP / RTC`: dos ajustes do relé primeiro, do cabeçalho dos canais depois.

    É o fator que leva ohm secundário a primário. Público porque a
    localização de falta precisa dele para os mesmos `Z1MAG` (ver
    `faultloc/seqneg.py`).
    """
    from osclab.formats import conjuntos

    # Dos canais das TRINCAS, como no plano: o registro inteiro mistura a
    # relação do TP com a da tensão de bateria e não decide nenhuma.
    achados = [c for c in conjuntos.de_registro(registro) if not c.sem_sinal]
    tensao = next((c.canais for c in achados if c.grandeza == "V"), None)
    corrente = next((c.canais for c in achados if c.grandeza == "I"), None)
    return (_relacao_dos_ajustes(ajustes)
            or _relacao_do_registro(registro, tensao, corrente))


def _em_primario(zonas: list[Zona], parametros: Parametros | None, fator: float):
    """As zonas e os parâmetros, multiplicados para a base primária.

    O ajuste do relé é SEMPRE secundário — é assim que se escreve `Z1MG`. Em
    primário são as ZONAS que mudam de base, e não a trajetória: a trajetória
    é medida, e medida não se reescreve para caber no desenho. Multiplicar as
    zonas é a mesma conta, feita do lado que não é dado.
    """
    from dataclasses import replace as _replace

    def numero(n: Numero) -> Numero:
        return _replace(n, valor=n.valor * fator)

    novas = [_replace(z, alcance=numero(z.alcance),
                      x=None if z.x is None else numero(z.x),
                      r=None if z.r is None else numero(z.r)) for z in zonas]
    novos_parametros = (None if parametros is None
                    else _replace(parametros, modulo=numero(parametros.modulo)))
    return novas, novos_parametros


def _aviso(curto: str, longo: str, tom: str = "atencao") -> dict:
    """Um aviso em duas alturas: a chip e o hover.

    A ficha do rodapé é uma linha de texto no meio do gráfico, e um aviso de
    três orações ali empurra todo o resto para fora da tela — foi o que
    aconteceu na primeira versão deste painel. Então o aviso tem um `curto`,
    que é o que se lê de relance, e um `longo`, que é o raciocínio inteiro e
    mora no hover. Nada é apagado; o que é explicação sai da linha de frente.
    """
    return {"curto": curto, "longo": longo, "tom": tom}


def _par_do_vinculo(registro: Record, chave: str):
    """A corrente e a tensão de um VÍNCULO, ou `(None, None)`.

    Não é «procurar a trinca de corrente e a de tensão com o mesmo rótulo»,
    e o motivo é o defeito que isso tinha: o rótulo (`G1`, `G2`) é contado
    entre TODOS os conjuntos do registro, então a corrente de um vão é `G1` e
    a tensão do MESMO vão é `G2`. Casar pelo rótulo pegava a tensão do lado
    errado — e um plano de impedância com a tensão do outro lado do
    transformador desenha uma trajetória plausível e inteiramente falsa.

    Quem sabe o que casa com o que é o vínculo, feito em «editar grupos». É a
    mesma fonte do triângulo de tensões (`plot/triangulo.py`).
    """
    escolhas = getattr(registro, "vinculos_de_potencia", None) or {}
    vinculo = escolhas.get(chave)
    if not vinculo:
        return None, None
    por_nome = {c.nome: c for c in conjuntos.de_registro(registro)}
    corrente = por_nome.get(chave)
    tensao = por_nome.get(str(vinculo.get("com") or ""))
    if corrente is None or tensao is None:
        return None, None
    if corrente.grandeza != "I" or tensao.grandeza != "V":
        return None, None
    return corrente, tensao


def _par_unico(registro: Record):
    """O par quando há UMA trinca de corrente e UMA de tensão. Aí não há o que
    casar, e exigir vínculo seria pedir que o usuário confirmasse a única
    resposta possível — que é o caso de quase todo registro de linha.

    Com duas de cada e nenhum vínculo, devolve `(None, None)`: ali o programa
    **não adivinha**. Escolher a primeira de cada uma é exatamente o defeito
    que `_par_do_vinculo` existe para não ter.
    """
    todos = [c for c in conjuntos.de_registro(registro) if not c.sem_sinal]
    correntes = [c for c in todos if c.grandeza == "I"]
    tensoes = [c for c in todos if c.grandeza == "V"]
    if len(correntes) == 1 and len(tensoes) == 1:
        return correntes[0], tensoes[0]
    # Uma tensão e várias correntes — o 87L da SEL grava `IA` (a do 21) e os
    # terminais do diferencial `IAL`, `IAX`, `IAT`. O nome responde, sem
    # palpite: a corrente que casa com a tensão é a de nome CORRESPONDENTE
    # (`I*` ↔ `V*`, `I*W` ↔ `V*W`). Só vale se for exatamente uma.
    if len(tensoes) == 1:
        alvo = _sem_grandeza(tensoes[0].nome)
        casam = [c for c in correntes if _sem_grandeza(c.nome) == alvo]
        if alvo and len(casam) == 1:
            return casam[0], tensoes[0]
    return None, None


def _sem_grandeza(nome: str) -> str:
    """`I*W` → `*W`, `V*` → `*`: o nome do conjunto sem a letra da grandeza.
    Vazio quando o nome não começa por ela (um `ccbm` declarado, por exemplo),
    e aí não há correspondência a afirmar."""
    nome = (nome or "").strip().upper()
    return nome[1:] if nome[:1] in ("I", "V", "U") and "*" in nome[1:3] else ""


def vinculos_possiveis(registro: Record) -> list[dict]:
    """Os vínculos que podem virar plano, com o motivo de quem não pode.

    Sai da lista do triângulo — é o mesmo par corrente×tensão —, mas o motivo
    é reescrito: o que o plano perde com tensão de linha não é a mesma coisa
    que o triângulo perde.
    """
    from osclab.plot import triangulo

    saida = []
    for cru in triangulo.vinculos_possiveis(registro):
        v = dict(cru)
        if not v.get("vale"):
            v["motivo"] = ("tensão de linha: sem as três fase-neutro não há "
                           "laço de terra, e é nele que caem quase todas as "
                           "faltas de linha")
        saida.append(v)
    return saida


def _amostras_em_ohm(registro: Record, lado: str):
    """De onde `trajetoria` tira os números, e por que não da amostra crua.

    `Z = V / I`, então a conta só fecha se V e I estiverem na MESMA base e sem
    prefixo. A amostra crua não está nem uma coisa nem outra:

    - **O prefixo.** Um relé grava a tensão em `kV` e a corrente em `A`.
      Dividir uma pela outra dá **kΩ**, e um plano em kΩ com zonas em Ω põe a
      falta mil vezes mais longe do que ela está — sem nada denunciando, que é
      a pior forma de errar que esta tela tem.
    - **O lado.** O botão `primário`/`secundário` do cabeçalho converte o que
      a tela desenha. Se o plano continuasse na base do arquivo, trocar o lado
      mudaria todos os gráficos menos este.

    Devolve `(amostras, lados)`: a função que entrega o canal já em volt ou
    ampère do lado pedido, e o conjunto de lados que realmente saíram. Mais de
    um lado ali dentro quer dizer que algum canal não declarou relação e ficou
    como estava — e aí V e I estão em bases diferentes. O desenho sai, com
    aviso: o programa avisa, nunca bloqueia.
    """
    from osclab.plot import conversao, unidades

    lados: set[str] = set()
    #: Para que lado houve CONVERSÃO de verdade (canal primário lido em
    #: secundário, ou o contrário). É onde uma RTP/RTC corrigida à mão tem de
    #: reescalar a trajetória — sem conversão, a relação não entrou na conta.
    virou: set[str] = set()

    def amostras(canal_idx: int) -> np.ndarray:
        canal = registro.analog_channels[canal_idx]
        bruto = registro.analog[canal_idx]
        # `1/1` NÃO é relação: é o que fica no campo quando o arquivo não
        # declara nada, e é o caso de todo `.CEV`. `conversao.converter`
        # divide por 1 e devolve o lado PEDIDO, o que é inofensivo para o
        # desenho de uma onda e fatal aqui: o plano acreditaria estar em
        # secundário com números primários, e compararia a trajetória com a
        # zona na régua errada sem nada denunciando.
        razao = conversao.relacao(canal)
        proprio = "primario" if canal.is_primary else "secundario"
        if razao > 1.0 and lado in ("primario", "secundario"):
            bruto, saiu, _ = conversao.converter(bruto, canal, lado)
        else:
            saiu = proprio
        lados.add(saiu)
        if saiu != proprio:
            virou.add(saiu)
        fator, _ = unidades.fator_do_prefixo(canal.unit)
        return bruto * fator if fator != 1.0 else bruto

    amostras.virou = virou
    return amostras, lados


def montar(registro: Record, painel, ajustes_do_registro: dict,
           lado: str, i0: int, i1: int) -> dict:
    """O pacote de um painel de impedância.

    Nunca levanta: um painel que não dá para montar devolve o motivo em
    `avisos` e a tela desenha o que sobrou. Ficar sem gráfico por falta de um
    ajuste é o oposto do que este programa faz com diagnóstico.
    """
    laco = (getattr(painel, "laco", "") or "AN").upper()
    avisos: list[str] = []

    # DE ONDE SAEM OS SEIS CANAIS, em ordem de certeza decrescente:
    # o vínculo que o usuário escolheu, o único que serve, ou o par único do
    # registro. Nunca «o primeiro de cada» — ver `_par_do_vinculo`.
    possiveis = vinculos_possiveis(registro)
    chave = (getattr(painel, "vinculo", "") or "").strip()
    escolhido = next((v for v in possiveis if v["vinculo"] == chave), None)
    if escolhido is None:
        servem = [v for v in possiveis if v["vale"]]
        escolhido = servem[0] if len(servem) == 1 else None
    corrente = tensao = None
    if escolhido is not None and escolhido["vale"]:
        corrente, tensao = _par_do_vinculo(registro, escolhido["vinculo"])
    if corrente is None or tensao is None:
        corrente, tensao = _par_unico(registro)

    # O NOME, quando a tela não mandou um. Traz o laço junto porque é ele
    # que muda a conta: dois planos do mesmo par com laços diferentes são
    # dois gráficos diferentes, e «Plano de impedância 1» e «2» não contam
    # qual é qual. Renomear apaga a marca e o servidor devolve o que recebeu.
    padrao_do_nome = (f"Impedância {escolhido['par']} · {laco}" if escolhido
                      else f"Impedância · {laco}")
    cabecalho = {
        "tipo": "impedancia", "id": painel.id,
        "nome": painel.nome or padrao_do_nome,
        "laco": laco, "lado": lado, "unidade": "Ω",
        "vinculo": escolhido["vinculo"] if escolhido else "",
        "par": escolhido["par"] if escolhido else "",
        "vinculos": possiveis,
    }
    if corrente is None or tensao is None:
        if escolhido is not None and not escolhido["vale"]:
            porque = escolhido["motivo"]
        elif possiveis:
            porque = ("este registro tem mais de um par corrente×tensão e "
                      "nenhum escolhido. Escolha no botão «vínculo» do "
                      "cabeçalho: casar pelo nome do grupo pegaria a tensão "
                      "do outro lado do equipamento, e o desenho sairia "
                      "plausível e errado")
        else:
            porque = ("este registro não tem uma trinca de corrente e uma de "
                      "tensão que formem um laço. Faça o par em «+ sinal» "
                      "→ «editar grupos» → «vincular»")
        return {**cabecalho, "pontos": [], "zonas": [], "parametros": None,
                "k0": None, "entradas": {}, "comparavel": False,
                "avisos": [_aviso("sem plano", porque[0].upper() + porque[1:] + ".",
                                  "ruim")]}

    ajustes = como_dicionario(ajustes_do_registro.get("ajustes"))
    # A RELAÇÃO antes de tudo: o que foi digitado em primário vira secundário
    # aqui, e o formulário volta na base do botão geral.
    relacao_lida = (_relacao_do_registro(registro, tensao.canais, corrente.canais)
                    or _relacao_dos_ajustes(ajustes))
    pedidos = manuais_de(getattr(painel, "manuais", None))
    relacao = pedidos.get("relacao") or relacao_lida
    manuais = em_secundario(pedidos, relacao)
    # Os parâmetros PRIMEIRO, e os manuais deles antes das zonas: a sugestão
    # de alcance sai de `SUGESTAO %` sobre o módulo, então mudar o módulo à
    # mão tem de chegar às zonas sugeridas — senão o usuário corrige a linha
    # e as zonas continuam calculadas sobre a linha antiga.
    parametros = com_manuais_nos_parametros(parametros_da_linha(ajustes),
                                            manuais.get("zl"))
    if parametros is None:
        avisos.append(_aviso(
            "sem os parâmetros da linha",
            "O arquivo não traz Z1MAG/Z1ANG. Sem os parâmetros não há régua de "
            "«% da LT» nem sugestão de alcance de zona."))

    # O k0 NÃO vira aviso. Ele é a outra metade da régua deste laço, e vai
    # escrito na mesma ficha dos parâmetros — que fica vermelha quando ele falta.
    # Como aviso, ele ocupava uma linha inteira do rodapé para dizer o que
    # cabe em duas palavras ao lado do número que ele corrige.
    compensacao = k0_de(ajustes)
    k0 = compensacao[0] if compensacao else None

    residual = corrente.canais.get("N")
    amostras, lados_vistos = _amostras_em_ohm(registro, lado)
    indices, r, x = trajetoria(registro, tensao.canais, corrente.canais,
                               laco, k0, i0, i1, residual, amostras)
    # A RTP/RTC digitada também corrige a TRAJETÓRIA quando ela passou por uma
    # conversão de base: Z secundário = Z primário ÷ (RTP/RTC), e a divisão foi
    # feita com a relação do arquivo.
    if pedidos.get("relacao") and relacao_lida and amostras.virou:
        k = (relacao_lida / relacao if "secundario" in amostras.virou
             else relacao / relacao_lida)
        r, x = r * k, x * k
    if pedidos.get("relacao"):
        avisos.append(_aviso(
            f"RTP/RTC digitada: {relacao:g}",
            f"A análise usa RTP/RTC = {relacao:g}, digitada à mão"
            + (f"; o arquivo diz {relacao_lida:g}." if relacao_lida
               else "; o arquivo não declara nenhuma.")))
    if len(lados_vistos) > 1:
        avisos.append(_aviso(
            "tensão e corrente em bases diferentes",
            "Parte dos canais deste laço não tem relação de TC/TP no arquivo "
            "e ficou como estava, então a tensão e a corrente que entram em "
            "Z = V/I não estão na mesma base. A FORMA da trajetória vale; o "
            "valor em ohms, não.", "ruim"))
    zonas = com_manuais_nas_zonas(
        zonas_de(ajustes, parametros, laco, registro.line_frequency or 60.0),
        manuais.get("zonas"))
    angulo = parametros.angulo.valor if parametros else 80.0
    forma_lida = caracteristica_de(ajustes, laco)
    escolha = str(getattr(painel, "caracteristica", "") or "").lower()
    if escolha not in ("mho", "quad", "ambas"):
        # Sem escolha: a que o relé usa; com as duas, mho (a tela avisa).
        escolha = ("quad" if forma_lida["quad"] and not forma_lida["mho"]
                   else "mho")

    # A BASE, que é onde dois desenhos certos dão uma conclusão errada.
    #
    # O ajuste do relé é SEMPRE secundário — é assim que se escreve `Z1MG`. A
    # trajetória sai na base em que os canais realmente ficaram, que pode não
    # ser a que a tela pediu: quando o arquivo não declara relação, o botão
    # «secundário» não converte nada e os canais continuam em primário. Com
    # as duas coisas em bases diferentes, a falta aparece fora de uma Z1 em
    # que ela entrou — errado e calado, que é o pior defeito desta tela.
    #
    # Quem muda de base são as ZONAS, nunca a trajetória: a trajetória é
    # medida, e medida não se reescreve para caber no desenho.
    base = (lados_vistos.pop() if len(lados_vistos) == 1
            else ("primario" if lado == "primario" else "secundario"))
    comparavel = True
    if base == "primario" and zonas:
        if relacao:
            zonas, parametros = _em_primario(zonas, parametros, relacao)
            if any(z.alcance.origem == "lido" for z in zonas):
                avisos.append(_aviso(
                    f"zonas × RTP/RTC = {relacao:g}",
                    f"O plano está em ohms primários e o ajuste do relé é "
                    f"secundário, como todo ajuste de distância. As zonas "
                    f"foram multiplicadas por RTP/RTC = {relacao:g} para "
                    f"caírem na mesma régua da trajetória; no relé elas "
                    f"continuam sendo o valor secundário."))
        else:
            comparavel = False
            avisos.append(_aviso(
                "zonas sem régua comum",
                "O plano está em ohms primários, o ajuste do relé é "
                "secundário e nem o arquivo nem os ajustes declaram RTC/RTP "
                "— sem elas as zonas não podem ser postas na mesma régua da "
                "trajetória. O desenho da trajetória vale; a posição das "
                "zonas e o veredito, não.", "ruim"))

    # O QUE O FORMULÁRIO EDITA, na base em que as zonas acabaram de ficar:
    # a do botão geral quando há relação, secundário quando não há. A tela
    # escreve a base ao lado de cada campo e manda de volta junto do número.
    # A RTP/RTC vai junto, editável (24/10/2026): é ela que leva o ajuste à
    # régua da trajetória, e quando a do arquivo está errada a análise
    # inteira erra junto.
    base_do_formulario = ("primario" if base == "primario" and relacao
                          else "secundario")
    para_o_formulario = {
        "zl": parametros.para_json() if parametros else None,
        "zonas": [z.para_json(parametros.modulo.valor if parametros else 0.0, angulo)
                  for z in zonas],
        "base": base_do_formulario,
        "relacao": relacao,
        "relacao_lida": relacao_lida,
        "relacao_digitada": bool(pedidos.get("relacao")),
    }

    if not zonas:
        entradas: dict[str, int | None] = {}
    elif comparavel:
        entradas = entrada_nas_zonas(indices, r, x, zonas, angulo, escolha)
    else:
        entradas = {z.nome: None for z in zonas}

    if zonas and all(z.alcance.origem == "sugerido" for z in zonas):
        avisos.append(_aviso(
            "zonas sugeridas, nenhuma do relé",
            "Nenhuma destas zonas saiu do relé: são o padrão do OscLab sobre "
            "os parâmetros da linha. Servem para situar a falta na linha; não "
            "servem para dizer se o relé devia ter atuado."))

    # O INSTANTE vai junto do índice. A tela marca os cursores no plano, e
    # cursor é tempo: sem `t` ela teria de refazer aqui o mapa índice→tempo
    # que o registro já tem — e erraria nos registros de taxa variável, em
    # que ele não é uma régua.
    pontos = [
        {"n": int(indices[k]),
         "t": float(registro.time[int(indices[k])]),
         "r": None if not math.isfinite(r[k]) else float(r[k]),
         "x": None if not math.isfinite(x[k]) else float(x[k])}
        for k in range(indices.size)
    ]
    return {
        **cabecalho,
        "pontos": pontos,
        "zonas": [z.para_json(parametros.modulo.valor if parametros else 0.0, angulo)
                  for z in zonas],
        "parametros": parametros.para_json() if parametros else None,
        "caracteristica": {**forma_lida, "escolhida": escolha},
        "k0": None if compensacao is None else {
            "re": k0.real, "im": k0.imag,
            "modulo": abs(k0), "angulo": math.degrees(math.atan2(k0.imag, k0.real)),
            "origem": compensacao[1], "de": compensacao[2],
        },
        "ajuste": para_o_formulario,
        "entradas": entradas,
        # `None` em `entradas` quer dizer DUAS coisas diferentes — «não
        # entrou nesta zona» e «não dá para comparar» —, e a tela precisa
        # distinguir: a primeira é notícia boa, a segunda é a tela dizendo
        # que não sabe. Este campo é a diferença.
        "comparavel": comparavel,
        "avisos": avisos,
    }
