# Onde o trabalho está

**11/11/2026 — realce do desenho da subestação no ramo `realce-subestacao`, para revisão:** claro 31 (aresta de 0,50 px no início, cor de sempre: traço ÷ título 18 %), escuro 19 (0,51 px, 28 %), colados no `portal.css` como o `exportar_realce.py 31 19` da maquete gerou. Sai o `vector-effect` do escuro; a casca da casa de arquivos e base deixa de sair com 1 px. Conferido contra a maquete: diferença máxima de 3/255.

**11/11/2026 — tema escuro = paleta 08 «Ardósia clara», no ramo `escuro-08`, para revisão:** todos os tokens do escuro (página, milimetrado, gráficos, barra, rodapé, fases, digital, cursores, localizador, calculadora) mais o desenho da subestação no realce 20 (0,79 px, 34 % do título). `tools/paleta.py` atualizado, e as convenções de fase do escuro (`fases.css`) reajustadas ao fundo novo. O claro não mudou.

**11/11/2026 — calculadora em gaveta (variante 10) implementada no ramo `calculadora-10`, para revisão:** domínio fasor, funções novas, nomes padronizados (a fileira IA…VN insere o nome completo do canal; seletor de grupo «G1 · radical» com duas trincas), `{k0}` com origem, TC sem relação digitável, sugestões e «guardar como modelo»; defeito do main corrigido (conta + filtro → erro 500). Teste de navegador com nomes longos (`tests/test_calculadora_navegador.py`). **Perguntas abertas:** conta livre no fasor ou só laços prontos; relação de TC digitada vale só para a conta ou para o canal; conta de unidade nova ganha gráfico próprio; separador `;`.

**11/11/2026 — janela de eventos (variante 03) implementada no ramo `eventos-03`, para revisão:** `.hdr` da Schneider lido sozinho; SER e `.eev` só pelo «+ arquivo», valendo na aba, sem gravar; trilha da distribuição contada no Python; nada classificado por nome. Ver `docs/log-de-eventos.md`.

## 10/11/2026 (noite) — fila combinada com o Alexandre, para retomar depois de compactar

Identidade visual f10 no main e publicada (4d09705). Localizador: **variante 17 escolhida**
(maquete em `../osclab-maquetes`, ramo `maquete/localizador-grafico`, 85c3aec), com dois
ajustes antes de virar padrão:
- sai a troca **R+jX ⇄ |Z|∠θ** da janela «parâmetros» (a tabela já mostra as duas formas);
  ficam `Ω/km` e primário/secundário — conferir com ele se o `Ω/km` fica;
- saem as **wordbits** embaixo dos valores do relé («de Z1MAG, Z1ANG, PTRY, CTRW»):
  ele esperava uma variável por valor, e o valor derivado confunde.

Ordem proposta (aguardando o ok dele). Paralelo = agentes desta sessão, cada um no seu
worktree e porta; **nunca dois terminais** (decisão dele).

