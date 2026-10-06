// modal.js
// ========
// Popup de confirmação reutilizável - substitui confirm()/prompt()/
// alert() nativos do navegador para ações destrutivas. Usado por
// deleteChat() (layout.js) e wireDeleteAccountButton() (settings.js).
//
// Não existe markup fixo em nenhum HTML: showConfirmModal() monta o
// popup inteiro via JS e remove do DOM ao fechar, então basta incluir
// este arquivo (como qualquer outro script compartilhado) pra usar.

/**
 * @param {object} options
 * @param {string} options.title
 * @param {string} options.message
 * @param {string} [options.confirmText="Confirmar"]
 * @param {string} [options.cancelText="Cancelar"]
 * @param {string} [options.confirmLoadingText="Aguarde..."]
 * @param {boolean} [options.danger] - estiliza o botão de confirmar como destrutivo
 * @param {boolean} [options.password] - adiciona um campo de senha ao popup
 * @param {string} [options.inputValue] - texto inicial para renomear uma conversa
 * @param {(password?: string) => Promise<any>} [options.onConfirm] - chamado
 *   ao confirmar; se devolver uma Promise, o botão mostra estado de
 *   carregando e um erro rejeitado aparece dentro do próprio popup
 *   (nunca um alert()). O popup só fecha se a Promise resolver.
 */
function showConfirmModal(options) {
  options = options || {};
  var previousFocus = document.activeElement;
  var busy = false;
  var background = Array.from(document.body.children).map(function (el) {
    return { el: el, inert: el.inert };
  });

  var overlay = document.createElement("div");
  overlay.className = "modal-overlay";

  var modal = document.createElement("div");
  modal.className = "modal";
  modal.setAttribute("role", options.danger ? "alertdialog" : "dialog");
  modal.tabIndex = -1;
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", "modal-title");
  overlay.appendChild(modal);

  var titleEl = document.createElement("h2");
  titleEl.id = "modal-title";
  titleEl.textContent = options.title || "";
  modal.appendChild(titleEl);

  var messageEl = document.createElement("p");
  messageEl.className = "modal-message";
  messageEl.id = "modal-description";
  messageEl.textContent = options.message || "";
  messageEl.hidden = !options.message;
  if (options.message) modal.setAttribute("aria-describedby", messageEl.id);
  modal.appendChild(messageEl);

  var passwordInput = null;
  if (options.password || options.inputValue !== undefined) {
    passwordInput = document.createElement("input");
    passwordInput.type = options.password ? "password" : "text";
    passwordInput.className = "modal-input";
    passwordInput.placeholder = options.password ? "Senha" : "";
    passwordInput.autocomplete = options.password ? "current-password" : "off";
    passwordInput.setAttribute("aria-label", options.password ? "Senha" : options.title);
    if (!options.password) passwordInput.value = options.inputValue;
    modal.appendChild(passwordInput);
    if (options.password && typeof wirePasswordVisibility === "function") {
      wirePasswordVisibility(modal);
    }
  }

  if (options.renderContent) options.renderContent(modal);
  var errorEl = document.createElement("p");
  errorEl.className = "modal-error";
  errorEl.hidden = true;
  errorEl.setAttribute("role", "alert");
  modal.appendChild(errorEl);

  var actions = document.createElement("div");
  actions.className = "modal-actions";
  modal.appendChild(actions);

  var cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "btn-outline";
  cancelBtn.textContent = options.cancelText || "Cancelar";
  actions.appendChild(cancelBtn);

  var confirmBtn = document.createElement("button");
  confirmBtn.type = "button";
  confirmBtn.className = options.danger ? "btn-destructive" : "btn-primary";
  confirmBtn.textContent = options.confirmText || "Confirmar";
  actions.appendChild(confirmBtn);

  document.body.appendChild(overlay);
  background.forEach(function (entry) { entry.el.inert = true; });

  // A classe que dispara a transição de entrada só é aplicada depois
  // de o navegador pintar o estado inicial (dois rAF em sequência) -
  // aplicá-la no mesmo frame do append faria a transição não rodar.
  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      if (!closed) overlay.classList.add("modal-open");
    });
  });

  var closed = false;
  function close() {
    if (closed || busy) return;
    closed = true;
    document.removeEventListener("keydown", onKeydown);
    overlay.classList.remove("modal-open");
    overlay.inert = true;
    background.forEach(function (entry) { entry.el.inert = entry.inert; });
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
    setTimeout(function () {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (options.onClose) options.onClose();
    }, 160);
  }

  function onKeydown(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    if (e.key === "Tab") {
      var items = Array.from(modal.querySelectorAll('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href]'));
      items = items.filter(function (el) { return el.getClientRects().length; });
      var first = items[0], last = items[items.length - 1];
      if (!first) { e.preventDefault(); modal.focus(); }
      else if (e.shiftKey && (document.activeElement === first || document.activeElement === modal)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) close();
  });
  document.addEventListener("keydown", onKeydown);
  cancelBtn.addEventListener("click", close);

  function handleConfirm() {
    if (busy || closed) return;
    errorEl.hidden = true;

    if (options.password && !passwordInput.value) {
      errorEl.textContent = "Digite sua senha para confirmar.";
      errorEl.hidden = false;
      passwordInput.focus();
      return;
    }

    if (!options.onConfirm) {
      close();
      return;
    }

    busy = true;
    cancelBtn.disabled = true;
    if (passwordInput) passwordInput.readOnly = true;
    modal.setAttribute("aria-busy", "true");
    withLoadingState(
      confirmBtn,
      options.confirmLoadingText || "Aguarde...",
      function () {
        return options.onConfirm(passwordInput ? passwordInput.value : undefined);
      },
    )
      .then(function () { busy = false; close(); })
      .catch(function (err) {
        busy = false;
        cancelBtn.disabled = false;
        if (passwordInput) passwordInput.readOnly = false;
        modal.removeAttribute("aria-busy");
        errorEl.textContent = err.message;
        errorEl.hidden = false;
      });
  }

  confirmBtn.addEventListener("click", handleConfirm);

  if (passwordInput) {
    passwordInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        handleConfirm();
      }
    });
    setTimeout(function () {
      if (!closed) { passwordInput.focus(); if (!options.password) passwordInput.select(); }
    }, 50);
  } else {
    // Foco no Cancelar por padrão, não no Confirmar - evita que um
    // Enter sem querer logo após abrir o popup dispare a ação
    // destrutiva sem intenção.
    setTimeout(function () {
      if (!closed) cancelBtn.focus();
    }, 50);
  }
}
