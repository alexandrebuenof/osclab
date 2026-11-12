"""O painel «localizador de faltas»: o número do relé e o arrumador do painel.

A conta dos métodos é a de `faultloc/ldl.py` e tem os testes dela
(`test_ldl.py`); aqui se testa o que é deste painel — ler a distância que o
PRÓPRIO relé calculou, em cada formato do parque, e entregar à tela tudo em
km e em % da linha, porque o JavaScript não decide número.
"""

from __future__ import annotations

import pytest

from osclab import paths
from osclab.faultloc import ldl, rele
from osclab.library import acervo
from osclab.plot import localizador, paineis
from tests.fabrica import escrever_cev
from tests.test_ldl import LINHA, _rede, _registro

# ---------------------------------------------------------------------------
# O número do relé, formato por formato (levantado no banco em 09/11/2026)
# ---------------------------------------------------------------------------


def _cev(campos: dict, ajustes: str = "") -> str:
    nomes = ",".join(f'"{n}"' for n in campos)
    valores = ",".join(campos.values())
    return ('"FID","RID","SID","1234"\n"FID=SEL-421-R100"\n"MONTH","DAY","YEAR"\n11,5,2026\n'
            f"{nomes}\n{valores}\n" + ajustes)


def test_sel_cev_le_o_location_sem_unidade_e_diz_que_presumiu():
    achado = rele.do_cev(_cev({"EVENT_NUM": "1", "EVENT": '"BG T"', "LOCATION": "14.63"},
                              "LL      = 137.00\n"), "x.cev")
    assert (achado.valor, achado.campo, achado.unidade, achado.presumido) == \
        (14.63, "LOCATION", None, True)
    assert achado.km == 14.63


def test_sel_411l_prefere_o_baseado_em_impedancia_e_le_a_milha():
    """O 411L não tem LOCATION; o valor vem com `(SE)` e, às vezes, com a unidade."""
    achado = rele.do_cev(_cev({"EVENT": '"ABC"', "FLM": '"SE"', "TW_LOCATION": '"$$$$.$$(mi)"',
                               "Z_BASED_LOCATION": '"305.08(SE)"'}))
    assert (achado.valor, achado.campo, achado.unidade) == (305.08, "Z_BASED_LOCATION", None)
    em_milha = rele.do_cev(_cev({"Z_BASED_LOCATION": '"10.00(mi)"'}))
    assert em_milha.unidade == "mi" and em_milha.km == pytest.approx(16.09344)
    pelo_ajuste = rele.do_cev(_cev({"Z_BASED_LOCATION": '"10.00(SE)"'}, 'LLUNIT  := "MI"\n'))
    assert pelo_ajuste.unidade == "mi"


def test_sem_distancia_calculada_nao_ha_numero():
    """`$$$$.$$` é o relé dizendo que não calculou: ausência, nunca zero."""
    assert rele.do_cev(_cev({"EVENT": '"AB T"', "LOCATION": "$$$$.$$"})) is None
    sem = "15 | 20:11:36 | 0.884 | 004.022 FT_DA Fault location | Not measured"
    assert rele.do_texto(sem) is None


def test_hdr_da_sel_e_do_411l_e_do_twfl():
    sel = "Event: BC                Location:  -12.76     Time Source: OTHER"
    assert rele.do_texto(sel).valor == -12.76
    z = rele.do_texto("TW Location: $$$$.$$(mi) Z-Based Location: 2.54(ME) From: LOCAL"
                      '\n"LLUNIT",MI')
    assert (z.valor, z.unidade, z.campo) == (2.54, "mi", "Z-Based Location")
    tw = rele.do_texto('"L1_Fault_Location","112.576(km)"\n"L1_Fault_Location_Method","SE TW"')
    assert (tw.valor, tw.unidade) == (112.576, "km")
    assert rele.do_texto("Event:  CG T  Location:  +17.31   Frequency: 60.0").valor == 17.31


