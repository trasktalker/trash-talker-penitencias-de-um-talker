"""API de configuração e verificação do Google Authenticator (TOTP)."""

import os

from flask import Blueprint, g, jsonify, request

from backend import two_factor
from backend.auth import SESSION_COOKIE_NAME, require_auth, set_session_cookie
from backend.routes.auth_api import _public_user

two_factor_api = Blueprint("two_factor_api", __name__, url_prefix="/api")


@two_factor_api.before_request
def protect_mutations():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    allowed = {request.host_url.rstrip("/"), os.environ.get("FRONTEND_ORIGIN", "").rstrip("/")}
    origin = request.headers.get("Origin")
    if (origin and origin not in allowed) or request.headers.get("Sec-Fetch-Site") == "cross-site":
        return jsonify({"error": "Origem da solicitação não permitida."}), 403
    if not request.is_json:
        return jsonify({"error": "Envie os dados em JSON."}), 415
    if request.content_length and request.content_length > 16384:
        return jsonify({"error": "Solicitação muito grande."}), 413


@two_factor_api.after_request
def no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@two_factor_api.app_errorhandler(two_factor.TwoFactorError)
def handle_two_factor_error(error):
    response = jsonify({"error": str(error), "code": error.code})
    response.status_code = error.status
    response.headers["Cache-Control"] = "no-store"
    if error.retry_after is not None:
        response.headers["Retry-After"] = str(error.retry_after)
    return response


def _body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise two_factor.TwoFactorError("Dados inválidos.")
    return body


def _text(body, field, maximum):
    value = body.get(field, "")
    if not isinstance(value, str) or len(value) > maximum:
        raise two_factor.TwoFactorError("Dados inválidos.")
    return value


@two_factor_api.route("/login/2fa", methods=["POST"])
def verify_login():
    body = _body()
    result = two_factor.complete_login(_text(body, "challengeToken", 128), _text(body, "code", 128).strip())
    response = jsonify({"user": _public_user(result["user"])})
    return set_session_cookie(response, *result["session"])


@two_factor_api.route("/2fa/status", methods=["GET"])
@require_auth
def two_factor_status():
    return jsonify(two_factor.status(g.user["id"]))


def _manage(action):
    body = _body()
    result, session = two_factor.manage(
        g.user["id"], request.cookies.get(SESSION_COOKIE_NAME), action,
        password=_text(body, "password", 1024), code=_text(body, "code", 128).strip(),
    )
    response = jsonify(result)
    return set_session_cookie(response, *session) if session else response


@two_factor_api.route("/2fa/setup", methods=["POST"])
@require_auth
def setup():
    return _manage("setup")


@two_factor_api.route("/2fa/confirm", methods=["POST"])
@require_auth
def confirm():
    return _manage("confirm")


@two_factor_api.route("/2fa/disable", methods=["POST"])
@require_auth
def disable():
    return _manage("disable")


@two_factor_api.route("/2fa/recovery-codes", methods=["POST"])
@require_auth
def regenerate_recovery_codes():
    return _manage("recovery-codes")
