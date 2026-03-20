// content.js — Agente PJE-Calc
// Automação DOM do PJE-Calc Cidadão (localhost:9257) — 5 fases de preenchimento
// Injetado automaticamente pela extensão em qualquer página do PJE-Calc Cidadão.
//
// Mecanismo de persistência: sessionStorage sobrevive a recargas da mesma origem,
// permitindo retomar de onde parou após navegação por menus que recarregam a página.

'use strict';

const STORAGE_KEY = 'pjecalc_agente_state';

// ── Estado ────────────────────────────────────────────────────────────────────

function carregarEstado() {
  try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}'); }
  catch { return {}; }
}

function salvarEstado(estado) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(estado));
}

function limparEstado() {
  sessionStorage.removeItem(STORAGE_KEY);
}

// ── Utilitários ───────────────────────────────────────────────────────────────

async function aguardar(ms) {
  return new Promise(r => setTimeout(r, ms));
}

/** Aguarda elemento aparecer no DOM (equivalente ao wait_for_selector do Playwright) */
async function aguardarElemento(seletor, timeout = 8000) {
  const inicio = Date.now();
  while (Date.now() - inicio < timeout) {
    const el = document.querySelector(seletor);
    if (el && el.offsetParent !== null) return el; // visível
    await aguardar(200);
  }
  return null;
}

/** Exibe barra de status fixa no rodapé (não bloqueia) */
function log(msg) {
  console.info('[Agente PJE-Calc]', msg);
  let bar = document.getElementById('pjecalc-agente-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'pjecalc-agente-bar';
    bar.style.cssText = [
      'position:fixed', 'bottom:0', 'left:0', 'width:100%', 'z-index:2147483646',
      'background:#1a3a6b', 'color:#fff', 'padding:6px 16px',
      'font:13px/1.4 Arial,sans-serif', 'box-shadow:0 -2px 6px rgba(0,0,0,.3)',
    ].join(';');
    document.body.appendChild(bar);
  }
  bar.textContent = '\u25B6 Agente PJE-Calc: ' + msg;
}

/** Overlay amarelo bloqueante: aguarda usuário clicar "Continuar" */
async function pausarParaUsuario(mensagem) {
  // Remover overlay anterior se existir
  const antigo = document.getElementById('pjecalc-agente-overlay');
  if (antigo) antigo.remove();

  return new Promise(resolve => {
    const div = document.createElement('div');
    div.id = 'pjecalc-agente-overlay';
    div.style.cssText = [
      'position:fixed', 'top:0', 'left:0', 'width:100%', 'z-index:2147483647',
      'background:#fff3cd', 'border-bottom:3px solid #ffc107',
      'padding:14px 20px', 'font:14px/1.5 Arial,sans-serif',
      'display:flex', 'align-items:center', 'gap:14px',
      'box-shadow:0 4px 10px rgba(0,0,0,.25)',
    ].join(';');

    const icone = document.createElement('span');
    icone.style.fontSize = '24px';
    icone.textContent = '\u26A0\uFE0F';

    const texto = document.createElement('span');
    texto.style.flex = '1';
    const titulo = document.createElement('strong');
    titulo.textContent = 'A\u00e7\u00e3o necess\u00e1ria: ';
    texto.appendChild(titulo);
    // mensagem pode conter HTML com <strong>/<em>/<br> — usar DOMParser para segurança
    const frag = document.createRange().createContextualFragment(mensagem);
    texto.appendChild(frag);

    const btn = document.createElement('button');
    btn.id = 'pjecalc-btn-continuar';
    btn.textContent = 'Continuar \u25B6';
    btn.style.cssText = 'background:#1a3a6b;color:#fff;border:none;' +
      'padding:8px 22px;border-radius:4px;cursor:pointer;font:14px Arial,sans-serif;white-space:nowrap';

    div.appendChild(icone);
    div.appendChild(texto);
    div.appendChild(btn);
    document.body.prepend(div);

    btn.addEventListener('click', () => { div.remove(); resolve(); });
  });
}

