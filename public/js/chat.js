// Conversation controller. API contracts and existing composer IDs are unchanged.
var selectedWelcomePersonality = "trashtalker", selectedWelcomeEffort = "trash";
var chatPicker = null, envioEmAndamento = null, envioBoasVindas = null, cancelamentoEmAndamento = false;
var ICONE_PARAR = '<svg aria-hidden="true" viewBox="0 0 20 20" width="16" height="16" fill="currentColor"><rect x="5" y="5" width="10" height="10" rx="2"/></svg><span>Parar e desfazer envio</span>';
document.addEventListener("DOMContentLoaded", function () {
  wireComposer("welcome-form", "welcome-input", "welcome-submit", async function (event) {
    event.preventDefault();
    if (cancelamentoEmAndamento) return;
    if (envioBoasVindas) { pararBoasVindas(); return; }
    var input = document.getElementById("welcome-input"), text = input.value.trim();
    if (!text) return;
    var pedido = { controller: new AbortController(), texto: text, chatId: null };
    envioBoasVindas = pedido;
    setComposerPensando("welcome-input", "welcome-submit", true);
    try {
      var result = await apiFetch("/api/chats", { method: "POST", body: {
        personality: selectedWelcomePersonality, effort: selectedWelcomeEffort
      }});
      pedido.chatId = result.id;
      if (envioBoasVindas !== pedido) { await discardWelcome(pedido); return; }
      emitTT("created", { id: result.id });
      try {
        var response = await apiFetch("/api/chats/" + result.id + "/messages", {
          method: "POST", body: { content: text }, signal: pedido.controller.signal
        });
        if (envioBoasVindas !== pedido) return;
        emitTT("response", response);
        location.href = "/dashboard/chat/" + result.id;
      } catch (error) {
        if (envioBoasVindas !== pedido) return;
        // The server may have saved the message. Never automatically send it twice.
        location.href = "/dashboard/chat/" + result.id + "?resposta=erro";
      }
    } catch (error) {
      if (envioBoasVindas !== pedido) {
        if (!pedido.chatId) recoveryMessage("Não foi possível confirmar se a conversa foi criada. Confira a lista antes de tentar novamente.", null);
        return;
      }
      envioBoasVindas = null;
      setComposerPensando("welcome-input", "welcome-submit", false);
      showUIMessage(error.message);
    }
  });
  wireComposer("chat-form", "chat-input", "chat-submit", async function (event) {
    event.preventDefault();
    if (cancelamentoEmAndamento) return;
    if (envioEmAndamento) { pararDeResponder(); return; }
    var input = document.getElementById("chat-input"), text = input.value.trim();
    if (!text) return;
    var messages = document.getElementById("chat-messages");
    var empty = messages.querySelector(".chat-empty"); if (empty) empty.remove();
    var userBubble = buildMessageBubble("user", text), typingBubble = buildTypingBubble();
    messages.append(userBubble, typingBubble); input.value = "";
    messages.scrollTop = messages.scrollHeight;
    var pedido = { controller: new AbortController(), chatId: location.pathname.split("/").pop(),
      texto: text, userBubble: userBubble, typingBubble: typingBubble };
    envioEmAndamento = pedido;
    setComposerPensando("chat-input", "chat-submit", true);
    try {
      var result = await apiFetch("/api/chats/" + pedido.chatId + "/messages", {
        method: "POST", body: { content: text }, signal: pedido.controller.signal
      });
      if (envioEmAndamento !== pedido) return;
      envioEmAndamento = null; typingBubble.remove();
      setComposerPensando("chat-input", "chat-submit", false);
      if (result.cancelled || !result.assistantMessage) {
        recoveryMessage("O servidor não confirmou uma resposta. Reabra a conversa para conferir o histórico.", pedido.chatId);
        return;
      }
      if (result.handoffMessage) {
        messages.appendChild(buildMessageBubble("assistant", result.handoffMessage.content, "mathias"));
        if (result.chat && result.chat.personality === "trashtalker") {
          var handoff = document.createElement("p"); handoff.className = "ui-message handoff-message";
          handoff.setAttribute("role", "status");
          handoff.textContent = "O TrashTalker assumiu para continuar esta conversa mais longa.";
          messages.appendChild(handoff);
        }
      }
      messages.appendChild(buildMessageBubble("assistant", result.assistantMessage.content, result.chat && result.chat.personality));
      messages.scrollTop = messages.scrollHeight;
      if (result.chat) {
        refletirPersonalidade(result.chat.personality);
        var links = document.querySelectorAll(".chat-link");
        links.forEach(function (link) {
          if (link.pathname === "/dashboard/chat/" + pedido.chatId) {
            link.querySelector(".chat-link-text").textContent = result.chat.title;
            link.title = result.chat.title; link.setAttribute("aria-label", result.chat.title);
          }
        });
      }
      emitTT("response", result);
    } catch (error) {
      if (envioEmAndamento !== pedido) return;
      envioEmAndamento = null; typingBubble.remove();
      setComposerPensando("chat-input", "chat-submit", false);
      recoveryMessage("A resposta falhou. Sua mensagem pode ter sido salva; confira o histórico antes de tentar novamente. " + error.message, pedido.chatId);
    }
  });
  loadChatMessagesIfNeeded(); setupWelcomePersonalityPicker();
  if (typeof initVoiceInput === "function") initVoiceInput(document.getElementById("chat-input") || document.getElementById("welcome-input"));
});
function wireComposer(formId, inputId, submitId, onSubmit) {
  var form = document.getElementById(formId), input = document.getElementById(inputId), submit = document.getElementById(submitId);
  if (!form || !input || !submit) return;
  function sync() { submit.disabled = cancelamentoEmAndamento || (!envioEmAndamento && !envioBoasVindas && !input.value.trim()); resizeComposerInput(input); }
  input.addEventListener("input", sync); sync();
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener("submit", onSubmit);
}
function resizeComposerInput(input) {
  input.style.height = "auto";
  var maxHeight = parseFloat(getComputedStyle(input).maxHeight) || Infinity;
  input.style.height = Math.min(maxHeight, input.scrollHeight) + "px";
}
function buildMessageBubble(role, content, personality) {
  var bubble = document.createElement("div"), avatar = document.createElement("div"), text = document.createElement("div");
  bubble.className = "msg-bubble " + (role === "user" ? "msg-user" : "msg-assistant");
  avatar.className = "msg-avatar"; avatar.setAttribute("aria-hidden", "true");
  text.className = "msg-content"; text.textContent = content;
  if (role === "user") {
    avatar.innerHTML = '<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="10" cy="6" r="3"/><path d="M3 18c0-8 14-8 14 0"/></svg>';
    bubble.append(avatar, text);
  } else {
    var known = ["mathias", "trashtalker"].includes(personality);
    var author = document.createElement("span"); author.className = "msg-author";
    author.textContent = known ? (personality === "mathias" ? "MathIAs" : "TrashTalker") : "IA";
    if (known) {
      var logo = document.createElement("img"); logo.src = personality === "mathias" ? "/mathias-mark.svg" : "/logo-talker.svg";
      logo.alt = ""; logo.width = 28; logo.height = 28; avatar.appendChild(logo);
      bubble.classList.add("msg-" + personality);
    } else avatar.textContent = "IA";
    bubble.append(avatar, author, text);
    if (typeof addSpeakButton === "function") addSpeakButton(bubble);
  }
  return bubble;
}
function buildTypingBubble() {
  var bubble = buildMessageBubble("assistant", "Preparando resposta…");
  bubble.classList.add("msg-typing");
  var voice = bubble.querySelector(".voice-speak-button"); if (voice) voice.remove();
  return bubble;
}
async function loadChatMessagesIfNeeded() {
  var container = document.getElementById("chat-messages"); if (!container) return;
  var id = location.pathname.split("/").pop(), data;
  try { data = await apiFetch("/api/chats/" + id); }
  catch (error) {
    if (error.status === 401 || error.status === 404) location.href = "/dashboard";
    else recoveryMessage("Não foi possível carregar o histórico. " + error.message, id);
    return;
  }
  container.replaceChildren();
  setupChatPersonalityPicker(id, { personality: data.chat.personality, effort: data.chat.effort });
  updatePersonalityHeading(data.chat.personality);
  if (!data.messages.length) {
    var empty = document.createElement("p"); empty.className = "chat-empty";
    empty.textContent = "Você pode começar com uma frase."; container.appendChild(empty);
  }
  // Historical API messages do not carry reliable authorship; never guess.
  data.messages.forEach(function (message) { container.appendChild(buildMessageBubble(message.role, message.content)); });
  container.scrollTop = container.scrollHeight; emitTT("chat", data);
  if (new URLSearchParams(location.search).has("resposta")) showUIMessage("Não foi possível obter a resposta. Confira a mensagem salva no histórico antes de tentar novamente.");
}
function updatePersonalityHeading(personality) {
  var title = document.querySelector(".topbar-title");
  if (!title) return;
  title.textContent = personality === "mathias" ? "MathIAs" : personality === "trashtalker" ? "TrashTalker" : "Conversa";
}
function setComposerPensando(inputId, submitId, thinking) {
  var input = document.getElementById(inputId), submit = document.getElementById(submitId);
  if (!input || !submit) return;
  if (!submit.dataset.iconeEnviar) submit.dataset.iconeEnviar = submit.innerHTML;
  if (!input.dataset.placeholderOriginal) input.dataset.placeholderOriginal = input.placeholder;
  input.disabled = thinking; resizeComposerInput(input);
  input.placeholder = thinking ? "Preparando resposta…" : input.dataset.placeholderOriginal;
  submit.innerHTML = thinking ? ICONE_PARAR : submit.dataset.iconeEnviar;
  submit.classList.toggle("is-stop", thinking);
  submit.title = thinking ? "Parar e desfazer envio" : "Enviar mensagem";
  submit.setAttribute("aria-label", submit.title);
  submit.disabled = cancelamentoEmAndamento || (!thinking && !input.value.trim());
  document.querySelectorAll(".voice-mic-button, .personality-picker-trigger, .personality-picker-option").forEach(function (button) { button.disabled = thinking || cancelamentoEmAndamento; });
  emitTT("generating", thinking || cancelamentoEmAndamento);
  if (!thinking) input.focus();
}
function recoveryMessage(message, id) {
  cancelamentoEmAndamento = true; // Block duplicate sends until authoritative history is loaded.
  var status = showUIMessage(message);
  var link = document.createElement("a"); link.href = id ? "/dashboard/chat/" + encodeURIComponent(id) : "/dashboard"; link.textContent = " Reabrir conversa";
  if (status) status.appendChild(link);
  var submit = document.getElementById("chat-submit") || document.getElementById("welcome-submit");
  if (submit) submit.disabled = true;
  emitTT("generating", false);
}
function finishCancel(kind) {
  cancelamentoEmAndamento = false;
  setComposerPensando(kind + "-input", kind + "-submit", false);
  showUIMessage("Envio desfeito. Seu rascunho foi restaurado.", null, false);
}
async function pararDeResponder() {
  var pedido = envioEmAndamento; if (!pedido) return;
  envioEmAndamento = null; cancelamentoEmAndamento = true; pedido.controller.abort(); pedido.typingBubble.remove();
  document.getElementById("chat-input").value = pedido.texto;
  setComposerPensando("chat-input", "chat-submit", false);
  showUIMessage("Confirmando o cancelamento…", null, false);
  try {
    await apiFetch("/api/chats/" + pedido.chatId + "/cancel", { method: "POST" });
    pedido.userBubble.remove(); finishCancel("chat");
  } catch (error) {
    recoveryMessage("Não foi possível confirmar a exclusão do envio. A mensagem continua no histórico até você conferir. Seu rascunho foi mantido. " + error.message, pedido.chatId);
  }
}
function pararBoasVindas() {
  var pedido = envioBoasVindas; if (!pedido) return;
  envioBoasVindas = null; cancelamentoEmAndamento = true; pedido.controller.abort();
  document.getElementById("welcome-input").value = pedido.texto;
  setComposerPensando("welcome-input", "welcome-submit", false);
  showUIMessage("Confirmando o cancelamento…", null, false);
  if (pedido.chatId) discardWelcome(pedido);
}
async function discardWelcome(pedido) {
  try {
    await apiFetch("/api/chats/" + pedido.chatId + "/delete", { method: "POST" });
    finishCancel("welcome");
  } catch (error) {
    recoveryMessage("Não foi possível confirmar a exclusão da conversa criada. Seu rascunho foi mantido. " + error.message, pedido.chatId);
  }
}

