// settings.js
// ===========
// Tela de Configurações: informações da conta (email, data de criação),
// alteração de senha, exportação dos dados da conta (LGPD) e o botão
// "Excluir Conta" (o resto da página - troca de tema - já é cuidado
// por js/theme.js em toda página).

document.addEventListener("DOMContentLoaded", function () {
  wireDeleteAccountButton();
  loadAccountInfo();
  wirePasswordForm();
  wireExportDataButton();
  wireSectionNav();
});

// Realça no menu a seção que está na tela (scroll-spy simples).
function wireSectionNav() {
  var links = document.querySelectorAll(".settings-nav a");
  if (!links.length || !("IntersectionObserver" in window)) return;
  var byId = {};
  links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      links.forEach(function (a) { a.classList.remove("active"); });
      byId[entry.target.id].classList.add("active");
    });
  }, { rootMargin: "-20% 0px -65% 0px" });
  Object.keys(byId).forEach(function (id) {
    var section = document.getElementById(id);
    if (section) observer.observe(section);
  });
}

function wireDeleteAccountButton() {
  var deleteBtn = document.getElementById("delete-account-btn");
  if (!deleteBtn) return;

  deleteBtn.addEventListener("click", function () {
    var accountPassword = "";
    var confirmation = "";
    var requiredPhrase = "eu quero excluir essa conta";

    function showFinalConfirmation() {
      showConfirmModal({
        title: "Tem certeza que quer excluir essa conta?",
        message: "Essa ação não pode ser desfeita. Sua conta e todas as conversas serão apagadas.",
        confirmText: "Excluir definitivamente",
        confirmLoadingText: "Excluindo...",
        danger: true,
        onClose: function () { accountPassword = ""; confirmation = ""; },
        onConfirm: function () {
          return apiFetch("/api/account/delete", {
            method: "POST",
            body: { password: accountPassword, confirmation: confirmation },
          }).then(function () {
            accountPassword = "";
            emitTT("logout");
            window.location.href = "/";
          }).catch(function (err) {
            throw new Error(err.message + " Para corrigir os dados, cancele e inicie a exclusão novamente.");
          });
        },
      });
    }

    function showPhraseConfirmation() {
      showConfirmModal({
        title: "Confirme a frase — etapa 2 de 3",
        message: 'Digite exatamente: "' + requiredPhrase + '"',
        inputValue: "",
        confirmText: "Continuar",
        onConfirm: function (value) {
          if (value !== requiredPhrase) return Promise.reject(new Error("Digite a frase exatamente como indicada."));
          confirmation = value;
        },
        onClose: function () {
          if (confirmation) showFinalConfirmation();
          else accountPassword = "";
        },
      });
    }

    showConfirmModal({
      title: "Excluir conta — etapa 1 de 3",
      message:
        "Essa ação não pode ser desfeita e todas as suas conversas serão " +
        "apagadas. Digite sua senha para confirmar.",
      confirmText: "Continuar",
      danger: true,
      password: true,
      onConfirm: function (password) {
        accountPassword = password;
      },
      onClose: function () {
        if (accountPassword) showPhraseConfirmation();
      },
    });
  });
}

// Preenche email + data de criação com os mesmos dados de GET
// /api/dashboard que js/layout.js já busca para montar a sidebar -
// getDashboard() (js/api.js) reaproveita essa requisição em vez de
// fazer outra.
async function loadAccountInfo() {
  var emailEl = document.getElementById("account-info-email");
  var createdAtEl = document.getElementById("account-info-created-at");
  if (!emailEl || !createdAtEl) return;

  var data;
  try {
    data = await getDashboard();
  } catch (_err) {
    // Sessão inválida: js/layout.js (carregado nesta mesma página) já
    // cuida do redirecionamento para /login.
    return;
  }

  emailEl.textContent = data.user.email;
  createdAtEl.textContent = data.user.created_at
    ? new Date(data.user.created_at).toLocaleDateString("pt-BR")
    : "—";
}

function wirePasswordForm() {
  var form = document.getElementById("password-form");
  if (!form) return;

  var newInput = document.getElementById("new-password");
  var confirmInput = document.getElementById("confirm-new-password");
  var errorBanner = document.getElementById("password-error");
  var successBanner = document.getElementById("password-success");

  // wirePasswordRequirements/passwordRequirementsErrorMessage vêm de
  // js/auth.js (carregado antes deste script - ver settings.html) e são
  // a mesma checklist usada no cadastro e na redefinição de senha.
  wirePasswordRequirements(
    newInput,
    document.getElementById("new-password-requirements"),
  );

  // Mesma ideia de js/auth.js (wirePasswordConfirmValidation), só que
  // inline: aquela função é fixa nos ids "password"/"confirm-password"
  // das páginas públicas de auth, e generalizá-la não valeria a pena
  // por essas poucas linhas de lógica duplicada.
  confirmInput.addEventListener("input", function () {
    confirmInput.setCustomValidity(
      newInput.value !== confirmInput.value ? "As senhas não coincidem" : "",
    );
  });

  // O formulário fica recolhido; abre/fecha animando a altura (ver .collapse).
  var toggleBtn = document.getElementById("password-toggle");
  var collapse = document.getElementById("password-collapse");
  function setPasswordOpen(open) {
    collapse.classList.toggle("open", open);
    toggleBtn.setAttribute("aria-expanded", String(open));
    toggleBtn.hidden = open;
    // inert tira os campos recolhidos da ordem de tabulação.
    collapse.inert = !open;
    if (open) document.getElementById("current-password").focus();
    else toggleBtn.focus();
  }
  collapse.inert = true;
  toggleBtn.addEventListener("click", function () { setPasswordOpen(true); });
  document.getElementById("password-cancel").addEventListener("click", function () {
    form.reset();
    errorBanner.hidden = true;
    setPasswordOpen(false);
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    errorBanner.hidden = true;
    successBanner.hidden = true;
    var submitBtn = form.querySelector("button[type=submit]");

    var passwordError = passwordRequirementsErrorMessage(newInput.value);
    if (passwordError) {
      errorBanner.textContent = passwordError;
      errorBanner.hidden = false;
      return;
    }

    withLoadingState(submitBtn, "Salvando...", function () {
      return apiFetch("/api/account/password", {
        method: "POST",
        body: {
          currentPassword: document.getElementById("current-password").value,
          newPassword: newInput.value,
        },
      });
    })
      .then(function () {
        form.reset();
        successBanner.hidden = false;
        setPasswordOpen(false);
      })
      .catch(function (err) {
        errorBanner.textContent = err.message;
        errorBanner.hidden = false;
      });
  });
}

// Busca o JSON de exportação via apiFetch (mesmo tratamento de
// erro/loading-state do resto do app) e dispara o download na mão:
// Blob + link temporário com atributo download. Primeiro download de
// arquivo do app - não existia nenhum padrão pra reaproveitar.
function wireExportDataButton() {
  var exportBtn = document.getElementById("export-data-btn");
  if (!exportBtn) return;

  exportBtn.addEventListener("click", function () {
    withLoadingState(exportBtn, "Exportando...", function () {
      return apiFetch("/api/account/export");
    })
      .then(function (data) {
        var blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = "trash-talker-dados.json";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      })
      .catch(function (err) {
        showUIMessage(err.message, document.getElementById("export-data-btn").closest(".card"));
      });
  });
}
