"""A lista de eventos pronta para a tela, no TEMPO DA ABA.

O leitor (`formats/eventos.py`) entrega o tempo de cada evento contado da
primeira amostra do registro dele. Com mais de um registro na aba, o B e o C
estão deslocados em relação ao A (`plot/alinhamento.py`): o instante `t` da
aba cai em `t + d` no outro registro, então o evento do outro entra em
`t − d`. A conta é feita aqui, com o MESMO `d` que desloca as ondas — se a
lista e a onda usassem deslocamentos diferentes, clicar no trip do B poria o
cursor fora do trip do B, sem nada denunciar.

A lista de cada registro vai separada, com a letra do IED. Juntar e ordenar
é da tela, que precisa das duas formas: uma lista só, em ordem de tempo, que
é o que responde «o trip do B veio antes ou depois do A?», e o filtro por IED.
"""

from __future__ import annotations

#: O que se diz quando o registro não traz lista nenhuma.
SEM_LISTA = ("este registro não trouxe lista de eventos. A da Schneider vem no "
             ".hdr, junto com o COMTRADE; a SEL (SER) e a Ingeteam (SUCESOS) "
             "exportam a lista à parte, e a importação desses arquivos ainda "
             "vai entrar")
#: E quando há um arquivo, mas o programa não achou nele uma tabela que
#: soubesse ler. Pedido dele, 02/11/2026: relé que nunca vimos escreve a
#: hora, o sinal e o valor em outra ordem, e tabela lida errado é pior que o
#: texto cru — o texto ao menos não mente.
NAO_RECONHECIDA = ("o programa não reconheceu uma tabela de eventos neste "
                   "arquivo, então ele vai como veio, sem ligação com o cursor")


def chave_do_nome(nome: str) -> str:
    """O nome sem espaço nem dois-pontos, em maiúsculas.

    O mesmo sinal vem escrito de dois jeitos pelo MESMO relé: `MAIN  Gen.
    trip command` na lista de eventos e `MAIN : Gen. trip command` no canal
    digital do COMTRADE (Schneider, conferido nos 250 `.hdr` do banco: 15 316
    eventos casaram com o digital na mesma amostra).
    """
    return "".join(c for c in (nome or "").upper() if not c.isspace() and c != ":")


def indice_dos_digitais(canais) -> dict[str, int]:
    """`{chave do nome: índice}` dos digitais de um registro. Nome repetido
    fica com o primeiro: dois canais de mesmo nome não se distinguem pelo
    texto do evento, e escolher o segundo seria palpite."""
    saida: dict[str, int] = {}
    for canal in canais or ():
        saida.setdefault(chave_do_nome(canal.name), canal.index)
    return saida


def _linha(evento, d: float, fim: float | None, conhecida: bool,
           digitais: dict[str, int] | None = None) -> dict:
    t = evento.t - d if conhecida and evento.t is not None else None
    # Fora da gravação: o relé continua listando depois que o COMTRADE acaba
    # (no banco, 4186 eventos de 250 listas). Aparece, mas não leva o cursor:
    # ali não há onda para ele cair.
    fora = conhecida and evento.t is not None and (
        evento.t < 0 or (fim is not None and evento.t > fim))
    # O digital que este evento nomeia, quando o registro o grava: clicar no
    # evento seleciona a tira dele (pedido dele, 02/11/2026). Sem casamento,
    # `None` — o clique só move o cursor, e nada se inventa.
    digital = (digitais or {}).get(chave_do_nome(evento.descricao))
    return {"t": t, "hora": evento.hora, "endereco": evento.endereco,
            "descricao": evento.descricao, "valor": evento.valor, "fora": bool(fora),
            "digital": digital}


