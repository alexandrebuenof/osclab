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
from osclab.formats import conjuntos, fases
from osclab.formats.base import Record, Trecho
from osclab.plot import alfa as alfa_mod
from osclab.plot import (
    catalogo,
    conversao,
    digitais,
    escala,
    fasorial,
    imas,
    navegacao,
    paineis,
    serie,
    sinais,
    triangulo,
    unidades,
)
from osclab.plot import complexo as complexo_mod
from osclab.plot import diferencial as diferencial_mod
from osclab.plot import harmonicos as harmonicos_mod
from osclab.plot import impedancia as impedancia_mod
from osclab.plot.conversao import LADOS

#: Versão do formato do pacote da janela. Sobe quando a tela passa a depender
#: de um campo novo. Ver o comentário em `montar`.
CONTRATO = 24


def montar(registro: Record, *, de: float | None = None, ate: float | None = None,
           colunas: int = 900, lado: str = "arquivo", filtro: bool = False,
           layout: list | None = None, contas: list | None = None,
           ajustes: dict | None = None, outros: list | None = None) -> dict:
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
    # A margem conta a janela DE MEDIDA, que com taxa fracionária traz uma ou
    # duas amostras a mais que `por_ciclo` — ver `fasor.pesos_do_ciclo`.
    # Sobrar história é de graça; faltar deixa buraco na tela.
    largura = max((fasor.pesos_do_ciclo(
        fasor.ciclo_em_amostras(t.taxa_hz, registro.line_frequency)).size
        for t in trechos if t.taxa_hz > 0), default=0)
    margem = max(largura, por_ciclo) - 1 if por_ciclo > 0 else 0
    j0 = max(i0 - margem, 0)
    janela_de_trechos = _trechos_recortados(trechos, j0, i1)

    # O prefixo `k` sai do registro inteiro, nunca da janela: se saísse da
    # janela, o eixo trocaria de kA para A ao ampliar a pré-falta.
    escalas = unidades.por_unidade(registro, lado)
    disponiveis = catalogo.de_registro(registro, lado, contas)
    por_id = {x.id: x for x in disponiveis}

    arranjo = layout if layout is not None else paineis.padrao(registro, lado)
    tempo_digitais = digitais.tempo_das_colunas(registro, i0, i1, colunas)
    todos_digitais = digitais.resumos(registro)

    saida = []
    for painel in arranjo:
        if painel.tipo == paineis.DIGITAL:
            saida.append(_painel_digital(registro, painel, i0, i1, colunas))
        elif painel.tipo == paineis.FASORIAL:
            # Sem série nenhuma: o diagrama é de UM instante, e os números dele
            # vêm da leitura do cursor. Ver `plot/fasorial.py`.
            saida.append(fasorial.montar(registro, painel, por_id, escalas,
                                         lado))
        elif painel.tipo == paineis.TRIANGULO:
            # Também de UM instante, e também alimentado pela leitura do
            # cursor — mas os seis sinais saem do VÍNCULO, não da lista do
            # painel. Ver `plot/triangulo.py`.
            saida.append(triangulo.montar(registro, painel, por_id, escalas,
                                          lado))
        elif painel.tipo == paineis.IMPEDANCIA:
            # O único painel que é uma TRAJETÓRIA e não um instante: ele
            # precisa da janela inteira, e dos ajustes do relé para saber
            # onde ficam as zonas. Ver `plot/impedancia.py`.
            saida.append(impedancia_mod.montar(registro, painel, ajustes or {},
                                               lado, i0, i1 - 1))
        elif painel.tipo == paineis.COMPLEXO:
            # O caminho do fasor, do começo do registro inteiro — não da
            # janela: a bolinha anda até o cursor, e o cursor pode estar
            # longe do pedaço ampliado. Ver `plot/complexo.py`.
            saida.append(complexo_mod.montar(registro, painel, por_id,
                                             escalas, lado))
        elif painel.tipo == paineis.ALFA:
            # Também do registro inteiro, pela mesma razão do complexo: o
            # ponto anda até o cursor sem ida ao servidor. Ver `plot/alfa.py`.
            saida.append(alfa_mod.montar(registro, painel, outros, ajustes))
        elif painel.tipo == paineis.DIFERENCIAL:
            # Do registro inteiro, como o alfa, e com os ajustes do relé: o
            # gráfico só sai quando todos têm valor. Ver `plot/diferencial.py`.
            saida.append(diferencial_mod.montar(registro, painel, ajustes))
        elif painel.tipo == paineis.HARMONICOS:
            # Idem: as barras são de UM instante e vêm da leitura do cursor.
            saida.append(harmonicos_mod.montar(registro, painel, por_id,
                                               escalas, lado))
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
        # O instante em que o registro deixou de repetir o ciclo anterior, para
        # o ímã dos cursores. É PALPITE, e a tela diz isso ao mostrá-lo — ver
        # `plot/imas.py`. `None` quando não há pré-falta com que calibrar.
        "inicio_da_perturbacao": _instante(registro,
                                           imas.inicio_da_perturbacao(registro)),
        # A frequência NOMINAL do registro. A tela escreve `60 Hz` em alguns
        # rótulos, e num arquivo de 50 Hz esses rótulos estariam errados.
        "frequencia_hz": float(registro.line_frequency),
        # Os canais que o arranjo padrão NÃO desenhou por estarem sem sinal.
        # Vão para a tela porque esconder tem que ser visível e reversível: um
        # trafo energizado por um lado só tem a outra trinca em zero
        # legitimamente, e esse zero é informação. Ver `analysis/presenca.py`.
        "sem_sinal": _sem_sinal(registro, saida),
        "paineis": saida,
        # Tudo que se PODE acrescentar, para a tela montar a busca sem precisar
        # de outra chamada. O nome de cada sinal nasce aqui, no Python, porque
        # é identidade: o mesmo nome tem que valer na legenda, na tabelinha e
        # no relatório. Ver `plot/catalogo.py`.
        "catalogo": [{"id": x.id, "nome": x.nome,
                      # O que o botão do filtro faz com ESTE sinal: o id que
                      # o gráfico desenha no lugar dele. Vem calculado daqui
                      # para a tela poder marcar a caixinha na coluna em que o
                      # sinal realmente está e escrever o nome que a legenda
                      # escreve — sem repetir a conta no JavaScript, que é
                      # como as duas divergiriam. Ver `catalogo.efetivo`.
                      #
                      # Um por MEDIDA, porque a medida é de cada painel: num
                      # gráfico em RMS o canal `IAW` desenha `IAW · 60Hz RMS`,
                      # e a lista daquele gráfico tem que dizer isso.
                      "efetivo": {m: catalogo.efetivo(x.id, m, filtro, por_id).id
                                  for m in sinais.MEDIDAS},
                      "unidade": x.unidade,
                      "unidade_mostrada": x.unidade_mostrada,
                      "familia": x.familia, "grandeza": x.grandeza,
                      "descricao": x.descricao, "origem": x.origem,
                      "fundamental": x.fundamental,
                      "fundamental_origem": x.fundamental_origem,
                      "canal": x.canal,
                      "grandeza_do_canal": x.grandeza_do_canal,
                      "sem_sinal": bool(x.sem_sinal),
                      # A LINHA e o BLOCO: é com estes três que a tela monta a
                      # matriz de canais × contas e os blocos dela, em vez de
                      # uma lista de cento e vinte nomes. Ver `plot/catalogo`.
                      "linha": x.linha, "grupo": x.grupo, "coluna": x.coluna,
                      # `componente`, `modulo` ou `misto` — só para conta do
                      # usuário. É o que diz à tela se a conta TEM onda e
                      # contínua, ou se tem uma folha só. Ver `catalogo.Sinal`.
                      "dominio": x.dominio,
                      # A expressão da conta do usuário. A tela usa para
                      # separar «o OscLab deduziu» de «você escreveu» — as
                      # duas são `familia: "conta"` aqui dentro.
                      "expressao": x.expressao,
                      "bloco": x.bloco, "motivo": x.motivo, "nota": x.nota,
                      "aviso": x.aviso,
                      # Só a componente simétrica traz isto: é o único sinal
                      # cuja origem é palpite, e o único que a tela corrige.
                      "conjunto": x.conjunto}
                     for x in disponiveis],
        # Os VÍNCULOS de potência que o usuário fez, para o editor de grupos
        # mostrar o par e a tela saber o que oferecer. Ver
        # `Record.vinculos_de_potencia` — o programa não deduz nenhum.
        "vinculos_de_potencia": {
            str(k): {"com": str(v.get("com") or ""),
                     "base": str(v.get("base") or "fase")}
            for k, v in (getattr(registro, "vinculos_de_potencia", None)
                         or {}).items()},
        # Os conjuntos trifásicos do registro, com a chave estável de cada um
        # — é por ela que o vínculo é gravado, e não pelo `G1`, que é posição.
        "conjuntos": [{"chave": c.nome, "rotulo": c.rotulo,
                       "grandeza": c.grandeza, "unidade": c.unidade,
                       "sem_sinal": bool(c.sem_sinal),
                       # Contra o quê o relé mediu: `fase` ou `linha`. Vai
                       # junto porque é o que o vínculo de potência precisa
                       # saber, e porque a tela estava CHUTANDO isso a partir
                       # do nome do conjunto — com a trinca sabendo, o chute
                       # vira pergunta respondida.
                       "base": c.base,
                       "canais": [int(x) for x in c.abc]}
                      for c in conjuntos.de_registro(registro)],
        # Onde mora a energia de cada LINHA do catálogo, para a barrinha do
        # menu: `{linha: [60 Hz, harmônicos, contínua]}`, frações somando 1.
        # Linha sem onda com que medir não entra, e a tela não desenha barra.
        # Ver `catalogo.energia_das_linhas` — e repare que é MEDIDO, não
        # herdado do veredito de `filtering`.
        "energia": {k: [round(f, 4) for f in v] for k, v in
                    catalogo.energia_das_linhas(registro, disponiveis, lado,
                                                escalas, trechos).items()},
        # Os digitais do REGISTRO — a lista inteira, para a busca. Quais estão
        # na tela é assunto de cada painel.
        "digitais_disponiveis": [{"indice": r.indice, "nome": r.nome,
                                  "mudou": r.mudou, "instante": r.instante,
                                  "sem_placa": r.sem_placa}
                                 for r in todos_digitais],
        "digitais_mudaram": sum(1 for r in todos_digitais if r.mudou and not r.sem_placa),
        "digitais_sem_placa": sum(1 for r in todos_digitais if r.sem_placa),
        # Os IEDs desta aba. Com um registro só, vazio: a tela não escreve
        # letra nenhuma. Com mais de um, quem preenche é `plot/varios.py`.
        "ieds": [],
        "tempo_digitais": tempo_digitais,
    }