/** Formata número float como moeda brasileira: 1234.56 → "1.234,56" */
function fmtBR(valor) {
  if (valor == null || valor === '') return '0,00';
  return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── Primitivas DOM ────────────────────────────────────────────────────────────
// Equivalem às funções _fill/_select/_radio/_checkbox do playwright_script_builder.py
// JSF/RichFaces requer eventos input+change+blur para disparar Ajax listeners.

async function preencher(fieldId, valor, obrigatorio = true) {
  if (valor == null || valor === '') {
    if (obrigatorio) log('Campo obrigatório vazio: ' + fieldId);
    return false;
  }
  const seletores = [
    '#formulario\\:' + fieldId + '_input',   // RichFaces calendar widget
    "[id='formulario:" + fieldId + "']",
    "input[id$=':" + fieldId + "']",
    "input[id$='" + fieldId + "']",
  ];
  for (const sel of seletores) {
    const el = await aguardarElemento(sel, 3000);
    if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
      el.focus();
      el.value = '';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.value = String(valor);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      el.dispatchEvent(new Event('blur',   { bubbles: true }));
      log('\u2713 ' + fieldId + ': ' + valor);
      await aguardar(150);
      return true;
    }
  }
  if (obrigatorio) {
    await pausarParaUsuario(
      'Campo <strong>' + fieldId + '</strong> n\u00e3o encontrado. ' +
      'Preencha manualmente e clique em Continuar.'
    );
  }
  return false;
}

async function selecionar(fieldId, valor) {
  if (!valor) return false;
  const seletores = [
    "[id='formulario:" + fieldId + "']",
    "select[id$=':" + fieldId + "']",
    "select[id$='" + fieldId + "']",
  ];
  for (const sel of seletores) {
    const el = await aguardarElemento(sel, 3000);
    if (el && el.tagName === 'SELECT') {
      const opts = [...el.options];
      const opt =
        opts.find(o => o.value === valor) ||
        opts.find(o => o.text.trim().toLowerCase().includes(valor.toLowerCase()));
      if (opt) {
        el.value = opt.value;
        el.dispatchEvent(new Event('change', { bubbles: true }));
        log('\u2713 select ' + fieldId + ': ' + opt.text.trim());
        await aguardar(150);
        return true;
      }
    }
  }
  return false;
}

async function marcarRadio(fieldId, valor) {
  if (!valor) return false;
  const seletores = [
    "[id='formulario:" + fieldId + "'] input[value='" + valor + "']",
    "table[id='formulario:" + fieldId + "'] input[value='" + valor + "']",
    "input[name$='" + fieldId + "'][value='" + valor + "']",
    "input[name$=':" + fieldId + "'][value='" + valor + "']",
  ];
  for (const sel of seletores) {
    const el = document.querySelector(sel);
    if (el) {
      el.click();
      log('\u2713 radio ' + fieldId + ': ' + valor);
      await aguardar(150);
      return true;
    }
  }
  return false;
}

async function marcarCheckbox(fieldId, marcar) {
  const seletores = [
    "[id='formulario:" + fieldId + "']",
    "input[id$=':" + fieldId + "']",
    "input[id$='" + fieldId + "']",
  ];
  for (const sel of seletores) {
    const el = await aguardarElemento(sel, 3000);
    if (el && el.type === 'checkbox') {
      if (Boolean(el.checked) !== Boolean(marcar)) el.click();
      log('\u2713 checkbox ' + fieldId + ': ' + marcar);
      await aguardar(150);
      return true;
    }
  }
  return false;
}

async function clicarSalvar() {
  const seletores = [
    "[id='formulario:salvar']",
    "input[value='Salvar']",
    "a[id*='salvar']",
    "button[id*='salvar']",
  ];
  for (const sel of seletores) {
    const el = await aguardarElemento(sel, 5000);
    if (el) {
      el.click();
      log('Salvando...');
      await aguardar(1800); // aguarda Ajax RichFaces
      return true;
    }
  }
  log('Bot\u00e3o Salvar n\u00e3o encontrado');
  return false;
}

async function clicarNovo() {
  const seletores = [
    "[id='formulario:novo']",
    "input[value='Novo']",
    "a[id*='novo']",
    "button[id*='novo']",
    '.sprite-novo',
  ];
  for (const sel of seletores) {
    const el = await aguardarElemento(sel, 5000);
    if (el) {
      el.click();
      log('Clicando Novo...');
      await aguardar(1000);
      return true;
    }
  }
  log('Bot\u00e3o Novo n\u00e3o encontrado');
  return false;
}

async function clicarAba(abaId) {
  const seletores = [
    "[id='formulario:" + abaId + "_lbl']",
    '#' + abaId + '_lbl',
    "[id$='" + abaId + "_lbl']",
  ];
  for (const sel of seletores) {
    const el = await aguardarElemento(sel, 5000);
    if (el) {
      el.click();
      await aguardar(800);
      return true;
    }
  }
  return false;
}

