// avatar.js
// =========
// Função compartilhada que desenha o avatar do usuário (foto, avatar
// ilustrado ou iniciais). Equivalente ao partial src/views/partials/avatar.ejs
// do projeto original, só que como uma função JS reaproveitável em vez de
// um template renderizado no servidor.
//
// Usada em: js/layout.js (avatar pequeno da sidebar) e js/account.js
// (avatar grande da tela de conta).

/**
 * Devolve o HTML (string) do avatar do usuário.
 * @param {string|null} image - pode ser: null, uma URL/data-URL, ou
 *   "avatar:<id>" apontando para um dos avatares ilustrados em /avatars/.
 * @param {string} name - nome do usuário, usado para gerar as iniciais
 *   quando não há imagem.
 * @param {number} size - tamanho em pixels (largura/altura).
 */
function renderAvatarHTML(image, name, size) {
  var style = "width:" + size + "px;height:" + size + "px";

  if (image && image.indexOf("avatar:") === 0) {
    var avatarId = image.replace("avatar:", "");
    return (
      '<img class="avatar" style="' +
      style +
      '" src="/avatars/' +
      avatarId +
      '.svg" alt="' +
      escapeHtml(name) +
      '" />'
    );
  }

  if (image) {
    return (
      '<img class="avatar" style="' +
      style +
      '" src="' +
      escapeHtml(image) +
      '" alt="' +
      escapeHtml(name) +
      '" />'
    );
  }

  var initials = (name || "").substring(0, 2).toUpperCase() || "??";
  return (
    '<div class="avatar avatar-fallback" style="' +
    style +
    '">' +
    escapeHtml(initials) +
    "</div>"
  );
}

// Pequeno helper para não injetar HTML não escapado no innerHTML (o nome
// do usuário, em particular, é dado que ele mesmo digitou no cadastro).
function escapeHtml(value) {
  var div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}
