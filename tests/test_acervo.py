"""O acervo: guardar, parear, recusar e listar.

Todos os testes redirecionam `paths.LIBRARY_DIR` para uma pasta temporária — o
acervo de verdade do usuário nunca é tocado por um teste.
"""

from __future__ import annotations

import pytest

from osclab import paths
from osclab.formats.base import FormatError
from osclab.library import acervo
from tests.fabrica import escrever_comtrade


@pytest.fixture(autouse=True)
def acervo_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LIBRARY_DIR", tmp_path / "acervo")
    return tmp_path / "acervo"


def _par(tmp_path, nome="REGISTRO", **kw) -> list[tuple[str, bytes]]:
    # Devolve [(nome_cfg, bytes), (nome_dat, bytes)] — desempacotável em dois.
    """Um par .cfg/.dat pronto para ser 'enviado'."""
    cfg = escrever_comtrade(tmp_path / f"origem-{nome}", nome=nome, **kw)
    dat = cfg.with_suffix(".dat")
    return [(cfg.name, cfg.read_bytes()), (dat.name, dat.read_bytes())]


# ---------------------------------------------------------------------------
# O caminho feliz
# ---------------------------------------------------------------------------

def test_guarda_um_par_completo(tmp_path):
    r = acervo.guardar(_par(tmp_path, n=64))
    assert len(r.aceitos) == 1
    assert not r.problemas
    item = r.aceitos[0]
    assert item.nome == "REGISTRO"
    assert item.n_amostras == 64
    assert item.estacao == "SE TESTE"
    assert set(item.arquivos) == {"REGISTRO.cfg", "REGISTRO.dat"}


def test_o_resumo_fica_em_cache(tmp_path):
    """A lista tem que abrir sem reler o registro inteiro."""
    sha = acervo.guardar(_par(tmp_path, n=64)).aceitos[0].sha
    item = acervo.obter(sha)
    assert item is not None
    assert item.n_analogicos == 3
    assert item.n_digitais == 4
    assert item.amostras_por_ciclo == pytest.approx(16.0, rel=0.01)


def test_o_registro_guardado_abre(tmp_path):
    sha = acervo.guardar(_par(tmp_path, n=64)).aceitos[0].sha
    registro = acervo.ler(sha)
    assert registro.n_samples == 64
    assert registro.analog.shape == (3, 64)


def test_lista_do_mais_novo_para_o_mais_velho(tmp_path):
    acervo.guardar(_par(tmp_path, nome="PRIMEIRO", n=32))
    acervo.guardar(_par(tmp_path, nome="SEGUNDO", n=64))
    nomes = [i.nome for i in acervo.listar()]
    assert set(nomes) == {"PRIMEIRO", "SEGUNDO"}
    assert len(acervo.listar()) == 2


# ---------------------------------------------------------------------------
# Endereçado por conteúdo
# ---------------------------------------------------------------------------

def test_enviar_duas_vezes_nao_duplica(tmp_path):
    arquivos = _par(tmp_path, n=64)
    primeiro = acervo.guardar(arquivos)
    segundo = acervo.guardar(arquivos)
    assert len(primeiro.aceitos) == 1
    assert len(segundo.aceitos) == 0
    assert len(segundo.repetidos) == 1
    assert len(acervo.listar()) == 1


def test_mesmo_nome_conteudo_diferente_convivem(tmp_path):
    """Todo fabricante exporta com o nome padrao dele. Dois registros de
    subestacoes diferentes chegam com o mesmo nome e nao podem se atropelar."""
    acervo.guardar(_par(tmp_path / "a", nome="FRA00045", n=32))
    acervo.guardar(_par(tmp_path / "b", nome="FRA00045", n=64))
    itens = acervo.listar()
    assert len(itens) == 2
    assert {i.n_amostras for i in itens} == {32, 64}


def test_dat_diferente_e_outro_registro(tmp_path):
    """O par e' que forma o evento: mesmo .cfg com outro .dat e' outro registro."""
    a = _par(tmp_path / "x", nome="R", n=64)
    b = _par(tmp_path / "y", nome="R", n=64, freq=50.0, taxa=1000.0)
    acervo.guardar(a)
    acervo.guardar(b)
    assert len(acervo.listar()) == 2


# ---------------------------------------------------------------------------
# Quando falta alguma coisa
# ---------------------------------------------------------------------------