| rodada | frente | depende de | onde |
|---|---|---|---|
| 1 | **A. Localizador 17 no main**, de verdade e com testes (tela de localização desligada, cabeçalho km/%/parâmetros + comprimento, rodapé só com o trecho a patrulhar, hachura sem «não mede», âmbar do relé, «? métodos», janela «parâmetros» em faixas com Relé/Base/Digitado e «usar» por coluna, vermelho quando difere, selo `relé ≠ base` com Z1/Z0-k0/LL, «a partir de SE X / deste terminal / do IED A») | — | main |
| 1 | **B. Eventos**: janela no padrão da «lógica» — vista formatada + «texto» cru; fontes: eventos do Schneider no `.hdr`, **`.eev` da GE** (ele tem um exemplo real; ler o formato localmente, nunca versionar; a maquete usa `.eev` fictício no mesmo formato) e `.txt` de relé (bloco de notas). Retomar o que já existe: commit 8fd0832 (eventos, maquete 1) e `Desktop\OscLab maquetes\eventos-10.html` | — | worktree `maquete/eventos`, porta 8773 |
| 1 | **C. Calculadora**: dez maquetes funcionais, aberto a sugestões (a 0.7.0 já tem o domínio ONDA) | — | worktree `maquete/calculadora`, porta 8774 |
| 2 | **D. Menus lado a lado**: uma página que abre os menus de TODOS os gráficos (incl. «+ sinal», parâmetros do localizador) pós-A, para ver se parecem da mesma mão; e o caso de **duas oscilografias na mesma aba** (como fica «parâmetros» com dois IEDs). Depois, padronizar | A | 8771 |
| 2 | **E. Refino da seq. negativa (dois terminais)**: botão «refinar» ao lado da legenda da seq. negativa → janela com V e I do relé A e do relé B; chave fase ⇄ seq. negativa; alinhamento **automático (padrão)** ⇄ manual (escolher pontos por cursor ou outra forma); zoom nas analógicas/sequência; ao lado, I2/V2 ao vivo com o cursor e a localização por seq. negativa a partir de um IED; campo para digitar a seq. negativa à mão. Antecedente: `Desktop\OscLab maquetes\localizador-refino-10.html` (04/11, sem escolha) | A | 8771 |
| 3 | **F. Modo escuro**: várias paletas para ele escolher, tudo validado no `tools/paleta.py`. Por último, de noite (ele pede quando for dormir) | B–E escolhidos | 8771 |

**Replanejado às 21h50, com o ok dele** (ele volta no máximo duas vezes antes de dormir):
A–E rodam JÁ, todas em paralelo; D e E usam a 17 da maquete em vez de esperar o main.
Na 1ª volta ele avalia; na 2ª dá os vereditos e pede o F (escuro), que roda de madrugada.
Onde está cada uma: A `../osclab-localizador` (ramo `localizador-17`, porta 8776, merge no
main só depois da minha revisão) · B `../osclab-maq-eventos` 8774 · C `../osclab-maq-calculadora`
8775 · D `../osclab-maquetes` ramo `maquete/menus` 8771 (também ajusta a 17) ·
E `../osclab-maq-refino` 8773. Padrões assumidos sem resposta dele: `Ω/km` fica; o `.eev`
real (pendrive) é lido só para aprender o formato, a maquete usa um fictício.

**Resultado da noite (22h40):** A juntado no main (d166c90, suíte ok, sem push). Maquetes prontas e no ar:
B eventos 8774 (`.eev` = CSV do EnerVista; recomendadas 02/03) · C calculadora 8775 (recomendada 10)
· D vitrine http://localhost:8771/maquete/menus/ (72 menus, 9 desconexões) + dois IEDs nas
variantes 18/19/20 · E refino 8773 (recomendada 03+01+06+02). Perguntas de cada uma nos `.md`
das maquetes. **Defeito no main:** com dois IEDs, em secundário, a coluna do relé B usa a
relação do relé A (`faultloc/parametros.montar` recebe um `rtp_rtc` só) — corrigir junto com
a escolha 18/19/20. **Defeito no main achado pela C:** conta do usuário + filtro 60 Hz = erro 500
(`plot/catalogo.efetivo`). Falta F (escuro), de noite.

**Para a manhã de 11/11 (as três janelas do Chrome ficaram abertas):**
- Etapa 1: localizador 17 (8776, já no main) · eventos 8774 (limpos; recomendadas 02, 03 e a nova 10 «trilha»)
  · calculadora 8775 (limpa; recomendada 10, alternativa enxuta 04 «ƒx na legenda»).
- Etapa 2: vitrine dos menus 8771 `/maquete/menus/` (por peça · comparar · ficha · dois IEDs 17–20;
  achados novos: bolinhas de cor em Arial; lógica/eventos fecham no Esc mas não no clique fora)
  · refino 8773 (limpo a pedido dele; pergunta: B tracejado com várias fases ou uma tira por fase?).
- Etapa 3: paletas do escuro 8777 `/maquete/escuro/` (dez, todas passam no validador; recomendadas 09
  Heliográfica e 05 Carvão quente).
- A corrigir no main, com ele: relé B convertido pela relação do A (dois IEDs, secundário) e erro 500
  da conta do usuário com filtro 60 Hz (`plot/catalogo.efetivo`). Nada de push ainda.

