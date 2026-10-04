'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const MARCADOR = '// --- fim da lógica pura; nada abaixo desta linha é injetado no n8n ---';

test('route.js tem o marcador que o injetor usa para cortar', () => {
  const fonte = fs.readFileSync(path.join(__dirname, 'route.js'), 'utf8');
  assert.equal(fonte.includes(MARCADOR), true,
    'sem o marcador, add_asset_query_branch.py nao sabe onde cortar o module.exports');
  assert.equal(fonte.indexOf(MARCADOR), fonte.lastIndexOf(MARCADOR),
    'o marcador tem que aparecer uma unica vez');
});

test('a logica pura nao usa nada do n8n nem do Node', () => {
  const fonte = fs.readFileSync(path.join(__dirname, 'route.js'), 'utf8');
  const pura = fonte.split(MARCADOR)[0];
  for (const proibido of ['$input', '$json', "require(", 'module.exports', 'process.']) {
    assert.equal(pura.includes(proibido), false,
      `a logica pura nao pode conter ${proibido}`);
  }
});
