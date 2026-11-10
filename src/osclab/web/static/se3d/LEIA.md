# Subestação 3D: a vista 02 para o site

> **De onde vêm estes arquivos.** Os dois SVG são CÓPIAS do que o gerador
> produz no ramo das maquetes (`maquete/identidade-visual`, pasta
> `../osclab-maquetes`): `node maquetes/se3d/exportar-site.mjs` escreve em
> `../osclab-maquetes/src/osclab/web/static/se3d/`, e de lá eles são copiados
> para cá à mão. O gerador (cena, câmera, exportação) NÃO vem para o `main`:
> é Node, e o programa não depende de Node. Para mudar o desenho, regenere
> lá e copie os dois `.svg` de novo — nunca edite aqui. Os caminhos
> `maquetes/se3d/...` citados abaixo são os daquele ramo.
>
> Quem usa: `static/js/vitrine.js` (o início, em traço; arquivos e base, só
> a casa de comando do sólido). As cores vêm das variáveis `--se-*`
> definidas no `static/css/portal.css`, nos dois temas.

Dois desenhos da mesma câmera (aérea média, do lado das linhas: azimute −38°,
elevação 26°), em faixa 3 : 1 (`viewBox="0 0 1800 600"`):

| arquivo | modo | tamanho |
|---|---|---|
| `vista-02-traco.svg` | traço: arestas em tinta, faces na cor do papel | ~381 kB |
| `vista-02-solido.svg` | sólido: faces em 3 tons, arestas finas | ~412 kB |

Não edite à mão: eles saem de `node maquetes/se3d/exportar-site.mjs`. Para
conferir: `node maquetes/se3d/fotografar-site.mjs` (fotos em
`maquetes/se3d/fotos/site-*.png`).

**Sem fundo** (o papel, o milimetrado e a cor de fundo são da página), sem
`width`/`height` e com `preserveAspectRatio="xMidYMid meet"`: dê largura ao
contêiner e `svg{display:block;width:100%;height:auto}`.

## Como embutir

O script da identidade busca o texto e o põe num elemento que ELE criou.
`innerHTML` só é permitido nesse elemento:

```js
const caixa = document.createElement("div");
caixa.className = "se3d-caixa";
destino.append(caixa);
fetch("/static/se3d/vista-02-traco.svg")
  .then((r) => r.text())
  .then((svg) => { caixa.innerHTML = svg; });
```

Embutido assim (e não por `<img>`), o CSS da página alcança o desenho: as
variáveis, o aceso e o hover funcionam. Por `<img>` ele aparece só com as
cores padrão e sem interação. O `<style>` interno é todo escopado em
`svg.se3d` e nas classes `se-aceso-*`, então não vaza para a página.

## Variáveis CSS

Defina num ancestral. Todas têm valor padrão.

| variável | o que pinta | padrão |
|---|---|---|
| `--se-tinta` | arestas, cabos, treliças, rótulos | `#1b2a44` |
| `--se-tinta-longe` | o mesmo, no que está ao fundo do pátio (mais de 18 m além do centro) | `#6f7f96` |
| `--se-papel` | traço: toda face (é o que tapa o que está atrás). Sólido: só entra na mistura do esmaecer | `#fbfdff` |
| `--se-face-1` | sólido: face de frente para a luz | `#e6ebf1` |
| `--se-face-2` | sólido: face de lado | `#b9c3cf` |
| `--se-face-3` | sólido: face na sombra | `#8593a5` |
| `--se-tela` | telas dos IEDs no raio-x | `= --se-tinta` |
| `--se-destaque` | o grupo aceso, as frentes de onda, as ondas na tela do RDP | `#c2410c` |

No traço, `--se-papel` deve ser a cor do fundo da página. Senão, cada peça
aparece como um recorte opaco de outra cor sobre o milimetrado.

```css
.minha-faixa {                       /* tinta clara sobre marinho */
  --se-tinta: #e4ecf6; --se-tinta-longe: #7f93b3; --se-papel: #0f1d33;
  --se-face-1: #4a6189; --se-face-2: #2e4266; --se-face-3: #1d2d4b;
  --se-destaque: #ffb347;
}
```

## Grupos, camadas e classes

| seletor | o que é |
|---|---|
| `[data-grupo="linhas"]` | LT-1: torres, cabos e vão de entrada |
| `[data-grupo="viajantes"]` | LT-2 (ondas viajantes) |
| `[data-grupo="trafo"]` | TR-1, disjuntores, cubículos e alimentadores |
| `[data-grupo="oscilografia"]` | casa de comando: casca e interior |
| `[data-grupo="base"]` | armário do servidor, dentro da casa |
| `[data-grupo="fundo"]` | pátio, barramento, pórtico, cerca e canaletas |
| `[data-camada="casa-casca"]` | paredes e telhado da casa |
| `[data-camada="raio-x"]` | interior da casa, **escondido** por padrão |
| `[data-camada="frentes"]` | marcas de frente de onda na LT-2, **escondidas** por padrão |

Um mesmo grupo aparece em vários `<g>`, intercalados com os outros grupos,
porque a ordem de pintura manda. Por isso, selecione sempre por atributo
(`[data-grupo=…]`) e nunca por posição.

Classes: `.f` face, `.f1 .f2 .f3` tom (só no sólido), `.a` aresta, `.l` cabo
ou treliça (a espessura vem no atributo `stroke-width`), `.longe` ao fundo,
`.fr` frente de onda, `.t` rótulo, e `.ied`, `.tela`, `.onda` para as peças do
raio-x.

## Aceso, hover e raio-x

