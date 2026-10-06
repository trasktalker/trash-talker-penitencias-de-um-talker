// account.js
// ==========
// Tela "Minha Conta". Nome, email, foto/avatar, apelido, pronome e
// interesses vêm todos do banco de dados (via GET /api/dashboard) e
// são salvos num único POST /api/account. Até esta mudança, apelido e
// interesses só existiam no localStorage deste navegador e a IA não
// tinha como enxergá-los (ela roda no servidor) - ver schema.sql
// (colunas display_name/pronoun/interests em users) e ai.py
// (generate_reply usa esses campos para personalizar o system prompt).
//
// Migração: quem já tinha apelido/interesses salvos no formato antigo
// (localStorage) tem esse valor lido uma única vez, só como valor
// inicial do formulário, e só quando o banco ainda não tem nada salvo.
// Depois do primeiro "Salvar", tudo passa a vir do banco e a chave
// antiga do localStorage nunca mais é lida nem escrita.

document.addEventListener("DOMContentLoaded", async function () {
  var form = document.getElementById("account-form");
  if (!form) return;

  var data;
  try {
    data = await getDashboard();
  } catch (err) {
    if (err.status === 401) {
      window.location.href = "/login";
    } else {
      // Falha passageira (rede, servidor) - a sessão pode continuar
      // válida, então não expulsa o usuário para o login por engano.
      showUIMessage(err.message);
    }
    return;
  }

  var user = data.user;
  initAccountForm(form, user);
});

