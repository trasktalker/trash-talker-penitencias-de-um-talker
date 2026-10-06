"""
Testes dos endpoints de autenticação (routes/auth_api.py).

Cobrem cadastro, login, sessão, logout, "esqueci minha senha" e
redefinição de senha - incluindo os caminhos de erro, que são onde
moram os riscos de segurança.
"""

from backend import db
from conftest import SENHA_PADRAO, cadastrar, logar


# --------------------------------------------------------------------------
# Cadastro
# --------------------------------------------------------------------------


def test_cadastro_valido_cria_usuario(cliente):
    resposta = cadastrar(cliente)
    assert resposta.status_code == 201
    assert resposta.get_json() == {"ok": True}

    linha = db.query_one("SELECT * FROM users WHERE email = %s", ("pessoa@exemplo.com",))
    assert linha is not None
    assert linha["name"] == "Pessoa"


def test_cadastro_nao_guarda_senha_em_texto_puro(cliente):
    cadastrar(cliente)
    linha = db.query_one("SELECT * FROM users WHERE email = %s", ("pessoa@exemplo.com",))
    assert SENHA_PADRAO not in linha["password_hash"]
    assert linha["password_hash"].startswith(("pbkdf2:", "scrypt:"))


def test_cadastro_normaliza_email_para_minusculas(cliente):
    cadastrar(cliente, email="  PESSOA@Exemplo.COM  ")
    assert db.query_one(
        "SELECT id FROM users WHERE email = %s", ("pessoa@exemplo.com",)
    ) is not None


def test_cadastro_com_email_invalido_e_recusado(cliente):
    resposta = cadastrar(cliente, email="nao-e-um-email")
    assert resposta.status_code == 400
    assert "error" in resposta.get_json()


def test_cadastro_com_senha_curta_e_recusado(cliente):
    resposta = cadastrar(cliente, senha="1234")
    assert resposta.status_code == 400


def test_cadastro_sem_nome_e_recusado(cliente):
    resposta = cadastrar(cliente, nome="   ")
    assert resposta.status_code == 400


def test_cadastro_sem_os_aceites_e_recusado_e_nao_cria_conta(cliente):
    assert cadastrar(cliente, aceites=False).status_code == 400
    # Só um dos dois também não vale, nem valores "parecidos" com True.
    for parcial in ({"acceptTerms": True}, {"acceptAi": True}, {"acceptTerms": "true", "acceptAi": 1}):
        corpo = {"email": "pessoa@exemplo.com", "password": SENHA_PADRAO, "name": "Pessoa", **parcial}
        assert cliente.post("/api/signup", json=corpo).status_code == 400
    assert db.query("SELECT id FROM users") == []


def test_cadastro_registra_data_e_versao_do_aceite(cliente):
    from backend.auth import CONSENT_VERSION

    cadastrar(cliente)
    linha = db.query_one("SELECT terms_accepted_at, consent_version FROM users")
    assert linha["terms_accepted_at"] is not None
    assert linha["consent_version"] == CONSENT_VERSION


def test_cadastro_com_email_repetido_devolve_409(cliente):
    cadastrar(cliente)
    resposta = cadastrar(cliente, nome="Outra Pessoa")
    assert resposta.status_code == 409
    quantidade = db.query_one(
        "SELECT count(*) AS total FROM users WHERE email = %s", ("pessoa@exemplo.com",)
    )
    assert quantidade["total"] == 1


def test_cadastro_nao_loga_automaticamente(cliente):
    """Comportamento herdado do projeto original: o usuário vai para /login."""
    cadastrar(cliente)
    assert cliente.get("/api/me").status_code == 401


# --------------------------------------------------------------------------
# Login e sessão
# --------------------------------------------------------------------------


def test_login_valido_cria_sessao_e_cookie(cliente):
    cadastrar(cliente)
    resposta = logar(cliente)

    assert resposta.status_code == 200
    assert resposta.get_json()["user"]["email"] == "pessoa@exemplo.com"
    assert "session_token" in resposta.headers.get("Set-Cookie", "")
    assert db.query("SELECT * FROM sessions") != []


def test_login_nao_devolve_hash_da_senha(cliente):
    cadastrar(cliente)
    usuario = logar(cliente).get_json()["user"]
    assert "password_hash" not in usuario


def test_login_com_senha_errada_devolve_401(cliente):
    cadastrar(cliente)
    resposta = logar(cliente, senha="senha-errada-mas-longa")
    assert resposta.status_code == 401
    assert db.query("SELECT * FROM sessions") == []


def test_login_com_email_inexistente_devolve_401(cliente):
    resposta = logar(cliente, email="ninguem@exemplo.com")
    assert resposta.status_code == 401