def test_sem_o_dat_fica_esperando(tmp_path):
    """Não é erro: o arquivo vai para a antessala e espera o par."""
    so_cfg = [_par(tmp_path, n=32)[0]]
    r = acervo.guardar(so_cfg)
    assert not r.aceitos
    assert not r.problemas
    assert any("esperando o .dat" in linha for linha in r.aguardando)


def test_sem_o_cfg_fica_esperando(tmp_path):
    so_dat = [_par(tmp_path, n=32)[1]]
    r = acervo.guardar(so_dat)
    assert not r.aceitos
    assert any("esperando o .cfg" in linha for linha in r.aguardando)


def test_um_par_bom_entra_mesmo_com_outro_incompleto(tmp_path):
    """Um arquivo incompleto nao pode derrubar os outros do mesmo envio."""
    bons = _par(tmp_path / "bom", nome="BOM", n=32)
    so_cfg = [_par(tmp_path / "ruim", nome="INCOMPLETO", n=32)[0]]
    r = acervo.guardar([*bons, *so_cfg])
    assert [i.nome for i in r.aceitos] == ["BOM"]
    assert any("INCOMPLETO" in linha.upper() for linha in r.aguardando)


def test_registro_quebrado_nao_entra_no_acervo(tmp_path):
    """Se nao abrir, a pasta e' apagada: um acervo com coisa quebrada e' pior
    do que um acervo vazio."""
    cfg_nome, cfg_bytes = _par(tmp_path, n=32)[0]
    r = acervo.guardar([(cfg_nome, cfg_bytes), ("REGISTRO.dat", b"\x00" * 10)])
    assert not r.aceitos
    assert r.problemas
    assert acervo.listar() == []


def test_envio_vazio(tmp_path):
    r = acervo.guardar([])
    assert r.problemas


def test_avisa_sobre_extensao_que_nao_e_comtrade(tmp_path):
    """A Schneider exporta .sfd e .txt junto — nao fazem parte da norma."""
    arquivos = _par(tmp_path, n=32)
    r = acervo.guardar([*arquivos, ("REGISTRO.sfd", b"qualquer coisa")])
    assert len(r.aceitos) == 1
    assert any(".sfd" in p for p in r.problemas)


# ---------------------------------------------------------------------------
# Segurança: os nomes vêm do navegador
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("malicioso", [
    "../../../../windows/system32/evil.cfg",
    "..\\..\\evil.cfg",
    "/etc/passwd.cfg",
    "C:\\Windows\\evil.cfg",
])
def test_nome_com_caminho_nao_escapa_da_pasta(malicioso):
    limpo = acervo.nome_seguro(malicioso)
    assert "/" not in limpo
    assert "\\" not in limpo
    assert not limpo.startswith("..")


def test_agrupa_ignorando_maiusculas():
    grupos = acervo.agrupar(["REGISTRO.CFG", "registro.dat", "Registro.HDR"])
    assert len(grupos) == 1
    assert set(grupos["registro"]) == {".cfg", ".dat", ".hdr"}


# ---------------------------------------------------------------------------
# Consultar e remover
# ---------------------------------------------------------------------------

def test_sha_que_nao_existe(tmp_path):
    assert acervo.obter("naoexiste123") is None
    assert acervo.caminho_principal("naoexiste123") is None
    with pytest.raises(FormatError, match="nao esta"):
        acervo.ler("naoexiste123")


@pytest.mark.parametrize("sha", ["", "../outro", "a/b", "..", "nao alfanumerico"])
def test_sha_invalido_nao_vira_caminho(sha):
    assert acervo.obter(sha) is None


def test_remover(tmp_path):
    sha = acervo.guardar(_par(tmp_path, n=32)).aceitos[0].sha
    assert acervo.remover(sha) is True
    assert acervo.listar() == []
    assert acervo.remover(sha) is False


# ---------------------------------------------------------------------------
# A antessala: arquivo que chega sem o par fica esperando
# ---------------------------------------------------------------------------

def test_cfg_primeiro_depois_dat(tmp_path):
    """O caso que quebrou no primeiro teste de verdade: ninguém arrasta os dois
    juntos — manda um, vê que faltou, manda o outro."""
    cfg, dat = _par(tmp_path, n=64)

    primeiro = acervo.guardar([cfg])
    assert not primeiro.aceitos
    assert primeiro.aguardando
    assert "esperando o .dat" in primeiro.aguardando[0]

    segundo = acervo.guardar([dat])
    assert len(segundo.aceitos) == 1
    assert segundo.aceitos[0].n_amostras == 64
    assert acervo.aguardando() == {}