def test_micom_que_nao_mediu_e_dito_e_nao_confundido_com_arquivo_sem_campo(tmp_path):
    """O P139 escreve o campo com «Not measured» quando o localizador dele
    não rodou. É informação sobre o AJUSTE do relé — a tela diz «não mediu»
    em vez do «—» de quem não traz nada. Mas um número noutro arquivo vence."""
    sem = "15 | 20:11:36 | 0.884 | 004.022 | FT_DA Fault location       | Not measured\n"
    (tmp_path / "x.hdr").write_text(sem, encoding="cp1252")
    achado = rele.do_registro(tmp_path, ["x.cfg", "x.hdr"])
    assert isinstance(achado, rele.NaoMediu)
    assert (achado.campo, achado.arquivo, achado.escrito) == (
        "FT_DA Fault location", "x.hdr", "Not measured")
    (tmp_path / "x.txt").write_text(sem.replace("Not measured", "10.3 km"), encoding="cp1252")
    assert rele.do_registro(tmp_path, ["x.cfg", "x.hdr", "x.txt"]).km == 10.3
    (tmp_path / "y.hdr").write_text("nada aqui\n", encoding="cp1252")
    assert rele.do_registro(tmp_path, ["y.hdr"]) is None


def test_o_painel_diz_nao_mediu_sem_linha_do_rele(pacote):
    nm = rele.NaoMediu("FT_DA Fault location", "x.hdr", "Not measured")
    p = localizador.montar(pacote, None, None, nm, None)
    assert p["rele"] is None
    assert p["rele_nao_mediu"]["escrito"] == "Not measured"
    # Digitado vence, e aí não há o que dizer de «não mediu».
    p = localizador.montar(pacote, None, None, nm, 12.5)
    assert p["rele"]["km"] == 12.5 and p["rele_nao_mediu"] is None


def test_micom_le_o_km_e_o_percentual_da_fault_log():
    achado = rele.do_texto(
        "12 | 20:11:36.355 | 0.884 | 004.022 FT_DA Fault location       | 10.3 km\n"
        "13 | 20:11:36.355 | 0.884 | 004.027 FT_DA Fault locat. percent | 69.31 %\n")
    assert (achado.valor, achado.unidade, achado.percentual) == (10.3, "km", 69.31)
    assert achado.campo == "FT_DA Fault location"


def test_o_cev_vem_antes_do_hdr(tmp_path):
    (tmp_path / "a.cev").write_text(_cev({"LOCATION": "20.59"}), encoding="cp1252")
    (tmp_path / "a.hdr").write_text("Event: AG  Location:  99.99", encoding="cp1252")
    achado = rele.do_registro(tmp_path, ["a.hdr", "a.cev"])
    assert (achado.valor, achado.arquivo) == (20.59, "a.cev")
    assert rele.do_registro(tmp_path, ["nada.cfg"]) is None


# ---------------------------------------------------------------------------
# O arrumador do painel, em cima de uma localização sintética de verdade
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pacote():
    rede = _rede(0.43, 0.0, "AG")
    return ldl.montar(_registro(rede["S"]), _registro(rede["R"], nome="SE BETA"), 0.0,
                      LINHA, None)


def test_tudo_sai_em_km_e_em_porcentagem_da_linha(pacote):
    res = pacote["resultado"]
    p = localizador.montar(pacote, None, None, None, None)
    L = LINHA["km"]
    assert p["linha_km"] == L
    assert p["resultado"]["km"] == res["km"]
    assert p["resultado"]["pct"] == pytest.approx(res["km"] / L * 100)
    assert p["resultado"]["patrulha_km"] == pytest.approx([res["km"] - res["faixa"],
                                                           res["km"] + res["faixa"]])
    for m, par in p["metodos"].items():
        km = pacote["metodos"][m]["km"]
        assert par["km"] == km
        assert par["pct"] == (None if km is None else pytest.approx(km / L * 100))
    # As marcações em % vêm com o km em que caem: a tela só converte em pixel.
    for marca in p["marcas_pct"]:
        assert marca["km"] == pytest.approx(marca["rotulo"] * L / 100)


