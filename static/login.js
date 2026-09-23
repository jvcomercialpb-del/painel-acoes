/* Tela de login: envia usuário e senha para /api/login e, se der certo, entra no app. */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);

  function mostrarErro(mensagem) {
    $('aviso-login-texto').textContent = mensagem;
    $('aviso-login').hidden = false;
  }

  $('form-login').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    $('aviso-login').hidden = true;
    const botao = $('botao-entrar');
    const dados = new FormData(evento.target);
    const usuario = String(dados.get('usuario') || '').trim();
    const senha = String(dados.get('senha') || '');

    botao.disabled = true;
    botao.textContent = 'Entrando…';
    try {
      const resposta = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usuario, senha }),
      });
      const corpo = await resposta.json().catch(() => ({}));
      if (!resposta.ok || !corpo.ok) {
        mostrarErro(corpo.erro || 'Não foi possível entrar. Tente de novo.');
        return;
      }
      window.location.href = '/';
    } catch (erro) {
      console.error(erro);
      mostrarErro('Não conseguimos falar com o app agora. Confira se a janela preta do app ainda está aberta e tente de novo.');
    } finally {
      botao.disabled = false;
      botao.textContent = 'Entrar';
    }
  });
})();
