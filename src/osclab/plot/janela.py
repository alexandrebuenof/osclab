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

from osclab.dsp import fasor
from osclab.formats import fases
from osclab.formats.base import Record, Trecho
from osclab.plot import (
    catalogo,
    conversao,
    digitais,
    escala,
    navegacao,
    paineis,
    serie,
    sinais,
    unidades,
)
from osclab.plot.conversao import LADOS

#: Versão do formato do pacote da janela. Sobe quando a tela passa a depender
#: de um campo novo. Ver o comentário em `montar`.
CONTRATO = 5


def montar(registro: Record, *, de: float | None = None, ate: float | None = None,
           colunas: int = 900, lado: str = "arquivo", filtro: bool = False,
           layout: list | None = None) -> dict:
    """O pacote de uma janela, pronto para o navegador.

    `layout` é a lista de painéis que a tela montou (ver `plot/paineis.py`).
    Sem ela, sai o arranjo padrão: um painel por unidade do arquivo e um com os
    digitais que mudaram.

    `filtro` vale para o registro inteiro; a medida (instantâneo × RMS) é de
    cada painel. Os dois juntos decidem o que um canal do IED vira ali dentro —
    ver `catalogo.efetivo`.
    """
    if lado not in LADOS:
        lado = "arquivo"
    if lado == "arquivo":
        lado = conversao.lado_natural(registro)
    filtro = sinais.aplicavel(filtro, registro.filtering)

    t0, t1 = navegacao.extensao(registro)
    de, ate = navegacao.limitar(t0, t1, de, ate, navegacao.passo(registro))

    i0, i1 = serie.recortar(registro, de, ate)
    tempo = registro.time[i0:i1]

    # As curvas de fundamental e de RMS olham um ciclo PARA TRÁS. Sem puxar esse
    # ciclo a mais, o começo da janela na tela ficaria sem curva a cada gesto —
    # e o usuário veria um pedaço em branco que aparece e some conforme arrasta.
    #
    # O ciclo é medido em AMOSTRAS, e num registro de taxa variável isso muda de
    # trecho para trecho. A margem usa o maior deles: sobrar história é de
    # graça, faltar deixa buraco na tela.
    trechos = registro.trechos
    por_ciclo = max((fasor.amostras_por_ciclo(t.taxa_hz, registro.line_frequency)
                     for t in trechos), default=0)
    margem = (por_ciclo - 1) if por_ciclo > 0 else 0
    j0 = max(i0 - margem, 0)
    janela_de_trechos = _trechos_recortados(trechos, j0, i1)

    # O prefixo `k` sai do registro inteiro, nunca da janela: se saísse da
    # janela, o eixo trocaria de kA para A ao ampliar a pré-falta.
    escalas = unidades.por_unidade(registro, lado)
    disponiveis = catalogo.de_registro(registro, lado)
    por_id = {x.id: x for x in disponiveis}

    arranjo = layout if layout is not None else paineis.padrao(registro, lado)
    tempo_digitais = digitais.tempo_das_colunas(registro, i0, i1, colunas)
    todos_digitais = digitais.resumos(registro)

    saida = []
    for painel in arranjo:
        if painel.tipo == paineis.DIGITAL:
            saida.append(_painel_digital(registro, painel, i0, i1, colunas))
        else:
            saida.append(_painel_analogico(
                registro, painel, por_id, escalas, lado, filtro,
                tempo, j0, i0, i1, janela_de_trechos, colunas))

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
        # A versão do FORMATO deste pacote. A tela compara com a dela e avisa
        # quando não batem — é o que pega o caso de o servidor estar rodando
        # uma versão antiga, que já custou três rodadas de "não vi a mudança":
        # os `.py` só são lidos quando o programa sobe, e o navegador recarrega
        # o `.js` sozinho. Suba este número sempre que o formato mudar.
        "contrato": CONTRATO,
        "de": t0,
        "ate": t1,
        "limite_de": limite_de,
        "limite_ate": limite_ate,
        "inteiro": navegacao.inteiro(limite_de, limite_ate, t0, t1),
        "lado_pedido": lado,
        "filtro": filtro,
        # O veredito de bruto × filtrado. A tela usa para duas coisas: escrever
        # na tira o que o arquivo é, e TRAVAR o botão do filtro quando o relé
        # já filtrou — filtrar de novo só acrescentaria mais um ciclo de atraso.
        "filtragem": str(registro.filtering),
        "filtragem_origem": str(registro.filtering_source),
        "amostras_da_janela_do_fasor": int(por_ciclo),
        # Taxa variável não é erro, mas muda como se lê o gráfico: cada trecho
        # tem a sua janela de um ciclo, e há um pedaço sem curva em cada
        # fronteira. A tela avisa.
        "taxa_variavel": bool(registro.taxa_variavel),
        "trechos": [{"de": float(registro.time[t.inicio]),
                     "ate": float(registro.time[min(t.fim, registro.n_samples) - 1]),
                     "taxa_hz": round(t.taxa_hz, 3)} for t in trechos],
        "amostras_na_janela": int(i1 - i0),
        "reduzido": bool(tempo.size > colunas * serie.LIMITE_SEM_REDUZIR),
        "tempo": [round(float(x), 9) for x in tempo_saida],
        "marcacoes_tempo": escala.marcacoes(t0, t1, alvo=6),
        "disparo_s": _disparo(registro),
        "paineis": saida,
        # Tudo que se PODE acrescentar, para a tela montar a busca sem precisar
        # de outra chamada. O nome de cada sinal nasce aqui, no Python, porque
        # é identidade: o mesmo nome tem que valer na legenda, na tabelinha e
        # no relatório. Ver `plot/catalogo.py`.
        "catalogo": [{"id": x.id, "nome": x.nome, "unidade": x.unidade,
                      "unidade_mostrada": x.unidade_mostrada,
                      "familia": x.familia, "grandeza": x.grandeza,
                      "descricao": x.descricao, "origem": x.origem,
                      "fundamental": x.fundamental,
                      "fundamental_origem": x.fundamental_origem,
                      "canal": x.canal,
                      "grandeza_do_canal": x.grandeza_do_canal}
                     for x in disponiveis],
        # Os digitais do REGISTRO — a lista inteira, para a busca. Quais estão
        # na tela é assunto de cada painel.
        "digitais_disponiveis": [{"indice": r.indice, "nome": r.nome,
                                  "mudou": r.mudou, "instante": r.instante}
                                 for r in todos_digitais],
        "digitais_mudaram": sum(1 for r in todos_digitais if r.mudou),
        "tempo_digitais": tempo_digitais,
    }