def lista(letra: str, sha: str, apelido: str, achada, d: float = 0.0,
          fim: float | None = None, digitais: dict[str, int] | None = None) -> dict:
    """O pacote de UM registro. `achada` é a `formats.eventos.Lista` ou None.

    `tem` é ter a lista ANIMADA (ligada ao cursor). Sem ela, `cru` pode
    trazer o arquivo como veio — a tela mostra o texto em vez de nada.
    """
    pacote = {"letra": letra, "sha": sha, "apelido": apelido or "",
              "tem": achada is not None and achada.reconhecida,
              "cru": achada.cru if achada is not None else ""}
    if achada is None or not achada.reconhecida:
        pacote.update(motivo=SEM_LISTA if achada is None else NAO_RECONHECIDA,
                      de=achada.de if achada is not None else "",
                      referencia="", avisos=[], eventos=[], dados=[])
        return pacote
    conhecida = achada.referencia_conhecida
    pacote.update(
        motivo="",
        de=achada.de,
        referencia=achada.referencia,
        avisos=list(achada.avisos),
        eventos=[_linha(e, d, fim, conhecida, digitais) for e in achada.eventos],
        dados=[_linha(e, d, fim, conhecida) for e in achada.dados],
    )
    return pacote


# ===========================================================================
# A lista de HORA DE RELÓGIO no tempo da aba (10/11/2026).
#
# Um `.eev`, um SER, uns SUCESOS trazem data e hora; a tela fala em segundos
# desde a primeira amostra. Entre as duas coisas há um deslocamento que o
# arquivo de eventos NÃO declara — o fuso dele, e às vezes o relógio de outro
# relé. A regra do leitor universal: o que o arquivo não diz vira campo para
# digitar, com uma SUGESTÃO ao lado, e a tela diz a origem (lido, sugerido,
# digitado).
#
# A sugestão é medida, não palpite de calendário: para cada deslocamento
# candidato (de −14 h a +14 h, de 15 em 15 min), conta-se quantos eventos
# caem na MESMA amostra de um digital do registro que tem o mesmo nome e
# muda ali. Ganha o que casa mais; empate, o que põe mais eventos dentro da
# gravação; empate de novo, a diferença dos fusos que o `.cfg` declara.
# ===========================================================================

import re as _re  # noqa: E402

import numpy as _np  # noqa: E402

#: Quantos eventos têm de casar para a sugestão se chamar sugestão.
MINIMO_CASADOS = 2
_CANDIDATOS_H = _np.arange(-14.0, 14.0001, 0.25)


def mudancas_dos_digitais(registro) -> dict[str, _np.ndarray]:
    """`{chave do nome: instantes em que o digital muda}` (s, tempo do registro)."""
    saida: dict[str, _np.ndarray] = {}
    if registro is None or not registro.n_samples or registro.status.size == 0:
        return saida
    tempo = _np.asarray(registro.time, dtype=float)
    muda = _np.diff(registro.status.astype(_np.int8), axis=1) != 0
    for canal in registro.status_channels:
        linha = muda[canal.index] if canal.index < muda.shape[0] else None
        if linha is None:
            continue
        idx = _np.nonzero(linha)[0] + 1
        if idx.size:
            saida.setdefault(chave_do_nome(canal.name), tempo[idx])
    return saida


def _segundos_desde(eventos, inicio) -> _np.ndarray:
    return _np.array([(e.quando - inicio).total_seconds() if e.quando is not None else _np.nan
                      for e in eventos], dtype=float)


def _tolerancia(registro) -> float:
    taxa = registro.base_rate_hz if registro is not None else 0.0
    return max(0.002, 1.5 / taxa) if taxa else 0.002


def _casados(t: _np.ndarray, chaves: list[str], mudancas: dict, tol: float) -> int:
    n = 0
    for ti, k in zip(t, chaves, strict=False):
        m = mudancas.get(k)
        if m is None or not _np.isfinite(ti):
            continue
        j = _np.searchsorted(m, ti)
        perto = min((abs(m[x] - ti) for x in (j - 1, j) if 0 <= x < m.size), default=_np.inf)
        if perto <= tol:
            n += 1
    return n


def texto_do_deslocamento(h: float) -> str:
    """`4.0` → `+4:00`; `-3.5` → `−3:30`; com segundos quando os há."""
    sinal = "−" if h < 0 else "+"
    s = abs(h) * 3600.0
    hh, resto = divmod(s, 3600.0)
    mm, ss = divmod(resto, 60.0)
    base = f"{sinal}{int(hh)}:{int(mm):02d}"
    if ss >= 0.0005:
        base += f":{ss:06.3f}".replace(".", ",")
    return base


