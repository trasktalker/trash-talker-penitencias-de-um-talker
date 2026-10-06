# language: pt

Funcionalidade: Autenticação de usuários
  Como uma pessoa que quer usar o TrashTalker
  Quero criar uma conta e entrar nela com segurança
  Para que minhas conversas fiquem guardadas e só eu tenha acesso a elas

  Cenário: Criar uma conta com dados válidos
    Dado que não existe conta com o e-mail "novo@exemplo.com"
    Quando eu me cadastro com o e-mail "novo@exemplo.com" e a senha "Senha-Forte-123"
    Então a conta deve ser criada
    E eu ainda não devo estar autenticado

  Cenário: Entrar com as credenciais corretas
    Dado que existe uma conta com o e-mail "pessoa@exemplo.com" e a senha "Senha-Forte-123"
    Quando eu entro com o e-mail "pessoa@exemplo.com" e a senha "Senha-Forte-123"
    Então eu devo estar autenticado
    E eu devo receber um cookie de sessão

  Cenário: Entrar com a senha errada
    Dado que existe uma conta com o e-mail "pessoa@exemplo.com" e a senha "Senha-Forte-123"
    Quando eu entro com o e-mail "pessoa@exemplo.com" e a senha "senha-que-nao-e-a-minha"
    Então eu devo receber o status 401
    E eu não devo estar autenticado

  Cenário: Entrar com um e-mail que não tem conta
    Quando eu entro com o e-mail "ninguem@exemplo.com" e a senha "Senha-Forte-123"
    Então eu devo receber o status 401

  Cenário: Não é possível cadastrar o mesmo e-mail duas vezes
    Dado que existe uma conta com o e-mail "pessoa@exemplo.com" e a senha "Senha-Forte-123"
    Quando eu me cadastro com o e-mail "pessoa@exemplo.com" e a senha "Outra-Senha-456"
    Então eu devo receber o status 409

  Cenário: Cadastro com senha muito curta é recusado
    Quando eu me cadastro com o e-mail "novo@exemplo.com" e a senha "123"
    Então eu devo receber o status 400
    E não deve existir conta com o e-mail "novo@exemplo.com"

  Cenário: Sair da conta encerra a sessão
    Dado que eu estou logado
    Quando eu saio da conta
    Então eu não devo estar autenticado

  Cenário: Pedir redefinição de senha para um e-mail que não existe não revela nada
    Quando eu peço a redefinição de senha do e-mail "ninguem@exemplo.com"
    Então eu devo receber o status 200
    E nenhum token de redefinição deve ter sido gerado

  Cenário: Redefinir a senha pelo link recebido
    Dado que existe uma conta com o e-mail "pessoa@exemplo.com" e a senha "Senha-Forte-123"
    E que eu pedi a redefinição de senha do e-mail "pessoa@exemplo.com"
    Quando eu redefino a senha para "Senha-Nova-999" usando o token recebido
    Então eu devo receber o status 200
    E eu devo conseguir entrar com o e-mail "pessoa@exemplo.com" e a senha "Senha-Nova-999"
    E eu não devo conseguir entrar com o e-mail "pessoa@exemplo.com" e a senha "Senha-Forte-123"

  Cenário: Redefinir a senha derruba sessões abertas em outros dispositivos
    Dado que existe uma conta com o e-mail "pessoa@exemplo.com" e a senha "Senha-Forte-123"
    E que essa conta está aberta em outro dispositivo
    E que eu pedi a redefinição de senha do e-mail "pessoa@exemplo.com"
    Quando eu redefino a senha para "Senha-Nova-999" usando o token recebido
    Então o outro dispositivo não deve mais estar autenticado

  Cenário: Token de redefinição só vale uma vez
    Dado que existe uma conta com o e-mail "pessoa@exemplo.com" e a senha "Senha-Forte-123"
    E que eu pedi a redefinição de senha do e-mail "pessoa@exemplo.com"
    Quando eu redefino a senha para "Senha-Nova-999" usando o token recebido
    E eu redefino a senha para "Outra-Senha-888" usando o token recebido
    Então eu devo receber o status 400
