# Ideias anotadas pelo Alexandre — backlog

Lista enviada por ele em 17/09/2026 (anotações de WhatsApp + complementos na conversa).
**Não implementar ainda** — está aqui para não se perder. Transcrição fiel, com a
interpretação do Claude em itálico onde houve dúvida.

---

# Modos de análise por tipo de instalação (dito por ele em 11/10/2026)

**Não implementar ainda.** Escolhidos no menu principal, onde se envia o arquivo:

1. **Modo de análise de linhas.**
2. **Modo de análise de trafo + alimentadores.**
3. **Modo de análise de malha diferencial** — para comissionamento/energização de
   equipamentos novos.

# Versão 0.5.0 — calculadora (dito por ele em 11/10/2026)

- Fica num lugar **"escondido"**, para não ocupar muito espaço na tela — **a escolha do
  lugar é do Claude**, a propor.
- Operações básicas entre sinais: somar, subtrair, multiplicar, dividir, **mais de uma
  operação na mesma expressão**, e outras que o Claude julgar úteis.
- O usuário **cria e nomeia** sinais novos a partir dos existentes, e pode somar sinais
  novos com existentes.
- Os sinais gerados vão para o bloco **«Calculados»** do catálogo.
- Referência: a calculadora do **SEL SynchroWAVe**.

## Proposta aprovada por ele (11/10/2026)

Decidido com ele, uma pergunta por vez:

1. **Domínio: os dois**, escolhido ao criar a conta.
   - **Onda** (amostra a amostra): o resultado vira uma LINHA com as 5 colunas
     (onda, RMS, DC, 60 Hz, 60 Hz RMS), como o `IN`. Divisão de ondas não é
     oferecida no sentido físico (estoura em cada passagem por zero).
   - **Fasor** (60 Hz): `+ − × ÷`, operador `a` (1∠120°), `mod()`, `ang()`,
     `conj()`. Faz V1/V2, Z = V/I, S = V·I*. Resultado: módulo na curva, módulo
     e ângulo no cursor; mora na coluna `filtrado.rms`, como o `3I0`.
2. **Onde guarda: no registro, com «salvar como modelo».** O modelo é oferecido
   em todo arquivo que tenha os canais usados; sem eles, aparece riscado com o
   motivo.
3. **Extras da primeira versão:** `abs`, raiz, potência (`x²`) e
   `atrasar(x, ms)`. **Ficaram de fora por ora:** `girar(x, graus)` e
   comparação → digital (`x > k` virando sinal 0/1).

Decidido pelo Claude (ele delegou o lugar):

- **Lugar:** botão **«ƒx nova conta»** dentro do catálogo («+ sinal»), na barra
  ao lado de «editar grupos» e «canais». O sinal criado aparece no bloco
  «Calculados».
- **Sintaxe:** sinais entre colchetes com autocompletar —
  `([VAY] - [VBY]) / 1.732`. O usuário dá o nome.
- **Unidades conferidas:** A + A passa, A + V é recusado, V ÷ A vira Ω,
  V × A vira VA.
- **Primário × secundário:** cada canal é convertido ANTES da conta (mesma regra
  do resíduo), senão somar primário com secundário erraria por 1000× sem aviso.

---

# Plano de curto prazo (dito por ele em 20/09/2026, depois do push da 0.4.0)

Esta parte **é** para implementar, nesta ordem de intenção dele:

1. **Poder criar mais gráficos** — analógicos ou digitais. — **FEITO em 20/09/2026.**
2. **Cursores magnéticos** — *presumivelmente encostar o cursor em algo notável
   (passagem por zero, pico, transição de digital, início da falta).* — **FEITO.**
3. **Gráfico fasorial.** — **FEITO.**
4. **Gráfico do filtro de Fourier** — ver os harmônicos do sinal bruto. **Ele
   escolheu a curva de DC ao longo do tempo** (20/09/2026). — **FEITO.**
5. **Calculadora** — o usuário cria novos sinais a partir dos existentes.
6. **Comissionamento**: muitas oscilografias, conferir todos os valores calculados contra
   outros analisadores, e validar o nosso filtro com o par filtrado × não filtrado da
   MESMA oscilografia.

## O item 1, como ficou (20/09/2026)

O gráfico virou **painel**: uma lista ordenada, cada item com `{id, tipo, nome, sinais,
medida}` (`src/osclab/plot/paineis.py`). A tela manda a lista inteira no corpo do pedido
(`POST /api/onda/<sha>` e `.../leitura`) e o servidor desenha o que veio, na ordem em que
veio — ele não guarda arranjo nenhum.

Duas consequências que valem registrar:

- **A leitura do cursor passou a casar por id de sinal**, não por posição. Com painéis, o
  mesmo canal pode estar em dois gráficos com medidas diferentes.
- **Painel digital é painel**, e não um bloco fixo no fim. É o que permite pôr digitais
  ENTRE duas trincas de corrente — a leitura natural de um religamento.

## Sugestão para a DC%, que ele pediu (20/09/2026)

