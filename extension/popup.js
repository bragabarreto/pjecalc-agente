// popup.js — Agente PJE-Calc
'use strict';

const $ = id => document.getElementById(id);

// ── Carregar configurações salvas ─────────────────────────────────────────────
chrome.storage.sync.get(['server_url', 'sessao_id'], ({ server_url, sessao_id }) => {
  if (server_url) {
    $('server-url').value    = server_url;
    $('server-config').value = server_url;
  }
  if (sessao_id) {
    $('sessao-id').value = sessao_id;
  }
});

// ── Salvar configuração ────────────────────────────────────────────────────────
$('btn-salvar-config').addEventListener('click', () => {
  const url = $('server-config').value.trim().replace(/\/$/, '');
  if (!url) { mostrarStatus('Informe a URL do servidor.', 'erro'); return; }
  chrome.storage.sync.set({ server_url: url }, () => {
    $('server-url').value = url;
    mostrarStatus('Configuração salva!', 'ok');
  });
});

// ── Abrir PJE-Calc e iniciar preenchimento ─────────────────────────────────────
$('btn-abrir').addEventListener('click', () => {
  const server_url = $('server-url').value.trim().replace(/\/$/, '');
  const sessao_id  = $('sessao-id').value.trim();

  if (!sessao_id) { mostrarStatus('Cole o ID da sessão antes de abrir.', 'erro'); return; }
  if (!server_url) { mostrarStatus('Configure a URL do servidor primeiro.', 'erro'); return; }

  // Salvar sessão para uso futuro
  chrome.storage.sync.set({ sessao_id, server_url });

  // Construir URL do PJE-Calc com parâmetros do agente no hash
  const pjecalcUrl =
    'http://localhost:9257/pjecalc/pages/principal.jsf' +
    '#agente-sessao=' + encodeURIComponent(sessao_id) +
    '&agente-server=' + encodeURIComponent(server_url);

  chrome.tabs.create({ url: pjecalcUrl });
  window.close();
});

// ── Sincronizar campo server-url ↔ server-config ──────────────────────────────
$('server-url').addEventListener('change', () => {
  $('server-config').value = $('server-url').value;
});

// ── Status ─────────────────────────────────────────────────────────────────────
function mostrarStatus(msg, tipo) {
  const el = $('status');
  el.textContent = msg;
  el.className   = tipo === 'ok' ? 'status-ok' : 'status-erro';
  setTimeout(() => { el.textContent = ''; el.className = ''; }, 3000);
}
