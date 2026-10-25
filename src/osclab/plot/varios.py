"""Mais de um registro na mesma aba: IED A, IED B, IED C.

## A identidade de um sinal leva a LETRA do registro

Os sinais do IED A continuam com os ids de sempre (`c0:instantaneo`), para os
arranjos de uma aba de um registro só valerem igual. Os dos outros levam a
letra na frente, separada por `|`: `B|c0:instantaneo`, `C|q0:0:rms`, e os
digitais `B|3`. É por ela que o servidor sabe de qual registro ler, e é ela que
a tela usa para marcar o sinal com o selo do IED.

## Cada registro é montado pela conta de SEMPRE

Este módulo não refaz desenho nem leitura: ele separa o arranjo por registro,
chama `janela.montar` e `leitura.em` uma vez para cada um — o B na janela
deslocada dele (`[de + d, ate + d]`, ver `plot/alinhamento.py`) — e junta os
pedaços. Um painel que mistura IEDs recebe as séries de cada um, cada série
com o SEU vetor de tempo, já trazido para o eixo da aba; a escala vertical é
refeita sobre todas.

## Quais painéis misturam IEDs

O analógico, o digital e o espectro: em nenhum deles o número de um IED
depende do outro. Cada tira digital e cada série analógica leva o SEU vetor de
tempo; o espectro é, em cada sinal, percentual da fundamental DELE.

O fasorial, o complexo, o plano alfa, o de impedância e o diferencial
comparam ÂNGULO entre sinais, e entre dois registros o ângulo só vale tanto
quanto o alinhamento: uma amostra a 1000 Hz são 21,6°. Neles entram só os
sinais do A, até haver um alinhamento mais fino que uma amostra.

## Memória

Cada registro é lido do acervo no pedido, usado e solto; nada fica guardado
entre pedidos. Os pedaços montados por registro são descartados assim que o
pacote final sai.
"""

from __future__ import annotations

from dataclasses import replace

from osclab.formats.base import Record
from osclab.plot import alinhamento, escala, paineis

#: As letras dos IEDs, na ordem em que entram na aba.
LETRAS = ("A", "B", "C")
MAXIMO_DE_REGISTROS = 3
SEPARADOR = "|"


def letra_de(identidade: str) -> tuple[str, str]:
    """`B|c0:instantaneo` → `("B", "c0:instantaneo")`; sem letra, é o A."""
    if SEPARADOR in identidade:
        letra, resto = identidade.split(SEPARADOR, 1)
        if letra in LETRAS:
            return letra, resto
    return "A", identidade


def com_letra(letra: str, identidade: str) -> str:
    return identidade if letra == "A" else f"{letra}{SEPARADOR}{identidade}"


# ---------------------------------------------------------------------------
# O arranjo
# ---------------------------------------------------------------------------

#: Os tipos de painel que aceitam sinais de mais de um registro.
TIPOS_MISTURAVEIS = (paineis.ANALOGICO, paineis.DIGITAL, paineis.HARMONICOS)


def padrao(registros: list[tuple[str, Record]], lado: str = "arquivo") -> list:
    """O arranjo de abertura de uma aba com vários registros.

    Um conjunto por IED, como cada um abriria sozinho: os gráficos analógicos
    do A, depois os do B, …, e no fim um painel digital por IED. Escolha
    dele, 22/10/2026 (maquete «abas»).
    """
    analogicos, digitais = [], []
    for letra, registro in registros:
        for painel in paineis.padrao(registro, lado):
            novo = replace(painel,
                           id=painel.id if letra == "A" else f"{letra}{painel.id}",
                           sinais=tuple(com_letra(letra, s) for s in painel.sinais))
            (digitais if painel.tipo == paineis.DIGITAL else analogicos).append(novo)
    return analogicos + digitais


def separar(layout: list, letra: str) -> list:
    """Os painéis do arranjo com SÓ os sinais do registro `letra`, sem a letra.

    Todo painel entra — vazio quando não tem sinal daquele registro —, para os
    ids casarem na hora de juntar. Painel que não mistura registros só entra
    no A.
    """
    saida = []
    for painel in layout:
        if letra != "A" and painel.tipo not in TIPOS_MISTURAVEIS:
            continue
        meus = tuple(resto for s in painel.sinais
                     for de_quem, resto in [letra_de(s)] if de_quem == letra)
        saida.append(replace(painel, sinais=meus))
    return saida


# ---------------------------------------------------------------------------
# Juntar os pedaços
# ---------------------------------------------------------------------------

