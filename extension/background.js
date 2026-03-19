// background.js — Service Worker do Agente PJE-Calc
// Responsável por: buscar dados da API Railway (sem restrições CORS)

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'FETCH_DADOS') {
    const { sessao_id, server_url } = msg;
    const url = `${server_url}/api/calculo/${sessao_id}`;

    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status} — ${r.statusText}`);
        return r.json();
      })
      .then(dados => sendResponse({ ok: true, dados }))
      .catch(err => sendResponse({ ok: false, erro: err.message }));

    return true; // manter canal aberto para resposta assíncrona
  }

  if (msg.type === 'PING') {
    sendResponse({ ok: true });
    return true;
  }
});
