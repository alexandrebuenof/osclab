"""A leitura dos ajustes que vêm dentro do registro (`formats/ajustes.py`).

O trecho abaixo é SINTÉTICO, escrito para o teste no formato que a SEL despeja
no `.HDR` do COMTRADE — o do arquivo de ajustes do QuickSet. Nenhum arquivo
real entra no repositório.
"""

from __future__ import annotations

from osclab.formats import ajustes

HDR_QUICKSET = '''\
LT TESTE                                   Date: 01/01/2026  Time: 00:00:00.000
Event: BC                Location:  -5.00                    Time Source: OTHER

SET_S1.TXT
[INFO]
RELAYTYPE=SEL-421-4
[S1]
"SID","SE TESTE"
"BID1","DJ-01"
"CTRW",240
"PTRY",1200.0
"Z1MAG",1.26
"Z1ANG",71.17
"Z1MG","1.00"
"DIR3",R
"FAULT","50P1 OR Z2P OR Z3P"
"PTDIR","IN207 # recepcao direcional"
"PROTSEL1","PSV60 := NOT IN101 AND IN102 # disjuntor fechado"
'''


def test_o_formato_csv_com_aspas_do_HDR_da_SEL_e_lido(tmp_path):
    """LT COXIPO, 22/10/2026: o `.HDR` trazia `"Z1MAG",1.26` e as relações
    de TC/TP, e o plano de impedância dizia «o arquivo não traz Z1MAG».
    O leitor só conhecia `NOME := VALOR`."""
    (tmp_path / "x.hdr").write_text(HDR_QUICKSET, encoding="utf-8")
    dados = ajustes.do_registro(tmp_path, ["x.cfg", "x.hdr"], ["IN207", "IN101"])
    valores = dict(dados["ajustes"])
    logica = dict(dados["logica"])
    assert valores["Z1MAG"] == "1.26"
    assert valores["Z1ANG"] == "71.17"
    assert valores["CTRW"] == "240"
    assert valores["PTRY"] == "1200.0"
    assert valores["Z1MG"] == "1.00"          # entre aspas, sem as aspas
    assert valores["DIR3"] == "R"
    # Texto entre aspas com espaço é TEXTO, não equação.
    assert valores["SID"] == "SE TESTE"
    # Operador continua fazendo dele lógica, e o termo único que é canal
    # digital também — o comentário depois de `#` não conta.
    assert "FAULT" in logica
    assert "PTDIR" in logica
    # A equação embrulhada no `"PROTSELn",` sai pelo nome de DENTRO.
    assert logica["PSV60"].startswith("NOT IN101 AND IN102")
    assert "PROTSEL1" not in valores and "PROTSEL1" not in logica


def test_o_formato_de_sempre_continua_valendo():
    """`NOME := VALOR`, dois por linha, como o SEL escreve no `.CEV`."""
    texto = "Z1MAG := 1.26     Z1ANG := 71.17\nTR := M1P OR Z1G\n"
    assert ajustes.pares(texto) == [("Z1MAG", "1.26"), ("Z1ANG", "71.17"),
                                     ("TR", "M1P OR Z1G")]
    aj, lg = ajustes.separar(ajustes.pares(texto))
    assert ["TR", "M1P OR Z1G"] in lg and ["Z1MAG", "1.26"] in aj


def test_a_classificacao_do_rele_segue_lida_do_mesmo_HDR(tmp_path):
    (tmp_path / "x.hdr").write_text(HDR_QUICKSET, encoding="utf-8")
    assert ajustes.classificacao_no_hdr(tmp_path, ["x.hdr"]) == "BC"


# ---------------------------------------------------------------------------
# Formas que o banco do parque mostrou (24/10/2026)
# ---------------------------------------------------------------------------

def test_hdr_do_311c_com_o_nome_sem_aspas():
    """`Z1MAG,"12.35"`: o `.HDR` COMTRADE do 311C não põe aspas no nome, e o
    leitor tirava 3 pares de ~450. Linha de amostras não vira ajuste."""
    texto = 'RID,"LT TESTE UPC2"\nCTR,"160"\nZ1MAG,"12.35"\n1,"0.5"\n'
    lidos = dict(ajustes.pares(texto))
    assert lidos == {"RID": "LT TESTE UPC2", "CTR": "160", "Z1MAG": "12.35"}


def test_um_espaco_so_separa_dois_ajustes():
    """O 787 encosta a coluna quando o valor tem oito caracteres."""
    lidos = dict(ajustes.pares("VWDG1   := 138.000 VWDG2   := 34.500\n"
                               "PTR     := 1200.00 VNOM    := 138.00\n"
                               "XY      := 51P1 >= 3\n"))
    assert lidos["VWDG1"] == "138.000" and lidos["VWDG2"] == "34.500"
    assert lidos["PTR"] == "1200.00" and lidos["VNOM"] == "138.00"
    assert lidos["XY"] == "51P1 >= 3"


def test_equacao_continuada_sai_inteira():
    """4xx: a linha termina em barra invertida. 311C: a seguinte vem recuada
    e começa por operador."""
    barra = chr(92)
    lidos = dict(ajustes.pares(
        f"TR      := Z1T OR Z2T OR {barra}\n"
        f"            51S1T OR 67P3T # TRIP GERAL\n"
        "ULTR    := NOT 50L\n"))
    assert lidos["TR"] == "Z1T OR Z2T OR 51S1T OR 67P3T # TRIP GERAL"
    assert lidos["ULTR"] == "NOT 50L"
    lidos = dict(ajustes.pares("TR    =M1P + Z1G + 51GT\n        + Z4GT\nTRCOMM=M2P + Z2G\n"))
    assert lidos["TR"] == "M1P + Z1G + 51GT + Z4GT" and lidos["TRCOMM"] == "M2P + Z2G"


def test_hdr_em_json_do_acselerator():
    texto = ('{"Settings":[{"Group":"Summary Data","Name":"EVENT","Value":"ABC T"},'
             '{"Group":"Group 1","Name":"RID","Value":"LT TESTE"},'
             '{"Group":"Group 1","Name":"Z1MAG","Value":"4.38"},'
             '{"Group":"SELogic Group 1","Name":"TR","Value":"M1P + Z1G"}]}')
    todos = ajustes._pares_com_forma(texto)
    assert dict((n, v) for n, v, _ in todos) == {
        "EVENT": "ABC T", "RID": "LT TESTE", "Z1MAG": "4.38", "TR": "M1P + Z1G"}
    ajuste, logica = ajustes.separar(todos, set())
    nomes_logica = {nome for nome, _ in logica}
    assert "TR" in nomes_logica and "RID" not in nomes_logica


def test_texto_de_apelido_com_igual_nao_vira_ajuste():
    """`ALIAS5 :=SV12 PROT_50G_50R SV12=1 SV12=0` (SEL-751): com um espaço só
    o `SV12=1` virava ajuste e tomava o lugar da equação do `SV12`."""
    lidos = dict(ajustes.pares("ALIAS5  :=SV12 PROT_50G_50R SV12=1 SV12=0\n"
                               "SV12    := (50G1T OR 50N1T) AND SH0 #PROTECAO\n"))
    assert lidos["ALIAS5"] == "SV12 PROT_50G_50R SV12=1 SV12=0"
    assert lidos["SV12"] == "(50G1T OR 50N1T) AND SH0 #PROTECAO"