def _deslocar(valores, d: float) -> list:
    """Do tempo do registro para o tempo da aba: menos o deslocamento."""
    return [round(float(t) - d, 9) for t in valores]


def _sinais_de(letra: str, pedaco: dict, tempo: list, d: float) -> list:
    saida = []
    for s in pedaco.get("sinais") or []:
        novo = dict(s)
        novo["id"] = com_letra(letra, s["id"])
        novo["id_efetivo"] = com_letra(letra, s.get("id_efetivo") or s["id"])
        novo["ied"] = letra
        novo["tempo"] = tempo
        novo["picos"] = _deslocar(s.get("picos") or [], d)
        novo["zeros"] = _deslocar(s.get("zeros") or [], d)
        saida.append(novo)
    return saida


def _juntar_analogico(base: dict, letra: str, pedaco: dict, tempo: list,
                      d: float, apelido: str) -> None:
    """Põe no painel `base` (já montado) os sinais do `pedaco` de outro IED.

    O eixo: mesma unidade, mesmo lado; unidade nova vai para a direita se ela
    estiver livre; uma terceira é recusada, como num painel de um registro só.
    A faixa de cada eixo é refeita sobre os dois.
    """
    novos = _sinais_de(letra, pedaco, tempo, d)
    if not novos:
        return
    if not base.get("sinais"):
        # Painel só com sinais deste IED: herda o eixo dele inteiro.
        for chave in ("unidade", "unidade_do_arquivo", "minimo", "maximo",
                      "marcacoes", "casas", "eixo_dir"):
            base[chave] = pedaco.get(chave)
        if base.get("do_padrao"):
            base["nome"] = pedaco.get("nome") or base.get("nome")
        base["sinais"] = novos
        base["rodape"] = [f"IED {letra}: {x}" for x in pedaco.get("rodape") or []]
        base["avisos"] = list(base.get("avisos") or []) + list(pedaco.get("avisos") or [])
        return

    faixas = {"esq": [base["minimo"], base["maximo"]]}
    if base.get("eixo_dir"):
        faixas["dir"] = [base["eixo_dir"]["minimo"], base["eixo_dir"]["maximo"]]
    unidades = {"esq": base.get("unidade_do_arquivo"),
                "dir": (base.get("eixo_dir") or {}).get("unidade_do_arquivo")}
    dele = {"esq": (pedaco.get("unidade_do_arquivo"), pedaco.get("minimo"),
                    pedaco.get("maximo"), pedaco.get("unidade")),
            "dir": ((pedaco.get("eixo_dir") or {}).get("unidade_do_arquivo"),
                    (pedaco.get("eixo_dir") or {}).get("minimo"),
                    (pedaco.get("eixo_dir") or {}).get("maximo"),
                    (pedaco.get("eixo_dir") or {}).get("unidade"))}
    avisos = list(base.get("avisos") or [])
    for s in novos:
        unidade, minimo, maximo, mostrada = dele[s["eixo"]]
        if unidade == unidades["esq"]:
            eixo = "esq"
        elif unidades["dir"] in (None, unidade):
            eixo = "dir"
            if unidades["dir"] is None:
                unidades["dir"] = unidade
                faixas["dir"] = [minimo, maximo]
                base["eixo_dir"] = {"unidade": mostrada, "unidade_do_arquivo": unidade,
                                    "minimo": minimo, "maximo": maximo,
                                    "marcacoes": [], "casas": 0}
        else:
            avisos.append(f"{s['sinal']} (IED {letra}) não cabe: o gráfico já "
                          "tem dois eixos.")
            continue
        faixas[eixo] = [min(faixas[eixo][0], minimo), max(faixas[eixo][1], maximo)]
        s["eixo"] = eixo
        base["sinais"].append(s)

    base_, topo = escala.faixa(*faixas["esq"])
    base.update(minimo=base_, maximo=topo,
                marcacoes=escala.marcacoes(base_, topo, alvo=4),
                casas=escala.casas_decimais(topo - base_))
    if "dir" in faixas and base.get("eixo_dir"):
        b2, t2 = escala.faixa(*faixas["dir"])
        base["eixo_dir"].update(minimo=b2, maximo=t2,
                                marcacoes=escala.marcacoes(b2, t2, alvo=4),
                                casas=escala.casas_decimais(t2 - b2))
    base["avisos"] = avisos
    base["rodape"] = list(base.get("rodape") or []) + [
        f"IED {letra} ({apelido}): {x}" for x in pedaco.get("rodape") or []]