Regras de sempre: maquete antes (dez por função nova), versão `0.8.0` só quando ele aprovar
a rodada, push só com a confirmação dele.


## 10/11/2026 — o painel localizador da variante 17 (ramo `localizador-17`)

Feito, a partir da maquete `maquete/localizador-grafico` (variante 17, com os dois
ajustes pedidos: sem a troca R+jX ⇄ |Z|∠θ e sem as wordbits sob os valores do relé):
a TELA de localização desligada (`TELA_LOC_LIGADA = false`, código guardado); cabeçalho
com km / % da linha, «parâmetros», «? métodos», `comprimento` e o selo `⚠ relé ≠ base`;
hachura onde a curva não mede, colchete do platô, relé em âmbar (paleta `LOCALIZADOR`
em `tools/paleta.py`); rodapé só com o trecho a patrulhar; janela «parâmetros» refeita
(Relé · Base · Digitado, «usar» por coluna, vermelho além da tolerância, Ω/km e
primário/secundário como vista). Conta em `faultloc/parametros.py`, com testes.
`sugerida`/`casou` saíram da busca da base. `CONTRATO` 24 → 25.

Pendente com o Alexandre: revisar e juntar no `main`; versão `0.8.0` quando aprovar.

## 09/11/2026 — painel localizador, parâmetros da linha e linhas de três terminais (commits 469091c … 36261f5)

Feito: painel «localizador de faltas» (curvas dos métodos no tempo; curva apagada fora do
trecho em que mede; triângulo quando sai da moldura; «relé não mediu» do MiCOM); janela
«parâmetros» (escolher a linha na base ou digitar; vale com um terminal só); dicionário
pausado como implementação futura (`futura=True` em `basedados/pasta.py`, nada apagado);
linhas de três terminais (`basedados/tres_terminais.py`, arquivo `linhas/linhas-3t.csv` ao
lado do `linhas.csv`, que não é tocado; caminho A–B com perfil; papéis marcáveis na tela;
TAP cadastrável à mão). O `linhas.gravar` deixou de perder colunas e linhas sem parâmetro.

A carga do `linhas-3t.csv` é `docs-privados/montagem-base-linhas/tres_terminais.py`, pela
topologia do OnLiner (barra com número 0 = identificada pelo nome; conta barras vizinhas
distintas, não ramos). Rodar de novo não sobrescreve o que foi marcado ou cadastrado à mão.
Resultado na base: 14 certas, 2 a conferir, 16 sem TAP confirmado (relatório em
`relatorio-da-montagem/tres-terminais.md`).

Pendente com o Alexandre:

1. **Linhas arrumadas pelo Caderno de Manobras (rev. 10) e pela LDAT**, a pedido dele, no
   `linhas-3t.csv` da base (cada registro com a folha ou o código na nota): Alto Boa Vista–
   Confresa corrigida (A = Alto Boa Vista, TAP = Espigão do Leste, 137 km A–B); TAP de
   Morro da Mesa, Mineradora e Cargill cadastrados; 9 linhas em trechos confirmadas sem TAP;
   Campos de Júlio–Comodoro seccionada na Coletora Comodoro. Resumo: 19 de três terminais,
   9 sem TAP, 1 seccionada. Continuam a conferir: Rio Claro (caderno sem derivação ×
   OnLiner com ramo de 54 km), LRV Dist. Ind.–Foz do Cedro (ligação provisória para Canoa
   Quebrada, FL.52) e Sinop–Sinop Centro (chave 305 NA, FL.47) — o que cada fonte diz está
   em `duvidas-para-refinar.md` (itens 12–14), na pasta da base, para ele refinar com o
   OnLiner aberto; toda dúvida de modelagem sai nessa etapa. Coxipó/B. Duro II–Distrito
   não tem km nem Z na base (FL.12: direto, sem TAP). A cópia `linhas-3t.antes-de-
   arrumar-…csv` é de meio caminho; a original se refaz com o script da montagem.
