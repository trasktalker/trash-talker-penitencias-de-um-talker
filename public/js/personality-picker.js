// personality-picker.js
// =====================
// Pill dropdown reutilizável (gatilho "Nome ⌄" abrindo uma lista com
// nome + subtítulo e um check na opção atual) usado no campo de
// mensagem para escolher a personalidade da IA e o nível de esforço da
// conversa. Mesmo padrão visual do seletor de modelo do Gemini.
//
// O menu é dividido em grupos (personalidade em cima, esforço embaixo,
// separados por uma linha) - cada grupo tem sua própria seleção
// independente, como o "Extended thinking" separado dos modelos no
// seletor do Gemini.
//
// Sem markup fixo nos HTMLs: initPersonalityPicker() monta tudo dentro
// do elemento vazio passado (#personality-picker). Mecânica de
// abrir/fechar copiada de modal.js (dois requestAnimationFrame antes de
// aplicar a classe que dispara a transição CSS; Escape e clique fora
// fecham).
//
// Componente "controlado": clicar numa opção só fecha o menu e chama
// onChange(grupo, id) - não marca a opção sozinho. Quem chama decide
// quando (e se) a seleção visual muda, via o `setSelected` devolvido -
// o que permite refletir a escolha na hora e reverter se a chamada à
// API falhar (ver wiring em chat.js).

/**
 * @param {HTMLElement} rootEl - container vazio (ex.: #personality-picker)
 * @param {Array<{key: string, label?: string, selected: string,
 *   options: Array<{id: string, name: string, subtitle: string}>}>} groups
 *   Os rótulos selecionados de todos os grupos aparecem no gatilho,
 *   separados por "/" (ex.: "MathIAs/Talker").
 * @param {(groupKey: string, id: string) => void} onChange
 * @returns {{ setSelected: (groupKey: string, id: string) => void }}
 */
