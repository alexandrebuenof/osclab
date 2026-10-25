"""A base de dados: a pasta, as gavetas e o dicionário dos sinais digitais.

Nenhum teste aqui usa fixture. Não é estilo: é para que o `tudo.py` — que roda
sem pytest instalado — consiga rodá-los de verdade. Um teste que o runner
oficial pula é um teste que não existe no dia em que a regressão aparece.

Cada teste monta a sua própria pasta temporária e aponta `paths` para ela, de
modo que a base de verdade do usuário nunca é tocada.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
from pathlib import Path

from osclab import paths
from osclab.basedados import digitais, pasta


@contextlib.contextmanager
def _area():
    """Uma pasta de dados só para este teste."""
    tmp = Path(tempfile.mkdtemp(prefix="osclab-base-"))
    nomes = ("DATA_DIR", "BASE_PADRAO", "BASES_FILE",
             "CONFIG_DIR", "CACHE_DIR", "LIBRARY_DIR")
    antes = {n: getattr(paths, n) for n in nomes}
    paths.DATA_DIR = tmp
    paths.BASE_PADRAO = tmp / "base"
    paths.BASES_FILE = tmp / "bases.json"
    paths.CONFIG_DIR = tmp / "config"
    paths.CACHE_DIR = tmp / "cache"
    paths.LIBRARY_DIR = tmp / "library"
    try:
        yield tmp
    finally:
        for n, v in antes.items():
            setattr(paths, n, v)
        shutil.rmtree(tmp, ignore_errors=True)


def _cliente():
    """Um cliente de teste do Flask, montado aqui e não numa fixture — o
    `tudo.py` não sabe fixtures, e teste pulado não pega regressão."""
    from osclab.web.server import create_app
    return create_app().test_client()


# ---------------------------------------------------------------------------
# A pasta
# ---------------------------------------------------------------------------

def test_sem_base_nenhuma_o_programa_responde_e_nao_quebra():
    """O estado «ainda não tem base» é o estado normal do primeiro dia."""
    with _area():
        assert pasta.ativa() is None
        e = pasta.estado()
        assert e["tem"] is False
        assert e["base"] is None
        assert [g["id"] for g in e["gavetas"]] == ["dicionario", "linhas"]
        assert all(g["itens"] == 0 for g in e["gavetas"])


def test_criar_deixa_a_marca_e_as_gavetas_no_disco():
    with _area():
        base = pasta.criar("Base da Regional Norte")
        assert base.existe
        # O nome é o mesmo no disco e na tela.
        assert base.pasta.name == "Base da Regional Norte"
        for g in ("dicionario", "linhas"):
            assert (base.pasta / g).is_dir()
        marca = json.loads((base.pasta / "base.json").read_text(encoding="utf-8"))
        assert marca["nome"] == "Base da Regional Norte"
        assert marca["formato"] == pasta.FORMATO


def test_o_apelido_da_pasta_sai_sem_acento_e_sem_espaco():
    """É esse nome que atravessa pen-drive, rede e o zip de outra regional."""
    assert pasta.apelido("Base da Subestação Nobres") == "base-da-subestacao-nobres"
    assert pasta.apelido("   ") == "base"
    assert pasta.apelido("Ação 2026!") == "acao-2026"


def test_o_NOME_da_base_e_o_nome_da_PASTA():
    """Ele soltou o nome em 19/10/2026: era travado em «database», e com um
    nome só não cabia mais de uma base na mesma pasta mãe."""
    with _area() as tmp:
        outra = tmp / "um lugar qualquer"
        outra.mkdir()
        base = pasta.criar("base-subestacoes", outra)
        assert base.pasta == outra / "base-subestacoes"
        assert base.nome == "base-subestacoes"
        # e duas bases convivem onde antes colidiam
        outra_base = pasta.criar("base-linhas", outra)
        assert outra_base.pasta == outra / "base-linhas"


def test_sem_nome_a_pasta_se_chama_database():
    """O padrão continua sendo o nome que todo mundo vai procurar."""
    with _area() as tmp:
        mae = tmp / "OscLab Regional Norte"
        mae.mkdir()
        base = pasta.criar("", mae)
        assert base.pasta == mae / pasta.NOME_PADRAO
        assert base.nome == pasta.NOME_PADRAO


def test_o_nome_da_base_NAO_pode_ser_um_caminho():
    """Barra no nome não é nome ruim: é outro caminho, e criaria a base
    noutro lugar. A tela avisa e deixa criar o resto; isto aqui barra."""
    with _area() as tmp:
        for ruim in ("../fora", "sub/pasta", "..", "."):
            try:
                pasta.criar(ruim, tmp)
            except pasta.ErroDaBase:
                pass
            else:
                raise AssertionError(f"devia ter recusado «{ruim}»")


def test_criar_de_novo_com_o_mesmo_nome_ABRE_em_vez_de_apagar():
    """Criar por cima de uma base que já existe apagaria trabalho de alguém."""
    with _area():
        base = pasta.criar("Minha base")
        digitais.anotar(base, "SEL", "351", "51P1T", "trip de fase")
        de_novo = pasta.criar("Minha base")
        assert de_novo.pasta == base.pasta
        assert len(digitais.listar(de_novo)) == 1


def test_criar_numa_pasta_que_ja_tem_coisa_dentro_recusa_com_explicacao():
    with _area() as tmp:
        ocupada = tmp / "Minha base"
        ocupada.mkdir()
        (ocupada / "planilha.xlsx").write_text("não sou uma base")
        try:
            pasta.criar("Minha base")
        except pasta.ErroDaBase as erro:
            assert "já existe" in str(erro)
        else:
            raise AssertionError("devia ter recusado")


def test_escolher_uma_pasta_que_nao_e_base_recusa_dizendo_o_que_falta():
    with _area() as tmp:
        qualquer = tmp / "fotos"
        qualquer.mkdir()
        try:
            pasta.escolher(qualquer)
        except pasta.ErroDaBase as erro:
            assert "base.json" in str(erro)
        else:
            raise AssertionError("devia ter recusado")


def test_a_base_cujo_caminho_sumiu_CONTINUA_na_lista_e_se_diz_ausente():
    """O pen-drive pode voltar amanhã. Esquecer sozinho seria decidir pelo dono."""
    with _area() as tmp:
        base = pasta.criar("Base do pen-drive")
        shutil.rmtree(base.pasta)
        ainda = pasta.ativa()
        assert ainda is not None
        assert ainda.existe is False
        e = pasta.estado()
        assert e["tem"] is False          # não dá para consultar...
        assert e["base"]["existe"] is False
        assert len(e["conhecidas"]) == 1  # ...mas ela não sumiu da lista
        assert tmp.exists()


def test_a_lembranca_de_qual_base_esta_ativa_fica_FORA_da_base():
    """A base viaja num zip sem levar a opinião de quem a montou."""
    with _area():
        base = pasta.criar("Base da equipe")
        pasta.habilitar("linhas", False)
        assert paths.BASES_FILE.is_file()
        assert not (base.pasta / paths.BASES_FILE.name).exists()
        guardado = json.loads(paths.BASES_FILE.read_text(encoding="utf-8"))
        assert guardado["habilitadas"]["linhas"] is False


def test_a_gaveta_ADIADA_volta_sem_migracao_nenhuma():
    """O histórico continua fora da lista. Adiar não custa nada:
    `Base.gaveta()` cria a pasta que faltar na hora de usar, então uma base
    criada hoje ganha `registros/` no dia em que a tela chegar."""
    with _area():
        assert "registros" not in pasta.IDS
        base = pasta.criar("Base")
        assert not (base.pasta / "registros").exists()
        assert base.gaveta("registros").is_dir()   # nasce quando for pedida


def test_o_DICIONARIO_tem_esse_nome_na_tela_e_na_pasta():
    """Nome oficial, escolhido por ele em 19/10/2026: dicionário. Na tela com
    acento; na pasta sem, que é o que atravessa pen-drive e rede."""
    assert pasta.GAVETAS[0].id == "dicionario"
    assert pasta.GAVETAS[0].nome == "Dicionário"
    assert pasta.PASTA_DO_DICIONARIO == "dicionario"
    assert digitais.ARQUIVO == "dicionario.csv"
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "trip de fase")
        assert (base.pasta / "dicionario" / "dicionario.csv").is_file()


def test_a_gaveta_desligada_para_de_ser_consultada_e_nao_apaga_nada():
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "trip de fase")
        assert pasta.usa("dicionario") is True

        pasta.habilitar("dicionario", False)
        assert pasta.usa("dicionario") is False
        assert pasta.habilitadas()["linhas"] is True   # as outras não mexem
        assert len(digitais.listar(base)) == 1         # nada no disco é apagado

        pasta.habilitar("dicionario", True)
        assert pasta.usa("dicionario") is True


def test_habilitar_uma_gaveta_que_nao_existe_e_erro():
    with _area():
        try:
            pasta.habilitar("quadros", True)
        except pasta.ErroDaBase:
            return
        raise AssertionError("devia ter recusado")


# ---------------------------------------------------------------------------
# O dicionário dos sinais digitais
# ---------------------------------------------------------------------------

def test_um_verbete_SEM_descricao_e_valido_e_sobrevive_a_ida_e_volta():
    """A regra conservadora: quem não tem certeza deixa em branco."""
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "IN101")
        de_volta = digitais.listar(base)
        assert len(de_volta) == 1
        assert de_volta[0].sinal == "IN101"
        assert de_volta[0].descricao == ""
        assert de_volta[0].categoria == ""


def test_o_csv_sai_com_BOM_para_o_excel_abrir_os_acentos():
    """Sem o BOM, «estágio» volta como «estÃ¡gio» no primeiro duplo clique."""
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "trip do estágio 1")
        bruto = (base.pasta / "dicionario" / "dicionario.csv").read_bytes()
        assert bruto.startswith(b"\xef\xbb\xbf")
        assert b"fabricante;modelo;sinal;descricao;categoria" in bruto


def test_anotar_duas_vezes_CORRIGE_em_vez_de_duplicar():
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "errado")
        digitais.anotar(base, "sel", "351", "51p1t", "certo")
        lista = digitais.listar(base)
        assert len(lista) == 1
        assert lista[0].descricao == "certo"


def test_anotar_com_None_nao_mexe_e_com_vazio_apaga():
    """Apagar uma descrição errada é operação legítima — e frequente."""
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "trip de fase", "trip")
        digitais.anotar(base, "SEL", "351", "51P1T", categoria="partida")
        v = digitais.listar(base)[0]
        assert v.descricao == "trip de fase"   # None não mexeu
        assert v.categoria == "partida"
        digitais.anotar(base, "SEL", "351", "51P1T", descricao="")
        assert digitais.listar(base)[0].descricao == ""


def test_o_mesmo_sinal_em_MODELOS_diferentes_sao_dois_verbetes():
    """`51P1T` quer dizer coisas diferentes num 351 e num 411L."""
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "no 351")
        digitais.anotar(base, "SEL", "411L", "51P1T", "no 411L")
        assert len(digitais.listar(base)) == 2
        assert digitais.descrever(base, "SEL", "411L", "51P1T").descricao == "no 411L"


def test_uma_categoria_que_o_programa_nao_conhece_vira_vazio_e_nao_derruba_o_arquivo():
    with _area():
        base = pasta.criar("Base")
        digitais.importar(base, "SEL;351;51P1T;trip de fase;disparo\n")
        v = digitais.listar(base)[0]
        assert v.descricao == "trip de fase"
        assert v.categoria == ""


def test_importar_ACRESCENTA_e_corrige_sem_apagar_o_que_voce_escreveu():
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "IN101", "entrada do 86BF", "estado")
        resumo = digitais.importar(base,
            "fabricante;modelo;sinal;descricao;categoria\n"
            "SEL;351;IN101;;\n"                       # a linha de fora é vazia
            "ABB;REL670;PHPIOC-TRIP;trip instantâneo;trip\n")
        assert resumo["acrescentados"] == 1
        assert digitais.descrever(base, "SEL", "351", "IN101").descricao == "entrada do 86BF"
        assert digitais.descrever(base, "ABB", "REL670", "PHPIOC-TRIP").categoria == "trip"


def test_importar_aceita_VIRGULA_quando_o_arquivo_veio_com_virgula():
    """Quem exporta o Excel em outra região manda vírgula. Não é motivo para
    recusar o arquivo da pessoa."""
    with _area():
        base = pasta.criar("Base")
        digitais.importar(base,
            "fabricante,modelo,sinal,descricao,categoria\n"
            "SEL,351,TRIP,saída de trip do relé,trip\n")
        assert digitais.descrever(base, "SEL", "351", "TRIP").categoria == "trip"


def test_linha_sem_SINAL_nao_vira_verbete():
    with _area():
        base = pasta.criar("Base")
        digitais.importar(base, "SEL;351;;descrição órfã;trip\n\n;;;;\n")
        assert digitais.listar(base) == []


def test_descrever_devolve_None_quando_a_base_nao_conhece_o_sinal():
    """O `None` é o caminho NORMAL: a base nasce vazia, e o leitor tem que
    mostrar o nome cru sem reclamar."""
    with _area():
        base = pasta.criar("Base")
        assert digitais.descrever(base, "SEL", "351", "NUNCA_VISTO") is None


def test_remover_tira_so_o_verbete_pedido():
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "um")
        digitais.anotar(base, "SEL", "351", "50P1", "outro")
        assert digitais.remover(base, "SEL", "351", "51P1T") is True
        assert [v.sinal for v in digitais.listar(base)] == ["50P1"]
        assert digitais.remover(base, "SEL", "351", "51P1T") is False


def test_a_contagem_da_gaveta_e_a_que_a_tela_mostra():
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "trip")
        digitais.anotar(base, "SEL", "351", "50P1", "partida")
        e = pasta.estado()
        conta = {g["id"]: g["itens"] for g in e["gavetas"]}
        assert conta["dicionario"] == 2
        assert conta["linhas"] == 0


# ---------------------------------------------------------------------------
# As rotas
# ---------------------------------------------------------------------------

def test_a_tela_inicial_AVISA_enquanto_nao_houver_base():
    with _area():
        r = _cliente().get("/")
        assert r.status_code == 200
        assert "Você ainda não tem uma base de dados".encode() in r.data
        assert b"criar ou escolher" in r.data


def test_a_tela_inicial_mostra_a_LINHA_DE_ESTADO_quando_ha_base():
    with _area():
        base = pasta.criar("Base da Regional Norte")
        digitais.anotar(base, "SEL", "351", "51P1T", "trip de fase")
        r = _cliente().get("/")
        assert b"linha-da-base" in r.data
        assert "Você ainda não tem".encode() not in r.data
        assert b"dicion" in r.data


def test_a_gaveta_desligada_aparece_RISCADA_e_nao_some_da_linha():
    with _area():
        pasta.criar("Base")
        pasta.habilitar("linhas", False)
        r = _cliente().get("/")
        assert b"apagada" in r.data
        assert b"linhas e estruturas" in r.data


def test_a_tela_da_base_sobe_com_o_estado_dentro_do_HTML():
    """O estado viaja no HTML para a tela não piscar vazia antes de saber se
    existe base — justamente a tela em que o «ainda não tem» é o assunto."""
    with _area():
        r = _cliente().get("/base")
        assert r.status_code == 200
        assert b"estado-da-base" in r.data
        assert b"js/base.js" in r.data


def test_criar_pela_rota_devolve_o_estado_novo_inteiro():
    with _area():
        c = _cliente()
        r = c.post("/api/base/criar", json={"nome": "Base da Regional Norte"})
        assert r.status_code == 200
        dados = r.get_json()
        assert dados["tem"] is True
        assert dados["base"]["nome"] == "Base da Regional Norte"
        assert len(dados["gavetas"]) == 2


def test_escolher_uma_pasta_errada_volta_400_com_o_motivo_na_tela():
    with _area() as tmp:
        r = _cliente().post("/api/base/escolher", json={"pasta": str(tmp / "nada")})
        assert r.status_code == 400
        assert "não encontrei" in r.get_json()["erro"]


def test_a_rota_da_gaveta_liga_e_desliga():
    with _area():
        c = _cliente()
        c.post("/api/base/criar", json={"nome": "Base"})
        r = c.post("/api/base/gaveta", json={"gaveta": "linhas", "ligada": False})
        marcas = {g["id"]: g["ligada"] for g in r.get_json()["gavetas"]}
        assert marcas["linhas"] is False
        assert marcas["dicionario"] is True
        assert "registros" not in marcas


def test_anotar_um_digital_pela_rota_grava_e_devolve_a_contagem():
    with _area():
        c = _cliente()
        c.post("/api/base/criar", json={"nome": "Base"})
        r = c.post("/api/base/dicionario", json={
            "fabricante": "SEL", "modelo": "351", "sinal": "51P1T",
            "descricao": "trip temporizado de fase", "categoria": "trip"})
        assert r.status_code == 200
        assert r.get_json()["itens"] == 1
        lista = c.get("/api/base/dicionario").get_json()["verbetes"]
        assert lista[0]["categoria"] == "trip"


def test_anotar_SEM_base_ativa_volta_400_em_vez_de_estourar():
    with _area():
        r = _cliente().post("/api/base/dicionario", json={"sinal": "51P1T"})
        assert r.status_code == 400
        assert "base" in r.get_json()["erro"].lower()


def test_um_verbete_SEM_sinal_e_recusado_com_motivo():
    with _area():
        c = _cliente()
        c.post("/api/base/criar", json={"nome": "Base"})
        r = c.post("/api/base/dicionario", json={"fabricante": "SEL", "sinal": "  "})
        assert r.status_code == 400


def test_importar_pela_rota_junta_ao_que_ja_existe():
    with _area():
        c = _cliente()
        c.post("/api/base/criar", json={"nome": "Base"})
        c.post("/api/base/dicionario", json={"fabricante": "SEL", "modelo": "351",
                                           "sinal": "IN101", "descricao": "minha"})
        r = c.post("/api/base/dicionario/importar", json={
            "texto": "SEL;351;IN101;;\nABB;REL670;PHPIOC-TRIP;trip instantâneo;trip\n"})
        assert r.get_json()["acrescentados"] == 1
        lista = {v["sinal"]: v for v in c.get("/api/base/dicionario").get_json()["verbetes"]}
        assert lista["IN101"]["descricao"] == "minha"


def test_importar_NADA_volta_400():
    with _area():
        c = _cliente()
        c.post("/api/base/criar", json={"nome": "Base"})
        r = c.post("/api/base/dicionario/importar", json={"texto": "   "})
        assert r.status_code == 400


def test_o_diagnostico_diz_onde_a_base_esta():
    with _area():
        c = _cliente()
        assert c.get("/saude").get_json()["base"] == ""
        c.post("/api/base/criar", json={"nome": "Base"})
        assert c.get("/saude").get_json()["base"].endswith("Base")


def test_a_base_do_usuario_NAO_pode_entrar_no_repositorio_publico():
    """O repositório é público e a base guarda dado da distribuidora — KMZ de
    estrutura, parâmetro de linha, nome de sinal do parque. A barra na frente
    é obrigatória: `base/` solto barraria `src/osclab/formats/base.py` e o
    clone não rodaria. Já custou um commit para descobrir, no `library/`."""
    texto = (paths.PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    linhas = [l.strip() for l in texto.splitlines()]
    assert "/base/" in linhas
    assert "/database/" in linhas    # o nome fixo da pasta da base
    assert "/base-*/" in linhas      # os apelidos que a versão anterior gerava
    assert "/bases.json" in linhas
    assert "base/" not in linhas     # sem a barra, levaria o formats/base.py junto


# ---------------------------------------------------------------------------
# O navegador de pastas
# ---------------------------------------------------------------------------

def test_o_navegador_lista_SO_pastas_e_pula_as_ocultas():
    """A pergunta é «onde», não «qual arquivo». E pasta oculta não é lugar de
    guardar a base de ninguém."""
    from osclab.basedados import navegar
    with _area() as tmp:
        (tmp / "Documentos").mkdir()
        (tmp / ".oculta").mkdir()
        (tmp / "planilha.xlsx").write_text("não sou pasta")
        nomes = [p["nome"] for p in navegar.listar(str(tmp))["pastas"]]
        assert nomes == ["Documentos"]


def test_o_navegador_sabe_subir_um_nivel_e_para_na_raiz():
    from osclab.basedados import navegar
    with _area() as tmp:
        dentro = tmp / "uma" / "outra"
        dentro.mkdir(parents=True)
        r = navegar.listar(str(dentro))
        assert r["pai"] == str(tmp / "uma")
        raiz = navegar.listar("/")
        assert raiz["pai"] is None      # a raiz não tem acima


def test_uma_pasta_que_nao_existe_volta_VAZIA_e_nao_derruba_a_tela():
    from osclab.basedados import navegar
    with _area() as tmp:
        r = navegar.listar(str(tmp / "nao-existe"))
        assert r["existe"] is False
        assert r["pastas"] == []
        assert r["atalhos"]             # os atalhos continuam, para sair dali


def test_a_rota_das_pastas_responde_com_atalhos_e_subpastas():
    with _area() as tmp:
        (tmp / "Relatorios").mkdir()
        r = _cliente().get("/api/base/pastas?onde=" + str(tmp))
        dados = r.get_json()
        assert r.status_code == 200
        # O `create_app` também cria `cache/`, `config/` e `library/` aqui —
        # por isso a conferência é de pertencimento, e não de igualdade.
        assert "Relatorios" in [p["nome"] for p in dados["pastas"]]
        assert dados["atual"] == str(tmp.resolve())


def test_quando_a_janela_do_SISTEMA_nao_abre_a_resposta_diz_isso():
    """`disponivel: false` é o que faz a tela cair no navegador desenhado na
    página. Sem esse campo, o «…» não faria nada numa máquina sem tkinter —
    que é o pior defeito possível num botão: o que não reage."""
    from osclab.basedados import navegar
    r = navegar.nativo("/tmp")
    assert set(r) == {"disponivel", "caminho", "cancelado"}
    if not r["disponivel"]:
        assert r["caminho"] == ""


def test_a_rota_da_janela_do_sistema_responde_sem_derrubar_o_servidor():
    with _area():
        r = _cliente().post("/api/base/pasta-nativa", json={"inicial": "/tmp"})
        assert r.status_code == 200
        assert "disponivel" in r.get_json()


def test_a_coluna_chama_se_CATEGORIA_e_nao_tipo():
    """Palavra dele, 19/10/2026 — e a mesma que a engrenagem usa: «agrupar por
    categoria», «pintar por categoria». Uma palavra só para a mesma coisa."""
    assert digitais.COLUNAS == ("fabricante", "modelo", "sinal", "descricao", "categoria")
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "351", "51P1T", "trip de fase", "trip")
        texto = (base.pasta / "dicionario" / "dicionario.csv").read_text(encoding="utf-8-sig")
        assert texto.splitlines()[0] == "fabricante;modelo;sinal;descricao;categoria"
        assert digitais.listar(base)[0].categoria == "trip"


def test_as_CATEGORIAS_sao_as_seis_defendidas_e_nao_ha_balde():
    """Cada uma passou no teste «quero esses sinais juntos e nessa cor?».
    E não há `outros`: balde compete com o vazio, e tudo que dá dúvida acaba
    nele. Se um sinal real não couber, falta categoria COM NOME."""
    assert digitais.CATEGORIAS == (
        "", "trip", "partida", "bloqueio", "estado", "io", "auxiliar")
    assert "outros" not in digitais.CATEGORIAS
    assert "alarme" not in digitais.CATEGORIAS   # ou bloqueia, e é bloqueio, ou é estado


def test_a_AUXILIAR_guarda_a_logica_interna_do_rele():
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "SEL", "", "SV01T",
                        "saída do temporizador auxiliar 1", "auxiliar")
        digitais.anotar(base, "SEL", "", "LOP",
                        "perda de potencial — bloqueia os elementos de tensão", "bloqueio")
        digitais.anotar(base, "SEL", "351", "IN101", "entrada do 86BF", "io")
        por_sinal = {v.sinal: v.categoria for v in digitais.listar(base)}
        assert por_sinal == {"SV01T": "auxiliar", "LOP": "bloqueio", "IN101": "io"}


def test_uma_categoria_antiga_que_saiu_vira_VAZIO_e_nao_derruba_o_arquivo():
    """Uma base montada antes desta decisão pode trazer `alarme`. O arquivo
    continua abrindo; o verbete só fica sem categoria."""
    with _area():
        base = pasta.criar("Base")
        digitais.importar(base, "SEL;351;IN102;contato de alarme;alarme\n")
        v = digitais.listar(base)[0]
        assert v.descricao == "contato de alarme"
        assert v.categoria == ""


def test_identificar_parte_o_equipamento_em_fabricante_e_modelo():
    """O campo é texto livre: tanto vem «SEL-351» quanto o nome do vão. O que
    não for reconhecido vira MODELO — um palpite errado de fabricante casaria
    o verbete errado."""
    assert digitais.identificar("SEL-351") == ("SEL", "351")
    assert digitais.identificar("ABB REL670") == ("ABB", "REL670")
    assert digitais.identificar("FRA00045") == ("", "FRA00045")
    assert digitais.identificar("") == ("", "")


def test_identificar_entende_a_fid_da_sel_e_o_micom():
    """O COMTRADE da SEL grava a FID inteira: sem tirar `FID=` e a revisão,
    nenhum registro SEL achava o fabricante (banco do parque, 24/10/2026)."""
    assert digitais.identificar("FID=SEL-487E-3-R312-V0-Z106101-D20160115") == ("SEL", "487E")
    assert digitais.identificar("FID=SEL-311C-1-R508-V1-Z104101-D20170818") == ("SEL", "311C")
    assert digitais.identificar("SEL-451-5") == ("SEL", "451")
    assert digitais.identificar("SEL-411L-1") == ("SEL", "411L")
    assert digitais.identificar("FID=SEL-411L-A-R133-V0-Z022004-D20250515") == ("SEL", "411L")
    assert digitais.identificar("SEL-TWFL") == ("SEL", "TWFL")
    assert digitais.identificar("P439-655-704; F: 3.704576.4") == ("SCHNEIDER", "P439")


def test_descrever_sobe_os_TRES_degraus_ate_achar():
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "", "", "TRIP", "saída de trip do relé", "trip")
        digitais.anotar(base, "SEL", "", "51P1T", "trip temporizado de fase", "trip")
        digitais.anotar(base, "SEL", "351", "IN101", "entrada do 86BF", "io")

        # o do modelo vence no modelo, e não existe para outro modelo
        assert digitais.descrever(base, "SEL", "351", "IN101").descricao == "entrada do 86BF"
        assert digitais.descrever(base, "SEL", "411L", "IN101") is None
        # o do fabricante vale para a família inteira
        assert digitais.descrever(base, "SEL", "411L", "51P1T") is not None
        # o genérico vale até para um relé que o arquivo não identifica
        assert digitais.descrever(base, "", "", "TRIP").descricao == "saída de trip do relé"
        assert digitais.descrever(base, "ABB", "REL670", "TRIP") is not None
        # e o que ninguém cadastrou continua sem resposta
        assert digitais.descrever(base, "SEL", "351", "NUNCA_VISTO") is None


def test_o_mais_ESPECIFICO_vence_o_generico():
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "", "", "IN101", "entrada genérica", "io")
        digitais.anotar(base, "SEL", "351", "IN101", "entrada do 86BF", "io")
        assert digitais.descrever(base, "SEL", "351", "IN101").descricao == "entrada do 86BF"
        generico = digitais.descrever(base, "ABB", "REL670", "IN101")
        assert generico.descricao == "entrada genérica"


def test_aplicaveis_devolve_UM_verbete_por_sinal_com_a_origem():
    """Dois verbetes do mesmo sinal na tela confundiriam quem procura o
    significado: a consulta mostra só o que venceu, e diz onde venceu."""
    with _area():
        base = pasta.criar("Base")
        digitais.anotar(base, "", "", "IN101", "entrada genérica", "io")
        digitais.anotar(base, "SEL", "351", "IN101", "entrada do 86BF", "io")
        digitais.anotar(base, "SEL", "", "51P1T", "trip de fase", "trip")
        lista = digitais.aplicaveis(base, "SEL-351")
        assert [v["sinal"] for v in lista] == ["51P1T", "IN101"]
        porsinal = {v["sinal"]: v for v in lista}
        assert porsinal["IN101"]["descricao"] == "entrada do 86BF"
        assert porsinal["IN101"]["origem"] == "deste modelo"
        assert porsinal["51P1T"]["origem"] == "de todo SEL"


def test_a_rota_do_registro_avisa_quando_nao_ha_o_que_consultar():
    """Sem base, sem gaveta ligada ou com o dicionário vazio, a tela precisa
    saber POR QUÊ — é o que ela escreve para quem clicou na chave cinza."""
    with _area():
        c = _cliente()
        r = c.get("/api/dicionario/sem-sha-nenhum")
        dados = r.get_json()
        assert dados["tem"] is False
        assert "base de dados" in dados["motivo"]

        c.post("/api/base/criar", json={"nome": "Base"})
        dados = c.get("/api/dicionario/sem-sha-nenhum").get_json()
        assert dados["tem"] is False
        assert "vazio" in dados["motivo"]

        c.post("/api/base/dicionario", json={"sinal": "TRIP", "descricao": "trip"})
        dados = c.get("/api/dicionario/sem-sha-nenhum").get_json()
        assert dados["tem"] is True
        assert dados["verbetes"][0]["sinal"] == "TRIP"


def test_o_dicionario_DESLIGADO_na_gaveta_nao_responde_a_consulta():
    with _area():
        c = _cliente()
        c.post("/api/base/criar", json={"nome": "Base"})
        c.post("/api/base/dicionario", json={"sinal": "TRIP", "descricao": "trip"})
        c.post("/api/base/gaveta", json={"gaveta": "dicionario", "ligada": False})
        dados = c.get("/api/dicionario/sem-sha-nenhum").get_json()
        assert dados["tem"] is False
        assert "desligado" in dados["motivo"]
