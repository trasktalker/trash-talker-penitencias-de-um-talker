# Processo de desenvolvimento

Como o Trash Talker é desenvolvido, quais decisões técnicas foram
tomadas e por quê, e quais riscos continuam abertos.

Para rodar os testes, ver `testes.md`.

---

## 1. Estrutura do projeto

```
python-app/
├── backend/      # API Flask + acesso ao banco
├── frontend/     # HTML/CSS/JS estático (sem build)
├── tests/        # testes de API (pytest)
├── features/     # especificações de comportamento (Behave)
└── docs/         # este arquivo e testes.md
```

O backend não tem ORM nem framework de frontend. É uma escolha, não uma
omissão: o projeto é pequeno, é base de um TCC, e SQL cru + JavaScript
puro tornam cada camada legível sem conhecimento prévio de biblioteca.

---

## 2. Convenções

**Python**
- SQL sempre parametrizado (`%s` + tupla). Nunca concatenar valor em
  string de query - é o que protege contra SQL Injection.
- Toda rota que exige login usa `@require_auth`; dentro dela, `g.user`
  está garantidamente preenchido.
- Toda rota que toca uma conversa usa `get_owned_chat(chat_id, user_id)`
  e devolve **404** (não 403) quando não pertence ao usuário - 403
  confirmaria que o id existe.
- Comentário explica *por quê*, não *o quê*. O código já diz o quê.

**Testes**
- Nomes em português, descrevendo o comportamento:
  `test_falha_da_ia_devolve_502_sem_perder_a_mensagem_do_usuario`.
- Um comportamento por teste.
- Gherkin em português, com `# language: pt`.

**Git**
- Nunca commitar `.env`, credencial, token ou chave de API.
- Mensagem de commit deve dizer o que mudou. Ver a seção 6 (dívida).

---

## 3. Fluxo de trabalho

Para qualquer alteração de comportamento:

1. Entender o comportamento atual (ler o código, rodar o que existe).
2. Escrever ou ajustar o teste que descreve o comportamento desejado.
3. Implementar.
4. Rodar **as duas** suítes: `python -m pytest` e `python -m behave`.
5. Se algo quebrou, achar a causa raiz antes de mexer no teste.
6. Atualizar a documentação se o comportamento externo mudou.

### Definição de pronto

Uma alteração está pronta quando:

- [ ] `python -m pytest` passa inteiro
- [ ] `python -m behave` passa inteiro
- [ ] a aplicação sobe com `python app.py` e as páginas respondem
- [ ] comportamento novo ou alterado tem teste
- [ ] nenhuma credencial entrou no repositório
- [ ] documentação afetada foi atualizada

---

## 4. Decisões técnicas

Registro das decisões cujo motivo não é óbvio pelo código.

### D-01 — `create_app()` como application factory

**Situação:** `app.py` tinha um `app = create_app()` solto no nível do
módulo, e `create_app()` chamava `db.init_pool()`. Consequência:
**importar** `app.py` já abria conexão com o Postgres. Sem
`DATABASE_URL` no ambiente, o import explodia - o que tornava
impossível rodar testes, ler as rotas ou fazer análise estática.

**Decisão:** remover a instanciação do nível do módulo. `create_app()`
virou uma *application factory*, padrão que o Flask reconhece
nativamente.

**Impacto:** `python app.py` funciona igual. `flask --app app routes`
encontra a fábrica sozinho (verificado). Para um servidor WSGI, aponte
para a fábrica: `gunicorn "app:create_app()"`.

### D-02 — Trocar a senha derruba as sessões

**Situação:** a sessão é validada apenas pelo token na tabela
`sessions`; ela não consulta o hash da senha. Ou seja, quem já estivesse
logado continuava logado depois da troca de senha - inclusive alguém com
acesso indevido. Isso esvazia o propósito de trocar a senha.

**Decisão:** `auth.destroy_all_sessions(user_id, exceto=None)`, ligada
nos dois fluxos:

- **Reset por e-mail** (`/api/reset-password`): derruba **todas** as
  sessões. Quem redefine por e-mail geralmente perdeu o acesso -
  possivelmente porque outra pessoa entrou na conta.
- **Troca estando logado** (`/api/account/password`): derruba as
  outras, **mantém a atual**. Quem acabou de trocar a senha na própria
  tela não deve ser deslogado dela.

**Alteração deliberada de comportamento externo.** Registrada aqui por
isso. Coberta por teste de regressão nas duas suítes.

### D-03 — Banco de teste separado, com trava

