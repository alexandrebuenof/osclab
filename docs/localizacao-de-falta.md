# Localização de falta — os métodos, de onde vêm e o que falta

Levantamento de 23/10/2026, pedido do Alexandre: **todos** os métodos de
localização, de um e de dois terminais, para implementar e depois comparar a
precisão de cada um. A maquete do painel é `painel-localizacao-10.html`
(Área de Trabalho, «OscLab maquetes»); o que já roda no programa é a gaveta
«localizar falta» (`faultloc/seqneg.py`).

As fontes são três, e cada método diz de qual veio:

- **Pós IME** — os slides de *Proteção dos Equipamentos e Sistemas Elétricos*,
  capítulos I (LT), II (50/51), III (67), IV (21) e V (85), e o caderno de
  Exercícios Resolvidos. Os PDFs **não entram no repositório**; aqui fica só a
  página e a ideia, com as nossas palavras.
- **Energisa** — a planilha `LocDef_SeqNeg.xls` e o método da reatância que a
  proteção usa.
- **Literatura** — os que não estão nos slides; a referência vai junto para
  pesquisa.

O que os slides **não** trazem: Takagi, componentes superpostas como
localizador, nenhum método de dois terminais e ondas viajantes. Trazem a base
de onde todos saem: os laços com k0, o modelo do erro da Rf, a reatância
polarizada por I2/I0, a não homogeneidade e a mútua.

## O painel no programa — etapa 1 (23/10/2026)

Escolhas dele, entre as maquetes: tela própria (não gaveta), duas abas
(painel principal e simulações), os dois métodos padrão da proteção (seq.
negativa 2T e laço da falta) ligados e os outros depois, cada um com teste
contra os exercícios da pós. O |Z| aparente não entra (sempre impreciso com
Rf); o nível de curto fica para registros SEM tensão, onde é o único que
funciona.

- **O platô** começa 2 ciclos depois do início da falta (1,1 numa falta
  curta) e acaba ¾ de ciclo antes do FIM DA FALTA ou da abertura, o que vier
  antes. O fim da falta é medido pela corrente das fases com defeito voltando
  para menos da metade do caminho entre a pré-falta e a falta — porque quem
  elimina a falta pode ser o outro terminal, e aí a abertura nunca aparece.
- **O resultado** é, nesta etapa, uma preferência fixa: seq. negativa quando
  há os dois terminais, laço quando não há. A faixa de patrulha é a
  dispersão no platô (mínimo 0,3 km) — e a tela diz isso. **Ela não mede o
  erro do método**: o laço com Rf e carga erra uns km com dispersão quase
  zero. Quem mede o erro é a simulação da etapa 2.
- **Número fora da linha não vira resultado**: aparece com o motivo (falta
  externa, para trás, ou platô errado).
- **A direção** (32Q): com V2 na referência, falta para frente põe I2
  adiantada de 180° − ∠Z2 da fonte; o sinal de Re{(V2/I2)·1∠−θL} decide.
  Os dois terminais para frente = falta interna.

### O que os registros reais mostraram

Nos três registros do acervo com falta (o COXIPO do SEL-421 e dois MiCOM), a
direção sai **«para trás»** e o laço sai **negativo**. No COXIPO, com a linha
dos ajustes do próprio relé (13,4 km), o laço dá **−12,8 km** e I2 fica a
−81° de V2 — quase 180° do +103° da planilha LocDef. O sintético, com a
convenção conhecida (corrente positiva saindo da barra para a linha), fecha;
então a suspeita é a **polaridade da corrente no arquivo**, não a conta.
**Pergunta aberta para o Alexandre** — e, se for polaridade, falta decidir
como corrigir (uma correção por registro, gravada ao lado dele, como a das
fases).

## A equação comum

Quase todo método de impedância é a mesma conta com uma corrente de
polarização diferente:

    m = Im{ V_laço · I_pol* } / Im{ Z1L · I_laço · I_pol* }

`I_pol = I_laço` dá a reatância simples; `ΔI` (superposta) dá Takagi; `3I0` e
`I2` dão as polarizadas. A dedução sai do comparador do elemento de reatância
(Cap. IV, slides 8–11 e 63): no equilíbrio, `Im[(I_L·Z_R − V_L)·I_pol*] = 0`;
trocando `Z_R` por `m·Z1L` sai o `m`.

Laços (Cap. IV, slides 23–30; Exercícios 2, 8, 10, 13):

| laço | V | I |
|---|---|---|
| fase-terra (AN, BN, CN) | `Vφ` | `Iφ + k0·3I0`, `k0 = (Z0L − Z1L)/(3·Z1L)` |
| fase-fase (AB, BC, CA) | `Vφ1 − Vφ2` | `Iφ1 − Iφ2` (sem k0) |

