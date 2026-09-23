/*
 * Painel autenticado: menu lateral, página de Ações (ao vivo, via Yahoo
 * Finance), Minha carteira, Minha conta e Administração.
 * Fala com o motor (app.py) só por chamadas a /api/...
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);

  // ======================================================== FORMATAÇÃO (pt-BR)
  const MENOS = '−';
  const formatoMoeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

  function numero(valor, casas) {
    return valor.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  }
  function moeda(valor) { return formatoMoeda.format(valor); }
  function moedaComSinal(valor) {
    const sinal = valor > 0 ? '+' : valor < 0 ? MENOS : '';
    return sinal + formatoMoeda.format(Math.abs(valor));
  }
  function percentual(valor, casas = 2) {
    const sinal = valor > 0 ? '+' : valor < 0 ? MENOS : '';
    return sinal + numero(Math.abs(valor), casas) + '%';
  }
  function classeSinal(valor) { return valor > 0 ? 'alta' : valor < 0 ? 'baixa' : ''; }
  function dataBr(iso) {
    const [ano, mes, dia] = iso.split('-').map(Number);
    return String(dia).padStart(2, '0') + '/' + String(mes).padStart(2, '0') + '/' + ano;
  }
  function dataLonga(iso) {
    const [ano, mes, dia] = iso.split('-').map(Number);
    return new Date(ano, mes - 1, dia).toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
  }
  function escapar(texto) {
    return String(texto).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function lerCor(variavel) { return getComputedStyle(document.documentElement).getPropertyValue(variavel).trim(); }
  function selo(valor) {
    const alta = valor >= 0;
    return '<span class="selo selo--' + (alta ? 'alta' : 'baixa') + '"><span aria-hidden="true">' + (alta ? '▲' : '▼') +
      '</span><span class="visualmente-oculto">' + (alta ? 'Alta de' : 'Queda de') + '</span>' + percentual(valor) + '</span>';
  }
  function iniciais(nome) {
    const partes = String(nome).trim().split(/\s+/).filter(Boolean);
    if (!partes.length) return '?';
    const letras = partes.length > 1 ? partes[0][0] + partes[partes.length - 1][0] : partes[0].slice(0, 2);
    return letras.toUpperCase();
  }

  // ============================================================== API
  async function api(caminho, opcoes) {
    let resposta;
    try {
      resposta = await fetch(caminho, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opcoes));
    } catch (erro) {
      return { erro: 'Não conseguimos falar com o app agora. Confira se a janela preta ainda está aberta e tente de novo.' };
    }
    let corpo = {};
    try { corpo = await resposta.json(); } catch (erro) { /* resposta sem corpo (ex.: CSV) */ }
    if (resposta.status === 401) {
      window.location.href = '/login';
      return { erro: 'sessão expirada' };
    }
    if (resposta.status === 403 && corpo.precisaTrocarSenha) {
      ativarBloqueioSenha();
      return { erro: 'precisa trocar senha' };
    }
    if (!resposta.ok) {
      return { erro: corpo.erro || 'Algo deu errado. Tente de novo.' };
    }
    return corpo;
  }

  // ======================================================= AVISOS / ESTADO
  function mostrarAvisoGlobal(titulo, texto) {
    $('aviso-global-titulo').textContent = titulo;
    $('aviso-global-texto').textContent = texto;
    $('aviso-global').hidden = false;
  }
  function esconderAvisoGlobal() { $('aviso-global').hidden = true; }

  function exibirAvisoInline(elemento, texto, sucesso) {
    elemento.querySelector('p').textContent = texto;
    elemento.classList.toggle('aviso--sucesso', Boolean(sucesso));
    elemento.hidden = false;
  }

  let usuarioAtual = null;
  let paginaAtual = 'acoes';
  let periodoAtual = '6mo';

  function ativarBloqueioSenha() {
    document.querySelectorAll('.menu__item').forEach((b) => { b.disabled = true; });
    document.querySelectorAll('.pagina-conteudo').forEach((s) => { s.hidden = true; });
    $('bloqueio-senha').hidden = false;
  }
  function liberarNavegacao() {
    document.querySelectorAll('.menu__item').forEach((b) => { b.disabled = false; });
    $('bloqueio-senha').hidden = true;
  }

  function aplicarUsuario(usuario) {
    usuarioAtual = usuario;
    $('nome-usuario').textContent = usuario.nomeCompleto;
    $('avatar-usuario').textContent = iniciais(usuario.nomeCompleto);
    $('menu-admin').hidden = usuario.tipo !== 'admin';
  }

  function irParaPagina(nome) {
    paginaAtual = nome;
    document.querySelectorAll('.menu__item').forEach((b) => {
      if (b.dataset.pagina) b.setAttribute('aria-current', b.dataset.pagina === nome ? 'page' : 'false');
    });
    document.querySelectorAll('.pagina-conteudo').forEach((s) => { s.hidden = s.id !== 'pagina-' + nome; });
    if (nome === 'acoes') carregarAcoes();
    else if (nome === 'carteira') carregarCarteira();
    else if (nome === 'conta') carregarConta();
    else if (nome === 'admin') carregarAdmin();
  }

  // ================================================================ AÇÕES
  const PERIODOS = [
    { valor: '1mo', rotulo: '1 mês' },
    { valor: '3mo', rotulo: '3 meses' },
    { valor: '6mo', rotulo: '6 meses' },
    { valor: 'ytd', rotulo: 'No ano' },
    { valor: '1y', rotulo: '1 ano' },
    { valor: 'max', rotulo: 'Máximo' },
  ];

  function montarBotoesPeriodo() {
    $('periodo').innerHTML = PERIODOS.map((p) =>
      '<button type="button" data-periodo="' + p.valor + '" aria-pressed="' + (p.valor === periodoAtual) + '">' + p.rotulo + '</button>'
    ).join('');
    $('periodo').addEventListener('click', (evento) => {
      const botao = evento.target.closest('button');
      if (!botao) return;
      periodoAtual = botao.dataset.periodo;
      $('periodo').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === botao)));
      carregarAcoes();
    });
  }

  function esqueletoCards() {
    return Array.from({ length: 3 }).map(() =>
      '<div class="card card--carregando"><span class="esqueleto"></span><span class="esqueleto esqueleto--grande"></span><span class="esqueleto"></span></div>'
    ).join('');
  }

  function faisca(base100, cor) {
    const minimo = Math.min(100, ...base100);
    const maximo = Math.max(100, ...base100);
    const altura = 44;
    const y = (v) => (altura - 2 - ((v - minimo) / (maximo - minimo || 1)) * (altura - 4)).toFixed(2);
    const x = (i) => ((i / (base100.length - 1 || 1)) * 100).toFixed(3);
    const caminho = base100.map((v, i) => (i ? 'L' : 'M') + x(i) + ' ' + y(v)).join(' ');
    return '<svg class="card__faisca" viewBox="0 0 100 ' + altura + '" preserveAspectRatio="none" aria-hidden="true">' +
      '<line x1="0" x2="100" y1="' + y(100) + '" y2="' + y(100) + '" stroke="var(--eixo)" stroke-width="1" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>' +
      '<path d="' + caminho + '" fill="none" stroke="' + cor + '" stroke-width="2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>';
  }

  function renderCardsAcoes(acoes) {
    if (!acoes.length) {
      $('ac-cards').removeAttribute('aria-busy');
      $('ac-cards').innerHTML = '<p class="lista-carteira__vazio">Sua carteira está vazia. Vá em "Minha carteira" para adicionar ações.</p>';
      return;
    }
    $('ac-cards').innerHTML = acoes.map((a) => {
      const estilo = ' style="--cor: var(' + a.cor + ')"';
      const cabecalho = '<div class="card__topo"><span class="card__marca" aria-hidden="true">' + escapar(a.ticker.slice(0, 2)) +
        '</span><div class="card__nome"><h3>' + escapar(a.ticker) + '</h3><span>B3</span></div>' +
        (a.disponivel ? selo(a.variacaoPct) : '') + '</div>';
      if (!a.disponivel) {
        return '<article class="card card--indisponivel"' + estilo + '>' + cabecalho + '<p>' + escapar(a.mensagem) + '</p></article>';
      }
      const variacaoReais = a.precoFinal - a.precoInicial;
      return '<article class="card"' + estilo + ' aria-label="' + escapar(a.ticker) + '">' + cabecalho +
        '<p class="card__preco">' + moeda(a.precoFinal) + '</p>' +
        '<p class="card__rotulo">Cotação mais recente</p>' +
        faisca(a.base100, lerCor(a.cor)) +
        '<dl class="card__dados">' +
          '<div><dt>Preço inicial do período</dt><dd>' + moeda(a.precoInicial) + '</dd></div>' +
          '<div><dt>Variação em R$</dt><dd class="' + classeSinal(variacaoReais) + '">' + moedaComSinal(variacaoReais) + '</dd></div>' +
        '</dl></article>';
    }).join('');
    $('ac-cards').removeAttribute('aria-busy');
  }

  let grafico = null;
  const pluginLinhaBase = {
    id: 'linhaBase',
    beforeDatasetsDraw(chart) {
      const escalaY = chart.scales.y;
      const y = escalaY.getPixelForValue(100);
      if (y < chart.chartArea.top || y > chart.chartArea.bottom) return;
      const ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = lerCor('--eixo');
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(chart.chartArea.left, y);
      ctx.lineTo(chart.chartArea.right, y);
      ctx.stroke();
      ctx.restore();
    },
  };
  const pluginMira = {
    id: 'mira',
    afterDatasetsDraw(chart) {
      const ativos = chart.tooltip && chart.tooltip.getActiveElements();
      if (!ativos || !ativos.length) return;
      const x = ativos[0].element.x;
      const ctx = chart.ctx;
      ctx.save();
      ctx.strokeStyle = lerCor('--texto-3');
      ctx.globalAlpha = 0.5;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, chart.chartArea.top);
      ctx.lineTo(x, chart.chartArea.bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  function renderGraficoAcoes(acoesTodas) {
    const acoes = acoesTodas.filter((a) => a.disponivel && a.datas && a.datas.length > 1);
    const vazio = $('ac-grafico-vazio');
    if (grafico) { grafico.destroy(); grafico = null; }
    if (!acoes.length) {
      vazio.hidden = false;
      vazio.textContent = acoesTodas.length
        ? 'Não conseguimos carregar os dados das ações da sua carteira agora.'
        : 'Adicione ações à sua carteira para ver o gráfico.';
      return;
    }
    vazio.hidden = true;
    if (typeof window.Chart !== 'function') {
      $('ac-grafico').innerHTML = '<div class="grafico__erro"><p>O gráfico não pôde ser carregado. Recarregue a página (F5).</p></div>';
      return;
    }
    const todasDatas = Array.from(new Set(acoes.flatMap((a) => a.datas))).sort();
    const cores = { superficie: lerCor('--superficie'), borda: lerCor('--borda'), texto: lerCor('--texto'), texto3: lerCor('--texto-3'), grade: lerCor('--grade'), fonte: lerCor('--fonte') };

    const datasets = acoes.map((a) => {
      const porData = new Map(a.datas.map((d, i) => [d, i]));
      const cor = lerCor(a.cor);
      return {
        label: a.ticker,
        data: todasDatas.map((d) => (porData.has(d) ? a.base100[porData.get(d)] : null)),
        indices: todasDatas.map((d) => (porData.has(d) ? porData.get(d) : null)),
        precos: a.fechamentos,
        borderColor: cor,
        backgroundColor: cor,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBorderWidth: 2,
        pointHoverBorderColor: cores.superficie,
        pointHitRadius: 8,
        tension: 0,
        spanGaps: true,
      };
    });

    Chart.defaults.font.family = cores.fonte;
    grafico = new Chart($('ac-canvas'), {
      type: 'line',
      data: { labels: todasDatas, datasets },
      plugins: [pluginLinhaBase, pluginMira],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom', labels: { color: cores.texto3, boxWidth: 10, usePointStyle: true, padding: 14, font: { size: 12.5 } } },
          tooltip: {
            backgroundColor: cores.superficie,
            borderColor: cores.borda,
            borderWidth: 1,
            titleColor: cores.texto,
            bodyColor: cores.texto,
            titleFont: { weight: '600', size: 13 },
            bodyFont: { size: 13 },
            padding: 12,
            cornerRadius: 10,
            boxPadding: 6,
            usePointStyle: true,
            itemSort: (a, b) => b.parsed.y - a.parsed.y,
            callbacks: {
              title: (itens) => (itens.length ? dataLonga(todasDatas[itens[0].dataIndex]) : ''),
              label: (item) => {
                const ds = item.dataset;
                const i = ds.indices[item.dataIndex];
                const preco = i != null ? moeda(ds.precos[i]) : '—';
                return ds.label + '  ' + preco + '   ' + percentual(item.parsed.y - 100) + ' no período';
              },
            },
          },
        },
        scales: {
          x: { grid: { display: false }, border: { color: lerCor('--eixo') }, ticks: { color: cores.texto3, maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: { size: 12 } } },
          y: { grid: { color: cores.grade, drawTicks: false }, border: { display: false }, ticks: { color: cores.texto3, padding: 8, font: { size: 12 }, maxTicksLimit: 7, callback: (v) => numero(v, 0) } },
        },
      },
    });
  }

  function renderIndicadoresAcoes(acoes) {
    if (!acoes.length) { $('ac-indicadores').innerHTML = ''; return; }
    const cabecalho = acoes.map((a) =>
      '<th scope="col"><span class="th-acao"><span class="ponto" style="--cor: var(' + a.cor + ')"></span>' + escapar(a.ticker) + '</span></th>'
    ).join('');
    const linhas = [
      ['Preço inicial', (a) => moeda(a.precoInicial)],
      ['Preço final', (a) => moeda(a.precoFinal)],
      ['Variação no período', (a) => '<span class="' + classeSinal(a.variacaoPct) + '">' + percentual(a.variacaoPct) + '</span>'],
      ['Máxima', (a) => moeda(a.maxima.valor) + '<span class="sub">' + dataBr(a.maxima.data) + '</span>'],
      ['Mínima', (a) => moeda(a.minima.valor) + '<span class="sub">' + dataBr(a.minima.data) + '</span>'],
      ['Volatilidade anualizada', (a) => numero(a.volatilidade, 1) + '%'],
    ];
    $('ac-indicadores').innerHTML =
      '<table><caption class="visualmente-oculto">Indicadores por ação</caption>' +
      '<thead><tr><th scope="col">Indicador</th>' + cabecalho + '</tr></thead><tbody>' +
      linhas.map(([rotulo, funcao]) =>
        '<tr><th scope="row">' + escapar(rotulo) + '</th>' +
        acoes.map((a) => '<td>' + (a.disponivel ? funcao(a) : '—') + '</td>').join('') + '</tr>'
      ).join('') + '</tbody></table>';
  }

  async function carregarAcoes() {
    $('ac-cards').setAttribute('aria-busy', 'true');
    $('ac-cards').innerHTML = esqueletoCards();
    const resultado = await api('/api/acoes?periodo=' + encodeURIComponent(periodoAtual));
    if (resultado.erro) {
      if (resultado.erro !== 'sessão expirada' && resultado.erro !== 'precisa trocar senha') {
        mostrarAvisoGlobal('Não foi possível carregar as ações', resultado.erro);
      }
      return;
    }
    esconderAvisoGlobal();
    $('acoes-atualizado').textContent = 'Atualizado às ' + resultado.atualizadoEm + ' · atualiza automaticamente a cada 15 minutos.';
    $('ac-baixar-csv').href = '/api/acoes/csv?periodo=' + encodeURIComponent(periodoAtual);
    renderCardsAcoes(resultado.acoes);
    renderGraficoAcoes(resultado.acoes);
    renderIndicadoresAcoes(resultado.acoes);
  }

  // ============================================================ CARTEIRA
  function renderListaCarteira(tickers) {
    const container = $('lista-carteira');
    container.removeAttribute('aria-busy');
    if (!tickers.length) {
      container.innerHTML = '<p class="lista-carteira__vazio">Sua carteira está vazia. Adicione uma ação acima.</p>';
      return;
    }
    container.innerHTML = tickers.map((t) =>
      '<div class="lista-carteira__item"><strong>' + escapar(t) + '</strong>' +
      '<button type="button" class="botao botao--perigo botao--pequeno" data-remover="' + escapar(t) + '">Remover</button></div>'
    ).join('');
    container.querySelectorAll('[data-remover]').forEach((botao) => {
      botao.addEventListener('click', async () => {
        botao.disabled = true;
        const resultado = await api('/api/carteira/' + encodeURIComponent(botao.dataset.remover), { method: 'DELETE' });
        if (resultado.erro) { exibirAvisoInline($('aviso-carteira'), resultado.erro); botao.disabled = false; return; }
        carregarCarteira();
      });
    });
  }

  async function carregarCarteira() {
    $('lista-carteira').setAttribute('aria-busy', 'true');
    const resultado = await api('/api/carteira');
    if (resultado.erro) return;
    renderListaCarteira(resultado.tickers);
  }

  // ============================================================== CONTA
  async function carregarConta() {
    const resultado = await api('/api/me');
    if (resultado.erro) return;
    const u = resultado.usuario;
    $('conta-resumo').innerHTML = '<strong>' + escapar(u.nomeCompleto) + '</strong> · usuário <strong>' + escapar(u.usuario) +
      '</strong> · ' + escapar(u.email) + ' · <span class="tipo-selo ' + (u.tipo === 'admin' ? 'tipo-selo--admin' : '') + '">' +
      (u.tipo === 'admin' ? 'Administrador' : 'Usuário comum') + '</span>';
  }

  // ========================================================= ADMINISTRAÇÃO
  function mostrarSenhaGerada(senha, texto) {
    const el = $('senha-gerada-criar');
    el.hidden = false;
    el.innerHTML = '<div class="cartao-senha-temp"><p>' + escapar(texto) + '</p><code>' + escapar(senha) + '</code></div>';
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function renderTabelaAdmin(usuarios) {
    const container = $('tabela-admin');
    container.removeAttribute('aria-busy');
    const linhas = usuarios.map((u) => {
      const souEu = usuarioAtual && u.id === usuarioAtual.id;
      const botoes = [];
      if (u.tipo === 'comum') {
        botoes.push('<button type="button" class="botao botao--linha botao--pequeno" data-acao="promover" data-id="' + u.id + '">Promover a admin</button>');
      } else {
        botoes.push('<button type="button" class="botao botao--linha botao--pequeno" data-acao="rebaixar" data-id="' + u.id + '">Rebaixar a comum</button>');
      }
      botoes.push('<button type="button" class="botao botao--linha botao--pequeno" data-acao="redefinir" data-id="' + u.id + '">Redefinir senha</button>');
      if (!souEu) {
        botoes.push('<button type="button" class="botao botao--perigo botao--pequeno" data-acao="excluir" data-id="' + u.id + '">Excluir</button>');
      }
      return '<tr><td>' + escapar(u.nomeCompleto) + (souEu ? ' <span class="etiqueta">você</span>' : '') + '</td>' +
        '<td>' + escapar(u.usuario) + '</td><td>' + escapar(u.email) + '</td>' +
        '<td><span class="tipo-selo ' + (u.tipo === 'admin' ? 'tipo-selo--admin' : '') + '">' + (u.tipo === 'admin' ? 'Administrador' : 'Comum') + '</span></td>' +
        '<td><div class="acoes-linha">' + botoes.join('') + '</div></td></tr>';
    }).join('');
    container.innerHTML = '<table class="tabela-admin"><thead><tr><th scope="col">Nome</th><th scope="col">Usuário</th>' +
      '<th scope="col">E-mail</th><th scope="col">Tipo</th><th scope="col"></th></tr></thead><tbody>' + linhas + '</tbody></table>';
    container.querySelectorAll('[data-acao]').forEach((botao) => {
      botao.addEventListener('click', () => tratarAcaoAdmin(botao.dataset.acao, Number(botao.dataset.id), botao));
    });
  }

  async function tratarAcaoAdmin(acao, id, botao) {
    const confirmacoes = {
      excluir: 'Tem certeza que quer excluir este usuário? Essa ação não pode ser desfeita.',
      rebaixar: 'Tem certeza que quer tirar os poderes de administrador desse usuário?',
    };
    if (confirmacoes[acao] && !window.confirm(confirmacoes[acao])) return;
    botao.disabled = true;
    const resultado = acao === 'excluir'
      ? await api('/api/admin/usuarios/' + id, { method: 'DELETE' })
      : await api('/api/admin/usuarios/' + id + '/' + acao, { method: 'POST' });
    botao.disabled = false;
    if (resultado.erro) { window.alert(resultado.erro); return; }
    if (acao === 'redefinir') {
      mostrarSenhaGerada(resultado.senhaTemporaria, 'Nova senha temporária gerada. Passe para a pessoa — ela só aparece aqui uma vez:');
    }
    carregarAdmin();
  }

  async function carregarAdmin() {
    $('tabela-admin').setAttribute('aria-busy', 'true');
    const resultado = await api('/api/admin/usuarios');
    if (resultado.erro) return;
    renderTabelaAdmin(resultado.usuarios);
  }

  // =============================================================== EVENTOS
  function configurarEventos() {
    document.querySelectorAll('.menu__item').forEach((botao) => {
      botao.addEventListener('click', () => irParaPagina(botao.dataset.pagina));
    });

    $('botao-sair').addEventListener('click', async () => {
      await api('/api/logout', { method: 'POST' });
      window.location.href = '/login';
    });

    $('form-troca-obrigatoria').addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const aviso = $('aviso-troca-obrigatoria');
      const dados = new FormData(evento.target);
      const senhaNova = dados.get('senhaNova');
      if (senhaNova !== dados.get('senhaNovaConfirma')) { exibirAvisoInline(aviso, 'As duas senhas novas não são iguais.'); return; }
      const resultado = await api('/api/conta/senha', { method: 'POST', body: JSON.stringify({ senhaAtual: dados.get('senhaAtual'), senhaNova }) });
      if (resultado.erro) { exibirAvisoInline(aviso, resultado.erro); return; }
      aviso.hidden = true;
      evento.target.reset();
      liberarNavegacao();
      irParaPagina('acoes');
    });

    $('form-add-carteira').addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const aviso = $('aviso-carteira');
      aviso.hidden = true;
      const dados = new FormData(evento.target);
      const ticker = String(dados.get('ticker') || '').trim().toUpperCase();
      const botao = evento.target.querySelector('button[type=submit]');
      botao.disabled = true;
      botao.textContent = 'Verificando…';
      const resultado = await api('/api/carteira', { method: 'POST', body: JSON.stringify({ ticker }) });
      botao.disabled = false;
      botao.textContent = 'Adicionar';
      if (resultado.erro) { exibirAvisoInline(aviso, resultado.erro); return; }
      evento.target.reset();
      carregarCarteira();
      if (paginaAtual === 'acoes') carregarAcoes();
    });

    $('form-troca-senha').addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const aviso = $('aviso-conta');
      const dados = new FormData(evento.target);
      const senhaNova = dados.get('senhaNova');
      if (senhaNova !== dados.get('senhaNovaConfirma')) { exibirAvisoInline(aviso, 'As duas senhas novas não são iguais.'); return; }
      const resultado = await api('/api/conta/senha', { method: 'POST', body: JSON.stringify({ senhaAtual: dados.get('senhaAtual'), senhaNova }) });
      if (resultado.erro) { exibirAvisoInline(aviso, resultado.erro); return; }
      evento.target.reset();
      exibirAvisoInline(aviso, 'Senha alterada com sucesso.', true);
    });

    $('form-criar-usuario').addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const aviso = $('aviso-criar-usuario');
      aviso.hidden = true;
      $('senha-gerada-criar').hidden = true;
      const dados = new FormData(evento.target);
      const corpo = { nomeCompleto: dados.get('nomeCompleto'), usuario: dados.get('usuario'), email: dados.get('email') };
      const resultado = await api('/api/admin/usuarios', { method: 'POST', body: JSON.stringify(corpo) });
      if (resultado.erro) { exibirAvisoInline(aviso, resultado.erro); return; }
      evento.target.reset();
      mostrarSenhaGerada(resultado.senhaTemporaria, 'Usuário "' + corpo.usuario + '" criado. Senha temporária (passe para a pessoa, só aparece aqui uma vez):');
      carregarAdmin();
    });

    // atualiza a página de Ações sozinha a cada 15 minutos
    setInterval(() => { if (paginaAtual === 'acoes') carregarAcoes(); }, 15 * 60 * 1000);
  }

  // ================================================================ INÍCIO
  async function iniciar() {
    montarBotoesPeriodo();
    configurarEventos();
    const resultado = await api('/api/me');
    if (resultado.erro) return; // api() já redireciona para /login se for o caso
    aplicarUsuario(resultado.usuario);
    if (resultado.usuario.senhaTemporaria) {
      ativarBloqueioSenha();
    } else {
      liberarNavegacao();
      irParaPagina('acoes');
    }
  }

  iniciar().catch((erro) => {
    console.error(erro);
    mostrarAvisoGlobal('Algo deu errado ao montar o painel', 'Tente recarregar a página (F5).');
  });
})();