def test_me_sem_sessao_devolve_401(cliente):
    assert cliente.get("/api/me").status_code == 401


def test_me_com_sessao_devolve_usuario(cliente, usuario_logado):
    resposta = cliente.get("/api/me")
    assert resposta.status_code == 200
    assert resposta.get_json()["user"]["id"] == usuario_logado["id"]


def test_logout_remove_sessao_do_banco(cliente, usuario_logado):
    assert cliente.post("/api/logout").status_code == 200
    assert db.query("SELECT * FROM sessions") == []
    assert cliente.get("/api/me").status_code == 401


def test_sessao_expirada_nao_autentica(cliente, usuario_logado):
    """A sessão é validada por `expires_at > now()` - forçamos o vencimento."""
    db.execute("UPDATE sessions SET expires_at = now() - interval '1 day'")
    assert cliente.get("/api/me").status_code == 401


# --------------------------------------------------------------------------
# Esqueci minha senha
# --------------------------------------------------------------------------


def test_esqueci_senha_com_email_existente_gera_token(cliente):
    cadastrar(cliente)
    resposta = cliente.post("/api/forgot-password", json={"email": "pessoa@exemplo.com"})
    assert resposta.status_code == 200
    assert len(db.query("SELECT * FROM password_reset_tokens")) == 1


def test_esqueci_senha_com_email_inexistente_tambem_devolve_ok(cliente):
    """
    Proteção contra enumeração de contas: a resposta precisa ser idêntica
    exista ou não o e-mail, senão dá para descobrir quem tem conta.
    """
    resposta = cliente.post("/api/forgot-password", json={"email": "ninguem@exemplo.com"})
    assert resposta.status_code == 200
    assert resposta.get_json() == {"ok": True}
    assert db.query("SELECT * FROM password_reset_tokens") == []


# --------------------------------------------------------------------------
# Redefinição de senha
# --------------------------------------------------------------------------


def _token_de_redefinicao(cliente):
    cliente.post("/api/forgot-password", json={"email": "pessoa@exemplo.com"})
    return db.query_one("SELECT * FROM password_reset_tokens")["token"]


def test_redefinicao_troca_a_senha(cliente):
    cadastrar(cliente)
    token = _token_de_redefinicao(cliente)

    resposta = cliente.post(
        "/api/reset-password", json={"token": token, "newPassword": "Nova-Senha-999"}
    )
    assert resposta.status_code == 200
    assert logar(cliente, senha=SENHA_PADRAO).status_code == 401
    assert logar(cliente, senha="Nova-Senha-999").status_code == 200


def test_redefinicao_com_token_invalido_e_recusada(cliente):
    cadastrar(cliente)
    resposta = cliente.post(
        "/api/reset-password", json={"token": "token-inventado", "newPassword": "Nova-Senha-999"}
    )
    assert resposta.status_code == 400


def test_token_de_redefinicao_so_pode_ser_usado_uma_vez(cliente):
    cadastrar(cliente)
    token = _token_de_redefinicao(cliente)

    primeira = cliente.post(
        "/api/reset-password", json={"token": token, "newPassword": "Nova-Senha-999"}
    )
    segunda = cliente.post(
        "/api/reset-password", json={"token": token, "newPassword": "Outra-Senha-888"}
    )
    assert primeira.status_code == 200
    assert segunda.status_code == 400


def test_token_de_redefinicao_expirado_e_recusado(cliente):
    cadastrar(cliente)
    token = _token_de_redefinicao(cliente)
    db.execute("UPDATE password_reset_tokens SET expires_at = now() - interval '1 hour'")

    resposta = cliente.post(
        "/api/reset-password", json={"token": token, "newPassword": "Nova-Senha-999"}
    )
    assert resposta.status_code == 400


def test_redefinicao_com_senha_curta_e_recusada(cliente):
    cadastrar(cliente)
    token = _token_de_redefinicao(cliente)
    resposta = cliente.post(
        "/api/reset-password", json={"token": token, "newPassword": "123"}
    )
    assert resposta.status_code == 400


def test_redefinicao_derruba_sessoes_abertas(cliente, aplicacao):
    """
    Regressão da correção de segurança: antes, quem já estava logado em
    outro dispositivo continuava logado depois da vítima redefinir a
    senha - o que anulava o efeito da troca.
    """
    cadastrar(cliente)
    outro_dispositivo = aplicacao.test_client()
    assert logar(outro_dispositivo).status_code == 200
    assert outro_dispositivo.get("/api/me").status_code == 200

    token = _token_de_redefinicao(cliente)
    cliente.post("/api/reset-password", json={"token": token, "newPassword": "Nova-Senha-999"})

    assert outro_dispositivo.get("/api/me").status_code == 401