def _painel_digital(registro: Record, painel, i0: int, i1: int,
                    colunas: int) -> dict:
    """Um painel de tiras digitais."""
    indices = paineis.indices_digitais(painel)
    return {
        "id": painel.id,
        "tipo": paineis.DIGITAL,
        "nome": painel.nome or "Digitais",
        "do_padrao": painel.do_padrao,
        "sinais_pedidos": [str(k) for k in indices],
        "tiras": digitais.tiras(registro, i0, i1, colunas, indices),
    }


def _painel_analogico(registro: Record, painel, por_id: dict, escalas: dict,
                      lado: str, filtro: bool, tempo, j0: int, i0: int, i1: int,
                      janela_de_trechos, colunas: int) -> dict:
    """Um painel de ondas: os sinais, as duas escalas e os avisos.

    A unidade do painel é a do PRIMEIRO sinal que entrou nele — não há
    unidade "do painel" decidida de fora. Quem vier depois com outra unidade
    vai para o eixo da direita; um terceiro tipo de unidade é recusado, porque
    a tela tem dois lados e o terceiro seria desenhado numa escala que não
    está escrita em lugar nenhum.
    """
    pedidos = []
    for identidade in painel.sinais:
        alvo = catalogo.efetivo(identidade, painel.medida, filtro, por_id)
        if alvo is not None:
            pedidos.append((identidade, alvo))

    unidade_esq = pedidos[0][1].unidade if pedidos else ""
    unidade_dir = next((s.unidade for _, s in pedidos if s.unidade != unidade_esq),
                       None)

    avisos, escolhidos = [], []
    for identidade, alvo in pedidos:
        if alvo.unidade not in (unidade_esq, unidade_dir):
            avisos.append(f"{alvo.nome} ({alvo.unidade_mostrada}) não cabe: "
                          "o gráfico já tem dois eixos.")
            continue
        valores = catalogo.serie(registro, alvo, j0, i1, janela_de_trechos,
                                 lado, escalas)[i0 - j0:]
        escolhidos.append((identidade, alvo, valores,
                           "dir" if alvo.unidade != unidade_esq else "esq"))

    def faixa(quais):
        if not quais:
            return None
        pilha = np.vstack([v for _, _, v, _ in quais])
        reducao = serie.reduzir(tempo, pilha, colunas)
        finitos = reducao.valores[np.isfinite(reducao.valores)]
        base, topo = escala.faixa(float(finitos.min()) if finitos.size else -1.0,
                                  float(finitos.max()) if finitos.size else 1.0)
        return reducao, base, topo

    pela_esquerda = [x for x in escolhidos if x[3] == "esq"]
    pela_direita = [x for x in escolhidos if x[3] == "dir"]
    esq = faixa(pela_esquerda)
    dir_ = faixa(pela_direita)

    base, topo = (esq[1], esq[2]) if esq else (-1.0, 1.0)
    intervalo = topo - base
    _, mostrada_esq = escalas.get(unidade_esq, (1.0, unidade_esq))

    eixo_dir = None
    if dir_:
        _, mostrada_dir = escalas.get(unidade_dir, (1.0, unidade_dir))
        eixo_dir = {
            "unidade": mostrada_dir,
            "unidade_do_arquivo": unidade_dir,
            "minimo": dir_[1],
            "maximo": dir_[2],
            "marcacoes": escala.marcacoes(dir_[1], dir_[2], alvo=4),
            "casas": escala.casas_decimais(dir_[2] - dir_[1]),
        }

    canais = {c.index: c for c in registro.analog_channels}
    sinais_json = []
    k_esq = k_dir = 0
    for identidade, alvo, _, eixo in escolhidos:
        if eixo == "esq":
            valores = serie.arredondar(esq[0].valores[k_esq], intervalo)
            k_esq += 1
            unidade_mostrada = mostrada_esq
        else:
            valores = serie.arredondar(dir_[0].valores[k_dir],
                                       eixo_dir["maximo"] - eixo_dir["minimo"])
            k_dir += 1
            unidade_mostrada = eixo_dir["unidade"]

        canal = canais.get(alvo.canal) if alvo.canal >= 0 else None
        fase, _origem = fases.da_canal(canal) if canal is not None else ("", "")
        lado_final = lado
        convertido = True
        if canal is not None:
            _, lado_final, convertido = conversao.converter(
                np.zeros(1), canal, lado)

        sinais_json.append({
            # O id PEDIDO é a identidade do sinal no painel: é por ele que a
            # tela o tira, o seleciona e o casa com a leitura do cursor. O
            # efetivo é o que foi calculado depois dos botões.
            "id": identidade,
            "id_efetivo": alvo.id,
            "familia": alvo.familia,
            # O nome do ARQUIVO, quando há canal por trás; e o nome NOSSO. Os
            # dois aparecem na tela, para ficar claro o que é qual.
            "nome": canal.name if canal is not None else "",
            # O nome NOSSO: para um canal do IED é a fundamental que
            # vinculamos (`IA`); para uma conta nossa é o nome dela
            # (`IA RMS`, `3I0`). Vazio quando não reconhecemos o canal — o
            # OscLab não batiza o que não conseguiu identificar.
            "sinal": (alvo.fundamental if alvo.familia == "canal" else alvo.nome),
            "padrao": (alvo.fundamental if alvo.familia == "canal" else alvo.nome),
            "descricao": alvo.descricao,
            "indice": canal.index if canal is not None else None,
            "fase": fase,
            "unidade": unidade_mostrada,
            "eixo": eixo,
            "lado": lado_final,
            "convertido": convertido,
            "serie": valores,
        })

    return {
        "id": painel.id,
        "tipo": paineis.ANALOGICO,
        # Enquanto o usuário não renomeou, o nome sai da unidade — e por isso
        # acompanha a troca de lado, que muda `A` para `kA`.
        "nome": (serie.titulo_do_grupo(mostrada_esq)
                 if painel.do_padrao or not painel.nome else painel.nome),
        "do_padrao": painel.do_padrao,
        "medida": painel.medida,
        "medida_aplicavel": _medida_aplicavel(painel, por_id),
        "unidade": mostrada_esq,
        "unidade_do_arquivo": unidade_esq,
        "minimo": base,
        "maximo": topo,
        "marcacoes": escala.marcacoes(base, topo, alvo=4) if esq else [],
        "casas": escala.casas_decimais(intervalo),
        "eixo_dir": eixo_dir,
        "avisos": avisos,
        "sinais": sinais_json,
    }


