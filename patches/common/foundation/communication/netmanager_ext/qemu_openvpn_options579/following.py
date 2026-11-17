"""Strict complete-final vector projection for the two original broker guards.

No source mutation, dynamic feature admission or metadata substitution. Old
pristine/prefix states still flow through their original exact source guards.
"""
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from guarded_source_vector579 import load,heads,vector,target

HERE=Path(__file__).resolve().parent

def advance(root,project,revision,files):
    value=load(HERE)
    if value['projects'].get(project)!=revision or len(value['files'])!=7:
        raise ValueError('fixed original projects/complete seven-source options vector')
    # Seeing any one new final identity commits this guard to validating the
    # COMPLETE vector. A mixed/unknown final can never fall back to an ancestor.
    observed={name:hashlib.sha256(target(root,name).read_bytes()).hexdigest() for name in value['files']}
    if not any(observed[name]==pair[1] for name,pair in value['files'].items()):return files
    heads(root,value)
    if vector(root,value)!='final':raise ValueError('complete new final broker/options source vector required')
    expected=[]
    for name,old,final in files:
        pair=value['files'].get(project+'/'+name)
        if pair:
            if pair[0]!=final:raise ValueError('exact RO13 ancestor broker identity differs')
            final=pair[1]
        expected.append((name,old,final))
    return tuple(expected)