O aceso já vem embutido. Basta pôr a classe `se-aceso-<grupo>` no `<svg>` ou
em qualquer ancestral: `se-aceso-linhas`, `-viajantes`, `-trafo`,
`-oscilografia` ou `-base`. O grupo passa para `--se-destaque` e o resto
esmaece em direção a `--se-papel` (por mistura de cor, não por transparência,
para não deixar ver o que está atrás). `oscilografia` e `base` abrem o raio-x:
a casca fica tracejada e o interior aparece. `viajantes` mostra as frentes
de onda.

Hover pelo desenho, com o grupo sob o mouse:

```js
const svg = caixa.querySelector("svg");
let atual = null;
const acender = (g) => {
  if (g === atual) return;                       // não recalcula à toa
  if (atual) caixa.classList.remove("se-aceso-" + atual);
  if (g) caixa.classList.add("se-aceso-" + g);
  atual = g;
};
svg.addEventListener("mouseover", (e) => {
  const g = e.target.closest("[data-grupo]")?.dataset.grupo;
  acender(g && g !== "fundo" ? g : null);
});
svg.addEventListener("mouseleave", () => acender(null));
// ou a partir de um item de lista: li.onmouseenter = () => acender("oscilografia")
```

O raio-x por CSS puro, sem o aceso embutido (por exemplo, para abrir a casa
ao passar o mouse num cartão):

```css
.cartao-oscilografia:hover ~ .se3d-caixa [data-camada="raio-x"] { display: inline; }
.cartao-oscilografia:hover ~ .se3d-caixa [data-camada="casa-casca"] .f { fill-opacity: .06; }
.cartao-oscilografia:hover ~ .se3d-caixa [data-camada="casa-casca"] .a { stroke-dasharray: 5 3.5; }
```

Para trocar o estilo do aceso, sobrescreva com seletor mais específico.
Exemplo: aceso sem esmaecer o resto:

```css
.minha-faixa .se3d-caixa[class*="se-aceso-"] svg.se3d { --_tinta: var(--se-tinta); --_longe: var(--se-tinta-longe); }
```

`--_tinta`, `--_longe`, `--_papel` e `--_dest` são internas: o aceso troca
essas, e as `--se-*` ficam sendo só da identidade.

## Ligar o desenho ao layout: âncoras, chão, horizonte e escala

Cada SVG traz, no fim, um `<g id="se-ancoras">` invisível. O comentário do topo
traz os mesmos números em JSON, na linha `SE3D-DADOS {…}`. As coordenadas
estão no viewBox (1800 × 600):

| elemento | o que marca | x, y |
|---|---|---|
| `circle[data-ancora="linhas"]` | topo da torre da LT-1 | 305.9, 94.3 |
| `circle[data-ancora="viajantes"]` | meio do vão da LT-2, da torre ao pórtico | 655.3, 292.3 |
| `circle[data-ancora="trafo"]` | topo das buchas do TR-1 | 1166.6, 119.3 |
| `circle[data-ancora="oscilografia"]` | porta da casa de comando | 1129.7, 98.3 |
| `circle[data-ancora="base"]` | o rack do servidor (dentro da casa) | 1123.9, 64.0 |
| `line[data-ref="chao"]` | linha do chão: o canto do pátio mais perto da câmera | y = 438.3 (canto em x = 818.5) |
| `circle[data-ref="canto-frente"]` | esse canto, com `data-px-por-metro` | 818.5, 438.3 |
| `line[data-ref="horizonte"]` | horizonte | y = −1367.2 |
| `rect[data-ref="bbox"]` | a subestação: pátio cercado, mastros do pórtico e casa (sem as torres de fora) | 525.9, 14.0, 942.5 × 424.3 |
| `rect[data-ref="desenho"]` | tudo o que está desenhado (os cabos vão até a borda esquerda e a de baixo) | 0, 14.0, 1643.8 × 586 |

O **horizonte fica fora do quadro, bem acima** (y negativo): a câmera olha
26° para baixo. Ele serve para saber a direção das fugas, não para alinhar
título.

Para converter para pixel da página, use `svg.getScreenCTM()` ou uma regra de
três. Com o `meet`, a escala é `min(largura/1800, altura/600)`, e o desenho
fica centrado:

```js
const svg = caixa.querySelector("svg");
const p = svg.createSVGPoint();
const c = svg.querySelector('[data-ancora="trafo"]');
p.x = +c.getAttribute("cx"); p.y = +c.getAttribute("cy");
const naTela = p.matrixTransform(svg.getScreenCTM());   // px da janela
```

**Escala**: no canto da frente do pátio, **1 m = 12,8 px do viewBox**,
medido na direção que não encurta (paralela à tela). Ao longo das duas bordas
do pátio que saem desse canto, as fugas encurtam o metro para 9,0 e 11,2 px.
Mais para o fundo ele encolhe (perspectiva).

Para casar o milimetrado com o desenho, dimensione a malha em fração da
largura renderizada do SVG. Na largura `L` px, 1 m vale `12.8 × L / 1800` px.
Com `L = 1500`, 1 m ≈ 10,7 px, e um quadrado de 10 mm da malha = 1 m fica
quase exato com a malha de 10,7 px. Isso vale só para a frente: é perspectiva,
e o metro do fundo é menor.

## O que ficou simplificado

- Peça menor que ~16 px do viewBox vira **uma silhueta** (o contorno convexo
  dela). Na largura de site isso não se vê. Ampliado, um isolador perde as
  saias.
- No sólido, o material sumiu: são só três tons de face. Concreto, porcelana
  e aço têm a mesma cor, e quem separa é o tom da luz.
- Rótulos menores que 4 px saíram. Nesta vista isso é tudo.
- Os cabos que saem do quadro (LT-1, LT-2 e alimentadores) são cortados na
  borda, de propósito.
