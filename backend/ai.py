"""
ai.py
=====
Integração com a IA (Gemini) que gera as respostas do TrashTalker.

Diferente do script original (que guardava um histórico `mensagens` em
memória, em uma lista global), aqui a aplicação Flask é stateless entre
requests - o histórico de cada conversa é reconstruído a partir do
banco (ver routes/chats_api.py) e passado inteiro para generate_reply()
a cada chamada.
"""

import os

from backend.personalities import DEFAULT_PERSONALITY, get_personality_prompt

# O Google recomenda fortemente manter a temperatura no padrão (1.0) nos
# modelos Gemini 3 - valores mais baixos podem causar loop ou piorar a
# resposta. top_p também fica no padrão do modelo.
TEMPERATURE = 1.0

# Teto de segurança, não o tamanho da resposta: os tokens de "thinking"
# saem desse MESMO orçamento, e com thinking "high" o raciocínio sozinho
# pode passar de alguns milhares de tokens - se estourar, a resposta
# visível vem cortada ou vazia. Quem mantém a resposta curta é o prompt
# (ver personalities.py).
MAX_OUTPUT_TOKENS = 16384

# O Gemini devolve 503 UNAVAILABLE ("this model is currently experiencing
# high demand") de vez em quando - é pico temporário do lado do Google, não
# erro nosso, e a própria mensagem pede pra tentar de novo. O SDK NÃO tenta
# sozinho: sem `retry_options` ele usa a estratégia "never retry"
# (stop_after_attempt(1) em _api_client.retry_args), e o erro sobe na
# primeira falha - virando 502 na cara de quem está conversando.
#
# Os defaults do SDK (5 tentativas, esperas de 1/2/4/8s) são pensados para
# job em lote, não para alguém olhando os "..." na tela. Aqui: 3 tentativas
# no total, esperando ~1s e ~2s. Custa no máximo uns 3s a mais no pior caso
# e resolve a esmagadora maioria dos picos.
RETRY_ATTEMPTS = 3
RETRY_INITIAL_DELAY = 1.0
RETRY_MAX_DELAY = 4.0

# Nível de "esforço" escolhido por conversa: troca o quanto o Gemini pensa
# antes de responder. O trocadilho é com o nome do projeto - "Trash"
# responde mais rápido, "Talker" pensa mais e demora mais.
#
# Os dois usam o mesmo modelo de propósito: quem conversa aqui são pessoas
# com dificuldade, então acertar importa mais que custo ou velocidade. O
# gemini-4-argon é o modelo mais novo disponível; se o nome estiver errado,
# todo envio de mensagem vira 502.
EFFORTS = {
    "trash": {
        "name": "Trash",
        "subtitle": "Respostas mais rápidas",
        "model": "gemini-4-argon",
        "thinking_level": "medium",
    },
    "talker": {
        "name": "Talker",
        "subtitle": "Respostas mais caprichadas",
        "model": "gemini-4-argon",
        "thinking_level": "high",
    },
}
DEFAULT_EFFORT = "trash"

# Sem os campos "model"/"thinking_level" - o frontend só precisa do rótulo,
# e qual modelo está por trás de cada opção é detalhe interno (mesma ideia
# do PERSONALITIES_PUBLIC em personalities.py).
EFFORTS_PUBLIC = [
    {"id": key, "name": value["name"], "subtitle": value["subtitle"]}
    for key, value in EFFORTS.items()
]


def get_effort(key):
    """
    Configuração (modelo + thinking_level) do esforço `key`, com fallback
    para o padrão se a chave for desconhecida/vazia - cobre conversas
    criadas antes desta coluna existir e valores inválidos vindos do cliente.
    """
    return EFFORTS.get(key) or EFFORTS[DEFAULT_EFFORT]


_client = None


def get_client():
    """Cria o client do Gemini na primeira chamada (lazy), não na importação
    do módulo - assim o app.py não quebra ao subir se GEMINI_API_KEY ainda
    não estiver configurada, só a chamada de chat é que falha."""
    global _client
    if _client is None:
        from google import genai
        from google.genai import types  # import aqui: o SDK é pesado e só a rota de chat precisa dele (cold start)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("A variável de ambiente GEMINI_API_KEY não foi definida")
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=RETRY_ATTEMPTS,
                    initial_delay=RETRY_INITIAL_DELAY,
                    max_delay=RETRY_MAX_DELAY,
                )
            ),
        )
    return _client


