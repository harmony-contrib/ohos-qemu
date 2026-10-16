// Focused host approximation of ArkTS's Error-only throw constraint. The real
// complete official ArkTS/HAP checker is still the final acceptance authority.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const ts = require(path.join(process.argv[2], 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js'));
const actual = process.argv[3];
const negative = path.join(path.dirname(actual), 'limited-throw-negative.ts');
fs.writeFileSync(negative, `
function unknownCatch(): void { try { throw new Error('real'); } catch (error) { throw error; } }
function arbitraryString(): void { throw 'not an Error'; }
function arbitraryAny(value: any): void { throw value; }
`);
const program = ts.createProgram([actual, negative], {
  strict: true, skipLibCheck: true, target: ts.ScriptTarget.ES2020,
  module: ts.ModuleKind.CommonJS, moduleResolution: ts.ModuleResolutionKind.NodeJs,
  baseUrl: path.join(process.argv[2], 'ets/api')
});
const checker = program.getTypeChecker();
function invalidThrows(filename) {
  const source = program.getSourceFile(filename); assert(source);
  const symbol = checker.resolveName('Error', source, ts.SymbolFlags.Type, false); assert(symbol);
  const errorType = checker.getDeclaredTypeOfSymbol(symbol);
  const invalid = [];
  function visit(node) {
    if (ts.isThrowStatement(node)) {
      const value = checker.getTypeAtLocation(node.expression);
      if ((value.flags & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) !== 0 || !checker.isTypeAssignableTo(value, errorType)) {
        invalid.push(node.expression.getText(source));
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(source); return invalid;
}
assert.deepStrictEqual(invalidThrows(actual), [], 'candidate has a throw expression without Error type');
assert.deepStrictEqual(invalidThrows(negative), ['error', "'not an Error'", 'value']);
console.log('Official SDK TypeChecker Error-only host guard: real candidate passes; catch unknown/string/any throw regressions rejected. Full real ArkTS/HAP recheck required.');