Ver `testes.md`, seção 3. Resumo: os testes truncam tabelas; rodar isso
no banco errado apagaria dados reais. As travas recusam rodar sem
`TEST_DATABASE_URL` ou quando ela é igual a `DATABASE_URL`.

### D-04 — PostgreSQL nos testes, não SQLite

Ver `testes.md`, seção 3. Resumo: `db.py` depende de recursos exclusivos
do Postgres. Testar em SQLite validaria um código diferente do que roda
em produção.

### D-05 — `thinking_budget=0` no Gemini

Modelos Gemini 2.5+ fazem raciocínio interno por padrão, e esses tokens
saem do **mesmo** orçamento do `max_output_tokens`. Sem desligar, a
resposta visível vinha cortada no meio. Um chatbot de conversa não
precisa de raciocínio profundo. Ver `backend/ai.py`.

### D-06 — 404 em vez de 403 para recurso de outro usuário

Um 403 confirmaria que aquele id existe. O 404 não distingue "não
existe" de "não é seu", o que não entrega informação a quem esteja
sondando ids.

---

## 5. Divergências

Quando o requisito, a implementação e o teste discordarem, **não escolha
em silêncio**. Registre a divergência aqui, decida com base em
evidência, e só então altere o código ou o teste.

Nenhuma divergência aberta no momento.

---

## 6. Riscos e dívida técnica

| ID | Risco | Severidade | Situação |
|---|---|---|---|
| R-01 | Connection string do Neon commitada em texto puro no README, presente no histórico do Git desde o commit inicial, em repositório público | **Crítica** | Removida do arquivo atual. **Continua no histórico.** Exige rotação da senha no painel do Neon - remover o arquivo não resolve |
| R-02 | Nome do modelo em `ai.py` (`gemini-3.5-flash`) não confirmado como existente | Alta | Em aberto. Se estiver errado, todo envio de mensagem devolve 502. Verificar com `client.models.list()` |
| R-03 | Sem rate limiting em `/api/login`, `/api/signup`, `/api/forgot-password` | Alta | Em aberto. Permite força bruta de senha e abuso do envio de e-mail |
| R-04 | Sem token CSRF nas rotas que alteram dados | Média | Em aberto. Mitigado parcialmente por cookie `SameSite=Lax` + JSON via `fetch`, mas não é proteção equivalente |
| R-05 | Avatar em base64 sem limite de tamanho, gravado em `users.image` | Média | Em aberto. Um payload grande incha a linha e toda resposta que a devolve |
| R-06 | Sem limite de tamanho de requisição (`MAX_CONTENT_LENGTH`) | Média | Em aberto |
| R-07 | Histórico inteiro da conversa vai para o Gemini a cada mensagem | Média | Em aberto. Conversa longa = custo, latência e risco de estourar o limite de tokens. Truncar para as últimas N mensagens |
| R-08 | `traceback.print_exc()` em `chats_api.send_message` | Baixa | Em aberto. Debug temporário da migração Groq→Gemini; trocar por `logging` |
| R-09 | Sem ferramenta de migração de banco - `schema.sql` é rodado à mão | Baixa | Aceito conscientemente. O arquivo usa `IF NOT EXISTS`/`ADD COLUMN IF NOT EXISTS` e é idempotente |
| R-10 | Frontend sem nenhum teste automatizado | Baixa | Aceito no escopo atual |
| R-11 | Mensagens de commit pouco descritivas ("bazinga", "TCC amanhã") | Baixa | Em aberto. Dificulta entender a evolução do projeto |

### R-01 em detalhe

Este é o item que exige ação fora do código. Uma credencial que foi
commitada em repositório público deve ser considerada **comprometida**,
independentemente de ter sido removida depois: o histórico do Git
preserva o valor, e repositórios públicos são varridos por bots.

Ordem correta de remediação:

1. **Rotacionar a senha no painel do Neon** (isto invalida a credencial
   vazada - é o passo que realmente resolve).
2. Atualizar o `DATABASE_URL` no `.env` local.
3. Só então, opcionalmente, reescrever o histórico do Git.

Remover a linha do arquivo sem fazer o passo 1 dá falsa sensação de
segurança.

---

## 7. Onde encontrar as coisas

| Procurando por | Vá para |
|---|---|
| Rotas da API | `backend/routes/auth_api.py`, `backend/routes/chats_api.py` |
| Sessão, senha, tokens de reset | `backend/auth.py` |
| Acesso ao banco | `backend/db.py` |
| Estrutura das tabelas | `backend/schema.sql` |
| System prompt do TrashTalker | `backend/ai.py` |
| Páginas e arquivos estáticos | `backend/app.py` (mapa `page_routes`) |
| Configuração necessária | `backend/.env.example` |