2. Os trechos que o caderno não resolve pedem o relatório de barras do `.olr`.
   **Decisão de 10/11/2026: a base fica só com as linhas de qualidade BOA (115).** As outras
   60 (16 casadas pelo comprimento, 4 com km discordante, 3 derivações a conferir, 2 de
   fonte mista fora do padrão, 2 sem comprimento, 33 sem impedância) foram para
   `linhas/a-conferir/`, inteiras e com o motivo, e voltam numa etapa de conferência com o
   OnLiner aberto. Relatório da montagem, com uma linha de exemplo:
   `relatorio-da-montagem/como-a-base-foi-montada.html` (gerado por
   `docs-privados/montagem-base-linhas/relatorio_base.py`). Atenção: o `montar.py`
   reescreve o `linhas.csv` e traria as separadas de volta.
3. ~~Casagem automática com dois registros~~ — **retirada em 10/11/2026**, decisão dele:
   o programa não adivinha linha. A linha da base é sempre escolhida em «parâmetros»;
   a estrela de «sugerida» também saiu (`sugerida`/`casou` seguem no pacote, sempre
   falsos, até a janela ser refeita).
4. A janela «parâmetros» vai ser refeita na repaginação da identidade visual (pedido dele).
5. Versão: nada subiu; `0.8.0` quando ele aprovar a rodada.
6. Push: commits de 09/11 ainda não enviados.

## Noite de 01/11/2026 — o dicionário dos digitais (commits 3bc20f3, a7665be)

Decisões do Alexandre: `partida` → `pickup`; entram `teleprotecao`, `comando` e `alarme`;
colunas `funcao` (ANSI), `fase`, `estagio`, `fonte`, `referencia`; e a camada da
**instalação** — o uso de um elemento é do AJUSTE, não do modelo (o 50 estágio 2 que envia
seletividade lógica num alimentador, o 50 estágio 3 que bloqueia o religamento noutro). A
tela da base edita tudo no clique, exporta e importa o CSV.

Conteúdo (fora do repositório, na base do usuário): os verbetes de modelo vieram dos manuais
(definições dos bits SEL em inglês, com a página); os de instalação, da **lógica SELOGIC que
vem dentro do `.CEV`** — equação, comentário do engenheiro e apelido do sinal (`fonte =
ajuste`); os demais, da gramática dos nomes de cada fabricante (`fonte = deduzido`). Mais de
95 % dos digitais que mudam no banco de oscilografias saem descritos. Scripts e relatório em
`docs-privados/dicionario/`.

Defeitos achados e corrigidos: Ingeteam (modelo no campo de estação, ou fabricante só no nome
do arquivo) e SIPROTEC 5 (número de série no campo do equipamento) não casavam verbete de
modelo; a consulta por registro varria a lista inteira por sinal (1,2 s → 0,28 s).

Pendente com o Alexandre: categoria da seletividade lógica (pus `bloqueio`); confirmar «HCL»
como linha viva e `BM…` como SIPROTEC 5; a cor do `alarme` no tema claro (ΔE ~6 do bloqueio).

## 31/10 e 01/11/2026 — trincas, classificador, LDL de um terminal e a base de linhas (commits e68792b … 4585b9c)

Feito no programa:

- **Trincas** do GE UR, do GE 850 e do MiCOM P632; `IY` é neutro; `VX` fica sem vínculo.
- **Classificador**: inrush não é falta (2º harmônico ≥ 20 %, corrente subindo, tensão sem afundar);
  a falta que evolui até a trifásica é dita como evolução.
- **LDL de um terminal**: o resultado sai pelo Takagi I2 na falta assimétrica e pelo Takagi ΔI na
  trifásica (`ldl.preferencia`).
- **Conferência 10 (21)**: tolerância pela oscilação do nosso próprio número, com teto, e o veredito
  «possível medida no transitório».
- **Conferência 1 (resíduo)**: «polaridade invertida» e «entrada própria» deixaram de ser reprovação.

**Base de linhas da distribuidora (dado privado, fora do repositório).** Montada a partir do OnLiner
(ASPEN), da planilha de instalações, do PAM e do Caderno de Manobras; os scripts ficam em
`docs-privados/montagem-base-linhas/`. Três lições de método que valem para qualquer base:

