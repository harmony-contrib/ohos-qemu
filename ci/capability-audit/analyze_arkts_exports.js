#!/usr/bin/env node
/* Compare API 26 runtime-bearing declarations with the properties exported by each loaded module. */

const fs = require('fs');
const path = require('path');

function argumentsFrom(argv) {
  const result = {};
  for (let index = 2; index < argv.length; index += 2) {
    const key = argv[index];
    if (!key.startsWith('--') || index + 1 >= argv.length) {
      throw new Error(`invalid argument at ${key}`);
    }
    result[key.slice(2)] = argv[index + 1];
  }
  for (const key of ['typescript', 'api-dir', 'kits-dir', 'runtime', 'output']) {
    if (!result[key]) throw new Error(`missing --${key}`);
  }
  return result;
}

const args = argumentsFrom(process.argv);
const ts = require(path.resolve(args.typescript));

function bindingNames(name, output) {
  if (ts.isIdentifier(name)) {
    output.add(name.text);
    return;
  }
  for (const element of name.elements || []) {
    if (!ts.isOmittedExpression(element)) bindingNames(element.name, output);
  }
}

function metadata(node) {
  const result = {
    syscaps: [],
    since: null,
    dynamic_since: null,
    static_since: null,
    availability: [],
    system_api: false,
  };
  for (const tag of ts.getJSDocTags(node)) {
    const name = tag.tagName.text;
    const comment = typeof tag.comment === 'string' ? tag.comment : '';
    if (name === 'syscap') {
      const match = comment.match(/SystemCapability\.[A-Za-z0-9_.]+/);
      if (match) result.syscaps.push(match[0]);
    } else if (name === 'since') {
      const match = comment.match(/\d+/);
      if (!match) continue;
      const version = Number(match[0]);
      const normalized = comment.toLowerCase();
      let modes;
      if (/dynamic\s*&\s*static/.test(normalized)) modes = ['dynamic', 'static'];
      else if (/\bdynamiconly\b|\bdynamic\b/.test(normalized)) modes = ['dynamic'];
      else if (/\bstaticonly\b|\bstatic\b/.test(normalized)) modes = ['static'];
      // interface-sdk-js defines an unqualified @since as dynamic by default.
      else modes = ['dynamic'];
      for (const mode of modes) {
        const key = `${mode}_since`;
        if (result[key] === null || version < result[key]) result[key] = version;
      }
    } else if (name === 'systemapi') {
      result.system_api = true;
    }
  }
  result.availability = ['dynamic', 'static'].filter(
    (mode) => result[`${mode}_since`] !== null
  );
  result.since = result.dynamic_since ?? result.static_since;
  result.syscaps = [...new Set(result.syscaps)].sort();
  return result;
}

function addDeclaration(output, name, node, kind) {
  const detail = metadata(node);
  detail.kind = kind;
  const previous = output.get(name);
  if (!previous) {
    output.set(name, detail);
    return;
  }
  previous.syscaps = [...new Set([...previous.syscaps, ...detail.syscaps])].sort();
  if (previous.since === null || (detail.since !== null && detail.since < previous.since)) {
    previous.since = detail.since;
  }
  for (const mode of ['dynamic', 'static']) {
    const key = `${mode}_since`;
    if (previous[key] === null || (detail[key] !== null && detail[key] < previous[key])) {
      previous[key] = detail[key];
    }
  }
  previous.availability = ['dynamic', 'static'].filter(
    (mode) => previous[`${mode}_since`] !== null
  );
  previous.system_api = previous.system_api && detail.system_api;
  if (previous.kind !== detail.kind) previous.kind = 'overloaded';
}

function declarationNames(statement, output) {
  const isDefault = (statement.modifiers || []).some(
    (modifier) => modifier.kind === ts.SyntaxKind.DefaultKeyword
  );
  if (isDefault) return;
  if (ts.isFunctionDeclaration(statement) || ts.isClassDeclaration(statement) ||
      ts.isEnumDeclaration(statement)) {
    const isConstEnum = ts.isEnumDeclaration(statement) && (statement.modifiers || []).some(
      (modifier) => modifier.kind === ts.SyntaxKind.ConstKeyword
    );
    const kind = ts.isFunctionDeclaration(statement) ? 'function' :
      (ts.isClassDeclaration(statement) ? 'class' : (isConstEnum ? 'const_enum' : 'enum'));
    if (statement.name) addDeclaration(output, statement.name.text, statement, kind);
  } else if (ts.isVariableStatement(statement)) {
    for (const declaration of statement.declarationList.declarations) {
      const names = new Set();
      bindingNames(declaration.name, names);
      for (const name of names) addDeclaration(output, name, statement, 'variable');
    }
  } else if (ts.isModuleDeclaration(statement)) {
    if (ts.isIdentifier(statement.name) || ts.isStringLiteral(statement.name)) {
      addDeclaration(output, statement.name.text, statement, 'namespace');
    }
  }
}

function isExported(statement) {
  return (statement.modifiers || []).some(
    (modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword
  );
}

function moduleBlocks(declaration) {
  let body = declaration.body;
  while (body && ts.isModuleDeclaration(body)) body = body.body;
  return body && ts.isModuleBlock(body) ? [body] : [];
}

function expectedExports(file) {
  const sourceText = fs.readFileSync(file, 'utf8');
  const source = ts.createSourceFile(file, sourceText, ts.ScriptTarget.Latest, true,
                                     ts.ScriptKind.TS);
  let defaultNamespace = null;
  for (const statement of source.statements) {
    if (ts.isExportAssignment(statement) && !statement.isExportEquals &&
        ts.isIdentifier(statement.expression)) {
      defaultNamespace = statement.expression.text;
    }
  }

  const names = new Map();
  for (const statement of source.statements) {
    if (defaultNamespace && ts.isModuleDeclaration(statement) &&
        statement.name.text === defaultNamespace) {
      for (const block of moduleBlocks(statement)) {
        for (const member of block.statements) declarationNames(member, names);
      }
    }
    if (isExported(statement) && !ts.isExportDeclaration(statement) &&
        !ts.isInterfaceDeclaration(statement) &&
        !ts.isTypeAliasDeclaration(statement)) {
      declarationNames(statement, names);
    }
  }
  names.delete(defaultNamespace);
  return [...names.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, detail]) => ({name, ...detail}));
}