function setupWelcomePersonalityPicker() {
  var container = document.getElementById("personality-picker");
  if (!container || !document.getElementById("welcome-form")) return;

  getDashboard()
    .then(function (data) {
      var picker = initPersonalityPicker(
        container,
        [
          {
            key: "personality",
            options: data.personalities,
            selected: selectedWelcomePersonality,
          },
          {
            key: "effort",
            label: "Esforço",
            options: data.efforts,
            selected: selectedWelcomeEffort,
          },
        ],
        function (grupo, id) {
          if (grupo === "personality") { selectedWelcomePersonality = id; updatePersonalityHeading(id); }
          else selectedWelcomeEffort = id;
          picker.setSelected(grupo, id);
        },
      );
    })
    .catch(function () { showUIMessage("As opções de personalidade não carregaram. Você pode conversar com a opção atual ou recarregar a página."); });
}

// Tela de conversa: personalidade e esforço atuais já vêm em
// GET /api/chats/<id> (loadChatMessagesIfNeeded) - só a lista de opções
// (nome/subtítulo de cada uma) precisa de uma chamada própria a
// GET /api/dashboard.
function setupChatPersonalityPicker(chatId, atual) {
  var container = document.getElementById("personality-picker");
  if (!container) return;

  // Rota e nome do campo que cada grupo salva no backend.
  var rotas = {
    personality: { path: "/personality", campo: "personality" },
    effort: { path: "/effort", campo: "effort" },
  };

  getDashboard()
    .then(function (data) {
      var picker = initPersonalityPicker(
        container,
        [
          {
            key: "personality",
            options: data.personalities,
            selected: atual.personality,
          },
          {
            key: "effort",
            label: "Esforço",
            options: data.efforts,
            selected: atual.effort,
          },
        ],
        function (grupo, id) {
          var anterior = atual[grupo];
          // Reflete a escolha na hora e desfaz se o backend recusar.
          picker.setSelected(grupo, id);
          atual[grupo] = id;
          if (grupo === "personality") updatePersonalityHeading(id);

          var rota = rotas[grupo];
          var body = {};
          body[rota.campo] = id;

          apiFetch("/api/chats/" + chatId + rota.path, {
            method: "POST",
            body: body,
          }).catch(function (err) {
            picker.setSelected(grupo, anterior);
            atual[grupo] = anterior;
            if (grupo === "personality") updatePersonalityHeading(anterior);
            showUIMessage(err.message);
          });
        },
      );
      chatPicker = { picker: picker, atual: atual };
    })
    .catch(function () { showUIMessage("As opções de personalidade não carregaram. Você pode conversar com a opção atual ou recarregar a página."); });
}

// Sincroniza o pill com a personalidade que já está salva no banco, para
// os casos em que ela muda sem o usuário abrir o seletor - hoje só a
// preguiça do MathIAs (ver routes/chats_api.py:send_message). Silencioso
// se o picker ainda não montou ou se nada mudou.
function refletirPersonalidade(personality) {
  updatePersonalityHeading(personality);
  if (!chatPicker || !personality) return;
  if (chatPicker.atual.personality === personality) return;
  chatPicker.atual.personality = personality;
  chatPicker.picker.setSelected("personality", personality);
}
