"""
Motor do app "Ações — carteira com login".

Este arquivo cuida de tudo que precisa ficar escondido e seguro: login,
senhas, banco de dados, administração de usuários e busca de cotações no
Yahoo Finance. A parte visual (o que aparece na tela) fica em templates/
(estrutura das páginas) e static/ (estilo e comportamento no navegador).

Para rodar o app, dê dois cliques em "Abrir app.bat" (na mesma pasta deste
arquivo) ou, no terminal, rode:  python app.py
"""

from __future__ import annotations

import csv
import io
import json
import os
import secrets
import sqlite3
import threading
import webbrowser
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import anthropic
import yfinance as yf
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# ============================================================== CONFIGURAÇÃO

PASTA_BASE = Path(__file__).parent
PASTA_DADOS = PASTA_BASE / "dados"
PASTA_DADOS.mkdir(exist_ok=True)
ARQUIVO_BANCO = PASTA_DADOS / "banco.db"
ARQUIVO_CHAVE = PASTA_DADOS / "chave_secreta.txt"

load_dotenv(PASTA_BASE / ".env")

# Toda carteira nova começa com estas ações.
TICKERS_INICIAIS = ["PETR4", "ITUB4", "VALE3"]

# Períodos aceitos nos botões do gráfico (valores que o Yahoo Finance entende).
PERIODOS_VALIDOS = {"1mo", "3mo", "6mo", "ytd", "1y", "max"}
PERIODO_PADRAO = "6mo"

# Rótulo em português e "prazo" de cada período, usados no texto que vai para
# a IA (ver "Análise do Dia" mais abaixo).
PERIODO_INFO = {
    "1mo": ("1 mês", "curto prazo"),
    "3mo": ("3 meses", "curto prazo"),
    "6mo": ("6 meses", "médio prazo"),
    "ytd": ("no ano", "médio prazo"),
    "1y": ("1 ano", "longo prazo"),
    "max": ("máximo", "longo prazo"),
}

# Não busca de novo no Yahoo Finance se já buscamos há menos de 15 minutos.
DURACAO_CACHE = timedelta(minutes=15)

# Modelo mais barato da Anthropic no momento — suficiente para escrever um
# texto curto e didático a partir de números já calculados aqui no app.
MODELO_IA = "claude-haiku-4-5"

# Arquivo com as instruções do agente de IA, separado do código para poder
# ser ajustado sem mexer no resto do app.
ARQUIVO_INSTRUCOES_IA = PASTA_BASE / "instrucoes_analise_ia.txt"

# Reaproveita a "Análise do Dia" por 15 minutos para a mesma carteira e o
# mesmo período, em vez de chamar a IA de novo a cada clique.
DURACAO_CACHE_ANALISE = timedelta(minutes=15)

# Depois de logar, a pessoa continua logada por até 7 dias (mesmo fechando
# e abrindo o navegador de novo), a não ser que clique em "Sair".
DURACAO_SESSAO = timedelta(days=7)

# Letras e números usados para gerar senha temporária. Sem 0/O/1/l/I, que se
# confundem fácil quando alguém digita ou lê em voz alta.
ALFABETO_SENHA = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"

# Cores das linhas do gráfico e dos cards, na ordem em que as ações aparecem
# (definidas em static/style.css). Repete o ciclo se a carteira tiver mais
# ações do que cores.
CORES_SERIE = ["--serie-1", "--serie-2", "--serie-3", "--serie-4", "--serie-5", "--serie-6"]


def obter_chave_secreta() -> str:
    """A chave secreta assina o cookie de sessão. Gerada uma vez e guardada
    em disco, para que o login continue valendo mesmo se o app reiniciar."""
    if ARQUIVO_CHAVE.exists():
        return ARQUIVO_CHAVE.read_text(encoding="utf-8").strip()
    chave = secrets.token_hex(32)
    ARQUIVO_CHAVE.write_text(chave, encoding="utf-8")
    return chave


