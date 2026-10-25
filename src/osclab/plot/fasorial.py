"""O painel fasorial: que fasores ele mostra, e em que base de pu.

## O diagrama não calcula fasor nenhum

Módulo e ângulo de cada sinal já saem da leitura do cursor (`plot/leitura.py`),
com a mesma janela de um ciclo da tabelinha e da curva. Este módulo só diz
**quais** sinais o painel tem, com que nome e cor, e **qual é o 1 pu** de cada
um. Fazer a conta de novo aqui seria uma segunda implementação do fasor — que é
como o diagrama e a tabelinha passariam a discordar.

## Quem pode entrar

O que tem fasor de 60 Hz: os canais senoidais (`IAW`), o resíduo de uma trinca
(`IN G1`) e as componentes simétricas (`3I0 G1`, `I1 G1`, `I2 G1`). Uma entrada
por LINHA do catálogo: `IAW`, `IAW · 60Hz` e `IAW · 60Hz RMS` têm o mesmo
fasor, e três caixinhas para a mesma seta seriam duas a mais.

## A base do pu: o `.cfg` quando ele serve, e o registro quando não serve

Pedido do usuário (out/2026): tensão e corrente no mesmo diagrama, em pu, para
uma não esmagar a outra. A primeira ideia foi tirar a base do primário/
secundário que o `.cfg` declara. **Ela funciona em menos arquivos do que
parece**, e o parque do usuário é um dos que ela não atende.

O campo da norma guarda um PAR, e nada obriga esse par a ser a nominal do
equipamento. Medido no SEL-451 do alimentador: ele grava `120 / 1` nos canais
de corrente e de tensão — isso é a RELAÇÃO (RTP = 13800/115 = 120), não
`13800 / 115`. A base saía 120 kV para uma barra de 13,8 kV, e as tensões
apareciam com 0,067 pu: três setas no meio do círculo.

**A razão não é inútil: falta a outra metade do par.** `120 / 1` com o
secundário nominal vira `600 / 5` e `13800 / 115` — que é o que está na placa
do equipamento. O secundário não está no arquivo, mas é padrão de ofício: 5 A
no TC, 115 V fase-fase no TP. Ver `_da_relacao`, e as duas constantes no topo.

Na TENSÃO a derivação é conferida contra a pré-falta e por isso é confiável:
uma barra sadia está na nominal. Medido no alimentador do parque: `120 × 115 ÷
√3 = 7,967 kV`, e a pré-falta mediu 101 % disso. Na CORRENTE não há
conferência possível — a carga é qualquer fração da nominal —, então o 5 A é
premissa: vai escrito na tela e se corrige num clique. Com TC de 1 A a base
sai 5× maior.

Quando o par TEM dois valores, ele é usado direto, e aí valem as peneiras:

1. **O par tem que ser um par de valores**, não uma razão (`secundário = 1`).
2. **Na tensão, a pré-falta tem que bater.** O primeiro ciclo do registro é
   medido e comparado com a base:

       perto de 1,0        a base serve como está
       perto de 1/√3       TP declarado fase-fase num canal fase-terra:
                           a base vira base/√3, e a origem diz isso
       qualquer outra coisa   o par não é nominal — não serve de base

   Não há peneira equivalente para a CORRENTE: a carga de um alimentador pode
   ser qualquer fração da nominal, então nenhuma medida do registro contradiz
   uma base de corrente.

**Sem base utilizável, quem manda é o registro**: o maior fasor daquela
grandeza no REGISTRO INTEIRO vira 1 pu. Tensão e corrente passam a ocupar o
mesmo círculo — que é o pedido original — e cada uma chega ao raio no instante
em que ela é máxima.

**No registro inteiro, e não no instante do cursor.** A primeira versão
normalizava pelo maior do instante, e isso quebra duas vezes no mesmo evento:
depois que o disjuntor abre sobram 0,2 A de fuga, e normalizados por si mesmos
eles vão ao raio como se fossem falta; e as tensões cresciam a cada passo do
cursor, porque o que encolhia era a corrente ao lado delas. Com o máximo do
registro, a seta de cada instante diz quanto aquele instante tem do pico
daquele evento — e dois instantes podem ser comparados.

Nos dois casos o módulo em ampère e em volt continua na tabela ao lado: o pu é
do desenho, onde ele serve para as duas grandezas caberem juntas.

## A régua da sequência é a das FASES, sempre

O resíduo e as componentes herdam a base da fase A da trinca deles — tanto a
nominal quanto o pico do registro. Não é comodidade: `V2` de um sistema são
dois ou três por cento da tensão de fase, e normalizado por si mesmo ele
encheria o círculo em todo registro. Um desequilíbrio de 2 % se leria igual a
um de 30 %, que é o contrário do que o diagrama existe para mostrar.

Com a régua da fase, `V2 = 0,21 pu` quer dizer «21 % da tensão de barra» — o
número do ofício, o mesmo que se compara com o ajuste do 47 ou do 67Q.

**É também o que impede qualquer normalização pela PRÉ-FALTA de valer para a
sequência.** A tensão de sequência negativa de um sistema são antes da falta
é zero; dividir por ela é dividir por zero. Se a pré-falta entrar algum dia
como escala, ela entra como base da FASE, nunca de cada sinal.
"""

