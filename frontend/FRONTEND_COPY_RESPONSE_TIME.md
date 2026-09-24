# Frontend — copiar resposta + tempo de resposta

Alterações desta etapa:

- botão **Copiar** abaixo de cada resposta da Gentileza;
- estado temporário **Copiado** após a cópia;
- cópia apenas do texto renderizado da resposta, sem controles da interface;
- indicador em tempo real **Pensando... X,Xs** enquanto a requisição está em andamento;
- indicador persistente **Respondido em X,Xs** após a resposta;
- o tempo fica salvo junto da mensagem no histórico local;
- mensagens antigas continuam funcionando, apenas sem tempo retroativo;
- em caso de falha, o tempo aparece como **Falhou em X,Xs**.

O tempo representa o tempo total percebido pelo frontend para receber a resposta (n8n + modelos/serviços + backend + rede), e não tempo de raciocínio interno do modelo.

Arquivos alterados:

- `frontend/src/App.jsx`
- `frontend/src/components/ChatArea.jsx`
- `frontend/src/App.css`