**A convenção do k0 muda por fabricante** (Cap. IV, slides 133, 138–139, 155):
k0 complexo com ou sem o 3 no denominador; Siemens com `RE/RL` e `XE/XL`
separados; `K0X = (X0 − X1)/(3·X1)` só para o elemento de reatância. Ler o k0
dos ajustes exige saber qual convenção o relé usa.

## Os métodos

### Dois terminais

| método | estado | fonte |
|---|---|---|
| **Sequência negativa, sem sincronismo** — `\|V2S − m·Z2L·I2S\| = \|V2R − (1−m)·Z2L·I2R\|`, 2º grau em m | **feito** (`faultloc/seqneg.py`) | planilha LocDef (Energisa); Tziouvaras, Roberts, Benmouyal, *New multi-ended fault location design for two- or three-terminal lines*, 7th IEE DPSP, 2001; base nos slides: Cap. IV 60–62 |
| Dois terminais sincronizados — `m = Re{(V2S − V2R + Z2L·I2R)/(Z2L·(I2S + I2R))}` | maquete | Johns & Jamali, IEE Proc. C 137(6), 1990; Girgis, Hart, Peterson, IEEE Trans. PWRD 7(1), 1992 |
| Novosel — sequência positiva, sem sincronismo (serve para trifásica) | futuro | Novosel, Hart, Udren, Garitty, *Unsynchronized two-terminal fault location estimation*, IEEE Trans. PWRD 11(1), 1996 |
| Linha de três terminais / correção de infeed | futuro | Cap. IV 148–150, 158, 173; Cap. V 12–13; Exercício 10 |
| Ondas viajantes (tipo D) | adiado — ver CLAUDE.md, TWFL | Gale et al., 5th IEE DPSP, 1993 |

**Por que a sequência negativa 2T é a mais precisa** (e é ela que o painel
recomenda primeiro):
- a sequência zero não entra, então o Z0 da linha — o parâmetro mais incerto —
  não importa;
- a Rf e a carga se cancelam: as duas pontas veem a mesma tensão no ponto da
  falta;
- só entram MÓDULOS, então os relés não precisam de sincronismo. Alinhar
  pelo início da falta basta, e só para os dois serem lidos dentro da falta
  sustentada.

Ela perde precisão quando um terminal manda pouca I2 (fonte fraca) somado ao
ruído, e não serve para trifásica (sem I2).

No Monte Carlo da maquete (200 faltas sorteadas: Rf 0–40 Ω, carga ±35°,
fonte remota ×0,4–4,4, não homogeneidade −22° a +4°, Z0 ±15 %, ruído 0,4 %),
a sequência negativa 2T põe 90 % das faltas dentro de ~0,2 km; o melhor
método de um terminal, dentro de ~6 km. **Número de simulação**: o
comissionamento com registros reais é que vai dizer o de verdade.

### Um terminal

| método | estado | fonte |
|---|---|---|
| Reatância polarizada por 3I0 (Takagi modificado) | maquete | Cap. IV 63, 70–72; Exercício 8 (validado); Schweitzer, *A review of impedance-based fault locating experience*, 1990 |
| Reatância polarizada por I2 | maquete | Cap. IV 63, 70–72, 137, 157, 216 (a polarização preferida: a rede de sequência negativa não muda com manobra de trafo aterrado) |
| Takagi (corrente superposta, precisa de pré-falta) | maquete | Takagi et al., IEEE Trans. PAS-101(8), 1982; o modelo do erro que ele corrige: Cap. IV 56–58 |
| Reatância simples — `Im{V/(I + k0·3I0)}/X1L` (o laço da falta) | **feito** (`faultloc/ldl.py`) | método da Energisa; Cap. IV 24, 27, 30, 63–66, 138–139; Exercícios 8 e 10 |
| Impedância aparente `\|Z\|/\|Z1L\|` | maquete (para mostrar por que não se usa) | Cap. IV 25–30, 56–62 |
| Nível de curto — só o módulo da corrente e as impedâncias de fonte | maquete | Cap. II 21–23, 87–88, 97–98; Exercícios 3, 4 e 7 (validado); Girgis, Fallon, Lubkeman, IEEE Trans. IA 29(6), 1993 |
| Eriksson (compensa a alimentação remota) | futuro | Eriksson, Saha, Rockefeller, IEEE Trans. PAS-104(2), 1985 |
| Compensação de mútua (K0M = Z0M/(3·Z1L), corrente da paralela) | futuro | Cap. IV 28–29, 213–217; Cap. III 44–47; Exercícios 2, 9, 11, 13; Wheeler, Proc. IEE 117(2), 1970 |
| Compensação da não homogeneidade (girar I_pol por ξ2/ξ0) | futuro | Cap. IV 74–87 |
| Fator de alcance de linha não transposta (por laço) | futuro | Cap. I 35–41; IEEE Std 1870-2019 |