- **O OnLiner tem a linha; quem falha é o casamento.** O nome da barra no estudo é abreviado e não
  lembra o da SE. O **comprimento** (da planilha ou do traçado das estruturas) serve de impressão
  digital: uma ponta pelo nome, a outra onde o caminho fecha em 2 %, com tensão igual, só na área
  ASPEN da distribuidora (a base é nacional) e com saída única. A barra deduzida fica escrita.
- **Nunca estimar impedância pelo condutor** para preencher buraco. Linha sem parâmetro fica sem
  parâmetro, com o motivo e a fonte a cobrar.
- **Derivação** se compara pelo ramal, não pelo tronco; linha **seccionada** sai da base; o
  comprimento da planilha às vezes é o de um vão.

**Pendente com o Alexandre:**

1. Refinar a base com a proteção: exportar do mesmo `.olr` os relatórios de barras, de chaves e de
   34,5 kV, e dizer qual barra é cada SE não reconhecida (lista pronta em `docs-privados`).
2. Os ajustes dos relés como conferência da base: cobertura parcial (só o `.CEV` da SEL traz o
   ajuste dentro da oscilografia); levantar o que os arquivos de ajuste cobrem.
3. Os 4 registros de um alimentador em que o relé diz CA e o classificador diz energização.
4. Fila: o dicionário (lógicas dos IEDs + manuais), cores do tema claro.

Feito depois: o **`b1`** chega à localização — da base (`seqneg.linha_da_base`; zero não é
capacitância, é o que o OnLiner escreve sem o dado) e digitado (campo B1, opcional, na tela; o
«guardar na base» grava junto). O `J2 Vn` do 850 que estava na fila **já não era pendurado** como
resíduo em nenhum dos 573 registros do banco desde `e68792b`. A régua «resíduo tem de ficar
negativo» foi tentada e desfeita: ela tirava do grupo a entrada de neutro do PL300 nos registros
sem falta à terra (só o ruído do conversor) e a deixava nos com falta — o mesmo relé mudando de
arranjo de um registro para outro.

## 25/10/2026 — confiabilidade e universalidade (commits b6c1495 … 3b1a958)

**Princípio novo (CLAUDE.md): o leitor é universal.** Qualquer relé abre e
analisa; o que não se lê automaticamente se digita; nada do parque da
Energisa MT pode virar condição.

Feito:

- Diferencial 87T sai em 28/28 registros de 487E/787 (o `ccbm` com o nome do
  relé juntava os terminais; `E87HR` lido). 87L: cada terminal vira trinca,
  o plano de impedância casa `I*` ↔ `V*`, o alfa lê `87LPR/87LPA` e `87LR/87LANG`.
- Paleta: o validador simulava daltonismo errado (fora do espaço LMS);
  corrigido. Tema ESCURO com cores novas escolhidas pelo Alexandre.
- LDL: validação independente virou `tests/test_ldl_validacao.py`; nota 50 → ~75.
- Rotinas contra o dado real: `tools/comissionar.py` (placar em
  `docs-privados/comissionamento/`), `tools/fotografia.py` (foto em
  `docs-privados/fotografia/banco-2026-10-25.jsonl`), `tests/test_varredura.py`.

**Pendente com o Alexandre:**

1. `git push` dos commits do dia.
2. Cores: escolher entre as 10 maquetes de «cores das fases»
   (`OscLab maquetes/cores-das-fases-10.html`) e as cores do tema CLARO (ele
   ainda reprova no validador corrigido).
3. Classificador: «falta já em curso» (inclui a falta entre 1 e 2 ciclos do
   começo, xfail em `test_varredura.py`), os 74 religadores «AG sem trip»,
   seleção de fase do relé como prova.
4. LDL: Takagi como RESULTADO de um terminal quando houver pré-falta (hoje
   é só conferência; o pior erro com carga cai de 50 para 5 km, mas piora no
   TC saturado e na falta à terra perto da barra). Antes, medir o Takagi
   polarizado por I2. A capacitância `b1` ainda não tem campo na tela.
5. Propostas de função nova (pedem 10 maquetes): diferencial juntando dois
   registros (P139/451), ajustes do MiCOM por exportação de texto do Easergy,
   ajustes do PL300 pelo `AJUSTES_*`.

