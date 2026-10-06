// Segredos e códigos ficam apenas na memória desta página, nunca em localStorage.
document.addEventListener("DOMContentLoaded", function () {
  var card = document.getElementById("two-factor-card");
  if (!card) return;
  function el(id) { return document.getElementById("two-factor-" + id); }
  var currentAction = null;
  var enabled = false;
  var available = false;
  var busy = false;
  var recoveryCodes = [];
  var setupTimer = null;

  function clearSensitive() {
    clearTimeout(setupTimer);
    el("password-form").reset();
    el("confirm-form").reset();
    el("qr").removeAttribute("src");
    el("manual-key").textContent = "";
    el("recovery-list").replaceChildren();
    recoveryCodes = [];
  }

  function showPanel(name) {
    ["actions", "password-form", "enrollment", "recovery"].forEach(function (id) {
      el(id).hidden = id !== name;
    });
  }

  function showActions(focus) {
    clearSensitive();
    currentAction = null;
    el("start").hidden = enabled;
    el("regenerate").hidden = !enabled;
    el("disable").hidden = !enabled;
    showPanel(available ? "actions" : "");
    if (focus && available) el(enabled ? "regenerate" : "start").focus();
  }

  function showError(message) {
    el("error").textContent = message;
    el("error").hidden = false;
  }

  async function loadStatus() {
    el("retry").hidden = true;
    el("error").hidden = true;
    showPanel("");
    try {
      var data = await apiFetch("/api/2fa/status");
      enabled = data.enabled;
      available = data.available;
      el("status").textContent = enabled
        ? "Ativada. Códigos de recuperação restantes: " + data.recoveryCodesRemaining + "."
        : "Desativada. Você pode ativar esta proteção quando quiser.";
      showActions(false);
      if (!available) {
        showError("Autenticação em dois fatores temporariamente indisponível. Tente mais tarde.");
        el("retry").hidden = false;
      }
    } catch (err) {
      el("status").textContent = "Não foi possível consultar a proteção da conta.";
      showError(err.message);
      el("retry").hidden = false;
    }
  }

  function beginAction(action) {
    if (busy) return;
    clearSensitive();
    el("error").hidden = true;
    currentAction = action;
    var needsCode = action !== "setup";
    el("reauth-field").hidden = !needsCode;
    el("reauth-code").required = needsCode;
    el("action-title").textContent = action === "disable" ? "Desativar autenticação em dois fatores"
      : action === "recovery-codes" ? "Gerar novos códigos de recuperação" : "Confirme sua senha";
    el("action-help").textContent = action === "disable"
      ? "Sua conta voltará a usar somente a senha. Confirme com sua senha e um código válido."
      : action === "recovery-codes" ? "Os códigos anteriores deixarão de funcionar. Confirme com sua senha e um código válido."
        : "Digite sua senha atual para configurar o Google Authenticator.";
    el("action-submit").textContent = action === "disable" ? "Desativar proteção"
      : action === "recovery-codes" ? "Gerar novos códigos" : "Continuar";
    showPanel("password-form");
    el("password").focus();
  }

  async function perform(button, action) {
    if (busy) return;
    busy = true;
    var label = button.textContent;
    card.querySelectorAll("button").forEach(function (item) { item.disabled = true; });
    button.textContent = "Aguarde...";
    el("error").hidden = true;
    try {
      await action();
    } catch (err) {
      if (err.data && err.data.code === "setup_expired") showActions(false);
      showError(err.message);
    } finally {
      el("password").value = "";
      el("reauth-code").value = "";
      el("confirm-code").value = "";
      card.querySelectorAll("button").forEach(function (item) { item.disabled = false; });
      button.textContent = label;
      busy = false;
    }
  }

  function showRecovery(codes) {
    clearSensitive();
    enabled = true;
    recoveryCodes = codes;
    el("status").textContent = "Ativada. Seus outros dispositivos foram desconectados.";
    codes.forEach(function (code) {
      var item = document.createElement("li");
      var text = document.createElement("code");
      text.textContent = code;
      item.appendChild(text);
      el("recovery-list").appendChild(item);
    });
    showPanel("recovery");
    el("recovery-title").focus();
  }

  el("start").addEventListener("click", function () { beginAction("setup"); });
  el("disable").addEventListener("click", function () { beginAction("disable"); });
  el("regenerate").addEventListener("click", function () { beginAction("recovery-codes"); });
  el("retry").addEventListener("click", loadStatus);
  card.querySelectorAll("[data-two-factor-cancel]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!busy) { el("error").hidden = true; showActions(true); }
    });
  });

  el("password-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var action = currentAction;
    perform(el("action-submit"), async function () {
      var data = await apiFetch("/api/2fa/" + action, {
        method: "POST", body: { password: el("password").value, code: el("reauth-code").value.trim() },
      });
      if (action === "setup") {
        el("qr").src = data.qrCodeDataUrl;
        el("manual-key").textContent = data.manualKey;
        showPanel("enrollment");
        el("confirm-code").focus();
        setupTimer = setTimeout(function () {
          if (!busy) { showActions(false); showError("Ativação expirada. Inicie a configuração novamente."); }
        }, data.expiresIn * 1000);
      } else if (data.recoveryCodes) {
        showRecovery(data.recoveryCodes);
      } else {
        enabled = false;
        showActions(false);
        el("status").textContent = "Desativada. Seus outros dispositivos foram desconectados.";
      }
    });
  });

  el("confirm-form").addEventListener("submit", function (event) {
    event.preventDefault();
    perform(el("confirm-form").querySelector("button[type=submit]"), async function () {
      var data = await apiFetch("/api/2fa/confirm", { method: "POST", body: { code: el("confirm-code").value.trim() } });
      showRecovery(data.recoveryCodes);
    });
  });

  el("download").addEventListener("click", function () {
    var content = "Trash Talker — códigos de recuperação\nCada código pode ser usado uma única vez. Guarde em local seguro.\n\n" + recoveryCodes.join("\n");
    var url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
    var link = document.createElement("a");
    link.href = url;
    link.download = "trash-talker-codigos-recuperacao.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  });
  el("done").addEventListener("click", function () { showActions(true); loadStatus(); });
  window.addEventListener("pagehide", function () { clearSensitive(); showPanel(""); });
  window.addEventListener("pageshow", function (event) { if (event.persisted) loadStatus(); });
  loadStatus();
});
