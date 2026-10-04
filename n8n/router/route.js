'use strict';

// Fonte única do roteador. O nó "Roteamento da Consulta" do n8n é artefato
// gerado: add_asset_query_branch.py injeta este arquivo e acrescenta o invólucro
// que lê a entrada do nó e devolve o item de saída. Editar o nó na interface do
// n8n faz o teste de contrato falhar — edite aqui.
//
// Nada acima do marcador de fim da lógica pura pode mencionar as globais do n8n,
// nem como exemplo em comentário: o teste de contrato procura o texto literal.

const ENTIDADES = {
  custo: /\b(custos?|gastos?|gastamos|gastou|gastar|despesas?)\b/,
  chamado: /\b(chamados?|tickets?|ordens? de servico|solicitacoes?|atendimentos?)\b/,
  ativo: /\b(ativos?|equipamentos?|inventario|climatizacao|climatizadores?|ar(?:es)?[ -]?condicionad[oa]s?|maquinas? de ar|splits?|extintores?|incendio|purificadores?|gelagua|bebedouros?|filtros? de agua|btus?)\b/,
};

const QUALIFICADORES = {
  preventivo: /\b(preventivas?|preventivos?)\b/,
  corretivo: /\b(corretivas?|corretivos?)\b/,
};

const CONTA_RAZAO = { corretivo: '41140014', preventivo: '41140026' };

// Salvaguarda determinística de continuidade, herdada do roteador antigo: uma
// pergunta curta de acompanhamento ("e na praça Natal?", "quantos desses...")
// deve herdar os filtros do turno anterior mesmo que o modelo esqueça de marcar
// follow_up. Sem isso, a pergunta de acompanhamento vira consulta nova e perde
// os filtros, que era o defeito que o hint de ativos já corrigia.
const ACOMPANHAMENTO = [
  /^(e\b|(?:quantos?|quantas?) sao\b|quais? (sao|a|as)\b)/,
  /\b(desses?|dessas?|dos ativos|das maquinas|mesma loja|nesse local|la\b)\b/,
];

const DOMINIOS_VALIDOS = new Set([
  'chamados_corretiva', 'chamados_preventiva', 'ativos', 'custos',
]);

// Dimensões que fazem sentido nos quatro domínios e por isso sobrevivem à troca
// de assunto: é o que mantém "e na praça Natal?" funcionando. Tudo que não está
// aqui é específico de um domínio e é descartado ao trocar, para que um
// fornecedor de chamado não contamine um ranking de custo.
const CAMPOS_COMPARTILHADOS = new Set([
  'praca', 'store_name', 'start_date', 'end_date', 'year', 'month',
  'date_field', 'group_by', 'limit', 'list_limit', 'sort_by', 'sort_order',
  'query_shape', 'response_format',
]);

function normalizar(valor) {
  return String(valor == null ? '' : valor)
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();
}

function detectar(texto) {
  const v = normalizar(texto);
  // Precedência de entidade: custo, chamado, ativo. "Chamados de ar
  // condicionado" é chamado filtrado por categoria, não inventário.
  const entidade = ENTIDADES.custo.test(v) ? 'custo'
    : ENTIDADES.chamado.test(v) ? 'chamado'
    : ENTIDADES.ativo.test(v) ? 'ativo'
    : null;
  const qualificador = QUALIFICADORES.preventivo.test(v) ? 'preventivo'
    : QUALIFICADORES.corretivo.test(v) ? 'corretivo'
    : null;
  return { entidade, qualificador };
}

function dominioDeChamado(qualificador) {
  return qualificador === 'preventivo' ? 'chamados_preventiva' : 'chamados_corretiva';
}

function pareceAcompanhamento(texto) {
  const v = normalizar(texto).replace(/\s+/g, ' ').trim();
  return ACOMPANHAMENTO.some((padrao) => padrao.test(v));
}

function route({ chatInput, lastDomain, allowedDomains } = {}) {
  const { entidade, qualificador } = detectar(chatInput);
  const anterior = typeof lastDomain === 'string' && DOMINIOS_VALIDOS.has(lastDomain.trim())
    ? lastDomain.trim()
    : null;

  let dominio = null;
  let contaRazao = null;

  if (entidade === 'custo') {
    dominio = 'custos';
    contaRazao = qualificador ? CONTA_RAZAO[qualificador] : null;
  } else if (entidade === 'chamado' || qualificador) {
    dominio = dominioDeChamado(qualificador);
  } else if (entidade === 'ativo') {
    dominio = 'ativos';
  } else if (anterior) {
    dominio = anterior;
  }

  if (!dominio) {
    return { domain: 'desconhecido', contaRazao: null, deniedDomain: null, followUpHint: false };
  }

  const permitidos = Array.isArray(allowedDomains) ? allowedDomains : [];
  if (!permitidos.includes(dominio)) {
    return { domain: 'sem_acesso', contaRazao: null, deniedDomain: dominio, followUpHint: false };
  }
  // A dica só vale quando há estado anterior no MESMO domínio: herdar filtros de
  // outro assunto é o vazamento que preservarEstado existe para evitar.
  const followUpHint = anterior === dominio && pareceAcompanhamento(chatInput);
  return { domain: dominio, contaRazao, deniedDomain: null, followUpHint };
}

function preservarEstado(estadoAnterior, dominioNovo) {
  const anterior = estadoAnterior && typeof estadoAnterior === 'object' ? estadoAnterior : {};
  const dominioAnterior = typeof anterior.domain === 'string' ? anterior.domain.trim() : '';
  if (dominioAnterior && dominioAnterior === dominioNovo) return { ...anterior };
  // Domínio mudou, ou o estado é antigo e não registra domínio: só o
  // compartilhado atravessa.
  const mantido = {};
  for (const campo of CAMPOS_COMPARTILHADOS) {
    if (anterior[campo] !== undefined && anterior[campo] !== null) mantido[campo] = anterior[campo];
  }
  return mantido;
}

// --- fim da lógica pura; nada abaixo desta linha é injetado no n8n ---
module.exports = {
  route, preservarEstado, detectar, normalizar, pareceAcompanhamento,
  DOMINIOS_VALIDOS, CAMPOS_COMPARTILHADOS, CONTA_RAZAO,
};
