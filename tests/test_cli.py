"""O modo `--ler` do terminal.

O caminho chega aqui do jeito que o Windows entrega: entre aspas quando o
arquivo foi arrastado para a janela, ou partido em pedaços quando foi digitado
sem aspas e tem espaço. Já fechou a janela do usuário uma vez — agora tem teste.
"""

from __future__ import annotations

from osclab.cli import inspecionar
from tests.fabrica import escrever_comtrade


def test_le_caminho_simples(tmp_path, capsys):
    cfg = escrever_comtrade(tmp_path, nome="simples", n=32)
    assert inspecionar.main([str(cfg)]) == 0
    saida = capsys.readouterr().out
    assert "SE TESTE" in saida
    assert "Canais analogicos" in saida


def test_le_caminho_entre_aspas(tmp_path, capsys):
    """É assim que o caminho chega quando o arquivo é arrastado para o cmd."""
    cfg = escrever_comtrade(tmp_path, nome="aspas", n=32)
    assert inspecionar.main([f'"{cfg}"']) == 0
    assert "SE TESTE" in capsys.readouterr().out


def test_le_caminho_com_espaco_partido_em_pedacos(tmp_path, capsys):
    """Caminho digitado sem aspas: o cmd entrega um argumento por pedaço."""
    pasta = tmp_path / "uma pasta com espaco"
    cfg = escrever_comtrade(pasta, nome="com espaco", n=32)
    assert inspecionar.main(str(cfg).split(" ")) == 0
    assert "SE TESTE" in capsys.readouterr().out


def test_arquivo_inexistente_explica(tmp_path, capsys):
    assert inspecionar.main([str(tmp_path / "nao-existe.cfg")]) == 1
    assert "Nao encontrei" in capsys.readouterr().out


def test_sem_argumento_mostra_o_uso(capsys):
    assert inspecionar.main([]) == 2
    assert "uso:" in capsys.readouterr().out


def test_arquivo_que_nao_e_oscilografia(tmp_path, capsys):
    ruim = tmp_path / "qualquer.cfg"
    ruim.write_text("nao sou um comtrade", encoding="utf-8")
    assert inspecionar.main([str(ruim)]) == 1
    assert "[ERRO]" in capsys.readouterr().out