6. Plano de impedância: a ficha «% da LT» é |Z|/|ZL| e soma a Rf ao
   comprimento (Rondonópolis CG: 16,5 % contra 12 % do relé). Mostrar a
   reatância, as duas, ou deixar?
7. A conferência 1 (resíduo) reprova 72 registros do banco em que o `IN`
   medido é entrada própria (`Current IN` do MiCOM, `IN` do 311C, `INS`
   sensível do PL300). Não é defeito de conta; a conferência precisa
   reconhecer esse caso em vez de reprovar.

Feito depois (commits 7a153f8, 51157ed, f71e71d): 87T com bloqueio e
restrição juntos; LDL recusa a trifásica externa (a direção comparava fasores
que giram), Takagi de conferência, seq. negativa pela linha distribuída;
plano de impedância com k0 sobre a soma das fases (o `IN` do 311C é entrada
própria e tirava a compensação: 6 de 22 faltas reais erravam até 71 pontos);
conferências 9 (87T) e 10 (21) contra o relé — na 10, só o 321 de Coxipó
diverge, sem explicação ainda (conferir no SIGRA).

## 24/10/2026 — etapa de aprendizagem sobre o banco do parque (sem commit)

O banco inteiro de oscilografias (558 registros) foi lido, junto com os `.hdr` e os manuais dos seis fabricantes. O que se aprendeu, com os dados reais, está em `docs-privados/aprendizado/`, e o dicionário dos digitais em `docs-privados/dicionario/dicionario.csv`, com 2077 verbetes prontos para importar. Nada disso entra no git.

Defeitos corrigidos, cada um com teste:

- **Dialetos SEL:**
  - o `.CEV` do 311C/311L (`"FID",<soma>`), que não abria;
  - um leitor novo para o relatório EVE em texto do SEL-321 (`formats/sel_texto.py`).
- **Taxa `nrates = 0`:** o `.cfg` do SEL-751 e do 311C não declara taxa, e `analysis/falta.py` lia `sample_rates[0]`, que vale 0 nesse caso. Faltas de 9 kA saíam «nenhuma descontinuidade». Agora a taxa sai de `Record.trechos`.
- **Trincas que não fechavam:**
  - O religador escreve `T1 Phase C Current` e a última ocorrência do C é a de `CURRENT`.
  - O PL300 escreve `IA-Int.Fase A`, com a fase duas vezes, e o `Int.` era lido como neutro.
  - O acento de `Tensión` soltava o N.
  - A correção é uma **segunda tentativa** (`conjuntos._sem_as_marcas`), só para quem a primeira deixou sem trinca. A fotografia do banco antes × depois mostrou que nenhuma trinca que já fechava mudou.
- **Data da edição 1991:** a norma manda `mm/dd/aa`, e ela era lida como dd/mm.
- **`.dat` ASCII com linha colada (coletor RTAC):** a amostra perdida comprimia a onda. Agora cada amostra vai para a posição do seu número, e o que se perdeu fica em branco, com aviso.
- **Trip em espanhol:** `disparo_do_rele` passou a reconhecer `Disparo` (Ingeteam).
- **`k0`:**
  - Agora se lê `k0M1`/`k0A1` em par.
  - `Z0F`, que é o limiar do 32G e não k0, deixou de ser usado.
- **Dicionário:** `identificar` passou a entender a FID da SEL (`FID=SEL-487E-3-R312…` → SEL 487E; `411L-A` → 411L) e o MiCOM.
- **Digitais sem placa:** os digitais que a placa do relé não tem saem da tela padrão (`[IOBOARDS]`).

**Em aberto com o Alexandre:** a lista está no relatório da sessão. O principal:
- os 74 religadores que agora saem AG sem trip;
- a identificação de fabricante do PL300 e do SIPROTEC, que não vem no campo do equipamento;
- a cor do cursor 2, que o validador de paleta não confere;
- as maquetes do acervo e dos temas.

## 23/10/2026 — localização de falta, etapa 1 de 3 (sem commit)