async function clicarMenu(texto) {
  await aguardar(600);
  const links = document.querySelectorAll('a, span.menuItem, li.menuItem');
  for (const a of links) {
    if (a.textContent.trim().toLowerCase().includes(texto.toLowerCase())) {
      a.click();
      log('Menu: ' + texto);
      // Aguarda possível recarga de página
      await aguardar(2000);
      return true;
    }
  }
  log('Menu n\u00e3o encontrado: ' + texto);
  return false;
}

// ── Mapeamentos de Enums ──────────────────────────────────────────────────────

function mapIndice(v) {
  const m = {
    'Tabela JT Unica Mensal': 'TRABALHISTA',
    'Tabela JT Única Mensal': 'TRABALHISTA',
    'IPCA-E': 'IPCA_E',
    'Selic':  'SELIC',
    'TRCT':   'TRCT',
  };
  return m[v] || 'TRABALHISTA';
}

function mapJuros(v) {
  return (v && v.toLowerCase().includes('selic')) ? 'SELIC' : 'TRABALHISTA';
}

function mapBase(v) {
  return (v && v.toLowerCase().includes('total')) ? 'CREDITO_TOTAL' : 'VERBAS';
}

function mapCaract(v) {
  const m = {
    'Comum':            'COMUM',
    'Décimo Terceiro':  'DECIMO_TERCEIRO',
    'Decimo Terceiro':  'DECIMO_TERCEIRO',
    'Aviso Prévio':     'AVISO_PREVIO',
    'Aviso Previo':     'AVISO_PREVIO',
    'Férias':           'FERIAS',
    'Ferias':           'FERIAS',
  };
  return m[v] || 'COMUM';
}

function mapOcorr(v) {
  const m = {
    'Mensal':               'MENSAL',
    'Dezembro':             'DEZEMBRO',
    'Período Aquisitivo':   'PERIODO_AQUISITIVO',
    'Periodo Aquisitivo':   'PERIODO_AQUISITIVO',
    'Desligamento':         'DESLIGAMENTO',
  };
  return m[v] || 'MENSAL';
}

function mapDevedor(v) {
  const m = {
    'Reclamado':   'RECLAMADO',
    'Reclamante':  'RECLAMANTE',
    'Ambos':       'AMBOS',
  };
  return m[v] || 'RECLAMADO';
}

function parseNumero(n) {
  if (!n) return { numero: '', digito: '', ano: '', regiao: '', vara: '' };
  const m = n.match(/^(\d+)-(\d+)\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$/);
  if (!m) return { numero: n, digito: '', ano: '', regiao: '', vara: '' };
  return { numero: m[1], digito: m[2], ano: m[3], regiao: m[5], vara: m[6] };
}

// ── Fases de Preenchimento ────────────────────────────────────────────────────

async function fase01NovocalculoEParametros(dados) {
  log('Fase 1 — Novo C\u00e1lculo Externo...');

  // Navegar para "Cálculo Externo" no menu
  const clicou = await clicarMenu('lculo Externo');
  if (!clicou) {
    await pausarParaUsuario(
      'Clique em <strong>C\u00e1lculo Externo</strong> no menu e depois clique em Continuar.'
    );
  }
  await aguardar(2000);

  const proc = dados.processo || {};
  const { numero, digito, ano, regiao, vara } = parseNumero(proc.numero || '');

  // Aba: Dados do Processo
  await clicarAba('tabDadosProcesso');
  await preencher('numero', numero);
  await preencher('digito', digito);
  await preencher('ano', ano);
  await preencher('regiao', regiao);
  await preencher('vara', vara);
  await preencher('reclamanteNome', proc.reclamante || '', false);
  await preencher('reclamadoNome',  proc.reclamado  || '', false);

  if (proc.cpf_reclamante) {
    await marcarRadio('documentoFiscalReclamante', 'CPF');
    await preencher('reclamanteNumeroDocumentoFiscal', proc.cpf_reclamante, false);
  }
  if (proc.cnpj_reclamado) {
    await marcarRadio('tipoDocumentoFiscalReclamado', 'CNPJ');
    await preencher('reclamadoNumeroDocumentoFiscal', proc.cnpj_reclamado, false);
  }

  // Aba: Parâmetros do Cálculo
  await clicarAba('tabParametrosCalculo');
  const cj = dados.correcao_juros || {};
  await selecionar('indiceTrabalhista', mapIndice(cj.indice_correcao));
  await selecionar('juros',             mapJuros(cj.taxa_juros));
  await selecionar('baseDeJurosDasVerbas', mapBase(cj.base_juros));

  const ir = dados.imposto_renda || {};
  if (ir.apurar) {
    await marcarCheckbox('apurarImpostoRenda', true);
    if (ir.meses_tributaveis) {
      await preencher('qtdMesesRendimento', String(ir.meses_tributaveis), false);
    }
    if (ir.dependentes) {
      await marcarCheckbox('possuiDependentes', true);
      await preencher('quantidadeDependentes', String(ir.dependentes), false);
    }
  }

  await clicarSalvar();
  log('Fase 1 conclu\u00edda.');
}

