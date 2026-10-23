#!/usr/bin/env python3
"""Read actual native Ninja/output bytes; no build/ELF-tool/resource subprocesses.

This gate proves effective compile/link flags and closed local code inputs.
It is not a runtime/CFI-type-membership or first-artifact behavior pass.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,re,shlex,struct
ACE='obj/foundation/arkui/ace_engine'
REQUIRED_DSOS=('arkui/ace_engine/libace_compatible.z.so', 'arkui/ace_engine/libace_compatible_components.z.so', 'arkui/ace_engine/libace_container_scope.z.so', 'arkui/ace_engine/libace_engine_pa_ark.z.so', 'arkui/ace_engine/libace_form_render.z.so', 'arkui/ace_engine/libace_forward_compatibility.z.so', 'arkui/ace_engine/libace_network.z.so', 'arkui/ace_engine/libace_uicontent.z.so', 'arkui/ace_engine/libace_xcomponent_controller.z.so', 'arkui/ace_engine/libarkoala_native_ani.so', 'arkui/ace_engine/libarkts_frontend.z.so', 'arkui/ace_engine/libarkui_badge.z.so', 'arkui/ace_engine/libarkui_bubble.z.so', 'arkui/ace_engine/libarkui_button.z.so', 'arkui/ace_engine/libarkui_calendarpicker.z.so', 'arkui/ace_engine/libarkui_checkbox.z.so', 'arkui/ace_engine/libarkui_containerreader.z.so', 'arkui/ace_engine/libarkui_counter.z.so', 'arkui/ace_engine/libarkui_datapanel.z.so', 'arkui/ace_engine/libarkui_datepicker.z.so', 'arkui/ace_engine/libarkui_dialog.z.so', 'arkui/ace_engine/libarkui_dynamiclayout.z.so', 'arkui/ace_engine/libarkui_folderstack.z.so', 'arkui/ace_engine/libarkui_gauge.z.so', 'arkui/ace_engine/libarkui_hyperlink.z.so', 'arkui/ace_engine/libarkui_imageanimator.z.so', 'arkui/ace_engine/libarkui_indexer.z.so', 'arkui/ace_engine/libarkui_lazycolumnlayout.z.so', 'arkui/ace_engine/libarkui_lazywaterflowlayout.z.so', 'arkui/ace_engine/libarkui_linearsplit.z.so', 'arkui/ace_engine/libarkui_loadingprogress.z.so', 'arkui/ace_engine/libarkui_marquee.z.so', 'arkui/ace_engine/libarkui_menu.z.so', 'arkui/ace_engine/libarkui_navigator.z.so', 'arkui/ace_engine/libarkui_panel.z.so', 'arkui/ace_engine/libarkui_patternlock.z.so', 'arkui/ace_engine/libarkui_progress.z.so', 'arkui/ace_engine/libarkui_qrcode.z.so', 'arkui/ace_engine/libarkui_radio.z.so', 'arkui/ace_engine/libarkui_rating.z.so', 'arkui/ace_engine/libarkui_richeditor.z.so', 'arkui/ace_engine/libarkui_select.z.so', 'arkui/ace_engine/libarkui_sheet.z.so', 'arkui/ace_engine/libarkui_sidebar.z.so', 'arkui/ace_engine/libarkui_slider.z.so', 'arkui/ace_engine/libarkui_span.z.so', 'arkui/ace_engine/libarkui_stepper.z.so', 'arkui/ace_engine/libarkui_symbol.z.so', 'arkui/ace_engine/libarkui_tabswiper.z.so', 'arkui/ace_engine/libarkui_textclock.z.so', 'arkui/ace_engine/libarkui_textfield.z.so', 'arkui/ace_engine/libarkui_textpicker.z.so', 'arkui/ace_engine/libarkui_texttimer.z.so', 'arkui/ace_engine/libarkui_timepicker.z.so', 'arkui/ace_engine/libarkui_toggle.z.so', 'arkui/ace_engine/libarkui_waterflow.z.so', 'arkui/ace_engine/libarkuicustomnode_ani.so', 'arkui/ace_engine/libarkuiuiextension_ani.so', 'arkui/ace_engine/libcj_frontend_ohos.z.so', 'arkui/ace_engine/libcomponentSnapshot_ani.so', 'arkui/ace_engine/libcomponentUtils_ani.so', 'arkui/ace_engine/libcurves_ani.so', 'arkui/ace_engine/libdrawable_descriptor.z.so', 'arkui/ace_engine/libdrawabledescriptor.z.so', 'arkui/ace_engine/libfocusController_ani.so', 'arkui/ace_engine/libimagecache_ani.so', 'arkui/ace_engine/libinspector_ani.so', 'arkui/ace_engine/libmatrix4_ani.so', 'arkui/ace_engine/libmediaquery_ani.so', 'arkui/ace_engine/libobserver_ani.so', 'arkui/ace_engine/liboverlayManager_ani.so', 'arkui/ace_engine/libperformanceMonitor_ani.so', 'arkui/ace_engine/libpluginComponent_ani.so', 'arkui/ace_engine/libpromptAction_ani.so', 'arkui/ace_engine/libprompt_ani.so', 'arkui/ace_engine/libsmartGestureController_ani.so', 'arkui/ace_engine/libsmartlayout.z.so', 'arkui/ace_engine/libsystemprompt_ani.so', 'arkui/ace_engine/libtest_ani.so', 'arkui/ace_engine/libui_sa.z.so', 'arkui/ace_engine/libui_service_mgr.z.so', 'arkui/ace_engine/libui_session.z.so', 'arkui/ace_engine/libuiservice.z.so')
DATA_OBJECTS=('obj/foundation/arkui/ace_engine/adapter/ohos/entrance/pa_engine/engine/jsi/abc_pamgmt_class.o', 'obj/foundation/arkui/ace_engine/frameworks/base/resource/entry.o', 'obj/foundation/arkui/ace_engine/frameworks/base/resource/errorcode.o', 'obj/foundation/arkui/ace_engine/frameworks/base/resource/indexletter_bar.o', 'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/arkCommon.o', 'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/arkDynamicComponent.o', 'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/engine/jsi/abc_ark_common.o', 'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/engine/jsi/abc_ark_dynamiccomponent.o', 'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/engine/jsi/abc_preload.o', 'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/engine/jsi/abc_proxy_class.o', 'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/js_proxy_class.o', 'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/js_proxy_class_ark_breakpoint.o', 'obj/foundation/arkui/ace_engine/frameworks/core/components_ng/pattern/app_bar/interfaces/custom_app_bar_abc.o', 'obj/foundation/arkui/ace_engine/frameworks/core/components_ng/pattern/container_modal/interfaces/customtitle_abc.o')
STATIC_CODE=(
 'obj/commonlibrary/qrcode_generator/libqrcodegen.a',
 'obj/foundation/communication/netmanager_base/interfaces/innerkits/netconnclient/libnet_conn_parcel.a',
 'obj/third_party/bounds_checking_function/libsec_static_ace_cfi.a',
)
# Kept separate from the original83 emitted-boundary history above.
EMITTED_EXAMPLE_DSO='arkui/ace_engine/libui_sa.z.so'
def require(ok,why):
 if not ok:raise ValueError(why)
def safe(root,name):
 p=PurePosixPath(name)
 require(not p.is_absolute() and name not in ('','.') and '..' not in p.parts,'unsafe native path: '+name)
 f=root/name
 for q in (f,*f.parents):
  if q==root:break
  require(not q.is_symlink(),'symlink native input: '+name)
 return f
def descriptor(p):
 b=p.read_bytes();return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def expand(s,values,depth=0):
 require(depth<16,'recursive Ninja variable');s=s.replace('$$','\x00').replace('$:',':')
 def sub(m):
  key=m.group(1) or m.group(2);require(key in values,'unbound Ninja variable: '+key);return expand(values[key],values,depth+1)
 s=re.sub(r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)',sub,s)
 require('$' not in s,'unsupported Ninja escape');return s.replace('\x00','$')
def flags(values,fields):
 return shlex.split(' '.join(expand(values.get(k,''),values) for k in fields))
def effective_cfi(tokens):
 enabled=set();cross=False;lto=False;visibility=None;recover=set()
 kinds={'cfi-vcall','cfi-icall'}
 for t in tokens:
  if t.startswith(('-fsanitize=','-fno-sanitize=')):
   on=t.startswith('-fsanitize=');v=set(t.split('=',1)[1].split(','))
   if 'all' in v or 'cfi' in v:v|=kinds
   if on:enabled|=v
   else:enabled-=v
  elif t=='-fsanitize-cfi-cross-dso':cross=True
  elif t=='-fno-sanitize-cfi-cross-dso':cross=False
  elif t=='-fno-lto':lto=False
  elif t=='-flto' or t.startswith('-flto='):lto=True
  elif t.startswith('-fvisibility='):visibility=t.split('=',1)[1]
  elif t.startswith(('-fsanitize-recover=','-fno-sanitize-recover=')):
   v=set(t.split('=',1)[1].split(','))
   if 'all' in v or 'cfi' in v:v|=kinds
   if t.startswith('-fsanitize-recover='):recover|=v
   else:
    if 'all' in v:recover.clear()
    else:recover-=v
 return dict(vcall='cfi-vcall' in enabled,icall='cfi-icall' in enabled,cross_dso=cross,lto=lto,visibility=visibility,recover_cfi=bool(recover&{'all','cfi','cfi-vcall','cfi-icall'}))
def check_flags(tokens,where,link=False):
 v=effective_cfi(tokens)
 require(all(v[k] for k in ('vcall','icall','cross_dso','lto')),'incomplete effective CFI flags: '+where)
 # The official cross-DSO compile config supplies default type visibility.
 if not link:require(v['visibility']=='default','cross-DSO metadata visibility missing: '+where)
 require(not v['recover_cfi'],'CFI recovery enabled: '+where)
 return v
def linkage(edge):
 """One finite extraction for native checks and cross-product consumer discovery."""
 tokens=flags(edge['values'],('ldflags','libs','solibs'));parts=[x for t in tokens for x in t.split(',')]
 names=set(edge['inputs']);libraries=[];search=[];sysroots=[];modes=[];responses=[];pending=None
 for part in parts:
  if part=='-Wl' or part=='-Xlinker':continue
  if pending:
   kind=pending;pending=None
   if kind=='exclude':
    require(part and '/' not in part and not part.startswith('-'),'malformed --exclude-libs')
   elif kind=='library':libraries.append(part)
   elif kind=='search':search.append(part)
   else:sysroots.append(part)
   continue
  if part=='--exclude-libs':pending='exclude';continue
  if part.startswith('--exclude-libs='):continue
  if part in ('-l','--library'):pending='library';continue
  if part.startswith('-l'):libraries.append(part[2:])
  elif part.startswith('--library='):libraries.append(part.split('=',1)[1])
  elif part in ('-L','--library-path'):pending='search';continue
  elif part.startswith('-L'):search.append(part[2:])
  elif part.startswith('--library-path='):search.append(part.split('=',1)[1])
  elif part=='--sysroot':pending='sysroot';continue
  elif part.startswith('--sysroot='):sysroots.append(part.split('=',1)[1])
  elif part in ('-Bstatic','-static','--static','--whole-archive','--push-state','--pop-state','--start-lib','--end-lib'):modes.append(part)
  if part.startswith('@'):responses.append(part)
  if part.endswith(('.a','.o','.so')):names.add(part)
 require(pending is None,'incomplete linker option argument')
 return dict(names=names,libraries=libraries,search_paths=search,sysroots=sysroots,modes=modes,responses=responses,tokens=tokens)
def check_hidden_inputs(tokens,explicit,compiler_runtime=()):
 # Kept as a small test/public primitive, backed by the exact shared extraction.
 edge=dict(inputs=list(explicit),values=dict(ldflags=shlex.join(tokens)))
 v=linkage(edge)
 require(set(v['libraries'])<=set(('unwind','c++','c','dl','m')),'unknown platform -l library')
 require(not v['modes'] and not v['responses'],'static/whole-archive/response linker mode')
 require(not v['search_paths'],'unexpected linker search path')
 for part in v['names']:
  require(not (part.endswith(('.a','.o')) and part not in explicit and part not in compiler_runtime),'hidden static linker code input: '+part)
 return v
def checked_linkage(edge,compiler_runtime,triple):
 v=linkage(edge)
 require(set(v['libraries'])<=set(('unwind','c++','c','dl','m')),'unknown platform -l library')
 require(not v['modes'] and not v['responses'],'static/whole-archive/response linker mode')
 allowed_search={'obj/third_party/musl/usr/lib/'+triple,'../../prebuilts/clang/ohos/linux-x86_64/llvm/lib/clang/15.0.4/lib/'+triple}
 require(set(v['search_paths'])<=allowed_search and v['sysroots']==['obj/third_party/musl'],'unknown native linker search/sysroot')
 for part in v['names']:
  require(not (part.endswith(('.a','.o')) and part not in edge['inputs'] and part not in compiler_runtime),'hidden static linker code input: '+part)
 return v
def parse_ninja(path,solink_only=False):
 if solink_only:
  possible=path.read_bytes().replace(b'\r\n',b'\n').replace(b'\r',b'\n').replace(b'$\n',b'')
  if not any(b'build ' in line and b'solink' in line for line in possible.split(b'\n')):return []
 raw=path.read_text();lines=raw.replace('$\r\n','').replace('$\n','').splitlines();base={};edges=[];current=None
 for l in lines:
  if not l.strip() or l.startswith('#'):continue
  if l.startswith('build '):
   out,body=l[6:].split(': ',1);parts=body.split();rule=parts[0]
   if solink_only and rule!='solink':
    current=None;continue
   ins=[]
   for x in parts[1:]:
    if x in ('|','||'):break
    ins.append(x)
   require('$' not in out+' '.join(ins),'unsupported escaped native edge')
   current=dict(outputs=out.split(),rule=rule,inputs=ins,values=dict(base),ninja=str(path));edges.append(current)
  elif l[:1].isspace():
   if current is not None and ' = ' in l:
    k,v=l.strip().split(' = ',1);current['values'][k]=v
  elif ' = ' in l:
   k,v=l.split(' = ',1);base[k]=v;current=None
  else:current=None
 return edges
def data_only_elf(path,machine):
 b=path.read_bytes();require(b[:4]==b'\x7fELF' and b[5]==1,'generated data object is not little-endian ELF')
 cls=b[4];require(cls in (1,2),'ELF class')
 require(struct.unpack_from('<H',b,16)[0]==1 and struct.unpack_from('<H',b,18)[0]==machine,'data ELF type/ABI')
 if cls==2:off=struct.unpack_from('<Q',b,40)[0];sz,num=struct.unpack_from('<HH',b,58);fmt='<IIQQQQIIQQ'
 else:off=struct.unpack_from('<I',b,32)[0];sz,num=struct.unpack_from('<HH',b,46);fmt='<IIIIIIIIII'
 require(num and sz==struct.calcsize(fmt) and off+num*sz<=len(b),'data ELF sections')
 for i in range(num):
  s=struct.unpack_from(fmt,b,off+i*sz);kind,attributes,start,size,entsize=s[1],s[2],s[4],s[5],s[9]
  require(not (attributes&4 and size),'generated data object has executable bytes')
  if kind in (2,11):
   unit=24 if cls==2 else 16;require(entsize==unit and size%unit==0 and start+size<=len(b),'data ELF symbols')
   for a in range(start,start+size,unit):
    info=b[a+4] if cls==2 else b[a+12];require((info&15) not in (2,10),'generated data object contains a function')
 return descriptor(path)
def cfi_dso_elf(path,machine):
 b=path.read_bytes();require(len(b)>=52 and b[:4]==b'\x7fELF' and b[5]==1,'DSO is not little-endian ELF')
 cls=b[4];require(cls==(1 if machine==40 else 2),'DSO ELF class/ABI')
 require(struct.unpack_from('<H',b,16)[0]==3 and struct.unpack_from('<H',b,18)[0]==machine,'DSO ET_DYN/ABI')
 if cls==2:
  require(len(b)>=64,'short ELF64 DSO');off=struct.unpack_from('<Q',b,40)[0];sz,num=struct.unpack_from('<HH',b,58);fmt='<IIQQQQIIQQ'
 else:off=struct.unpack_from('<I',b,32)[0];sz,num=struct.unpack_from('<HH',b,46);fmt='<IIIIIIIIII'
 require(num and sz==struct.calcsize(fmt) and off+num*sz<=len(b),'DSO section headers')
 sections=[struct.unpack_from(fmt,b,off+i*sz) for i in range(num)];found=[]
 for section in sections:
  if section[1]!=11:continue
  start,size,link,unit=section[4],section[5],section[6],section[9];need=24 if cls==2 else 16
  require(unit==need and size%unit==0 and start+size<=len(b) and link<num,'DSO dynsym table')
  strings=sections[link];require(strings[1]==3 and strings[4]+strings[5]<=len(b),'DSO dynsym string table');st=b[strings[4]:strings[4]+strings[5]]
  for i in range(start,start+size,unit):
   if cls==2:name,info,other,index,value,length=struct.unpack_from('<IBBHQQ',b,i)
   else:name,value,length,info,other,index=struct.unpack_from('<IIIBBH',b,i)
   require(name<len(st),'DSO dynsym name offset');end=st.find(b'\0',name);require(end>=0,'unterminated DSO dynsym name')
   if st[name:end]!=b'__cfi_check':continue
   require(index!=0 and (info>>4) in (1,2) and (info&15) in (2,10) and (other&3) in (0,3),'__cfi_check not a defined exported function')
   require(index<num and sections[index][2]&4 and sections[index][3]<=value<sections[index][3]+sections[index][5],'__cfi_check outside an executable section')
   found.append(dict(name='__cfi_check',value=value,section=index,binding=info>>4,visibility=other&3))
 require(len(found)==1,'missing/duplicate exported __cfi_check')
 return dict(artifact=descriptor(path),machine=machine,elf_class=cls,exported_cfi_check=found[0],CFI_type_membership_verified=False)
def ar_members(path):
 b=path.read_bytes();require(b.startswith(b'!<arch>\n'),'archive magic');i=8;longnames=b'';members={}
 while i<len(b):
  require(i+60<=len(b) and b[i+58:i+60]==b'`\n','archive header');h=b[i:i+60];i+=60
  try:size=int(h[48:58].strip())
  except ValueError:raise ValueError('archive member length')
  require(size>=0 and i+size<=len(b),'truncated archive member');payload=b[i:i+size];i+=size+(size%2);name=h[:16].decode('ascii').strip()
  if name=='//':longnames=payload;continue
  if name in ('/','/SYM64/'):continue
  if name.startswith('#1/'):
   n=int(name[3:]);require(n<=len(payload),'archive BSD name');name=payload[:n].rstrip(b'\0').decode();payload=payload[n:]
  elif name.startswith('/'):
   n=int(name[1:]);require(n<len(longnames),'archive long name');name=longnames[n:].split(b'/\n',1)[0].decode()
  else:name=name.rstrip('/')
  require(name and '/' not in name and name not in members,'duplicate/unsafe archive member');members[name]=payload
 require(i==len(b),'archive trailing bytes');return members

def scan_archive_consumers(out):
 allowed_consumers={
  STATIC_CODE[0]:{'arkui/ace_engine/libace_compatible.z.so','arkui/ace_engine/libace_compatible_components.z.so','arkui/ace_engine/libarkui_qrcode.z.so'},
  STATIC_CODE[2]:{'arkui/ace_engine/libsmartlayout.z.so'},
 }
 consumers={x:set() for x in allowed_consumers}
 for file in out.rglob('*.ninja'):
  require(not file.is_symlink(),'global Ninja symlink')
  text=file.read_bytes()
  if not any(x.encode('utf-8') in text for x in allowed_consumers):continue
  for edge in parse_ninja(file,solink_only=True):
   if edge['rule']!='solink':continue
   for archive,allowed in allowed_consumers.items():
    if archive in linkage(edge)['names']:
     actual=edge['outputs'][0];require(actual in allowed,'unreviewed CFI archive consumer: '+actual);consumers[archive].add(actual)
 for archive,allowed in allowed_consumers.items():require(consumers[archive]==allowed,'missing fixed CFI archive consumers: '+archive)
 return consumers

def product_example_selection(out,arch,nodes,selected):
 """Separate actual product membership from mere emitted common-config edges."""
 metadata=safe(out,'packages/phone/system_module_info.json')
 require(metadata.is_file(),'missing complete product module installation metadata')
 rows=json.loads(metadata.read_text())
 require(type(rows) is list and rows,'complete product module installation list')
 installed={};library_type='lib' if arch=='arm' else 'lib64'
 for row in rows:
  require(type(row) is dict and {'source','dest','type','install_enable'}<=set(row) and
          type(row['source']) is str and row['source'] and type(row['dest']) is list and
          all(type(x) is str and x for x in row['dest']) and type(row['type']) is str and
          type(row['install_enable']) is bool,'malformed product module metadata')
  if not row['install_enable'] or not row['source'].endswith('.so'):continue
  source=PurePosixPath(row['source'])
  require(not source.is_absolute() and '..' not in source.parts and str(source)!='.' and
          row['dest'],'unsafe or empty selected product module')
  installed.setdefault(str(source),[]).append(row)
 floor=set(REQUIRED_DSOS)-{EMITTED_EXAMPLE_DSO}
 require(floor<=set(installed),'missing fixed ACE product installation members')
 for name in floor:
  require(all(row['type']==library_type for row in installed[name]),
          'fixed ACE product installation ABI kind: '+name)
 # Read every native solink; metadata restricts consumer identity, never flags.
 consumers=[];inventory={};product_links=set()
 for file in sorted(out.rglob('*.ninja')):
  require(not file.is_symlink(),'global product Ninja symlink')
  inventory[str(file.relative_to(out))]=descriptor(file)
  for edge in parse_ninja(file,solink_only=True):
   outputs={str(PurePosixPath(name)) for name in edge['outputs']}
   product_outputs=outputs&set(installed)
   if not product_outputs:continue
   product_links.update(product_outputs)
   inputs=linkage(edge)
   named=any(PurePosixPath(name).name=='libui_sa.z.so' for name in inputs['names'])
   library=any(name in ('ui_sa','ui_sa.z') or
               PurePosixPath(name.lstrip(':')).name=='libui_sa.z.so'
               for name in inputs['libraries'])
   if named or library:
    consumers.append(dict(outputs=sorted(product_outputs),ninja=descriptor(file),
        explicit_and_linker_names=sorted(inputs['names']),libraries=inputs['libraries']))
 require(floor<=product_links,'fixed product ACE solink missing from actual global graph')
 member=EMITTED_EXAMPLE_DSO in installed
 required=member or bool(consumers)
 if required:
  require(EMITTED_EXAMPLE_DSO in nodes and nodes[EMITTED_EXAMPLE_DSO]['rule']=='solink',
          'selected product example has no native solink')
  selected[EMITTED_EXAMPLE_DSO]=nodes[EMITTED_EXAMPLE_DSO]
 else:
  # The only finite exception: never infer scope from artifact existence.
  selected.pop(EMITTED_EXAMPLE_DSO,None)
 return dict(product_module_metadata=descriptor(metadata),module_count=len(rows),
     fixed_product_floor=sorted(floor),selected_common_dsos=sorted(selected),
     example=dict(output=EMITTED_EXAMPLE_DSO,product_member=member,
         product_link_consumers=consumers,native_CFI_required=required,
         classification='product-selected' if required else 'emitted-unselected',
         reason='actual installation membership or product link dependency' if required else
                'absent from complete actual installation metadata and every product native solink'),
     product_solink_outputs=sorted(product_links),global_ninja_inventory=inventory,
     runtime_passed=False,first_artifact_behavior_gate_passed=False)

def verify(out,arch):
 out=Path(out).resolve();machine={'arm64':183,'arm':40,'x86_64':62}[arch]
 nodes={};all_edges=[];seen={}
 paths=list(safe(out,ACE).rglob('*.ninja'))
 # These are the only nonempty local archives in the sealed selected closure.
 for archive in STATIC_CODE:
  paths+=list(safe(out,str(PurePosixPath(archive).parent)).glob('*.ninja'))
 for p in sorted(set(paths)):
  require(not p.is_symlink(),'Ninja symlink');seen[str(p.relative_to(out))]=descriptor(p)
  for e in parse_ninja(p):
   all_edges.append(e)
   for name in e['outputs']:
    require(name not in nodes,'duplicate native output: '+name);nodes[name]=e
 selected={};dso_evidence={}
 for name in REQUIRED_DSOS:
  if name==EMITTED_EXAMPLE_DSO:continue
  require(name in nodes and nodes[name]['rule']=='solink','missing required ACE DSO: '+name);selected[name]=nodes[name]
 common={name for name,e in nodes.items() if e['rule'] in ('cxx','cc') and '-DUNITEST_FRIEND_CLASS=' in flags(e['values'],('cflags',))}
 # Newly emitted DSO boundaries with the same real common-config inputs are checked too.
 for e in all_edges:
  if e['rule']=='solink' and common.intersection(e['inputs']):selected[e['outputs'][0]]=e
 product_selection=product_example_selection(out,arch,nodes,selected)
 triple={'arm64':'aarch64-linux-ohos','arm':'arm-linux-ohos','x86_64':'x86_64-linux-ohos'}[arch]
 compiler_base='../../prebuilts/clang/ohos/linux-x86_64/llvm/lib/'
 runtime_allowed=(compiler_base+'clang/15.0.4/lib/'+triple+'/libclang_rt.builtins.a',compiler_base+'clang/15.0.4/lib/'+triple+'/libclang_rt.gwp_asan.a',compiler_base+triple+'/libc++abi.a')
 compiler_runtime=set();checked={};archives={};data={}
 def code(name):
  if name in checked:return
  require(name in nodes and nodes[name]['rule'] in ('cxx','cc'),'unbound local code object: '+name)
  e=nodes[name];fields=('cflags','cflags_cc') if e['rule']=='cxx' else ('cflags','cflags_c')
  tokens=flags(e['values'],fields);v=check_flags(tokens,name)
  p=safe(out,name);require(p.is_file(),'missing compiled object: '+name)
  checked[name]=dict(object=descriptor(p),source=e['inputs'],effective=v,ninja=e['ninja'])
 def archive(name):
  if name in archives:return
  p=safe(out,name);members=ar_members(p)
  if not members:
   require(p.stat().st_size==8,'noncanonical empty archive');archives[name]=dict(artifact=descriptor(p),members=[]);return
  require(name in STATIC_CODE and name in nodes and nodes[name]['rule']=='alink','unadmitted nonempty archive: '+name)
  e=nodes[name];objects=[x for x in e['inputs'] if x.endswith('.o')]
  require(len(objects)==len(e['inputs']) and len({PurePosixPath(x).name for x in objects})==len(objects),'archive input shape')
  require(set(members)=={PurePosixPath(x).name for x in objects},'actual archive member set differs from native graph')
  for x in objects:
   code(x);require(members[PurePosixPath(x).name]==safe(out,x).read_bytes(),'archive member differs from real object bytes')
  archives[name]=dict(artifact=descriptor(p),members=objects)
 for name,e in selected.items():
  check_flags(flags(e['values'],('ldflags',)),name,True)
  explicit=set(e['inputs'])
  linked=checked_linkage(e,runtime_allowed,triple)
  for runtime in runtime_allowed:
   if runtime in linked['names']:compiler_runtime.add(runtime)
  for x in e['inputs']:
   if x.endswith('.o'):
    if x in nodes and nodes[x]['rule'] in ('cxx','cc'):code(x)
    else:
     require(x in DATA_OBJECTS,'unbound generated object: '+x)
     data[x]=data_only_elf(safe(out,x),machine)
   elif x.endswith('.a'):archive(x)
   elif not x.endswith('.so'):raise ValueError('unknown explicit linker input: '+x)
  require(safe(out,name).is_file(),'missing linked DSO: '+name)
  dso_evidence[name]=cfi_dso_elf(safe(out,name),machine)
 scan_archive_consumers(out)
 runtime_evidence={name:descriptor(out/name) for name in sorted(compiler_runtime)}
 return dict(scope='actual native CFI flag and local link-input coverage ONLY',arch=arch,dsos={n:dso_evidence[n] for n in sorted(selected)},compiled_inputs=checked,archives=archives,compiler_runtime_inputs_under_existing_platform_policy=runtime_evidence,data_objects=data,ninja_files=seen,product_selection=product_selection,actual_artifacts_checked=True,native_compile_execution_independently_proven=False,runtime_passed=False,first_artifact_behavior_gate_passed=False)
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--arch',choices=('arm64','arm','x86_64'),required=True);p.add_argument('--output',type=Path);a=p.parse_args(argv)
 d=verify(a.out,a.arch);s=json.dumps(d,indent=2)+'\n'
 if a.output:a.output.write_text(s)
 else:print(s,end='')
 return 0
if __name__=='__main__':raise SystemExit(main())