function initPersonalityPicker(rootEl, groups, onChange) {
  groups.forEach(function (group) {
    if (group.key === "effort") group.options = group.options.map(function (option) {
      return Object.assign({}, option, { name: option.id === "talker" ? "Mais elaborada" : "Mais rápida",
        subtitle: option.id === "talker" ? "Uma resposta com mais desenvolvimento" : "Uma resposta mais direta" });
    });
  });
  var trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "personality-picker-trigger";
  trigger.setAttribute("aria-haspopup", "true");
  trigger.setAttribute("aria-expanded", "false");

  var triggerLabel = document.createElement("span");
  trigger.appendChild(triggerLabel);

  var chevron = document.createElement("span");
  chevron.className = "personality-picker-chevron";
  chevron.innerHTML =
    '<svg viewBox="0 0 20 20" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="5 8 10 13 15 8"></polyline></svg>';
  trigger.appendChild(chevron);

  var menu = document.createElement("div");
  menu.className = "personality-picker-menu";
  menu.setAttribute("role", "menu");
  menu.id = rootEl.id + "-menu";
  menu.setAttribute("aria-label", "Personalidade e esforço");
  menu.inert = true;
  trigger.setAttribute("aria-controls", menu.id);

  // { grupo: { id da opção: elemento do botão } }
  var optionEls = {};

  groups.forEach(function (group, indice) {
    optionEls[group.key] = {};

    var section = document.createElement("div");
    section.className = "personality-picker-group";
    section.setAttribute("role", "group");
    section.setAttribute("aria-label", group.label || "Personalidade");
    // Linha separando o grupo anterior, igual ao seletor do Gemini.
    if (indice > 0) section.classList.add("personality-picker-group-divided");

    if (group.label) {
      var label = document.createElement("div");
      label.className = "personality-picker-group-label";
      label.textContent = group.label;
      section.appendChild(label);
    }

    group.options.forEach(function (opcao) {
      var option = document.createElement("button");
      option.type = "button";
      option.className = "personality-picker-option";
      option.setAttribute("role", "menuitemradio");
      option.setAttribute("aria-checked", "false");

      var text = document.createElement("span");
      text.className = "personality-picker-option-text";

      var name = document.createElement("span");
      name.className = "personality-picker-option-name";
      name.textContent = opcao.name;
      text.appendChild(name);

      var subtitle = document.createElement("span");
      subtitle.className = "personality-picker-option-subtitle";
      subtitle.textContent = opcao.subtitle;
      text.appendChild(subtitle);

      option.appendChild(text);

      var check = document.createElement("span");
      check.className = "personality-picker-check";
      check.innerHTML =
        '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 10.5 8 14.5 16 6"></polyline></svg>';
      option.appendChild(check);

      option.addEventListener("click", function () {
        close();
        if (onChange) onChange(group.key, opcao.id);
      });

      optionEls[group.key][opcao.id] = option;
      section.appendChild(option);
    });

    menu.appendChild(section);
  });

  rootEl.appendChild(trigger);
  rootEl.appendChild(menu);

  // Gatilho mostra o que está escolhido em todos os grupos, na ordem em
  // que aparecem no menu: "MathIAs/Talker".
  function atualizarGatilho() {
    triggerLabel.replaceChildren();
    groups.forEach(function (g) {
      var escolhida = g.options.filter(function (o) {
        return o.id === g.selected;
      })[0];
      if (escolhida) {
        var part = document.createElement("span");
        part.className = g.key === "effort" ? "picker-effort" : "picker-personality";
        part.textContent = (triggerLabel.childNodes.length ? "/" : "") + escolhida.name;
        triggerLabel.appendChild(part);
      }
    });
  }

  function setSelected(groupKey, id) {
    var group = groups.filter(function (g) {
      return g.key === groupKey;
    })[0];
    if (!group) return;
    group.selected = id;

    atualizarGatilho();

    Object.keys(optionEls[groupKey]).forEach(function (key) {
      var selecionada = key === id;
      optionEls[groupKey][key].classList.toggle("selected", selecionada);
      optionEls[groupKey][key].setAttribute(
        "aria-checked",
        selecionada ? "true" : "false",
      );
    });
  }

  var open = false;

  function openMenu() {
    if (open) return;
    open = true;
    trigger.setAttribute("aria-expanded", "true");
    menu.inert = false;
    // O menu abre para cima; em telas baixas ele não cabe inteiro no
    // espaço acima do gatilho e vazaria pela borda de cima. Limita a
    // altura ao espaço real (com uma folga) e deixa rolar por dentro.
    // Medido a cada abertura porque a posição do campo de mensagem muda
    // conforme a tela e a quantidade de mensagens.
    var rect = trigger.getBoundingClientRect();
    var espacoAcima = rect.top - 16;
    var espacoAbaixo = window.innerHeight - rect.bottom - 16;
    var abaixo = espacoAcima < 240 && espacoAbaixo > espacoAcima;
    menu.style.bottom = abaixo ? "auto" : "calc(100% + 0.5rem)";
    menu.style.top = abaixo ? "calc(100% + 0.5rem)" : "auto";
    menu.style.maxHeight = Math.max(80, abaixo ? espacoAbaixo : espacoAcima) + "px";
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (!open) return;
        menu.classList.add("open");
        (menu.querySelector('.selected') || menu.querySelector('button')).focus();
      });
    });
    document.addEventListener("keydown", onKeydown);
    document.addEventListener("click", onDocumentClick);
  }

  function close(restoreFocus) {
    if (!open) return;
    open = false;
    trigger.setAttribute("aria-expanded", "false");
    menu.classList.remove("open");
    if (restoreFocus !== false && menu.contains(document.activeElement)) trigger.focus();
    menu.inert = true;
    document.removeEventListener("keydown", onKeydown);
    document.removeEventListener("click", onDocumentClick);
  }

  function onKeydown(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    if (e.key === "Tab") close();
    var options = Array.from(menu.querySelectorAll('button'));
    var index = options.indexOf(document.activeElement);
    if (["ArrowDown", "ArrowUp", "Home", "End"].indexOf(e.key) !== -1) {
      e.preventDefault();
      if (e.key === "Home") index = 0;
      else if (e.key === "End") index = options.length - 1;
      else index = (index + (e.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
      if (options[index]) options[index].focus();
    }
  }

  // Clique em qualquer lugar dentro de rootEl (gatilho ou menu) NÃO
  // fecha - só clique fora. Sem esse filtro, o próprio clique que abre o
  // menu (ainda se propagando até o document nesse mesmo tick) fecharia
  // o menu imediatamente em seguida.
  function onDocumentClick(e) {
    if (!rootEl.contains(e.target)) close(false);
  }

  trigger.addEventListener("click", function () {
    if (open) close();
    else openMenu();
  });
  trigger.addEventListener("keydown", function (event) {
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault(); openMenu();
    }
  });
  rootEl.addEventListener("focusout", function (event) {
    if (event.relatedTarget && !rootEl.contains(event.relatedTarget)) close(false);
  });

  groups.forEach(function (group) {
    setSelected(group.key, group.selected);
  });

  return { setSelected: setSelected };
}