async function fase02HistoricoSalarial(dados) {
  log('Fase 2 — Hist\u00f3rico Salarial...');
  await clicarMenu('Hist\u00f3rico Salarial');
  await aguardar(2000);

  const hist = dados.historico_salarial || [];
  if (hist.length === 0) {
    log('Fase 2: sem hist\u00f3rico salarial. Ignorando.');
    return;
  }

  for (const h of hist) {
    await clicarNovo();
    await preencher('nome', h.nome || 'Sal\u00e1rio');
    await marcarRadio('tipoValor', 'FIXO');
    await marcarRadio('tipoVariacaoDaParcela', 'MONETARIO');
    await preencher('valorParaBaseDeCalculo', fmtBR(h.valor));
    await preencher('competenciaInicial', h.data_inicio);
    await preencher('competenciaFinal',   h.data_fim);
    await clicarSalvar();
  }
  log('Fase 2 conclu\u00edda.');
}

async function fase03Verbas(dados, verbas) {
  log('Fase 3 — Verbas Deferidas...');
  await clicarMenu('Verbas');
  await aguardar(2000);

  const lista = [
    ...(verbas.predefinidas   || []),
    ...(verbas.personalizadas || []),
  ];

  for (const v of lista) {
    await clicarNovo();
    await preencher('descricao', v.nome_pjecalc || v.nome_sentenca);
    await marcarRadio('caracteristicaVerba', mapCaract(v.caracteristica));
    await marcarRadio('ocorrenciaPagto',     mapOcorr(v.ocorrencia));

    if (v.valor_informado) {
      await marcarRadio('valor', 'INFORMADO');
      await preencher('valorDevidoInformado', fmtBR(v.valor_informado), false);
    }

    await marcarCheckbox('fgts', !!v.incidencia_fgts);
    await marcarCheckbox('inss', !!v.incidencia_inss);
    await marcarCheckbox('irpf', !!v.incidencia_ir);
    await clicarSalvar();
  }

  // Verbas não reconhecidas: pausar para ação manual
  for (const vNR of (verbas.nao_reconhecidas || [])) {
    await pausarParaUsuario(
      'Verba <strong>"' + vNR.nome_sentenca + '"</strong> n\u00e3o foi mapeada automaticamente. ' +
      'Adicione-a manualmente no PJE-Calc e clique em Continuar.'
    );
  }

  log('Fase 3 conclu\u00edda.');
}

async function fase04FGTS(dados) {
  log('Fase 4 — FGTS...');
  await clicarMenu('FGTS');
  await aguardar(2000);

  const fgts = dados.fgts || {};
  const aliq = (fgts.aliquota || 0.08) >= 0.08 ? '8%' : '2%';

  // Selecionar linha da alíquota na tabela clicando na célula
  const tds = [...document.querySelectorAll('td')];
  const tdAliq = tds.find(td => td.textContent.trim() === aliq);
  if (tdAliq) {
    tdAliq.click();
    await aguardar(500);
  }

  await marcarCheckbox('multa',            !!fgts.multa_40);
  await marcarCheckbox('multaDoArtigo467', !!fgts.multa_467);
  await clicarSalvar();
  log('Fase 4 conclu\u00edda.');
}

async function fase05Honorarios(dados) {
  log('Fase 5 — Honor\u00e1rios...');
  const hon = dados.honorarios || {};

  if (!hon.percentual && !hon.valor_fixo) {
    log('Fase 5: sem honor\u00e1rios. Ignorando.');
    return;
  }

  await clicarMenu('Honor\u00e1rios');
  await aguardar(2000);
  await clicarNovo();

  await selecionar('tpHonorario', 'SUCUMBENCIA');
  await preencher('descricao', 'Honor\u00e1rios Advocat\u00edcios', false);
  await marcarRadio('tipoDeDevedor', mapDevedor(hon.parte_devedora));

  if (hon.valor_fixo) {
    await marcarRadio('tipoValor', 'INFORMADO');
    await preencher('valor', fmtBR(hon.valor_fixo), false);
  } else if (hon.percentual) {
    await marcarRadio('tipoValor', 'CALCULADO');
    await preencher('aliquota', (hon.percentual * 100).toFixed(2), false);
  }

  await clicarSalvar();
  log('Fase 5 conclu\u00edda.');
}