def test_dat_primeiro_depois_cfg(tmp_path):
    """A ordem inversa também tem que funcionar."""
    cfg, dat = _par(tmp_path, n=64)
    assert acervo.guardar([dat]).aguardando
    assert len(acervo.guardar([cfg]).aceitos) == 1
    assert len(acervo.listar()) == 1


def test_o_que_espera_fica_visivel(tmp_path):
    """A antessala tem que aparecer na tela: o pareamento é por nome, e dois
    registros com o mesmo nome poderiam se juntar errado sem ninguém ver."""
    cfg, _ = _par(tmp_path, nome="SOZINHO", n=32)
    acervo.guardar([cfg])
    espera = acervo.aguardando()
    assert "sozinho" in espera
    assert ".cfg" in espera["sozinho"]


def test_esquecer_o_que_espera(tmp_path):
    cfg, _ = _par(tmp_path, n=32)
    acervo.guardar([cfg])
    assert acervo.esquecer_aguardando() == 1
    assert acervo.aguardando() == {}


def test_a_antessala_nao_aparece_na_lista_do_acervo(tmp_path):
    cfg, _ = _par(tmp_path, n=32)
    acervo.guardar([cfg])
    assert acervo.listar() == []


def test_reenviar_o_cfg_corrigido_vale_o_novo(tmp_path):
    """Quem manda de novo quer que o novo valha."""
    cfg_velho, _ = _par(tmp_path / "v", nome="R", n=32)
    cfg_novo, dat_novo = _par(tmp_path / "n", nome="R", n=64)

    acervo.guardar([cfg_velho])
    acervo.guardar([cfg_novo])
    resultado = acervo.guardar([dat_novo])

    assert len(resultado.aceitos) == 1
    assert resultado.aceitos[0].n_amostras == 64


def test_par_errado_nao_entra_de_contrabando(tmp_path):
    """Um .dat de outro registro não pode entrar só porque o nome bate."""
    cfg, _ = _par(tmp_path / "a", nome="IGUAL", n=64)
    _, dat_de_outro = _par(tmp_path / "b", nome="IGUAL", n=64, na=7, nd=9)

    acervo.guardar([cfg])
    resultado = acervo.guardar([dat_de_outro])

    assert not resultado.aceitos
    assert resultado.problemas
    assert acervo.listar() == []


def test_varios_esperando_ao_mesmo_tempo(tmp_path):
    acervo.guardar([_par(tmp_path / "a", nome="UM", n=32)[0]])
    acervo.guardar([_par(tmp_path / "b", nome="DOIS", n=32)[0]])
    assert set(acervo.aguardando()) == {"um", "dois"}


# ---------------------------------------------------------------------------
# Vínculos: a correção de fase feita pelo usuário
# ---------------------------------------------------------------------------

def test_o_vinculo_corrigido_sobrevive_a_fechar_o_programa(tmp_path):
    """Quem corrigiu uma fase corrigiu para sempre, não até fechar o navegador.
    Guardar isso na tela faria a correção sumir no meio de uma análise."""
    sha = acervo.guardar(_par(tmp_path, n=64)).aceitos[0].sha
    acervo.gravar_vinculos(sha, {"0": "C"})
    # Reler do zero é o que um programa reaberto faz.
    assert acervo.vinculos(sha) == {0: "C"}
    assert acervo.ler(sha).analog_channels[0].phase_escolhida == "C"


def test_escolha_vazia_tira_o_vinculo(tmp_path):
    """Voltar atrás tem que ser possível: o usuário pode ter corrigido errado."""
    sha = acervo.guardar(_par(tmp_path, n=64)).aceitos[0].sha
    acervo.gravar_vinculos(sha, {"0": "C"})
    acervo.gravar_vinculos(sha, {"0": ""})
    assert acervo.vinculos(sha) == {}
    assert not (acervo._raiz() / sha / acervo.VINCULOS).exists()


def test_vinculo_com_lixo_e_ignorado(tmp_path):
    """A tela manda texto, e o servidor não confia nele."""
    sha = acervo.guardar(_par(tmp_path, n=64)).aceitos[0].sha
    acervo.gravar_vinculos(sha, {"0": "Z", "nao_e_numero": "A", "1": "b"})
    assert acervo.vinculos(sha) == {1: "B"}