const runtime = JSON.parse(fs.readFileSync(args.runtime, 'utf8'));
const rows = [];
for (const module of runtime.modules) {
  const root = module.module.startsWith('@kit.') ? args['kits-dir'] : args['api-dir'];
  const file = path.join(root, `${module.module}.d.ts`);
  const allExpectedDetails = expectedExports(file);
  // napi_load_module() exercises dynamic ArkTS. Static-only declarations use
  // the ANI/Taihe/ABC path and must not be treated as properties of a NAPI
  // module object. Declarations without a mode-qualified @since remain part
  // of the dynamic contract; excluding them would silently drop inherited or
  // older declarations whose mode is not written on the export itself.
  const expectedDetails = allExpectedDetails.filter(
    (detail) => detail.kind !== 'const_enum' &&
      (detail.availability.length === 0 || detail.availability.includes('dynamic'))
  );
  // Ambient const enums need not have a NAPI object: a program compiler can
  // inline their members. Keep the SDK contract visible and pending a real
  // compiled caller check; absence in Object.keys() is not that check.
  const compiledConstants = allExpectedDetails.filter(
    (detail) => detail.kind === 'const_enum' &&
      (detail.availability.length === 0 || detail.availability.includes('dynamic'))
  ).map((detail) => ({...detail, status: 'compiled_caller_not_verified'}));
  const staticOnlyDetails = allExpectedDetails.filter(
    (detail) => !detail.availability.includes('dynamic') &&
      detail.availability.includes('static')
  );
  const expected = expectedDetails.map((detail) => detail.name);
  const actual = [...(module.exports || [])].sort();
  const actualSet = new Set(actual);
  const expectedSet = new Set(expected);
  const missing = expected.filter((name) => !actualSet.has(name));
  const missingDetails = expectedDetails.filter((detail) => !actualSet.has(detail.name));
  const officialSet = new Set(module.official_profile_syscaps);
  const missingOfficial = missingDetails.filter((detail) =>
    detail.syscaps.length === 0 ? officialSet.size > 0 :
      detail.syscaps.some((syscap) => officialSet.has(syscap))
  );
  const unexpected = actual.filter((name) => !expectedSet.has(name));
  let status;
  if (!module.loaded) status = 'module_load_failed';
  else if (module.export_probe_status !== 0) status = 'export_probe_failed';
  else if (missingOfficial.length) status = 'official_runtime_exports_missing';
  else if (missing.length) status = 'runtime_exports_missing_outside_profile';
  else status = 'runtime_exports_complete';
  rows.push({
    module: module.module,
    loaded: module.loaded,
    audit_status: module.audit_status,
    official_profile_syscaps: module.official_profile_syscaps,
    expected_runtime_exports: expected,
    expected_runtime_export_details: expectedDetails,
    compiled_constant_enum_contracts: compiledConstants,
    static_only_exports_excluded_from_dynamic_probe: staticOnlyDetails,
    actual_runtime_exports: actual,
    missing_runtime_exports: missing,
    missing_runtime_export_details: missingDetails,
    missing_official_runtime_exports: missingOfficial,
    unexpected_runtime_exports: unexpected,
    status,
  });
}

const summary = {
  module_count: rows.length,
  loaded: rows.filter((row) => row.loaded).length,
  export_surface_complete: rows.filter((row) => row.status === 'runtime_exports_complete').length,
  official_export_surface_missing: rows.filter(
    (row) => row.status === 'official_runtime_exports_missing'
  ).length,
  outside_profile_export_surface_missing: rows.filter(
    (row) => row.status === 'runtime_exports_missing_outside_profile'
  ).length,
  export_probe_failed: rows.filter((row) => row.status === 'export_probe_failed').length,
  module_load_failed: rows.filter((row) => row.status === 'module_load_failed').length,
  missing_export_count: rows.reduce((total, row) => total + row.missing_runtime_exports.length, 0),
  missing_official_export_count: rows.reduce(
    (total, row) => total + row.missing_official_runtime_exports.length, 0
  ),
  missing_official_public_function_count: rows.reduce(
    (total, row) => total + row.missing_official_runtime_exports.filter(
      (detail) => detail.kind === 'function' && !detail.system_api
    ).length, 0
  ),
  missing_official_system_function_count: rows.reduce(
    (total, row) => total + row.missing_official_runtime_exports.filter(
      (detail) => detail.kind === 'function' && detail.system_api
    ).length, 0
  ),
  static_only_export_count_excluded_from_dynamic_probe: rows.reduce(
    (total, row) => total + row.static_only_exports_excluded_from_dynamic_probe.length, 0
  ),
  compiled_constant_enum_contract_count: rows.reduce(
    (total, row) => total + row.compiled_constant_enum_contracts.length, 0
  ),
};
const result = {profile: runtime.profile, summary, modules: rows};
fs.mkdirSync(path.dirname(args.output), {recursive: true});
fs.writeFileSync(args.output, JSON.stringify(result, null, 2) + '\n');
process.stdout.write(JSON.stringify(summary, null, 2) + '\n');