**Ele escolheu a segunda:**

- **No gráfico de harmônicos, a DC é a barra do índice 0.** Responde "quanto tem agora,
  neste cursor".
- **Como CURVA, no gráfico analógico, vindo do catálogo** (`IA DC`, em ampères, ou
  `IA DC%`) — **escolhida**. Responde "como ela decai", que é a pergunta de proteção
  de verdade: a constante de tempo do decremento é a relação X/R do circuito, e é ela que
  diz se o TC vai saturar.

**Ressalva que precisa estar na tela:** a "DC" que sai de uma janela de um ciclo não é uma
componente contínua de verdade — é a **média daquele ciclo**, e ela decai.

## Sobre o comissionamento (item 6), para ele decidir antes de começar

O resultado daquela etapa **não pode morar só numa conversa**. Proposta: um gabarito
versionado no repositório com os valores esperados por registro e por cursor (JSON), lido
por um teste. Os **números** podem entrar no repositório público se anonimizados — mas
**as oscilografias não**. O teste procura os arquivos numa pasta local (fora do git) e se
declara pulado quando ela não existe.

---

# Backlog original (17/09/2026)

## Localização de faltas

1. **Calcular em tempo real a posição da falta** pelo método de um terminal e pelo método
   de dois terminais (sequência negativa), ao vivo, e se possível **pegando os parâmetros
   de impedância da linha automaticamente**.
   - *O método de dois terminais por sequência negativa é o não sincronizado — encaixa com
     o problema de GPS da distribuidora.*
2. **Mostrar se a falta está para trás ou para frente** na linha (direcionalidade) e
   **identificar se houve recepção de teleproteção**.
3. **Mostrar a estrutura da falta pelo KMZ** — cruzar a distância estimada com o arquivo
   KMZ de estruturas/postes para apontar o poste provável.

## Ajustes dos relés desenhados sobre o registro

4. **Desenhar os ajustes das funções ao vivo:** 50/51 (curva tempo × corrente), 21 mho e 21
   quadrilateral, entre outras.
5. **Trajetória da impedância ("bolinha") no plano R-X** — **FEITO em 20/10/2026**, como
   painel de impedância ligado aos cursores.
6. **Ponto móvel sobre a curva do 51**, acompanhando o valor da corrente ao longo do
   registro.
7. **Mostrar o estado do disjuntor** ao longo do registro.

## Análise da perturbação

8. **Identificar se a falta ocorreu no ponto máximo da tensão** ou não (ângulo de
   incidência).
9. **Identificar cabos batendo na distribuição** (conductor clashing) — faltas transitórias
   repetitivas, de curta duração.
10. **Filtro de Fourier para comparar os harmônicos em um inrush de trafo.** — *virou o
    item 4 do plano de curto prazo.*
11. **Identificar o grupo de ligação do transformador** (Dyn11 etc.) a partir da defasagem
    entre os lados no registro.
12. **Identificar se o sistema está radializado ou em anel**, para constar no mini
    relatório.
    - *A mais difícil da lista: provavelmente não se resolve só com a oscilografia.*

## Visualização

13. **Alternar entre variáveis do relé (word bits) e variáveis do software** — *feito em
    20/09/2026, nas abas IED × OscLab do catálogo de sinais.*
14. **Desenhar o triângulo de tensões** — *feito.*
16. **Marcar cada amostra com um pontinho** no traço — opcional, **desligado por padrão**.
    *(Pedido em 18/09/2026.)*
    - O detalhe que decide a implementação: com a janela ampla, o traço **não é feito de
      amostras** — é o mínimo e o máximo de cada coluna de pixel (`plot/serie.py`). Pôr um
      ponto em cada vértice ali seria desenhar amostra onde não há.
    - Regra: o ponto só aparece quando a janela **não** foi reduzida — o servidor já
      informa isso no campo `reduzido`.
17. **Ler fasor e RMS no cursor** — *feito no marco 0.4a.*

## Alinhamento

15. **Alinhar oscilografias automaticamente**, identificando pontos em comum — tanto para
    linha quanto para **"trafo com als"**. *Termo "als" a confirmar com o Alexandre.*
    - No caso de linha, com o GPS da distribuidora não confiável, o alinhamento por
      descontinuidade é a via principal (ver `requisitos-funcionais.md`, seção 4).

## Consequência de arquitetura que essa lista revela

Vários itens (1, 2, 4, 5, 6) dependem de **ler os ajustes do relé**, não só a oscilografia.
Isso é uma **terceira classe de entrada** do programa — ver
`ajustes-e-logica-dentro-do-registro.md`, que responde boa parte dessa pendência: em muitos
casos os ajustes já vêm dentro do próprio arquivo de oscilografia.

## Pendências de esclarecimento

- O que é "trafo com als" no item 15.
- O que "em tempo real / ao vivo" significa no item 1: conexão com o relé, ou recálculo
  instantâneo conforme o usuário move os cursores sobre o registro já aberto?
