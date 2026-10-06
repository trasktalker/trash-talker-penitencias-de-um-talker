"""2FA com PostgreSQL real: sessão, recuperação, limites e concorrência."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from cryptography.fernet import Fernet

from backend import db, two_factor
from conftest import SCHEMA_PATH, SENHA_PADRAO, cadastrar, logar


@pytest.fixture(autouse=True)
def key_and_clock(monkeypatch):
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    clock = [datetime.now(timezone.utc)]
    monkeypatch.setattr(two_factor, "_now", lambda: clock[0])
    return clock


def setup(cliente):
    result = cliente.post("/api/2fa/setup", json={"password": SENHA_PADRAO})
    assert result.status_code == 200, result.get_json()
    assert result.headers["Cache-Control"] == "no-store"
    return result.get_json()["manualKey"]


def activate(cliente):
    secret = setup(cliente)
    result = cliente.post("/api/2fa/confirm", json={"code": pyotp.TOTP(secret).at(two_factor._now())})
    assert result.status_code == 200, result.get_json()
    return secret, result.get_json()["recoveryCodes"]


def challenge(cliente, senha=SENHA_PADRAO):
    result = logar(cliente, senha=senha)
    assert result.status_code == 202, result.get_json()
    assert result.get_json()["twoFactorRequired"] is True
    assert "user" not in result.get_json()
    return result.get_json()["challengeToken"]


def verify(cliente, token, code):
    return cliente.post("/api/login/2fa", json={"challengeToken": token, "code": code})


def test_estado_inicial_e_setup_nao_ativam_antes_da_confirmacao(cliente, usuario_logado):
    assert cliente.get("/api/2fa/status").get_json() == {
        "enabled": False, "available": True, "recoveryCodesRemaining": 0,
    }
    secret = setup(cliente)
    state = db.query_one("SELECT * FROM user_two_factor")
    assert state["secret_encrypted"] is None
    assert secret not in state["pending_secret_encrypted"]
    assert two_factor._decrypt(state["pending_secret_encrypted"]) == secret
    assert logar(cliente).status_code == 200


def test_setup_exige_sessao_senha_e_json_mesma_origem(cliente, usuario_logado):
    assert cliente.post("/api/2fa/setup", json={"password": "errada"}).status_code == 400
    assert cliente.post("/api/2fa/setup", json={"password": SENHA_PADRAO},
                        headers={"Origin": "https://invasor.example"}).status_code == 403
    assert cliente.post("/api/2fa/setup", data={"password": SENHA_PADRAO}).status_code == 415
    assert cliente.post("/api/2fa/setup", json={"password": SENHA_PADRAO},
                        headers={"Origin": "http://localhost"}).status_code == 200
    cliente.post("/api/logout")
    assert cliente.get("/api/2fa/status").status_code == 401
    assert cliente.post("/api/2fa/setup", json={"password": SENHA_PADRAO}).status_code == 401


def test_ativacao_gera_oito_hashes_e_revoga_sessoes_anteriores(cliente, usuario_logado, aplicacao):
    other = aplicacao.test_client()
    logar(other)
    old_cookie = cliente.get_cookie("session_token").value
    secret, codes = activate(cliente)
    assert len(codes) == len(set(codes)) == 8
    rows = db.query("SELECT code_hash FROM two_factor_recovery_codes")
    assert len(rows) == 8
    assert all(code.replace("-", "") not in str(rows) for code in codes)
    assert cliente.get_cookie("session_token").value != old_cookie
    assert other.get("/api/me").status_code == 401
    assert cliente.get("/api/me").status_code == 200
    state = db.query_one("SELECT * FROM user_two_factor")
    assert state["pending_secret_encrypted"] is None
    assert secret not in state["secret_encrypted"]
    assert cliente.post("/api/2fa/setup", json={"password": SENHA_PADRAO}).status_code == 409


def test_confirmacao_exige_mesma_sessao_e_setup_vigente(cliente, usuario_logado, aplicacao, key_and_clock):
    secret = setup(cliente)
    other = aplicacao.test_client()
    logar(other)
    code = pyotp.TOTP(secret).at(two_factor._now())
    assert other.post("/api/2fa/confirm", json={"code": code}).get_json()["code"] == "setup_expired"
    key_and_clock[0] += timedelta(minutes=11)
    result = cliente.post("/api/2fa/confirm", json={"code": code})
    assert result.get_json()["code"] == "setup_expired"
    assert not cliente.get("/api/2fa/status").get_json()["enabled"]


def test_setup_substituido_rejeita_chave_antiga(cliente, usuario_logado):
    old = setup(cliente)
    new = setup(cliente)
    assert old != new
    # Verifica diretamente que o QR anterior não é a chave cadastrada.
    state = db.query_one("SELECT * FROM user_two_factor")
    assert two_factor._decrypt(state["pending_secret_encrypted"]) == new


def test_senha_correta_nao_cria_sessao_antes_do_codigo(cliente, usuario_logado, key_and_clock):
    secret, _ = activate(cliente)
    cliente.post("/api/logout")
    token = challenge(cliente)
    assert cliente.get("/api/me").status_code == 401
    assert cliente.get("/api/dashboard").status_code == 401
    assert db.query("SELECT * FROM sessions") == []
    assert token not in str(db.query("SELECT * FROM two_factor_login_challenges"))
    key_and_clock[0] += timedelta(seconds=30)
    result = verify(cliente, token, pyotp.TOTP(secret).at(two_factor._now()))
    assert result.status_code == 200
    assert result.get_json()["user"]["id"] == usuario_logado["id"]
    assert cliente.get("/api/me").status_code == 200
    assert db.query("SELECT * FROM two_factor_login_challenges") == []


def test_codigo_errado_antigo_e_reutilizado_nao_autenticam(cliente, usuario_logado, key_and_clock):
    secret, _ = activate(cliente)
    token = challenge(cliente)
    reused = pyotp.TOTP(secret).at(two_factor._now())
    expired = pyotp.TOTP(secret).at(two_factor._now() - timedelta(minutes=2))
    assert verify(cliente, token, "invalido").status_code == 400
    assert verify(cliente, token, expired).status_code == 400
    assert verify(cliente, token, reused).status_code == 400
    assert cliente.get("/api/me").status_code == 401
    key_and_clock[0] += timedelta(seconds=30)
    fresh = pyotp.TOTP(secret).at(two_factor._now())
    assert verify(cliente, token, fresh).status_code == 200
    new_token = challenge(cliente)
    assert verify(cliente, new_token, fresh).status_code == 400


@pytest.mark.parametrize("offset", [-30, 30])
def test_tolerancia_de_um_intervalo_de_relogio(cliente, usuario_logado, key_and_clock, offset):
    secret, _ = activate(cliente)
    key_and_clock[0] += timedelta(seconds=90)
    token = challenge(cliente)
    assert verify(cliente, token, pyotp.TOTP(secret).at(two_factor._now() + timedelta(seconds=offset))).status_code == 200


def test_desafio_expira_em_cinco_minutos(cliente, usuario_logado, key_and_clock):
    _, codes = activate(cliente)
    token = challenge(cliente)
    key_and_clock[0] += timedelta(minutes=5)
    assert verify(cliente, token, codes[0]).get_json()["code"] == "challenge_expired"
    assert len(db.query("SELECT * FROM two_factor_recovery_codes")) == 8


def test_recuperacao_uso_unico_sem_desativar_2fa(cliente, usuario_logado):
    _, codes = activate(cliente)
    token = challenge(cliente)
    assert verify(cliente, token, codes[0].upper()).status_code == 200
    status = cliente.get("/api/2fa/status").get_json()
    assert status["enabled"] and status["recoveryCodesRemaining"] == 7
    assert verify(cliente, token, codes[1]).status_code == 400
    assert verify(cliente, challenge(cliente), codes[0]).status_code == 400


def test_limite_persistente_nao_reinicia_com_novo_desafio(cliente, usuario_logado, key_and_clock):
    _, codes = activate(cliente)
    for i in range(5):
        token = challenge(cliente)
        result = verify(cliente, token, "invalido")
        assert result.status_code == (429 if i == 4 else 400)
    assert result.headers["Retry-After"] == "900"
    assert logar(cliente).status_code == 429
    assert verify(cliente, token, codes[0]).status_code == 429
    key_and_clock[0] += timedelta(minutes=16)
    assert verify(cliente, challenge(cliente), codes[0]).status_code == 200
    assert db.query_one("SELECT failed_attempts FROM user_two_factor")["failed_attempts"] == 0


def test_novo_setup_nao_reinicia_limite(cliente, usuario_logado):
    setup(cliente)
    for _ in range(4):
        assert cliente.post("/api/2fa/confirm", json={"code": "invalido"}).status_code == 400
    setup(cliente)
    assert cliente.post("/api/2fa/confirm", json={"code": "invalido"}).status_code == 429


def test_desativar_exige_senha_e_fator(cliente, usuario_logado):
    _, codes = activate(cliente)
    assert cliente.post("/api/2fa/disable", json={"password": "errada", "code": codes[0]}).status_code == 400
    assert cliente.post("/api/2fa/disable", json={"password": SENHA_PADRAO, "code": "invalido"}).status_code == 400
    result = cliente.post("/api/2fa/disable", json={"password": SENHA_PADRAO, "code": codes[0]})
    assert result.status_code == 200 and result.get_json()["enabled"] is False
    assert db.query("SELECT * FROM two_factor_recovery_codes") == []
    assert db.query_one("SELECT secret_encrypted FROM user_two_factor")["secret_encrypted"] is None
    assert logar(cliente).status_code == 200


def test_renovar_invalida_codigos_antigos(cliente, usuario_logado):
    _, codes = activate(cliente)
    result = cliente.post("/api/2fa/recovery-codes", json={"password": SENHA_PADRAO, "code": codes[0]})
    assert result.status_code == 200
    new_codes = result.get_json()["recoveryCodes"]
    assert len(new_codes) == 8 and not set(codes) & set(new_codes)
    token = challenge(cliente)
    assert verify(cliente, token, codes[1]).status_code == 400
    assert verify(cliente, token, new_codes[0]).status_code == 200


def test_reset_senha_preserva_2fa_revoga_sessoes_e_desafios(cliente, usuario_logado, aplicacao):
    _, codes = activate(cliente)
    other = aplicacao.test_client()
    pending = challenge(other)
    cliente.post("/api/forgot-password", json={"email": "pessoa@exemplo.com"})
    reset_token = db.query_one("SELECT token FROM password_reset_tokens")["token"]
    result = cliente.post("/api/reset-password", json={"token": reset_token, "newPassword": "Nova-Senha-999"})
    assert result.status_code == 200
    assert cliente.get("/api/me").status_code == 401
    assert verify(other, pending, codes[0]).get_json()["code"] == "challenge_expired"
    assert verify(cliente, challenge(cliente, "Nova-Senha-999"), codes[0]).status_code == 200
    assert cliente.get("/api/2fa/status").get_json()["enabled"]


def test_troca_de_senha_invalida_setup_pendente(cliente, usuario_logado):
    secret = setup(cliente)
    cliente.post("/api/account/password", json={"currentPassword": SENHA_PADRAO, "newPassword": "Nova-Senha-999"})
    result = cliente.post("/api/2fa/confirm", json={"code": pyotp.TOTP(secret).at(two_factor._now())})
    assert result.get_json()["code"] == "setup_expired"


def test_dados_publicos_e_exportacao_nao_revelam_segredos(cliente, usuario_logado):
    secret, codes = activate(cliente)
    for url in ("/api/me", "/api/dashboard", "/api/2fa/status", "/api/account/export"):
        result = cliente.get(url)
        assert result.status_code == 200
        text = result.get_data(as_text=True)
        assert secret not in text and "secret_encrypted" not in text and "password_hash" not in text
        assert all(code not in text for code in codes)


def test_sem_chave_login_com_2fa_falha_fechado(cliente, usuario_logado, monkeypatch):
    activate(cliente)
    cliente.post("/api/logout")
    monkeypatch.delenv("TOTP_ENCRYPTION_KEY")
    assert logar(cliente).status_code == 503
    assert cliente.get("/api/me").status_code == 401


def test_chave_incorreta_nao_libera_recuperacao(cliente, usuario_logado, monkeypatch):
    _, codes = activate(cliente)
    token = challenge(cliente)
    monkeypatch.setenv("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert verify(cliente, token, codes[0]).status_code == 503
    assert len(db.query("SELECT * FROM two_factor_recovery_codes")) == 8


def test_sem_chave_contas_sem_2fa_continuam_funcionando(cliente, usuario_logado, monkeypatch):
    monkeypatch.delenv("TOTP_ENCRYPTION_KEY")
    assert logar(cliente).status_code == 200
    assert not cliente.get("/api/2fa/status").get_json()["available"]
    assert cliente.post("/api/2fa/setup", json={"password": SENHA_PADRAO}).status_code == 503


@pytest.mark.parametrize("body", [[], {"code": 123456}, {"code": "a" * 129}, {"password": {}}, None])
def test_entrada_invalida_rejeitada_sem_erro_500(cliente, usuario_logado, body):
    result = cliente.post("/api/2fa/confirm", json=body, content_type="application/json")
    assert result.status_code == 400


def test_concorrencia_consume_desafio_e_codigo_apenas_uma_vez(cliente, usuario_logado, aplicacao):
    _, codes = activate(cliente)
    cliente.post("/api/logout")
    token = challenge(cliente)
    def attempt(_):
        with aplicacao.test_client() as client:
            return verify(client, token, codes[0]).status_code
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(attempt, range(2))) == [200, 400]
    assert len(db.query("SELECT * FROM sessions")) == 1
    assert len(db.query("SELECT * FROM two_factor_recovery_codes")) == 7


def test_erro_interno_reverte_consumo_do_codigo(cliente, usuario_logado, monkeypatch):
    _, codes = activate(cliente)
    token = challenge(cliente)
    def fail(*_args, **_kwargs):
        raise RuntimeError("falha simulada ao criar sessão")
    with monkeypatch.context() as patch:
        patch.setattr(two_factor, "create_session", fail)
        with pytest.raises(RuntimeError, match="falha simulada"):
            verify(cliente, token, codes[0])
    assert verify(cliente, token, codes[0]).status_code == 200


def test_schema_idempotente_preserva_conta_2fa(cliente, usuario_logado):
    activate(cliente)
    with open(SCHEMA_PATH, encoding="utf-8") as source:
        db.execute(source.read())
    assert cliente.get("/api/2fa/status").get_json()["enabled"]
    assert len(db.query("SELECT * FROM two_factor_recovery_codes")) == 8


def test_excluir_conta_limpa_tabelas_2fa(cliente, usuario_logado, aplicacao):
    activate(cliente)
    challenge(aplicacao.test_client())
    result = cliente.post("/api/account/delete", json={"password": SENHA_PADRAO, "confirmation": "eu quero excluir essa conta"})
    assert result.status_code == 200
    for table in ("user_two_factor", "two_factor_recovery_codes", "two_factor_login_challenges"):
        assert db.query("SELECT * FROM " + table) == []
