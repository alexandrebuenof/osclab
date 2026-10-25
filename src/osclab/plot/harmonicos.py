"""O painel de harmônicos: que sinais ele mostra, e até que ordem.

## O painel não calcula espectro nenhum

Como no fasorial, as barras saem da leitura do cursor (`plot/leitura.py`), da
MESMA janela de um ciclo que alimenta a tabelinha, a curva e o fasor. Este
módulo só diz **quais** sinais o painel tem e **qual é o teto de ordens**
daquele registro. A conta é uma só: `dsp/fasor.espectro`.

É por isso que a primeira barra do desenho é, dígito a dígito, o mesmo número
que a coluna `60 Hz RMS` da tabelinha. Duas implementações do mesmo Fourier é
como o desenho e a tabela passariam a discordar.

## Quem pode entrar: ONDA, e só

Canal senoidal (`IAW`) e resíduo de trinca (`IN G1`). Os dois são **onda**:
existe uma série de amostras de onde tirar raias.

**Componente simétrica fica de fora**, e não é limitação de implementação. A
transformação de Fortescue é definida sobre fasores de UMA frequência: `I1` é
feito dos três fasores de 60 Hz das fases. Perguntar "qual é o 5º harmônico do
I1" não tem resposta a partir desse número — teria que ser outra conta
(Fortescue sobre os fasores de 5ª ordem de cada fase), que é uma função
diferente e ainda não existe. Oferecer a caixinha e devolver zero seria pior
que não oferecer.

## O teto de ordens é do ARQUIVO, não do programa

Com `n` amostras por ciclo a DFT distingue até a raia `n/2` — ver
`fasor.ordens_mediveis`. No parque: 2000 Hz dão 33,3/ciclo e vão até o 16º; um
MiCOM a 1200 Hz vai até o 10º; um `.CEV` a 4 amostras por ciclo não mede
harmônico nenhum. O painel escreve o teto no rodapé em vez de desenhar barras
que a taxa não sustenta — além do teto não há zero, há **aliasing**: uma barra
plausível na ordem errada.

## E a gravação precisa ser BRUTA

O filtro de 60 Hz apaga exatamente o que este painel mede. Então:

* a série analisada é sempre a do canal **como está no arquivo**, mesmo que a
  tela esteja com o botão do filtro aceso — ver `plot/leitura.py`;
* num registro que o RELÉ já gravou filtrado (`registro.filtering`), não há
  harmônico nenhum no arquivo, e o painel diz isso. Vários registros do parque
  são assim, e um espectro zerado sem explicação se leria como defeito do
  programa.

## A componente contínua é a barra de ordem ZERO

Decisão do usuário, revista em 15/10/2026: a DC passou a ser a primeira barra
do desenho, à esquerda da fundamental — é o que a SEL faz, e foi o que ele
pediu. O valor é o mesmo da coluna `DC` da tabelinha: a média da janela de um
ciclo, pelos mesmos pesos da DFT (ver `_espectro_da_onda`, em `plot/leitura.py`).

A barra ENTRA sem empurrar o desenho: a última ordem sai para ela caber, e a
contagem de barras não muda. Com 33,3 amostras por ciclo o teto é a 16ª, e a
16ª é justamente a que tem só 1,04 amostra por período — a que menos se
sustenta. Trocar a mais frágil pela contínua é trocar uma barra que quase não
mede por uma que mede.

A ressalva de setembro continua valendo, e está no rodapé e no `title` da
barra: a DC de uma janela de um ciclo **não é uma contínua de verdade** — é a
média daquele ciclo, e ela decai. Uma barra sugere permanência que não existe.
Quem mostra o decremento — que é a pergunta de proteção, porque a constante de
tempo é a relação X/R e é ela que diz se o TC vai saturar — continua sendo a
CURVA `IA DC` do gráfico analógico.
"""

from __future__ import annotations

from osclab.dsp import fasor
from osclab.formats import conjuntos, fases
from osclab.formats.base import Record
from osclab.plot import catalogo

