// voice.js
// ========
// Tudo que é voz mora aqui. O resto do app não sabe como isto funciona -
// chat.js só chama initVoiceInput() e addSpeakButton(), e chat.html só
// carrega este arquivo e tem um <div id="voice-controls"> vazio.
//
// Duas metades:
//   - STT (fala -> texto): botão de microfone no campo de mensagem, em
//     push-to-talk, pela Web Speech API do navegador. O texto reconhecido
//     só PREENCHE o campo; quem envia continua sendo a pessoa.
//   - TTS (texto -> fala): botão de alto-falante em cada resposta da IA.
//     Usa a voz natural do Gemini (POST /api/tts); se o servidor falhar,
//     lê com a voz do próprio navegador.
//
// Requisitos do navegador:
//   - Contexto seguro: só funciona em HTTPS ou em localhost/127.0.0.1.
//     Servido por IP da rede local (ex.: http://192.168.x.x:5000) o
//     navegador bloqueia o microfone.
//   - SpeechRecognition existe no Chrome/Edge/Safari (com prefixo
//     webkit) e NÃO existe no Firefox. Onde faltar, os botões
//     simplesmente não aparecem e o chat de texto segue igual - é por
//     isso que toda a montagem passa por feature detection.

var VOICE_LANG = "pt-BR";

var ReconhecimentoDeFala =
  window.SpeechRecognition || window.webkitSpeechRecognition;

function temReconhecimento() {
  return typeof ReconhecimentoDeFala === "function";
}

// Checa o valor, não só a existência da chave: `"speechSynthesis" in
// window` continua verdadeiro quando a propriedade existe valendo
// undefined, e aí addSpeakButton criaria botões que não falam nada.
function temSintese() {
  return !!(
    window.speechSynthesis && typeof window.SpeechSynthesisUtterance === "function"
  );
}

var ICONE_MIC =
  '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="7.5" y="2.5" width="5" height="9" rx="2.5"></rect><path d="M4.8 9.2a5.2 5.2 0 0 0 10.4 0"></path><line x1="10" y1="14.4" x2="10" y2="17.5"></line></svg>';

var ICONE_MIC_PARAR =
  '<svg viewBox="0 0 20 20" width="15" height="15" fill="currentColor"><rect x="5.6" y="5.6" width="8.8" height="8.8" rx="1.6"></rect></svg>';

var ICONE_SOM =
  '<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7.6h2.6L10 4.6v10.8l-3.4-3H4z"></path><path d="M13 7.4a3.6 3.6 0 0 1 0 5.2"></path></svg>';

var ICONE_SOM_PARAR =
  '<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7.6h2.6L10 4.6v10.8l-3.4-3H4z"></path><line x1="13" y1="7.6" x2="16.4" y2="12.4"></line><line x1="16.4" y1="7.6" x2="13" y2="12.4"></line></svg>';

// --------------------------------------------------------------------------
// Fala -> texto (STT)
// --------------------------------------------------------------------------

/**
 * Monta o botão de microfone e liga o reconhecimento de fala ao campo de
 * mensagem. Não faz nada (e devolve null) se o navegador não suportar -
 * quem chama não precisa checar.
 *
 * O texto reconhecido é escrito em `inputEl` e NUNCA enviado sozinho: a
 * pessoa revisa e manda como sempre. Se já houver algo digitado, o que
 * for falado é acrescentado no fim em vez de apagar o que estava lá.
 *
 * @param {HTMLTextAreaElement|HTMLInputElement} inputEl - campo de mensagem
 * @param {(texto: string) => void} [onFinalTranscript] - avisado com o
 *   texto final quando o reconhecimento termina (opcional)
 * @returns {HTMLButtonElement|null} o botão criado, ou null se não houver suporte
 */