Fórmulas do nível de curto (Cap. II 21–23; sistema radial, x em pu):

    trifásica    x = (E/|I| − |ZS1|) / |Z1L|
    bifásica     x = (√3·E/(2·|I|) − |ZS1|) / |Z1L|
    monofásica   x = (3E/|I| − |2·ZS1 + ZS0|) / |2·Z1L + Z0L|

Erra para longe com alimentação remota, Rf e fonte mais fraca que a do estudo.

### O que ajuda a ler a precisão (não localiza)

- **Rf máxima confiável da reatância** (critério SEL): `Rf_max ≈ (1 − m)·20·X1L`
  — Cap. IV 144.
- **Resistência de arco** (Warrington): `R = 8750·(l + 3·v·t)/(I_IED·I_arco^0,4)`,
  l em pés, v em mph — Cap. IV 44–48, 140–142, 166; Exercício 1. Para
  conferir se a Rf estimada é plausível.
- **Efeito da carga**: exportada → sobrealcance; importada → subalcance —
  Cap. IV 60–66, 144–145.

## Casos de teste (viram teste automático)

**Exercício 8** (Exercícios Resolvidos, slide 20): LT com Z1 = 2,11 + j24,87 Ω
e Z0 = 20,82 + j84,60 Ω, k0 = 0,836 ∠ −12,5°. Seis faltas AN com VA, IA e 3I0;
recalculado em 23/10/2026:

| caso | carga δ | Rf | x real | reatância simples | polarizada por 3I0 |
|---|---|---|---|---|---|
| 1 | 0° | 3 Ω | 0,75 | 0,790 | 0,754 |
| 2 | −35° | 3 Ω | 0,75 | 0,691 | 0,753 |
| 3 | 0° | 11 Ω | 0,45 | 0,547 | 0,464 |
| 4 | +40° | 11 Ω | 0,45 | **0,800** | 0,467 |
| 5 | −30° | 7 Ω | 0 | −0,001 | 0,006 |

O caso 4 é o retrato do efeito de reatância com carga importada. Os fasores de
entrada estão no slide; o teste os copia com a página citada.

**Exercício 7** (slides 17–18), nível de curto, 138 kV: ZS1 = j12,02,
ZS0 = j7,42, Z1 = j61,50, Z0 = j234,71 Ω. Alcances 76 % (3φ), 63 % (2φ), 40 %
(1φ com I50 = 1360 A), 29 % (residual com I50R = 1770 A) — os quatro fecham.

**Planilha LocDef**, folha COXIPO – BARRO DURO: m2 = 0,006230, 0,058 km de
COXIPO (já em `tests/test_seqneg.py`).

**Falta no caderno: caso de dois terminais.** O comissionamento de verdade
precisa de pares de registros reais dos dois terminais com a falta achada pela
turma de linha.

## Dois terminais precisam de alinhamento — o que isso quer dizer

A sequência negativa 2T não precisa de sincronismo de ÂNGULO (só módulos e o
ângulo de I2 contra V2 do mesmo terminal), mas precisa que os dois terminais
sejam **lidos dentro da falta sustentada**. Com o relógio de um relé 37 ms
adiantado, o mesmo cursor lê um terminal ainda na entrada da falta e o
resultado foge (na maquete: 24,5 km contra 26,1 km alinhado, falta em 25,8).
Por isso a aba «alinhar A × B» da maquete mostra as fases e a sequência
negativa dos dois IEDs, um sob o outro ou sobrepostos, com o platô marcado.

O 2T **sincronizado** é outra história: ele usa o ângulo absoluto, e o
alinhamento pelo início da falta (±½ amostra, ~5,6° a 32 am/ciclo) não basta.

## Bibliografia dos slides que trata do assunto

Ziegler, *Numerical Distance Protection* (Siemens, 1999) — tem capítulo de
localização; Altuve & Schweitzer, *Modern Solutions for Protection, Control
and Monitoring…* (SEL, 2010); IEEE Std C37.113-2015; Blackburn & Domin,
*Protective Relaying*, 4ª ed. (2014); Roberts, Guzmán, Schweitzer, *Z = V/I
does not make a distance relay* (SEL); Warrington, *Protective Relays* (1977).

E de fora dos slides, a referência geral: **IEEE Std C37.114-2014**, *Guide for
Determining Fault Location on AC Transmission and Distribution Lines*, e
Saha, Izykowski, Rosolowski, *Fault Location on Power Networks* (Springer,
2010).
