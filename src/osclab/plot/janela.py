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

from osclab.dsp import envoltoria, fasor
from osclab.formats import conjuntos, fases
from osclab.formats.base import Record, Trecho
from osclab.plot import (
    catalogo,
    conversao,
    digitais,
    escala,
    navegacao,
    serie,
    sinais,
    unidades,
)
from osclab.plot.conversao import LADOS

#: Versão do formato do pacote da janela. Sobe quando a tela passa a depender
#: de um campo novo. Ver o comentário em `montar`.
CONTRATO = 3


def montar(registro: Record, *, de: float | None = None, ate: float | None = None,
           colunas: int = 900, lado: str = "arquivo",
           filtro: bool = False, medidas: dict[str, str] | None = None,
           digitais_pedidos: list[int] | None = None,
           extras: dict[str, list[str]] | None = None,
           ocultos: list[int] | None = None) -> dict:
    """O pacote de uma janela, pronto para o navegador.

    `filtro` vale para o registro inteiro; `medidas` é a escolha de CADA
    gráfico, pela unidade do grupo. Ver `plot/sinais.py`.

    `extras` é o que o usuário acrescentou a cada gráfico, pela unidade do
    arquivo: `{"A": ["q0:0:rms", "c3:rms"]}`. Nada entra aí sozinho — ver
    `plot/catalogo.py`.

    `ocultos` são os canais que ele TIROU do gráfico, por índice. O grupo
    continua existindo mesmo ficando vazio: é dele que sai o botão que traz o
    canal de volta, e um grupo que some leva o botão junto.
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
    # Basta UM grupo pedir envoltória para a margem ser necessária. Sinal
    # acrescentado à mão conta: componente simétrica é sempre fasor, e canal em
    # RMS também olha um ciclo para trás.
    alguma_envoltoria = (filtro
                         or any(m == "rms" for m in (medidas or {}).values())
                         or any(lista for lista in (extras or {}).values()))
    margem = (por_ciclo - 1) if alguma_envoltoria and por_ciclo > 0 else 0
    j0 = max(i0 - margem, 0)
    janela_de_trechos = _trechos_recortados(trechos, j0, i1)

    escondidos = set(ocultos or ())
    grupos: dict[str, list] = {}
    for canal in registro.analog_channels:
        # O grupo nasce mesmo sem canal visível — ver a docstring.
        alvo = grupos.setdefault(canal.unit.strip(), [])
        if canal.index not in escondidos:
            alvo.append(canal)

    # O prefixo `k` sai do registro inteiro, nunca da janela: se saísse da
    # janela, o eixo trocaria de kA para A ao ampliar a pré-falta.
    escalas = unidades.por_unidade(registro, lado)
    # O apelido do conjunto (AT/BT, W/X) entra no nome do sinal. Num relé de
    # trafo, sem ele dois canais diferentes se chamariam `IA`.
    rotulos = conjuntos.rotulos_por_canal(registro)

    disponiveis = catalogo.de_registro(registro, lado)
    catalogo_por_id = {s.id: s for s in disponiveis}

    saida_grupos = []
    for unidade, canais in grupos.items():
        # A envoltória é calculada com o ciclo de história e recortada depois.
        # Calcular só dentro da janela daria uma curva que começa errada.
        grandeza = sinais.por_grupo(unidade, filtro, medidas)
        com_margem = registro.analog[[c.index for c in canais], j0:i1]
        bruto = envoltoria.calcular(com_margem, janela_de_trechos,
                                    registro.line_frequency, grandeza)[:, i0 - j0:]
        divisor, mostrada = escalas.get(unidade, (1.0, unidade))

        convertidos = []
        for k, canal in enumerate(canais):
            v, lado_final, foi = conversao.converter(bruto[k], canal, lado)
            convertidos.append((canal, v / divisor, lado_final, foi))

        # Os sinais acrescentados à mão. Os da MESMA unidade dividem o eixo da
        # esquerda com os canais — mesma escala, mesma leitura. Os de outra
        # unidade vão para um segundo eixo, à direita.
        pedidos = [catalogo_por_id[i] for i in (extras or {}).get(unidade, [])
                   if i in catalogo_por_id]
        unidade_dir = next((s.unidade for s in pedidos if s.unidade != unidade), None)
        avisos = []
        acrescentados = []
        for s_extra in pedidos:
            if s_extra.unidade not in (unidade, unidade_dir):
                # Um terceiro eixo não existe: a tela tem dois lados, e o
                # terceiro sinal seria desenhado numa escala que não está
                # escrita em lugar nenhum.
                avisos.append(f"{s_extra.nome} ({s_extra.unidade_mostrada}) não "
                              "cabe: o gráfico já tem dois eixos.")
                continue
            valores = catalogo.serie(registro, s_extra, j0, i1,
                                     janela_de_trechos, lado,
                                     escalas)[i0 - j0:]
            acrescentados.append((s_extra, valores,
                                  "dir" if s_extra.unidade != unidade else "esq"))

        pilha = np.vstack([v for _, v, _, _ in convertidos]) if convertidos else \
            np.empty((0, tempo.size))
        pilha_esq = np.vstack([pilha] + [v for _, v, e in acrescentados if e == "esq"]) \
            if any(e == "esq" for _, _, e in acrescentados) else pilha
        reducao = serie.reduzir(tempo, pilha_esq, colunas)

        finitos = reducao.valores[np.isfinite(reducao.valores)]
        minimo = float(finitos.min()) if finitos.size else -1.0
        maximo = float(finitos.max()) if finitos.size else 1.0
        base, topo = escala.faixa(minimo, maximo)
        intervalo = topo - base

        eixo_dir = None
        reducao_dir = None
        pela_direita = [v for _, v, e in acrescentados if e == "dir"]
        if pela_direita:
            reducao_dir = serie.reduzir(tempo, np.vstack(pela_direita), colunas)
            f_dir = reducao_dir.valores[np.isfinite(reducao_dir.valores)]
            base_d, topo_d = escala.faixa(float(f_dir.min()) if f_dir.size else -1.0,
                                          float(f_dir.max()) if f_dir.size else 1.0)
            _, mostrada_dir = escalas.get(unidade_dir, (1.0, unidade_dir))
            eixo_dir = {
                "unidade": mostrada_dir,
                "unidade_do_arquivo": unidade_dir,
                "minimo": base_d,
                "maximo": topo_d,
                "marcacoes": escala.marcacoes(base_d, topo_d, alvo=4),
                "casas": escala.casas_decimais(topo_d - base_d),
            }

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
                # O nome do SINAL: o do canal mais o que foi feito com ele.
                # `IA` e `IA RMS` são coisas diferentes e a tela diz qual é qual.
                "sinal": sinais.nome(fases.padrao(canal), grandeza,
                                     rotulos.get(canal.index, "")),
                "unidade": mostrada,
                "fase": fase,
                "fase_origem": str(origem),
                "lado": lado_final,
                "convertido": foi,
                "relacao": round(conversao.relacao(canal), 4),
                "serie": serie.arredondar(reducao.valores[k], intervalo),
            })

        # As séries dos acrescentados saem das MESMAS reduções: quem está no
        # eixo da esquerda foi reduzido junto com os canais, quem está na
        # direita tem a sua. Reduzir de novo, à parte, daria colunas com outro
        # alinhamento — e duas curvas do mesmo instante em x diferentes.
        extras_json = []
        k_esq = len(convertidos)
        k_dir = 0
        for s_extra, _, eixo in acrescentados:
            if eixo == "esq":
                valores = serie.arredondar(reducao.valores[k_esq], intervalo)
                k_esq += 1
                unidade_do_sinal = mostrada
            else:
                valores = serie.arredondar(reducao_dir.valores[k_dir],
                                           eixo_dir["maximo"] - eixo_dir["minimo"])
                k_dir += 1
                unidade_do_sinal = eixo_dir["unidade"]
            extras_json.append({
                "id": s_extra.id,
                "sinal": s_extra.nome,
                "familia": s_extra.familia,
                "origem": s_extra.origem,
                "descricao": s_extra.descricao,
                "unidade": unidade_do_sinal,
                "eixo": eixo,
                "serie": valores,
            })

        saida_grupos.append({
            "unidade": mostrada,
            "unidade_do_arquivo": unidade,
            "grandeza": grandeza,
            "medida": "rms" if grandeza in ("rms", "fundamental") else "instantaneo",
            "divisor": divisor,
            "titulo": serie.titulo_do_grupo(mostrada),
            "minimo": base,
            "maximo": topo,
            "marcacoes": escala.marcacoes(base, topo, alvo=4),
            "casas": escala.casas_decimais(intervalo),
            "canais": canais_json,
            # O que o usuário acrescentou a ESTE gráfico, e o segundo eixo
            # quando algum deles veio de outra unidade.
            "extras": extras_json,
            "eixo_dir": eixo_dir,
            "avisos": avisos,
        })

    # Os digitais: por padrão só os que MUDARAM, na ordem em que mudaram — a
    # tela passa a contar a sequência do evento de cima para baixo. Ver
    # `plot/digitais.py` para por que esse é o único critério que se sustenta
    # num relé de 5760 entradas binárias.
    todos = digitais.resumos(registro)
    escolhidos = (digitais.escolhidos_por_padrao(registro)
                  if digitais_pedidos is None else list(digitais_pedidos))

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
        "grupos": saida_grupos,
        "ocultos": sorted(escondidos),
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
        "digitais": {
            "tiras": digitais.tiras(registro, i0, i1, colunas, escolhidos),
            "tempo": digitais.tempo_das_colunas(registro, i0, i1, colunas),
            # A lista inteira vai junto para a busca funcionar sem outro
            # pedido: é nome e um inteiro por canal, barato até nos 5760 de um
            # SEL-487E, e evita uma viagem a cada letra digitada.
            "disponiveis": [{"indice": r.indice, "nome": r.nome,
                             "mudou": r.mudou,
                             "instante": r.instante} for r in todos],
            "mudaram": sum(1 for r in todos if r.mudou),
            "escolhidos": escolhidos,
        },
    }


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
