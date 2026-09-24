# CLAUDE.md

Este arquivo orienta o Claude Code (claude.ai/code) ao trabalhar neste repositório.

## Visão geral

App web local (não publicado na internet) que mostra cotações de ações da B3 em
tempo real (Yahoo Finance), com login obrigatório, administração de usuários e
uma carteira de ações por usuário. Serve tanto o back-end quanto o front-end a
partir de um único processo Flask.

Este projeto evoluiu de um painel estático (HTML/CSS/JS sem servidor, com
dados fixos de 2025) para um app com servidor, banco de dados e autenticação.
Os arquivos da versão antiga (sem login) ficam arquivados em
`versao-2025-sem-login/` e não são usados pelo app atual.

## Como rodar

```
pip install -r requirements.txt
python app.py
```

Ou, no Windows, dois cliques em `Abrir app.bat`. O app abre em
`http://localhost:5000` e tenta abrir o navegador padrão sozinho.

Não existe modo de "hot reload"/debug ligado (`debug=False` em `app.run`), de
propósito: o Flask debug mode expõe um console interativo que permite
executar código arbitrário a partir do navegador em caso de erro — inaceitável
mesmo rodando só localmente. Para desenvolver com reload automático, rode
manualmente com `flask --app app run --debug` sabendo desse risco, e nunca
deixe assim no que for entregue ao usuário final.

## Arquitetura

- **`app.py`** — único módulo do back-end (Flask). Contém: inicialização do
  banco SQLite, autenticação por sessão (cookie assinado), decorators de
  autorização, todas as rotas de página e de API, a camada de busca/cache do
  Yahoo Finance e o cálculo dos indicadores.
- **`templates/`** — duas páginas Jinja2: `login.html` (tela de entrada) e
  `index.html` (shell do app autenticado: menu lateral + 4 seções que o
  JavaScript alterna via `hidden`, sem recarregar a página).
- **`static/app.js`** — toda a lógica do app autenticado (SPA simples, sem
  framework): navegação entre páginas, chamadas a `/api/...`, renderização de
  cards/gráfico/tabelas, formulários de carteira/conta/administração.
- **`static/login.js`** — só a tela de login.
- **`static/style.css`** — todo o CSS do projeto (variáveis de cor no `:root`,
  suporta tema claro/escuro via `prefers-color-scheme`). Reaproveitado da
  versão anterior e estendido com menu lateral, formulários e tabela de
  administração.
- **`static/vendor/chart.umd.min.js`** — Chart.js 4.5.1, cópia local (o app
  não depende de CDN).
- **`dados/`** — criado em tempo de execução, **não é código**:
  - `banco.db`: banco SQLite (usuários, senhas com hash, carteiras).
  - `chave_secreta.txt`: chave usada para assinar o cookie de sessão, gerada
    uma vez com `secrets.token_hex(32)`. Se for apagada, todas as sessões
    ativas são invalidadas (força novo login), mas nenhum dado é perdido.
- **`.env`** (não versionado) — usuário/senha/nome/e-mail do primeiro
  administrador, lidos só quando a tabela `usuarios` está vazia, e
  `ANTHROPIC_API_KEY` (lida sempre, a cada request à IA). Ver `.env.exemplo`
  para o formato.
- **`instrucoes_analise_ia.txt`** — texto de sistema (system prompt) enviado
  à IA na "Análise do Dia". Fica fora de `app.py` de propósito, para poder
  ser editado sem tocar no código; é lido do disco a cada chamada (não é
  cacheado em memória), então uma edição vale imediatamente, sem reiniciar
  o app.

Não há build step, bundler nem framework de front-end: tudo é HTML/CSS/JS
servido diretamente pelo Flask (`static/` e `templates/`).

## Banco de dados (SQLite, `dados/banco.db`)

```sql
usuarios (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome_completo TEXT NOT NULL,
  usuario TEXT NOT NULL UNIQUE,
  email TEXT NOT NULL,
  senha_hash TEXT NOT NULL,       -- werkzeug generate_password_hash (pbkdf2:sha256)
  tipo TEXT NOT NULL CHECK(tipo IN ('admin', 'comum')),
  senha_temporaria INTEGER NOT NULL DEFAULT 0,  -- 1 = precisa trocar a senha antes de usar o resto do app
  criado_em TEXT NOT NULL
)

carteira (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,           -- código sem sufixo, ex.: "PETR4"
  UNIQUE(usuario_id, ticker)
)
```

Sem migrations formais: o schema é criado com `CREATE TABLE IF NOT EXISTS` em
`iniciar_banco()`. Qualquer mudança de schema precisa de um plano de migração
manual (o banco de um usuário real não pode ser recriado do zero).

## Autenticação e autorização

- Sessão via cookie assinado do Flask (`session`), com `permanent_session_lifetime`
  de 7 dias — sobrevive a F5 e a fechar/abrir o navegador dentro desse prazo.
  A sessão guarda **só** `usuario_id`; tipo de conta e status de senha
  temporária são sempre relidos do banco a cada request (nunca confiar em
  dado de sessão para autorização — evita ficar autorizando algo que já não é
  mais verdade, por exemplo depois de um "rebaixar" feito por outra aba/pessoa).
