"""Monta o que a tela precisa para desenhar uma janela do registro.

Tudo que decide número — qual janela, quais canais, que escala, que faixa
vertical, onde ficam as marcações — acontece AQUI, no Python, com teste. O
navegador recebe listas prontas e só desenha.

A conversão primário × secundário (em `plot/conversao.py`) é aplicada aqui, e
por um motivo de domínio: a relação de TC/TP vem do `.cfg`, e é ela que decide a
faixa vertical do gráfico. Converter no navegador significaria recalcular a
escala lá também — duas implementações da mesma conta, que é como elas
divergem.
"""

from __future__ import annotations

import numpy as np

from osclab.formats import fases
from osclab.formats.base import Record
from osclab.plot import conversao, escala, navegacao, serie, unidades
from osclab.plot.conversao import LADOS


def montar(registro: Record, *, de: float | None = None, ate: float | None = None,
           colunas: int = 900, lado: str = "arquivo") -> dict:
    """O pacote de uma janela, pronto para o navegador."""
    if lado not in LADOS:
        lado = "arquivo"
    if lado == "arquivo":
        lado = conversao.lado_natural(registro)

    t0, t1 = navegacao.extensao(registro)
    de, ate = navegacao.limitar(t0, t1, de, ate, navegacao.passo(registro))

    i0, i1 = serie.recortar(registro, de, ate)
    tempo = registro.time[i0:i1]

    grupos: dict[str, list] = {}
    for canal in registro.analog_channels:
        grupos.setdefault(canal.unit.strip(), []).append(canal)

    # O prefixo `k` sai do registro inteiro, nunca da janela: se saísse da
    # janela, o eixo trocaria de kA para A ao ampliar a pré-falta.
    escalas = unidades.por_unidade(registro, lado)

    saida_grupos = []
    for unidade, canais in grupos.items():
        bruto = registro.analog[[c.index for c in canais], i0:i1]
        divisor, mostrada = escalas.get(unidade, (1.0, unidade))

        convertidos = []
        for k, canal in enumerate(canais):
            v, lado_final, foi = conversao.converter(bruto[k], canal, lado)
            convertidos.append((canal, v / divisor, lado_final, foi))

        pilha = np.vstack([v for _, v, _, _ in convertidos]) if convertidos else \
            np.empty((0, tempo.size))
        reducao = serie.reduzir(tempo, pilha, colunas)

        finitos = reducao.valores[np.isfinite(reducao.valores)]
        minimo = float(finitos.min()) if finitos.size else -1.0
        maximo = float(finitos.max()) if finitos.size else 1.0
        base, topo = escala.faixa(minimo, maximo)
        intervalo = topo - base

        canais_json = []
        for k, (canal, _, lado_final, foi) in enumerate(convertidos):
            fase, origem = fases.da_canal(canal)
            canais_json.append({
                # O índice do canal no REGISTRO, não na posição do grupo: a
                # tela usa isto para casar cada linha com a leitura do cursor,
                # que vem na ordem do arquivo. Casar por posição erraria em
                # qualquer registro que intercale corrente e tensão.
                "indice": canal.index,
                "nome": canal.name,
                # O nome do ARQUIVO acima; o nome do SOFTWARE aqui. Os dois
                # aparecem na tela, para ficar claro o que é qual.
                "padrao": fases.padrao(canal),
                "unidade": mostrada,
                "fase": fase,
                "fase_origem": str(origem),
                "lado": lado_final,
                "convertido": foi,
                "relacao": round(conversao.relacao(canal), 4),
                "serie": serie.arredondar(reducao.valores[k], intervalo),
            })

        saida_grupos.append({
            "unidade": mostrada,
            "unidade_do_arquivo": unidade,
            "divisor": divisor,
            "titulo": serie.titulo_do_grupo(mostrada),
            "minimo": base,
            "maximo": topo,
            "marcacoes": escala.marcacoes(base, topo, alvo=4),
            "casas": escala.casas_decimais(intervalo),
            "canais": canais_json,
        })

    # O eixo do tempo é reduzido do mesmo jeito que os canais, para os dois
    # ficarem com o mesmo comprimento. Um canal fictício de zeros serve: o que
    # interessa desta chamada é só o vetor de tempo.
    tempo_saida = serie.reduzir(tempo, np.zeros((1, tempo.size)), colunas).tempo

    # Daqui para baixo, t0/t1 são as bordas da JANELA; limite_de/limite_ate são
    # as bordas do REGISTRO. A tela precisa das duas: uma para desenhar, outra
    # para saber se ainda há para onde arrastar.
    #
    # t0/t1 são a janela PEDIDA, não o instante da primeira e da última amostra
    # dentro dela. Parece o mesmo e não é: a tela devolve estes números no gesto
    # seguinte, e arredondar para a amostra mais próxima a cada ida e volta
    # encolheria a janela uma amostra por gesto — o desenho iria escorregando
    # sem ninguém entender por quê.
    limite_de, limite_ate = navegacao.extensao(registro)
    t0, t1 = float(de), float(ate)

    return {
        "de": t0,
        "ate": t1,
        "limite_de": limite_de,
        "limite_ate": limite_ate,
        "inteiro": navegacao.inteiro(limite_de, limite_ate, t0, t1),
        "lado_pedido": lado,
        "amostras_na_janela": int(i1 - i0),
        "reduzido": bool(tempo.size > colunas * serie.LIMITE_SEM_REDUZIR),
        "tempo": [round(float(x), 9) for x in tempo_saida],
        "marcacoes_tempo": escala.marcacoes(t0, t1, alvo=6),
        "disparo_s": _disparo(registro),
        "grupos": saida_grupos,
    }


def _disparo(registro: Record) -> float | None:
    """O instante do disparo em segundos, na mesma referência de `tempo`."""
    if registro.trigger_time is None or registro.start_time is None:
        return None
    return round((registro.trigger_time - registro.start_time).total_seconds(), 9)
