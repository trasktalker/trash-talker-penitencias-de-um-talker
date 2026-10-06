# Google Authenticator no Trash Talker

O 2FA é opcional por conta. Usa TOTP de 6 dígitos, SHA-1 e intervalos de
30 segundos, compatível com Google Authenticator e outros apps TOTP.
Não exige cadastro de aplicativo nem credenciais no Google Cloud.

## Preparar o ambiente e publicar

Execute os comandos a partir de `python-app/`, com Python 3.10 ou superior.

1. Instale as dependências: `python -m pip install -r requirements.txt`.
2. Gere uma chave **uma única vez por ambiente**:

   ```powershell
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

3. Guarde a chave em um gerenciador de segredos e configure
   `TOTP_ENCRYPTION_KEY` no ambiente do backend. Na Vercel, use
   **Settings > Environment Variables**. Todas as instâncias que acessam
   o mesmo banco devem usar a mesma chave. Não salve a chave no código,
   em commits ou em arquivos públicos.
4. Antes de publicar o código, aplique o esquema atualizado ao banco
   correto, com uma cópia de segurança disponível:

   ```powershell
   psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/schema.sql
   ```

   A migração cria três tabelas com `IF NOT EXISTS`. Reexecutá-la preserva
   as contas existentes. Nenhuma conta é inscrita automaticamente no 2FA.
5. Publique o backend e os arquivos estáticos juntos. Em produção, use
   HTTPS, `FLASK_ENV=production` e `FRONTEND_ORIGIN` com a origem exata do
   site. Na Vercel, o cookie também fica `Secure` quando `VERCEL=1`.
6. Valide em uma conta de teste: ativação, novo login, recuperação e
   desativação. Confira `/api/2fa/status` autenticado: `available` deve ser
   `true`. Mantenha o relógio do servidor sincronizado.

A aplicação não gera uma chave persistente automaticamente. Sem chave
válida, as operações 2FA retornam 503 e contas protegidas não conseguem
entrar, inclusive com código de recuperação. Contas sem 2FA continuam
funcionando. Uma chave com formato válido, mas diferente da original,
também não decifra os segredos já salvos. **Não substitua nem perca a chave**;
uma rotação exige decifrar com a anterior e recifrar com a nova.

Depois que houver contas com 2FA, não reverta para uma versão do login
que ignore o segundo fator. Em caso de incidente, corrija ou retire o
login do ar; remover a verificação permitiria acesso só com a senha.

## Ativar em uma conta

1. Entre e abra **Configurações > Autenticação em dois fatores**.
2. Clique em **Ativar autenticação em dois fatores** e confirme sua senha.
3. No Google Authenticator, toque em **+ > Ler QR code**. No mesmo celular,
   use a chave manual e selecione a opção baseada no tempo.
4. Informe um código do aplicativo para confirmar. A configuração pendente
   expira em 10 minutos e só pode ser confirmada na sessão que a iniciou.
5. Baixe ou guarde os oito códigos de recuperação e confirme que os guardou.
   Eles não poderão ser consultados novamente.

Os próximos logins pedem senha e código. **Usar código de recuperação**
permite entrar com um código reserva de uso único e mantém o 2FA ativo.
Se um código do autenticador acabou de ser aceito, aguarde o próximo antes
de utilizá-lo em outra operação.

É possível gerar oito novos códigos nas Configurações, invalidando todos
os anteriores, ou desativar o 2FA. Ambas as ações exigem a senha atual e
um código válido do autenticador ou de recuperação. Ativação, desativação
e renovação dos códigos encerram as demais sessões e renovam a atual.

Redefinir a senha por e-mail não desativa o 2FA. Sem acesso ao autenticador
e sem códigos de recuperação, não há recuperação automática da conta.

## Contratos e proteção

- `POST /api/login` mantém a resposta 200 atual para contas sem 2FA.
  Contas protegidas recebem 202 com `twoFactorRequired`, `challengeToken`
  e `expiresIn: 300`, sem sessão autenticada. Cada conta tem um desafio
  pendente; iniciar outro login invalida o anterior.
- `POST /api/login/2fa` recebe `{challengeToken, code}` e retorna o usuário
  público e cookie de sessão após verificação. O token é opaco, aleatório,
  armazenado somente como hash no banco e mantido na memória da página.
- `GET /api/2fa/status` exige sessão e retorna `enabled`, `available` e
  `recoveryCodesRemaining`. Não retorna segredos nem códigos.
- `POST /api/2fa/setup` recebe `{password}` e retorna `manualKey`,
  `qrCodeDataUrl` e `expiresIn: 600`. O QR é gerado no servidor, sem serviço externo.
- `POST /api/2fa/confirm` recebe `{code}`. A ativação só ocorre após validar
  o primeiro TOTP e retorna `recoveryCodes` uma única vez.
- `POST /api/2fa/disable` e `POST /api/2fa/recovery-codes` recebem
  `{password, code}`. A segunda operação retorna a nova lista uma única vez.
- Os POSTs 2FA exigem JSON e rejeitam origens estrangeiras. As respostas
  de autenticação usam `Cache-Control: no-store`. Nunca registre corpos
  dessas requisições/respostas em ferramentas de monitoramento.
- Cinco falhas de reautenticação/2FA por conta em 15 minutos bloqueiam
  novas tentativas por 15 minutos (HTTP 429 e `Retry-After`). Reiniciar o
  servidor, refazer o setup ou emitir outro desafio não zera o limite.
- A tolerância do TOTP é de um intervalo antes/depois; o último intervalo
  aceito é persistido. Códigos de recuperação têm 128 bits aleatórios e
  são guardados como SHA-256. O consumo, desafio e criação da sessão
  compartilham uma transação, serializada por conta.
- Desafios e configurações pendentes são vinculados à versão da senha;
  alterar/redefinir a senha os torna inválidos. A exclusão da conta remove
  os dados 2FA em cascata. Exportações de perfil não incluem segredos.

## Testes

Use um banco PostgreSQL dedicado. A suíte apaga seus dados entre casos e
recusa `TEST_DATABASE_URL` ausente ou igual à `DATABASE_URL`.

```powershell
python -m pip install pytest
$env:TEST_DATABASE_URL='postgresql://usuario:senha@localhost/trashtalker_test'
python -m pytest
```

Os testes geram chaves temporárias, verificam expiração, replay, concorrência,
rollback, limites, migração idempotente e regressões do login atual.

Referências: [PyOTP](https://pyauth.github.io/pyotp/),
[OWASP MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html),
[Fernet](https://cryptography.io/en/stable/fernet/).
