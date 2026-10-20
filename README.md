# Trash Talker — versão Python + HTML/CSS/JS puro

Autenticação em dois fatores: [configuração do Google Authenticator, migração e testes](docs/2fa.md).

Esta pasta (`python-app/`) é uma reescrita completa do projeto **Trash
Talker**, originalmente em TypeScript (Express + EJS + better-auth),
usando apenas:

- **Front-end**: HTML5 + CSS3 + JavaScript puro (sem React/Next/Vue/Angular
  e sem nenhuma etapa de build).
- **Back-end**: Python (Flask), com SQL cru via `psycopg2` (sem ORM),
  falando com o mesmo banco PostgreSQL (Neon ou outro).

O projeto TypeScript original não faz parte deste repositório. As
referências a arquivos como `src/routes/*.ts` ou `*.ejs` nesta
documentação e nos comentários do código apontam para aquela versão.

---

## 1. Análise do projeto original

Antes de converter, vale entender exatamente o que existia:

- **Não era um app React/Next.** O `AGENTS.md` do projeto original conta
  a história: a aplicação já tinha sido *simplificada* de uma versão
  antiga em Next.js/Drizzle/shadcn para uma versão bem mais simples em
  **Express + EJS** (HTML renderizado no servidor) + **JavaScript puro**
  no navegador. Ou seja, o trabalho de "sair do React" já tinha sido
  feito antes de eu começar - o que restava migrar era o **TypeScript no
  servidor** (Express, EJS, SQL cru via `pg`, autenticação via
  `better-auth`) e transformar os templates EJS em HTML estático puro.
- **Rotas / páginas**: `/`, `/login`, `/signup`, `/forgot-password`,
  `/reset-password`, `/privacy`, `/terms` (públicas; hoje também
  `/cookies`) e
  `/dashboard`, `/dashboard/chat/:id`, `/dashboard/account`,
  `/dashboard/settings`, `/dashboard/information` (exigem login).
- **Autenticação**: e-mail/senha via `better-auth`, sessão por cookie.
- **Dados**: PostgreSQL com tabelas `user`, `session`, `account`,
  `verification`, `chat`, `message` (geradas pelo `better-auth`).
- **Funcionalidade incompleta no original** (marcada como TODO "Stage 3"
  no próprio código): o envio de mensagem no chat não era persistido -
  a mensagem do usuário só aparecia localmente na tela, sem chamada ao
  servidor e sem resposta de IA de verdade. **Essa lacuna já foi fechada
  nesta versão**: hoje existe `POST /api/chats/<id>/messages`, que salva
  a mensagem, chama o Gemini (`backend/ai.py`) e persiste a resposta.
  Ver seção 6.

---

## 2. Estratégia de migração

**O que muda de arquitetura (e por quê):**

O EJS renderizava HTML no servidor, misturando marcação com dados do
banco (`<% chats.forEach(...) %>` etc.). Isso não existe em HTML puro.
A troca foi:

1. Cada `view.ejs` virou um arquivo `.html` estático, com a mesma
   marcação e as mesmas classes CSS (para o `app.css` continuar
   funcionando sem nenhuma alteração).
2. Tudo que era dinâmico (lista de conversas na sidebar, nome/avatar do
   usuário, mensagens de uma conversa) passou a ser buscado do
   backend via `fetch()`, depois de a página já estar carregada, e
   desenhado no DOM por JavaScript. Esse é o papel principal de
   `public/js/layout.js` (sidebar/usuário) e `public/js/chat.js`
   (mensagens).
3. Os `<form method="post">` que antes causavam um recarregamento de
   página completo (padrão de app "old school" renderizado no
   servidor) foram trocados por chamadas `fetch()` que conversam com
   uma **API JSON** em Python (pasta `backend/`). A navegação entre
   páginas continua sendo "de verdade" (não é uma SPA com roteamento
   por JavaScript) - existe um arquivo `.html` separado por rota,
   como no original.
4. **Autenticação**: `better-auth` foi substituído por uma
   implementação própria e simples em `backend/auth.py` (sessão por
   cookie + hash de senha com `werkzeug.security`). Ver o aviso na
   seção 5.
