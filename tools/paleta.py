"""Confere — e amplia — a paleta de cores dos traços.

## Por que isto existe

O cabeçalho do `osclab.css` afirma que as cores de fase "passaram pelo
validador de paleta". O validador era uma ferramenta de fora, e afirmação que
não se pode repetir não é verificável: quando foi preciso acrescentar cores
para o gráfico nunca repetir uma, não havia com que conferir se as novas se
separam das velhas. Agora há, e mora no repositório.

## O que ele confere

Para cada par de cores da paleta, em cada tema, e em quatro visões — normal,
protanopia, deuteranopia e tritanopia:

* **ΔE2000** entre os dois, que é a distância perceptual. Duas curvas no mesmo
  gráfico a ΔE < 15 são duas curvas que se confundem num relance — e num
  relance é como se lê uma oscilografia.
* **contraste WCAG** de cada cor contra o fundo do tema: um traço de 1,4 px
  precisa de pelo menos 3:1 para existir.

O daltonismo não é detalhe de acessibilidade aqui: é requisito de ofício.
Protanopia e deuteranopia somadas chegam a 8 % dos homens, e uma equipe de
proteção tem homens; um laudo em que IA e IC se confundem é um laudo errado
para quem o lê.

## O que ele NÃO decide

A escolha final é humana. O programa ordena os candidatos pela distância
mínima que cada um guarda da paleta que já existe, e quem escolhe olha. Cor é
convenção de campo — azul-A / branco-B / vermelho-C é da distribuidora, não da
matemática.

    python3 tools/paleta.py            confere a paleta atual
    python3 tools/paleta.py --sugerir  propõe cores para ampliá-la
"""

from __future__ import annotations

import argparse
import math

#: A paleta de traço de cada tema, como está no `osclab.css`.
TEMAS = {
    "escuro": {
        "fundo": "#0e1415",
        "cores": {
            "--fase-a": "#4b83d6",
            "--fase-b": "#b8860b",
            "--fase-c": "#d45560",
            "--fase-n": "#2c9b75",
            "--calculado-1": "#b07ae0",
            "--calculado-2": "#e86aa8",
            "--calculado-3": "#8aa0a6",
            "--traco-1": "#50a824",
            "--traco-2": "#e65d19",
            "--traco-3": "#75783a",
        },
    },
    "claro": {
        "fundo": "#ffffff",
        "cores": {
            "--fase-a": "#3574de",
            "--fase-b": "#b8860b",
            "--fase-c": "#96172b",
            "--fase-n": "#157f5c",
            "--calculado-1": "#6b3fa0",
            "--calculado-2": "#a8306a",
            "--calculado-3": "#57696b",
            "--traco-1": "#50a824",
            "--traco-2": "#e65d19",
            "--traco-3": "#75783a",
        },
    },
}

#: Distância perceptual mínima entre dois traços do mesmo gráfico. Abaixo
#: disso, "a azul e a outra azul" — que é como se descreve um gráfico que não
#: se lê.
DELTA_MINIMO = 15.0

#: Sob daltonismo a exigência cede um pouco: exigir o mesmo em todas as visões
#: esvazia o espaço de cor a ponto de sobrarem cinco tons de cinza. A legenda e
#: a tabelinha sempre nomeiam o sinal — a cor nunca carrega a identidade
#: sozinha —, então o alvo aqui é "dá para seguir a curva", não "dá para
#: nomeá-la pela cor".
DELTA_MINIMO_DALTONICO = 9.0

#: Contraste WCAG mínimo contra o fundo. Um traço de 1,4 px é texto fino.
CONTRASTE_MINIMO = 3.0

#: Pares que já estavam abaixo do piso quando este validador foi escrito, e
#: que ficaram como estão por decisão — não por descuido.
#:
#: `--fase-a` é convenção de campo da distribuidora (azul-A, âmbar-B,
#: vermelho-C) e não se muda sem conversar. `--calculado-1` e `--calculado-2`
#: podem mudar, e a conversa está pendente com o Alexandre.
#:
#: Estão aqui para o validador SAIR LIMPO: um verificador que reprova sempre
#: deixa de ser lido, e aí um conflito NOVO passa junto com os velhos. Tirar um
#: par daqui é a forma de dizer "resolvemos este".
CONHECIDAS = {
    ("--fase-a", "--calculado-1", "protanopia"),
    ("--calculado-1", "--calculado-2", "protanopia"),
}


# ---------------------------------------------------------------------------
# Conversões de cor
# ---------------------------------------------------------------------------

