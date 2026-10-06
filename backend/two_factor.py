"""TOTP, recuperação e login: decisões e consumo atômicos no PostgreSQL."""

import base64
import hashlib
import io
import logging
import math
import os
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken
from psycopg2.errors import InsufficientPrivilege
from psycopg2.extras import RealDictCursor

from backend import db
from backend.auth import create_session, verify_password

CHALLENGE_TTL = timedelta(minutes=5)
SETUP_TTL = timedelta(minutes=10)
ATTEMPT_WINDOW = timedelta(minutes=15)
MAX_ATTEMPTS = 5


class TwoFactorError(Exception):
    def __init__(self, message, status=400, code="two_factor_error", retry_after=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after = retry_after


def _now():
    return datetime.now(timezone.utc)


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cipher():
    try:
        return Fernet(os.environ.get("TOTP_ENCRYPTION_KEY", "").encode("ascii"))
    except (ValueError, UnicodeError):
        raise TwoFactorError(
            "Autenticação em dois fatores temporariamente indisponível. Tente mais tarde.",
            503, "two_factor_unavailable",
        ) from None


def _decrypt(value):
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeError):
        raise TwoFactorError(
            "Autenticação em dois fatores temporariamente indisponível. Tente mais tarde.",
            503, "two_factor_unavailable",
        ) from None


@contextmanager
def _transaction():
    # Rejeições previstas precisam COMMITAR os contadores de tentativas.
    # Falhas inesperadas fazem rollback, inclusive do consumo de códigos.
    rejection = None
    with db.get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                yield cursor
            except TwoFactorError as error:
                rejection = error
    if rejection:
        raise rejection