from __future__ import annotations

import math

import numpy as np

from osclab.dsp import fasor
from osclab.formats import conjuntos, fases
from osclab.formats.base import Record
from osclab.plot import catalogo, conversao
from osclab.plot.paineis import FASORIAL

#: A faixa da razão pré-falta / base declarada que denuncia um TP declarado
#: fase-fase lido num canal fase-terra. O alvo é 1/√3 = 0,577; a folga cobre
#: uma barra operando a ±15 % da nominal sem encostar em 1,0.
FAIXA_FASE_FASE = (0.45, 0.70)

#: A faixa em que a pré-falta confirma que a base declarada É a nominal da
#: barra. Fora dela — e fora da faixa do fase-fase — o par do arquivo não é
#: nominal de nada, e não serve de base. Ver o cabeçalho.
FAIXA_NOMINAL = (0.80, 1.20)

#: O secundário NOMINAL de um TC e de um TP, quando o arquivo só declara a
#: relação. São as duas constantes que transformam `120 / 1` em `600 / 5`.
#:
#: 5 A é o secundário de praticamente todo TC de proteção do parque (1 A
#: existe, e nesse caso a base sai 5× maior — por isso o número vai escrito
#: na tela e é editável num clique). 115 V é o secundário FASE-FASE do TP,
#: que com relação 120 dá 13,8 kV — a tensão da barra, conferida contra a
#: pré-falta antes de virar base.
SECUNDARIO_DO_TC = 5.0
SECUNDARIO_DO_TP = 115.0

#: A faixa em que o que o registro MEDE confirma que a base tem a ordem de
#: grandeza certa. É larga de propósito: um alimentador rural de madrugada
#: anda a 1 % da nominal do TC, e uma falta chega a 20 vezes ela. O que esta
#: peneira pega é o erro de MIL vezes — o par escrito em volt num canal
#: gravado em quilovolt.
FAIXA_COERENTE = (0.002, 50.0)

#: O que cada prefixo de unidade vale. A relação do arquivo é um número puro,
#: então 115 V viram 0,115 num canal gravado em kV — sem isto a base sairia
#: mil vezes maior, que é exatamente a ordem de erro que o pu existe para não
#: ter.
_PREFIXOS = {"": 1.0, "k": 1e3, "M": 1e6, "m": 1e-3}


def tem_fasor(sinal: catalogo.Sinal) -> bool:
    """Se o sinal é a BASE de uma linha com fasor de 60 Hz."""
    if sinal.familia == "canal":
        return sinal.bloco == "alternado"
    # Conta do usuário: tem fasor se o resultado for senoidal — soma e
    # subtração de senoides é senoide; produto entre sinais não é. Quem
    # decide é o bloco, e quem decide o bloco é `plot/contas.py`.
    if sinal.familia == "conta":
        return (sinal.bloco == "alternado"
                and sinal.grandeza == "instantaneo")
    if not sinal.id.startswith("q"):
        return False
    _, chave, grandeza = sinal.id.split(":")
    if chave == catalogo.RESIDUAL:
        return grandeza == "instantaneo"
    return chave in catalogo.COMPONENTES