def _to_gemini_contents(history):
    """Converte o histórico {"role": "user"|"assistant", "content": str} do
    banco para o formato `contents` esperado pela API do Gemini - que usa
    "model" no lugar de "assistant" para as respostas da IA."""
    from google.genai import types  # import aqui: o SDK é pesado e só a rota de chat precisa dele (cold start)
    contents = []
    for m in history:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=m["content"])])
        )
    return contents


def _build_user_context_section(user):
    """
    Bloco anexado ao fim do SYSTEM_PROMPT em cada chamada, com o que a
    IA sabe sobre a pessoa (apelido/pronome/interesses do perfil - ver
    routes/chats_api.py:update_account). Nome sempre entra (users.name
    é NOT NULL); apelido, pronome e interesses só entram se existirem,
    pra não mandar instrução vazia pro modelo. Esse bloco é o mesmo (e
    é anexado da mesma forma) qualquer que seja a personalidade
    escolhida pra conversa (ver personalities.py) - só acrescenta
    contexto sobre quem está falando, não define a personalidade em si.
    """
    # Sem apelido, vai só o primeiro nome: a IA chama a pessoa "como um
    # amigo faria" e não precisa do nome completo (minimização de dados -
    # tudo aqui é enviado ao Google a cada mensagem).
    display_name = (user.get("display_name") or "").strip() or (
        (user.get("name") or "").strip().split(" ")[0]
    )
    pronoun = (user.get("pronoun") or "").strip()
    interests = [i for i in (user.get("interests") or []) if i]

    lines = [
        "# SOBRE A PESSOA COM QUEM VOCÊ ESTÁ FALANDO",
        "- O nome da pessoa é " + display_name + ". Chame a pessoa pelo nome de "
        "vez em quando, do jeito que um amigo faria - não precisa ser em toda "
        "mensagem, só quando soar natural (numa saudação, pra puxar assunto, pra "
        "dar ênfase).",
    ]

    if pronoun:
        lines.append("- Use o pronome '" + pronoun + "' pra se referir a essa pessoa.")

    if interests:
        lines.append(
            "- Interesses da pessoa: " + ", ".join(interests) + ". Puxe assunto "
            "com isso quando fizer sentido, faça analogias, mostre que prestou "
            "atenção - sem citar a lista como se fosse um checklist."
        )

    lines.append(
        "- Use essas informações com naturalidade, como um amigo que já conhece "
        "a pessoa. Nunca liste esses dados de volta pra pessoa, nunca repita esse "
        "bloco como se fosse um formulário, e não force menção a eles se não vier "
        "a calhar na conversa."
    )

    return "\n".join(lines)


def generate_reply(
    history, user, personality=DEFAULT_PERSONALITY, effort=DEFAULT_EFFORT
):
    """
    history: lista de dicts {"role": "user"|"assistant", "content": str},
    ordenada da mensagem mais antiga para a mais recente (já inclui a
    mensagem atual do usuário).
    user: dict do usuário logado (ver auth.get_session_user), usado só
    para personalizar o system prompt com nome/pronome/interesses (ver
    _build_user_context_section).
    personality: chave da personalidade a usar (ver
    backend/personalities.py) - default DEFAULT_PERSONALITY, pra
    qualquer chamador que não pense em personas ter o mesmo
    comportamento de antes.
    effort: chave do nível de esforço (ver EFFORTS acima), que decide
    qual modelo do Gemini responde.
    Devolve o texto da resposta da IA.
    """
    from google.genai import types  # import aqui: o SDK é pesado e só a rota de chat precisa dele (cold start)
    system_prompt = get_personality_prompt(personality) + "\n\n" + _build_user_context_section(user)
    effort_config = get_effort(effort)

    response = get_client().models.generate_content(
        model=effort_config["model"],
        contents=_to_gemini_contents(history),
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            # thinking_level, não o antigo thinking_budget: os modelos
            # Gemini 3 não deixam desligar o thinking (budget=0), e mandar
            # os dois parâmetros juntos dá 400. Ver EFFORTS acima.
            thinking_config=types.ThinkingConfig(
                thinking_level=effort_config["thinking_level"]
            ),
            # Não declaramos nenhuma ferramenta (function calling) - o modelo só
            # devolve texto. Sem desligar isso explicitamente, o SDK imprime um
            # aviso sobre "automatic function calling" a cada chamada, sujando o
            # log sem que haja nada de fato para chamar.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        ),
    )

    if not response.text:
        # Acontece quando os filtros de segurança do Gemini bloqueiam a
        # resposta (finish_reason SAFETY, por exemplo) - o try/except em
        # chats_api.py transforma isso na mensagem de erro genérica.
        raise RuntimeError(
            "Resposta vazia ou bloqueada pelos filtros de segurança do Gemini"
        )
    return response.text


