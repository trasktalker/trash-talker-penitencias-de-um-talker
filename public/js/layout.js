// layout.js
// =========
// Carregado em toda página do dashboard (dashboard.html, chat.html,
// account.html, settings.html). Monta as partes
// dinâmicas do layout que, no projeto original, o EJS renderizava no
// servidor a partir do banco de dados: a lista de conversas na sidebar
// e o "chip" do usuário (avatar + nome) no rodapé da sidebar.
//
// Também funciona como o "guarda de autenticação" do lado do cliente:
// como não existe mais uma sessão renderizada no servidor, cada página
// do dashboard pergunta ao backend "quem está logado?" via
// GET /api/dashboard; se a resposta for 401, redireciona para /login -
// exatamente o que o middleware requireAuth (src/require-auth.ts) fazia
// no Express.
//
// Substitui: public/js/sidebar.js e as partes dinâmicas de
// src/views/partials/{dashboard-head,sidebar}.ejs.

document.addEventListener("DOMContentLoaded", function () {
  loadDashboardShell();
  wireLogout();
  wireNewChatButton();
  wireSidebarToggle();
});

// Dois botões (mesmo ícone, mesmo comportamento) - um dentro do
// cabeçalho da sidebar (ao lado do logo, estilo DeepSeek), outro na
// topbar (visível quando a sidebar está colapsada, pra reabrir - ver
// app.css). No mobile ele abre/fecha a gaveta sobreposta
// (.sidebar-open, já existia); no desktop minimiza a sidebar de vez
// (.sidebar-collapsed em <html>, não em .app-shell, porque essa classe
// também precisa ser lida cedo - ver o script inline no <head> de
// cada página - e nesse ponto .app-shell ainda não existe no DOM). O
// estado colapsado persiste entre páginas porque este é um app
// multi-página de verdade, sem isso a sidebar "voltaria" a cada
// navegação.
function wireSidebarToggle() {
  var toggles = document.querySelectorAll(".sidebar-toggle");
  var appShell = document.querySelector(".app-shell");
  if (!toggles.length || !appShell) return;
  var sidebar = appShell.querySelector(".sidebar");
  var main = appShell.querySelector(".app-main");
  var desktop = window.matchMedia("(min-width: 1024px)");
  var opener = main.querySelector(".sidebar-toggle");
  var backdrop = document.createElement("button");
  backdrop.type = "button";
  backdrop.className = "sidebar-backdrop";
  backdrop.setAttribute("aria-label", "Ocultar barra lateral");
  backdrop.tabIndex = -1;
  backdrop.hidden = true;
  appShell.insertBefore(backdrop, sidebar);

  function sync() {
    var open = appShell.classList.contains("sidebar-open") && !desktop.matches;
    var expanded = desktop.matches
      ? !document.documentElement.classList.contains("sidebar-collapsed") : open;
    sidebar.inert = !desktop.matches && !open;
    main.inert = open;
    backdrop.hidden = !open;
    toggles.forEach(function (toggle) {
      toggle.setAttribute("aria-controls", "app-sidebar");
      toggle.setAttribute("aria-expanded", String(expanded));
      toggle.title = expanded ? "Ocultar barra lateral" : "Mostrar barra lateral";
      toggle.setAttribute("aria-label", toggle.title);
    });
  }
  function closeDrawer() {
    appShell.classList.remove("sidebar-open");
    sync();
    opener.focus();
  }
  toggles.forEach(function (toggle) {
    toggle.addEventListener("click", function () {
      if (desktop.matches) {
        var collapsed = document.documentElement.classList.toggle("sidebar-collapsed");
        try { localStorage.setItem("trash-talker-sidebar-collapsed", collapsed ? "1" : "0"); } catch (_) {}
        sync();
        (collapsed ? opener : sidebar.querySelector(".sidebar-toggle")).focus();
      } else if (appShell.classList.contains("sidebar-open")) {
        closeDrawer();
      } else {
        appShell.classList.add("sidebar-open");
        sync();
        sidebar.querySelector(".sidebar-toggle").focus();
      }
    });
  });
  backdrop.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (event) {
    if (desktop.matches || !appShell.classList.contains("sidebar-open") || document.querySelector(".modal-overlay")) return;
    if (event.key === "Escape") { event.preventDefault(); closeDrawer(); }
    if (event.key === "Tab") {
      var items = Array.from(sidebar.querySelectorAll('a[href], button:not(:disabled)')).filter(function (el) { return el.getClientRects().length; });
      var first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  desktop.addEventListener("change", function () {
    appShell.classList.remove("sidebar-open");
    sync();
    if (!desktop.matches && sidebar.contains(document.activeElement)) opener.focus();
  });
  sidebar.querySelector('.sidebar-new-chat button').setAttribute("aria-label", "Nova conversa");
  sidebar.querySelectorAll('.sidebar-secondary a').forEach(function (link) { link.setAttribute("aria-label", link.textContent.trim()); });
  sync();
}

async function loadDashboardShell() {
  var data;
  try {
    data = await getDashboard();
  } catch (err) {
    if (err.status === 401) {
      // Sem sessão válida: manda para o login, igual ao requireAuth original.
      window.location.href = "/login";
    } else {
      // Falha passageira (rede, servidor) - a sessão pode continuar
      // válida, então não expulsa o usuário para o login por engano.
      showUIMessage(err.message);
    }
    return;
  }

  emitTT("user", data.user);
  renderUserChip(data.user);
  renderChatList(data.chats);
  if (data.needsConsent) askForConsent();
}

// Contas criadas antes do registro de aceite, ou depois de uma mudança nos
// termos (CONSENT_VERSION em backend/auth.py), confirmam de novo aqui. Sem
// aceitar, a pessoa continua podendo navegar, exportar os dados, excluir a
// conta ou sair - só não conversa (o servidor responde 403). A janela volta
// no próximo carregamento de página.
function askForConsent() {
  var consents;
  showConfirmModal({
    title: "Atualizamos nossos termos",
    message: "Para continuar conversando, confirme os dois itens abaixo. A idade mínima agora é 18 anos.",
    confirmText: "Aceitar e continuar",
    cancelText: "Agora não",
    renderContent: function (modal) { consents = renderConsentChecks(modal); },
    onConfirm: function () {
      if (!consents.accepted()) {
        return Promise.reject(new Error("Marque as duas confirmações para continuar."));
      }
      return apiFetch("/api/account/consent", { method: "POST", body: consents.body() });
    },
  });
}

function renderUserChip(user) {
  var chip = document.querySelector(".user-chip");
  if (!chip) return;

  chip.dataset.userId = user.id;

  // O apelido (display_name) agora vem do banco - mesma prioridade de
  // antes (apelido > nome da conta), só que a fonte de verdade mudou
  // de localStorage pro servidor.
  var displayName = user.display_name || user.name;

  var avatarSlot = chip.querySelector(".avatar-slot");
  if (avatarSlot) {
    avatarSlot.innerHTML = renderAvatarHTML(user.image, user.name, 32);
  }
  var nameEl = chip.querySelector(".user-name");
  if (nameEl) nameEl.textContent = displayName;
  chip.setAttribute("aria-label", "Conta: " + displayName);
}

function renderChatList(chats) {
  var list = document.querySelector(".chat-list");
  if (!list) return;

  list.innerHTML = "";
  chats.forEach(function (chat) {
    list.appendChild(buildChatListItem(chat));
  });
}

function buildChatListItem(chat) {
  var li = document.createElement("li");
  li.className = "chat-item";

  var link = document.createElement("a");
  link.href = "/dashboard/chat/" + chat.id;
  link.className = "chat-link";
  // O title (tooltip nativo) é quem identifica a conversa quando a
  // sidebar está colapsada e só o ícone aparece.
  link.title = chat.title;
  link.setAttribute("aria-label", chat.title);
  if (link.pathname === window.location.pathname) link.setAttribute("aria-current", "page");
  link.innerHTML =
    '<svg class="icon chat-link-icon" viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3.3" y="4.3" width="13.4" height="9.4" rx="2.2"></rect><path d="M7.5 13.7v3l3.4-3"></path></svg><span class="chat-link-text"></span>';
  // Título vem do usuário (mensagem/renomeação) - por segurança, nunca
  // via innerHTML/interpolação de string, sempre textContent.
  link.querySelector(".chat-link-text").textContent = chat.title;
  li.appendChild(link);

  var actions = document.createElement("span");
  actions.className = "chat-actions";

  var renameBtn = document.createElement("button");
  renameBtn.type = "button";
  renameBtn.title = "Renomear";
  renameBtn.setAttribute("aria-label", "Renomear: " + chat.title);
  renameBtn.innerHTML =
    '<svg viewBox="0 0 20 20" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M13.2 3.8 16.2 6.8 6.5 16.5H3.5v-3Z"></path></svg>';
  renameBtn.addEventListener("click", function () {
    renameChat(chat.id, chat.title);
  });

  var deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.title = "Excluir";
  deleteBtn.setAttribute("aria-label", "Excluir: " + chat.title);
  deleteBtn.innerHTML =
    '<svg viewBox="0 0 20 20" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="6" x2="16" y2="6"></line><path d="M8 6V4.2h4V6"></path><path d="M6 6l.8 9.8a1 1 0 0 0 1 .9h4.4a1 1 0 0 0 1-.9L14 6"></path></svg>';
  deleteBtn.addEventListener("click", function () {
    deleteChat(chat.id, chat.title);
  });

  actions.appendChild(renameBtn);
  actions.appendChild(deleteBtn);
  li.appendChild(actions);

  return li;
}

function wireNewChatButton() {
  var form = document.querySelector(".sidebar-new-chat");
  if (!form) return;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    window.location.href = "/dashboard";
  });
}

