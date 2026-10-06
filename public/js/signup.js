// signup.js
// =========
// Equivalente, para a tela de cadastro, ao que login.js faz para a tela
// de login. Intercepta o envio do formulário e chama POST /api/signup.
//
// Igual ao original: cadastro NÃO loga o usuário automaticamente - ele
// é enviado para /login para entrar com a conta recém-criada
// (ver src/routes/auth-forms.ts, authFormsRouter.post("/signup", ...)).

document.addEventListener("DOMContentLoaded", function () {
  var form = document.querySelector(".auth-form");
  var errorBox = document.getElementById("signup-error");
  if (!form) return;
  var consents = renderConsentChecks(document.getElementById("signup-consents"));

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var email = document.getElementById("email").value;
    var name = document.getElementById("name").value;
    var password = document.getElementById("password").value;
    var confirmPassword = document.getElementById("confirm-password").value;
    var button = form.querySelector("button[type=submit]");
    errorBox.hidden = true;

    // getUnmetPasswordRules/passwordRequirementsErrorMessage vêm de
    // js/auth.js (carregado antes deste script - ver signup.html).
    var passwordError = passwordRequirementsErrorMessage(password);
    if (passwordError) {
      errorBox.textContent = passwordError;
      errorBox.hidden = false;
      return;
    }

    if (password !== confirmPassword) {
      errorBox.textContent = "As senhas não coincidem";
      errorBox.hidden = false;
      return;
    }

    if (!consents.accepted()) {
      errorBox.textContent = "Para criar a conta, marque as duas confirmações.";
      errorBox.hidden = false;
      (consents.terms.checked ? consents.ai : consents.terms).focus();
      return;
    }

    withLoadingState(button, "Criando conta...", function () {
      return apiFetch("/api/signup", {
        method: "POST",
        body: Object.assign({ email: email, name: name, password: password }, consents.body()),
      });
    })
      .then(function () {
        window.location.href = "/login";
      })
      .catch(function (err) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      });
  });
});