def de_hex(codigo: str) -> tuple[float, float, float]:
    codigo = codigo.lstrip("#")
    return tuple(int(codigo[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def para_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in rgb)


def linear(c: float) -> float:
    """sRGB com gama para luz linear. É nela que se soma e se mistura luz."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def com_gama(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def luminancia(rgb) -> float:
    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b) -> float:
    la, lb = luminancia(a), luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def para_lab(rgb) -> tuple[float, float, float]:
    r, g, b = (linear(c) for c in rgb)
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    # Branco D65
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(rgb1, rgb2) -> float:
    """ΔE2000 — a distância que corresponde ao que o olho chama de diferente.

    ΔE76 (a distância euclidiana em Lab) seria dez linhas, e erra justamente
    onde importa: ela exagera diferenças no azul e as esconde no amarelo, que
    é o par que este programa mais usa.
    """
    l1, a1, b1 = para_lab(rgb1)
    l2, a2, b2 = para_lab(rgb2)

    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_medio = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(c_medio ** 7 / (c_medio ** 7 + 25 ** 7))) \
        if c_medio > 0 else 0.0

    a1l, a2l = (1 + g) * a1, (1 + g) * a2
    c1l, c2l = math.hypot(a1l, b1), math.hypot(a2l, b2)
    h1 = math.degrees(math.atan2(b1, a1l)) % 360 if (a1l or b1) else 0.0
    h2 = math.degrees(math.atan2(b2, a2l)) % 360 if (a2l or b2) else 0.0

    dl = l2 - l1
    dc = c2l - c1l
    if c1l * c2l == 0:
        dh = 0.0
    elif abs(h2 - h1) <= 180:
        dh = h2 - h1
    else:
        dh = h2 - h1 - 360 if h2 > h1 else h2 - h1 + 360
    dhl = 2 * math.sqrt(c1l * c2l) * math.sin(math.radians(dh) / 2)

    l_medio = (l1 + l2) / 2
    cl_medio = (c1l + c2l) / 2
    if c1l * c2l == 0:
        h_medio = h1 + h2
    elif abs(h1 - h2) <= 180:
        h_medio = (h1 + h2) / 2
    elif h1 + h2 < 360:
        h_medio = (h1 + h2 + 360) / 2
    else:
        h_medio = (h1 + h2 - 360) / 2

    t = (1 - 0.17 * math.cos(math.radians(h_medio - 30))
         + 0.24 * math.cos(math.radians(2 * h_medio))
         + 0.32 * math.cos(math.radians(3 * h_medio + 6))
         - 0.20 * math.cos(math.radians(4 * h_medio - 63)))

    sl = 1 + (0.015 * (l_medio - 50) ** 2) / math.sqrt(20 + (l_medio - 50) ** 2)
    sc = 1 + 0.045 * cl_medio
    sh = 1 + 0.015 * cl_medio * t
    rt = -2 * math.sqrt(cl_medio ** 7 / (cl_medio ** 7 + 25 ** 7)) \
        * math.sin(math.radians(60 * math.exp(-(((h_medio - 275) / 25) ** 2)))) \
        if cl_medio > 0 else 0.0

    return math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dhl / sh) ** 2
                     + rt * (dc / sc) * (dhl / sh))


#: Matrizes de Viénot–Brettel–Mollon (1999) sobre RGB LINEAR. São a
#: aproximação padrão para protanopia e deuteranopia; para tritanopia a
#: aproximação linear é mais grosseira, e por isso ela entra aqui como aviso,
#: não como reprovação.
DICROMACIAS = {
    "protanopia": ((0.0, 2.02344, -2.52581), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "deuteranopia": ((1.0, 0.0, 0.0), (0.494207, 0.0, 1.24827), (0.0, 0.0, 1.0)),
    "tritanopia": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-0.395913, 0.801109, 0.0)),
}


def como_daltonico(rgb, tipo: str):
    r, g, b = (linear(c) for c in rgb)
    m = DICROMACIAS[tipo]
    saida = [m[i][0] * r + m[i][1] * g + m[i][2] * b for i in range(3)]
    return tuple(com_gama(c) for c in saida)


VISOES = ("normal", *DICROMACIAS)


def ver(rgb, visao: str):
    return rgb if visao == "normal" else como_daltonico(rgb, visao)


# ---------------------------------------------------------------------------
# Conferência
# ---------------------------------------------------------------------------

def conferir(cores: dict[str, str], fundo: str) -> tuple[list[str], list[str]]:
    """As queixas contra uma paleta: `(reprovações, avisos)`.

    Tritanopia fica no segundo saco. Não por ser menos importante para quem a
    tem, mas porque a simulação dela por matriz linear é reconhecidamente
    grosseira — reprovar por um número em que não se confia é trocar um
    problema real por um imaginário. Aparece para ser olhada, não para barrar.
    """
    reprovacoes, avisos = [], []
    rgb_fundo = de_hex(fundo)

    for nome, codigo in cores.items():
        razao = contraste(de_hex(codigo), rgb_fundo)
        if razao < CONTRASTE_MINIMO:
            reprovacoes.append(f"{nome} {codigo}: contraste {razao:.2f}:1 "
                               f"contra o fundo (mínimo {CONTRASTE_MINIMO})")

    nomes = list(cores)
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            for visao in VISOES:
                d = delta_e(ver(de_hex(cores[a]), visao),
                            ver(de_hex(cores[b]), visao))
                piso = (DELTA_MINIMO if visao == "normal"
                        else DELTA_MINIMO_DALTONICO)
                if d >= piso:
                    continue
                linha = f"{a} × {b} em {visao}: ΔE {d:.1f} (mínimo {piso})"
                if (a, b, visao) in CONHECIDAS:
                    avisos.append(f"{linha} — conhecido, ver CONHECIDAS")
                elif visao == "tritanopia":
                    avisos.append(linha)
                else:
                    reprovacoes.append(linha)
    return reprovacoes, avisos


def distancia_minima(codigo: str, cores: dict[str, str]) -> float:
    """A pior distância deste candidato contra a paleta, em todas as visões."""
    pior = math.inf
    for codigo_existente in cores.values():
        for visao in VISOES:
            d = delta_e(ver(de_hex(codigo), visao),
                        ver(de_hex(codigo_existente), visao))
            # Normaliza pelo piso de cada visão, para comparar maçãs com maçãs:
            # ΔE 12 sob protanopia é folga; ΔE 12 na visão normal é aperto.
            piso = DELTA_MINIMO if visao == "normal" else DELTA_MINIMO_DALTONICO
            pior = min(pior, d / piso)
    return pior


def candidatos(passo: int = 12):
    """Uma varredura grosseira do espaço de cor, em HSL."""
    for matiz in range(0, 360, passo):
        for saturacao in (0.45, 0.6, 0.75):
            for luz in (0.4, 0.5, 0.6, 0.7):
                yield hsl(matiz, saturacao, luz)


def hsl(h: float, s: float, luz: float) -> str:
    c = (1 - abs(2 * luz - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = luz - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x),
               (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return para_hex((r + m, g + m, b + m))


def sugerir(quantas: int = 5) -> None:
    """Propõe cores que se separam de TODAS as que já existem, nos dois temas.

    Guloso de propósito: escolhe a que guarda a maior distância mínima, junta
    ela à paleta e repete. Não é o ótimo global — mas o ótimo global de um
    problema destes muda de resposta com o piso escolhido, e o que se quer aqui
    é uma lista curta para um humano olhar.
    """
    atuais = {tema: dict(d["cores"]) for tema, d in TEMAS.items()}
    escolhidas = []

    for _ in range(quantas):
        melhor, melhor_nota = None, -math.inf
        for codigo in candidatos():
            notas = []
            for tema, dados in TEMAS.items():
                if contraste(de_hex(codigo), de_hex(dados["fundo"])) \
                        < CONTRASTE_MINIMO:
                    notas = []
                    break
                notas.append(distancia_minima(codigo, atuais[tema]))
            if not notas:
                continue
            nota = min(notas)
            if nota > melhor_nota:
                melhor, melhor_nota = codigo, nota
        if melhor is None:
            print("Acabaram os candidatos que cabem nos dois temas.")
            return
        escolhidas.append((melhor, melhor_nota))
        for tema in atuais:
            atuais[tema][f"novo-{len(escolhidas)}"] = melhor

    print("Candidatos, do que guarda mais folga para o que guarda menos.")
    print("A nota é a distância mínima dividida pelo piso: 1,00 é o limite.\n")
    for i, (codigo, nota) in enumerate(escolhidas, start=1):
        print(f"  {i}. {codigo}   folga {nota:.2f}×")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sugerir", action="store_true",
                        help="propõe cores novas em vez de conferir as atuais")
    parser.add_argument("--quantas", type=int, default=5)
    argumentos = parser.parse_args()

    if argumentos.sugerir:
        sugerir(argumentos.quantas)
        return 0

    problemas = 0
    for tema, dados in TEMAS.items():
        reprovacoes, avisos = conferir(dados["cores"], dados["fundo"])
        print(f"tema {tema}: {len(dados['cores'])} cores, "
              f"{len(reprovacoes) or 'nenhuma'} reprovação(ões), "
              f"{len(avisos)} aviso(s)")
        for q in reprovacoes:
            print(f"  ✗ {q}")
        for q in avisos:
            print(f"  · {q}")
        problemas += len(reprovacoes)
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