_DESLOC = _re.compile(
    r"^\s*([+\-−]?)\s*(\d{1,2})(?::(\d{1,2}))?(?::(\d{1,2}(?:[.,]\d+)?))?\s*h?\s*$")


def ler_deslocamento(texto: str) -> float | None:
    """`+4`, `-4:00`, `−3:30`, `0:00:00,012` → horas; `None` se ilegível."""
    m = _DESLOC.match(texto or "")
    if not m:
        try:
            return float((texto or "").replace(",", ".").replace("−", "-"))
        except ValueError:
            return None
    sinal = -1.0 if m.group(1) in ("-", "−") else 1.0
    seg = float((m.group(4) or "0").replace(",", "."))
    return sinal * (int(m.group(2)) + int(m.group(3) or 0) / 60.0 + seg / 3600.0)


def _fuso_declarado(registro) -> float | None:
    """`carimbo − local` do `.cfg`: a diferença que uma lista em hora LOCAL
    teria contra um registro carimbado noutro fuso."""
    if registro is None:
        return None
    carimbo, local = registro.fuso_horas, getattr(registro, "fuso_local_horas", None)
    if carimbo is None or local is None:
        return None
    return carimbo - local


def sugerir(eventos, registro, mudancas) -> dict:
    """A melhor hipótese de deslocamento para esta lista, com o porquê."""
    if registro is None or registro.start_time is None:
        return {"h": 0.0, "casados": 0, "dentro": 0,
                "porque": "o registro não diz a hora de início"}
    base = _segundos_desde(eventos, registro.start_time)
    chaves = [chave_do_nome(e.descricao) for e in eventos]
    dur = float(registro.time[-1]) if registro.n_samples else 0.0
    tol = _tolerancia(registro)
    declarado = _fuso_declarado(registro)
    melhor = None
    tabela = []
    for h in _CANDIDATOS_H:
        t = base + h * 3600.0
        dentro = int(_np.count_nonzero((t >= 0) & (t <= dur)))
        casados = _casados(t, chaves, mudancas, tol) if dentro else 0
        prefer = 1 if declarado is not None and abs(h - declarado) < 1e-9 else 0
        nota = (casados, dentro, prefer, -abs(h))
        tabela.append((nota, float(h), casados, dentro))
        if melhor is None or nota > melhor[0]:
            melhor = (nota, float(h), casados, dentro)
    _, h, casados, dentro = melhor
    if casados >= MINIMO_CASADOS:
        porque = (f"{casados} eventos caem na mesma amostra de um digital do registro "
                  f"com o mesmo nome")
    elif dentro:
        porque = (f"nenhum evento casa com um digital; com este deslocamento "
                  f"{dentro} eventos caem dentro da gravação")
    else:
        h = declarado if declarado is not None else 0.0
        casados = dentro = 0
        porque = ("com deslocamento nenhum entre −14 h e +14 h algum evento cai dentro "
                  "da gravação: confira se a lista é deste relé e deste dia")
    outros = sorted(tabela, reverse=True)[:4]
    return {"h": h, "casados": casados, "dentro": dentro, "porque": porque,
            "candidatos": [{"h": x[1], "texto": texto_do_deslocamento(x[1]), "casados": x[2],
                            "dentro": x[3]} for x in outros if x[3]]}


def _texto_do_fuso(h: float | None) -> str:
    if h is None:
        return ""
    if abs(h) < 1e-9:
        return "UTC"
    return "UTC" + texto_do_deslocamento(h)


def _o_registro_diz(registro) -> str:
    if registro is None:
        return ""
    partes = []
    if registro.fuso_horas is not None:
        partes.append(f"carimbos em {_texto_do_fuso(registro.fuso_horas)}")
    local = getattr(registro, "fuso_local_horas", None)
    if local is not None and local != registro.fuso_horas:
        partes.append(f"hora local {_texto_do_fuso(local)}")
    return ("; ".join(partes) + " (lido do .cfg)") if partes else "o registro não declara fuso"


