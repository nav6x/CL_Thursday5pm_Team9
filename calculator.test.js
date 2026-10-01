const test = require('node:test');
const assert = require('node:assert');
const { add, multiply } = require('./calculator');

test('adds two numbers', () => {
  assert.strictEqual(add(2, 3), 5);
});

test('multiplies two numbers', () => {
  assert.strictEqual(multiply(4, 5), 20);
});
