"""O cabeçalho da oscilografia: uma linha por IED, os fatos alinhados.

Escolhido na maquete `maquete/cabecalho` em 21/11/2026, variante 22: com
duas ou mais oscilografias na aba o cabeçalho deixou de falar só do IED A —
cada uma é uma linha da mesma tabela, e o mesmo fato de dois relés fica um
embaixo do outro («taxa embaixo de taxa»).

    terminal      relé     taxa      falta  disparo                  alinhamento
    A SE LIRA     REL-311  2.000 Hz  AG     24/10/2026 03:00:00,145  referência
    B SE ANTARES  REL-311  2.000 Hz  AG     24/10/2026 03:00:00,170  início da falta
                                            +25,0 ms                 · +25,2 ms

    (e também formato, canais e TC · TP)

Regras da tabela, e por quê:

* **A linha é o TERMINAL** (a subestação); o nome do registro vai no hover e
  se renomeia no ✎. Com uma oscilografia só não há letra nem terminal: o
  título da página já diz.
* **Uma linha por IED**: o detalhe (amostras por ciclo, gravação bruta ou
  filtrada, a dica do tipo de falta) vai no hover. TC e TP são DOIS fatos e
  ficam lado a lado.
* **O A é a referência** e tem a linha destacada (só com mais de um IED).
* **A data do disparo aparece SEMPRE** — é ela que denuncia o relé sem GPS,
  que volta para a data de fábrica (01/01/2000). A hora é a que o arquivo
  gravou, nunca convertida. Embaixo, o Δ do disparo para o do A.
* **⚠ no relógio que não serve para comparar**: o arquivo declara «sem
  sincronismo», ou a DATA difere da do A. O texto não afirma a causa (pode
  ser GPS, fuso, ajuste manual): diz o que se vê e lembra que o alinhamento
  pelo início da falta não depende da hora.
* **Alinhamento numa coluna**: o critério e o relógio × A curto
  («início da falta · +25,2 ms»); a precisão e o por extenso no hover.

Tudo que é número sai daqui como TEXTO pronto, com vírgula decimal: o
navegador só pinta.
"""

from __future__ import annotations

from datetime import datetime

from osclab.analysis import falta as falta_mod
from osclab.plot import alinhamento

#: O nome de cada critério de alinhamento, como a tela escreve.
NOMES_DO_ALINHAMENTO = alinhamento.NOMES


def _milhar(n) -> str:
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _dec(x, casas: int) -> str:
    try:
        return f"{float(x):.{casas}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def _taxa(t) -> str:
    """`2000` → `2.000`; `959.693` → `959,693` (taxa que não fecha em inteiro)."""
    try:
        t = float(t)
    except (TypeError, ValueError):
        return "—"
    if abs(t - round(t)) < 1e-6:
        return _milhar(t)
    return f"{t:.3f}".rstrip("0").replace(".", ",")