app = Flask(__name__)
app.secret_key = obter_chave_secreta()
app.permanent_session_lifetime = DURACAO_SESSAO

# Em produção (Railway) o site roda em https, então o cookie de sessão deve
# ser marcado como "secure" (só trafega em conexão criptografada). Em local
# (http://localhost) isso ficaria desligado, senão o login nunca funcionaria.
# O Railway define sozinho a variável RAILWAY_ENVIRONMENT_NAME em todo deploy.
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RAILWAY_ENVIRONMENT_NAME"))


# =================================================================== BANCO

def conectar_banco() -> sqlite3.Connection:
    conexao = sqlite3.connect(ARQUIVO_BANCO)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def iniciar_banco() -> None:
    with conectar_banco() as conexao:
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_completo TEXT NOT NULL,
                usuario TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL,
                senha_hash TEXT NOT NULL,
                tipo TEXT NOT NULL CHECK(tipo IN ('admin', 'comum')),
                senha_temporaria INTEGER NOT NULL DEFAULT 0,
                criado_em TEXT NOT NULL
            )
            """
        )
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS carteira (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                ticker TEXT NOT NULL,
                UNIQUE(usuario_id, ticker)
            )
            """
        )
        existem_usuarios = conexao.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"]
        if existem_usuarios == 0:
            criar_primeiro_admin(conexao)