function initVoiceInput(inputEl, onFinalTranscript) {
  if (!inputEl) return null;
  if (!temReconhecimento()) {
    var unsupported = document.getElementById("voice-label");
    if (unsupported) unsupported.textContent = "Ditado indisponível neste navegador. Você pode digitar.";
    return null;
  }

  var container = document.getElementById("voice-controls");
  if (!container) return null;

  var botao = document.createElement("button");
  // "button" e não "submit": este botão vive dentro do <form> do
  // composer, e um submit aqui mandaria a mensagem sem querer.
  botao.type = "button";
  botao.className = "voice-mic-button";
  botao.innerHTML = ICONE_MIC;
  botao.title = "Falar";
  botao.setAttribute("aria-label", "Ditar mensagem por voz");

  container.appendChild(botao);

  // O CSS só reserva o espaço extra do microfone quando ele realmente
  // existe - sem isso, navegador sem suporte (Firefox) ficaria com um
  // buraco no campo de mensagem.
  var composer = inputEl.closest(".composer");
  if (composer) composer.classList.add("has-voice");

  var reconhecedor = new ReconhecimentoDeFala();
  reconhecedor.lang = VOICE_LANG;
  // continuous = false: o próprio navegador encerra ao detectar silêncio,
  // que é justamente o comportamento de push-to-talk pedido.
  reconhecedor.continuous = false;
  reconhecedor.interimResults = true;
  reconhecedor.maxAlternatives = 1;

  var gravando = false;
  var textoBase = "";
  var textoFinal = "";

  function marcar(ativo) {
    gravando = ativo;
    botao.classList.toggle("is-recording", ativo);
    botao.innerHTML = ativo ? ICONE_MIC_PARAR : ICONE_MIC;
    botao.title = ativo ? "Parar de gravar" : "Falar";
    botao.setAttribute(
      "aria-label",
      ativo ? "Parar de gravar" : "Ditar mensagem por voz",
    );
  }

  // Escreve no campo E dispara o evento "input": sem isso o wireComposer
  // não reavalia nada e a seta de enviar continuaria desabilitada, mesmo
  // com texto na tela.
  function escrever(texto) {
    if (inputEl.disabled || cancelamentoEmAndamento) return;
    inputEl.value = texto;
    inputEl.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.addEventListener("tt:generating", function (event) {
    if (event.detail && gravando) { reconhecedor.abort(); marcar(false); }
  });
  reconhecedor.onresult = function (evento) {
    var parcial = "";
    for (var i = evento.resultIndex; i < evento.results.length; i++) {
      var trecho = evento.results[i][0].transcript;
      if (evento.results[i].isFinal) textoFinal += trecho;
      else parcial += trecho;
    }
    escrever(textoBase + textoFinal + parcial);
  };

  reconhecedor.onerror = function (evento) {
    var erro = evento.error;
    // "no-speech" e "aborted" são desfechos normais de push-to-talk (a
    // pessoa desistiu, ou tocou e não falou) - resetar o botão em
    // silêncio, sem alerta, é o comportamento menos irritante.
    if (erro === "no-speech" || erro === "aborted") return;

    var mensagens = {
      "not-allowed":
        "Preciso de permissão para usar o microfone. Libere o acesso nas " +
        "configurações do navegador e tente de novo.",
      "service-not-allowed":
        "O navegador bloqueou o reconhecimento de voz. Isso costuma " +
        "acontecer fora de HTTPS ou localhost.",
      "audio-capture":
        "Não encontrei nenhum microfone disponível neste dispositivo.",
      network:
        "O reconhecimento de voz precisa de internet e a conexão falhou. " +
        "Tente de novo em instantes.",
    };
    showUIMessage(
      mensagens[erro] ||
        "Não consegui te ouvir agora (" + erro + "). Tente de novo.",
    );
  };

  reconhecedor.onend = function () {
    marcar(false);
    if (textoFinal && onFinalTranscript) onFinalTranscript(textoFinal);
  };

  botao.addEventListener("click", function () {
    if (gravando) {
      reconhecedor.stop();
      return;
    }
    // Ditar por cima do que a IA está falando fica confuso, e o eco do
    // alto-falante ainda contamina o reconhecimento.
    pararFala();

    textoFinal = "";
    textoBase = inputEl.value;
    if (textoBase && !/\s$/.test(textoBase)) textoBase += " ";

    try {
      reconhecedor.start();
      marcar(true);
    } catch (_e) {
      // start() lança InvalidStateError se já estiver rodando - o
      // reconhecedor é o mesmo objeto, então basta ignorar.
      marcar(false);
    }
  });

  return botao;
}

// --------------------------------------------------------------------------
// Texto -> fala (TTS)
// --------------------------------------------------------------------------

// Caminho principal: a voz natural do Gemini, gerada no servidor
// (POST /api/tts, ver backend/ai.py:synthesize_speech) e tocada num
// <audio>. Se o servidor falhar (cota, rede, demora), cai na voz do
// próprio navegador (speechSynthesis) - mais robótica, mas a pessoa nunca
// fica sem ouvir.

var vozEscolhida = null;

/**
 * Melhor voz do navegador para a leitura de reserva: português do Brasil
 * primeiro, e entre elas as "Google"/"Natural"/"Online", que soam bem
 * melhor que as offline do sistema. Sem nenhuma, vale qualquer voz pt.
 */
function pickBestVoice() {
  if (!temSintese()) return null;
  var vozes = window.speechSynthesis.getVoices().filter(function (v) {
    return v.lang && v.lang.indexOf("pt") === 0;
  });
  if (!vozes.length) return null;
  function nota(v) {
    return (/^pt[-_]BR/i.test(v.lang) ? 2 : 0) + (/google|natural|online/i.test(v.name) ? 1 : 0);
  }
  return vozes.reduce(function (melhor, v) {
    return nota(v) > nota(melhor) ? v : melhor;
  });
}

// Em vários navegadores getVoices() volta vazio na primeira chamada: a
// lista é carregada de forma assíncrona. Por isso a voz é recalculada
// quando o navegador avisa que a lista chegou.
if (temSintese()) {
  vozEscolhida = pickBestVoice();
  window.speechSynthesis.onvoiceschanged = function () {
    vozEscolhida = pickBestVoice();
  };
}

// O que está tocando (ou sendo gerado) agora:
// { botao, controle (AbortController do fetch), audio, utterance, manutencao }.
var falaAtual = null;

/** Interrompe a leitura em andamento (ou a geração do áudio), se houver. */
function pararFala() {
  if (!falaAtual) return;
  var anterior = falaAtual;
  falaAtual = null;
  if (anterior.controle) anterior.controle.abort();
  if (anterior.audio) anterior.audio.pause();
  clearInterval(anterior.manutencao);
  marcarBotaoDeFala(anterior.botao, "parado");
  if (temSintese()) window.speechSynthesis.cancel();
}

/** @param {"parado"|"carregando"|"falando"} estado */
function marcarBotaoDeFala(botao, estado) {
  if (!botao) return;
  var ativo = estado !== "parado";
  botao.classList.toggle("is-speaking", estado === "falando");
  botao.classList.toggle("is-loading", estado === "carregando");
  botao.innerHTML = ativo ? ICONE_SOM_PARAR : ICONE_SOM;
  botao.title = estado === "carregando" ? "Preparando o áudio… (clique para cancelar)"
    : ativo ? "Parar a leitura" : "Ouvir esta resposta";
  botao.setAttribute(
    "aria-label",
    estado === "carregando" ? "Preparando o áudio, clique para cancelar"
      : ativo ? "Parar a leitura" : "Ouvir esta resposta em voz alta",
  );
}

/** Encerra `atual` se ainda for a leitura em andamento. */
function encerrarFala(atual) {
  if (falaAtual !== atual) return;
  clearInterval(atual.manutencao);
  falaAtual = null;
  marcarBotaoDeFala(atual.botao, "parado");
}

/**
 * Lê `texto` em voz alta, interrompendo qualquer leitura anterior: tenta a
 * voz do Gemini e, se não der, a do navegador.
 *
 * @param {string} texto
 * @param {HTMLButtonElement} [botao] - botão que dispara, para refletir o estado
 * @param {string} [personality] - decide a voz no servidor ("trashtalker"/"mathias")
 */
function speakMessage(texto, botao, personality) {
  if (!texto || !texto.trim()) return;
  pararFala();
  var atual = { botao: botao };
  falaAtual = atual;

  // Áudio já gerado para este mesmo texto: toca de novo na hora, sem
  // gastar outra chamada (a cota do Gemini TTS é limitada).
  if (botao && botao._audio && botao._audio.texto === texto) {
    tocarAudio(atual, botao._audio.url, texto);
    return;
  }

  var controle = typeof AbortController === "function" ? new AbortController() : null;
  atual.controle = controle;
  marcarBotaoDeFala(botao, "carregando");

  // fetch direto, e não apiFetch: a resposta é um arquivo de áudio, não JSON.
  fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ text: texto, personality: personality }),
    signal: controle ? controle.signal : undefined,
  })
    .then(function (resposta) {
      if (!resposta.ok) throw new Error("TTS indisponível (" + resposta.status + ")");
      return resposta.blob();
    })
    .then(function (blob) {
      if (falaAtual !== atual) return; // a pessoa parou ou pediu outra mensagem
      var url = URL.createObjectURL(blob);
      if (botao) {
        if (botao._audio) URL.revokeObjectURL(botao._audio.url);
        botao._audio = { texto: texto, url: url };
      }
      tocarAudio(atual, url, texto);
    })
    .catch(function (erro) {
      if (falaAtual !== atual || (erro && erro.name === "AbortError")) return;
      falarNoNavegador(atual, texto);
    });
}

