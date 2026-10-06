// landing.js
// ==========
// A landing page ("/") agora é a mesma tanto para visitantes quanto
// para quem já tem sessão ativa - antes, um usuário logado era
// redirecionado automaticamente para /dashboard ao abrir "/"; agora ele
// só vê a nav e o CTA do hero mudarem de "Entrar / Criar Conta /
// Começar a conversar" para "Ir para o Dashboard / Ir para o Chat".
//
// O HTML já nasce no estado "deslogado" (ver index.html) - isso evita
// qualquer flash quebrado para o caso mais comum (visitante sem conta)
// e significa que, se este script falhar ou demorar, a página continua
// inteiramente utilizável. Assim que GET /api/me confirma a sessão,
// trocamos para o estado "logado" - mesmo tipo de flash que já existe
// hoje no nome/avatar da sidebar do dashboard (ver layout.js).

document.addEventListener("DOMContentLoaded", function () {
  apiFetch("/api/me")
    .then(function () {
      showLoggedInState();
    })
    .catch(function () {
      // Sem sessão (401) ou erro de rede: mantém o estado deslogado que
      // já está no HTML por padrão.
    });
});

function showLoggedInState() {
  document
    .querySelectorAll("[data-nav-guest], [data-hero-guest]")
    .forEach(function (el) {
      el.hidden = true;
    });
  document
    .querySelectorAll("[data-nav-user], [data-hero-user]")
    .forEach(function (el) {
      el.hidden = false;
    });
}