O painel 1 das maquetes entrou no programa: **«localizar falta» abre uma tela
própria** no lugar das ondas, com a faixa do resultado presa no topo e três
passos (alinhar A × B, conferir o platô, resultado). A conta é
`faultloc/ldl.py`: a LDL amostra a amostra pela **sequência negativa de dois
terminais** e pelo **laço da falta (reatância)**, a mediana do platô, a
direção pela seq. negativa com V2 na referência, e o cursor 1 compartilhado
com a oscilografia. A linha ganhou **Z0** (base, ajustes Z0MAG/Z0ANG,
digitado). Testes em `tests/test_ldl.py`. Ver `localizacao-de-falta.md`.

**Próximo:** etapa 2, a aba de simulações (painel 1 da maquete
`localizacao-painel-1.html`); depois a etapa 3, a ajuda dos métodos.
**Em aberto com o Alexandre:** a polaridade de corrente dos registros reais
(ver «O que os registros reais mostraram» em `localizacao-de-falta.md`).

---

Atualizado em **21/10/2026**, versão **0.7.0**. Este arquivo existe para uma
sessão nova saber de onde continuar sem reler o histórico inteiro. Mantê-lo
curto e atual vale mais do que mantê-lo completo.

## O ponto exato

A última rodada fechou o **plano de impedância**, incluindo os ajustes
manuais. O próximo passo, escolhido pelo Alexandre em 21/10/2026, são os
**outros três gráficos** — complexo, espectro e plano alfa —, que já têm
maquete aprovada e nenhuma pergunta de engenharia em aberto.

Suíte: **725 passam, 0 falham, 19 pulam** (`python3 tudo.py` da raiz).

## O que já funciona

| Parte | Estado |
|---|---|
| Leitura | COMTRADE (`.cfg`/`.dat`), `.CEV` + `.HDR` da SEL, com detecção de filtragem |
| Acervo | importação, metadados, selo do tipo de falta no cartão |
| Painéis | analógico, digital, fasorial, triângulo de tensões, harmônicos, **plano de impedância** |
| Análise | classificador de tipo de falta (11 tipos), com os porquês escritos |
| Base de dados | pasta, gavetas, dicionário de sinais digitais |
| Ajustes do relé | lidos do `SETTINGS` do `.CEV` e do `.HDR`; painel de lógica |

### O plano de impedância, em detalhe

É o painel mais novo e o que tem mais decisão acumulada. O registro completo
está em `plano-de-impedancia.md` no projeto do Claude; o essencial:

- Entra pelo «+ adicionar gráfico» e nasce no **laço que o classificador
  achou** (`data-laco` no `<body>` do `onda.html`).
- Desenha trajetória, zonas, parâmetros da linha, MTA e os dois cursores. Os
  pontos da trajetória só aparecem **enquanto a mão está no cursor**.
- **Todo número carrega a origem**: `lido` (traço cheio), `sugerido`
  (tracejado) e `digitado` (pontilhado). Uma zona inventada que pareça lida
  do relé é o pior defeito que esta tela pode ter.
- Os ajustes manuais ficam numa caixa pendurada no `body`, **não dentro do
  painel**: cada tecla pede a janela ao servidor de novo e a resposta refaz
  os painéis, então um menu no cabeçalho sumiria a cada letra.
- O que se digita é **ohm secundário**, como o ajuste do relé. O JSON traz um
  campo `ajuste` com os valores antes da conversão de base — é o que o
  formulário edita.

## A fila

1. **Os outros três gráficos** — complexo, espectro, plano alfa. ← aqui
2. **Abas e multi-registro** — duas oscilografias independentes em abas, e a
   tira para somar um terceiro registro na mesma janela.
3. **Localizador de falta** — reatância simples, Takagi com 3I0 e Takagi com
   ΔI. É o propósito do programa, e tudo o que ele precisa já existe.
4. **Relatório automático** — a outra metade do propósito, ainda sem nada.
5. **Log de eventos** — do `.HDR` quando vem, ou importado de `.txt`.
6. **Popular a base** — todas as linhas e todos os sinais digitais.

## Pendências conhecidas

Dívidas reais, não ideias. Cada uma já foi vista e deixada para depois:

1. **`tudo.py` pula em silêncio quem pede fixture** — 239 de 646 testes. Teste
   que não roda é pior que teste nenhum. Os testes novos de `impedancia` e
   `falta` foram escritos **sem fixture** por causa disso.
