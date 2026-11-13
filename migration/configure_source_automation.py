#!/usr/bin/env python3
"""Keep component mirrors from executing inherited upstream GitHub workflows."""
import argparse
import concurrent.futures
import datetime
import json
from pathlib import Path
import subprocess
import threading
import time

blocked = threading.Event()
write_lock = threading.Lock()
next_write = 0.0


def gh(*arguments, mutation=False):
    global next_write
    for attempt in range(3):
        if blocked.is_set():
            raise RuntimeError('Stopped after GitHub rate limiting')
        if mutation:
            with write_lock:
                delay = max(0, next_write - time.monotonic())
                next_write = max(next_write, time.monotonic()) + 0.6
            time.sleep(delay)
        result = subprocess.run(['gh', *arguments], capture_output=True, text=True, timeout=120)
        if not result.returncode:
            return json.loads(result.stdout) if result.stdout.strip() else None
        diagnostic = result.stderr + result.stdout
        if any(term in diagnostic.lower() for term in ('rate limit', 'abuse detection')):
            blocked.set()
            raise RuntimeError(diagnostic[-1200:])
        transient = any(term in diagnostic.lower() for term in (
            'timeout', 'timed out', 'eof', 'connection reset', 'http 500', 'http 502', 'http 503'))
        if not transient or attempt == 2:
            raise RuntimeError(diagnostic[-1200:])
        time.sleep(2 * (attempt + 1))


def migration_triggered(run, actor):
    who = run['actor']['login']
    event = run['event']
    if who == 'openharmony-qemu-mirror-sync[bot]' and event in ('push', 'workflow_run', 'schedule'):
        return True
    if who == 'dependabot[bot]' and event in ('push', 'pull_request', 'pull_request_target'):
        return True
    return (who == actor and event == 'push'
            and run['head_branch'] in ('OpenHarmony-7.0-Release-qemu', 'upstream/baseline-7.0'))


def configure(name, actor):
    record = dict(name=name, status='failed', cancellation_requested=[], retained_runs=[])
    try:
        endpoint = 'repos/openharmony-qemu/' + name
        gh('api', '--method', 'PUT', endpoint + '/actions/permissions', '-F', 'enabled=false', mutation=True)
        policy = gh('api', endpoint + '/actions/permissions')
        if policy['enabled'] is not False:
            raise ValueError('Component GitHub Actions is still enabled')
        record['verified_actions_enabled'] = False
        pages = gh('api', '--paginate', '--slurp', endpoint + '/actions/runs?per_page=100')
        for run in (run for page in pages for run in page['workflow_runs']):
            if run['status'] == 'completed':
                continue
            if not migration_triggered(run, actor):
                record['retained_runs'].append(dict(id=run['id'], event=run['event'],
                    actor=run['actor']['login'], branch=run['head_branch']))
                continue
            try:
                gh('api', '--method', 'POST', endpoint + '/actions/runs/' + str(run['id']) + '/cancel',
                   mutation=True)
            except RuntimeError:
                current = gh('api', endpoint + '/actions/runs/' + str(run['id']))
                if current['status'] != 'completed':
                    raise
            record['cancellation_requested'].append(run['id'])
        record.update(status='disabled', audited_native_runs=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record['error'] = str(error)
    record['checked_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--migration-actor', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    projects = json.loads(args.catalog.read_text())['repositories']
    if not args.apply:
        print(json.dumps([project['name'] for project in projects], indent=2))
        return
    previous = ({row['name']: row for row in map(json.loads, args.journal.read_text().splitlines())}
                if args.journal.exists() else {})
    priority = {'chromium_fast_float': -2, 'chromium_third_party_angle_glmark2': -1}
    projects = sorted(projects, key=lambda row: priority.get(row['name'], 0 if row.get('auto_sync') else 1))
    selected = [row['name'] for row in projects if not (
        previous.get(row['name'], {}).get('status') == 'disabled'
        and previous[row['name']].get('audited_native_runs'))]
    args.journal.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(configure, name, args.migration_actor): name for name in selected}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            with args.journal.open('a') as stream:
                stream.write(json.dumps(result, sort_keys=True) + '\n')
            print(result['name'] + ': ' + result['status'] + '; canceled ' +
                  str(len(result['cancellation_requested'])) + '; retained ' +
                  str(len(result['retained_runs'])), flush=True)
            failed |= result['status'] != 'disabled'
            if blocked.is_set():
                for pending in futures:
                    pending.cancel()
                raise SystemExit('GitHub requested rate-limit backoff; progress is preserved in the journal')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