def _instante(texto: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _data_e_hora(instante: datetime | None, texto: str) -> str:
    """«24/10/2026 03:00:00,145»: o carimbo como o arquivo gravou, ao ms."""
    if instante is None:
        return texto or "—"
    ms = instante.microsecond // 1000
    return f"{instante:%d/%m/%Y %H:%M:%S},{ms:03d}"


def _falta(item: dict) -> dict:
    """O selo da falta e o que o relé gravou, com a MESMA regra da tira de
    antes (`falta.rele_concorda`, `falta.e_tipo_de_falta`)."""
    tipo = item.get("falta_tipo") or ""
    do_rele = item.get("classificacao_do_rele") or ""
    saida = {
        "sigla": item.get("falta_sigla") or tipo or "sem falta",
        "cor": (item.get("falta_cor") or "") if tipo else "vazio",
        "trip": bool(item.get("falta_trip")),
        "confianca": item.get("falta_confianca") or "",
        "dica": item.get("falta_dica") or "",
        "rele": None,
    }
    if not do_rele:
        return saida
    tem_tipo = falta_mod.e_tipo_de_falta(do_rele)
    concorda = falta_mod.rele_concorda(tipo, item.get("falta_inicial") or "", do_rele)
    if not concorda and tipo:
        saida["rele"] = {"texto": f"relé: {do_rele}", "classe": "conflita",
                         "dica": f"O relé gravou {do_rele} no arquivo, e o OscLab leu "
                                 "outro tipo."}
    elif tipo and tem_tipo:
        saida["rele"] = {"texto": "✓ relé", "classe": "concorda",
                         "dica": f"O relé gravou {do_rele} no arquivo, o mesmo tipo. "
                                 "(Na SEL, o T solto é TRIP, não terra.)"}
    else:
        saida["rele"] = {"texto": f"relé: {do_rele}", "classe": "",
                         "dica": "O que o próprio relé gravou no arquivo." if tem_tipo else
                                 "O que o relé gravou no campo do evento — o motivo do "
                                 "relatório, não o tipo da falta."}
    return saida


def _suspeita(item: dict, instante, instante_a, e_o_a: bool) -> str:
    """Por que a hora deste IED não serve para comparar, ou ``""``."""
    relogio = (item.get("relogio") or "").lower()
    if "sem sincronismo" in relogio:
        return ("O arquivo declara o relógio SEM SINCRONISMO: a hora dele não serve "
                "para comparar com outro registro. O alinhamento pelo início da "
                "falta não depende dela.")
    if e_o_a or instante is None or instante_a is None:
        return ""
    if instante.date() != instante_a.date():
        dif = alinhamento.relogio_curto((instante - instante_a).total_seconds() * 1000.0)
        return (f"A data deste relé difere da do A ({dif}). Se ele estava sem GPS no "
                "evento, a hora do arquivo não serve para comparar — pode ser também "
                "fuso ou ajuste manual. O alinhamento pelo início da falta não "
                "depende dela.")
    return ""


def _medicao(item: dict, relacoes: list[dict] | None) -> dict:
    tc, tp = item.get("relacao_tc") or "", item.get("relacao_tp") or ""
    dica = ""
    if relacoes:
        # Com mais de uma relação («vários»), uma por EQUIPAMENTO no hover.
        dica = "\n".join(f"{r['equipamento']}: {r['tipo']} {r['relacao']}" for r in relacoes)
    elif not tc and not tp:
        dica = "O arquivo não declara relação de TC nem de TP."
    return {"tc": f"TC {tc}" if tc else "TC —", "tp": f"TP {tp}" if tp else "TP —",
            "dica": dica}


def _linha(ficha: dict, item: dict, instante_a, varios: bool,
           relacoes: list[dict] | None) -> dict:
    letra = ficha.get("letra") or "A"
    e_o_a = letra == "A"
    taxas = ficha.get("taxas_hz") or ([item["taxa_hz"]] if item.get("taxa_hz") else [])
    filtrado = (ficha.get("filtragem") or "") == "filtrado"
    texto_disparo = item.get("disparo") or item.get("inicio") or ""
    instante = _instante(texto_disparo)
    suspeita = _suspeita(item, instante, instante_a, e_o_a)

    delta = ""
    if not e_o_a and instante is not None and instante_a is not None:
        delta = alinhamento.relogio_curto((instante - instante_a).total_seconds() * 1000.0)
    data_hora = _data_e_hora(instante, texto_disparo)
    sem_disparo = ("" if item.get("disparo")
                   else "Sem disparo marcado: a hora é a do início do registro. ")
    do_a = (f"{delta} do disparo do A. " if delta
            else ("O disparo de referência. " if varios else ""))
    fuso = (f"Relógio do arquivo: {item['relogio']}" if item.get("relogio")
            else "O arquivo não diz o fuso.")
    dica_disparo = suspeita or (sem_disparo + do_a + fuso)

    nome = ficha.get("apelido") or item.get("nome") or ficha.get("arquivo") or ""
    linha = {
        "letra": letra,
        "sha": ficha.get("sha") or item.get("sha") or "",
        "referencia": e_o_a and varios,
        # A subestação; quando o arquivo não a declara (o .CEV não declara),
        # o NOME do registro — duas linhas «sem subestação» não se distinguem.
        "terminal": item.get("estacao") or nome,
        "terminal_e_nome": not item.get("estacao"),
        "nome": nome,
        "apelido": ficha.get("apelido") or "",
        "arquivo": item.get("nome_do_arquivo") or ficha.get("arquivo") or "",
        "rele": item.get("modelo") or ficha.get("rele") or "—",
        "formato": item.get("formato") or "—",
        "formato_dica": ("Gravação filtrada pelo relé: só a componente de 60 Hz." if filtrado
                         else "Gravação bruta: a onda como o conversor a mediu."),
        "taxa": f"{' / '.join(_taxa(t) for t in taxas) or '—'} Hz",
        "taxa_dica": (f"{_dec(item.get('amostras_por_ciclo'), 2)} amostras por ciclo · "
                      f"{_milhar(item.get('n_amostras'))} amostras"),
        "canais": f"{item.get('n_analogicos', '—')} an. · {item.get('n_digitais', '—')} dig.",
        "medicao": _medicao(item, relacoes),
        "falta": _falta(item),
        "disparo": {"texto": data_hora, "delta": delta, "suspeito": bool(suspeita),
                    "dica": dica_disparo},
        "alinhamento": None,
    }
    if not e_o_a:
        precisao = ficha.get("precisao_ms")
        relogio_ms = ficha.get("relogio_ms")
        linha["alinhamento"] = {
            "por": NOMES_DO_ALINHAMENTO.get(ficha.get("alinhado_por"),
                                            ficha.get("alinhado_por") or "—"),
            # O critério que VALEU, para a tela comparar com o pedido.
            "por_chave": ficha.get("alinhado_por") or "",
            "por_dica": (f"Precisão ± {_dec(precisao, 2)} ms: uma amostra do registro "
                         "mais lento." if precisao is not None else ""),
            "relogio": alinhamento.relogio_curto(relogio_ms),
            "relogio_atencao": relogio_ms is not None and abs(relogio_ms) > (precisao or 1.0),
            "relogio_dica": (f"Relógio do IED {letra} {ficha['relogio_texto']} do A, "
                             "no mesmo evento." if ficha.get("relogio_texto") else ""),
            "aviso_curto": ficha.get("aviso_curto") or "",
            "aviso": ficha.get("aviso") or "",
        }
    return linha


def montar(fichas: list[dict], itens: dict[str, dict],
           relacoes: dict[str, list[dict]] | None = None) -> dict:
    """A tabela do cabeçalho.

    `fichas` são as do pacote da janela (`varios._ficha`, A primeiro);
    `itens` são os do acervo (`Item.como_dicionario`) por sha; `relacoes`,
    por sha, as relações por equipamento quando o registro tem mais de uma.
    """
    relacoes = relacoes or {}
    varios = len(fichas) > 1
    item_a = itens.get(fichas[0].get("sha"), {}) if fichas else {}
    instante_a = _instante(item_a.get("disparo") or item_a.get("inicio") or "")
    return {
        "varios": varios,
        "linhas": [_linha(f, itens.get(f.get("sha"), {}), instante_a, varios,
                          relacoes.get(f.get("sha"))) for f in fichas],
    }