5. **"Estado" sem React**: como não há framework de front-end, cada
   página HTML tem seu próprio script de inicialização que roda no
   `DOMContentLoaded`: busca os dados que precisa via `fetch`, preenche
   o DOM, e liga os `addEventListener` dos formulários/botões. Não há
   um "estado global" - cada página busca de novo o que precisa quando
   é carregada, o que é normal (e mais simples de entender) em uma
   aplicação multi-página como esta.

**Ordem em que a conversão foi feita:**

1. Banco de dados (`schema.sql`) e camada de acesso (`db.py`).
2. Autenticação (`auth.py`) - é a peça mais sensível (segurança).
3. Endpoints da API (`routes/auth_api.py`, `routes/chats_api.py`),
   mapeando 1:1 cada rota que existia em `src/routes/*.ts`.
4. `app.py` juntando tudo e servindo os arquivos estáticos do frontend
   (hoje a montagem fica em `backend/factory.py`).
5. CSS copiado do original (`public/css/app.css`), que depois evoluiu.
6. JavaScript utilitário compartilhado (`api.js`, `avatar.js`,
   `theme.js`).
7. Uma página HTML por vez, com seu JS específico, comparando
   visualmente com o `.ejs` original até bater 1:1.

---

## 3. Estrutura de arquivos

```
python-app/
├── app.py                    # ponto de entrada: `app = create_app()` (python app.py / Vercel)
├── requirements.txt
├── .env.example              # modelo do .env (copie e preencha)
├── vercel.json               # deploy: rewrites das páginas, cache, maxDuration
├── backend/
│   ├── factory.py            # create_app(): registra as rotas e serve o frontend (page_routes)
│   ├── db.py                 # pool de conexões Postgres + helpers de query
│   ├── auth.py               # sessão por cookie, hash/política de senha, tokens de reset, aceite dos termos
│   ├── two_factor.py         # 2FA (TOTP, códigos de recuperação, limite de tentativas)
│   ├── ai.py                 # Gemini: resposta do chat (níveis de esforço); texto -> fala (TTS) via ElevenLabs
│   ├── personalities.py      # personas (TrashTalker, MathIAs), system prompts e "preguiça" do MathIAs
│   ├── email_utils.py        # envio do e-mail de redefinição via SMTP
│   ├── avatars.py            # lista fixa dos avatares ilustrados
│   ├── schema.sql            # esquema do banco (idempotente, rodado à mão)
│   └── routes/
│       ├── auth_api.py       # /api/login, /api/signup, /api/logout, /api/me, esqueci/redefinir senha
│       ├── chats_api.py      # /api/dashboard, /api/chats/..., /api/tts, /api/account/...
│       └── two_factor_api.py # /api/login/2fa, /api/2fa/...
├── public/                   # frontend estático (servido pelo Flask ou pela CDN da Vercel)
│   ├── index.html            # landing page ("/")
│   ├── login.html, signup.html, forgot-password.html, reset-password.html
│   ├── privacy.html, terms.html, cookies.html
│   ├── dashboard.html        # tela de boas-vindas (primeira mensagem cria a conversa)
│   ├── chat.html             # uma conversa (id vem da URL)
│   ├── account.html, settings.html
│   ├── css/app.css
│   ├── js/
│   │   ├── api.js            # fetch() com tratamento de erro + GET /api/dashboard compartilhado
│   │   ├── ui.js             # mensagens de status e eventos internos (emitTT)
│   │   ├── theme.js          # tema claro/escuro
│   │   ├── modal.js          # diálogo acessível (confirmar, renomear, aceite)
│   │   ├── avatar.js         # desenha avatar (foto/ilustrado/iniciais)
│   │   ├── auth.js           # validação de senha + esqueci senha/redefinir
│   │   ├── login.js / signup.js
│   │   ├── landing.js        # landing page única, adapta nav/CTA à sessão
│   │   ├── layout.js         # sidebar + guarda de autenticação + janela de aceite
│   │   ├── chat.js           # composer, mensagens, parar/desfazer envio
│   │   ├── personality-picker.js  # seletor de personalidade e esforço
│   │   ├── voice.js          # ditado por voz e botão "ouvir" (TTS)
│   │   ├── account.js        # formulário de perfil
│   │   ├── settings.js       # senha, exportação, exclusão de conta
│   │   └── two-factor.js     # telas do 2FA nas Configurações
│   ├── avatars/*.png, images/*.svg
│   └── logo-talker.svg, mathias-mark.svg, conversation-art*.svg
├── tests/                    # testes de API (pytest)
│   ├── conftest.py           # banco de teste isolado + fixtures
│   ├── test_auth_api.py
│   ├── test_chats_api.py
│   ├── test_account_api.py
│   └── test_two_factor_api.py
├── features/                 # especificações de comportamento (Behave, Gherkin pt-BR)
│   ├── environment.py
│   ├── autenticacao.feature, conversas.feature, conta.feature
│   └── steps/
└── docs/
    ├── processo.md           # como o projeto é desenvolvido + decisões técnicas e riscos
    ├── testes.md             # como rodar e escrever testes
    ├── 2fa.md                # Google Authenticator: configuração e contratos
    └── proposta-do-site.md   # proposta do produto
```