def _pre_falta(registro: Record, canal, lado: str) -> float | None:
    """O eficaz da fundamental no primeiro ciclo inteiro do registro.

    **No lado que a tela mostra**, e não no do arquivo. A pré-falta existe
    para ser comparada com a base derivada, e a base derivada está no lado
    escolhido: conferir 7,97 kV de primário contra 66,4 V de secundário dá
    120× de diferença, nenhum dos candidatos bate, e um arquivo com RTP
    perfeitamente declarado cai no «maior do registro» só por estar em
    secundário.
    """
    trechos = registro.trechos
    if not trechos:
        return None
    ciclo = fasor.ciclo_em_amostras(trechos[0].taxa_hz, registro.line_frequency)
    if ciclo <= 0:
        return None
    valores = registro.analog[canal.index] if registro.analog.size else None
    if valores is None or not valores.size:
        return None
    convertido, _, _ = conversao.converter(valores, canal, lado)
    largura = fasor.pesos_do_ciclo(ciclo).size
    medido = fasor.no_instante(convertido, largura - 1, ciclo)
    return medido.fundamental if medido else None


def base_do_canal(registro: Record, canal, lado: str,
                  divisor: float) -> tuple[float | None, str]:
    """`(base, origem)` de um canal, na unidade e no lado que a tela mostra.

    `base` é `None` quando o arquivo não dá de onde tirá-la; `origem` diz, em
    uma linha, de onde ela veio — ou por que não há.
    """
    p, s = float(canal.primary or 0.0), float(canal.secondary or 0.0)
    if p <= 0 or s <= 0 or (p == 1.0 and s == 1.0):
        return None, "o arquivo não declara RTC/RTP"

    _, lado_final, _ = conversao.converter(np.zeros(1), canal, lado)
    if s == 1.0 and p > 1.0:
        # `120 / 1` é a RELAÇÃO, não um par de nominais — nenhum TC tem 1 A de
        # secundário. Mas a relação MAIS o secundário nominal dão a base:
        # 120 × 5 A = 600 A, 120 × 115 V = 13,8 kV. Ver `_da_relacao`.
        return _da_relacao(registro, canal, p, lado, lado_final,
                           divisor)

    base = p if lado_final == "primario" else s
    origem = f"{_numero(p)} / {_numero(s)} do arquivo"

    # A ORDEM DE GRANDEZA vem primeiro, e tem que vir: o par pode estar em
    # volt num canal gravado em quilovolt, e aí nenhuma conta sobre ele faz
    # sentido — nem a do √3 logo abaixo, que mediria 0 % e culparia o par.
    base, origem = _conferida(base, registro, canal, lado,
                              _fator_da_unidade(canal.unit), origem)
    if base is None:
        return None, origem

    fase, _ = fases.da_canal(canal)
    grandeza = fases.grandeza_da_unidade(canal.unit.strip())
    if grandeza == "V" and fase in ("A", "B", "C"):
        # A tensão de uma barra sadia é a nominal dela, e isso é conferível. A
        # corrente não tem equivalente: a carga pode ser qualquer fração.
        medido = _pre_falta(registro, canal, lado)
        convertido = base
        razao = medido / convertido if medido is not None and convertido > 0 else None
        if razao is None:
            pass                     # sem um ciclo inteiro antes: não contesta
        elif FAIXA_FASE_FASE[0] <= razao <= FAIXA_FASE_FASE[1]:
            base /= math.sqrt(3.0)
            origem += (f" ÷ √3 — a pré-falta mediu {razao:.0%} da base: "
                       "o TP está declarado fase-fase")
        elif not FAIXA_NOMINAL[0] <= razao <= FAIXA_NOMINAL[1]:
            return None, (f"a pré-falta mediu {razao:.0%} da base declarada "
                          f"({_numero(p)} / {_numero(s)}): esse par não é a "
                          "nominal da barra")
    return base / divisor, origem