def _state(cursor, user_id):
    # Todos os chamadores bloqueiam primeiro users, na mesma ordem.
    try:
        cursor.execute("INSERT INTO user_two_factor (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        cursor.execute("SELECT * FROM user_two_factor WHERE user_id = %s", (user_id,))
        return cursor.fetchone()
    except InsufficientPrivilege:
        # Somente identificadores da conexão; nunca registrar DSN, senha ou dados da conta.
        # Leitura local do driver: não consulta uma transação que já foi abortada.
        try:
            params = cursor.connection.get_dsn_parameters()
            logging.getLogger(__name__).error(
                "DB_PERMISSION_DIAGNOSTIC table=user_two_factor user=%r database=%r host=%r",
                params.get("user"), params.get("dbname"), params.get("host"),
            )
        except Exception:
            logging.getLogger(__name__).error("DB_PERMISSION_DIAGNOSTIC metadata_unavailable")
        raise


def _check_limit(state, now):
    if state["blocked_until"] and state["blocked_until"] > now:
        seconds = math.ceil((state["blocked_until"] - now).total_seconds())
        raise TwoFactorError(
            "Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.",
            429, "two_factor_rate_limited", seconds,
        )


def _reject_factor(cursor, state, now, message="Código inválido, expirado ou já utilizado."):
    window = state["failure_window_at"]
    failures = state["failed_attempts"] if window and now - window < ATTEMPT_WINDOW else 0
    failures += 1
    blocked = now + ATTEMPT_WINDOW if failures >= MAX_ATTEMPTS else None
    cursor.execute(
        "UPDATE user_two_factor SET failed_attempts = %s, failure_window_at = %s, "
        "blocked_until = %s WHERE user_id = %s",
        (failures, window if failures > 1 else now, blocked, state["user_id"]),
    )
    if blocked:
        raise TwoFactorError("Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.",
                             429, "two_factor_rate_limited", 900)
    raise TwoFactorError(message, 400, "invalid_two_factor_code")


def _reset_failures(cursor, user_id):
    cursor.execute(
        "UPDATE user_two_factor SET failed_attempts = 0, failure_window_at = NULL, "
        "blocked_until = NULL WHERE user_id = %s", (user_id,),
    )


def _totp_step(secret, code, now, last_step=-1):
    if not re.fullmatch(r"[0-9]{6}", code):
        return None
    totp = pyotp.TOTP(secret)
    current = int(now.timestamp()) // 30
    # Tolerância de um intervalo de relógio; cada intervalo só é aceito uma vez.
    for step in (current + 1, current, current - 1):
        if step > last_step and pyotp.utils.strings_equal(totp.at(step * 30), code):
            return step
    return None


def _verify_factor(cursor, state, code, now):
    step = _totp_step(_decrypt(state["secret_encrypted"]), code, now, state["last_used_step"])
    if step is not None:
        cursor.execute("UPDATE user_two_factor SET last_used_step = %s WHERE user_id = %s",
                       (step, state["user_id"]))
    else:
        normalized = re.sub(r"[\s-]", "", code).lower()
        if not re.fullmatch(r"[a-f0-9]{32}", normalized):
            _reject_factor(cursor, state, now)
        cursor.execute(
            "DELETE FROM two_factor_recovery_codes WHERE user_id = %s AND code_hash = %s RETURNING code_hash",
            (state["user_id"], _digest(normalized)),
        )
        if cursor.fetchone() is None:
            _reject_factor(cursor, state, now)
    _reset_failures(cursor, state["user_id"])


def _recovery_codes(cursor, user_id):
    cursor.execute("DELETE FROM two_factor_recovery_codes WHERE user_id = %s", (user_id,))
    codes = [secrets.token_hex(16) for _ in range(8)]
    cursor.executemany(
        "INSERT INTO two_factor_recovery_codes (user_id, code_hash) VALUES (%s, %s)",
        [(user_id, _digest(code)) for code in codes],
    )
    return ["-".join(code[i:i + 8] for i in range(0, 32, 8)) for code in codes]


def _clear_pending(cursor, user_id):
    cursor.execute(
        "UPDATE user_two_factor SET pending_secret_encrypted = NULL, pending_expires_at = NULL, "
        "pending_session_hash = NULL, pending_password_version = NULL WHERE user_id = %s", (user_id,),
    )


def _rotate_session(cursor, user_id):
    cursor.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    cursor.execute("DELETE FROM two_factor_login_challenges WHERE user_id = %s", (user_id,))
    return create_session(user_id, cursor=cursor)


def password_login(email, password):
    with _transaction() as cursor:
        # Serializa login e ativação, evitando criar sessão sem 2FA durante a ativação.
        cursor.execute("SELECT * FROM users WHERE email = %s FOR UPDATE", (email,))
        user = cursor.fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            raise TwoFactorError("Email ou senha incorretos", 401, "invalid_credentials")
        state = _state(cursor, user["id"])
        if not state["secret_encrypted"]:
            return {"user": user, "session": create_session(user["id"], cursor=cursor)}
        _cipher()
        now = _now()
        _check_limit(state, now)
        challenge = secrets.token_urlsafe(32)
        cursor.execute(
            "INSERT INTO two_factor_login_challenges (token_hash, user_id, password_version, expires_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET "
            "token_hash = EXCLUDED.token_hash, password_version = EXCLUDED.password_version, "
            "expires_at = EXCLUDED.expires_at",
            (_digest(challenge), user["id"], _digest(user["password_hash"]), now + CHALLENGE_TTL),
        )
        return {"twoFactorRequired": True, "challengeToken": challenge, "expiresIn": 300}


def complete_login(challenge, code):
    token_hash = _digest(challenge)
    row = db.query_one("SELECT user_id FROM two_factor_login_challenges WHERE token_hash = %s", (token_hash,))
    if not row:
        raise TwoFactorError("Verificação expirada. Entre novamente com sua senha.", 400, "challenge_expired")
    with _transaction() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (row["user_id"],))
        user = cursor.fetchone()
        cursor.execute("SELECT * FROM two_factor_login_challenges WHERE token_hash = %s", (token_hash,))
        pending = cursor.fetchone()
        now = _now()
        if (not user or not pending or pending["expires_at"] <= now
                or pending["password_version"] != _digest(user["password_hash"])):
            raise TwoFactorError("Verificação expirada. Entre novamente com sua senha.", 400, "challenge_expired")
        state = _state(cursor, user["id"])
        if not state["secret_encrypted"]:
            raise TwoFactorError("Verificação expirada. Entre novamente com sua senha.", 400, "challenge_expired")
        _check_limit(state, now)
        _verify_factor(cursor, state, code, now)
        cursor.execute("DELETE FROM two_factor_login_challenges WHERE token_hash = %s", (token_hash,))
        return {"user": user, "session": create_session(user["id"], cursor=cursor)}