def test_o_trecho_assentado_cobre_o_plato_e_fica_dentro_da_falta(pacote):
    """Fora do assentado a tela apaga a curva: entrando na falta a janela está
    pela metade, saindo dela o laço mede carga. Ele precisa conter o platô —
    senão a curva de onde sai a mediana sairia apagada — e não pode começar
    antes de um ciclo depois do início da falta."""
    ev = pacote["eventos"]
    a0, a1 = ev["assentado"]
    p0, p1 = ev["plato"]
    assert a0 <= p0 and p1 <= a1
    assert a0 >= ev["inicio"] + 1 / 60 - 1e-9
    fins = [x for x in (ev["abre_a"], ev["fim_falta"]) if x is not None]
    if fins:
        assert a1 <= min(fins) + 1e-9


def test_os_dois_cursores_e_a_diferenca(pacote):
    plato = pacote["eventos"]["plato"]
    rede = _rede(0.43, 0.0, "AG")
    a, b = _registro(rede["S"]), _registro(rede["R"], nome="SE BETA")
    c1 = ldl.montar(a, b, 0.0, LINHA, plato[0] + 0.004)["cursor"]
    c2 = ldl.montar(a, b, 0.0, LINHA, plato[1] - 0.004)["cursor"]
    p = localizador.montar(pacote, c1, c2, None, None)
    m = pacote["resultado"]["metodo"]
    assert p["diferenca"]["km"][m] == pytest.approx(c2["km"][m] - c1["km"][m])
    assert p["cursor1"]["pct"][m] == pytest.approx(c1["km"][m] / LINHA["km"] * 100)
    sem = localizador.montar(pacote, c1, None, None, None)
    assert sem["cursor2"] is None and sem["diferenca"] is None


def test_o_rele_digitado_vence_o_lido_e_a_diferenca_e_contra_o_resultado(pacote):
    lido = rele.DoRele(20.0, None, "LOCATION", "x.cev")
    res_km = pacote["resultado"]["km"]
    p = localizador.montar(pacote, None, None, lido, None)
    r = p["rele"]
    assert (r["km"], r["origem"], r["presumido"]) == (20.0, "lido", True)
    assert p["rele"]["delta_km"] == pytest.approx(20.0 - res_km)
    p = localizador.montar(pacote, None, None, lido, 33.5)
    assert (p["rele"]["km"], p["rele"]["origem"]) == (33.5, "digitado")
    assert localizador.montar(pacote, None, None, None, None)["rele"] is None


def test_sem_linha_a_regua_sai_do_rele():
    """Sem Z1 nenhum método tem km, mas o relé tem o número dele."""
    sem_linha = {"metodos": {}, "resultado": None}
    p = localizador.montar(sem_linha, None, None, rele.DoRele(37.2, "km", "LOCATION", ""), None)
    assert p["linha_km"] is None and p["marcas_pct"] == []
    assert p["regua"]["min"] == 0 and p["regua"]["max"] >= 37.2
    assert localizador.montar(sem_linha, None, None, None, None)["regua"] is None


def test_o_painel_e_um_tipo_que_a_tela_pode_mandar():
    lidos = paineis.de_json([{"id": "t1", "tipo": "localizador", "nome": ""}])
    assert lidos[0].tipo == paineis.LOCALIZADOR
    assert localizador.esqueleto(lidos[0]) == {"id": "t1", "tipo": "localizador",
                                               "nome": "Localizador de faltas",
                                               "do_padrao": False}


# ---------------------------------------------------------------------------
# A rota: o bloco `painel` vai junto do pacote da localização
# ---------------------------------------------------------------------------


def test_a_rota_manda_o_bloco_do_painel_com_o_rele(tmp_path, monkeypatch, cliente):
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    caminho = escrever_cev(tmp_path / "origem", nome="EVENTO")
    texto = caminho.read_bytes().decode("cp1252").replace("$$$$.$$", "21.37")
    # A soma de verificação da linha muda; o leitor avisa e lê assim mesmo.
    sha = acervo.guardar([(caminho.name, texto.encode("cp1252"))]).aceitos[0].sha
    r = cliente.post(f"/api/onda/{sha}/localizar", json={"painel": True})
    assert r.status_code == 200
    rel = r.get_json()["painel"]["rele"]
    assert (rel["km"], rel["origem"], rel["campo"]) == (21.37, "lido", "LOCATION")
    r = cliente.post(f"/api/onda/{sha}/localizar", json={"painel": True, "rele_manual": 30})
    assert r.get_json()["painel"]["rele"]["origem"] == "digitado"
    # Sem o pedido do painel, o pacote é o de sempre da tela de localizar.
    assert "painel" not in cliente.post(f"/api/onda/{sha}/localizar", json={}).get_json()