function initAccountForm(form, user) {
  // --- Preenche os campos vindos do banco (nome, avatar) ---

  var nameInput = document.getElementById("name");
  nameInput.value = user.name;

  var avatarImageInput = document.getElementById("avatar-image-input");
  var avatarTrigger = document.getElementById("avatar-trigger");
  avatarImageInput.value = user.image || "";
  avatarTrigger.innerHTML = renderAvatarHTML(user.image, user.name, 96);

  // --- Apelido, pronome e interesses (banco de dados) ---

  var displayNameInput = document.getElementById("displayName");
  var pronounInput = document.getElementById("pronoun");
  var tagsContainer = document.getElementById("interest-tags");
  var tagInput = document.getElementById("tag-input");
  var tagAddBtn = document.getElementById("tag-add-btn");

  // Fallback só de migração: evita perder um apelido/interesses que já
  // existia no formato antigo (localStorage); só é usado quando o
  // banco ainda não tem nada salvo.
  var legacyLocal = {};
  try {
    var raw = localStorage.getItem("trash-talker-local-profile-" + user.id);
    legacyLocal = raw ? JSON.parse(raw) : {};
  } catch (_e) {
    legacyLocal = {};
  }

  var interests = [];
  if (user.interests && user.interests.length) {
    interests = user.interests.slice();
  } else if (legacyLocal.interests) {
    interests = legacyLocal.interests.slice();
  }

  displayNameInput.value = user.display_name || legacyLocal.displayName || "";
  pronounInput.value = user.pronoun || "";

  function renderTags() {
    tagsContainer.innerHTML = "";
    if (interests.length === 0) {
      var empty = document.createElement("span");
      empty.className = "tag-empty";
      empty.textContent =
        "Nenhum interesse adicionado. Selecione abaixo ou digite um novo.";
      tagsContainer.appendChild(empty);
      return;
    }
    interests.forEach(function (tag) {
      var chip = document.createElement("span");
      chip.className = "tag-chip";
      chip.textContent = tag + " ";
      var remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", "Remover interesse: " + tag);
      remove.addEventListener("click", function () {
        interests = interests.filter(function (t) {
          return t !== tag;
        });
        renderTags();
        syncSuggestions();
        tagInput.focus();
      });
      chip.appendChild(remove);
      tagsContainer.appendChild(chip);
    });
  }

  function syncSuggestions() {
    document.querySelectorAll(".tag-suggestion").forEach(function (btn) {
      btn.classList.toggle("active", interests.indexOf(btn.dataset.tag) !== -1);
      btn.setAttribute("aria-pressed", String(interests.indexOf(btn.dataset.tag) !== -1));
    });
  }

  document.querySelectorAll(".tag-suggestion").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var tag = btn.dataset.tag;
      if (interests.indexOf(tag) === -1) {
        interests.push(tag);
      } else {
        interests = interests.filter(function (t) {
          return t !== tag;
        });
      }
      renderTags();
      syncSuggestions();
    });
  });

  function addCustomTag() {
    var value = tagInput.value.trim();
    if (value && interests.indexOf(value) === -1) {
      interests.push(value);
      tagInput.value = "";
      renderTags();
      syncSuggestions();
    }
  }

  tagAddBtn.addEventListener("click", addCustomTag);
  tagInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      addCustomTag();
    }
  });

  renderTags();
  syncSuggestions();

  // --- Seletor de avatar (upload de arquivo ou avatar ilustrado) ---

  var avatarFileInput = document.getElementById("avatar-file-input");

  avatarTrigger.addEventListener("click", function () {
    avatarFileInput.click();
  });

  avatarFileInput.addEventListener("change", function () {
    var file = avatarFileInput.files && avatarFileInput.files[0];
    if (!file) return;
    shrinkAvatarPhoto(file)
      .then(function (dataUrl) {
        avatarImageInput.value = dataUrl;
        avatarTrigger.innerHTML = renderAvatarHTML(dataUrl, user.name, 96);
        syncAvatars();
      })
      .catch(function () {
        showUIMessage("Não consegui usar essa imagem. Tente outra foto (JPG ou PNG).");
      })
      .finally(function () { avatarFileInput.value = ""; });
  });

  function syncAvatars() {
    document.querySelectorAll(".illustrated-avatar-btn").forEach(function (btn) {
      var selected = avatarImageInput.value === "avatar:" + btn.dataset.avatarId;
      btn.classList.toggle("selected", selected);
      btn.setAttribute("aria-pressed", String(selected));
    });
  }
  syncAvatars();
  document.querySelectorAll(".illustrated-avatar-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.dataset.avatarId;
      avatarImageInput.value = "avatar:" + id;
      avatarTrigger.innerHTML = renderAvatarHTML(avatarImageInput.value, user.name, 96);
      syncAvatars();
    });
  });

  var cancelBtn = document.getElementById("account-cancel");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", function () {
      window.location.reload();
    });
  }

  // --- Envio do formulário ---

  var errorBanner = document.getElementById("account-error");
  var successBanner = document.getElementById("account-success");

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    errorBanner.hidden = true;
    successBanner.hidden = true;
    var submitBtn = form.querySelector("button[type=submit]");

    withLoadingState(submitBtn, "Salvando...", function () {
      return apiFetch("/api/account", {
        method: "POST",
        body: {
          name: nameInput.value,
          image: avatarImageInput.value || "",
          displayName: displayNameInput.value,
          pronoun: pronounInput.value,
          interests: interests,
        },
      });
    })
      .then(function () {
        successBanner.hidden = false;
        // Recarrega a página pra refletir os dados salvos em todo lugar
        // (ex: nome/avatar/apelido no chip da sidebar) sem precisar de
        // F5 manual.
        setTimeout(function () {
          window.location.reload();
        }, 800);
      })
      .catch(function (err) {
        errorBanner.textContent = err.message;
        errorBanner.hidden = false;
      });
  });
}

// O avatar aparece com no máximo 96px, então guardar a foto original (vários
// MB, com metadados EXIF - inclusive a localização GPS de onde foi tirada)
// seria dado desnecessário. Redesenhar num <canvas> e exportar como JPEG
// reduz para uns poucos KB e descarta todo metadado. O backend recusa
// imagem grande demais (MAX_IMAGE_CHARS em routes/chats_api.py).
var AVATAR_MAX_PX = 256;
function shrinkAvatarPhoto(file) {
  return new Promise(function (resolve, reject) {
    if (!/^image\//.test(file.type)) { reject(new Error("não é imagem")); return; }
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var scale = Math.min(1, AVATAR_MAX_PX / Math.max(img.naturalWidth, img.naturalHeight));
      var canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff"; // fundo para PNG transparente (JPEG não tem alfa)
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("imagem ilegível")); };
    img.src = url;
  });
}
