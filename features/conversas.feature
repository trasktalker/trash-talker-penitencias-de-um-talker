# language: pt

Funcionalidade: Conversar com o TrashTalker
  Como uma pessoa logada
  Quero conversar com o TrashTalker e ter minhas conversas guardadas
  Para retomar de onde parei e acompanhar minha evolução

  Cenário: Enviar uma mensagem e receber resposta
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    Quando eu envio a mensagem "Travei na hora de puxar assunto hoje"
    Então eu devo receber uma resposta do TrashTalker
    E a conversa deve ter 2 mensagens guardadas

  Cenário: A primeira mensagem vira o título da conversa
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    Quando eu envio a mensagem "Como puxar assunto?"
    Então o título da conversa deve ser "Como puxar assunto?"

  Cenário: O título não muda depois da primeira mensagem
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    Quando eu envio a mensagem "Como puxar assunto?"
    E eu envio a mensagem "E se a pessoa não responder?"
    Então o título da conversa deve ser "Como puxar assunto?"

  Cenário: Mensagem vazia é recusada
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    Quando eu envio a mensagem "   "
    Então eu devo receber o status 400
    E a conversa deve ter 0 mensagens guardadas

  Cenário: Quando a IA falha, a mensagem do usuário não é perdida
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    E que a IA está indisponível
    Quando eu envio a mensagem "essa mensagem não pode sumir"
    Então eu devo receber o status 502
    E a conversa deve ter 1 mensagens guardadas

  Cenário: Renomear uma conversa
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    Quando eu renomeio a conversa para "Papo sobre ansiedade social"
    Então o título da conversa deve ser "Papo sobre ansiedade social"

  Cenário: Renomear com título vazio é recusado
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    Quando eu renomeio a conversa para "   "
    Então eu devo receber o status 400
    E o título da conversa deve ser "New Chat"

  Cenário: Apagar uma conversa apaga também as mensagens dela
    Dado que eu estou logado
    E que eu tenho uma conversa aberta
    E que eu já enviei a mensagem "oi"
    Quando eu apago a conversa
    Então eu não devo ter nenhuma conversa

  Cenário: Não é possível ler a conversa de outra pessoa
    Dado que eu estou logado
    E que outra pessoa tem uma conversa
    Quando eu tento abrir a conversa da outra pessoa
    Então eu devo receber o status 404

  Cenário: Não é possível apagar a conversa de outra pessoa
    Dado que eu estou logado
    E que outra pessoa tem uma conversa
    Quando eu tento apagar a conversa da outra pessoa
    Então a conversa da outra pessoa deve continuar existindo

  Cenário: Conversas de outra pessoa não aparecem na minha lista
    Dado que eu estou logado
    E que outra pessoa tem uma conversa
    Quando eu abro meu painel
    Então eu não devo ter nenhuma conversa

  Cenário: É preciso estar logado para conversar
    Quando eu tento abrir meu painel sem estar logado
    Então eu devo receber o status 401
