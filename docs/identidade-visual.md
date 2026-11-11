# Identidade visual do OscLab — decidida em 10/11/2026

A identidade escolhida pelo Alexandre na rodada de maquetes (ramo
`maquete/identidade-visual`, pasta `../osclab-maquetes`) é a **f10 · Mistura
04 + 02**. Ela foi feita na maquete por CSS e JS que MOVEM elementos; aqui ela
é implementada de verdade, nos templates, no `osclab.css` e no `onda.js`.

Referência viva (não copiar a técnica, só o resultado):
- `../osclab-maquetes/src/osclab/web/static/css/identidades/final/10.css`
- `../osclab-maquetes/src/osclab/web/static/js/identidades/final/10.js`
- fotos: `../osclab-maquetes/maquetes/revisao/f10-*.png`
- servidor da maquete: http://localhost:8771/?identidade=f10 (se estiver no ar)

## O que ele pediu, em ordem de importância

1. **Não parecer feito por IA.** Sem gradiente, glow, roxo, Inter, cartão
   arredondado com sombra. Portal de produto de engenharia sério.
2. **Barra superior profissional e PRESA ao rolar** (sticky): uma faixa só, em
   marinho profundo (#0c1a2e…#12233d); logotipo + «OscLab»; menu em TEXTO
   (Início, Arquivos, Base de dados, e Oscilografia quando se está nela), sem
   caixas nem divisórias; item atual em peso 600 com filete branco de 2 px;
   à direita, controles quietos sem moldura (acervo, tema, versão). Nada de
   laranja/âmbar/vermelhão na barra.
3. **Logotipo «16 · Amostras»** (ver `docs/decisoes-de-estetica.md`). O nome
   ao lado é **«OscLab»** (decidido em 10/11/2026: sem serifa, O e L
   maiúsculos). A Trinca (L4) fica guardada, desligada, a uma troca de
   distância. Na aba do navegador: a **aplicação monocromática** do 16
   (`favicon-mono.svg` da maquete: escuro na aba clara, claro na escura).
4. **Papel milimetrado** é a textura da casa (página do início, arquivos e
   base). **Na oscilografia a página é LISA** e o milimetrado mora SÓ dentro
   da moldura de desenho de cada gráfico (grade sobre grade ficou ruim).
5. **O desenho 3D da subestação é um DETALHE interativo**, não a atração:
   pequeno, apagado, sem cotas; no hover de um serviço o equipamento certo
   acende em **azul-aço** (Linhas → LT-1, Ondas viajantes → cabo da LT-2,
   Oscilografia → raio-x da casa com os IEDs, Trafo → TR-1) e aparece a linha
   de chamada até o cartão.
6. **Cores sóbrias**: marinho profundo + papel + azul-aço como destaque único.
   Fases continuam com os tokens validados (`--fase-a/b/c/n`).
7. **Tema**: o CLARO da f10 passa a ser o PADRÃO (decidido em 10/11/2026,
   muda a regra antiga «tema escuro é o padrão»). O escuro continua no botão
   «tema», numa versão coerente (marinho profundo), validada pelo
   `tools/paleta.py` como toda cor.
   **Escuro escolhido em 11/11/2026: a paleta 08 «Ardósia clara»** (cinza-
   azulado médio, barra grafite), com o desenho da subestação no realce 20
   do tratamento «ajustável» — rodada de dez paletas no ramo `maquete/escuro`
   (`maquetes/ESCURO.md`). O claro ficou como estava.

## Página a página

- **Início (`menu.html`)**: layout da 04 — título à esquerda direto no papel,
  frase, dois botões (Enviar arquivos cheio em marinho, Base de dados em
  contorno); à direita o desenho 3D (`static/se3d/vista-02-traco.svg`)
  pequeno e apagado; a linha de chão; «Escolha o que você vai analisar.»; os
  quatro cartões com ícone em caixa, ligados ao desenho por linha de chamada
  só no hover (aceso AZUL). A casa de comando (grupos `oscilografia` e
  `base`) usa a MESMA tinta dos outros equipamentos, não a «de fundo»
  (`--se-tinta-longe`), senão parece apagada (pedido de 10/11). Depois a linha da base de dados, a seção «Do
  arquivo do relé à medida, em três passos» (branca, número em círculo fino,
  **retas ligando os círculos 1 — 2 — 3**) e o rodapé marinho de quatro
  colunas.
- **Arquivos e Base de dados**: faixa de título no papel (migalha, título,
  frase) atravessada pela linha de chão, e à direita **só a casa de comando**
  em sólido, raio-x, mais escura, sem faces branco-puras (Arquivos acende os
  IEDs, Base acende o armário do servidor, em azul). Blocos com cabeçalho.
- **Oscilografia (`abas.html` + `onda.html`)**: abas e «+ nova aba» (uma aba
  de verdade, sem caixa tracejada) alinhadas à margem dos blocos; página lisa;
  cabeçalho do registro; «+ adicionar oscilografia» e **«+ adicionar
  gráfico»** lado a lado, mesmo tamanho, mesmo «+» em texto; o menu de tipos
  de gráfico com **ícone por tipo**; **«localizar falta» sai da barra** e o
  acesso à tela de localização fica no cabeçalho do painel «localizador de
  faltas»; **gráfico analógico esticável na vertical** (alça na borda de
  baixo; ao soltar, redesenha na altura nova; duplo clique volta ao padrão);
  «lógica» alinhado aos outros botões.