2. **Entrada na zona medida na trajetória decimada** (600 pontos): erra
   algumas amostras num registro longo.
3. **Quadrilátero não desenhado** — o relé declara (`E21MG`, `XG1`/`RG1`) e o
   painel só faz mho.
4. **Vínculo em delta é recusado inteiro** no plano, mas
   `Z_AB = V_AB / (I_A − I_B)` sai direto de uma trinca de linha. Só o laço
   de terra é que não.
5. **«entrou Z1 · amostra 71»** usa o índice cru da amostra. Seria mais útil
   em ms depois do início da falta, ou em ciclos.
6. **A sugestão de zona** (80 %, 120 %, 200 %) está **a confirmar com a
   proteção**.
7. **`OSCLAB_DATA_DIR` aponta para dentro da pasta do programa** — acervo,
   cache e base no mesmo lugar do código. Decisão pendente: mudar só a base,
   mover a pasta de dados inteira, ou deixar como está.

## Como rodar

```
python3 tudo.py                 # a suíte inteira, da raiz
osclab.cmd                      # o programa (reiniciar após mexer em .py ou template)
```

Depois de mexer só em `.js` ou `.css`, Ctrl+F5 no navegador basta — o Jinja
cacheia template, então template exige reiniciar.

Servidor de desenvolvimento, quando for preciso um porta separada:

```
OSCLAB_DATA_DIR=<dir> python3 app.py --web --port <N> --no-venv --skip-install
```

**Amostras fictícias** para testar sem registro real: duas oscilografias
coerentes entre si (COMTRADE e `.CEV`+`.HDR`), dois terminais da mesma linha,
falta AN a 62 % com 1,5 Ω de arco. Ficam **fora do repositório**, na pasta de
arquivos do OscLab no computador do Alexandre, com um `LEIAME.md` e o script
que as gera.

## O que NÃO está neste repositório, e por quê

O repositório é **público** e os direitos são da distribuidora.

- **Oscilografias reais** da empresa. As fictícias existem justamente para
  isso; as reais ficam fora, apontadas por `OSCLAB_AMOSTRAS`.
- **Manuais de fabricante** — direito autoral. Entra o dado factual escrito
  com as nossas palavras, nunca o manual.
- **A base de dados** — KMZ das estruturas, parâmetros de linha, histórico.
  `/base/`, `/database/`, `/base-*/` e `/bases.json` estão no `.gitignore`.
- **`config/config.ini`** — tem IP e senha de equipamento. O modelo versionado
  é o `config.ini.example`. Uma senha de subestação commitada fica no
  histórico para sempre.
- **Os docs do projeto com dado da empresa.** O registro das discussões vive
  no projeto "Leitor de Oscilografia" no Claude. Alguns daqueles documentos
  **não podem** ser copiados para cá — em particular o de modelagem de
  linhas, que traz nomes de subestação e parâmetros reais do estudo de curto.

## As maquetes

Antes de implementar função nova, dez maquetes funcionais com dados fictícios
(regra 6 do `CLAUDE.md`). As publicadas até aqui, para consulta:

| Assunto | Link |
|---|---|
| Plano de impedância (mho) | `claude.ai/artifact/NQMGnoy2aSQwjc8ZJieHTX` |
| Plano complexo | `claude.ai/artifact/4xrQ2A5EKjmDZjtVHdCsHM` |
| Espectro | `claude.ai/artifact/4oqyPNNB7GjiSf4EjKu661` |
| Plano alfa (87L) | `claude.ai/artifact/5DdPuQwpWkLvDSx9Xa6ATV` |
| Multi-oscilografia | `claude.ai/artifact/56GuKo62gdQFWnSjDKo9ZF` |
| Tipo de falta | `claude.ai/artifact/VjBrrfVwB6D3tMSinTFjv3` |
| Ajustes manuais do plano | `claude.ai/artifact/RDW2oMHeh8GcHojowGnNiv` |

Os três primeiros são justamente os da próxima etapa: **complexo, espectro e
alfa já estão decididos em maquete** — falta só trazer para o programa.
