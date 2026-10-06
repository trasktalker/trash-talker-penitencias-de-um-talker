# language: pt

Funcionalidade: Gerenciar minha conta
  Como uma pessoa logada
  Quero editar meu perfil, trocar minha senha, exportar e apagar meus dados
  Para ter controle sobre as informações que o TrashTalker guarda sobre mim

  Cenário: Personalizar o perfil que o TrashTalker enxerga
    Dado que eu estou logado
    Quando eu atualizo meu perfil com o nome "Igor" e os interesses "música, programação"
    Então meu perfil deve ter o nome "Igor"
    E meus interesses devem ser "música, programação"

  Cenário: Interesses repetidos são guardados uma vez só
    Dado que eu estou logado
    Quando eu atualizo meu perfil com o nome "Igor" e os interesses "rock, rock, jazz"
    Então meus interesses devem ser "rock, jazz"

  Cenário: Nome muito curto é recusado
    Dado que eu estou logado
    Quando eu atualizo meu perfil com o nome "A"
    Então eu devo receber o status 400

  Cenário: Trocar a senha informando a senha atual
    Dado que eu estou logado
    Quando eu troco minha senha de "Senha-Forte-123" para "Senha-Nova-999"
    Então eu devo receber o status 200
    E eu devo continuar autenticado

  Cenário: Trocar a senha com a senha atual errada é recusado
    Dado que eu estou logado
    Quando eu troco minha senha de "senha-que-nao-e-a-minha" para "Senha-Nova-999"
    Então eu devo receber o status 401

  Cenário: Trocar a senha derruba outros dispositivos
    Dado que eu estou logado
    E que minha conta está aberta em outro dispositivo
    Quando eu troco minha senha de "Senha-Forte-123" para "Senha-Nova-999"
    Então o outro dispositivo não deve mais estar autenticado
    E eu devo continuar autenticado

  Cenário: Exportar meus dados
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    E que eu já enviei a mensagem "oi"
    Quando eu exporto meus dados
    Então a exportação deve conter 1 conversa
    E a exportação não deve conter minha senha

  Cenário: Exportar dados de uma conta sem nenhuma conversa
    Dado que eu estou logado
    Quando eu exporto meus dados
    Então eu devo receber o status 200
    E a exportação deve conter 0 conversa

  Cenário: Apagar a conta remove conversas e mensagens
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    E que eu já enviei a mensagem "oi"
    Quando eu apago minha conta com a senha "Senha-Forte-123"
    Então eu devo receber o status 200
    E não deve restar nenhum dado meu no banco
    E eu não devo estar autenticado

  Cenário: Apagar a conta com a senha errada é recusado
    Dado que eu estou logado
    Quando eu apago minha conta com a senha "senha-que-nao-e-a-minha"
    Então eu devo receber o status 401
    E eu devo continuar autenticado
