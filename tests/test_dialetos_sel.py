"""Os dois dialetos SEL que o banco de oscilografias do parque revelou
(24/10/2026), em arquivos SINTÉTICOS — nada de registro real no repositório.

1. O `.CEV` do SEL-311C: identificação em DUAS linhas (`"FID",<soma>` e
   `"FID=SEL-311C-…",<soma>`), sem RID nem SID; correntes sem unidade no
   título (`"IA"`); sem `PRIM_VAL`.
2. O relatório de evento em TEXTO do SEL-321, salvo como `.CEV`.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from osclab.formats import ajustes, registry


def _soma(linha_sem_soma: str) -> str:
    return f'{linha_sem_soma}"{sum(linha_sem_soma.encode("latin-1")) % 0x10000:04X}"'


def _cev_311c(caminho, por_ciclo=4, ciclos=4, diferencial=False):
    """Um CEV de 311C: IA pico 100·√2 eficaz=100 A em A, VA 60 kV eficaz."""
    linhas = [_soma('"FID",'), _soma('"FID=SEL-311C-1-R508-V1-Z104101-D20170818",'),
              _soma('"MONTH","DAY","YEAR","HOUR","MIN","SEC","MSEC",'),
              _soma("7,24,2026,20,2,57,549,"),
              _soma('"FREQ","SAM/CYC_A","SAM/CYC_D","NUM_OF_CYC","EVENT","LOCATION","IA","IB","IC",'),
              _soma(f'60.00,{por_ciclo},4,{ciclos},"AG T",5.10,100,20,20,'),
              _soma('"IA","IB","IC",' + ('"IAL","IAY",' if diferencial else '')
                    + '"VA(kV)","VB(kV)","VC(kV)","TRIG","TRIP 51G",')]
    n = por_ciclo * ciclos
    for k in range(n):
        fase = 2 * math.pi * k / por_ciclo
        # A amostra do CEV é ESCALADA no eficaz: o pico da senoide é o eficaz.
        giro = 2 * math.pi / 3
        ia, ib, ic = (100 * math.cos(fase), 20 * math.cos(fase - giro),
                      20 * math.cos(fase + giro))
        va, vb, vc = (60 * math.cos(fase), 60 * math.cos(fase - giro),
                      60 * math.cos(fase + giro))
        trig = '">"' if k == por_ciclo else '" "'
        bits = "C0" if k >= por_ciclo else "00"
        extra = f"{ia:.3f},-99999," if diferencial else ""
        linhas.append(_soma(f'{ia:.3f},{ib:.3f},{ic:.3f},{extra}{va:.3f},{vb:.3f},{vc:.3f},'
                            f'{trig},"{bits}",'))
    linhas.append(_soma('"SETTINGS",'))
    linhas.append('"RID =LT EXEMPLO   Z1MAG = 0.80   Z1ANG = 68.84",')
    caminho.write_text("\n".join(linhas) + "\n", encoding="latin-1")
    return caminho


def test_cev_do_311l_le_os_canais_do_diferencial_em_ampere(tmp_path):
    """`IAL`, `IAY`… vêm sem unidade como o `IA`; sem ela ficavam sem o ×√2.
    E o `-99999` de terminal sem fibra é ausência, não −99 999 A."""
    r = registry.read(_cev_311c(tmp_path / "l.CEV", diferencial=True))
    canais = {c.name: c for c in r.analog_channels}
    assert canais["IAL"].unit == "A"
    ial = r.analog[canais["IAL"].index]
    assert np.nanmax(ial) == pytest.approx(100 * math.sqrt(2), rel=1e-3)
    assert not np.isfinite(r.analog[canais["IAY"].index]).any()


def test_cev_do_311c_e_lido(tmp_path):
    r = registry.read(_cev_311c(tmp_path / "exemplo.CEV"))
    assert r.format_name == "cev"
    assert r.device_id.startswith("FID=SEL-311C")
    canais = {c.name: c for c in r.analog_channels}
    # Corrente sem unidade no título vira ampère; a tensão em kV diz primário.
    assert canais["IA"].unit == "A" and canais["IA"].is_primary
    assert canais["VA"].unit == "kV"
    # A amostra eficaz vira instantânea: pico = 100·√2.
    assert np.nanmax(r.analog[0]) == pytest.approx(100 * math.sqrt(2), rel=1e-3)
    assert r.classificacao_do_rele == "AG T"
    assert [c.name for c in r.status_channels] == ["TRIP", "51G"]
    assert r.status[0, -1] == 1 and r.status[0, 0] == 0


def test_cev_do_311c_traz_os_ajustes(tmp_path):
    c = _cev_311c(tmp_path / "exemplo.CEV")
    lidos = ajustes.do_registro(tmp_path, [c.name])
    assert dict(lidos["ajustes"]).get("Z1MAG") == "0.80"


RELATORIO_321 = """

