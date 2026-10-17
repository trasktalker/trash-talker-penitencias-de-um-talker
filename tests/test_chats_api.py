"""
Testes dos endpoints de conversa (routes/chats_api.py).

Além do caminho feliz, cobrem dois pontos de risco:
  - **isolamento entre usuários**: ninguém pode ler/renomear/apagar a
    conversa de outra pessoa adivinhando o id;
  - **falha da IA**: a aplicação precisa degradar com um 502 sem perder
    a mensagem que o usuário já tinha escrito.
"""

from backend import db
from conftest import cadastrar, logar


def _segundo_usuario(aplicacao):
    """Cria um segundo cliente autenticado com outra conta."""
    outro = aplicacao.test_client()
    cadastrar(outro, email="outro@exemplo.com", nome="Outro")
    assert logar(outro, email="outro@exemplo.com").status_code == 200
    return outro


# --------------------------------------------------------------------------
# Proteção de rota
# --------------------------------------------------------------------------


def test_rotas_protegidas_exigem_login(cliente):
    assert cliente.get("/api/dashboard").status_code == 401
    assert cliente.post("/api/chats").status_code == 401
    assert cliente.get("/api/chats/qualquer-id").status_code == 401
    assert cliente.get("/api/account/export").status_code == 401


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


def test_dashboard_devolve_usuario_conversas_e_avatares(cliente, usuario_logado, conversa):
    corpo = cliente.get("/api/dashboard").get_json()
    assert corpo["user"]["id"] == usuario_logado["id"]
    assert [c["id"] for c in corpo["chats"]] == [conversa]
    assert len(corpo["illustratedAvatars"]) > 0


def test_dashboard_nao_mostra_conversa_de_outro_usuario(cliente, aplicacao, usuario_logado):
    outro = _segundo_usuario(aplicacao)
    outro.post("/api/chats")

    assert cliente.get("/api/dashboard").get_json()["chats"] == []


# --------------------------------------------------------------------------
# Criar / ler conversa
# --------------------------------------------------------------------------


def test_criar_conversa_devolve_id_e_persiste(cliente, usuario_logado):
    resposta = cliente.post("/api/chats")
    assert resposta.status_code == 201

    chat_id = resposta.get_json()["id"]
    linha = db.query_one("SELECT * FROM chats WHERE id = %s", (chat_id,))
    assert linha["user_id"] == usuario_logado["id"]
    assert linha["title"] == "New Chat"


def test_ler_conversa_existente(cliente, conversa):
    resposta = cliente.get(f"/api/chats/{conversa}")
    assert resposta.status_code == 200
    assert resposta.get_json()["chat"]["id"] == conversa
    assert resposta.get_json()["messages"] == []


def test_ler_conversa_inexistente_devolve_404(cliente, usuario_logado):
    assert cliente.get("/api/chats/id-que-nao-existe").status_code == 404


def test_nao_e_possivel_ler_conversa_de_outro_usuario(cliente, aplicacao, usuario_logado):
    outro = _segundo_usuario(aplicacao)
    conversa_alheia = outro.post("/api/chats").get_json()["id"]

    assert cliente.get(f"/api/chats/{conversa_alheia}").status_code == 404


# --------------------------------------------------------------------------
# Enviar mensagem
# --------------------------------------------------------------------------


def test_enviar_mensagem_persiste_pergunta_e_resposta(cliente, conversa, ia_falsa):
    resposta = cliente.post(
        f"/api/chats/{conversa}/messages", json={"content": "Travei numa conversa hoje"}
    )
    assert resposta.status_code == 200

    corpo = resposta.get_json()
    assert corpo["userMessage"]["content"] == "Travei numa conversa hoje"
    assert corpo["assistantMessage"]["content"] == "Resposta simulada do TrashTalker."
    assert corpo["assistantMessage"]["personality"] == "trashtalker"

    salvas = db.query("SELECT role, content FROM messages ORDER BY created_at ASC")
    assert [m["role"] for m in salvas] == ["user", "assistant"]


def test_ia_recebe_o_historico_completo_da_conversa(cliente, conversa, ia_falsa):
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "primeira"})
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "segunda"})

    ultimo_historico = ia_falsa["chamadas"][-1]["history"]
    assert [m["content"] for m in ultimo_historico] == [
        "primeira",
        "Resposta simulada do TrashTalker.",
        "segunda",
    ]