# --------------------------------------------------------------------------
# Texto -> fala (botão "ouvir" de cada resposta, ver public/js/voice.js)
# --------------------------------------------------------------------------
# Antes o áudio vinha só da voz do navegador (Web Speech API), que soa
# robótica. O Gemini TTS gera fala natural e aceita uma instrução de
# estilo ("acolhedor, calmo..."). Se ele falhar (cota, rede), a rota
# devolve 502 e o frontend volta sozinho pra voz do navegador.
TTS_MODEL = "gemini-3.8-flash-tts"
TTS_LANGUAGE = "pt-BR"
TTS_SAMPLE_RATE = 24000  # formato do Gemini TTS: 24 kHz, mono, 16 bits
TTS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
# Nos testes o TTS levou de 5 a ~22s, mas às vezes passa de 40s. Melhor
# desistir em 30s (bem abaixo do maxDuration de 60s do vercel.json) e deixar
# o navegador ler com a voz dele do que deixar a pessoa esperando.
TTS_TIMEOUT_SECONDS = 30

# Uma voz por personalidade, combinando com o jeito de cada uma. "style"
# é a instrução de como falar - vale pra fala inteira.
TTS_VOICES = {
    "trashtalker": {
        "voice": "Achird",  # "Friendly"
        "style": "amigo próximo e acolhedor, calmo e tranquilo, jeito natural "
        "de jovem brasileiro conversando",
    },
    "mathias": {
        "voice": "Puck",  # "Upbeat"
        "style": "jovem brasileiro descontraído e bem-humorado, ritmo leve de "
        "conversa entre amigos",
    },
    "evaisto": {
        "voice": "Schedar",  # "Even"
        "style": "jovem brasileiro de 18 anos, humor seco e deadpan, fala "
        "tranquila e sem rir das próprias piadas",
    },
}


def _pcm_to_wav(pcm):
    """Põe cabeçalho WAV num PCM cru (16 bits, mono, 24 kHz) - o navegador
    não sabe tocar PCM sem cabeçalho."""
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TTS_SAMPLE_RATE)
        wav.writeframes(pcm)
    return buffer.getvalue()


def synthesize_speech(text, personality=DEFAULT_PERSONALITY):
    """
    Gera o áudio (WAV) de `text` falado com a voz da personalidade.
    Lança exceção se o Gemini falhar ou não devolver áudio - quem chama
    (routes/chats_api.py:text_to_speech) transforma isso em 502.

    Chama a API REST direto, sem o SDK: o client.interactions do SDK tenta
    de novo sozinho em 429 respeitando o Retry-After do Google - que, com
    a cota esgotada, chega a horas -, e não deixa desligar isso por chamada.
    Aqui é uma tentativa só, com tempo limite.
    """
    import base64
    import json
    import urllib.request

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("A variável de ambiente GEMINI_API_KEY não foi definida")

    voice = TTS_VOICES.get(personality) or TTS_VOICES[DEFAULT_PERSONALITY]
    body = {
        "model": TTS_MODEL,
        "input": [{
            "type": "user_input",
            "content": [{
                "type": "text",
                "text": text,
                "annotations": [{"type": "speech_metadata", "style": voice["style"]}],
            }],
        }],
        "response_format": {"type": "audio"},
        "generation_config": {
            "speech_config": [{"voice": voice["voice"], "language": TTS_LANGUAGE}]
        },
    }
    request = urllib.request.Request(
        TTS_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    # HTTPError (429 de cota, 5xx...) sobe direto pra rota.
    with urllib.request.urlopen(request, timeout=TTS_TIMEOUT_SECONDS) as response:
        interaction = json.loads(response.read())

    # O áudio vem em steps[].content[] com type "audio" (base64).
    data = next(
        (
            item.get("data")
            for step in interaction.get("steps") or []
            if step.get("type") == "model_output"
            for item in step.get("content") or []
            if item.get("type") == "audio" and item.get("data")
        ),
        None,
    )
    if not data:
        raise RuntimeError("O Gemini TTS não devolveu áudio")
    audio_bytes = base64.b64decode(data)
    # O 3.8 TTS devolve WAV pronto; modelos/formatos antigos devolviam PCM
    # cru (audio/l16) - nesse caso o cabeçalho é montado aqui.
    if not audio_bytes.startswith(b"RIFF"):
        audio_bytes = _pcm_to_wav(audio_bytes)
    return audio_bytes