#!/usr/bin/env python3
"""Install the complete fixed caption project during ordinary source preparation."""
import argparse,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
PATCHES=next(p for p in HERE.parents if p.name=='patches')
sys.path.insert(0,str(PATCHES/'lib'))
from guarded_source_vector579 import apply
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args()
    source=json.loads((HERE/'source_states.json').read_text())
    value={'projects':{source['parent_project']:source['parent_head']},
        'files':{source['project']+'/'+p:[None,h] for p,h in source['files'].items()}}
    if len(value['files'])!=23: raise ValueError('complete fixed production source required')
    apply(args.source_root.resolve(),HERE,value)