def _pico_do_canal(registro: Record, canal, lado: str) -> float | None:
    """O maior valor eficaz aproximado do canal, no lado que a tela mostra.

    Serve só para conferir ORDEM DE GRANDEZA — por isso sai do pico das
    amostras sobre √2, e não de uma janela de fasor: a conta cara não se
    justifica para responder "isto está mil vezes errado?".
    """
    valores = registro.analog[canal.index] if registro.analog.size else None
    if valores is None or not valores.size:
        return None
    convertido, _, _ = conversao.converter(valores, canal, lado)
    finitos = convertido[np.isfinite(convertido)]
    if not finitos.size:
        return None
    pico = float(np.max(np.abs(finitos)))
    return pico / math.sqrt(2.0) if pico > 0 else None


def _conferida(base: float, registro: Record, canal, lado: str, fator: float,
               origem: str) -> tuple[float | None, str]:
    """A base contra o que o registro mede, com o prefixo corrigido se preciso.

    **O par do arquivo não diz em que unidade ele está.** A norma manda o
    canal declarar a unidade dos DADOS (`kV`), e nada obriga o par de TC/TP a
    estar nela: há fabricante que grava `13800 / 115` num canal gravado em
    quilovolt. O número está certo e a base sai mil vezes maior.

    Quem denuncia é o próprio registro: uma base mil vezes acima do que o relé
    mediu não é base de nada. Quando dividir pelo prefixo da unidade põe tudo
    no lugar, é isso que se faz — e a origem diz. Quando não põe, não há base.
    """
    pico = _pico_do_canal(registro, canal, lado)
    if pico is None or base <= 0:
        return base, origem
    dentro = lambda x: x > 0 and FAIXA_COERENTE[0] <= pico / x <= FAIXA_COERENTE[1]
    if dentro(base):
        return base, origem
    if fator != 1.0 and dentro(base / fator):
        return base / fator, (f"{origem} — em {_numero(fator)}× a unidade do "
                              "canal, o que o registro mediu confirma")
    return None, (f"{origem}, mas o registro mede valores "
                  f"{_numero(round(base / max(pico, 1e-9)))}× menores que "
                  "isso: esse par não é a nominal deste canal")


def _fator_da_unidade(unidade: str) -> float:
    """Quanto vale 1 na unidade do canal: `kV` → 1000, `A` → 1."""
    texto = (unidade or "").strip()
    prefixo = texto[:-1] if len(texto) > 1 else ""
    return _PREFIXOS.get(prefixo, 1.0)


