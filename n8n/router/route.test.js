'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { route, preservarEstado, normalizar, DOMINIOS_VALIDOS } = require('./route.js');

const TODOS = ['chamados_corretiva', 'chamados_preventiva', 'ativos', 'custos'];

const rotear = (chatInput, extra = {}) =>
  route({ chatInput, lastDomain: null, allowedDomains: TODOS, ...extra });

test('custo vence ativo e o qualificador vira filtro de conta razão', () => {
  assert.equal(rotear('quanto gastamos com ar condicionado').domain, 'custos');
  const corretiva = rotear('qual o custo de manutenção corretiva em agosto?');
  assert.equal(corretiva.domain, 'custos');
  assert.equal(corretiva.contaRazao, '41140014');
  const preventiva = rotear('custo de manutenção preventiva');
  assert.equal(preventiva.domain, 'custos');
  assert.equal(preventiva.contaRazao, '41140026');
  assert.equal(rotear('qual loja teve o maior custo de manutenção?').contaRazao, null);
});

test('chamado vence ativo', () => {
  // Pergunta de chamado filtrada por categoria, não consulta de inventário.
  assert.equal(rotear('quantos chamados de ar condicionado?').domain, 'chamados_corretiva');
  assert.equal(rotear('quantos chamados estão abertos?').domain, 'chamados_corretiva');
});

test('qualificador decide o subtipo do chamado', () => {
  assert.equal(rotear('quantos chamados preventivos foram concluídos?').domain, 'chamados_preventiva');
  assert.equal(rotear('quantos chamados corretivos?').domain, 'chamados_corretiva');
});

test('qualificador sozinho implica chamado e vence marcador de ativo', () => {
  assert.equal(rotear('liste as preventivas atrasadas da praça Natal').domain, 'chamados_preventiva');
  // Tem "climatizacao" (ativo) e "preventivas" (qualificador): é chamado preventivo.
  assert.equal(rotear('qual a periodicidade das preventivas de climatização?').domain, 'chamados_preventiva');
});

test('ativo sem outro marcador vai para o inventário', () => {
  assert.equal(rotear('quantos extintores existem na loja 4006?').domain, 'ativos');
  assert.equal(rotear('liste os purificadores da praça Natal').domain, 'ativos');
});

test('sem marcador usa o domínio anterior', () => {
  assert.equal(rotear('e na praça Natal?', { lastDomain: 'ativos' }).domain, 'ativos');
  assert.equal(rotear('e quantos desses tem na loja 4006?', { lastDomain: 'custos' }).domain, 'custos');
});

test('sem marcador e sem contexto é desconhecido', () => {
  assert.equal(rotear('qual a capital da França?').domain, 'desconhecido');
});

test('acento e caixa não alteram a rota', () => {
  assert.equal(rotear('QUANTOS CHAMADOS PREVENTIVOS?').domain, 'chamados_preventiva');
  assert.equal(rotear('quantos chamados preventivos?').domain, 'chamados_preventiva');
  assert.equal(normalizar('Climatização'), 'climatizacao');
});

// --- Review Focus ---

test('domain nulo das 117 linhas existentes não vira domínio', () => {
  // A coluna domain será criada depois das linhas; todas vêm nulas.
  for (const vazio of [null, undefined, '', '   ']) {
    assert.equal(rotear('e na praça Natal?', { lastDomain: vazio }).domain, 'desconhecido');
  }
});

test('lastDomain inválido é descartado', () => {
  // "service" era o nome do roteador antigo e não é domínio válido.
  for (const invalido of ['service', 'asset', 'chamados', 'qualquer_coisa']) {
    assert.equal(rotear('e na praça Natal?', { lastDomain: invalido }).domain, 'desconhecido');
  }
});

test('sem permissão o domínio reconhecido vira sem_acesso, não desconhecido', () => {
  const negado = rotear('quantos extintores na loja 4006?', { allowedDomains: [] });
  assert.equal(negado.domain, 'sem_acesso');
  assert.equal(negado.deniedDomain, 'ativos');

  const soAtivos = rotear('quantos chamados abertos?', { allowedDomains: ['ativos'] });
  assert.equal(soAtivos.domain, 'sem_acesso');
  assert.equal(soAtivos.deniedDomain, 'chamados_corretiva');

  // Desconhecido não é negado: não há domínio a negar.
  assert.equal(rotear('qual a capital da França?', { allowedDomains: [] }).domain, 'desconhecido');
});

test('mensagem vazia, nula ou só pontuação não lança', () => {
  for (const vazio of [null, undefined, '', '   ', '???', '...']) {
    assert.equal(rotear(vazio).domain, 'desconhecido');
    assert.equal(rotear(vazio, { lastDomain: 'ativos' }).domain, 'ativos');
  }
});