#: Quantas ordens o desenho mostra, no máximo, mesmo quando a taxa dá mais.
#:
#: Um registro a 10 kHz mede até o 83º harmônico. Oitenta e três barras num
#: painel de 600 px são barras de dois pixels, e as que interessam em proteção
#: — 2ª, 3ª, 5ª, 7ª — ficariam indistinguíveis das outras setenta e seis. O
#: teto do arquivo continua escrito no rodapé.
ORDENS_DESENHADAS = 25

TIPO = "harmonicos"


def tem_espectro(sinal: catalogo.Sinal) -> bool:
    """Se o sinal é a base de uma linha que tem ONDA de onde tirar raias.

    Canal senoidal e resíduo entram; componente simétrica não — ver o cabeçalho
    do módulo.
    """
    if sinal.familia == "canal":
        return sinal.bloco == "alternado"
    # Conta do usuário: é onda, e tem espectro se for senoidal. Ver
    # `plot/contas.py` para quem decide isso.
    if sinal.familia == "conta":
        return (sinal.bloco == "alternado"
                and sinal.grandeza == "instantaneo")
    if not sinal.id.startswith("q"):
        return False
    _, chave, grandeza = sinal.id.split(":")
    return chave == catalogo.RESIDUAL and grandeza == "instantaneo"


def teto_do_registro(registro: Record) -> int:
    """A maior ordem que a taxa deste registro mede, no trecho mais lento.

    O trecho MAIS LENTO, e não o do cursor: o painel anuncia um teto só, e
    anunciar o do trecho rápido faria as barras sumirem sem aviso quando o
    cursor entrasse no trecho lento de um registro de taxa variável.
    """
    taxas = [t.taxa_hz for t in registro.trechos if t.taxa_hz > 0]
    if not taxas or registro.line_frequency <= 0:
        return 1
    por_ciclo = min(taxas) / float(registro.line_frequency)
    return fasor.ordens_mediveis(por_ciclo)


def montar(registro: Record, painel, por_id: dict, escalas: dict,
           lado: str) -> dict:
    """O pacote de um painel de harmônicos: os sinais, o teto e o rodapé."""
    canais = {c.index: c for c in registro.analog_channels}
    sinais_json = []
    for identidade in painel.sinais:
        alvo = por_id.get(identidade)
        if alvo is None or not tem_espectro(alvo):
            continue
        _, mostrada = escalas.get(alvo.unidade, (1.0, alvo.unidade))
        canal = canais.get(alvo.canal) if alvo.canal >= 0 else None
        sinais_json.append({
            "id": identidade,
            # O nome da LINHA, como no fasorial: o espectro é da linha inteira,
            # não de uma das contas dela.
            "sinal": alvo.linha or alvo.nome,
            "familia": alvo.familia,
            "fase": fases.da_canal(canal)[0] if canal is not None else "",
            "grupo": alvo.grupo,
            "unidade": mostrada,
            "unidade_do_arquivo": alvo.unidade,
            "descricao": alvo.descricao,
            "sem_sinal": bool(alvo.sem_sinal),
        })
    # Import adiado: `janela` importa este módulo, e no topo fecharia o ciclo.
    from osclab.plot import janela

    return {
        "id": painel.id,
        "tipo": TIPO,
        "nome": painel.nome or "Harmônicos",
        "do_padrao": painel.do_padrao,
        "sinais": sinais_json,
        "teto": teto_do_registro(registro),
        "desenhadas": ORDENS_DESENHADAS,
        # O aviso que muda a leitura do painel inteiro: num registro que o relé
        # gravou filtrado não há harmônico para medir.
        "ja_filtrado": str(registro.filtering) == "filtrado",
        # DECLARADO pelo arquivo ou DEDUZIDO pelo programa muda o tom do
        # aviso: uma dedução pode errar para o lado seguro num arquivo
        # limpo demais, e afirmar o que foi deduzido seria afirmar demais.
        "filtragem_deduzida": str(registro.filtering_source) != "declarado",
        "rodape": janela._rodape(registro, [(s["id"], por_id[s["id"]])
                                            for s in sinais_json]),
    }
