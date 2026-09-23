"""
Atualiza os dados do painel "Performance das Ações".

Como usar (no PowerShell, dentro da pasta app-acoes-2025):

    python atualizar_dados.py

O que ele faz:
  1. Baixa o arquivo oficial de cotações históricas da B3 (COTAHIST) do ano.
  2. Busca no Yahoo Finance os eventos (bonificações/desdobramentos) e os proventos.
  3. Confere os dados (pregões completos, preços B3 x Yahoo, saltos suspeitos).
  4. Só se tudo estiver certo, grava os arquivos da pasta data/.
     Se algo der errado, os dados antigos continuam intactos.
"""

import csv
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- configuração
ANO = 2025
ACOES = [
    {"ticker": "PETR4", "empresa": "Petrobras", "descricao": "Petróleo Brasileiro S.A. · PN"},
    {"ticker": "ITUB4", "empresa": "Itaú Unibanco", "descricao": "Itaú Unibanco Holding S.A. · PN"},
    {"ticker": "VALE3", "empresa": "Vale", "descricao": "Vale S.A. · ON"},
]
URL_B3 = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ANO}.ZIP"
PASTA_DADOS = Path(__file__).parent / "data"
LIMITE_DIFERENCA_YAHOO = 0.01  # preços B3 x Yahoo podem diferir no máximo 1%
LIMITE_SALTO_DIARIO = 0.20  # variação diária acima de 20% indica evento não ajustado


class ErroAmigavel(Exception):
    """Erro com mensagem pensada para quem não é programador."""