def _sugerir_fonte(achada, registro, textos_do_registro, mudancas) -> tuple[str, str, str]:
    """`(fonte, origem, porquê)` num arquivo que junta vários relés."""
    fontes = list(achada.fontes)
    if len(fontes) <= 1:
        return (fontes[0] if fontes else ""), "lido", "o arquivo traz um relé só"
    chave = chave_do_nome(" ".join(textos_do_registro))
    pelo_nome = [f for f in fontes if chave_do_nome(f) and chave_do_nome(f) in chave]
    if len(pelo_nome) == 1:
        return pelo_nome[0], "sugerido", "o nome do relé aparece no registro"
    melhor = ("", 0)
    for f in fontes:
        s = sugerir([e for e in achada.eventos if e.fonte == f], registro, mudancas)
        if s["casados"] > melhor[1]:
            melhor = (f, s["casados"])
    if melhor[1] >= MINIMO_CASADOS:
        return (melhor[0], "sugerido",
                f"{melhor[1]} eventos dele casam com digitais deste registro")
    return "", "nenhum", "nenhum relé do arquivo se deixou casar com este registro"


def _dt_e_rajadas(linhas: list[dict]) -> None:
    """Δ desde o instante anterior DA MESMA FONTE, e o número da rajada
    (eventos no mesmo milissegundo). Conta do servidor, não da tela."""
    por_fonte: dict[str, list[dict]] = {}
    for x in linhas:
        if x["t"] is not None:
            por_fonte.setdefault(x["fonte"], []).append(x)
    rajada = 0
    for grupo in por_fonte.values():
        grupo.sort(key=lambda x: x["t"])
        anterior = None
        for x in grupo:
            if anterior is None or x["t"] - anterior > 0.0005:
                x["dt"] = None if anterior is None else round((x["t"] - anterior) * 1000.0, 3)
                rajada += 1
                anterior = x["t"]
            else:
                x["dt"] = 0.0
            x["rajada"] = rajada