test('qualificadores contraditórios resolvem de forma determinística', () => {
  // Preventivo é testado primeiro, então vence. Regra documentada, não acidente.
  assert.equal(rotear('chamados corretivos e preventivos').domain, 'chamados_preventiva');
});

test('DOMINIOS_VALIDOS não inclui os resultados de controle', () => {
  assert.equal(DOMINIOS_VALIDOS.has('ativos'), true);
  assert.equal(DOMINIOS_VALIDOS.has('desconhecido'), false);
  assert.equal(DOMINIOS_VALIDOS.has('sem_acesso'), false);
});

// --- dica determinística de acompanhamento ---

test('acompanhamento no mesmo domínio liga a dica', () => {
  assert.equal(rotear('e na praça Natal?', { lastDomain: 'ativos' }).followUpHint, true);
  // A pergunta 4 do critério de aceite do marco.
  assert.equal(
    rotear('e quantos desses tem no salão de venda?', { lastDomain: 'ativos' }).followUpHint,
    true,
  );
  assert.equal(rotear('quantos desses foram concluídos?', { lastDomain: 'chamados_corretiva' }).followUpHint, true);
});

test('pergunta completa não é acompanhamento', () => {
  assert.equal(rotear('quantos extintores na loja 4006?', { lastDomain: 'ativos' }).followUpHint, false);
  assert.equal(rotear('quantos chamados estão abertos?', { lastDomain: 'chamados_corretiva' }).followUpHint, false);
});

test('a dica não atravessa troca de domínio', () => {
  // Parece acompanhamento, mas o domínio mudou: herdar filtro seria vazamento.
  const trocou = rotear('e quantos desses extintores tem?', { lastDomain: 'chamados_corretiva' });
  assert.equal(trocou.domain, 'ativos');
  assert.equal(trocou.followUpHint, false);
});

test('sem domínio anterior não há acompanhamento', () => {
  assert.equal(rotear('e quantos extintores tem?').followUpHint, false);
});

test('desconhecido e sem_acesso nunca ligam a dica', () => {
  assert.equal(rotear('qual a capital da França?').followUpHint, false);
  assert.equal(
    rotear('e na praça Natal?', { lastDomain: 'ativos', allowedDomains: [] }).followUpHint,
    false,
  );
});

// --- preservação de estado na troca de domínio ---

test('mesmo domínio preserva o estado inteiro', () => {
  const anterior = {
    domain: 'chamados_corretiva', praca: 'Natal', supplier: 'ONFLY',
    category: 'Climatização', year: 2026,
  };
  const mantido = preservarEstado(anterior, 'chamados_corretiva');

  assert.equal(mantido.praca, 'Natal');
  assert.equal(mantido.supplier, 'ONFLY');
  assert.equal(mantido.category, 'Climatização');
  assert.equal(mantido.year, 2026);
});

test('trocar de domínio preserva só os campos compartilhados', () => {
  const anterior = {
    domain: 'chamados_corretiva', praca: 'Natal', year: 2026, month: 8,
    supplier: 'ONFLY', category: 'Climatização', status: 'Concluído',
    analyst_responsible: 'Ana', selection_context: '{"lojas":["x"]}',
  };
  const mantido = preservarEstado(anterior, 'ativos');

  // Compartilhados sobrevivem: "e na praça Natal?" continua funcionando.
  assert.equal(mantido.praca, 'Natal');
  assert.equal(mantido.year, 2026);
  assert.equal(mantido.month, 8);
  // Específicos do domínio anterior não contaminam o novo.
  for (const vazou of ['supplier', 'category', 'status', 'analyst_responsible', 'selection_context']) {
    assert.equal(mantido[vazou], undefined, `${vazou} vazou para o domínio novo`);
  }
});

test('conta_razao de custos não vaza para ativos', () => {
  const anterior = { domain: 'custos', conta_razao: '41140014', praca: 'Natal' };
  const mantido = preservarEstado(anterior, 'ativos');

  assert.equal(mantido.conta_razao, undefined);
  assert.equal(mantido.praca, 'Natal');
});

test('estado anterior ausente ou sem domínio não lança', () => {
  for (const vazio of [null, undefined, {}]) {
    const mantido = preservarEstado(vazio, 'ativos');
    assert.equal(typeof mantido, 'object');
    assert.equal(mantido.praca, undefined);
  }
});

test('as 117 linhas sem domain são tratadas como troca de domínio', () => {
  // domain nulo: não há como saber de que domínio o estado é, então só o
  // compartilhado sobrevive.
  const anterior = { domain: null, praca: 'Natal', supplier: 'ONFLY' };
  const mantido = preservarEstado(anterior, 'ativos');

  assert.equal(mantido.praca, 'Natal');
  assert.equal(mantido.supplier, undefined);
});