- `login_necessario`: exige `usuario_id` na sessão. Em rota de página, redireciona
  para `/login`; em rota de API (`/api/...`), devolve 401 JSON.
- `admin_necessario`: relê o usuário no banco e confere `tipo == 'admin'`.
  Sempre usado depois de `login_necessario` (a ordem dos decorators importa).
- `before_request` (`exigir_troca_de_senha_temporaria`): bloqueia **qualquer**
  rota de API com `senha_temporaria = 1`, exceto login/logout/me/trocar-senha.
  Devolve `{"erro": ..., "precisaTrocarSenha": true}` com status 403; o
  front-end usa esse campo para mostrar a tela de "crie sua senha" e travar a
  navegação.
- Senhas: nunca armazenadas nem logadas em texto puro. Hash via
  `werkzeug.security.generate_password_hash`/`check_password_hash`. Senha
  temporária é gerada com `secrets.choice` sobre um alfabeto sem caracteres
  ambíguos (`0/O`, `1/l/I`) e é devolvida **uma única vez**, na resposta da
  chamada que a gerou — não fica salva em lugar nenhum além do hash.

## Yahoo Finance: busca e cache

- `yfinance` busca por `"{ticker}.SA"` (sufixo da B3).
- `obter_historico_com_cache()` guarda resultado (sucesso ou erro) em um dict
  em memória (`_cache`), por `(ticker, período)`, por 15 minutos
  (`DURACAO_CACHE`). Isso vale tanto para evitar chamadas repetidas de um
  mesmo usuário clicando toda hora quanto para não martelar o Yahoo Finance
  quando várias pessoas usam o app ao mesmo tempo.
- Qualquer falha (rede, ticker inexistente, resposta vazia) vira uma mensagem
  amigável em português — nunca uma stack trace chega ao usuário. Ver
  `ticker_existe()` (usada ao adicionar à carteira) e o campo `"erro"` dentro
  de `obter_historico_com_cache()`.
- Períodos aceitos (`PERIODOS_VALIDOS`): `1mo, 3mo, 6mo, ytd, 1y, max` — os
  mesmos valores que `yfinance`/Yahoo Finance entendem, usados diretamente
  como parâmetro de período. Qualquer período novo na UI precisa ser
  adicionado nessa constante **e** em `PERIODOS` no `static/app.js`.

## Análise do Dia (IA — Anthropic)

- Botão flutuante na página "Ações" (`static/style.css` → `.botao-flutuante`,
  `templates/index.html` → `#botao-analise-dia`) que abre uma janela
  (`#janela-analise`) e chama `GET /api/analise-dia?periodo=`.
- `montar_bloco_dados()` monta o texto numérico da carteira (preço, variação,
  mín/máx, variação de 5 pregões, tendência de médias móveis 20×50, e
  volatilidade — reaproveitando `calcular_indicadores()`). A tendência usa
  sempre 1 ano de histórico (`calcular_tendencia()`), independente do
  período escolhido na tela, para não depender de janelas curtas demais.
  **Só esse texto vai para a IA — nunca os gráficos.**
- `obter_instrucoes_ia()` lê `instrucoes_analise_ia.txt` do disco a cada
  chamada (arquivo pequeno, sem custo relevante) e vai como `system` na
  chamada à API da Anthropic.
- Modelo: `MODELO_IA = "claude-haiku-4-5"` (o mais barato da Anthropic no
  momento). Chave lida de `ANTHROPIC_API_KEY` a cada request (nunca
  hardcoded, nunca logada).
- **Streaming sem SSE de verdade**: a rota devolve `Response(gerar(), ...)`
  com `mimetype="text/plain"`. O gerador primeiro manda uma linha JSON de
  metadados (`{"tipo": "meta", ...}` + `\n`) e depois os pedaços de texto de
  `stream.text_stream` (SDK da Anthropic), conforme chegam. O front-end
  (`static/app.js` → `iniciarAnaliseDia()`) lê a resposta com
  `response.body.getReader()`, separa a primeira linha como metadados e
  escreve o resto na tela conforme chega — sem precisar de `EventSource`
  nem de um protocolo SSE formal.
- **Erros nunca viram texto técnico na tela.** Se a chave estiver ausente ou
  a carteira vazia, a rota devolve JSON comum (`{"erro": ...}`, status
  4xx/503) *antes* de começar a stream — o front-end detecta pelo
  `Content-Type` (`application/json` vs. `text/plain`) e trata cada caso.
  Se o erro acontecer **depois** de a stream já ter começado (ex.: chave
  ficou inválida no meio do caminho), o gerador manda o texto já escrito até
  ali seguido do marcador `\n[[ERRO]]` + mensagem amigável
  (`erro_amigavel_ia()`); o front-end procura por esse marcador nos pedaços
  recebidos (cuidando de não cortar o marcador ao meio entre dois pedaços).