def _juntar_digital(base: dict, letra: str, pedaco: dict, tempo: list,
                    d: float) -> None:
    """Põe no painel digital `base` as tiras de outro IED.

    Cada tira do outro IED leva o SEU vetor de colunas (`tempo`), já no eixo
    da aba: as colunas de dois registros de taxas diferentes não caem nos
    mesmos instantes, e uma tira desenhada no tempo da outra ficaria
    deslocada sem nada denunciar.
    """
    tiras = pedaco.get("tiras") or []
    for tira in tiras:
        # O id da tira com a letra: é por ele que a tela a tira do painel e a
        # seleciona. O `indice` continua sendo o do canal no registro dele.
        tira["id"] = com_letra(letra, str(tira["indice"]))
        tira["ied"] = letra
        tira["tempo"] = tempo
        tira["transicoes"] = _deslocar(tira.get("transicoes") or [], d)
    base["tiras"] = list(base.get("tiras") or []) + tiras
    base["sinais_pedidos"] = list(base.get("sinais_pedidos") or []) + [
        com_letra(letra, x) for x in pedaco.get("sinais_pedidos") or []]


def montar_janela(base: Record, outros: list, *, alinhar: str, montar,
                  apelido_a: str = "", sha_a: str = "", **kw) -> dict:
    """O pacote de uma janela com vários registros.

    `outros` é `[(registro, apelido, sha)]`, na ordem B, C. `montar` é
    `janela.montar` (passado por quem chama, para este módulo não depender
    dele e para o teste poder trocá-lo). `kw` vai igual para cada chamada.
    """
    registros = [("A", base)] + [(LETRAS[k + 1], r) for k, (r, _, _) in
                                 enumerate(outros[:MAXIMO_DE_REGISTROS - 1])]
    layout = kw.pop("layout", None)
    if layout is None:
        layout = padrao(registros, kw.get("lado", "arquivo"))

    # Os deslocamentos ANTES do A: o plano alfa do A precisa deles para pôr
    # o terminal remoto, que mora noutro registro, no tempo da aba.
    deslocs = {letra: alinhamento.deslocamento(base, registro, alinhar)
               for letra, registro in registros[1:]}
    pacote = montar(base, layout=separar(layout, "A"),
                    outros=[(letra, registro, deslocs[letra])
                            for letra, registro in registros[1:]], **kw)
    de, ate = pacote["de"], pacote["ate"]
    por_id = {p["id"]: p for p in pacote["paineis"]}
    ieds = []
    for letra, registro in registros[1:]:
        k = LETRAS.index(letra) - 1
        _, apelido, sha = outros[k]
        desl = deslocs[letra]
        d = desl["d"]
        sub = dict(kw)
        sub.pop("ajustes", None)
        # As contas do usuário falam dos canais do A; levá-las ao B daria
        # sinais com o nome certo e o canal errado.
        sub["contas"] = None
        pedaco = montar(registro, layout=separar(layout, letra),
                        **{**sub, "de": de + d, "ate": ate + d})
        tempo = _deslocar(pedaco.get("tempo") or [], d)
        tempo_dig = _deslocar(pedaco.get("tempo_digitais") or [], d)
        for p in pedaco["paineis"]:
            alvo = por_id.get(p["id"])
            if alvo is None:
                continue
            if p.get("tipo") == paineis.DIGITAL:
                _juntar_digital(alvo, letra, p, tempo_dig, d)
            elif p.get("tipo") == paineis.HARMONICOS:
                # O espectro é por sinal, em % da fundamental DELE: juntar é
                # só pôr os sinais do outro IED na lista, com a letra.
                for s in p.get("sinais") or []:
                    alvo.setdefault("sinais", []).append(
                        {**s, "id": com_letra(letra, s["id"]), "ied": letra})
            elif p.get("tipo") == paineis.ANALOGICO:
                _juntar_analogico(alvo, letra, p, tempo, d, apelido)
        for x in pedaco.get("catalogo") or []:
            novo = dict(x)
            novo["id"] = com_letra(letra, x["id"])
            novo["efetivo"] = {m: com_letra(letra, v)
                               for m, v in (x.get("efetivo") or {}).items()}
            novo["ied"] = letra
            pacote["catalogo"].append(novo)
        # Os digitais do B entram na busca dos digitais com a letra.
        for x in pedaco.get("digitais_disponiveis") or []:
            pacote["digitais_disponiveis"].append({**x, "ied": letra})
        ieds.append(_ficha(letra, registro, apelido, sha, desl))
        pacote["limite_de"] = min(pacote["limite_de"], float(registro.time[0]) - d)
        pacote["limite_ate"] = max(pacote["limite_ate"], float(registro.time[-1]) - d)
        del pedaco
    for x in pacote["catalogo"]:
        x.setdefault("ied", "A")
    for x in pacote["digitais_disponiveis"]:
        x.setdefault("ied", "A")
    # O nome dos gráficos do padrão leva o IED quando ele é de um só: «Correntes
    # (kA) · IED B». O que mistura IEDs fica com o nome da unidade.
    for p in pacote["paineis"]:
        if not p.get("do_padrao") or p.get("tipo") not in TIPOS_MISTURAVEIS:
            continue
        if p.get("tipo") == paineis.DIGITAL:
            letras = {t.get("ied") or "A" for t in p.get("tiras") or []}
        else:
            letras = {s.get("ied") or "A" for s in p.get("sinais") or []}
        if len(letras) == 1:
            p["nome"] = f"{p.get('nome') or ''} · IED {letras.pop()}".strip()
    pacote["ieds"] = [_ficha("A", base, apelido_a, sha_a, None)] + ieds
    pacote["alinhar"] = alinhar
    return pacote


