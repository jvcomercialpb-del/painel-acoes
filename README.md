# Ações — painel com login e carteira pessoal

App que mostra a cotação de ações da B3 ao vivo (direto do Yahoo Finance),
onde cada pessoa entra com usuário e senha e tem a própria carteira de ações.

Publicado na internet via [Railway](https://railway.com), a partir deste
repositório: toda vez que uma nova versão é enviada para o GitHub, o site
publica sozinho. Também pode ser rodado só no computador local (veja abaixo).

Link público: https://painel-acoes-production-6d29.up.railway.app/

Publicar uma nova versão é simples: envie as mudanças para o branch `main`
deste repositório (`git push`) e o Railway publica sozinho em alguns minutos.

## O que o app faz

- **Login obrigatório.** Ninguém vê nada sem entrar com usuário e senha.
  Continua logado mesmo se você apertar F5 ou fechar e abrir o navegador de
  novo depois de um tempo.
- **Dois tipos de conta**: administrador (você) e usuário comum.
- **Administração** (só para você, o administrador): criar pessoas, redefinir
  senha de quem esqueceu, promover/rebaixar administrador, excluir usuário.
- **Cada pessoa tem a própria carteira** de ações (começa com PETR4, ITUB4 e
  VALE3) e pode adicionar ou remover ações digitando o código.
- **Cotações ao vivo**, com cards, gráfico comparativo (com botões de
  período: 1 mês, 3 meses, 6 meses, no ano, 1 ano e máximo), tabela de
  indicadores e um botão para baixar os dados em CSV (abre no Excel).
- **Análise do Dia (com Inteligência Artificial).** Na página "Ações", um
  botão fixo no canto inferior direito abre uma janela com um texto
  explicando, em português simples, como está a carteira no período
  selecionado — feito pela IA da Anthropic (Claude) a partir só dos números
  (nunca inventa notícias nem promete retorno). Veja a seção
  [Análise do Dia](#análise-do-dia-com-ia) mais abaixo.

## Antes de começar: usuário e senha do primeiro administrador

Existe um arquivo chamado **`.env`** nesta pasta com o seu login de
administrador. Ele já foi criado com uma senha gerada automaticamente:

```
Usuário: admin
Senha:   H89Qub5WDRDQ
```

**Recomendo trocar essa senha assim que entrar pela primeira vez**, na página
"Minha conta" (veja o passo a passo mais abaixo).

Se quiser escolher você mesmo o usuário e a senha do administrador *antes* da
primeira vez que rodar o app: abra o arquivo `.env` (botão direito → Abrir
com → Bloco de notas), troque os valores de `ADMIN_USUARIO` e `ADMIN_SENHA` e
salve. Isso só funciona **antes** de o app rodar pela primeira vez (ou seja,
antes de existir qualquer usuário cadastrado). Depois disso, para trocar a
sua própria senha, use a página "Minha conta" dentro do app.

> O arquivo `.env` é só seu — nunca envie ele para ninguém nem para a
> internet. É nele que fica escrita a senha do administrador.

## Como abrir o app

1. Na pasta `app-acoes-2025`, dê **dois cliques** em **`Abrir app.bat`**.
2. Uma janela preta abre — é o motor do app. **Deixe ela aberta** enquanto
   estiver usando.
3. Alguns segundos depois, o navegador abre sozinho em `http://localhost:5000`.
4. Para fechar o app, feche a janela preta.

## Como entrar pela primeira vez

1. Na tela de entrada, digite o **usuário** e a **senha** do arquivo `.env`
   (veja a seção acima).
2. Clique em **Entrar**.
3. Você já cai direto no painel — o administrador criado pelo `.env` **não**
   precisa trocar a senha na primeira vez (a senha que você escolheu no
   `.env` já é a senha real). Mesmo assim, é uma boa ideia ir em **Minha
   conta** e trocar para uma senha só sua, que só você conhece.

## Como criar um usuário para outra pessoa

1. Entre como administrador e clique em **Administração**, no menu lateral.
2. Em "Criar usuário", preencha nome completo, nome de usuário (o que a
   pessoa vai digitar para entrar) e e-mail. Clique em **Criar usuário**.
3. O app mostra na tela uma **senha temporária**, uma única vez. **Copie e
   guarde agora** — depois de sair dessa tela, ela não aparece de novo.
4. Passe o usuário e a senha temporária para a pessoa. Na primeira vez que
   ela entrar, o app vai pedir para ela criar uma senha nova, só dela.

## "Esqueci minha senha" — como resolver

Não existe cadastro nem recuperação por e-mail. Quem resolve é você, o
administrador:

1. Vá em **Administração**.
2. Encontre a pessoa na tabela e clique em **Redefinir senha**.
3. Uma nova senha temporária aparece na tela, uma única vez. Passe para a
   pessoa. Da próxima vez que ela entrar, vai ter que criar uma senha nova.

## Como usar a carteira de ações

1. Clique em **Minha carteira**, no menu lateral.
2. Para adicionar uma ação, digite o código (por exemplo `WEGE3` ou `BBAS3`)
   e clique em **Adicionar**. O app confere se a ação existe antes de
   adicionar.
3. Para remover, clique em **Remover** ao lado da ação.
4. O que estiver na carteira aparece na página **Ações**, com cards, gráfico
   e tabela. Use os botões acima do gráfico para trocar o período.

## Análise do Dia (com IA)

Na página **Ações**, o botão **"Análise do Dia"** (canto inferior direito,
sempre visível mesmo rolando a página) abre uma janela com um texto sobre a
sua carteira, escrito pela IA da Anthropic (o mesmo Claude que ajudou a
construir este app) e que vai "aparecendo" na tela como se estivesse sendo
digitado.

**Como funciona, por trás da tela:**
1. O app pega os preços que já busca do Yahoo Finance e calcula os números
   de cada ação da sua carteira, no período que estiver selecionado (preço
   atual, variação, mínima/máxima, tendência, volatilidade etc.) — os
   mesmos cálculos que já aparecem na tabela de indicadores.
2. Só esses números (nunca o gráfico, nunca uma imagem) são enviados para a
   IA, junto com as instruções de como escrever (arquivo
   `instrucoes_analise_ia.txt` — veja abaixo).
3. A IA escreve um texto curto e didático: uma visão geral, até 2 ações que
   podem merecer atenção para compra e até 2 que podem pedir cautela, sempre
   explicando com números e nunca com certeza ("pode", nunca "vai"). No
   final, sempre aparece o aviso de que não é recomendação de investimento.

**Ajustando o texto que a IA escreve.** As instruções completas estão no
arquivo `instrucoes_analise_ia.txt`, na pasta do app. Você pode abrir esse
arquivo (botão direito → Abrir com → Bloco de notas) e ajustar o tom, o
tamanho ou as regras, sem precisar mexer em mais nada — na próxima vez que
alguém clicar no botão, o app já usa o texto novo.

**Configurando a chave de acesso.** O botão só funciona depois de configurar
a chave de acesso à API da Anthropic — a variável `ANTHROPIC_API_KEY`. Sem
ela, o botão continua aparecendo, mas a janela mostra um aviso amigável
explicando que a IA ainda não foi configurada. Veja como configurar em
**"Configurando a chave da IA"**, mais abaixo.

**Por que às vezes a análise aparece na hora, sem "digitar".** Se você (ou
outra pessoa) clicar no botão de novo em menos de 15 minutos, com a carteira
e o período iguais aos da última vez, o app reaproveita a análise já feita
em vez de gastar com a IA de novo — por isso ela aparece completa quase na
hora, mas a data/hora mostrada (**"análise gerada às HH:MM"**) é sempre a da
primeira vez que foi gerada.

**Quanto custa.** Cada análise usa o Claude Haiku 4.5, o modelo mais barato
da Anthropic. Para uma carteira típica (poucas ações), cada análise custa
uma fração de centavo de dólar — bem abaixo de R$ 0,05. Mesmo testando
várias vezes ao dia, o gasto tende a ficar irrelevante na fatura.

## Configurando a chave da IA

A chave de acesso à API da Anthropic nunca fica escrita no código nem vai
para o GitHub — ela mora fora do código, do mesmo jeito que a senha do
administrador.

**No seu computador:** abra o arquivo `.env` desta pasta (botão direito →
Abrir com → Bloco de notas) e cole a chave na linha `ANTHROPIC_API_KEY=`,
sem espaços antes ou depois do sinal de igual. Salve o arquivo e reinicie o
app (feche a janela preta e abra `Abrir app.bat` de novo) para a chave nova
valer.

**No Railway (site publicado):** entre no [painel do Railway](https://railway.com),
abra este projeto, clique na aba **Variables** (Variáveis) do serviço do
app, clique em **New Variable**, coloque o nome `ANTHROPIC_API_KEY` e cole a
chave como valor. O Railway reinicia o app sozinho depois de salvar — não
precisa fazer `git push` nem mexer em código.

Se ainda não tem uma conta na Anthropic para gerar a chave, é só avisar que
eu te guio pelo terminal, passo a passo, pela criação da conta em
console.anthropic.com, pela compra de um crédito inicial pequeno e pela
geração da chave.

## Como testar que está tudo funcionando

Depois de abrir o app (veja "Como abrir o app" acima):

1. **Login**: tente entrar com uma senha errada — deve aparecer uma mensagem
   de erro, sem travar a tela. Entre com a senha certa — deve funcionar.
2. **Continuar logado**: aperte F5. Você continua na mesma tela, sem precisar
   entrar de novo.
3. **Sair**: clique em "Sair", no canto inferior esquerdo. Você volta para a
   tela de login.
4. **Administração**: crie um usuário de teste, copie a senha temporária
   mostrada. Clique em "Sair" e entre com esse novo usuário e a senha
   temporária.
5. **Troca obrigatória de senha**: como esse usuário novo, o app deve travar
   e pedir para você criar uma senha antes de mostrar qualquer outra coisa.
   Crie a senha nova.
6. **Minha conta**: depois de logado, vá em "Minha conta" e troque a senha de
   novo, dessa vez por vontade própria (não porque o app obrigou).
7. **Carteira**: em "Minha carteira", adicione uma ação (ex.: `WEGE3`) e
   depois remova. Tente adicionar um código que não existe (ex.: `XPTO99`) —
   deve aparecer uma mensagem amigável, não um erro técnico.
8. **Ações**: vá em "Ações" e confira se aparecem os cards, o gráfico e a
   tabela. Clique nos botões de período (1 mês, 3 meses, etc.) e veja o
   gráfico mudar. Clique em "Baixar CSV" e confira se o arquivo abre no
   Excel.
9. **Proteções de administração**: volte a entrar como administrador, exclua
   o usuário de teste que você criou no passo 4. Tente excluir a própria
   conta de administrador — o app deve recusar. Se só existir um
   administrador, tente rebaixá-lo a usuário comum — o app também deve
   recusar.
10. **Análise do Dia**: na página "Ações", clique no botão "Análise do Dia"
    (canto inferior direito). A janela deve abrir e o texto deve aparecer
    "sendo digitado" aos poucos, com o período e a hora da análise no topo.
    Clique de novo rapidamente (menos de 15 minutos) — a análise deve
    aparecer quase na hora, com a mesma hora de antes (reaproveitada).
    Troque o período (por exemplo para "1 ano") e clique de novo — dessa vez
    deve chamar a IA de novo (mais devagar, digitando ao vivo).

Se todos esses passos funcionarem, o app está redondo.

## Problemas comuns e como resolver

**A janela preta fecha sozinha ou mostra "Algo deu errado".**
Tire uma foto da mensagem de erro. Confira se a pasta `app-acoes-2025` não
foi movida nem renomeada, e se o arquivo `.env` ainda existe.

**O navegador abre, mas mostra "não é possível acessar este site".**
Espere mais alguns segundos e recarregue (F5) — o motor pode ainda estar
iniciando. Se persistir, confira se a janela preta ainda está aberta.

**Esqueci a senha do administrador e só existe um administrador.**
Apague o arquivo `dados\banco.db` (isso apaga **todos** os usuários e
carteiras, sem volta) e abra o app de novo: ele volta a criar o primeiro
administrador a partir do arquivo `.env`. Só faça isso se realmente não tiver
outro jeito.

**Uma ação aparece com uma mensagem de erro em vez do gráfico.**
Normalmente é falta de internet ou o Yahoo Finance fora do ar no momento.
Espere alguns minutos (o app tenta de novo sozinho) ou clique nos botões de
período para forçar uma nova tentativa.

**Os acentos aparecem estranhos na janela preta (ex.: "usuÃ¡rio").**
É só a exibição no terminal — não afeta os dados nem a página no navegador.
O atalho `Abrir app.bat` já ajusta isso; se ainda acontecer, feche e abra o
app de novo pelo atalho (não rodando `python app.py` direto).

**A janela "Análise do Dia" mostra um aviso em vez do texto.**
Leia a mensagem — ela já explica o que fazer. As mais comuns: a chave da IA
ainda não foi configurada (veja "Configurando a chave da IA"), o crédito da
conta da Anthropic acabou (adicione mais em console.anthropic.com), ou a
Anthropic está fora do ar por instantes (espere um pouco e tente de novo).

**Quero rodar sem o atalho, direto pelo terminal.**
Abra o PowerShell nesta pasta e rode:
```
pip install -r requirements.txt
python app.py
```

## O que tem em cada arquivo

| Arquivo/pasta | Para que serve |
|---|---|
| `Abrir app.bat` | Atalho para ligar o app (duplo clique) |
| `app.py` | O motor do app: login, banco de dados, administração, busca de cotações |
| `templates/` | As páginas HTML (login e o painel principal) |
| `static/` | Visual (CSS), comportamento no navegador (JS) e a biblioteca de gráficos |
| `.env` | Usuário/senha do primeiro administrador e a chave da IA (não compartilhe) |
| `.env.exemplo` | Modelo do `.env`, para copiar caso precise recriá-lo |
| `instrucoes_analise_ia.txt` | Instruções que a IA segue para escrever a "Análise do Dia" — pode ajustar à vontade |
| `dados/banco.db` | Banco de dados: usuários, senhas (protegidas) e carteiras |
| `requirements.txt` | Lista de bibliotecas Python usadas |
| `CLAUDE.md` | Documentação técnica do projeto (para quem for mexer no código) |
| `versao-2025-sem-login/` | Arquivos da versão antiga do painel (sem login, dados fixos de 2025) — não é mais usada, ficou só de arquivo |

## Sobre os dados

As cotações vêm do Yahoo Finance, atualizadas quando você abre a página e, a
partir daí, a cada 15 minutos. É uma fonte gratuita e não oficial — os
preços podem diferir em centavos dos da B3. Informação para fins
informativos, não é recomendação de investimento.