def _da_relacao(registro: Record, canal, relacao: float, lado: str,
                lado_final: str, divisor: float) -> tuple[float | None, str]:
    """A base quando o arquivo declara só a RELAÇÃO (`120 / 1`).

    O par que falta é o secundário nominal, e ele não está no arquivo: 5 A no
    TC, 115 V fase-fase no TP. Com ele, `120 / 1` vira `600 / 5` e
    `13800 / 115` — que é o que o usuário lê na placa do equipamento.

    **Na tensão a conta é conferida**, e é por isso que ela é confiável: a
    barra sadia está na nominal, então a pré-falta tem que bater com a base
    derivada — fase-terra ou fase-fase, as duas são testadas. Quando não bate,
    não há base: devolve `None` e quem desenha usa o maior do registro.

    **Na corrente não há conferência possível** — a carga de um alimentador é
    qualquer fração da nominal. Ali o 5 A é premissa, vai escrito na tela e se
    corrige num clique. Com TC de 1 A a base sai 5× maior.
    """
    fator = _fator_da_unidade(canal.unit)
    grandeza = fases.grandeza_da_unidade(canal.unit.strip())
    como = f"{_numero(relacao)} / 1 é a relação"

    if grandeza == "I":
        secundario = SECUNDARIO_DO_TC / fator
        base = secundario * relacao if lado_final == "primario" else secundario
        return base / divisor, (f"{como}; com {_numero(SECUNDARIO_DO_TC)} A no "
                                "secundário do TC ela vale "
                                f"{_numero(relacao * SECUNDARIO_DO_TC)} / "
                                f"{_numero(SECUNDARIO_DO_TC)}")


    if grandeza != "V":
        return None, f"{como}, e não dá para derivar a nominal deste canal"

    fase_fase = SECUNDARIO_DO_TP / fator
    if lado_final == "primario":
        fase_fase *= relacao
    medido = _pre_falta(registro, canal, lado)
    fase, _ = fases.da_canal(canal)
    candidatos = [(fase_fase / math.sqrt(3.0), "fase-terra"),
                  (fase_fase, "fase-fase")]
    if fase not in ("A", "B", "C") or medido is None:
        # Sem fase reconhecida ou sem um ciclo de pré-falta não há o que
        # conferir, e a conta mais provável é a fase-terra de um canal `VA`.
        escolhida, como_ligado = candidatos[0]
        return escolhida / divisor, (f"{como}; com "
                                     f"{_numero(SECUNDARIO_DO_TP)} V no "
                                     f"secundário do TP, {como_ligado} — sem "
                                     "pré-falta para conferir")
    for valor, como_ligado in candidatos:
        razao = medido / valor if valor > 0 else 0.0
        if FAIXA_NOMINAL[0] <= razao <= FAIXA_NOMINAL[1]:
            return valor / divisor, (
                f"{como}; com {_numero(SECUNDARIO_DO_TP)} V no secundário do "
                f"TP ela vale {_numero(relacao * SECUNDARIO_DO_TP)} / "
                f"{_numero(SECUNDARIO_DO_TP)}, {como_ligado} — a pré-falta "
                f"mediu {razao:.0%} dela")
    return None, (f"{como}, mas a pré-falta não bate com "
                  f"{_numero(SECUNDARIO_DO_TP)} V de secundário nem "
                  "fase-terra nem fase-fase")


def _numero(x: float) -> str:
    return f"{x:g}"


def _fundamental_de(sinal: catalogo.Sinal,
                    por_id: dict) -> catalogo.Sinal | None:
    """O sinal que CARREGA o fasor deste: o eficaz de 60 Hz da mesma linha.

    `IAW` é onda; quem tem o módulo do fasor dela é `IAW · 60Hz RMS`. Num
    registro que o relé já gravou filtrado essa variante não existe, e quem
    responde é `IAW · RMS` — que ali sai da mesma DFT.
    """
    if sinal.familia == "canal":
        return (por_id.get(f"v{sinal.canal}:fundamental")
                or por_id.get(f"v{sinal.canal}:rms"))
    if sinal.familia == "conta":
        base = sinal.id.split(":")[0]
        return (por_id.get(f"{base}:fundamental")
                or por_id.get(f"{base}:rms"))
    partes = sinal.id.split(":")
    if partes[1:2] == [catalogo.RESIDUAL]:
        base = f"{partes[0]}:{catalogo.RESIDUAL}"
        return por_id.get(f"{base}:fundamental") or por_id.get(f"{base}:rms")
    return sinal                      # componente simétrica já é fasor


def _pico_do_registro(registro: Record, sinal: catalogo.Sinal, lado: str,
                      escalas: dict) -> float | None:
    """O maior módulo de fasor deste sinal no registro inteiro.

    É a base de quem não tem RTC/RTP utilizável — ver o cabeçalho. Sai do
    registro INTEIRO e não da janela da tela: ampliar um pedaço não pode mudar
    o tamanho das setas, senão duas telas do mesmo evento não se comparam.
    """
    n = registro.n_samples
    if n <= 0 or sinal is None:
        return None
    valores = catalogo.serie(registro, sinal, 0, n, registro.trechos, lado,
                             escalas)
    finitos = valores[np.isfinite(valores)]
    if not finitos.size:
        return None
    maior = float(np.max(np.abs(finitos)))
    return maior if maior > 0 else None


