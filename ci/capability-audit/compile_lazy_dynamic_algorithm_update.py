#!/usr/bin/env python3
"""Compile both complete LazyDynamicLayout repair TUs with each real product command."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT=ROOT/'patches/common/foundation/arkui/ace_engine/lazy_dynamic_algorithm_update'
PREFIX='foundation/arkui/ace_engine/frameworks/core/components_ng/pattern/dynamiclayout/'
TARGET='obj/foundation/arkui/ace_engine/frameworks/core/components_ng/pattern/dynamiclayout/ace_core_components_dynamiclayout_pattern_ng_ohos/'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--product',choices=PRODUCTS,action='append')
    args=parser.parse_args()
    output=args.output
    if output.exists() or output.is_symlink():raise ValueError('fresh complete lazy compile proof path required')
    records=[]
    for stem in ('lazy_dynamic_layout_model_ng','lazy_dynamic_layout_pattern'):
        per_tu=SimpleNamespace(source_root=args.source_root,output=output.with_name(output.stem+'-'+stem+'.json'),product=args.product)
        result=run(per_tu,component=COMPONENT,source_file=Path(PREFIX+stem+'.cpp'),target=TARGET+stem+'.o',caller=__file__)
        per_tu.output.write_text(json.dumps(result,indent=2)+'\n');records.append(result)
    report=dict(status='pass',scope='six_real_complete_lazy_dynamic_TU_objects_NOT_link_runtime_or_first_gate',
        first_artifact_behavior_gate_passed=False,records=records,objects_count=sum(row['objects_count'] for row in records))
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],objects_count=report['objects_count'])))
