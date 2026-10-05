'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

// Aponta para o export canonico VERSIONADO do workflow publicado. O default
// anterior era gentileza-stage2.json, que nunca foi commitado nem publicado:
// num clone limpo o npm test inteiro morria em ENOENT, e os testes rodavam
// contra um workflow que nao estava no ar.
const path = process.env.DOMAIN_WORKFLOW || '/n8n/workflows/chat-om-publicado.json';
const workflow = JSON.parse(fs.readFileSync(path, 'utf8'))[0];
const nodes = Object.fromEntries(workflow.nodes.map((node) => [node.name, node]));

function runCode(name, input, references) {
  const code = nodes[name].parameters.jsCode;
  const lookup = (target) => ({ first: () => ({ json: references[target] }) });
  const result = new Function('$input', '$', code)(
    { first: () => ({ json: input }) }, lookup,
  );
  return result[0].json;
}

test('custo mantém período no acompanhamento, usa a conta do roteador e retira filtro agrupado', () => {
  const route = { domain: 'custos', sessionId: 's', accessToken: 'token', contaRazao: '41140014',
    followUpHint: true,
    estadoPreservado: { domain: 'custos', year: 2026, month: 8, supplier: 'Antigo', query_shape: 'count' } };
  const query = runCode('Mesclar Consulta de Custos',
    { output: { follow_up: true, query_shape: 'group', group_by: 'supplier', supplier: null, clear_fields: [] } },
    { 'Roteamento da Consulta': route, 'When chat message received': { chatInput: 'Por fornecedor?' } });
  assert.equal(query.conta_razao, '41140014');
  assert.equal(query.year, 2026);
  assert.equal(query.month, 8);
  assert.equal(query.group_by, 'supplier');
  assert.equal(query.supplier, null);
  assert.equal(query.session_id, 's');
});

test('pergunta nova de custos limpa filtros anteriores', () => {
  const route = { domain: 'custos', sessionId: 's', accessToken: 'token', contaRazao: null,
    followUpHint: false,
    estadoPreservado: { domain: 'custos', year: 2026, conta_razao: '41140014' } };
  const query = runCode('Mesclar Consulta de Custos',
    { output: { follow_up: false, query_shape: 'count', group_by: null, clear_fields: [] } },
    { 'Roteamento da Consulta': route, 'When chat message received': { chatInput: 'Quanto custou?' } });
  assert.equal(query.year, null);
  assert.equal(query.conta_razao, null);
});

test('pergunta nova NAO herda filtro de outro dominio', () => {
  // Turno anterior: chamados corretivos em Natal, agosto. Agora uma pergunta
  // independente de custos sobre o ano inteiro. Herdar praça e mês devolveria
  // Natal/agosto a uma pergunta nacional e anual — e com cifra de dinheiro.
  const route = { domain: 'custos', sessionId: 's', accessToken: 'token', contaRazao: null,
    followUpHint: false,
    estadoPreservado: { domain: 'chamados_corretiva', praca: 'Natal', year: 2026, month: 8 } };
  const query = runCode('Mesclar Consulta de Custos',
    { output: { follow_up: false, query_shape: 'count', group_by: null, clear_fields: [] } },
    { 'Roteamento da Consulta': route,
      'When chat message received': { chatInput: 'Quanto gastamos com manutenção em 2026?' } });
  assert.equal(query.praca, null);
  assert.equal(query.month, null);
  assert.equal(query.year, null);
});

test('follow_up false do modelo vence a dica do roteador', () => {
  // A dica existe para quando o modelo ESQUECE de marcar acompanhamento. Ela não
  // pode sobrepor uma negativa explícita: "quais as lojas com maior gasto?" é
  // pergunta completa, e herdar praça e mês daria um ranking de um só mês.
  const route = { domain: 'custos', sessionId: 's', accessToken: 'token', contaRazao: null,
    followUpHint: true,
    estadoPreservado: { domain: 'custos', praca: 'Natal', month: 8, year: 2026 } };
  const query = runCode('Mesclar Consulta de Custos',
    { output: { follow_up: false, query_shape: 'ranking', group_by: 'store_name', clear_fields: [] } },
    { 'Roteamento da Consulta': route,
      'When chat message received': { chatInput: 'Quais as lojas com maior gasto de manutenção?' } });
  assert.equal(query.praca, null);
  assert.equal(query.month, null);
  assert.equal(query.group_by, 'store_name');
});