def montar(registro: Record, painel, por_id: dict, escalas: dict,
           lado: str) -> dict:
    """O pacote de um painel fasorial: os sinais, com nome, fase e base."""
    canais = {c.index: c for c in registro.analog_channels}
    achados = conjuntos.de_registro(registro)
    sinais_json = []
    for identidade in painel.sinais:
        alvo = por_id.get(identidade)
        if alvo is None or not tem_fasor(alvo):
            continue
        divisor, mostrada = escalas.get(alvo.unidade, (1.0, alvo.unidade))

        canal = canais.get(alvo.canal) if alvo.canal >= 0 else None
        de_quem = canal
        if canal is None and alvo.familia != "conta":
            # Resíduo e componente: a base é a da fase A da trinca deles.
            posicao = int(alvo.id[1:].split(":")[0])
            if 0 <= posicao < len(achados):
                de_quem = canais.get(achados[posicao].abc[0])
        if alvo.familia == "conta":
            # Conta do usuário não tem canal, e portanto não tem RTC/RTP de
            # onde tirar base. O 1 pu dela é o maior fasor dela no registro —
            # o mesmo caminho de quem não declara relação nenhuma.
            base, origem = None, "conta do usuário: não há RTC/RTP a herdar"
        else:
            base, origem = (base_do_canal(registro, de_quem, lado, divisor)
                            if de_quem is not None
                            else (None, "a trinca deste sinal sumiu do registro"))
        if canal is None and de_quem is not None and base is not None:
            origem = f"a de {de_quem.name}: {origem}"

        # O pico do registro vai SEMPRE, mesmo quando há base do arquivo: é
        # dele que sai a escala de quem não tem base, e as duas convivem no
        # mesmo painel quando só uma das grandezas foi declarada direito.
        #
        # **E ele sai da FASE, nunca da componente.** `V2` de um sistema são
        # dois ou três por cento da tensão de fase; normalizado por si mesmo
        # ele encheria o círculo em qualquer registro, e um desequilíbrio de
        # 2 % se leria igual a um de 30 %. A régua da sequência é a mesma das
        # fases que a produziram — é assim que `V2 = 0,21 pu` quer dizer
        # "21 % da tensão de barra", que é o número do ofício.
        fonte = alvo if (canal is not None or alvo.familia == "conta") else (
            por_id.get(f"c{de_quem.index}:instantaneo") if de_quem else None)
        pico = _pico_do_registro(registro, _fundamental_de(fonte, por_id), lado,
                                 escalas)

        sinais_json.append({
            "id": identidade,
            # O nome da LINHA: `IAW`, `IN G1`, `3I0 G1` — o fasor é da linha
            # inteira, não de uma das contas dela.
            "sinal": alvo.linha or alvo.nome,
            "familia": alvo.familia,
            "fase": fases.da_canal(canal)[0] if canal is not None else "",
            "grupo": alvo.grupo,
            "unidade": mostrada,
            # A entrada do relé não está cabeada: o que ela lê é ruído do
            # conversor, e o ÂNGULO de um ruído não aponta para lugar nenhum.
            # A tela não desenha seta para ele — o número continua na tabela.
            "sem_sinal": bool(alvo.sem_sinal),
            "unidade_do_arquivo": alvo.unidade,
            "descricao": alvo.descricao,
            "base": base,
            "base_origem": origem,
            "pico": pico,
        })
    # Import adiado: `janela` importa este módulo, e no topo fecharia o ciclo.
    from osclab.plot import janela

    return {
        "id": painel.id,
        "tipo": FASORIAL,
        "nome": painel.nome or "Fasores",
        "do_padrao": painel.do_padrao,
        "sinais": sinais_json,
        # A MESMA nota do gráfico de ondas: `G1` não diz sozinho de que três
        # canais ele saiu, e aqui a pergunta é a mesma — mais ainda, porque o
        # diagrama é feito de `3I0`, `I1` e `IN`, que são justamente os sinais
        # sem nome de arquivo a herdar. Ver `janela._rodape`.
        "rodape": janela._rodape(registro, [(s["id"], por_id[s["id"]])
                                            for s in sinais_json],
                                 sempre_filtrado=True),
    }
