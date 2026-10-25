"""Vários registros na mesma aba: onde cada um cai no tempo do primeiro.

## O eixo da aba é o tempo do IED A

O primeiro registro da aba (o IED A) não se move: o eixo da tela é o tempo
dele. Cada outro registro ganha um DESLOCAMENTO `d`, em segundos, e um instante
`t` do eixo da aba cai, no registro dele, em `t + d`.

## Três jeitos de achar o `d`

* `falta` — o padrão: o início da perturbação de cada um no mesmo instante.
  Sai de `analysis/falta.instante_da_falta`, que é o detector superposto do
  classificador. É o que alinha dois terminais de uma linha, mesmo com os
  relógios dos relés em desacordo.
* `disparo` — o gatilho de cada um no mesmo instante. Serve quando os relés
  disparam pela mesma lógica.
* `hora` — o carimbo de tempo de cada arquivo. Mostra a diferença de relógio
  entre os relés tal como ela é.

Sem falta detectada num dos registros, ele cai para o disparo; sem disparo,
para a hora — e a tira diz qual valeu.

## A precisão é de UMA AMOSTRA, e isso vai escrito

Alinhar pelo instante da falta acerta a amostra, não menos: a 1000 Hz, 1 ms.
Serve para OLHAR — comparar as formas, ver quem disparou antes —, e não para
calcular fasor entre dois registros: 1 ms são 21,6° a 60 Hz. Ver o CLAUDE.md,
«Alinhar registros pelo instante da falta tem precisão de uma amostra».

## Para alinhar pela HORA, os dois carimbos vão para o UTC

No parque o SEL-421 carimba em UTC e o SIPROTEC em hora local (`time_code`
−4). A tela continua MOSTRANDO a hora como cada arquivo escreveu — ver o
CLAUDE.md, «O fuso do COMTRADE: mostrar, nunca converter» —, mas para
comparar dois arquivos pela hora cada carimbo é levado ao UTC pelo fuso que o
PRÓPRIO arquivo declara. Sem fuso declarado num deles, a hora é comparada
como está e o alinhamento não afirma precisão nenhuma.

## A diferença de relógio aparece SEMPRE

Qualquer que seja o alinhamento escolhido, a tira mostra quanto o relógio de
cada registro difere do A no mesmo evento: a hora absoluta do início da falta
num menos no outro. Alinhar pela falta não apaga essa diferença — ela é
informação sobre a sincronização dos relés.
"""

from __future__ import annotations

from datetime import timedelta

from osclab.analysis import falta as falta_mod
from osclab.formats import conjuntos
from osclab.formats.base import Record

#: Os modos, na ordem do botão. O primeiro é o padrão.
MODOS = ("falta", "disparo", "hora")
NOMES = {"falta": "início da falta", "disparo": "disparo",
         "hora": "hora do arquivo"}


def instante_da_falta(registro: Record) -> float | None:
    """O início da perturbação, em segundos do próprio registro, ou `None`."""
    achados = [c for c in conjuntos.de_registro(registro)
               if c.grandeza == "I" and not c.sem_sinal]
    if not achados:
        return None
    i = falta_mod.instante_da_falta(registro, achados[0].canais)
    if i is None or not (0 <= i < registro.time.size):
        return None
    return float(registro.time[i])


def instante_do_disparo(registro: Record) -> float | None:
    """O disparo, em segundos do próprio registro, ou `None`."""
    if registro.trigger_time is None or registro.start_time is None:
        return None
    return (registro.trigger_time - registro.start_time).total_seconds()


def _referencia(registro: Record, modo: str) -> float | None:
    if modo == "falta":
        return instante_da_falta(registro)
    if modo == "disparo":
        return instante_do_disparo(registro)
    return 0.0 if registro.start_time is not None else None


def _inicio_utc(registro: Record):
    """O início do registro em UTC, quando o fuso é declarado; senão, cru."""
    if registro.start_time is None:
        return None
    fuso = registro.fuso_horas
    return registro.start_time - timedelta(hours=fuso or 0.0)


def fuso_declarado(*registros: Record) -> bool:
    return all(r.fuso_horas is not None for r in registros)


def _hora_absoluta(registro: Record, segundos: float | None):
    inicio = _inicio_utc(registro)
    if segundos is None or inicio is None:
        return None
    return inicio.timestamp() + segundos


def amostra_ms(registro: Record) -> float:
    """O intervalo entre amostras, em ms — a menor taxa entre os trechos."""
    taxas = [t.taxa_hz for t in registro.trechos if t.taxa_hz > 0]
    taxa = min(taxas) if taxas else float(registro.base_rate_hz or 0.0)
    return 1000.0 / taxa if taxa > 0 else 0.0