function tocarAudio(atual, url, texto) {
  var audio = new Audio(url);
  atual.controle = null;
  atual.audio = audio;
  audio.onended = function () { encerrarFala(atual); };
  function reserva() {
    // onerror e a recusa do play() podem disparar os dois: lê uma vez só.
    if (falaAtual !== atual || atual.utterance) return;
    atual.audio = null;
    falarNoNavegador(atual, texto);
  }
  audio.onerror = reserva;
  marcarBotaoDeFala(atual.botao, "falando");
  // play() é recusado se o navegador bloquear áudio (ex.: Safari depois de
  // uma espera longa desde o clique) - aí lê com a voz do navegador.
  var tocando = audio.play();
  if (tocando && tocando.catch) tocando.catch(reserva);
}

/** Leitura de reserva com a voz do navegador (Web Speech API). */
function falarNoNavegador(atual, texto) {
  if (!temSintese()) {
    encerrarFala(atual);
    return;
  }
  var fala = new SpeechSynthesisUtterance(texto);
  fala.lang = VOICE_LANG;
  if (!vozEscolhida) vozEscolhida = pickBestVoice();
  if (vozEscolhida) fala.voice = vozEscolhida;
  fala.onend = function () { encerrarFala(atual); };
  fala.onerror = fala.onend;

  // Bug conhecido do Chrome: a síntese trava sozinha por volta dos 15
  // segundos e a fala é cortada no meio. Um pause()/resume() periódico
  // mantém a fila viva até o fim.
  atual.manutencao = setInterval(function () {
    if (!window.speechSynthesis.speaking) return;
    window.speechSynthesis.pause();
    window.speechSynthesis.resume();
  }, 10000);

  atual.utterance = fala;
  marcarBotaoDeFala(atual.botao, "falando");
  window.speechSynthesis.speak(fala);
}

