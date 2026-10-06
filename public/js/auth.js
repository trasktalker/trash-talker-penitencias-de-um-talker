// auth.js
// =======
// Comportamentos de autenticação usados em várias páginas públicas:
//   1. Validação "as senhas coincidem" nos campos de confirmação de
//      senha (signup e reset-password).
//   2. Envio do formulário de "esqueci minha senha".
//   3. Envio do formulário de "redefinir senha".
//
// No original, os itens 2 e 3 chamavam a API do Better Auth diretamente
// do navegador (fetch("/api/auth/forget-password"), etc). Agora eles
// chamam os endpoints equivalentes do nosso backend Python
// (/api/forgot-password e /api/reset-password) - ver
// backend/routes/auth_api.py.

document.addEventListener("DOMContentLoaded", function () {
  wirePasswordConfirmValidation();
  wireForgotPasswordForm();
  wireResetPasswordForm();
  wirePasswordRequirements(
    document.getElementById("password"),
    document.getElementById("password-requirements"),
  );
});

// Política de senha forte, espelhando get_password_requirement_failures()
// em backend/auth.py - a validação de verdade é sempre a do backend, isto
// aqui só existe para dar feedback imediato (checklist ao digitar) e
// evitar uma ida ao servidor com uma senha que já sabemos que vai falhar.
// Usado nesta página (cadastro e redefinição, ambas com id="password") e,
// via wirePasswordRequirements/passwordRequirementsErrorMessage, também
// em js/settings.js (troca de senha estando logado).
var PASSWORD_RULES = [
  {
    id: "length",
    label: "Mínimo de 8 caracteres",
    test: function (p) {
      return p.length >= 8;
    },
  },
  {
    id: "upper",
    label: "Uma letra maiúscula",
    test: function (p) {
      return /[A-Z]/.test(p);
    },
  },
  {
    id: "lower",
    label: "Uma letra minúscula",
    test: function (p) {
      return /[a-z]/.test(p);
    },
  },
  {
    id: "digit",
    label: "Um número",
    test: function (p) {
      return /[0-9]/.test(p);
    },
  },
  {
    id: "special",
    label: "Um caractere especial (ex.: !@#$%^&*)",
    test: function (p) {
      return /[^A-Za-z0-9]/.test(p);
    },
  },
];

function getUnmetPasswordRules(password) {
  password = password || "";
  return PASSWORD_RULES.filter(function (rule) {
    return !rule.test(password);
  });
}

/** Devolve null se `password` atende a todas as regras, ou uma mensagem
 * com uma regra não cumprida por linha (mesmo formato usado pelo
 * backend em respostas de erro). */
function passwordRequirementsErrorMessage(password) {
  var unmet = getUnmetPasswordRules(password);
  if (unmet.length === 0) return null;
  return unmet
    .map(function (rule) {
      return rule.label;
    })
    .join("\n");
}

/** Monta a checklist de requisitos dentro de `list` (uma vez), mostra
 * somente durante o foco e atualiza a cada tecla. Não faz nada se um dos
 * dois elementos não existir na página (ex.: login.html tem #password,
 * mas nenhuma checklist). */
function wirePasswordRequirements(input, list) {
  if (!input || !list) return;
  list.hidden = document.activeElement !== input;
  var descriptions = (input.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
  if (list.id && descriptions.indexOf(list.id) === -1) descriptions.push(list.id);
  input.setAttribute("aria-describedby", descriptions.join(" "));

  PASSWORD_RULES.forEach(function (rule) {
    var item = document.createElement("li");
    item.dataset.rule = rule.id;
    item.textContent = rule.label;
    list.appendChild(item);
  });

  function atualizar() {
    var unmet = getUnmetPasswordRules(input.value).map(function (rule) {
      return rule.id;
    });
    Array.prototype.forEach.call(list.children, function (item) {
      item.classList.toggle("met", unmet.indexOf(item.dataset.rule) === -1);
    });
  }

  input.addEventListener("input", atualizar);
  input.addEventListener("focus", function () {
    atualizar();
    list.hidden = false;
  });
  input.addEventListener("blur", function () {
    list.hidden = true;
  });
  if (input.form) {
    input.form.addEventListener("reset", function () {
      // O evento precede a restauração dos valores pelo navegador.
      queueMicrotask(atualizar);
    });
  }
  atualizar();
}

function wirePasswordConfirmValidation() {
  var pass = document.getElementById("password");
  var confirmPass = document.getElementById("confirm-password");
  if (!pass || !confirmPass) return;

  confirmPass.addEventListener("input", function () {
    confirmPass.setCustomValidity(
      pass.value !== confirmPass.value ? "As senhas não coincidem" : "",
    );
  });
}

function wireForgotPasswordForm() {
  var form = document.getElementById("forgot-password-form");
  if (!form) return;

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var email = document.getElementById("email").value;
    var errorBox = document.getElementById("forgot-error");
    var successBox = document.getElementById("forgot-success");
    var button = form.querySelector("button[type=submit]");
    errorBox.hidden = true;

    withLoadingState(button, "Enviando...", function () {
      return apiFetch("/api/forgot-password", {
        method: "POST",
        body: { email: email },
      });
    })
      .then(function () {
        form.hidden = true;
        successBox.hidden = false;
      })
      .catch(function (err) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      });
  });
}

