#!/usr/bin/env node
/* Read actual SDK declarations; never evaluate source text or invent NAPI exports. */
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function extract(ts, apiDir, requested, requireConst = true) {
  const files = requested.map(row => path.join(apiDir, row.module + '.d.ts'));
  const program = ts.createProgram(files, { noLib: true, noResolve: true });
  const checker = program.getTypeChecker();
  const output = [];
  for (let index = 0; index < requested.length; index++) {
    const request = requested[index];
    if (!/^@ohos\.[A-Za-z0-9_.]+$/.test(request.module)) throw Error('invalid SDK module');
    const file = files[index];
    const source = program.getSourceFile(file);
    if (!source) throw Error('actual SDK declaration missing: ' + file);
    const diagnostics = program.getSemanticDiagnostics(source);
    const defaults = source.statements.filter(ts.isExportAssignment);
    const defaultNames = defaults.filter(node => !node.isExportEquals && ts.isIdentifier(node.expression))
      .map(node => node.expression.text);
    for (const contract of request.contracts) {
      const matches = [];
      function walk(node, namespaces) {
        if (ts.isEnumDeclaration(node) && node.name.text === contract.name) {
          if (diagnostics.some(entry => entry.category === ts.DiagnosticCategory.Error &&
              entry.start >= node.getStart(source) && entry.start < node.end)) {
            throw Error('compiler rejected SDK enum declaration: ' + contract.name);
          }
          const isConst = (node.modifiers || []).some(modifier => modifier.kind === ts.SyntaxKind.ConstKeyword);
          if (isConst !== requireConst) {
            throw Error('baseline enum const/runtime kind differs in this SDK: ' + contract.name);
          }
          // Members of an ambient namespace may be implicitly exported.
          // Check the compiler's export table rather than requiring spelling.
          const container = namespaces.length ? node.parent.parent : source;
          const symbol = checker.getSymbolAtLocation(namespaces.length ? container.name : source);
          if (!symbol || !checker.getExportsOfModule(symbol).some(entry => entry.name === contract.name)) {
            throw Error('const enum not exported by actual SDK module: ' + contract.name);
          }
          let importKind;
          if (namespaces.length === 0) importKind = 'named';
          else if (namespaces.length === 1 && defaultNames.includes(namespaces[0])) importKind = 'default_namespace';
          else throw Error('unsupported SDK namespace contract: ' + namespaces.join('.'));
          const members = node.members.map(member => {
            if (!ts.isIdentifier(member.name)) throw Error('non-identifier enum member');
            const value = checker.getConstantValue(member);
            if (!(typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value)))) {
              throw Error('not a compiler-resolved enum constant: ' + member.name.text);
            }
            return { name: member.name.text, value };
          });
          if (!members.length || new Set(members.map(member => member.name)).size !== members.length) {
            throw Error('empty or duplicate enum members');
          }
          matches.push({ module: request.module, name: contract.name, import_kind: importKind, members,
            sdk_declaration: file, sdk_declaration_sha256: crypto.createHash('sha256')
              .update(fs.readFileSync(file)).digest('hex') });
        }
        const next = ts.isModuleDeclaration(node) ? [...namespaces, node.name.text] : namespaces;
        ts.forEachChild(node, child => walk(child, next));
      }
      walk(source, []);
      if (matches.length !== 1) throw Error('require exactly one actual enum: ' + request.module + ':' + contract.name);
      output.push(matches[0]);
    }
  }
  return output;
}

if (require.main === module) {
  const args = {};
  for (let index = 2; index < process.argv.length; index += 2) {
    if (!process.argv[index].startsWith('--') || !process.argv[index + 1]) throw Error('invalid arguments');
    args[process.argv[index].slice(2)] = process.argv[index + 1];
  }
  for (const key of ['typescript', 'api-dir', 'ledger', 'device']) if (!args[key]) throw Error('missing --' + key);
  if (!['phone', '2in1'].includes(args.device)) throw Error('invalid profile');
  const requested = JSON.parse(fs.readFileSync(args.ledger, 'utf8')).devices[args.device]
    .arkts11_compiled_constant_enum_contracts;
  process.stdout.write(JSON.stringify(extract(require(path.resolve(args.typescript)),
    path.resolve(args['api-dir']), requested)) + '\n');
}
module.exports = { extract };