def test_ia_recebe_o_perfil_do_usuario(cliente, conversa, ia_falsa, usuario_logado):
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "oi"})
    assert ia_falsa["chamadas"][0]["user"]["id"] == usuario_logado["id"]


def test_mensagem_vazia_e_recusada(cliente, conversa, ia_falsa):
    resposta = cliente.post(f"/api/chats/{conversa}/messages", json={"content": "   "})
    assert resposta.status_code == 400
    assert db.query("SELECT * FROM messages") == []
    assert ia_falsa["chamadas"] == []


def test_mensagem_em_conversa_inexistente_devolve_404(cliente, usuario_logado, ia_falsa):
    resposta = cliente.post("/api/chats/nao-existe/messages", json={"content": "oi"})
    assert resposta.status_code == 404


def test_nao_e_possivel_mandar_mensagem_em_conversa_alheia(
    cliente, aplicacao, usuario_logado, ia_falsa
):
    outro = _segundo_usuario(aplicacao)
    conversa_alheia = outro.post("/api/chats").get_json()["id"]

    resposta = cliente.post(f"/api/chats/{conversa_alheia}/messages", json={"content": "oi"})
    assert resposta.status_code == 404
    assert db.query("SELECT * FROM messages") == []


def test_falha_da_ia_devolve_502_sem_perder_a_mensagem_do_usuario(
    cliente, conversa, ia_quebrada
):
    resposta = cliente.post(
        f"/api/chats/{conversa}/messages", json={"content": "mensagem importante"}
    )
    assert resposta.status_code == 502

    salvas = db.query("SELECT role, content FROM messages")
    assert len(salvas) == 1
    assert salvas[0]["role"] == "user"
    assert salvas[0]["content"] == "mensagem importante"


# --------------------------------------------------------------------------
# Título automático
# --------------------------------------------------------------------------


def test_primeira_mensagem_vira_titulo_da_conversa(cliente, conversa, ia_falsa):
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "Como puxar assunto?"})
    assert db.query_one("SELECT title FROM chats")["title"] == "Como puxar assunto?"


def test_titulo_longo_e_truncado(cliente, conversa, ia_falsa):
    texto = "x" * 100
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": texto})

    titulo = db.query_one("SELECT title FROM chats")["title"]
    assert titulo == "x" * 40 + "…"


def test_segunda_mensagem_nao_altera_o_titulo(cliente, conversa, ia_falsa):
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "primeira"})
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "segunda"})
    assert db.query_one("SELECT title FROM chats")["title"] == "primeira"


# --------------------------------------------------------------------------
# Renomear / apagar
# --------------------------------------------------------------------------


def test_renomear_conversa(cliente, conversa):
    resposta = cliente.post(f"/api/chats/{conversa}/title", json={"title": "Novo nome"})
    assert resposta.status_code == 200
    assert db.query_one("SELECT title FROM chats")["title"] == "Novo nome"


def test_renomear_com_titulo_vazio_e_recusado(cliente, conversa):
    resposta = cliente.post(f"/api/chats/{conversa}/title", json={"title": "  "})
    assert resposta.status_code == 400
    assert db.query_one("SELECT title FROM chats")["title"] == "New Chat"


def test_nao_e_possivel_renomear_conversa_alheia(cliente, aplicacao, usuario_logado):
    outro = _segundo_usuario(aplicacao)
    conversa_alheia = outro.post("/api/chats").get_json()["id"]

    cliente.post(f"/api/chats/{conversa_alheia}/title", json={"title": "invadido"})

    titulo = db.query_one("SELECT title FROM chats WHERE id = %s", (conversa_alheia,))["title"]
    assert titulo == "New Chat"


def test_apagar_conversa_remove_tambem_as_mensagens(cliente, conversa, ia_falsa):
    cliente.post(f"/api/chats/{conversa}/messages", json={"content": "oi"})

    assert cliente.post(f"/api/chats/{conversa}/delete").status_code == 200
    assert db.query("SELECT * FROM chats") == []
    assert db.query("SELECT * FROM messages") == []


def test_nao_e_possivel_apagar_conversa_alheia(cliente, aplicacao, usuario_logado):
    outro = _segundo_usuario(aplicacao)
    conversa_alheia = outro.post("/api/chats").get_json()["id"]

    cliente.post(f"/api/chats/{conversa_alheia}/delete")

    assert db.query_one("SELECT * FROM chats WHERE id = %s", (conversa_alheia,)) is not None