def _painel_digital(registro: Record, painel, i0: int, i1: int,
                    colunas: int) -> dict:
    """Um painel de tiras digitais."""
    indices = paineis.indices_digitais(painel)
    tiras = digitais.tiras(registro, i0, i1, colunas, indices)
    # Cada tira leva as suas transições, para o ímã dos cursores. Vão JUNTO da
    # tira, e não numa lista à parte, porque é assim que a tela consegue
    # obedecer só ao digital que o usuário selecionou.
    for tira in tiras:
        amostras = imas.afinar(imas.transicoes(registro, tira["indice"]),
                               i0, i1, colunas)
        tira["transicoes"] = [round(float(registro.time[k]), 9) for k in amostras]
    return {
        "id": painel.id,
        "tipo": paineis.DIGITAL,
        "nome": painel.nome or "Digitais",
        "do_padrao": painel.do_padrao,
        "sinais_pedidos": [str(k) for k in indices],
        "tiras": tiras,
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
    # Dois pedidos que os botões resolvem no MESMO sinal são uma curva só, e
    # desenhá-la duas vezes daria dois traços de cores diferentes exatamente em
    # cima um do outro — com duas entradas na legenda e duas linhas na
    # tabelinha do cursor, dizendo o mesmo número. Acontece de verdade: com o
    # filtro aceso, `IAW` e `IAW · 60Hz` são o mesmo traço.
    pedidos = []
    desenhados = set()
    for identidade in painel.sinais:
        alvo = catalogo.efetivo(identidade, painel.medida, filtro, por_id)
        if alvo is not None and alvo.id not in desenhados:
            desenhados.add(alvo.id)
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
    for identidade, alvo, serie_inteira, eixo in escolhidos:
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
            # O nome do SINAL: o do canal quando é o canal cru (`IAW`), e o
            # do canal mais a conta quando algum botão pegou (`IAW · 60Hz`).
            # Componente de sequência traz o próprio (`3I0 [1]`).
            #
            # Havia um `padrao` ao lado, com o nome NOSSO (`IA`) — a legenda
            # escrevia os dois, o do arquivo e o nosso. Desde que o nome do
            # sinal passou a ser o do arquivo, os dois campos carregavam a
            # mesma palavra, e dois campos com o mesmo valor é o começo de dois
            # campos com valores diferentes.
            "sinal": alvo.nome,
            "descricao": alvo.descricao,
            "indice": canal.index if canal is not None else None,
            "fase": fase,
            "unidade": unidade_mostrada,
            "eixo": eixo,
            "lado": lado_final,
            "convertido": convertido,
            "serie": valores,
            # Os pontos para o ímã dos cursores: os picos (crista e vale) e as
            # passagens por zero. Saem da série de RESOLUÇÃO CHEIA, antes da
            # redução por coluna de pixel — o pico da onda é uma amostra do
            # arquivo, não o extremo de um traço desenhado.
            "picos": _instantes(tempo, imas.picos(serie_inteira), colunas),
            "zeros": _instantes(tempo, imas.passagens_por_zero(serie_inteira),
                                colunas),
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
        # De que canais do arquivo saiu o que está aqui. Ver `_rodape`.
        "rodape": _rodape(registro, pedidos),
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

    Canal CONTÍNUO também não conta. Um painel só com a tensão da bateria não
    tem eficaz nenhum para mostrar — o catálogo nem oferece a variante —, e o
    botão aceso prometeria uma troca que não vai acontecer.
    """
    if not painel.sinais:
        return True
    for identidade in painel.sinais:
        alvo = por_id.get(identidade)
        if alvo is None or alvo.familia != "canal":
            continue
        if any(f"v{alvo.canal}:{g}" in por_id for g in ("rms", "fundamental")):
            return True
    return False


def _instantes(tempo, amostras, colunas: int) -> list[float]:
    """Os instantes de uma lista de amostras, afinada por coluna de pixel."""
    return [round(float(tempo[k]), 9)
            for k in imas.afinar(amostras, 0, tempo.size, colunas)]


#: O fecho do rodapé, quando o painel tem componente simétrica. Uma vez, no
#: fim — e não em cada linha, que era o molde `IA + IB + IC` da primeira
#: versão. Aquele molde mentia duas vezes: o `+` entre eficazes sugere soma de
#: módulos (três fases de 400 A somariam 1200 A, quando o 3I0 verdadeiro é
#: zero), e para `I1` e `I2` a conta nem é soma — exige girar duas fases de
#: 120°, que é multiplicar por complexo.
NOTA_DAS_COMPONENTES = ("componentes simétricas: módulo do fasor de um ciclo, "
                        "em eficaz")

#: O fecho do rodapé quando o painel tem resíduo. Vem separado da nota das
#: componentes, e só quando há resíduo: dizer "módulo do fasor de um ciclo"
#: embaixo de uma senoide somada no tempo seria descrever a conta errada, e é
#: justamente a diferença entre as duas que faz o resíduo existir.
#:
#: O `{nomes}` é preenchido com o que está NO PAINEL — `IN`, `VN`, ou os dois.
#: Citar o que não está na tela cobraria do leitor a decisão de descobrir qual
#: dos dois é o dele.
MOLDE_DO_RESIDUO = ("{nomes}: soma das três fases amostra a amostra — "
                    "leva a DC e os harmônicos")

#: O mesmo, para o resíduo que está na tela FILTRADO — `IN G1 · 60Hz` com o
#: filtro aceso, ou o `IN G1` de um registro que o relé já gravou filtrado.
#: Dizer "leva a DC e os harmônicos" embaixo dele seria descrever o que o
#: filtro acabou de tirar.
MOLDE_DO_RESIDUO_FILTRADO = ("{nomes}: soma das três fases, só a componente "
                             "de {f} Hz")


def nota_do_residuo(nomes, filtrado: bool = False,
                    frequencia: float = sinais.FREQUENCIA_PADRAO) -> str:
    """A nota do rodapé para os resíduos presentes no painel."""
    juntos = ", ".join(sorted(nomes))
    if filtrado:
        return MOLDE_DO_RESIDUO_FILTRADO.format(
            nomes=juntos, f=sinais.frequencia_no_nome(frequencia))
    return MOLDE_DO_RESIDUO.format(nomes=juntos)


def _rodape(registro: Record, pedidos: list,
            sempre_filtrado: bool = False) -> list[str]:
    """De que canais do arquivo saiu o que está neste painel.

    `sempre_filtrado` é para o diagrama fasorial: lá tudo é fasor de 60 Hz —
    não há onda bruta a desenhar —, então a nota do resíduo é a do filtrado
    qualquer que seja a coluna em que o sinal foi pedido.

    É a contrapartida do `G1`. O nome do grupo não depende de fabricante
    nenhum — e é justamente por não depender que ele não DIZ nada sozinho. Esta
    linha é onde o programa responde "`G1` é qual?", citando os nomes do
    arquivo entre aspas: sem as aspas, um `TC BUC 69kV:I A` no meio de uma
    lista com espaços e dois-pontos vira sopa, e um `J1 -IA` parece subtração.

Aparece **só** quando o painel tem algo que saiu de uma trinca:
    componente simétrica (`3I0 G1`, `I1 G1`) ou resíduo (`IN G1`, `VN G2`).
    São as únicas coisas na tela sem nome de arquivo a herdar — saem de TRÊS
    canais —, e por isso as únicas que precisam citar o grupo. Num painel só
    com `IAW`, `IBW` e `ICW` a linha repetiria o que a legenda já diz, e o
    grupo deles se pergunta no editor de grupos ou no catálogo.

    E só os grupos cujo CALCULADO está na tela: um painel com `3I0 G1` e os
    canais de `G2` cita `G1`, não os dois. O canal não precisa de tradução; a
    conta precisa.

    A linha de origem é a mesma para os dois, porque os três canais que entram
    na conta são os mesmos. O que muda é a nota do fim, que diz QUE conta foi
    feita — e são contas diferentes.
    """
    achados = conjuntos.de_registro(registro)
    nomes = {c.index: c.name for c in registro.analog_channels}

    posicoes: list[int] = []
    tem_componente = False
    #: `(nome, filtrado)` de cada resíduo na tela. A COLUNA do sinal diz se
    #: ele está filtrado: num `.CEV` o `IN G1` cru já mora em `filtrado.onda`.
    #: Par, e não dicionário: `IN G1` e `IN G1 · 60Hz` no mesmo painel são as
    #: duas coisas ao mesmo tempo, e cada uma leva a sua nota.
    residuos: set[tuple[str, bool]] = set()
    for _identidade, alvo in pedidos:
        if alvo.id.startswith("q"):
            partes = alvo.id.split(":")
            posicao = int(partes[0][1:])
            if partes[1:2] == [catalogo.RESIDUAL]:
                # `IN G1`, `VN G2` — o nome INTEIRO, que é o mesmo da legenda.
                # Já foi só `IN`: com dois grupos no mesmo painel a nota dizia
                # "IN: soma das três fases" sem dizer de quais três.
                if 0 <= posicao < len(achados):
                    trinca = achados[posicao]
                    residuos.add((conjuntos.juntar(f"{trinca.grandeza}N",
                                                   trinca.rotulo),
                                  sempre_filtrado
                                  or alvo.coluna.startswith("filtrado.")))
            else:
                tem_componente = True
        else:
            # Canal do arquivo não entra na conta das posições: ele já se
            # apresenta pelo nome na legenda.
            continue
        if 0 <= posicao < len(achados) and posicao not in posicoes:
            posicoes.append(posicao)

    if not posicoes:
        return []

    linhas = []
    for posicao in posicoes:
        trinca = achados[posicao]
        # **Só A, B e C.** É a lista dos canais que ENTRAM na conta, não a dos
        # canais do conjunto: o residual (`TC BUC 69kV:3I0` no SIPROTEC, `IG`
        # num SEL) pertence ao mesmo vão e está no mesmo painel, mas não entra
        # em Fortescue. Citá-lo aqui prometeria que ele foi somado.
        canais = ", ".join(f'"{nomes.get(i, i)}"' for i in trinca.abc)
        # O nome do grupo abre a linha: é a etiqueta que aparece no catálogo,
        # no editor de grupos e no nome dos sinais deste painel, e esta linha é
        # o que a traduz para os canais do arquivo.
        # Sem a palavra «de»: a linha é uma legenda, não uma frase, e o que
        # se lê dela é `G1` e os três nomes. Pedido do usuário (out/2026).
        linhas.append(f"{trinca.rotulo} — {canais}")
    if linhas:
        # Separados: o mesmo painel pode ter `IN G1` bruto e `VN G2 · 60Hz`.
        for filtrado in (False, True):
            quais = {n for n, f in residuos if f == filtrado}
            if quais:
                linhas.append(nota_do_residuo(quais, filtrado,
                                              registro.line_frequency))
        if tem_componente:
            linhas.append(NOTA_DAS_COMPONENTES)
    return linhas


def _sem_sinal(registro: Record, paineis_montados: list[dict]) -> list[dict]:
    """Os canais sem sinal que NÃO estão em nenhum gráfico agora.

    É o que o aviso do cabeçalho conta. A lista tem que encolher quando o
    usuário traz um deles de volta — senão o aviso ficaria repetindo que há
    canais escondidos depois de eles já estarem na tela, e um aviso que não
    acompanha o que se vê deixa de ser lido.

    Vão com o id de catálogo e a unidade, que é tudo de que a tela precisa para
    devolvê-los ao gráfico da unidade certa num clique.
    """
    mortos = conjuntos.canais_sem_sinal(registro)
    if not mortos:
        return []
    na_tela = {s.get("indice") for p in paineis_montados
               if p.get("tipo") == paineis.ANALOGICO
               for s in p.get("sinais", ())}
    return [{"id": f"c{c.index}:instantaneo", "nome": c.name,
             "unidade": c.unit.strip()}
            for c in registro.analog_channels
            if c.index in mortos and c.index not in na_tela]


def _instante(registro: Record, amostra: int | None) -> float | None:
    """O instante de uma amostra, ou `None` quando não há amostra nenhuma."""
    if amostra is None or not (0 <= amostra < registro.time.size):
        return None
    return round(float(registro.time[amostra]), 9)


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