/**
 * Acrescenta o botão de ouvir a uma bolha de resposta da IA. Aparece em
 * qualquer navegador: o áudio do Gemini toca em todos, e a voz do
 * navegador só entra como reserva.
 *
 * O texto é lido do DOM só na hora do clique, e não agora, porque a
 * bolha nasce vazia e é preenchida aos poucos pelo efeito de digitação
 * (revealGradually em chat.js).
 *
 * @param {HTMLElement} bolha - elemento .msg-bubble.msg-assistant
 */
function addSpeakButton(bolha) {
  if (!bolha) return;

  var botao = document.createElement("button");
  botao.type = "button";
  botao.className = "voice-speak-button";
  marcarBotaoDeFala(botao, "parado");

  botao.addEventListener("click", function () {
    if (falaAtual && falaAtual.botao === botao) {
      pararFala();
      return;
    }
    var conteudo = bolha.querySelector(".msg-content");
    // buildMessageBubble (chat.js) marca a bolha com msg-<personalidade>.
    var personality = bolha.classList.contains("msg-mathias") ? "mathias" : "trashtalker";
    speakMessage(conteudo ? conteudo.textContent : "", botao, personality);
  });

  bolha.appendChild(botao);
}

// Sair da página com o navegador ainda falando é desagradável: a fala
// continua tocando depois que a tela já mudou.
window.addEventListener("pagehide", pararFala);
