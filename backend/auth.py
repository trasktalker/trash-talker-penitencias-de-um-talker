"""
auth.py
=======
Substitui a biblioteca "better-auth" (usada no projeto TypeScript original)
por uma implementação própria, simples e explícita, de autenticação por
sessão com cookie.

O que este módulo faz:
  1. Hash e verificação de senha (via werkzeug, que já vem com o Flask).
  2. Criação/leitura/destruição de sessões (tabela `sessions`), com um
     cookie httponly guardando o token da sessão.
  3. Geração e validação de tokens de "esqueci minha senha"
     (tabela `password_reset_tokens`, equivalente à tabela `verification`
     do better-auth).
  4. Um decorator `require_auth` para proteger rotas que só usuários
     logados podem acessar (equivalente a src/require-auth.ts).

Aviso de migração (leia isto!):
  O better-auth usa seu próprio algoritmo de hash de senha (scrypt com um
  formato específico) e sua própria tabela `account` para guardar esse
  hash. Não é possível reaproduzir esse formato de forma simples em Python
  sem reimplementar a biblioteca inteira. Por isso este projeto usa um
  esquema de banco de dados NOVO (ver schema.sql) com hash via
  werkzeug.security (PBKDF2-SHA256). Isso significa que contas criadas
  pela versão antiga (TypeScript) não vão funcionar aqui - é preciso
  recriar as contas depois de rodar schema.sql em um banco novo (ou
  limpo). Para um projeto de TCC ainda em desenvolvimento, isso é o
  caminho mais simples e seguro.
"""

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from backend.db import execute, query_one

SESSION_COOKIE_NAME = "session_token"
SESSION_DURATION = timedelta(days=30)
RESET_TOKEN_DURATION = timedelta(hours=1)

PASSWORD_MIN_LENGTH = 8
_SPECIAL_CHAR_RE = re.compile(r"[^A-Za-z0-9]")

# Versão dos termos/consentimento em vigor. Trocar este valor quando a
# Política ou os Termos mudarem de forma relevante faz todo mundo ver de
# novo a janela de aceite (ver needs_consent e public/js/layout.js).
CONSENT_VERSION = "2026-10-06"


def has_required_consents(body):
    """
    As duas confirmações obrigatórias, usadas no cadastro e no novo aceite:
    18+ com Termos/Política, e o envio das mensagens à IA (consentimento
    específico - as conversas podem ter dado sensível, LGPD art. 11).
    Só vale True de verdade, não string/número "truthy".
    """
    return body.get("acceptTerms") is True and body.get("acceptAi") is True


def needs_consent(user):
    """True se a conta ainda não aceitou a versão atual dos termos."""
    return (user or {}).get("consent_version") != CONSENT_VERSION


def hash_password(password):
    """Gera o hash de uma senha para salvar no banco."""
    return generate_password_hash(password)


def verify_password(password, password_hash):
    """Confere se `password` corresponde ao hash salvo no banco."""
    return check_password_hash(password_hash, password)


def get_password_requirement_failures(password):
    """
    Confere `password` contra a política de senha forte do app e devolve
    a lista de mensagens (uma por regra não cumprida, em pt-BR) - lista
    vazia significa senha válida. Único lugar onde a regra é definida no
    backend, usado no cadastro, na redefinição por e-mail e na troca de
    senha estando logado (routes/auth_api.py e routes/chats_api.py), para
    não divergir entre os três. Espelha PASSWORD_RULES em public/js/auth.js.
    """
    password = password or ""
    failures = []
    if len(password) < PASSWORD_MIN_LENGTH:
        failures.append(
            f"A senha deve ter no mínimo {PASSWORD_MIN_LENGTH} caracteres"
        )
    if not re.search(r"[A-Z]", password):
        failures.append("A senha deve conter pelo menos 1 letra maiúscula")
    if not re.search(r"[a-z]", password):
        failures.append("A senha deve conter pelo menos 1 letra minúscula")
    if not re.search(r"[0-9]", password):
        failures.append("A senha deve conter pelo menos 1 número")
    if not _SPECIAL_CHAR_RE.search(password):
        failures.append(
            "A senha deve conter pelo menos 1 caractere especial (ex.: !@#$%^&*)"
        )
    return failures