def deslocamento(base: Record, outro: Record, modo: str) -> dict:
    """Quanto `outro` desloca em relação a `base`, e por qual critério.

    Devolve `{"d": s, "por": modo usado, "precisao_ms": …, "relogio_ms": …}`.
    `d` é tal que o instante `t` da aba cai em `t + d` no `outro`.
    """
    modo = modo if modo in MODOS else MODOS[0]
    usado = None
    d = 0.0
    for tentativa in MODOS[MODOS.index(modo):] + MODOS[:MODOS.index(modo)]:
        if tentativa == "hora":
            if base.start_time is None or outro.start_time is None:
                continue
            # Os DOIS no UTC, cada um pelo fuso que declarou.
            d = (_inicio_utc(base) - _inicio_utc(outro)).total_seconds()
            usado = "hora"
            break
        ref_base = _referencia(base, tentativa)
        ref_outro = _referencia(outro, tentativa)
        if ref_base is None or ref_outro is None:
            continue
        d = ref_outro - ref_base
        usado = tentativa
        break

    # A diferença de RELÓGIO: a hora absoluta do mesmo evento nos dois. O
    # evento é o início da falta quando os dois o têm; senão, o disparo.
    relogio = None
    for evento in (instante_da_falta, instante_do_disparo):
        a = _hora_absoluta(base, evento(base))
        b = _hora_absoluta(outro, evento(outro))
        if a is not None and b is not None:
            relogio = round((b - a) * 1000.0, 3)
            break

    # Pela hora, a precisão é a do sincronismo dos relógios — não há número
    # a dar. Pelos outros, uma amostra do registro mais lento.
    precisao = (None if usado == "hora"
                else round(max(amostra_ms(base), amostra_ms(outro)), 3))
    return {"d": float(d), "por": usado or "nenhum", "precisao_ms": precisao,
            "relogio_ms": relogio, "fuso_declarado": fuso_declarado(base, outro)}


# ---------------------------------------------------------------------------
# O relógio, e quanto de ÂNGULO o alinhamento sustenta
# ---------------------------------------------------------------------------

#: O erro de relógio de cada frase que o leitor COMTRADE escreve a partir do
#: `tmq_code` da norma (ver `formats/comtrade._QUALIDADE_DO_RELOGIO`). «Travado,
#: operação normal» não diz o número; 1 µs é o que um GPS entrega.
_ERRO_DO_RELOGIO = (
    ("relógio travado", 1e-6), ("abaixo de 1 ns", 1e-9), ("abaixo de 10 ns", 1e-8),
    ("abaixo de 100 ns", 1e-7), ("abaixo de 1 µs", 1e-6), ("abaixo de 10 µs", 1e-5),
    ("abaixo de 100 µs", 1e-4), ("abaixo de 1 ms", 1e-3), ("abaixo de 10 ms", 1e-2),
    ("abaixo de 100 ms", 1e-1), ("abaixo de 1 s", 1.0), ("abaixo de 10 s", 10.0),
)


def erro_do_relogio(registro: Record) -> float | None:
    """O erro do relógio declarado no arquivo, em segundos, ou `None`.

    `None` quando o arquivo não diz nada ou diz que o relógio estava sem
    sincronismo — e aí a hora do arquivo não serve para alinhar ângulo.
    """
    texto = (registro.time_quality or "").lower()
    if not texto or "sem sincronismo" in texto:
        return None
    for frase, erro in _ERRO_DO_RELOGIO:
        if frase in texto:
            return erro
    return None


def incerteza_em_graus(base: Record, outro: Record, desl: dict) -> float | None:
    """Quanto o ângulo ENTRE os dois registros pode estar errado, em graus.

    Pela hora, com os dois relógios sincronizados: o erro dos dois relógios
    somado. Pelos outros modos: uma amostra do registro mais lento. A conta é
    `360° × f × erro de tempo`. `None` quando nem isso se sabe.
    """
    f = float(base.line_frequency or 60.0)
    if desl.get("por") == "hora":
        # Sem o fuso dos dois, a hora não se compara com segurança: nada de
        # afirmar sincronismo.
        if not fuso_declarado(base, outro):
            return None
        a, b = erro_do_relogio(base), erro_do_relogio(outro)
        if a is None or b is None:
            return None
        return 360.0 * f * (a + b)
    if desl.get("precisao_ms") is None:
        return None
    return 360.0 * f * desl["precisao_ms"] / 1000.0


def fabricante(registro: Record) -> str:
    """O fabricante, pelo que o arquivo diz de si mesmo, ou `""`."""
    texto = " ".join([registro.device_id or "", registro.station or "",
                      registro.format_name or ""]).upper()
    for nome, pistas in (("SEL", ("SEL-", "SEL ", "CEV")),
                         ("Siemens", ("SIPROTEC", "SIEMENS", "7UT", "7SA", "7SJ")),
                         ("GE", ("MULTILIN", "T60", "L90", "D60", " GE ")),
                         ("ABB", ("ABB", "RET6", "REF6", "RED6", "REL6")),
                         ("Schneider", ("MICOM", "SCHNEIDER", "P63", "P54", "P44")),
                         ("Ingeteam", ("INGETEAM", "INGEPAC"))):
        if any(p in f" {texto} " for p in pistas):
            return nome
    return ""