// ── Orquestrador Principal ────────────────────────────────────────────────────

async function executarFase(estado) {
  const { dados, verbas, fase } = estado;
  const TOTAL_FASES = 5;

  if (fase >= TOTAL_FASES) {
    limparEstado();
    log('Preenchimento conclu\u00eddo! Revise os dados e clique em Liquidar.');
    return;
  }

  try {
    switch (fase) {
      case 0: await fase01NovocalculoEParametros(dados); break;
      case 1: await fase02HistoricoSalarial(dados); break;
      case 2: await fase03Verbas(dados, verbas); break;
      case 3: await fase04FGTS(dados); break;
      case 4: await fase05Honorarios(dados); break;
    }

    // Avançar fase
    estado.fase = fase + 1;
    salvarEstado(estado);

    // Se ainda há fases, continuar (pode ou não ter recarregado a página)
    if (estado.fase < TOTAL_FASES) {
      await executarFase(estado);
    } else {
      limparEstado();
      log('Preenchimento conclu\u00eddo! Revise os dados e clique em Liquidar.');
    }
  } catch (err) {
    console.error('[Agente PJE-Calc] Erro na fase', fase, err);
    log('Erro na fase ' + fase + ': ' + err.message);
    await pausarParaUsuario(
      'Ocorreu um erro na fase ' + (fase + 1) + ': <em>' + err.message + '</em>. ' +
      'Corrija manualmente e clique em Continuar para tentar a pr\u00f3xima fase.'
    );
    // Avançar mesmo após erro manual para não travar
    estado.fase = fase + 1;
    salvarEstado(estado);
    if (estado.fase < TOTAL_FASES) await executarFase(estado);
  }
}

async function main() {
  // Verificar se já há estado salvo (retomada após recarga de página)
  let estado = carregarEstado();

  if (estado.dados && estado.fase != null) {
    // Retomada após navegação/recarga
    log('Retomando fase ' + (estado.fase + 1) + '...');
    await aguardar(1500); // aguarda página carregar completamente
    await executarFase(estado);
    return;
  }

  // Primeira execução: verificar hash da URL com parâmetros do agente
  const hash = location.hash;
  if (!hash.includes('agente-sessao=')) return; // extensão inativa nesta página

  const params = Object.fromEntries(new URLSearchParams(hash.slice(1)));
  const sessao_id  = params['agente-sessao'];
  const server_url = params['agente-server']
    ? decodeURIComponent(params['agente-server'])
    : '';

  if (!sessao_id || !server_url) {
    log('Par\u00e2metros incompletos na URL. Verifique o link gerado pelo site.');
    return;
  }

  // Limpar hash da URL sem recarregar a página
  history.replaceState(null, '', location.pathname + location.search);

  log('Buscando dados do c\u00e1lculo... (' + sessao_id.slice(0, 8) + ')');

  // Buscar dados via background.js (sem restrições CORS)
  const resp = await new Promise(resolve =>
    chrome.runtime.sendMessage({ type: 'FETCH_DADOS', sessao_id, server_url }, resolve)
  );

  if (!resp || !resp.ok) {
    const erro = resp ? resp.erro : 'Sem resposta da extens\u00e3o';
    log('Erro ao buscar dados: ' + erro);
    await pausarParaUsuario(
      'N\u00e3o foi poss\u00edvel buscar os dados do c\u00e1lculo.<br>' +
      'Erro: <em>' + erro + '</em><br>' +
      'Verifique se o servidor est\u00e1 acess\u00edvel e clique em Continuar para tentar novamente.'
    );
    return;
  }

  // Salvar estado e iniciar automação
  estado = {
    dados:  resp.dados.dados,
    verbas: resp.dados.verbas_mapeadas || {},
    fase:   0,
  };
  salvarEstado(estado);

  log('Dados carregados. Iniciando preenchimento...');
  await aguardar(800);
  await executarFase(estado);
}

// ── Ponto de Entrada ──────────────────────────────────────────────────────────

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', main);
} else {
  main();
}
