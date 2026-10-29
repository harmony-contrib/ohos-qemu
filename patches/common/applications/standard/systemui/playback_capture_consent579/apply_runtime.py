#!/usr/bin/env python3
"""Exact12-file SystemUI source transaction, legacy migration and prefix rewind.

transact retains the original guarded_source_vector579.apply body with only
its neutral-member publication skip. Staging, exact patch/fuzz0, inode checks,
owned rollback, directory ownership and final full-vector verification remain.
No source/compile/runtime acceptance is inferred.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import subprocess

HERE=Path(__file__).resolve().parent
PATCHES=next(p for p in HERE.parents if p.name=='patches')
sys.path.insert(0,str(PATCHES/'lib'))
import guarded_source_vector579 as base
from guarded_source_vector579 import sha,target,identity,matches,replace,heads

PROJECT='applications/standard/systemui'
REVISION='d0f84037f1975dd9bf13ccbd279bd2d9b56e8a01'
LEGACY_MANIFEST_SHA='4d36415c30d4cfef580835cbb84502ebf51ca48ce36de571ab8fed654cf47187'
LOG_PATH=PROJECT+'/common/src/main/ets/default/Log.ts'
LOG_SHA='5a6ad08fe269488a91b334656db18d9831b719e775dd017939a22572a67f17a1'
PREFIX=PROJECT+'/product/default/dialog/'
MODULE=PREFIX+'src/main/module.json5'
PREVIOUS_MODULE_SHA='adf36413d8e5f0cdfa037ffc731be2edd5595f3a70de9820b4fff64965d54d49'
MEMBERS=(
 'src/main/ets/Application/AbilityStage.ts',
 'src/main/ets/ServiceExtAbility/ExtAbility.ts',
 'src/main/ets/ServiceExtAbility/PlaybackCaptureConsentExtension.ets',
 'src/main/ets/common/Log.ts',
 'src/main/ets/common/PlaybackCaptureConsent.ets',
 'src/main/ets/controller/Controller.ts',
 'src/main/ets/pages/ExtIndex.ets',
 'src/main/ets/pages/PlaybackCaptureConsentPage.ets',
 'src/main/module.json5',
 'src/main/resources/base/element/string.json',
 'src/main/resources/base/profile/main_pages.json',
 'src/main/resources/zh_CN/element/string.json')


def load():
    value=base.load(HERE)
    if value['projects']!={PROJECT:REVISION} or set(value['files'])!={PREFIX+name for name in MEMBERS}:
        raise ValueError('Only the complete fixed SystemUI12 source vector is accepted')
    raw=(HERE/'legacy_source_states.json').read_bytes()
    if sha(raw)!=LEGACY_MANIFEST_SHA:
        raise ValueError('Immutable complete legacy8 manifest changed')
    legacy=json.loads(raw)
    expected={name:pair[1] for name,pair in legacy['files'].items()}
    for name,pair in value['files'].items():
        if name not in expected: expected[name]=pair[0]
    if len(legacy['files'])!=8 or legacy['projects']!=value['projects'] or value.get('legacy_final')!=expected:
        raise ValueError('Complete actual legacy final, never per-file mixing, is required')
    if value.get('readonly')!={LOG_PATH:LOG_SHA}:
        raise ValueError('Only the exact official original logger may be copied')
    return value


def hashes(value, state):
    if state=='legacy_final': return value['legacy_final']
    if state=='previous_final':
        return dict(hashes(value,'final'), **{MODULE:PREVIOUS_MODULE_SHA})
    if state not in ('before','final'): raise ValueError('Unknown source state')
    return {name:pair[0 if state=='before' else 1] for name,pair in value['files'].items()}


def actual_hashes(root, value):
    return {name:sha(target(root,name).read_bytes()) if target(root,name).exists() else None
        for name in value['files']}


def complete(root, value):
    heads(root,value)
    logger=target(root,LOG_PATH)
    if not logger.is_file() or sha(logger.read_bytes())!=LOG_SHA:
        raise ValueError('Original actual SystemUI logger changed')
    observed=actual_hashes(root,value)
    for state in ('before','legacy_final','previous_final','final'):
        if observed==hashes(value,state):return state
    raise ValueError('Unknown or mixed SystemUI source vector preserved')


def vector(root,value):
    # A migration guards all12 members. Four neutral members are still checked
    # byte for byte but do not contribute an artificial before/after vote.
    observed=actual_hashes(root,value)
    votes=[]
    for name,pair in value['files'].items():
        digest=observed[name]
        if digest not in pair:raise ValueError('Unknown source bytes preserved: '+name)
        if pair[0]!=pair[1]:votes.append(pair.index(digest))
    if not votes or len(set(votes))!=1:raise ValueError('Mixed migration source vector preserved')
    return 'before' if votes[0]==0 else 'final'


def transact(root, component, value, *, reverse=False, patch_name='0001-product-source.patch', patch_steps=None):
    heads(root, value)
    if vector(root, value) == 'final':
        return
    originals = {}
    for name in value['files']:
        p = target(root, name)
        originals[name] = {'bytes': p.read_bytes(), 'identity': identity(p)} if p.exists() else None
    with tempfile.TemporaryDirectory(prefix='qemu-vector579-') as temporary:
        staged = Path(temporary)
        for name, original in originals.items():
            if original is not None:
                p = staged / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(original['bytes'])
        if vector(staged, value) != 'before':
            raise ValueError('actual preimage changed during snapshot')
        for name, backwards in (patch_steps if patch_steps is not None else [(patch_name, reverse)]):
            subprocess.run(['patch', '--binary', '--batch', '--reverse' if backwards else '--forward', '--fuzz=0', '-p1', '-i',
                str(component / name)], cwd=staged, check=True)
        if vector(staged, value) != 'final' or {
                str(p.relative_to(staged)) for p in staged.rglob('*') if p.is_file()} != {
                    n for n, pair in value['files'].items() if pair[1] is not None}:
            raise ValueError('finite complete final source vector required')
        finals = {n: (staged / n).read_bytes() if pair[1] is not None else None
                  for n, pair in value['files'].items()}
    heads(root, value)
    if vector(root, value) != 'before':
        raise ValueError('actual source changed before commit')
    installed, directories = {}, []
    try:
        for name, original in originals.items():
            p = target(root, name)
            if not matches(p, original):
                raise ValueError('actual source inode changed before replacement: ' + name)
            # Neutral members remain in the complete transaction guard but
            # keep their actual inode and mtime, including absent/absent files.
            if ((original is None and finals[name] is None) or
                    (original is not None and finals[name] == original['bytes'])):
                continue
            if finals[name] is None:
                installed[name] = None
                p.unlink()
                continue
            missing = []
            parent = p.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                s = directory.stat(follow_symlinks=False)
                directories.append((directory, (s.st_dev, s.st_ino)))
            replace(p, finals[name], original['identity'] if original else None, installed, name)
        if vector(root, value) != 'final':
            raise ValueError('final actual source vector differs')
    except BaseException as error:
        failures = []
        for name, original in reversed(list(originals.items())):
            try:
                p = target(root, name)
                if matches(p, original):
                    continue
                if name not in installed:
                    raise ValueError('unknown concurrent source preserved')
                if installed[name] is None:
                    if p.exists():
                        raise ValueError('concurrent source appeared after owned removal')
                elif (not p.exists() or identity(p) != installed[name] or
                        sha(p.read_bytes()) != value['files'][name][1]):
                    raise ValueError('unknown concurrent source preserved')
                if original is None:
                    p.unlink()
                else:
                    replace(p, original['bytes'], original['identity'], {}, name)
            except BaseException as rollback_error:
                failures.append(name + ': ' + str(rollback_error))
        for directory, inode in reversed(directories):
            try:
                s = directory.stat(follow_symlinks=False)
                if not stat.S_ISDIR(s.st_mode) or (s.st_dev, s.st_ino) != inode:
                    raise ValueError('created source directory changed: ' + str(directory))
                directory.rmdir()
            except (OSError, ValueError):
                failures.append('created source directory not empty: ' + str(directory))
        if failures:
            raise RuntimeError('source rollback incomplete: ' + '; '.join(failures)) from error
        if vector(root, value) != 'before':
            raise RuntimeError('source rollback did not restore complete preimage') from error
        raise



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--rewind',action='store_true')
    mode.add_argument('--require-final',action='store_true')
    args=parser.parse_args()
    root=args.source_root.resolve();value=load()
    marker=root/'.ohos-qemu-patches'
    if marker.is_symlink():raise ValueError('Source lock directory is linked')
    marker.mkdir(exist_ok=True)
    # Identical lock path to the original helper at this canonical component.
    fd=os.open(marker/(sha(str(HERE).encode())+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        initial=complete(root,value)
        if args.require_final:
            if initial!='final':raise ValueError('Complete repaired SystemUI final vector required')
        elif args.rewind:
            if initial!='before':
                start=hashes(value,initial);end=hashes(value,'before')
                selected=dict(value,files={name:[start[name],end[name]] for name in value['files']})
                patch='0000-legacy-product-source.patch' if initial=='legacy_final' else '0001-product-source.patch'
                steps=([('0003-upgrade-float-window.patch',False),(patch,True)]
                    if initial=='previous_final' else None)
                transact(root,HERE,selected,reverse=True,patch_name=patch,patch_steps=steps)
                if complete(root,value)!='before':raise ValueError('Complete original prefix not restored')
        elif initial!='final':
            start=hashes(value,initial);end=hashes(value,'final')
            selected=dict(value,files={name:[start[name],end[name]] for name in value['files']})
            patch='0002-upgrade-legacy-arkts.patch' if initial=='legacy_final' else '0001-product-source.patch'
            if initial=='previous_final':patch='0003-upgrade-float-window.patch'
            transact(root,HERE,selected,patch_name=patch)
            if complete(root,value)!='final':raise ValueError('Complete new SystemUI final vector not established')
    print('Product source transaction complete; actual build/new-QEMU acceptance remains pending')


if __name__=='__main__':
    main()