---

## 4. Como instalar e rodar

### Pré-requisitos

- Python 3.10+
- Um banco PostgreSQL (local, ou o mesmo Neon do projeto original)

Todos os comandos abaixo rodam a partir da pasta `python-app/`.

### Passo 1 - Ambiente virtual e dependências

```bash
cd python-app
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
python -m pip install -r requirements.txt
```

### Passo 2 - Banco de dados

Crie as tabelas rodando o schema fornecido:

```bash
psql "$DATABASE_URL" -f backend/schema.sql
```

O arquivo é idempotente: rode de novo sempre que ele mudar (novas
colunas/tabelas), sem perder dados.

> ⚠️ **Nunca cole uma connection string real neste arquivo.** Ela contém
> a senha do banco, e o repositório é público. Use sempre a variável de
> ambiente (`$DATABASE_URL`, lida do seu `.env`, que está no
> `.gitignore`).

> ⚠️ Este schema é **novo** (ver aviso de segurança na seção 5) - use um
> banco novo ou limpo, não o mesmo banco já populado pelo `better-auth`
> da versão TypeScript.

### Passo 3 - Variáveis de ambiente

```bash
cp .env.example .env
# edite o .env: DATABASE_URL é obrigatória; GEMINI_API_KEY para o chat;
# TOTP_ENCRYPTION_KEY para o 2FA; SMTP_* para o e-mail de redefinição
```

O que cada variável faz está comentado no próprio `.env.example`.

### Passo 4 - Rodar o servidor

```bash
python app.py
# Windows, sem ativar o venv: .\venv\Scripts\python.exe app.py
```

