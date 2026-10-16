/* Real API26 declarations; strips only ArkUI DSL/decorators, not caller methods.
 * Does not run the ArkTS/HAP compiler or prove installation/runtime. */
const ts = require(process.argv[3]), fs = require('fs'), path = require('path');
let text = fs.readFileSync(process.argv[2], 'utf8');
text = text.replace(/^@Entry\s*$/mg, '').replace(/^@Component\s*$/mg, '')
  .replace(/@State\s+/g, '').replace('struct Index {', 'class Index {');
const start = text.indexOf('  build() {');
if (start < 0) throw new Error('exact real UI build method required');
let depth = 0, end = -1;
for (let i = text.indexOf('{', start); i < text.length; i++) {
  if (text[i] === '{') depth++;
  else if (text[i] === '}' && --depth === 0) { end = i + 1; break; }
}
if (end < 0) throw new Error('unbalanced build body');
text = text.slice(0, start) + text.slice(end);
const base = process.argv[4], api = process.argv[5];
const source = path.join(base, 'caller.ts'), stub = path.join(base, 'arkui-context.d.ts');
fs.writeFileSync(source, text);
fs.writeFileSync(stub, "declare function getContext(value: object): import('@ohos.app.ability.common').default.UIAbilityContext;\n");
const program = ts.createProgram([source, stub], {strict: true, noEmit: true, skipLibCheck: true,
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, moduleResolution: ts.ModuleResolutionKind.NodeJs,
  baseUrl: api, paths: {'@ohos.*': ['@ohos.*.d.ts'], '@kit.*': ['../kits/@kit.*.d.ts']}});
const errors = ts.getPreEmitDiagnostics(program).filter(d => d.category === ts.DiagnosticCategory.Error);
if (errors.length) {
  console.error(ts.formatDiagnosticsWithColorAndContext(errors, {getCurrentDirectory: () => process.cwd(),
    getNewLine: () => '\n', getCanonicalFileName: x => x})); process.exitCode = 1;
} else console.log('Actual API26 ordinary PNG import/legacy permission and system-boundary caller methods type-check; ArkTS/HAP remains root-owned.');