# ---------------------------------------------------------------------------
# A janela «parâmetros»: escolher a linha na base pelo nome
# ---------------------------------------------------------------------------

def _base_com(tmp_path, monkeypatch, *linhas_):
    from osclab.basedados import linhas as linhas_mod
    from osclab.basedados import pasta as pasta_mod
    monkeypatch.setattr(paths, "BASES_FILE", tmp_path / "bases.json")
    base = pasta_mod.criar("base-de-teste", tmp_path)
    for x in linhas_:
        linhas_mod.gravar(base, x)
    return base


def _lt(nome, s, r, km=60.0, z0=True):
    from osclab.basedados.linhas import Linha
    return Linha(nome, s, r, 0.08 * km, 0.4 * km, km,
                 0.3 * km if z0 else None, 1.2 * km if z0 else None)


def test_a_busca_nao_sugere_nada_e_lista_em_ordem_alfabetica(tmp_path, monkeypatch):
    """Decidido em 10/11/2026: nenhuma linha é sugerida pelo nome do registro.
    A estrela era palpite tirado de um nome; quem escolhe é quem olha."""
    from osclab.basedados import linhas as linhas_mod
    base = _base_com(tmp_path, monkeypatch,
                     _lt("LT MI - NI", "MI", "NI"), _lt("LT SIGMA - OMEGA", "SIGMA", "OMEGA"),
                     _lt("LT ÁGUA BOA - SIGMA", "ÁGUA BOA", "SIGMA", z0=False))
    achadas = linhas_mod.buscar(base, "")
    assert [x["nome"] for x in achadas] == ["LT ÁGUA BOA - SIGMA", "LT MI - NI",
                                            "LT SIGMA - OMEGA"]
    # Nem o campo existe mais (saiu com a janela refeita, variante 17).
    assert not any("sugerida" in x or "casou" in x for x in achadas)
    # Cada palavra digitada filtra, sem acento e como pedaço de palavra.
    assert [x["nome"] for x in linhas_mod.buscar(base, "agua")] == ["LT ÁGUA BOA - SIGMA"]
    assert [x["nome"] for x in linhas_mod.buscar(base, "sig ome")] == ["LT SIGMA - OMEGA"]
    assert linhas_mod.buscar(base, "nada disso") == []
    assert achadas[0]["r0_ohm"] is None          # a tela avisa «sem Z0»
    assert linhas_mod.escolhida(base, "lt sigma - omega").comprimento_km == 60.0
    assert linhas_mod.escolhida(base, "LT INEXISTENTE") is None


def test_dois_trechos_de_mesmo_nome_se_distinguem_pelos_terminais(tmp_path, monkeypatch):
    """A base real repete o nome nos trechos de uma derivação (até o TAP e do
    TAP em diante). Pelo nome só, «o primeiro» seria trocar de linha calado."""
    from osclab.basedados import linhas as linhas_mod
    base = _base_com(tmp_path, monkeypatch, _lt("LD VG - POCONE", "VG", "TAP 70", km=20.2))
    # O `gravar` troca a de mesmo nome; a base real foi montada por script e
    # tem os dois trechos — então o segundo entra direto no arquivo.
    arquivo = linhas_mod._caminho(base)
    arquivo.write_text(arquivo.read_text(encoding="utf-8")
                       + "LD VG - POCONE;TAP 70;POCONE;5,3;26,6;66,4;19,9;79,7;;\n",
                       encoding="utf-8")
    assert linhas_mod.escolhida(base, "LD VG - POCONE") is None
    trecho = lambda s, r: linhas_mod.escolhida(base, "LD VG - POCONE", s, r)  # noqa: E731
    assert trecho("TAP 70", "POCONE").comprimento_km == 66.4
    assert trecho("VG", "TAP 70").comprimento_km == 20.2