def _ficha(letra: str, registro: Record, apelido: str, sha: str, desl) -> dict:
    """A linha do IED na tira de fatos."""
    taxas = sorted({round(t.taxa_hz) for t in registro.trechos if t.taxa_hz > 0})
    ficha = {
        "letra": letra,
        "sha": sha,
        "apelido": apelido or "",
        "arquivo": str(getattr(registro.source, "stem", "") or ""),
        "rele": registro.device_id or "",
        "taxas_hz": taxas,
        "falta_s": alinhamento.instante_da_falta(registro),
    }
    if desl is not None:
        ficha.update({
            "deslocamento_ms": round(desl["d"] * 1000.0, 3),
            "alinhado_por": desl["por"],
            "precisao_ms": desl["precisao_ms"],
            "relogio_ms": desl["relogio_ms"],
        })
    return ficha


def mesclar_leitura(base: dict, letra: str, outra: dict) -> None:
    """Põe na leitura do A as linhas do outro registro, com a letra no id."""
    for k, cursor in enumerate(outra.get("cursores") or []):
        if cursor is None or k >= len(base.get("cursores") or []):
            continue
        alvo = base["cursores"][k]
        if alvo is None:
            continue
        for identidade, linha in (cursor.get("sinais") or {}).items():
            alvo["sinais"][com_letra(letra, identidade)] = {**linha, "ied": letra}
    if base.get("entre") and outra.get("entre"):
        for identidade, linha in (outra["entre"].get("sinais") or {}).items():
            base["entre"]["sinais"][com_letra(letra, identidade)] = linha
    # O espectro do TRECHO entre os cursores, para o painel de espectro.
    if (base.get("espectro_entre") and outra.get("espectro_entre")
            and isinstance(base["espectro_entre"].get("sinais"), dict)):
        for identidade, linha in (outra["espectro_entre"].get("sinais") or {}).items():
            base["espectro_entre"]["sinais"][com_letra(letra, identidade)] = linha


def ler(base: Record, outros: list, pedidos: list, *, alinhar: str, ler,
        layout, **kw) -> dict:
    """A leitura dos cursores com vários registros.

    O A é lido como sempre. Cada outro é lido no instante em que o cursor
    caiu NO A, mais o deslocamento dele — cada um na amostra mais próxima do
    PRÓPRIO registro, sem interpolar. `ler` é `leitura.em`.
    """
    registros = [("A", base)] + [(LETRAS[k + 1], r) for k, (r, _, _) in
                                 enumerate(outros[:MAXIMO_DE_REGISTROS - 1])]
    if layout is None:
        layout = padrao(registros, kw.get("lado", "arquivo"))
    resultado = ler(base, pedidos, layout=separar(layout, "A"), **kw)
    sub = {**kw, "refere": None, "contas": None}
    for letra, registro in registros[1:]:
        d = alinhamento.deslocamento(base, registro, alinhar)["d"]
        instantes = [((c["t"] + d) if c else None, 0, 0.0)
                     for c in resultado.get("cursores") or []]
        outra = ler(registro, instantes, layout=separar(layout, letra), **sub)
        mesclar_leitura(resultado, letra, outra)
    return resultado
