# Testes

Este documento explica como rodar os testes do Trash Talker e como
escrever novos. Para as decisões de processo por trás deles, ver
`processo.md`.

---

## 1. Os dois tipos de teste

O projeto tem duas suítes, com propósitos diferentes:

| Suíte | Ferramenta | Onde | Responde a pergunta |
|---|---|---|---|
| Testes de API | `pytest` | `tests/` | "Este endpoint faz a coisa certa, inclusive quando dá errado?" |
| Testes de comportamento | `Behave` | `features/` | "A funcionalidade que prometemos ao usuário funciona?" |

As duas exercitam a aplicação pelo `test_client()` do Flask - ou seja,
pela mesma API HTTP que o JavaScript do frontend consome. Nenhuma delas
chama funções internas para forçar um resultado.

**O que NÃO é testado automaticamente:** o frontend (HTML/CSS/JS) e a
qualidade das respostas do Gemini. Ver seção 6.

---

## 2. Pré-requisitos

```bash
python -m pip install pytest behave
```

> No Windows/PowerShell, use `python -m pip` (com o `-m`) para garantir
> que o pacote vá para o ambiente virtual ativo, e não para o Python do
> sistema.

E um **banco PostgreSQL separado** do que você usa para desenvolver.

---

## 3. Por que um banco separado é obrigatório

Os testes **apagam todas as tabelas** antes de cada caso (`TRUNCATE ...
CASCADE`), para que um teste nunca dependa do estado deixado por outro.
Apontar isso para o seu banco de desenvolvimento apagaria seus dados de
verdade.

Por isso existem três travas:

1. Sem `TEST_DATABASE_URL` definida, a suíte **para** com uma mensagem
   explicando o motivo - ela nunca cai no `DATABASE_URL` do `.env`.
2. Se `TEST_DATABASE_URL` for **igual** a `DATABASE_URL`, a suíte
   também para.
3. O banco de teste é passado explicitamente para `create_app()`, em vez
   de sobrescrever variável de ambiente do processo.

Se você vir uma dessas mensagens, a trava está fazendo o trabalho dela.
Não contorne: crie o banco separado.

### Por que Postgres e não SQLite em memória

Seria mais rápido, mas `db.py` usa recursos que só existem no Postgres:
placeholders `%s` do psycopg2, coluna `TEXT[]` (`users.interests`),
`now()`, `= ANY(%s)` e `RealDictCursor`. Rodar em SQLite exigiria
reescrever a camada de dados só para os testes - e aí os testes estariam
validando um código diferente do que roda em produção, que é justamente
o que queremos evitar.

---

## 4. Como rodar

### Preparar o banco (uma vez)

```bash
createdb trashtalker_test
```

O schema é aplicado automaticamente pela própria suíte, a partir de
`backend/schema.sql`. Não precisa rodar `psql -f schema.sql` à mão.

### Definir a variável

Linux / macOS:
```bash
export TEST_DATABASE_URL="postgresql://localhost/trashtalker_test"
```

Windows / PowerShell:
```powershell
$env:TEST_DATABASE_URL = "postgresql://localhost/trashtalker_test"
```

### Rodar

```bash
python -m pytest                          # tudo
python -m pytest tests/test_auth_api.py   # um arquivo
python -m pytest -k redefinicao           # por nome

python -m behave                                    # tudo
python -m behave features/conversas.feature         # uma funcionalidade
python -m behave -n "Enviar uma mensagem"           # um cenário
```

---

## 5. A IA nunca é chamada de verdade

`ai.generate_reply()` faz uma chamada de rede paga ao Gemini. Nos testes
ela é substituída por uma função que devolve texto fixo:

- **pytest**: fixtures `ia_falsa` (responde) e `ia_quebrada` (levanta
  exceção), em `tests/conftest.py`.
- **Behave**: `before_scenario` em `features/environment.py`, mais o
  passo `Dado que a IA está indisponível` para os cenários de falha.

Isso é deliberado. O que está sob teste é o comportamento da aplicação
**em volta** da IA: a mensagem foi persistida? o título automático foi
gerado? quando a IA cai, a resposta é 502 **sem perder o que o usuário
escreveu**? A qualidade do texto que o modelo devolve não é algo que um
teste automatizado consiga afirmar.

---

## 6. Cobertura atual

**Coberto** (64 testes pytest + 33 cenários Behave):

- Cadastro: validações, e-mail duplicado, normalização, hash da senha
- Login/logout: credenciais, cookie de sessão, sessão expirada
- Esqueci a senha: geração de token, uso único, expiração, proteção
  contra enumeração de contas
- Redefinição de senha e invalidação de sessões
- Conversas: criar, ler, renomear, apagar, título automático
- Mensagens: persistência, histórico enviado à IA, mensagem vazia,
  **falha da IA sem perda de dados**
- **Isolamento entre usuários**: ler, renomear, apagar e mandar mensagem
  em conversa alheia - todos barrados
- Conta: perfil, interesses (deduplicação, limite, truncamento), troca
  de senha, exportação de dados, exclusão em cascata

**Não coberto:**

| Lacuna | Por quê |
|---|---|
| Frontend (HTML/CSS/JS) | Exigiria Selenium/Playwright - fora do escopo atual |
| Qualidade das respostas do Gemini | Não é verificável por asserção |
| Envio real de e-mail SMTP | Depende de servidor externo |
| Carga / concorrência | Nenhum teste de desempenho |
| Reconexão do pool ao Neon | `_with_retry` em `db.py` não tem teste |

---

## 7. Escrevendo novos testes

**Testes de API (`tests/`)**: use as fixtures prontas do `conftest.py` -
`cliente`, `usuario_logado`, `conversa`, `ia_falsa`, `ia_quebrada`. O
banco já vem limpo (`banco_limpo` é `autouse`).

```python
def test_alguma_coisa(cliente, conversa, ia_falsa):
    resposta = cliente.post(f"/api/chats/{conversa}/messages",
                            json={"content": "oi"})
    assert resposta.status_code == 200
```

**Cenários Behave (`features/`)**: todo `.feature` começa com
`# language: pt` e usa `Funcionalidade`, `Cenário`, `Dado`, `Quando`,
`Então`, `E`. Antes de criar um passo novo, procure em
`features/steps/` - a maioria já existe.

Descreva **comportamento observável**, não implementação:

- ✅ `Então eu devo receber uma resposta do TrashTalker`
- ❌ `Então generate_reply deve ser chamada com o histórico`

### Regra ao ver um teste falhar

Não altere o teste só para ele passar. Primeiro determine se quem está
errado é o teste ou o código. Se for divergência real entre o que o
requisito diz, o que o código faz e o que o teste espera, registre a
divergência em vez de escolher em silêncio (ver `processo.md`, seção 5).