def test_a_linha_escolhida_pelo_nome_vale_com_um_terminal_so(tmp_path, monkeypatch, cliente):
    """A linha da base é sempre ESCOLHIDA: sem escolha, a fonte «base» diz
    para escolher em «parâmetros» — nunca casa sozinha pelo nome."""
    _base_com(tmp_path, monkeypatch, _lt("LT ALFA - BETA", "ALFA", "BETA", km=37.5))
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    caminho = escrever_cev(tmp_path / "origem", nome="UM_TERMINAL")
    sha = acervo.guardar([(caminho.name, caminho.read_bytes())]).aceitos[0].sha
    sem = cliente.post(f"/api/onda/{sha}/localizar", json={"painel": True}).get_json()
    assert sem["fontes"]["base"]["ok"] is False
    assert "parâmetros" in sem["fontes"]["base"]["motivo"]
    com = cliente.post(f"/api/onda/{sha}/localizar",
                       json={"painel": True, "fonte": "base",
                             "linha_base": "LT ALFA - BETA"}).get_json()
    assert com["fonte"] == "base" and com["fontes"]["base"]["escolhida"] is True
    assert com["linha"]["km"] == 37.5
    errada = cliente.post(f"/api/onda/{sha}/localizar",
                          json={"fonte": "base", "linha_base": "LT GAMA"}).get_json()
    assert errada["fontes"]["base"]["ok"] is False and errada["linha"] is None
    lista = cliente.get(f"/api/onda/{sha}/linhas-da-base?q=alfa").get_json()
    assert lista["base"] is True and [x["nome"] for x in lista["linhas"]] == ["LT ALFA - BETA"]
    # A janela «parâmetros» (variante 17): a coluna da base nas quatro vistas,
    # e o selo, que só sai quando o relé difere — o CEV de teste não traz ajuste.
    par = com["parametros"]
    assert par["fichas"]["base"]["prim"]["ohm"]["km"] == "37,5"
    assert par["fichas"]["base"]["prim"]["km"]["r"] == "0,08"
    assert par["selo"] == [] and com["n_ieds"] == 1
    assert "estacao_conhecida" in com and com["sobre_o_resultado"]
    digitado = cliente.post(f"/api/onda/{sha}/localizar",
                            json={"painel": True, "fonte": "manual",
                                  "manual": {"r": "3", "x": "15", "km": "37,5"},
                                  "linha_base": "LT ALFA - BETA"}).get_json()
    assert digitado["fonte"] == "manual"
    cmp = digitado["parametros"]["comparacao"]["ohm"]["base"]
    assert cmp["km"] is False and cmp["mod"] is False and cmp["r0"] is False
    assert digitado["parametros"]["fichas"]["manual"]["prim"]["ohm"]["k0mod"] == ""


def test_a_linha_de_tres_terminais_entra_pelo_caminho_A_B_com_o_aviso(tmp_path, monkeypatch,
                                                                      cliente):
    from osclab.basedados import linhas as linhas_mod
    from tests.test_tres_terminais import CABECALHO, LINHAS, TRES_T
    base = _base_com(tmp_path, monkeypatch)
    pasta_linhas = base.gaveta(linhas_mod.PASTA)
    (pasta_linhas / "linhas.csv").write_text(CABECALHO + "\n".join(LINHAS) + "\n",
                                            encoding="utf-8")
    (pasta_linhas / "linhas-3t.csv").write_text(TRES_T, encoding="utf-8")
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    caminho = escrever_cev(tmp_path / "origem", nome="VG")
    sha = acervo.guardar([(caminho.name, caminho.read_bytes())]).aceitos[0].sha
    pedido = {"fonte": "base", "linha_base": {"nome": "LD VG - POCONE", "tipo": "3t"}}
    p = cliente.post(f"/api/onda/{sha}/localizar", json=pedido).get_json()
    assert p["fonte"] == "base" and p["linha"]["km"] == 80
    assert p["linha"]["perfil"][1][0] == 20                 # o perfil chega à conta
    assert "CANGAS" in p["aviso_linha"] and p["fontes"]["base"]["tap"]["nome"] == "CANGAS"
    lista = cliente.get(f"/api/onda/{sha}/linhas-da-base").get_json()
    assert lista["resumo_3t"]["tres_terminais"] == 1
    assert {x["nome"]: x["tipo"] for x in lista["linhas"]}["LD CV - BF"] == "trechos"
    r = cliente.post("/api/base/linhas-3t", json={"acao": "papeis", "nome": "LD VG - POCONE",
                                                  "papeis": ["A", "TAP", "B"]})
    assert r.status_code == 200
    p = cliente.post(f"/api/onda/{sha}/localizar", json=pedido).get_json()
    assert p["linha"]["km"] == pytest.approx(23.3) and "POCONE" in p["aviso_linha"]
    errado = cliente.post("/api/base/linhas-3t",
                          json={"acao": "papeis", "nome": "LD VG - POCONE",
                                "papeis": ["A", "A", "B"]})
    assert errado.status_code == 400