def status(user_id):
    state = db.query_one("SELECT secret_encrypted IS NOT NULL AS enabled FROM user_two_factor WHERE user_id = %s", (user_id,))
    count = db.query_one("SELECT count(*) AS total FROM two_factor_recovery_codes WHERE user_id = %s", (user_id,))
    try:
        _cipher()
        available = True
    except TwoFactorError:
        available = False
    return {"enabled": bool(state and state["enabled"]), "available": available,
            "recoveryCodesRemaining": count["total"]}


def manage(user_id, session_token, action, password="", code=""):
    """Ativação/gestão exigem sessão revalidada dentro da transação e reautenticação."""
    with _transaction() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (user_id,))
        user = cursor.fetchone()
        cursor.execute("SELECT id FROM sessions WHERE id = %s AND user_id = %s AND expires_at > now()",
                       (session_token, user_id))
        if not user or not cursor.fetchone():
            raise TwoFactorError("Não autenticado", 401, "unauthenticated")
        cipher = _cipher()
        state = _state(cursor, user_id)
        now = _now()
        _check_limit(state, now)
        if action != "confirm" and not verify_password(password, user["password_hash"]):
            _reject_factor(cursor, state, now, "Senha atual incorreta.")

        if action == "setup":
            if state["secret_encrypted"]:
                raise TwoFactorError("A autenticação em dois fatores já está ativa.", 409)
            secret = pyotp.random_base32()
            uri = pyotp.TOTP(secret).provisioning_uri(name=user["email"], issuer_name="Trash Talker")
            image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
            buffer = io.BytesIO()
            image.save(buffer)
            cursor.execute(
                "UPDATE user_two_factor SET pending_secret_encrypted = %s, pending_expires_at = %s, "
                "pending_session_hash = %s, pending_password_version = %s WHERE user_id = %s",
                (cipher.encrypt(secret.encode()).decode(), now + SETUP_TTL,
                 _digest(session_token), _digest(user["password_hash"]), user_id),
            )
            return {"manualKey": secret, "qrCodeDataUrl": "data:image/svg+xml;base64," +
                    base64.b64encode(buffer.getvalue()).decode(), "expiresIn": 600}, None

        if action == "confirm":
            if state["secret_encrypted"]:
                raise TwoFactorError("A autenticação em dois fatores já está ativa.", 409)
            if (not state["pending_secret_encrypted"] or state["pending_expires_at"] <= now
                    or state["pending_session_hash"] != _digest(session_token)
                    or state["pending_password_version"] != _digest(user["password_hash"])):
                raise TwoFactorError("Ativação expirada. Inicie a configuração novamente.", 400, "setup_expired")
            step = _totp_step(_decrypt(state["pending_secret_encrypted"]), code, now)
            if step is None:
                _reject_factor(cursor, state, now)
            cursor.execute("UPDATE user_two_factor SET secret_encrypted = pending_secret_encrypted, "
                           "last_used_step = %s WHERE user_id = %s", (step, user_id))
            _clear_pending(cursor, user_id)
            _reset_failures(cursor, user_id)
            codes = _recovery_codes(cursor, user_id)
            return {"enabled": True, "recoveryCodes": codes}, _rotate_session(cursor, user_id)

        if not state["secret_encrypted"]:
            raise TwoFactorError("A autenticação em dois fatores não está ativa.", 409)
        _verify_factor(cursor, state, code, now)
        if action == "disable":
            cursor.execute("UPDATE user_two_factor SET secret_encrypted = NULL, last_used_step = -1 WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM two_factor_recovery_codes WHERE user_id = %s", (user_id,))
            _clear_pending(cursor, user_id)
            return {"enabled": False}, _rotate_session(cursor, user_id)
        if action == "recovery-codes":
            return {"enabled": True, "recoveryCodes": _recovery_codes(cursor, user_id)}, _rotate_session(cursor, user_id)
        raise ValueError("Operação 2FA desconhecida")