LT EXEMPLO                              Date: 04/15/24    Time: 18:18:08.455

FID=SEL-321-1-R422-V000000pb-D990415

    CURRENTS (pri)             VOLTAGES (kV pri)     RELAY ELEMENTS  OUT   IN

                                                    ZZZZZZO  555566L 1357 1357
                                                    ABCABCO 3111077O &&&& &&&&
   IR     IA     IB     IC     VA      VB      VC   BCAGGGS 2NQPPNQP 2468 2468

     0    100      0   -100    60.0   -30.0   -30.0 ....... ........ .... 1...
     0      0     87    -87     0.0    52.0   -52.0 ....... ........ .... 1...
     0   -100      0    100   -60.0    30.0    30.0 ....... ........ .... 1...
     0      0    -87     87     0.0   -52.0    52.0 ....... ........ .... 1...

   900   1000      0   -100    20.0   -30.0   -30.0 ...2... .N...... 2... 1...
     0      0     87    -87     0.0    52.0   -52.0 ...2... .N...... 2... 1...
  -900  -1000      0    100   -20.0    30.0    30.0 ...2... .N...... 2... 1...
     0      0    -87     87     0.0   -52.0    52.0 ...2... .N...... 2... 1...


Event:  AG    Location:   +6.05    Frequency:    60.0

Targets: INST EN G                  V1 Mem:    78.9 / 244

GROUP 1

RELID =SEL-321
Z1MAG = 0.67    Z1ANG = 76.10   Z0MAG = 2.68    Z0ANG = 78.80
LL    = 10.40   CTR   = 160.0   PTR   = 1200.0
"""


def test_relatorio_de_texto_do_321(tmp_path):
    caminho = tmp_path / "SEL-321 - AG.CEV"
    caminho.write_text(RELATORIO_321, encoding="latin-1")
    r = registry.read(caminho)
    assert r.format_name == "sel-texto"
    assert r.station == "LT EXEMPLO"
    assert r.device_id == "FID=SEL-321-1-R422-V000000pb-D990415"
    assert [c.name for c in r.analog_channels] == ["IR", "IA", "IB", "IC", "VA", "VB", "VC"]
    assert r.trechos[0].taxa_hz == 240.0          # quatro amostras por ciclo
    nomes = [c.name for c in r.status_channels]
    # O nome do elemento é a coluna lida na VERTICAL.
    assert nomes[:7] == ["ZAB", "ZBC", "ZCA", "ZAG", "ZBG", "ZCG", "OOS"]
    assert nomes[7:15] == ["32", "51N", "51Q", "51P", "50P", "67N", "67Q", "LOP"]
    assert "OUT1&2" in nomes and "IN1&2" in nomes
    zag = nomes.index("ZAG")
    assert r.status[zag, 0] == 0 and r.status[zag, -1] == 1
    assert r.classificacao_do_rele == "AG"
    assert any("6.05" in x for x in r.relatos)
    # Eficaz → instantâneo.
    assert np.nanmax(r.analog[1]) == pytest.approx(1000 * math.sqrt(2))
    assert r.start_time.year == 2024 and r.start_time.month == 4 and r.start_time.day == 15


def test_relatorio_de_texto_traz_os_ajustes(tmp_path):
    caminho = tmp_path / "SEL-321 - AG.CEV"
    caminho.write_text(RELATORIO_321, encoding="latin-1")
    lidos = dict(ajustes.do_registro(tmp_path, [caminho.name])["ajustes"])
    assert lidos.get("Z1MAG") == "0.67" and lidos.get("LL") == "10.40"
    assert lidos.get("CTR") == "160.0"


def test_cev_comum_continua_do_leitor_cev(tmp_path):
    """O dialeto novo não pode roubar o CEV de sempre (451)."""
    p = tmp_path / "x.CEV"
    p.write_text('"FID","RID","SID","03E2"\n', encoding="latin-1")
    leitor = registry.reader_for(p)
    assert leitor.name == "cev"


def test_relatorio_321_sem_a_linha_em_branco_ainda_separa_out_de_in(tmp_path):
    """A linha `OUT IN` era lida numa posição fixa (quatro acima dos títulos):
    sem a linha em branco no meio, o prefixo sumia e `OUT1&2` e `IN1&2`
    viravam o mesmo nome."""
    texto = RELATORIO_321.replace("OUT   IN\n\n", "OUT   IN\n", 1)
    assert texto != RELATORIO_321
    caminho = tmp_path / "SEL-321 - AG.CEV"
    caminho.write_text(texto, encoding="latin-1")
    nomes = [c.name for c in registry.read(caminho).status_channels]
    assert "OUT1&2" in nomes and "IN1&2" in nomes
