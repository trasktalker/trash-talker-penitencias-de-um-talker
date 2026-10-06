// login.js
// ========
// No projeto original, o formulário de login era um <form method="post">
// de verdade, enviado para a rota Express POST /login, que renderizava a
// página de novo com uma mensagem de erro (ou redirecionava para
// /dashboard em caso de sucesso) - ver src/routes/auth-forms.ts.
//
// Como agora o frontend é HTML estático, o próprio JavaScript intercepta
// o envio do formulário, chama a API e decide o que fazer com o
// resultado.

document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("login-form");
  var errorBox = document.getElementById("login-error");
  if (!form) return;
  var factorForm = document.getElementById("login-2fa-form");
  var codeInput = document.getElementById("login-2fa-code");
  var factorError = document.getElementById("login-2fa-error");
  var challenge = null;
  var expiryTimer = null;
  var recoveryMode = false;
  var verifying = false;

  function resetLogin(message) {
    challenge = null;
    clearTimeout(expiryTimer);
    factorForm.hidden = true;
    factorForm.reset();
    form.hidden = false;
    document.getElementById("password").value = "";
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
    document.getElementById("password").focus();
  }

  function setRecoveryMode(value) {
    recoveryMode = value;
    codeInput.value = "";
    codeInput.inputMode = value ? "text" : "numeric";
    codeInput.maxLength = value ? 64 : 6;
    codeInput.minLength = value ? 32 : 6;
    if (value) codeInput.removeAttribute("pattern");
    else codeInput.pattern = "[0-9]{6}";
    document.getElementById("login-2fa-label").textContent = value ? "Código de recuperação" : "Código do autenticador";
    document.getElementById("login-2fa-help").textContent = value
      ? "Use um dos códigos salvos na ativação. Cada código só funciona uma vez."
      : "Digite o código de 6 dígitos do Google Authenticator.";
    document.getElementById("login-use-recovery").textContent = value ? "Usar Google Authenticator" : "Usar código de recuperação";
    factorError.hidden = true;
    codeInput.focus();
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var email = document.getElementById("email").value;
    var password = document.getElementById("password").value;
    var button = form.querySelector("button[type=submit]");
    errorBox.hidden = true;

    withLoadingState(button, "Entrando...", function () {
      return apiFetch("/api/login", {
        method: "POST",
        body: { email: email, password: password },
      });
    })
      .then(function (data) {
        if (data.twoFactorRequired) {
          challenge = data.challengeToken;
          document.getElementById("password").value = "";
          form.hidden = true;
          factorForm.hidden = false;
          setRecoveryMode(false);
          clearTimeout(expiryTimer);
          expiryTimer = setTimeout(function () {
            if (!verifying) resetLogin("Verificação expirada. Entre novamente com sua senha.");
          }, data.expiresIn * 1000);
          return;
        }
        window.location.href = "/dashboard";
      })
      .catch(function (err) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      });
  });

  document.getElementById("login-2fa-back").addEventListener("click", function () {
    if (!verifying) resetLogin();
  });
  document.getElementById("login-use-recovery").addEventListener("click", function () {
    if (!verifying) setRecoveryMode(!recoveryMode);
  });
  factorForm.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!challenge || verifying) return;
    verifying = true;
    factorError.hidden = true;
    withLoadingState(factorForm.querySelector("button[type=submit]"), "Verificando...", function () {
      return apiFetch("/api/login/2fa", {
        method: "POST", body: { challengeToken: challenge, code: codeInput.value.trim() },
      });
    }).then(function () {
      challenge = null;
      clearTimeout(expiryTimer);
      window.location.href = "/dashboard";
    }).catch(function (err) {
      codeInput.value = "";
      if (err.data && err.data.code === "challenge_expired") resetLogin(err.message);
      else {
        factorError.textContent = err.message;
        factorError.hidden = false;
        codeInput.focus();
      }
    }).finally(function () { verifying = false; });
  });
  // Credenciais temporárias nunca são persistidas no armazenamento do navegador.
  window.addEventListener("pagehide", function () {
    challenge = null;
    clearTimeout(expiryTimer);
    form.reset();
    factorForm.reset();
  });
  window.addEventListener("pageshow", function (event) { if (event.persisted) resetLogin(); });
});