# ------------------------------------------------------------------------- B3
def baixar_b3():
    print(f"1/4  Baixando o arquivo oficial da B3 ({ANO})... isso pode levar um minuto.")
    try:
        # o site da B3 recusa pedidos sem identificação de navegador
        pedido = urllib.request.Request(URL_B3, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(pedido, timeout=300) as resposta:
            conteudo = resposta.read()
    except urllib.error.HTTPError as erro:
        raise ErroAmigavel(
            f"O site da B3 recusou o download (código {erro.code}). "
            "O arquivo do ano pode ainda não existir ou o site pode estar fora do ar. Tente mais tarde."
        )
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ErroAmigavel("Não consegui acessar o site da B3. Verifique sua internet e tente novamente.")
    try:
        return zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile:
        raise ErroAmigavel("O arquivo recebido da B3 veio incompleto ou corrompido. Tente novamente.")


def ler_cotahist(arquivo_zip):
    """Lê o layout oficial COTAHIST (posições fixas, documentado pela B3)."""
    tickers = {acao["ticker"] for acao in ACOES}
    pregoes = {ticker: {} for ticker in tickers}
    with arquivo_zip.open(arquivo_zip.namelist()[0]) as arquivo:
        for bruta in arquivo:
            linha = bruta.decode("latin-1")
            if linha[:2] != "01":  # 01 = linha de cotação
                continue
            ticker = linha[12:24].strip()
            # CODBDI 02 = lote padrão; TPMERC 010 = mercado à vista
            if ticker not in tickers or linha[10:12] != "02" or linha[24:27] != "010":
                continue
            dia = f"{linha[2:6]}-{linha[6:8]}-{linha[8:10]}"
            fator_cotacao = int(linha[210:217])  # preços vêm por lote de N ações
            pregoes[ticker][dia] = {
                "fechamento": int(linha[108:121]) / 100 / fator_cotacao,
                "volume": int(linha[170:188]) / 100,
                "especificacao": linha[39:49],
            }
    # o arquivo da B3 não vem em ordem de data
    return {ticker: dict(sorted(dias.items())) for ticker, dias in pregoes.items()}


# ---------------------------------------------------------------------- Yahoo
def buscar_yahoo():
    print("2/4  Buscando bonificações, desdobramentos e proventos no Yahoo Finance...")
    try:
        import yfinance as yf
    except ImportError:
        raise ErroAmigavel("Falta a biblioteca yfinance. Instale com:  pip install yfinance")

    resultado = {}
    for acao in ACOES:
        ticker = acao["ticker"]
        try:
            # até hoje: eventos posteriores ao ano também mudam a escala do Yahoo
            historico = yf.Ticker(ticker + ".SA").history(
                start=f"{ANO}-01-01", auto_adjust=False, actions=True
            )
        except Exception:
            raise ErroAmigavel(
                f"O Yahoo Finance não respondeu ao pedir os dados de {ticker}. "
                "Verifique sua internet e tente novamente em alguns minutos."
            )
        if historico.empty:
            raise ErroAmigavel(f"O Yahoo Finance não devolveu dados para {ticker}. Tente mais tarde.")
        historico.index = historico.index.tz_localize(None).strftime("%Y-%m-%d")
        resultado[ticker] = historico
    return resultado


def produto(fatores):
    total = 1.0
    for fator in fatores:
        total *= fator
    return total


# ------------------------------------------------------------------ montagem
def montar_acao(acao, pregoes_b3, yahoo):
    ticker = acao["ticker"]
    if not pregoes_b3:
        raise ErroAmigavel(f"O arquivo da B3 não tem cotações de {ticker} em {ANO}.")

    inicio, fim = next(iter(pregoes_b3)), next(reversed(pregoes_b3))
    desdobramentos = [
        (dia, float(fator)) for dia, fator in yahoo["Stock Splits"].items() if fator > 0
    ]
    eventos_ano = [(dia, fator) for dia, fator in desdobramentos if inicio < dia <= fim]
    avisos = []

    def fator_no_ano(dia):  # eventos do ano que ocorreram depois do dia
        return produto(f for d, f in eventos_ano if d > dia)

    def fator_ate_hoje(dia):  # todos os eventos depois do dia (escala do Yahoo)
        return produto(f for d, f in desdobramentos if d > dia)

    # confere cada evento com a marcação "EB" (ex-bonificação) ou desdobramento da B3
    for dia, fator in eventos_ano:
        especificacao = pregoes_b3.get(dia, {}).get("especificacao", "")
        if " EB " not in f" {especificacao} " and " ED " not in f" {especificacao} ":
            avisos.append(f"{ticker}: evento de {dia} não aparece marcado como 'ex' na B3.")

    # confere o preço de fechamento B3 x Yahoo (Yahoo convertido para a escala original)
    diferenca_maxima = 0.0
    fechamento_yahoo = yahoo["Close"]
    dias_sem_yahoo = [dia for dia in pregoes_b3 if dia not in fechamento_yahoo.index]
    for dia, pregao in pregoes_b3.items():
        if dia in fechamento_yahoo.index:
            original = float(fechamento_yahoo[dia]) * fator_ate_hoje(dia)
            diferenca_maxima = max(diferenca_maxima, abs(original / pregao["fechamento"] - 1))
    if diferenca_maxima > LIMITE_DIFERENCA_YAHOO:
        raise ErroAmigavel(
            f"Os preços de {ticker} no Yahoo diferem {diferenca_maxima:.1%} dos da B3. "
            "Os eventos do Yahoo não são confiáveis agora; os dados antigos foram mantidos."
        )
    if dias_sem_yahoo:
        avisos.append(f"{ticker}: {len(dias_sem_yahoo)} pregão(ões) da B3 sem correspondente no Yahoo.")

    datas = list(pregoes_b3)
    fechamento = [round(pregoes_b3[d]["fechamento"], 2) for d in datas]
    ajustado = [round(pregoes_b3[d]["fechamento"] / fator_no_ano(d), 4) for d in datas]

    for anterior, atual, dia in zip(ajustado, ajustado[1:], datas[1:]):
        if abs(atual / anterior - 1) > LIMITE_SALTO_DIARIO:
            raise ErroAmigavel(
                f"{ticker} tem uma variação suspeita em {dia} ({atual / anterior - 1:+.0%}). "
                "Pode ser um desdobramento não registrado. Os dados antigos foram mantidos."
            )

    # proventos com data "ex" depois do 1º pregão: quem comprou no início teve direito
    proventos = []
    for dia, valor in yahoo["Dividends"].items():
        if valor > 0 and inicio < dia <= fim:
            valor_original = float(valor) * fator_ate_hoje(dia)
            proventos.append({"data": dia, "valor": round(valor_original / fator_no_ano(dia), 4)})

    return {
        "ticker": ticker,
        "empresa": acao["empresa"],
        "descricao": acao["descricao"],
        "datas": datas,
        "fechamento": fechamento,
        "fechamentoAjustado": ajustado,
        "volume": [round(pregoes_b3[d]["volume"], 2) for d in datas],
        "eventos": [{"data": d, "fator": f} for d, f in eventos_ano],
        "proventos": proventos,
        "conferencia": {"diferencaMaximaYahooPct": round(diferenca_maxima * 100, 3)},
    }, avisos


# ------------------------------------------------------------------ gravação
def gravar(acoes):
    print("4/4  Gravando os arquivos da pasta data/...")
    PASTA_DADOS.mkdir(exist_ok=True)
    pacote = {
        "ano": ANO,
        "geradoEm": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "fontes": {
            "precos": f"B3 — Séries Históricas (COTAHIST_A{ANO})",
            "urlPrecos": URL_B3,
            "eventosEProventos": "Yahoo Finance (biblioteca yfinance)",
        },
        "acoes": acoes,
    }
    js = (
        "// Arquivo gerado automaticamente por atualizar_dados.py. Não edite à mão.\n"
        "window.DADOS_ACOES = " + json.dumps(pacote, ensure_ascii=False) + ";\n"
    )

    def numero(valor, casas):  # formato que o Excel brasileiro entende
        return f"{valor:.{casas}f}".replace(".", ",")

    cotacoes = io.StringIO()
    escritor = csv.writer(cotacoes, delimiter=";", lineterminator="\n")
    escritor.writerow(["data", "ticker", "fechamento_b3_rs", "fechamento_ajustado_rs", "volume_rs"])
    for acao in acoes:
        for i, dia in enumerate(acao["datas"]):
            escritor.writerow([
                dia, acao["ticker"], numero(acao["fechamento"][i], 2),
                numero(acao["fechamentoAjustado"][i], 4), numero(acao["volume"][i], 2),
            ])

    proventos = io.StringIO()
    escritor = csv.writer(proventos, delimiter=";", lineterminator="\n")
    escritor.writerow(["data_ex", "ticker", "valor_por_acao_rs"])
    for acao in acoes:
        for provento in acao["proventos"]:
            escritor.writerow([provento["data"], acao["ticker"], numero(provento["valor"], 4)])

    # grava em arquivo temporário e só depois substitui: nunca deixa arquivo pela metade
    for nome, texto, codificacao in [
        (f"cotacoes-{ANO}.js", js, "utf-8"),
        (f"cotacoes-{ANO}.csv", cotacoes.getvalue(), "utf-8-sig"),
        (f"proventos-{ANO}.csv", proventos.getvalue(), "utf-8-sig"),
    ]:
        temporario = PASTA_DADOS / (nome + ".tmp")
        temporario.write_text(texto, encoding=codificacao)
        temporario.replace(PASTA_DADOS / nome)


def main():
    pregoes = ler_cotahist(baixar_b3())
    yahoo = buscar_yahoo()

    print("3/4  Conferindo os dados...")
    acoes, avisos = [], []
    for acao in ACOES:
        montada, avisos_acao = montar_acao(acao, pregoes[acao["ticker"]], yahoo[acao["ticker"]])
        acoes.append(montada)
        avisos += avisos_acao

    datas = {tuple(acao["datas"]) for acao in acoes}
    if len(datas) > 1:
        avisos.append("As ações não têm exatamente os mesmos dias de pregão.")

    gravar(acoes)

    print("\nPronto! Resumo:")
    for acao in acoes:
        eventos = ", ".join(f"{e['data']} (x{e['fator']})" for e in acao["eventos"]) or "nenhum"
        print(
            f"  {acao['ticker']}: {len(acao['datas'])} pregões ({acao['datas'][0]} a {acao['datas'][-1]}) | "
            f"fechamento R$ {acao['fechamento'][0]:.2f} -> R$ {acao['fechamento'][-1]:.2f} | "
            f"bonificações/desdobramentos: {eventos} | proventos: {len(acao['proventos'])} | "
            f"diferença máx. B3 x Yahoo: {acao['conferencia']['diferencaMaximaYahooPct']}%"
        )
    for aviso in avisos:
        print("  ATENÇÃO:", aviso)


if __name__ == "__main__":
    try:
        main()
    except ErroAmigavel as erro:
        print("\nNão foi possível atualizar os dados:", erro)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAtualização cancelada. Os dados antigos foram mantidos.")
        sys.exit(1)
