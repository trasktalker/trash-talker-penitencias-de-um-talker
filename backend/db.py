"""
db.py
=====
Camada de acesso ao banco de dados (PostgreSQL).

Filosofia mantida do projeto original (ver AGENTS.md): SQL cru, sem ORM,
sem query builder. Aqui usamos `psycopg2` com um pool de conexões simples
e uma função `query()` que devolve sempre uma lista de dicionários
(uma linha = um dict), parecido com o helper `sql` tagged-template que
existia em TypeScript (src/db.ts).

Diferença importante em relação ao `sql` do TypeScript original: em Python
não temos "tagged template literals", então em vez de escrever

    sql`SELECT * FROM chat WHERE id = ${chatId}`

escrevemos

    query("SELECT * FROM chats WHERE id = %s", (chat_id,))

O psycopg2 substitui os `%s` pelos valores de forma segura (usando
parâmetros de verdade, não concatenação de string), o que evita SQL
Injection - a mesma proteção que o template tag original oferecia.
"""

import os
import secrets
from contextlib import contextmanager

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

# Pool de conexões: em vez de abrir/fechar uma conexão nova a cada
# requisição (lento), mantemos algumas conexões abertas e "emprestadas"
# sob demanda. minconn=1 garante ao menos uma conexão pronta; maxconn=10
# é suficiente para uma aplicação pequena como esta.
_pool = None


def init_pool(database_url=None):
    """
    Cria o pool de conexões. Chamado uma vez, na inicialização do app.py.

    `database_url` é opcional e existe para os testes automatizados: quando
    não é passado (o caso de produção/desenvolvimento), o valor continua
    vindo da variável de ambiente DATABASE_URL exatamente como antes. Os
    testes passam a URL do banco de teste explicitamente (ver
    tests/conftest.py), sem depender de sobrescrever variável de ambiente
    do processo - o que evita o risco de uma suíte rodar por acidente
    contra o banco real.
    """
    global _pool
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("A variável de ambiente DATABASE_URL não foi definida")
    _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, dsn=database_url)


def close_pool():
    """
    Fecha todas as conexões do pool. Não é usado no ciclo normal da
    aplicação (o processo do Flask vive enquanto o servidor vive), só
    pelos testes, para não deixar conexões abertas entre sessões.
    """
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_connection():
    """
    Context manager que pega uma conexão do pool e devolve ao final.

    O Neon (Postgres serverless) fecha conexões ociosas no servidor sem
    avisar o cliente - a conexão só se revela morta quando alguém tenta
    usá-la (psycopg2.InterfaceError/OperationalError). Nesse caso ela é
    descartada (close=True) em vez de voltar pro pool, senão o próximo
    request pegaria a mesma conexão morta de novo.
    """
    if _pool is None:
        raise RuntimeError("init_pool() precisa ser chamado antes de usar o banco")
    conn = _pool.getconn()
    broken = False
    try:
        yield conn
        conn.commit()
    except Exception:
        broken = True
        try:
            conn.rollback()
        except Exception:
            pass  # conexão já morta - não há o que desfazer
        raise
    finally:
        _pool.putconn(conn, close=broken)


def _with_retry(run):
    """
    Roda `run()` (uma operação de banco) e tenta de novo uma única vez se
    a falha for de conexão (ver get_connection) - assim uma conexão que
    caiu por ociosidade não vira um erro visível pro usuário; ele só
    percebe se a segunda tentativa também falhar.
    """
    try:
        return run()
    except (psycopg2.InterfaceError, psycopg2.OperationalError):
        return run()


def query(sql_text, params=()):
    """
    Executa uma query e devolve todas as linhas como lista de dicts.
    Use para SELECT.
    """

    def run():
        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql_text, params)
                return [dict(row) for row in cur.fetchall()]

    return _with_retry(run)


def query_one(sql_text, params=()):
    """Como query(), mas devolve só a primeira linha (ou None)."""
    rows = query(sql_text, params)
    return rows[0] if rows else None


def execute(sql_text, params=()):
    """
    Executa um comando que não devolve linhas (INSERT/UPDATE/DELETE sem
    RETURNING). Use quando não precisar do resultado.
    """

    def run():
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text, params)

    return _with_retry(run)


def new_id():
    """
    Gera um id único em formato texto, usado como chave primária em todas
    as tabelas (equivalente ao @paralleldrive/cuid2 do projeto original,
    só que usando apenas a biblioteca padrão do Python).
    """
    return secrets.token_hex(12)


def get_owned_chat(chat_id, user_id):
    """
    Busca uma conversa (chat) garantindo que ela pertence ao usuário logado.
    Retorna None se não existir ou se pertencer a outro usuário - assim
    evitamos que um usuário acesse/edite a conversa de outra pessoa apenas
    adivinhando o id (equivalente a getOwnedChat() em src/db.ts).
    """
    return query_one(
        "SELECT * FROM chats WHERE id = %s AND user_id = %s",
        (chat_id, user_id),
    )
