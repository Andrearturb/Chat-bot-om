import { useEffect } from 'react';
import { createChat } from '@n8n/chat';
import '@n8n/chat/style.css';
import './App.css';

function App() {
  useEffect(() => {
    createChat({
      webhookUrl:
        'http://localhost:5678/webhook/9db5ead4-d4ca-4f5c-a1b4-3969e60cb8df/chat',

      target: '#n8n-chat',
      mode: 'fullscreen',

      showWelcomeScreen: false,

      initialMessages: [
        'Olá! 👋',
        'Sou o assistente de Obras & Manutenções. Como posso ajudar?'
      ],
    });
  }, []);

  return <div id="n8n-chat" />;
}

export default App;