def criar_primeiro_admin(conexao: sqlite3.Connection) -> None:
    usuario = os.environ.get("ADMIN_USUARIO", "").strip()
    senha = os.environ.get("ADMIN_SENHA", "").strip()
    nome = (os.environ.get("ADMIN_NOME", "").strip()) or "Administrador"
    email = (os.environ.get("ADMIN_EMAIL", "").strip()) or "admin@localhost"
    if not usuario or not senha:
        print(
            "\n[AVISO] Ainda não existe nenhum usuário e o arquivo .env não tem "
            "ADMIN_USUARIO/ADMIN_SENHA preenchidos. Copie .env.exemplo para .env, "
            "preencha essas duas linhas e rode o app de novo.\n"
        )
        return
    conexao.execute(
        "INSERT INTO usuarios (nome_completo, usuario, email, senha_hash, tipo, senha_temporaria, criado_em) "
        "VALUES (?, ?, ?, ?, 'admin', 0, ?)",
        (nome, usuario, email, generate_password_hash(senha), datetime.now().isoformat()),
    )
    usuario_id = conexao.execute("SELECT id FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()["id"]
    for ticker in TICKERS_INICIAIS:
        conexao.execute("INSERT OR IGNORE INTO carteira (usuario_id, ticker) VALUES (?, ?)", (usuario_id, ticker))
    print(f"\n[OK] Primeiro administrador criado: usuário \"{usuario}\".\n")


def usuario_por_id(conexao: sqlite3.Connection, usuario_id) -> sqlite3.Row | None:
    return conexao.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()


def usuario_para_json(linha: sqlite3.Row) -> dict:
    return {
        "id": linha["id"],
        "nomeCompleto": linha["nome_completo"],
        "usuario": linha["usuario"],
        "email": linha["email"],
        "tipo": linha["tipo"],
        "senhaTemporaria": bool(linha["senha_temporaria"]),
    }


def gerar_senha_temporaria(tamanho: int = 10) -> str:
    return "".join(secrets.choice(ALFABETO_SENHA) for _ in range(tamanho))


# ============================================================= AUTENTICAÇÃO

def login_necessario(rota):
    @wraps(rota)
    def decorada(*args, **kwargs):
        if "usuario_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"erro": "Sua sessão expirou. Faça login novamente."}), 401
            return redirect(url_for("pagina_login"))
        return rota(*args, **kwargs)

    return decorada


def admin_necessario(rota):
    @wraps(rota)
    def decorada(*args, **kwargs):
        with conectar_banco() as conexao:
            linha = usuario_por_id(conexao, session.get("usuario_id"))
        if not linha or linha["tipo"] != "admin":
            return jsonify({"erro": "Só administradores podem fazer isso."}), 403
        return rota(*args, **kwargs)

    return decorada


# Endpoints que continuam liberados mesmo com senha temporária pendente.
ENDPOINTS_LIBERADOS_SENHA_TEMPORARIA = {"api_login", "api_logout", "api_me", "api_trocar_senha"}


@app.before_request
def exigir_troca_de_senha_temporaria():
    if not request.path.startswith("/api/"):
        return None
    if request.endpoint in ENDPOINTS_LIBERADOS_SENHA_TEMPORARIA:
        return None
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return None
    with conectar_banco() as conexao:
        linha = usuario_por_id(conexao, usuario_id)
    if linha is None:
        session.clear()
        return jsonify({"erro": "Sua sessão expirou. Faça login novamente."}), 401
    if linha["senha_temporaria"]:
        return jsonify({
            "erro": "Antes de continuar, crie uma senha nova.",
            "precisaTrocarSenha": True,
        }), 403
    return None


# =================================================================== PÁGINAS

@app.route("/login")
def pagina_login():
    if "usuario_id" in session:
        return redirect(url_for("pagina_app"))
    return render_template("login.html")


@app.route("/")
@login_necessario
def pagina_app():
    return render_template("index.html")


# ============================================================ API: LOGIN

@app.route("/api/login", methods=["POST"])
def api_login():
    dados = request.get_json(silent=True) or {}
    usuario = (dados.get("usuario") or "").strip()
    senha = dados.get("senha") or ""
    if not usuario or not senha:
        return jsonify({"erro": "Informe usuário e senha."}), 400
    with conectar_banco() as conexao:
        linha = conexao.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
    if not linha or not check_password_hash(linha["senha_hash"], senha):
        return jsonify({"erro": "Usuário ou senha incorretos."}), 401
    session.clear()
    session.permanent = True
    session["usuario_id"] = linha["id"]
    return jsonify({"ok": True, "usuario": usuario_para_json(linha)})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    if "usuario_id" not in session:
        return jsonify({"erro": "Não autenticado."}), 401
    with conectar_banco() as conexao:
        linha = usuario_por_id(conexao, session["usuario_id"])
    if not linha:
        session.clear()
        return jsonify({"erro": "Não autenticado."}), 401
    return jsonify({"ok": True, "usuario": usuario_para_json(linha)})


@app.route("/api/conta/senha", methods=["POST"])
@login_necessario
def api_trocar_senha():
    dados = request.get_json(silent=True) or {}
    senha_atual = dados.get("senhaAtual") or ""
    senha_nova = dados.get("senhaNova") or ""
    if len(senha_nova) < 8:
        return jsonify({"erro": "A nova senha precisa ter pelo menos 8 caracteres."}), 400
    with conectar_banco() as conexao:
        linha = usuario_por_id(conexao, session["usuario_id"])
        if not linha or not check_password_hash(linha["senha_hash"], senha_atual):
            return jsonify({"erro": "A senha atual não confere."}), 400
        conexao.execute(
            "UPDATE usuarios SET senha_hash = ?, senha_temporaria = 0 WHERE id = ?",
            (generate_password_hash(senha_nova), linha["id"]),
        )
    return jsonify({"ok": True})


# ========================================================= API: CARTEIRA

@app.route("/api/carteira", methods=["GET"])
@login_necessario
def api_carteira_listar():
    with conectar_banco() as conexao:
        linhas = conexao.execute(
            "SELECT ticker FROM carteira WHERE usuario_id = ? ORDER BY ticker", (session["usuario_id"],)
        ).fetchall()
    return jsonify({"ok": True, "tickers": [linha["ticker"] for linha in linhas]})


@app.route("/api/carteira", methods=["POST"])
@login_necessario
def api_carteira_adicionar():
    dados = request.get_json(silent=True) or {}
    ticker = (dados.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify({"erro": "Informe o código da ação (ex.: WEGE3)."}), 400
    valido, mensagem = ticker_existe(ticker)
    if not valido:
        return jsonify({"erro": mensagem}), 400
    with conectar_banco() as conexao:
        try:
            conexao.execute(
                "INSERT INTO carteira (usuario_id, ticker) VALUES (?, ?)", (session["usuario_id"], ticker)
            )
        except sqlite3.IntegrityError:
            return jsonify({"erro": f"{ticker} já está na sua carteira."}), 400
    return jsonify({"ok": True, "ticker": ticker})


@app.route("/api/carteira/<ticker>", methods=["DELETE"])
@login_necessario
def api_carteira_remover(ticker):
    with conectar_banco() as conexao:
        conexao.execute(
            "DELETE FROM carteira WHERE usuario_id = ? AND ticker = ?",
            (session["usuario_id"], ticker.strip().upper()),
        )
    return jsonify({"ok": True})


# ======================================================= YAHOO FINANCE

_cache_trava = threading.Lock()
_cache: dict[tuple[str, str], dict] = {}


def _baixar_historico(ticker: str, periodo: str):
    papel = yf.Ticker(f"{ticker}.SA")
    return papel.history(period=periodo, auto_adjust=True)


def ticker_existe(ticker: str) -> tuple[bool, str]:
    try:
        historico = _baixar_historico(ticker, "5d")
    except Exception:
        return False, "Não consegui verificar essa ação agora. Pode ser a internet ou o Yahoo Finance fora do ar — tente de novo em instantes."
    if historico is None or historico.empty:
        return False, f'Não encontramos a ação "{ticker}". Confira o código (por exemplo WEGE3 ou BBAS3) e tente de novo.'
    return True, ""


def obter_historico_com_cache(ticker: str, periodo: str) -> dict:
    chave = (ticker, periodo)
    agora = datetime.now()
    with _cache_trava:
        entrada = _cache.get(chave)
        if entrada and (agora - entrada["buscado_em"]) < DURACAO_CACHE:
            return entrada["dados"]
    try:
        historico = _baixar_historico(ticker, periodo)
    except Exception:
        resultado = {"erro": "Não conseguimos falar com o Yahoo Finance agora. Tente novamente em alguns minutos."}
    else:
        if historico is None or historico.empty:
            resultado = {"erro": f'Não há dados para "{ticker}" nesse período.'}
        else:
            resultado = {
                "datas": [d.strftime("%Y-%m-%d") for d in historico.index],
                "fechamentos": [round(float(v), 4) for v in historico["Close"]],
            }
    with _cache_trava:
        _cache[chave] = {"dados": resultado, "buscado_em": agora}
    return resultado


def calcular_indicadores(datas: list[str], fechamentos: list[float]) -> dict:
    n = len(fechamentos)
    inicial = fechamentos[0]
    final = fechamentos[-1]
    maximo = max(fechamentos)
    minimo = min(fechamentos)
    indice_maximo = fechamentos.index(maximo)
    indice_minimo = fechamentos.index(minimo)
    variacoes_diarias = [fechamentos[i] / fechamentos[i - 1] - 1 for i in range(1, n) if fechamentos[i - 1]]
    if len(variacoes_diarias) > 1:
        media = sum(variacoes_diarias) / len(variacoes_diarias)
        variancia = sum((r - media) ** 2 for r in variacoes_diarias) / (len(variacoes_diarias) - 1)
        volatilidade = (variancia ** 0.5) * (252 ** 0.5) * 100
    else:
        volatilidade = 0.0
    return {
        "precoInicial": round(inicial, 2),
        "precoFinal": round(final, 2),
        "variacaoPct": round((final / inicial - 1) * 100, 2) if inicial else 0.0,
        "maxima": {"valor": round(maximo, 2), "data": datas[indice_maximo]},
        "minima": {"valor": round(minimo, 2), "data": datas[indice_minimo]},
        "volatilidade": round(volatilidade, 1),
        "base100": [round(v / inicial * 100, 4) for v in fechamentos] if inicial else [],
    }


# =========================================================== API: AÇÕES

@app.route("/api/acoes")
@login_necessario
def api_acoes():
    periodo = request.args.get("periodo", PERIODO_PADRAO)
    if periodo not in PERIODOS_VALIDOS:
        return jsonify({"erro": "Período inválido."}), 400
    with conectar_banco() as conexao:
        tickers = [
            linha["ticker"]
            for linha in conexao.execute(
                "SELECT ticker FROM carteira WHERE usuario_id = ? ORDER BY ticker", (session["usuario_id"],)
            ).fetchall()
        ]
    acoes = []
    for indice, ticker in enumerate(tickers):
        resultado = obter_historico_com_cache(ticker, periodo)
        cor = CORES_SERIE[indice % len(CORES_SERIE)]
        if "erro" in resultado:
            acoes.append({"ticker": ticker, "cor": cor, "disponivel": False, "mensagem": resultado["erro"]})
            continue
        indicadores = calcular_indicadores(resultado["datas"], resultado["fechamentos"])
        acoes.append({
            "ticker": ticker,
            "cor": cor,
            "disponivel": True,
            "datas": resultado["datas"],
            "fechamentos": resultado["fechamentos"],
            **indicadores,
        })
    return jsonify({
        "ok": True,
        "periodo": periodo,
        "acoes": acoes,
        "atualizadoEm": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })


@app.route("/api/acoes/csv")
@login_necessario
def api_acoes_csv():
    periodo = request.args.get("periodo", PERIODO_PADRAO)
    if periodo not in PERIODOS_VALIDOS:
        return jsonify({"erro": "Período inválido."}), 400
    with conectar_banco() as conexao:
        tickers = [
            linha["ticker"]
            for linha in conexao.execute(
                "SELECT ticker FROM carteira WHERE usuario_id = ? ORDER BY ticker", (session["usuario_id"],)
            ).fetchall()
        ]
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(["ticker", "data", "fechamento_rs"])
    for ticker in tickers:
        resultado = obter_historico_com_cache(ticker, periodo)
        if "erro" in resultado:
            continue
        for data, fechamento in zip(resultado["datas"], resultado["fechamentos"]):
            escritor.writerow([ticker, data, str(fechamento).replace(".", ",")])
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=minha-carteira-{periodo}.csv"},
    )


# ================================================ API: ANÁLISE DO DIA (IA)

def numero_br(valor: float, casas: int = 2) -> str:
    """Formata um número no padrão brasileiro (1.234,56)."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "@").replace(".", ",").replace("@", ".")


def moeda_br(valor: float) -> str:
    return f"R$ {numero_br(valor, 2)}"


def percentual_br(valor: float, casas: int = 2) -> str:
    sinal = "+" if valor > 0 else ("-" if valor < 0 else "")
    return f"{sinal}{numero_br(abs(valor), casas)}%"


def data_br(iso: str) -> str:
    ano, mes, dia = iso.split("-")
    return f"{dia}/{mes}/{ano}"


def calcular_tendencia(ticker: str) -> str:
    """Compara a média de 20 dias com a de 50 dias, usando até 1 ano de
    histórico (independente do período escolhido na tela), para dar um sinal
    de tendência mais estável do que olhar só o período selecionado."""
    resultado = obter_historico_com_cache(ticker, "1y")
    if "erro" in resultado:
        return "dados insuficientes para calcular"
    fechamentos = resultado["fechamentos"]
    if len(fechamentos) < 50:
        return "dados insuficientes para calcular (menos de 50 pregões de histórico)"
    media20 = sum(fechamentos[-20:]) / 20
    media50 = sum(fechamentos[-50:]) / 50
    if media20 > media50:
        return (
            f"média de 20 dias ({moeda_br(media20)}) acima da média de 50 dias "
            f"({moeda_br(media50)}) — indício de tendência de alta"
        )
    if media20 < media50:
        return (
            f"média de 20 dias ({moeda_br(media20)}) abaixo da média de 50 dias "
            f"({moeda_br(media50)}) — indício de tendência de baixa"
        )
    return "média de 20 dias igual à média de 50 dias — sem tendência clara"


def montar_bloco_dados(nome_usuario: str, periodo: str, tickers: list[str]) -> tuple[str, list[str]]:
    """Monta o texto com os números da carteira que vai para a IA. A IA só
    vê este texto — nunca os gráficos. Devolve o texto e a lista de tickers
    que ficaram sem dados (para avisar o usuário mesmo em caso de erro)."""
    rotulo, prazo = PERIODO_INFO[periodo]
    linhas = [
        f"Data de hoje: {datetime.now().strftime('%d/%m/%Y')}",
        f"Nome do usuário: {nome_usuario}",
        f"Período analisado: {rotulo} ({prazo})",
        "",
        "Ações da carteira:",
    ]
    sem_dados = []
    for ticker in tickers:
        resultado = obter_historico_com_cache(ticker, periodo)
        if "erro" in resultado:
            sem_dados.append(ticker)
            linhas.append(f"- {ticker}: sem dados ({resultado['erro']}). Ficou fora da análise.")
            continue
        datas, fechamentos = resultado["datas"], resultado["fechamentos"]
        indicadores = calcular_indicadores(datas, fechamentos)
        preco_atual = indicadores["precoFinal"]
        maxima_valor = indicadores["maxima"]["valor"]
        abaixo_maxima = ((maxima_valor - preco_atual) / maxima_valor * 100) if maxima_valor else 0.0
        if len(fechamentos) >= 6 and fechamentos[-6]:
            texto_5_pregoes = percentual_br((fechamentos[-1] / fechamentos[-6] - 1) * 100)
        else:
            texto_5_pregoes = "dados insuficientes"
        linhas.append(
            f"- {ticker}: preço atual {moeda_br(preco_atual)} ({data_br(datas[-1])}). "
            f"Variação no período: {percentual_br(indicadores['variacaoPct'])}. "
            f"Mínima {moeda_br(indicadores['minima']['valor'])} ({data_br(indicadores['minima']['data'])}), "
            f"máxima {moeda_br(maxima_valor)} ({data_br(indicadores['maxima']['data'])}) "
            f"— hoje está {numero_br(abaixo_maxima)}% abaixo da máxima. "
            f"Variação nos últimos 5 pregões: {texto_5_pregoes}. "
            f"Tendência: {calcular_tendencia(ticker)}. "
            f"Volatilidade anualizada: {numero_br(indicadores['volatilidade'], 1)}%."
        )
    return "\n".join(linhas), sem_dados


def obter_instrucoes_ia() -> str:
    return ARQUIVO_INSTRUCOES_IA.read_text(encoding="utf-8").strip()


def erro_amigavel_ia(excecao: Exception) -> str:
    """Traduz erros da API da Anthropic em mensagens amigáveis, em
    português, sem nunca expor detalhe técnico ao usuário."""
    if isinstance(excecao, anthropic.AuthenticationError):
        return "A chave de acesso à IA não é válida. Peça para o administrador conferir a chave configurada."
    if isinstance(excecao, anthropic.RateLimitError):
        return "A IA está recebendo muitos pedidos agora. Espere um instante e tente de novo."
    if isinstance(excecao, anthropic.APIStatusError):
        if "credit" in str(excecao).lower():
            return "O crédito da conta da IA acabou. Peça para o administrador adicionar mais crédito em console.anthropic.com."
        return "A IA está com algum problema no momento. Tente novamente em instantes."
    if isinstance(excecao, anthropic.APIConnectionError):
        return "Não conseguimos falar com a IA agora. Pode ser a internet ou a Anthropic fora do ar — tente novamente em instantes."
    return "Não conseguimos gerar a análise agora. Tente novamente em instantes."


_cache_analise_trava = threading.Lock()
_cache_analise: dict[tuple, dict] = {}


@app.route("/api/analise-dia")
@login_necessario
def api_analise_dia():
    periodo = request.args.get("periodo", PERIODO_PADRAO)
    if periodo not in PERIODOS_VALIDOS:
        return jsonify({"erro": "Período inválido."}), 400

    with conectar_banco() as conexao:
        usuario = usuario_por_id(conexao, session["usuario_id"])
        tickers = [
            linha["ticker"]
            for linha in conexao.execute(
                "SELECT ticker FROM carteira WHERE usuario_id = ? ORDER BY ticker", (session["usuario_id"],)
            ).fetchall()
        ]
    if not tickers:
        return jsonify({"erro": 'Sua carteira está vazia. Adicione ações em "Minha carteira" para receber uma análise.'}), 400

    rotulo, prazo = PERIODO_INFO[periodo]
    periodo_rotulo = f"{rotulo} ({prazo})"
    chave_cache = (session["usuario_id"], periodo, tuple(tickers))

    agora = datetime.now()
    with _cache_analise_trava:
        entrada = _cache_analise.get(chave_cache)
    if entrada and (agora - entrada["geradoEmDt"]) < DURACAO_CACHE_ANALISE:
        return jsonify({
            "ok": True,
            "cache": True,
            "texto": entrada["texto"],
            "periodoRotulo": periodo_rotulo,
            "geradoEm": entrada["geradoEm"],
            "semDados": entrada["semDados"],
        })

    chave_ia = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not chave_ia:
        return jsonify({
            "erro": "A análise por IA ainda não foi configurada neste app. Peça para o administrador configurar a chave de acesso (ANTHROPIC_API_KEY).",
        }), 503

    bloco_dados, sem_dados = montar_bloco_dados(usuario["nome_completo"], periodo, tickers)
    instrucoes = obter_instrucoes_ia()
    gerado_em_texto = agora.strftime("%H:%M")

    def gerar():
        meta = {"tipo": "meta", "periodoRotulo": periodo_rotulo, "geradoEm": gerado_em_texto, "semDados": sem_dados}
        yield json.dumps(meta) + "\n"
        cliente = anthropic.Anthropic(api_key=chave_ia)
        pedacos_texto = []
        try:
            with cliente.messages.stream(
                model=MODELO_IA,
                max_tokens=1024,
                system=instrucoes,
                messages=[{"role": "user", "content": bloco_dados}],
            ) as stream:
                for pedaco in stream.text_stream:
                    pedacos_texto.append(pedaco)
                    yield pedaco
        except Exception as excecao:  # nunca deixa um erro técnico chegar à tela
            yield "\n[[ERRO]]" + erro_amigavel_ia(excecao)
            return
        texto_final = "".join(pedacos_texto)
        with _cache_analise_trava:
            _cache_analise[chave_cache] = {
                "texto": texto_final,
                "geradoEm": gerado_em_texto,
                "geradoEmDt": agora,
                "semDados": sem_dados,
            }

    return Response(
        gerar(),
        mimetype="text/plain",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ========================================================= API: ADMINISTRAÇÃO

@app.route("/api/admin/usuarios", methods=["GET"])
@login_necessario
@admin_necessario
def api_admin_listar():
    with conectar_banco() as conexao:
        linhas = conexao.execute("SELECT * FROM usuarios ORDER BY nome_completo COLLATE NOCASE").fetchall()
    return jsonify({"ok": True, "usuarios": [usuario_para_json(linha) for linha in linhas]})


@app.route("/api/admin/usuarios", methods=["POST"])
@login_necessario
@admin_necessario
def api_admin_criar():
    dados = request.get_json(silent=True) or {}
    nome_completo = (dados.get("nomeCompleto") or "").strip()
    usuario = (dados.get("usuario") or "").strip()
    email = (dados.get("email") or "").strip()
    if not nome_completo or not usuario or not email:
        return jsonify({"erro": "Preencha nome completo, usuário e e-mail."}), 400
    senha_temporaria = gerar_senha_temporaria()
    with conectar_banco() as conexao:
        try:
            conexao.execute(
                "INSERT INTO usuarios (nome_completo, usuario, email, senha_hash, tipo, senha_temporaria, criado_em) "
                "VALUES (?, ?, ?, ?, 'comum', 1, ?)",
                (nome_completo, usuario, email, generate_password_hash(senha_temporaria), datetime.now().isoformat()),
            )
        except sqlite3.IntegrityError:
            return jsonify({"erro": f'Já existe um usuário com o nome de usuário "{usuario}".'}), 400
        novo_id = conexao.execute("SELECT id FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()["id"]
        for ticker in TICKERS_INICIAIS:
            conexao.execute("INSERT OR IGNORE INTO carteira (usuario_id, ticker) VALUES (?, ?)", (novo_id, ticker))
    return jsonify({"ok": True, "senhaTemporaria": senha_temporaria})


@app.route("/api/admin/usuarios/<int:usuario_id>/redefinir-senha", methods=["POST"])
@login_necessario
@admin_necessario
def api_admin_redefinir_senha(usuario_id):
    senha_temporaria = gerar_senha_temporaria()
    with conectar_banco() as conexao:
        linha = usuario_por_id(conexao, usuario_id)
        if not linha:
            return jsonify({"erro": "Usuário não encontrado."}), 404
        conexao.execute(
            "UPDATE usuarios SET senha_hash = ?, senha_temporaria = 1 WHERE id = ?",
            (generate_password_hash(senha_temporaria), usuario_id),
        )
    return jsonify({"ok": True, "senhaTemporaria": senha_temporaria})


@app.route("/api/admin/usuarios/<int:usuario_id>/promover", methods=["POST"])
@login_necessario
@admin_necessario
def api_admin_promover(usuario_id):
    with conectar_banco() as conexao:
        linha = usuario_por_id(conexao, usuario_id)
        if not linha:
            return jsonify({"erro": "Usuário não encontrado."}), 404
        conexao.execute("UPDATE usuarios SET tipo = 'admin' WHERE id = ?", (usuario_id,))
    return jsonify({"ok": True})


@app.route("/api/admin/usuarios/<int:usuario_id>/rebaixar", methods=["POST"])
@login_necessario
@admin_necessario
def api_admin_rebaixar(usuario_id):
    with conectar_banco() as conexao:
        linha = usuario_por_id(conexao, usuario_id)
        if not linha:
            return jsonify({"erro": "Usuário não encontrado."}), 404
        if linha["tipo"] == "admin":
            total_admins = conexao.execute("SELECT COUNT(*) AS n FROM usuarios WHERE tipo = 'admin'").fetchone()["n"]
            if total_admins <= 1:
                return jsonify({"erro": "Não é possível rebaixar: precisa sempre existir pelo menos um administrador."}), 400
        conexao.execute("UPDATE usuarios SET tipo = 'comum' WHERE id = ?", (usuario_id,))
    return jsonify({"ok": True})


@app.route("/api/admin/usuarios/<int:usuario_id>", methods=["DELETE"])
@login_necessario
@admin_necessario
def api_admin_excluir(usuario_id):
    if usuario_id == session.get("usuario_id"):
        return jsonify({"erro": "Você não pode excluir a si mesmo."}), 400
    with conectar_banco() as conexao:
        linha = usuario_por_id(conexao, usuario_id)
        if not linha:
            return jsonify({"erro": "Usuário não encontrado."}), 404
        if linha["tipo"] == "admin":
            total_admins = conexao.execute("SELECT COUNT(*) AS n FROM usuarios WHERE tipo = 'admin'").fetchone()["n"]
            if total_admins <= 1:
                return jsonify({"erro": "Não é possível excluir o último administrador."}), 400
        conexao.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    return jsonify({"ok": True})


# ====================================================================== MAIN

# Sempre prepara o banco de dados quando este módulo é carregado — tanto ao
# rodar "python app.py" direto (uso local) quanto quando um servidor de
# produção (waitress) importa "app" sem passar por "__main__" (uso no Railway).
iniciar_banco()

if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    print("\nAbrindo o app em http://localhost:5000 — deixe esta janela aberta enquanto usa o app.\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