def _medida_aplicavel(painel, por_id: dict) -> bool:
    """Se o botão instantâneo/RMS tem em que pegar neste painel.

    Ele só manda nos canais do IED — ver `catalogo.efetivo`. Num painel que só
    tem componentes simétricas, que são fasor e **só existem em eficaz**,
    clicar nele não muda número nenhum: o rótulo da tabelinha troca de `valor`
    para `RMS` e os valores ficam iguais. Botão que acende e não faz nada é
    pior que botão travado — o usuário acredita que a tabela mudou.

    Painel VAZIO é o único caso em que ele continua solto mesmo sem ninguém
    para mandar: ali ainda não há contradição nenhuma, e travar um controle
    antes de haver conteúdo é dizer "não pode" sem ter por quê.
    """
    if not painel.sinais:
        return True
    return any(identidade in por_id and por_id[identidade].familia == "canal"
               for identidade in painel.sinais)


def _trechos_recortados(trechos, j0: int, i1: int) -> list:
    """Os trechos que cruzam `[j0, i1)`, com os índices contados a partir de j0.

    A envoltória é calculada sobre uma fatia do registro; ela precisa saber
    onde estão as fronteiras de taxa DENTRO dessa fatia, senão calcularia a
    janela toda com uma taxa só e erraria depois da fronteira, em silêncio.
    """
    recortados = []
    for trecho in trechos:
        inicio, fim = max(trecho.inicio, j0), min(trecho.fim, i1)
        if fim > inicio:
            recortados.append(Trecho(inicio - j0, fim - j0, trecho.taxa_hz))
    return recortados


def _disparo(registro: Record) -> float | None:
    """O instante do disparo em segundos, na mesma referência de `tempo`."""
    if registro.trigger_time is None or registro.start_time is None:
        return None
    return round((registro.trigger_time - registro.start_time).total_seconds(), 9)