// Renomear e excluir usam o mesmo diálogo acessível. Os endpoints e
// os textos existentes continuam sendo os mesmos.

function renameChat(id, currentTitle) {
  showConfirmModal({
    title: "Novo nome da conversa:",
    inputValue: currentTitle,
    confirmText: "Renomear",
    onConfirm: function (title) {
      if (!title.trim() || title.trim() === currentTitle) return Promise.resolve();
      return apiFetch("/api/chats/" + id + "/title", {
        method: "POST", body: { title: title.trim() },
      }).then(function () { window.location.reload(); });
    },
  });
}

function deleteChat(id, title) {
  showConfirmModal({
    title: "Excluir conversa",
    message:
      'Tem certeza que deseja excluir a conversa "' +
      title +
      '"? Esta ação não pode ser desfeita.',
    confirmText: "Excluir",
    confirmLoadingText: "Excluindo...",
    danger: true,
    onConfirm: function () {
      return apiFetch("/api/chats/" + id + "/delete", { method: "POST" }).then(
        function () {
          window.location.href = "/dashboard";
        },
      );
    },
  });
}

function wireLogout() {
  var form = document.querySelector(".sidebar-footer form");
  if (!form) return;
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    apiFetch("/api/logout", { method: "POST" })
      .then(function () {
        emitTT("logout");
        window.location.href = "/login";
      }).catch(function (err) { showUIMessage("Não foi possível sair. Tente novamente. " + err.message); });
  });
}
