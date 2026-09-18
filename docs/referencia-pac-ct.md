# Referência de arquitetura — PAC CT

Análise do **PAC CT v1.12.0** (repositório público `GuilhermeMarini/pac-ct`),
indicado por Alexandre como modelo de formato para o OscLab. Baseada na leitura
do código real: `app.py`, `pac-ct.cmd`, `pac-ct.sh`, `README.md`,
`src/pacct/update.py`, `src/pacct/web/mount.py`, `src/pacct/web/update_check.py`,
`requirements.txt`, `VERSION`, `launcher.cfg`.

## 1. O que o usuário vê

- `pac-ct.cmd` sem argumentos abre um menu de sete opções no terminal; com
  argumentos, repassa tudo para `app.py --web`.
- Ao abrir, o `.cmd` chama `app.py --verificar`; **código de saída 10** significa
  "há versão nova" e o menu pinta `5) Atualizar <-- ha versao nova`. O script não
  interpreta texto.
- A opção 1 sobe um `ThreadingHTTPServer` na porta 8765 — a interface é web.
- Três temas, escolhidos por cookie de um ano.

## 2. Os quatro mecanismos que interessam

### 2.1 Bootstrap de dependências

`app.py` cria `.venv/` na própria pasta, se re-executa dentro dele e **só chama o
pip quando um `import` falha** — nunca para conferir versão. Motivo declarado:
subestação sem internet; um check de versão a cada boot transformaria "sem rede"
em "não abre". `--offline` instala de `vendor/` com `--no-index`, falhando rápido
e nomeando o wheel que falta.

Detalhes não óbvios, já incorporados ao OscLab:

- `is_inside_target_venv()` compara `sys.prefix`, não executáveis — o
  `.venv/bin/python` é link simbólico para o interpretador base e a comparação
  ingênua dá falso positivo, levando o programa a tentar instalar no Python do
  sistema, onde o PEP 668 recusa.
- No Windows usa `subprocess.call` em vez de `os.execv`, porque `os.execv` não faz
  quoting e o caminho contém espaço.
- `parse_requirements` trata referências PEP 508 (`nome @ git+...`).

### 2.2 Layout de instalação versionado

```
PAC-CT/
├── pac-ct.cmd / pac-ct.sh      launcher, nunca nomeia versão
├── versions/1.11.0/ 1.12.0/    uma pasta por versão, cada uma com seu .venv
├── current -> versions/1.12.0  junction no Windows
└── userdata/                   config.ini, cache/, rdbs/ — atualização nunca toca
```

O launcher exporta `PACCT_ROOT` (versão em execução) e `PACCT_DATA_DIR` (dados do
usuário); `paths.py` resolve tudo a partir dessas duas variáveis. Atualizar é
despejar a versão nova ao lado e repontar `current`; reverter é o mesmo
repontamento ao contrário.

Razão técnica real: no Windows um processo não substitui de forma confiável os
módulos de extensão que já carregou. Vale ainda mais para o OscLab, que carrega
numpy.

**O OscLab já nasce com essa separação**: `OSCLAB_ROOT` e `OSCLAB_DATA_DIR` em
`paths.py`, hoje apontando para a mesma pasta.

### 2.3 Atualização automática (não é Git)

Não usa `git pull`. Usa **GitHub Releases lidas anonimamente**:

- Consulta `https://github.com/<repo>/releases/latest/download/manifest.json` — o
  *redirect* de download, **não** a REST API, porque a API dá 60 requisições/hora
  por IP de origem e uma empresa inteira atrás de um NAT compartilha esse
  orçamento.
- `latest/` só resolve para release não-prerelease, então instantâneos de
  desenvolvimento nunca são oferecidos.
- O `manifest.json` traz o sha256 de cada pacote e a versão mínima de Python; o
  sha256 é **conferido antes de descompactar qualquer entrada**.
- Nenhum token embarcado — o repositório é público justamente para isso.
- A home pinta primeiro e **depois** pede a verificação por JavaScript; cache em
  processo de 6 h para sucesso e 15 min para falha, com lock para que dez abas
  virem uma requisição.
- Release cortada por tag, conferindo a tag contra o arquivo `VERSION`.

### 2.4 Um servidor, várias ferramentas

`mount.py` sobe **um** servidor e roteia por prefixo. Cada ferramenta escreve
rotas absolutas como se fosse dona da raiz; o dispatcher tira o prefixo e troca
`self.__class__`, e um shim injetado no `<head>` reescreve `fetch`.

Consequência boa: uma porta só no firewall, várias abas simultâneas.
**Ressalva:** a troca de `self.__class__` e o shim de `fetch` são contorno de
retrofit, não design. O OscLab usa Flask desde o início justamente para ter
roteamento de verdade sem esse contorno.

## 3. Outros padrões adotados no OscLab

- **Porta de entrada única para arquivos.** Só uma tela aceita upload; as demais
  escolhem do acervo por sha256. O que uma ferramenta gera volta para o acervo.
  Na PAC CT isso evitou mover 140 MB pela rede da subestação entre duas abas do
  mesmo servidor.
- **Cache endereçado por conteúdo**, compartilhado entre sessões e reinícios.
- **`config.ini` fora do git, semeado de `config.ini.example` no primeiro boot.**
- **Mensagens de erro que distinguem causas** (cópia incompleta × dependência
  ausente) em vez de um traceback.

## 4. O que NÃO foi copiado

- **Peso das dependências.** O `vendor/` da PAC CT tem ~2 MB (sete wheels
  puro-Python). O OscLab precisa de numpy, o que leva o pacote offline para
  dezenas de MB, específico por plataforma e versão de Python. A conta do pacote
  offline muda de natureza — decisão ainda em aberto.
- **Servidor só com a biblioteca padrão.** Funciona para tabela e formulário; a
  interface do OscLab tem forma de onda com zoom e cursores.
- **Lógica de domínio dentro de `web/`.** A PAC CT mantém `core/` e `parsers/`
  separados, mas cada ferramenta guarda seu `model.py` dentro de `web/`. No
  OscLab isso seria ruim: os algoritmos precisam rodar em lote e em teste.