function wireResetPasswordForm() {
  var form = document.getElementById("reset-password-form");
  var invalidLinkBox = document.getElementById("reset-invalid-link");
  if (!form) return;

  // O token vem na URL (?token=...), igual ao original
  // (pagesRouter.get("/reset-password", ...) lia req.query.token). Sem
  // servidor renderizando a página, é o próprio JS que decide se mostra
  // o formulário ou o aviso de link inválido.
  var token = new URLSearchParams(window.location.search).get("token");
  if (!token) {
    form.hidden = true;
    if (invalidLinkBox) invalidLinkBox.hidden = false;
    return;
  }
  form.dataset.token = token;
  form.hidden = false;

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var token = form.dataset.token;
    var newPassword = document.getElementById("password").value;
    var errorBox = document.getElementById("reset-error");
    var button = form.querySelector("button[type=submit]");
    errorBox.hidden = true;

    var passwordError = passwordRequirementsErrorMessage(newPassword);
    if (passwordError) {
      errorBox.textContent = passwordError;
      errorBox.hidden = false;
      return;
    }

    withLoadingState(button, "Salvando...", function () {
      return apiFetch("/api/reset-password", {
        method: "POST",
        body: { newPassword: newPassword, token: token },
      });
    })
      .then(function () {
        window.location.href = "/login?reset=success";
      })
      .catch(function (err) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      });
  });
}

// As duas confirmações obrigatórias, iguais no cadastro (signup.js) e na
// janela de novo aceite das contas antigas (layout.js). Fonte única do
// texto - o backend confere os mesmos dois campos (has_required_consents
// em backend/auth.py). Começam DESMARCADAS: aceite tem de ser um ato da
// pessoa, nunca algo que ela precise desmarcar.
// Devolve { terms, ai } (os checkboxes) e o objeto pronto pra API em body().
function renderConsentChecks(host) {
  var wrap = document.createElement("div");
  wrap.className = "consent-checks";

  function link(href, text) {
    var a = document.createElement("a");
    a.href = href; a.target = "_blank"; a.rel = "noopener"; a.textContent = text;
    return a;
  }
  function check(id, parts) {
    var label = document.createElement("label");
    label.className = "consent-check";
    label.htmlFor = id;
    var input = document.createElement("input");
    input.type = "checkbox"; input.id = id; input.required = true;
    var text = document.createElement("span");
    parts.forEach(function (part) {
      text.append(typeof part === "string" ? document.createTextNode(part) : part);
    });
    label.append(input, text);
    wrap.appendChild(label);
    return input;
  }

  var strong18 = document.createElement("strong"); strong18.textContent = "18 anos ou mais";
  var terms = check("consent-terms", [
    "Tenho ", strong18, " e li e aceito os ", link("/terms", "Termos de Uso"),
    " e a ", link("/privacy", "Política de Privacidade"), ".",
  ]);
  var strongAi = document.createElement("strong"); strongAi.textContent = "Google Gemini";
  var ai = check("consent-ai", [
    "Entendo que minhas mensagens são enviadas ao ", strongAi,
    " para gerar as respostas, inclusive se eu falar de sentimentos ou saúde. " +
    "No plano atual, o Google pode usá-las para melhorar seus produtos (",
    link("/privacy#ia", "saiba mais"), ").",
  ]);

  host.appendChild(wrap);
  return {
    terms: terms,
    ai: ai,
    accepted: function () { return terms.checked && ai.checked; },
    body: function () { return { acceptTerms: terms.checked, acceptAi: ai.checked }; },
  };
}