test('a dica ainda salva o acompanhamento quando o modelo omite follow_up', () => {
  const route = { domain: 'custos', sessionId: 's', accessToken: 'token', contaRazao: null,
    followUpHint: true,
    estadoPreservado: { domain: 'custos', praca: 'Natal', query_shape: 'count' } };
  const query = runCode('Mesclar Consulta de Custos',
    { output: { query_shape: 'count', group_by: null, clear_fields: [] } },
    { 'Roteamento da Consulta': route,
      'When chat message received': { chatInput: 'E quantos desses no mês passado?' } });
  assert.equal(query.praca, 'Natal');
});

test('preventiva conserva periodicidade no acompanhamento', () => {
  const route = { domain: 'chamados_preventiva', sessionId: 's', accessToken: 'token',
    followUpHint: true,
    estadoPreservado: { domain: 'chamados_preventiva', periodicity: 'Mensal', query_shape: 'count' } };
  const query = runCode('Mesclar Consulta Preventiva',
    { output: { follow_up: true, query_shape: 'count', group_by: null, praca: 'Natal', clear_fields: [] } },
    { 'Roteamento da Consulta': route });
  assert.equal(query.periodicity, 'Mensal');
  assert.equal(query.praca, 'Natal');
  assert.equal(query.date_field, 'created_on');
});

test('resposta de custos preserva estorno negativo e recusa filtro ausente no SAP', () => {
  const references = { 'Mesclar Consulta de Custos': { conta_razao: '41140014' } };
  const negative = runCode('Montar Resposta de Custos',
    { query_shape: 'count', total_count: 1, total_amount: '-20.70' }, references);
  assert.match(negative.output, /20,70/);
  assert.match(negative.output, /Estornos negativos/);
  const unsupported = runCode('Montar Resposta de Custos',
    { unsupported_filter: 'ar-condicionado', query_shape: 'count', total_count: 0 }, references);
  assert.match(unsupported.output, /não identifica ar-condicionado/);
});

test('custo de equipamento é recusado mesmo sem marcação do modelo', () => {
  const route = { domain: 'custos', sessionId: 's', accessToken: 'token', contaRazao: null,
    followUpHint: false, estadoPreservado: {} };
  const query = runCode('Mesclar Consulta de Custos',
    { output: { follow_up: false, query_shape: 'count', clear_fields: [], unsupported_filter: null } },
    { 'Roteamento da Consulta': route,
      'When chat message received': { chatInput: 'Quanto gastamos com ar-condicionado?' } });
  assert.equal(query.unsupported_filter, 'ar-condicionado');
  const category = runCode('Mesclar Consulta de Custos',
    { output: { follow_up: false, query_shape: 'count', clear_fields: [], unsupported_filter: null } },
    { 'Roteamento da Consulta': route,
      'When chat message received': { chatInput: 'Custos por categoria' } });
  assert.equal(category.unsupported_filter, 'categoria');
});

test('acompanhamento de ativos preserva equipamento, loja e capacidade', () => {
  // Antes, o estado de ativos salvava 9 colunas e filtros como tipo de
  // equipamento e código de loja nao sobreviviam: "e no salao de venda?" depois
  // de "quantos extintores na loja 4006?" respondia por todo incendio em
  // qualquer loja, citando menos filtros do que a pergunta anterior.
  const route = { domain: 'ativos', sessionId: 's', accessToken: 'token', followUpHint: true,
    estadoPreservado: { domain: 'ativos', asset_type: '["fire_safety"]', equipment_type: 'Extintor',
      store_code: '4006', brand: 'Marca X', capacity_btu_min: '18000', query_shape: 'count' } };
  const query = runCode('Mesclar Consulta de Ativos',
    { output: { follow_up: true, query_shape: 'count', location: 'salão de venda', clear_fields: [] } },
    { 'Roteamento da Consulta': route });

  assert.deepEqual(query.asset_types, ['fire_safety']);
  assert.equal(query.equipment_type, 'Extintor');
  assert.equal(query.store_code, '4006');
  assert.equal(query.brand, 'Marca X');
  assert.equal(query.location, 'salão de venda');
  // A coluna e texto; a API espera numero.
  assert.equal(query.capacity_btu_min, 18000);
});

test('resposta desconhecida mostra os quatro assuntos', () => {
  const output = runCode('Responder Assunto Desconhecido', {}, {}).output;
  for (const label of ['corretivos', 'preventivos', 'ativos', 'custos']) {
    assert.match(output, new RegExp(label));
  }
});
