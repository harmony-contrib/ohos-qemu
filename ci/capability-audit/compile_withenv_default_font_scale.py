#!/usr/bin/env python3
"""Compile complete JSView in both dynamic frontends with all real product commands."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT=ROOT/'patches/common/foundation/arkui/ace_engine/withenv_default_font_scale'
SOURCE=Path('foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/jsview/js_view.cpp')
PREFIX='obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/jsview/'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--product',choices=PRODUCTS,action='append')
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():raise ValueError('fresh complete two-frontend compile proof required')
    records=[]
    for frontend in ('ark','ng_ark'):
        per_tu=SimpleNamespace(source_root=args.source_root,output=args.output.with_name(args.output.stem+'-'+frontend+'.json'),product=args.product)
        result=run(per_tu,component=COMPONENT,source_file=SOURCE,
            target=PREFIX+'declarative_js_engine_'+frontend+'_ohos/js_view.o',caller=__file__)
        per_tu.output.write_text(json.dumps(result,indent=2)+'\n');records.append(result)
    report=dict(status='pass',scope='six_full_JSView_objects_both_dynamic_frontends_NOT_link_runtime_or_first_gate',
        first_artifact_behavior_gate_passed=False,records=records,objects_count=sum(row['objects_count'] for row in records))
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],objects_count=report['objects_count'])))