def pacote(letra: str, sha: str, apelido: str, achada, registro, d: float = 0.0,
           escolhas: dict | None = None, importado: bool = False,
           textos_do_registro: tuple[str, ...] = ()) -> dict:
    """O pacote de UMA lista (do registro ou importada), já no tempo da aba."""
    escolhas = escolhas or {}
    fim = float(registro.time[-1]) if registro is not None and registro.n_samples else None
    digitais = indice_dos_digitais(registro.status_channels) if registro is not None else {}
    base = lista(letra, sha, apelido, achada, d, fim, digitais)
    base.update(gravacao=([-d, fim - d] if fim is not None else None),
                importado=importado, arquivo=(achada.de if achada is not None else ""),
                formato=(achada.formato if achada is not None else ""),
                casas=(achada.casas if achada is not None else 3),
                colunas_extras=list(achada.colunas_extras) if achada is not None else [],
                fontes=[], fonte={"nome": "", "origem": "", "porque": ""},
                ordem={"valor": "", "origem": ""}, tempo={"modo": "relativo"})
    if achada is None or not achada.reconhecida:
        return base
    # Linhas do relé: a mais, o número da linha do arquivo, a fonte e as medidas.
    for linha_pkg, e in zip(base["eventos"], achada.eventos, strict=False):
        linha_pkg.update(linha=e.linha, fonte=e.fonte, numero=e.numero,
                         operando=e.operando, data=e.data, extras=list(e.extras))
        linha_pkg["fora"] = ("antes" if linha_pkg["t"] is not None and e.t < 0 else
                             "depois" if linha_pkg["fora"] else "")
    if achada.tempo != "absoluto":
        base["tempo"] = {"modo": "relativo",
                         "porque": (f"tRel do relé, contado de «{achada.referencia}»"
                                    if achada.referencia else "tRel do relé")
                                   + " — a primeira amostra do registro (lido do arquivo)"}
        _dt_e_rajadas(base["eventos"])
        return base

    mudancas = mudancas_dos_digitais(registro)
    # A fonte (o relé, num arquivo que junta vários).
    if "fonte" in escolhas:
        fonte, origem_f, porque_f = escolhas["fonte"], "digitado", "escolhido por você"
    else:
        fonte, origem_f, porque_f = _sugerir_fonte(achada, registro, textos_do_registro,
                                                    mudancas)
    contagem = {}
    for e in achada.eventos:
        contagem[e.fonte] = contagem.get(e.fonte, 0) + 1
    base["fontes"] = [{"nome": f, "n": contagem.get(f, 0)} for f in achada.fontes]
    base["fonte"] = {"nome": fonte, "origem": origem_f, "porque": porque_f}
    base["ordem"] = {"valor": achada.ordem_da_data, "origem": achada.origem_da_ordem}

    # O deslocamento.
    deles = [e for e in achada.eventos if not fonte or e.fonte == fonte]
    sug = sugerir(deles, registro, mudancas)
    digitado = (ler_deslocamento(escolhas.get("deslocamento", ""))
                if "deslocamento" in escolhas else None)
    erro = ("escreva como +4:00, −3:30 ou 0:00:00,012"
            if "deslocamento" in escolhas and digitado is None else "")
    if digitado is not None:
        h, origem, porque = digitado, "digitado", "digitado por você"
    else:
        h = sug["h"]
        origem = "sugerido" if sug["casados"] >= MINIMO_CASADOS or sug["dentro"] else "nenhum"
        porque = sug["porque"]
    inicio = registro.start_time if registro is not None else None
    base["tempo"] = {
        "modo": "absoluto", "registro": _o_registro_diz(registro),
        "inicio": inicio.strftime("%d/%m/%Y %H:%M:%S.%f") if inicio else "",
        "eventos": "o arquivo de eventos não declara fuso",
        "h": h, "texto": texto_do_deslocamento(h), "origem": origem, "porque": porque,
        "sugerido": {"h": sug["h"], "texto": texto_do_deslocamento(sug["h"]),
                     "casados": sug["casados"], "dentro": sug["dentro"],
                     "porque": sug["porque"]},
        "candidatos": sug.get("candidatos", []),
        "erro": erro,
    }
    ts = (_segundos_desde(achada.eventos, inicio) + h * 3600.0) if inicio else None
    for k, linha_pkg in enumerate(base["eventos"]):
        t = float(ts[k]) if ts is not None and _np.isfinite(ts[k]) else None
        linha_pkg["t"] = None if t is None else t - d
        linha_pkg["fora"] = ("" if t is None or (0 <= t <= (fim or 0)) else
                             "antes" if t < 0 else "depois")
    _dt_e_rajadas(base["eventos"])
    base["dentro"] = sum(1 for x in base["eventos"] if x["t"] is not None and not x["fora"])
    return base


# ===========================================================================
# A DISTRIBUIÇÃO dos eventos no tempo (11/11/2026), para a
# trilha. É contagem — quantos eventos caem em cada intervalo —, e por isso
# sai daqui; a tela só pinta. Nada se classifica: conta-se o que o arquivo
# listou, com o relé (A, B, C) como única separação.
# ===========================================================================

#: Os intervalos possíveis, de 1 ms a 2 dias. O da trilha é o MENOR que
#: deixa as barras com uns 4 px: a escala escolhe, ninguém digita.
_PASSOS = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30,
           60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800)
#: Pixels por barra que a trilha mira.
PIXELS_POR_BARRA = 4
_MAXIMO_DE_BARRAS = 1000


def texto_do_tempo(t: float) -> str:
    """Segundos no tempo da aba, para o hover: `0,162 s`, `−12 min 4 s`,
    `−16 h 35 min`, `−2 d 3 h`."""
    sinal = "−" if t < 0 else ""
    a = abs(t)
    if a < 60:
        return f"{sinal}{a:.3f} s".replace(".", ",")
    if a < 3600:
        return f"{sinal}{int(a // 60)} min {int(a % 60)} s"
    if a < 86400:
        return f"{sinal}{int(a // 3600)} h {int(a % 3600 // 60)} min"
    return f"{sinal}{int(a // 86400)} d {int(a % 86400 // 3600)} h"


