// api.js
// ======
// Pequeno wrapper em torno de fetch() usado por toda a aplicação para
// falar com o backend Python. Centraliza três coisas que, no projeto
// original, ficavam espalhadas: montar o corpo em JSON, tratar erros
// (mostrando a mensagem que o backend devolveu) e credenciais (cookie
// de sessão).

/**
 * Faz uma chamada à API e devolve os dados já decodificados de JSON.
 * Lança um Error com uma mensagem amigável em caso de falha, para que
 * quem chamar possa simplesmente fazer `.catch(err => mostrar(err.message))`.
 *
 * @param {string} path - ex.: "/api/login"
 * @param {object} [options]
 * @param {string} [options.method="GET"]
 * @param {object} [options.body] - será convertido para JSON automaticamente
 * @param {AbortSignal} [options.signal] - permite cancelar a chamada em
 *   andamento (usado pelo botão de parar a resposta da IA, em chat.js)
 */
async function apiFetch(path, options) {
  options = options || {};
  var fetchOptions = {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json" },
    // "same-origin" garante que o cookie de sessão (httponly) seja
    // enviado, já que o frontend e o backend são servidos pela mesma
    // origem (mesmo host:porta) neste projeto.
    credentials: "same-origin",
  };

  if (options.signal) fetchOptions.signal = options.signal;

  if (options.body !== undefined) {
    fetchOptions.body = JSON.stringify(options.body);
  }

  var response;
  try {
    response = await fetch(path, fetchOptions);
  } catch (networkError) {
    // Cancelamento deliberado (AbortController) não é falha de rede: quem
    // chamou é que mandou parar. Repassa o erro original para dar pra
    // distinguir dos casos abaixo - senão o botão de parar mostraria
    // "não foi possível conectar ao servidor" a cada uso.
    if (networkError && networkError.name === "AbortError") throw networkError;
    // fetch() só rejeita a Promise em falha de rede/conexão (servidor
    // fora do ar, sem internet, etc.) - erros HTTP (404, 401, 500) não
    // entram aqui, são tratados abaixo.
    throw new Error(
      "Não foi possível conectar ao servidor. Verifique sua conexão.",
    );
  }

  // 204 No Content não tem corpo para decodificar.
  var data = null;
  if (response.status !== 204) {
    try {
      data = await response.json();
    } catch (_parseError) {
      data = null;
    }
  }

  if (!response.ok) {
    var message =
      (data && data.error) || "Algo deu errado. Tente novamente.";
    var error = new Error(message);
    // Guardado à parte para quem chama poder diferenciar "sessão
    // inválida" (401) de qualquer outra falha (500, etc.) - nem todo
    // erro significa que o usuário não está mais logado.
    error.status = response.status;
    // Corpo completo do erro, para quem precisar de campos extras além da
    // mensagem devolvida pelo backend.
    error.data = data;
    throw error;
  }

  return data;
}

/**
 * GET /api/dashboard compartilhado pela página inteira. Vários scripts da
 * mesma página precisam desses dados ao carregar (layout.js pra sidebar,
 * chat.js pro seletor de personalidade, account.js/settings.js pros
 * formulários) - antes cada um fazia a própria requisição. A primeira
 * chamada dispara o fetch e as outras reaproveitam a mesma Promise. Se der
 * erro, a Promise guardada é descartada, pra próxima chamada tentar de novo.
 */
var dashboardRequest = null;
function getDashboard() {
  if (!dashboardRequest) {
    dashboardRequest = apiFetch("/api/dashboard").catch(function (err) {
      dashboardRequest = null;
      throw err;
    });
  }
  return dashboardRequest;
}

/**
 * Desabilita um botão de envio e troca seu texto enquanto uma Promise
 * (normalmente uma chamada de apiFetch) está em andamento - o "estado de
 * carregamento" pedido para as interações de formulário. Sempre restaura
 * o texto original ao final, com sucesso ou erro.
 *
 * @param {HTMLButtonElement} button
 * @param {string} loadingText
 * @param {() => Promise<any>} action
 */
async function withLoadingState(button, loadingText, action) {
  var originalText = button.textContent;
  var originalDisabled = button.disabled;
  button.disabled = true;
  button.textContent = loadingText;
  try {
    return await action();
  } finally {
    button.disabled = originalDisabled;
    button.textContent = originalText;
  }
}