# --------------------------------------------------------------------------
# Aceite dos termos (contas antigas / termos atualizados)
# --------------------------------------------------------------------------


def test_conta_com_aceite_atual_nao_precisa_aceitar_de_novo(cliente, usuario_logado):
    assert cliente.get("/api/dashboard").get_json()["needsConsent"] is False


def test_conta_sem_aceite_nao_conversa_ate_aceitar(cliente, conversa, ia_falsa):
    db.execute("UPDATE users SET consent_version = NULL, terms_accepted_at = NULL")
    assert cliente.get("/api/dashboard").get_json()["needsConsent"] is True

    resposta = cliente.post(f"/api/chats/{conversa}/messages", json={"content": "oi"})
    assert resposta.status_code == 403
    assert resposta.get_json()["needsConsent"] is True
    assert db.query("SELECT * FROM messages") == []
    assert ia_falsa["chamadas"] == []

    # Aceite incompleto não libera.
    assert cliente.post("/api/account/consent", json={"acceptTerms": True}).status_code == 400

    assert cliente.post(
        "/api/account/consent", json={"acceptTerms": True, "acceptAi": True}
    ).status_code == 200
    assert cliente.get("/api/dashboard").get_json()["needsConsent"] is False
    assert db.query_one("SELECT terms_accepted_at FROM users")["terms_accepted_at"] is not None
    assert cliente.post(f"/api/chats/{conversa}/messages", json={"content": "oi"}).status_code == 200


def test_aceite_exige_login(cliente):
    assert cliente.post("/api/account/consent", json={"acceptTerms": True, "acceptAi": True}).status_code == 401


# --------------------------------------------------------------------------
# Texto -> fala (botão "ouvir")
# --------------------------------------------------------------------------

WAV_FALSO = b"RIFF....WAVEfmt "


def test_tts_exige_login(cliente):
    assert cliente.post("/api/tts", json={"text": "oi"}).status_code == 401


def test_tts_devolve_audio_com_a_voz_da_personalidade(cliente, usuario_logado, monkeypatch):
    chamadas = []

    def _falsa(text, personality):
        chamadas.append((text, personality))
        return WAV_FALSO

    monkeypatch.setattr("backend.routes.chats_api.synthesize_speech", _falsa)
    resposta = cliente.post("/api/tts", json={"text": " Fala, parça! ", "personality": "mathias"})

    assert resposta.status_code == 200
    assert resposta.mimetype == "audio/wav"
    assert resposta.data == WAV_FALSO
    assert chamadas == [("Fala, parça!", "mathias")]


def test_tts_personalidade_invalida_usa_a_padrao(cliente, usuario_logado, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "backend.routes.chats_api.synthesize_speech",
        lambda text, personality: chamadas.append(personality) or WAV_FALSO,
    )
    cliente.post("/api/tts", json={"text": "oi", "personality": "inexistente"})
    assert chamadas == ["trashtalker"]


def test_tts_recusa_texto_vazio_ou_longo_demais(cliente, usuario_logado, monkeypatch):
    monkeypatch.setattr("backend.routes.chats_api.synthesize_speech", lambda *_: WAV_FALSO)
    assert cliente.post("/api/tts", json={"text": "   "}).status_code == 400
    assert cliente.post("/api/tts", json={"text": "a" * 2001}).status_code == 400


def test_tts_sem_aceite_devolve_403(cliente, usuario_logado, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "backend.routes.chats_api.synthesize_speech",
        lambda *a: chamadas.append(a) or WAV_FALSO,
    )
    db.execute("UPDATE users SET consent_version = NULL")
    resposta = cliente.post("/api/tts", json={"text": "oi"})
    assert resposta.status_code == 403
    assert chamadas == []


def test_tts_falha_do_gemini_devolve_502(cliente, usuario_logado, monkeypatch):
    def _falha(*_):
        raise RuntimeError("cota esgotada (simulada)")

    monkeypatch.setattr("backend.routes.chats_api.synthesize_speech", _falha)
    resposta = cliente.post("/api/tts", json={"text": "oi"})
    assert resposta.status_code == 502
    assert "error" in resposta.get_json()