def texto_do_passo(passo: float) -> str:
    if passo < 1:
        return f"{passo * 1000:g} ms"
    if passo < 60:
        return f"{passo:g} s"
    if passo < 3600:
        return f"{passo / 60:g} min"
    if passo < 86400:
        return f"{passo / 3600:g} h"
    return f"{passo / 86400:g} d"


def distribuicao(pacotes: list[dict], largura_px: float, escondidos=(),
                 faixa: tuple[float, float] | None = None) -> dict:
    """Quantos eventos caem em cada intervalo, no tempo da aba.

    `pacotes` são os de `pacote()`; `escondidos` são as chaves `letra|relé`
    desligadas na tela (as mesmas dos chips); `faixa` restringe a um trecho
    (a ampliação da gravação). A altura de cada barra (`h`, de 0 a 1) é
    PROPORCIONAL à contagem: o maior intervalo do registro vale 1 (pedido de
    11/11/2026, no lugar da raiz). Quem garante que um evento solto não some
    é a tela, com um mínimo de 2 px para toda contagem maior que zero.
    """
    escondidos = set(escondidos or ())
    tempos: list[float] = []
    letras: list[str] = []
    gravacao = None
    for p in pacotes:
        if gravacao is None and p.get("gravacao"):
            gravacao = tuple(p["gravacao"])
        if not p.get("tem"):
            continue
        primeira = p["fontes"][0]["nome"] if p.get("fontes") else ""
        for e in p["eventos"]:
            if e.get("t") is None:
                continue
            if f'{p["letra"]}|{e.get("fonte") or primeira}' in escondidos:
                continue
            tempos.append(float(e["t"]))
            letras.append(p["letra"])
    t = _np.asarray(tempos, dtype=float)
    if faixa is not None:
        lo, hi = float(faixa[0]), float(faixa[1])
        dentro = (t >= lo) & (t <= hi)
        t = t[dentro]
        letras = [x for x, ok in zip(letras, dentro, strict=False) if ok]
    else:
        extremos = list(t) + (list(gravacao) if gravacao else [])
        lo, hi = (min(extremos), max(extremos)) if extremos else (0.0, 1.0)
    if hi - lo <= 0:
        hi = lo + 0.001
    alvo = max(10, int(largura_px // PIXELS_POR_BARRA))
    passo = next((x for x in _PASSOS if x >= (hi - lo) / alvo), None)
    if passo is None:
        passo = _PASSOS[-1] * _np.ceil((hi - lo) / alvo / _PASSOS[-1])
    inicio = float(_np.floor(lo / passo) * passo)
    n = int(min(_MAXIMO_DE_BARRAS, max(1, _np.ceil((hi - inicio) / passo + 1e-9))))
    idx = (_np.clip(((t - inicio) // passo).astype(int), 0, n - 1) if t.size
           else _np.zeros(0, int))
    contagens = _np.bincount(idx, minlength=n)[:n]
    maximo = int(contagens.max()) if contagens.size else 0
    h = contagens / maximo if maximo else _np.zeros(n)
    pilhas = {}
    for letra in sorted(set(letras)):
        sel = _np.array([x == letra for x in letras], dtype=bool)
        c = _np.bincount(idx[sel], minlength=n)[:n]
        pilhas[letra] = [round(float(v), 4) for v in
                         _np.where(contagens > 0, h * c / _np.maximum(contagens, 1), 0.0)]
    rotulos = [f"{texto_do_tempo(inicio + k * passo)} a "
               f"{texto_do_tempo(inicio + (k + 1) * passo)}" for k in range(n)]
    return {"inicio": inicio, "passo": float(passo), "fim": inicio + n * float(passo),
            "passo_texto": texto_do_passo(float(passo)),
            "contagens": [int(x) for x in contagens], "h": [round(float(x), 4) for x in h],
            "pilhas": pilhas, "rotulos": rotulos, "maximo": maximo,
            "total": int(t.size), "gravacao": list(gravacao) if gravacao else None}