- **Cache de 15 min** (`_cache_analise`, `DURACAO_CACHE_ANALISE`), chave
  `(usuario_id, período, tuple(tickers))` — muda sozinho se a carteira
  mudar. Numa reutilização, a rota nem chama a IA: devolve JSON
  (`{"cache": true, "texto": ..., "geradoEm": ...}`) com o texto pronto, e o
  front-end anima a digitação localmente (`digitarTextoLocal()`) só por
  efeito visual — nenhuma chamada nova é feita à Anthropic.
- Testado localmente via `waitress-serve` + `curl`/`Invoke-RestMethod`
  (chave ausente, chave inválida, carteira vazia, cache, e uma chamada real)
  — ver histórico de testes no momento em que essa funcionalidade foi
  adicionada.

## Rotas de API (todas sob `/api/`, JSON)

| Rota | Método | Autenticação | Descrição |
|---|---|---|---|
| `/api/login` | POST | — | `{usuario, senha}` → cria sessão |
| `/api/logout` | POST | — | limpa a sessão |
| `/api/me` | GET | login | dados do usuário logado |
| `/api/conta/senha` | POST | login | troca a própria senha (`senhaAtual`, `senhaNova`) |
| `/api/carteira` | GET/POST | login | lista / adiciona ticker |
| `/api/carteira/<ticker>` | DELETE | login | remove ticker |
| `/api/acoes` | GET | login | `?periodo=` → cards/gráfico/indicadores da carteira |
| `/api/acoes/csv` | GET | login | mesma coisa, como CSV para baixar |
| `/api/analise-dia` | GET | login | `?periodo=` → "Análise do Dia" pela IA (streaming em texto puro, ou JSON se veio do cache/erro) |
| `/api/admin/usuarios` | GET/POST | admin | lista / cria usuário |
| `/api/admin/usuarios/<id>/redefinir-senha` | POST | admin | gera nova senha temporária |
| `/api/admin/usuarios/<id>/promover` | POST | admin | vira admin |
| `/api/admin/usuarios/<id>/rebaixar` | POST | admin | vira comum (bloqueia se for o último admin) |
| `/api/admin/usuarios/<id>` | DELETE | admin | exclui (bloqueia autoexclusão e último admin) |

Toda resposta de erro tem o formato `{"erro": "mensagem em português"}`. O
front-end (`app.js`, função `api()`) trata isso de forma central: 401 manda
para `/login`, 403 com `precisaTrocarSenha` ativa o bloqueio de troca de
senha, qualquer outro erro é mostrado na tela.

## Convenções do projeto

- Identificadores (nomes de função, variável, rota) em português, seguindo o
  código herdado da versão anterior. Mensagens de erro/aviso sempre em
  português do Brasil, sempre amigáveis — nunca expor stack trace ou detalhe
  técnico ao usuário final.
- Sem framework de front-end: JS puro, manipulação direta do DOM, os mesmos
  padrões visuais do painel original (`.card`, `.painel`, `.aviso`,
  `.esqueleto`, `.rolagem-tabela`, etc. — ver `static/style.css`).
- `app.py` é intencionalmente um único arquivo. Se crescer muito, considere
  separar em `auth.py`, `mercado.py`, `admin.py`, mas mantenha `app.py` como
  ponto de entrada único.

## Testando

Não há suíte de testes automatizados. Para verificar mudanças no back-end,
suba o servidor e use chamadas HTTP diretas (o que valida login, sessão,
proteções de administração e cache sem depender de um navegador):

```powershell
python app.py   # roda em segundo plano com Start-Process, ou em outra janela
Invoke-RestMethod -Uri http://localhost:5000/api/login -Method Post `
  -ContentType "application/json" -Body '{"usuario":"admin","senha":"..."}' `
  -SessionVariable sessao
Invoke-RestMethod -Uri http://localhost:5000/api/me -WebSession $sessao
```

Para testar de verdade a interface (cliques, formulários, gráfico), é preciso
abrir o navegador manualmente — não há ferramenta de automação de navegador
configurada neste ambiente.

## Segurança — coisas para não regredir

- Nunca commitar `.env`, `dados/banco.db` ou `dados/chave_secreta.txt` (estão
  no `.gitignore`).
- Nunca guardar senha em texto puro em lugar nenhum (banco, log, sessão).
- Nunca confiar em `tipo`/`senha_temporaria` vindos da sessão para decisões de
  autorização — sempre reler do banco (ver `admin_necessario` e
  `exigir_troca_de_senha_temporaria`).
- Manter `debug=False` em `app.run` neste arquivo.
- Ao publicar este app na internet no futuro (fora do escopo atual, que é só
  uso local), revisar: HTTPS, `SESSION_COOKIE_SECURE=True`, rate limiting no
  login, e trocar o servidor de desenvolvimento do Flask por um servidor WSGI
  de produção (ex.: waitress, que funciona bem no Windows).