# ---------------------------------------------------------------------------
# O zoom do duplo clique: a região da falta (12/11/2026)
# ---------------------------------------------------------------------------

CICLO = 1 / 60
FOLGA = localizador.FOLGA_DO_ZOOM * CICLO


def _eventos(inicio, plato, assentado):
    return {"inicio": inicio, "plato": plato, "assentado": assentado,
            "abre_a": None, "fim_falta": None}


def test_a_regiao_da_falta_vai_do_inicio_ao_fim_do_assentado_com_folga():
    """Falta no meio do registro: do início − 2 ciclos ao fim do trecho em que
    a curva mede + 2 ciclos. Começa no INÍCIO, não no platô: quem amplia quer
    ver a falta entrar."""
    ev = _eventos(0.100, [0.1333, 0.1800], [0.1167, 0.1925])
    z = localizador.janela_da_falta(ev, 0.0, 0.5, CICLO, 1 / 2000)
    assert z["motivo"] == ""
    assert z["de"] == pytest.approx(0.100 - FOLGA)
    assert z["ate"] == pytest.approx(0.1925 + FOLGA)


def test_falta_colada_no_inicio_ou_no_fim_corta_na_borda_sem_deslizar():
    """Na borda a janela é cortada; deslizar para dentro poria do outro lado um
    pedaço que não é da falta."""
    z = localizador.janela_da_falta(_eventos(0.010, [0.043, 0.08], [0.027, 0.09]),
                                    0.0, 0.5, CICLO, 1 / 2000)
    assert z["de"] == pytest.approx(0.0)
    assert z["ate"] == pytest.approx(0.09 + FOLGA)
    z = localizador.janela_da_falta(_eventos(0.400, [0.433, 0.49], [0.417, 0.5]),
                                    0.0, 0.5, CICLO, 1 / 2000)
    assert z["de"] == pytest.approx(0.400 - FOLGA)
    assert z["ate"] == pytest.approx(0.5)


def test_sem_plato_ou_sem_falta_nao_ha_zoom_e_diz_por_que():
    z = localizador.janela_da_falta(_eventos(0.1, None, [0.117, 0.13]), 0.0, 0.5, CICLO)
    assert z["de"] is None and z["ate"] is None
    assert "platô" in z["motivo"]
    z = localizador.janela_da_falta(None, 0.0, 0.5, CICLO)
    assert z["de"] is None and "início de falta" in z["motivo"]
    # o aviso da conta, quando houver, é o motivo
    aviso = "o registro não mostra o início"
    z = localizador.janela_da_falta(None, 0.0, 0.5, CICLO, aviso=aviso)
    assert z["motivo"] == aviso


def test_a_regiao_da_falta_de_uma_falta_simulada_contem_o_inicio_e_o_plato(pacote):
    """Na falta AG do fixture: a janela contém o início (com a folga) e o platô
    inteiro, e é menor que o registro — é zoom de verdade."""
    ev = pacote["eventos"]
    z = localizador.janela_da_falta(ev, 0.0, 10.0, CICLO, 1 / 2000)
    assert z["de"] == pytest.approx(max(ev["inicio"] - FOLGA, 0.0))
    assert z["de"] < ev["plato"][0] and z["ate"] > ev["plato"][1]
    assert z["ate"] - z["de"] < 10.0