Acesse [http://localhost:5000](http://localhost:5000). O Flask serve o
front-end e a API na mesma porta - não é preciso rodar dois servidores
separados.

---

### Passo 5 - Rodar os testes (opcional, mas recomendado)

Os testes exigem um banco **separado** e recusam rodar sem ele. Resumo:

```bash
python -m pip install pytest behave
createdb trashtalker_test
export TEST_DATABASE_URL="postgresql://localhost/trashtalker_test"

python -m pytest      # 108 testes de API (inclui 2FA)
python -m behave      # 33 cenários de comportamento (Gherkin pt-BR)
```

Detalhes, incluindo Windows/PowerShell e como escrever novos testes:
**`docs/testes.md`**.

---

## 5. Avisos de migração (leia antes de usar em produção)

- **Senhas antigas não funcionam aqui.** O `better-auth` usa seu próprio
  formato de hash (scrypt) guardado na tabela `account`. Reproduzir esse
  formato exatamente exigiria reimplementar detalhes internos da
  biblioteca. Em vez disso, este projeto usa `werkzeug.security`
  (PBKDF2-SHA256), um padrão simples e seguro, mas incompatível com
  hashes antigos. **Contas precisam ser recriadas** (cadastro de novo)
  depois de migrar para este backend.
- **Sem CSRF token.** O `better-auth` original incluía proteção CSRF nas
  suas rotas internas. Como os formulários agora são JSON via `fetch`
  com cookie `SameSite=Lax` (em vez de formulários HTML tradicionais
  entre origens), o risco principal de CSRF (um site malicioso
  enviando um POST em nome do usuário) já é bem reduzido, mas não é uma
  proteção formal equivalente. Só as rotas de 2FA (`/api/login/2fa`,
  `/api/2fa/*`) conferem a origem da requisição (`Origin` e
  `Sec-Fetch-Site`). Se for expor este projeto publicamente, vale
  adicionar um token CSRF nas demais rotas que alteram dados.
- **E-mail de redefinição de senha é enviado de verdade**, via SMTP
  (`backend/email_utils.py`), desde que `SMTP_HOST`, `SMTP_USER` e
  `SMTP_PASSWORD` estejam preenchidos no `.env`. Se a configuração
  estiver faltando ou o envio falhar, a aplicação **não quebra**: ela
  imprime o link no terminal onde o `python app.py` está rodando, como
  fallback de desenvolvimento (ver `forgot_password()` em
  `routes/auth_api.py`).

---

## 6. Sugestões de melhorias futuras

Já implementados nesta migração (ver histórico do projeto):
envio de mensagens de verdade com resposta de IA via Google Gemini
(`POST /api/chats/<id>/messages`, `ai.py`), e-mail de verdade no
"esqueci minha senha" via SMTP (`email_utils.py`), exclusão de conta
de verdade (`POST /api/account/delete`), título automático da
conversa a partir da primeira mensagem e escolha de personalidade de IA
por conversa (`backend/personalities.py`, `GET /api/dashboard` →
`personalities`, `POST /api/chats/<id>/personality`) - hoje com duas
opções, TrashTalker e MathIAs, mas a lista foi desenhada para crescer
sem mudar o formato da API. No mesmo seletor há o nível de esforço
(`EFFORTS` em `ai.py`, `POST /api/chats/<id>/effort`), que troca o quanto
o Gemini pensa antes de responder: os dois usam o `gemini-3.5-flash-lite`, com
thinking "medium" no "Trash" (mais rápido) e "high" no "Talker" (respostas
mais caprichadas). O MathIAs ainda tem uma
regra própria de "preguiça" (`LAZY_*` em `personalities.py`): mensagem
acima de 800 caracteres ele não responde - solta uma fala entregando os
pontos e a conversa passa em definitivo para o TrashTalker, com o
seletor acompanhando a troca na hora (campo `handoffMessage` na resposta
de `POST /api/chats/<id>/messages`). Enquanto a IA responde, o campo de
mensagem fica bloqueado e a seta de enviar vira um botão de parar
(`setComposerPensando`/`pararDeResponder` em `js/chat.js`). Parar cancela
a rodada inteira: o texto volta para o campo e a conversa fica como
estava. Como a chamada ao Gemini é bloqueante e não dá para abortá-la no
servidor, quem faz o trabalho é `POST /api/chats/<id>/cancel` - ele apaga
a mensagem que estava sendo respondida, e `send_message` confere se ela
ainda existe antes de gravar a resposta.

Também já existem:

- **Autenticação em dois fatores** opcional (Google Authenticator), com
  códigos de recuperação e limite de tentativas próprio - ver
  [docs/2fa.md](docs/2fa.md).
- **Aceite dos termos versionado** (`CONSENT_VERSION` em `auth.py`):
  cadastro exige as duas confirmações (18+/termos e envio à IA), e quem
  ainda não aceitou a versão atual não conversa até aceitar (403 com
  `needsConsent`).
- **Botão "ouvir"** em cada resposta: `POST /api/tts` gera a fala com o
  ElevenLabs (`ELEVENLABS_API_KEY`), com uma voz por personalidade; se falhar, o navegador lê
  com a voz dele (`public/js/voice.js`).
- **Exportação dos dados** da conta em JSON (`GET /api/account/export`).

O que ainda falta:

1. **CSRF token e rate limiting no login/signup/forgot-password**,
   especialmente se o projeto for ficar acessível na internet (ver
   aviso na seção 5). Hoje não há limite de tentativas de senha no login
   nem de envio de mensagens; só as verificações do 2FA têm limite.
2. **Limitar o histórico enviado à IA.** `ai.py` manda a conversa
   inteira para o Gemini a cada mensagem; em conversas muito longas isso
   aumenta custo/latência e pode estourar o limite de tokens do
   modelo - vale truncar para as últimas N mensagens.
3. **Resposta em streaming** no chat. O indicador de "digitando..." e a
   revelação gradual do texto já existem, mas são só de fachada: o
   backend ainda espera a resposta inteira do Gemini antes de devolver
   qualquer coisa.

## 7. Histórico de alterações (16/10/2026)

Mudanças feitas hoje, em ordem de horário (Brasília, UTC-03:00).

### 17:19 - commit `ce0de10` "Descreva suas alterações"

- **Landing animada:** `public/index.html` reescrito com GSAP, ScrollTrigger e Lenis, usando `public/css/landing-motion.css` e `public/js/landing-motion.js`. A landing antiga ficou em `public/index.original.html` (instruções para voltar estão no comentário do topo do `index.html`).
- **Nova personalidade EvAIsto** em `backend/personalities.py`, com prompt próprio, voz de TTS própria (`TTS_VOICES` em `ai.py`), borda amarela para as mensagens (`.msg-evaisto` em `app.css`) e nome/logo no mapa `PERSONAS` de `public/js/chat.js`.
- **Ícones SVG novos:** `public/evaisto-completo.svg` e `public/mathias-completo.svg`.
- **Botão "ouvir"** (`public/js/voice.js`): a personalidade agora vem do atributo `data-personality` da bolha, e não mais de uma checagem fixa entre MathIAs e TrashTalker.
- **Modelo do chat** em `ai.py` trocado para `gemini-4-argon` (Trash e Talker), com as menções no README e em `docs/processo.md` atualizadas.

### 17:31 - commit `66bdd98` "Troca modelo do chat para gemini-3.5-flash-lite"

- **Modelo do chat** (Trash e Talker) trocado para `gemini-3.5-flash-lite`. O `gemini-4-argon` estava com a cota gratuita zerada (erro 429), e todo envio de mensagem voltava 502.

### Sem commit ainda

- **EvAIsto, prompt revisado:** tratamento de situações graves (CVV 188, SAMU 192), limite para flerte com resposta padrão, acolhimento quando a pessoa está triste, sem palavrões e sem emojis, no máximo uma pergunta por mensagem.
- **`.env.example` removido** do repositório. Horário não registrado.
- **Correções (18:56):** referências ao modelo do chat no README, em `docs/processo.md` (R-02) e no comentário de `ai.py` atualizadas para `gemini-3.5-flash-lite`; alias `SYSTEM_PROMPT` removido de `backend/personalities.py`. As menções ao `.env.example` foram mantidas.

## 8. Histórico de alterações (17/10/2026)

Mudanças feitas hoje, em ordem cronológica. Horário de Brasília (UTC-03:00).
O horário de cada bloco é o do registro no README; o commit `940ce68` ("mudança visual", 03:36) já inclui a maior parte do que está listado até ali.

### 03:36 - commit `940ce68` "mudança visual"

- **Configurações** (`settings.html`, `settings.js`, `theme.js`): menu de seções fixo com destaque da seção visível, troca de tema com revelação circular (View Transitions), formulário de senha recolhido, selo de status do 2FA (`two-factor.js`) e links de privacidade em lista.
- **Perfil** (`account.html`, `account.js`): prévia ao vivo com o balão da IA, avatar com efeito de entrada, interesses animados, barra "alterações não salvas" e rotação de avatares ilustrados no celular.
- **Movimento** (`app.css`): tokens de duração e curva (`--dur-*`, `--ease-*`); a regra antiga `transition: none` foi substituída; bloco respeita `prefers-reduced-motion`.
- **Conversa e personalidades** (`chat.js`, `chats_api.py`, `schema.sql`): nova coluna `messages.personality` gravada em cada resposta da IA (e na troca do MathIAs para o TrashTalker). Histórico antigo sem a coluna usa a personalidade atual da conversa. Avatares recortados em `public/avatars/persona-*.svg`.
- **Tela inicial** (`dashboard.html`, `chat.js`): saudação com o nome da pessoa e brilho na cor da personalidade escolhida. Os cards de personalidade e as sugestões foram removidos depois, a pedido do usuário.
- **Landing** (`landing-motion.js`, `landing-motion.css`): o início da animação do manifesto foi separado do pin, para as palavras acenderem quando a frase entra na tela. Em até 860px a seção usa `100svh`.

### Sem commit ainda (após 03:36)

- **Perfil, polish** (`account.html`, `account.js`, `app.css`):
  - prévia fixa no topo, com o avatar como botão de trocar foto;
  - seção "Sua foto" com uma fileira de avatares que rola na horizontal, em qualquer largura;
  - interesses sugeridos sem repetição nos chips, que mostram só os criados pela pessoa;
  - barra de salvar com "Alterações não salvas", botão **Desfazer** (sem recarregar a página) e **Salvar**;
  - títulos e dicas encurtados; barra do topo com "Seu perfil".
- **Migração do banco:** antes de publicar, rode no banco de produção `ALTER TABLE messages ADD COLUMN IF NOT EXISTS personality TEXT;` (ou o `backend/schema.sql` inteiro, que é idempotente).

### 03:57 - Perfil: volta ao layout anterior (sem commit ainda)

- O polish do perfil (commit `fe4af63`) foi desfeito: `account.html`, `account.js` e `app.css` voltaram ao estado do commit `940ce68`.
- **Foto de perfil num ícone só:** o avatar grande (com selo de câmera) abre um menu com os 6 avatares ilustrados e o botão "Enviar foto do aparelho". Fecha com Esc, clique fora ou ao escolher.
- `account.html` agora chama `app.css` e `account.js` com `?v=20261017`, para a Vercel não misturar HTML novo com CSS antigo em cache.

### 04:02 - Remoção de documentação e observações sobre deploy (sem commit ainda)

- **Arquivos `.md` apagados** (o README foi mantido): `DEPLOY_VERCEL.md`, `docs/processo.md`, `docs/testes.md`, `docs/2fa.md` e `docs/proposta-do-site.md`. Não havia arquivos de plano de IA no repositório; a remoção seguiu a escolha de apagar todos os `.md` exceto o README.
- **Efeito no site: nenhum.** Esses arquivos eram só documentação. A aplicação e a Vercel não os leem nem os servem. O `vercel.json` só cita `docs/**` para excluí-los dos arquivos da função.
- **Referências que ficaram quebradas** (não corrigidas ainda):
  - Links e a árvore de pastas do próprio README (`docs/2fa.md`, `docs/testes.md`, `docs/processo.md`, `docs/proposta-do-site.md`).
  - Comentários em `backend/auth.py` e `backend/routes/chats_api.py` que citam `docs/processo.md`.
  - Mensagens de erro em `tests/conftest.py` e `features/environment.py` que citam `docs/testes.md`.
- **Informações do `DEPLOY_VERCEL.md` que continuam valendo para publicar:**
  - Antes de publicar, rode `backend/schema.sql` no banco de produção. Ele é idempotente e cria `users.terms_accepted_at`, `users.consent_version` e `messages.personality`. Sem essas colunas, o login falha.
  - Configure as variáveis de ambiente na Vercel: `DATABASE_URL`, `GEMINI_API_KEY`, `TOTP_ENCRYPTION_KEY`, e, se usar redefinição de senha por e-mail, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` e `SMTP_FROM`. Nunca envie o arquivo `.env` ao repositório nem à Vercel.
  - Faça primeiro um deploy de Preview, valide as URLs e só depois promova para Production.
  - O 2FA exige o `schema.sql` atualizado antes de publicar o backend e as telas. Não faça rollback para um login sem verificação 2FA depois que houver contas protegidas.
