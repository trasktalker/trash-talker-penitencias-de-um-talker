"""
email_utils.py
===============
Envio de e-mails transacionais (redefinição de senha) via SMTP, usando
só a biblioteca padrão do Python (smtplib) - sem dependência nova.
"""

import os
import smtplib
from email.mime.text import MIMEText


def send_password_reset_email(to_email, reset_url):
    """
    Manda o e-mail de redefinição de senha. Levanta uma exceção se a
    configuração de SMTP estiver incompleta ou se o envio falhar -
    quem chama decide o que fazer (ver forgot_password() em
    routes/auth_api.py, que cai para um fallback de console).
    """
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM") or smtp_user

    if not smtp_host or not smtp_user or not smtp_password:
        raise RuntimeError(
            "Configuração de SMTP incompleta "
            "(defina SMTP_HOST, SMTP_USER e SMTP_PASSWORD no .env)"
        )

    body = (
        "Oi!\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no "
        "Trash Talker.\n\n"
        "Clique no link abaixo para escolher uma nova senha (válido "
        "por 1 hora):\n\n"
        f"{reset_url}\n\n"
        "Se você não pediu essa redefinição, pode ignorar este "
        "e-mail - sua senha continua a mesma.\n"
        "\n--\n"
        # Rodapé de identificação. Sem link de "descadastrar" de propósito:
        # este é um e-mail transacional (só sai quando alguém pede a
        # redefinição) - não existe lista de envio da qual sair.
        "Você recebeu este e-mail porque foi pedida a redefinição de senha "
        "da conta ligada a este endereço no Trash Talker, um projeto "
        "acadêmico. Não enviamos e-mails de marketing.\n"
        "Dúvidas: trashtalkpodcast123456@gmail.com\n"
    )

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = "Redefinir sua senha - Trash Talker"
    message["From"] = smtp_from
    message["To"] = to_email

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_from, [to_email], message.as_string())
