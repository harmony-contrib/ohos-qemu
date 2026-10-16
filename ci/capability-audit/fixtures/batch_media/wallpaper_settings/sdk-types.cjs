/* Official declaration check only. Does not run the ArkTS/HAP compiler. */
const ts=require(process.argv[3]),fs=require('fs'),path=require('path');
const source=process.argv[2],base=process.argv[4],api=process.argv[5];
const input=path.join(base,'controller.ts'),stub=path.join(base,'settings.d.ts');
fs.copyFileSync(source,input);
fs.writeFileSync(stub,`declare module '@ohos/settings.common/src/main/ets/utils/SystemParamUtil' {export class SystemParamUtil {static isModifyWallpaperDisable(): Promise<boolean>;}}
declare module '@ohos/settings.common/src/main/ets/utils/LogUtil' {export class LogUtil {static error(message: string): void;static info(message: string): void;}}`);
const program=ts.createProgram([input,stub],{strict:true,noEmit:true,skipLibCheck:true,target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,moduleResolution:ts.ModuleResolutionKind.NodeJs,baseUrl:api,paths:{'@ohos.*':['@ohos.*.d.ts']}});
const errors=ts.getPreEmitDiagnostics(program).filter(d=>d.category===ts.DiagnosticCategory.Error);
if(errors.length){console.error(ts.formatDiagnosticsWithColorAndContext(errors,{getCurrentDirectory:()=>process.cwd(),getNewLine:()=> '\n',getCanonicalFileName:x=>x}));process.exitCode=1;}
else console.log('API26 actual declarations: public Picker/FS/Image and system Wallpaper types passed; ArkTS/HAP pending');