def create_session(user_id, cursor=None):
    """
    Cria uma nova sessão para o usuário e devolve o token (que vai para o
    cookie). Equivalente ao que o better-auth fazia internamente ao logar.
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_DURATION
    run = cursor.execute if cursor is not None else execute
    # Faxina das sessões vencidas a cada login, sem precisar de cron.
    # ponytail: varredura da tabela inteira; criar índice em expires_at se ela crescer muito.
    run("DELETE FROM sessions WHERE expires_at < now()")
    run("INSERT INTO sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
        (token, user_id, expires_at))
    return token, expires_at


def destroy_session(token):
    """Remove a sessão do banco (usado no logout)."""
    if token:
        execute("DELETE FROM sessions WHERE id = %s", (token,))


def destroy_all_sessions(user_id, exceto=None):
    """
    Apaga todas as sessões do usuário, opcionalmente preservando uma
    (`exceto` = token da sessão atual).

    Motivo: quando a senha de uma conta muda, qualquer sessão aberta em
    outro dispositivo/navegador continuava valendo, porque a sessão é
    validada só pelo token na tabela `sessions` - ela não consulta o
    hash da senha. Ou seja: uma pessoa que tivesse acesso indevido à
    conta continuava dentro mesmo depois da vítima trocar a senha, o que
    esvazia o propósito da troca. Ver docs/processo.md (decisão D-02).
    """
    if exceto:
        execute(
            "DELETE FROM sessions WHERE user_id = %s AND id <> %s",
            (user_id, exceto),
        )
    else:
        execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))


def get_session_user(req):
    """
    Lê o cookie de sessão da requisição e devolve o usuário correspondente
    (ou None se não houver sessão válida). Equivalente a getSessionUser()
    em src/require-auth.ts.
    """
    token = req.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    # Uma consulta só (JOIN) em vez de sessão + usuário separados: isto roda
    # em toda rota autenticada, e cada ida ao Neon é uma viagem de rede.
    return query_one(
        "SELECT u.id, u.name, u.email, u.image, u.display_name, u.pronoun, u.interests, "
        "u.consent_version "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.id = %s AND s.expires_at > now()",
        (token,),
    )


def set_session_cookie(response, token, expires_at):
    """Anexa o cookie de sessão em uma resposta Flask."""
    is_production = os.environ.get("FLASK_ENV") == "production" or os.environ.get("VERCEL") == "1"
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="Lax",
        secure=is_production,
        expires=expires_at,
        path="/",
    )
    return response


def clear_session_cookie(response):
    """Remove o cookie de sessão (usado no logout)."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


def require_auth(view_func):
    """
    Decorator usado em toda rota que exige usuário logado (equivalente ao
    middleware requireAuth do Express). Diferente da versão original (que
    redirecionava para /login), aqui devolvemos um JSON 401, já que estas
    rotas agora são uma API consumida via fetch() pelo JavaScript do
    frontend - é o próprio frontend que decide redirecionar para /login
    quando recebe esse 401 (ver public/js/layout.js).
    """

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        user = get_session_user(request)
        if not user:
            return jsonify({"error": "Não autenticado"}), 401
        g.user = user
        return view_func(*args, **kwargs)

    return wrapper


def create_password_reset_token(user_id):
    """Gera um token de redefinição de senha válido por 1 hora."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + RESET_TOKEN_DURATION
    execute("DELETE FROM password_reset_tokens WHERE expires_at < now()")
    execute(
        "INSERT INTO password_reset_tokens (token, user_id, expires_at) "
        "VALUES (%s, %s, %s)",
        (token, user_id, expires_at),
    )
    return token


def consume_password_reset_token(token):
    """
    Valida um token de redefinição de senha e já marca como usado.
    Devolve o user_id se válido, ou None se inválido/expirado/já usado.
    """
    row = query_one(
        "SELECT * FROM password_reset_tokens "
        "WHERE token = %s AND used = false AND expires_at > now()",
        (token,),
    )
    if not row:
        return None
    execute(
        "UPDATE password_reset_tokens SET used = true WHERE token = %s",
        (token,),
    )
    return row["user_id"]
