"""Fixed final-actor extension proposal. Never execute on bare Root host."""
from pathlib import Path
import json
from photos579_raw import ref,need,document
from photos579_registration import registration_candidate,LEDGER


def collect(packet, output, actor):
    output=Path(output);output.mkdir(exist_ok=False)
    result=registration_candidate(original_ledger=ref(LEDGER),archive=packet['archive'],
        main_boot=packet['main_boot'],main_suite=packet['main_suite'],actor=actor,output=output/'raw')
    path=output/'photos579-registration.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    raw=result['raw_replay']
    failures=[] if raw is None else list(raw['retained_failures'])+list(raw['replay_errors'])
    need(result['registrations']=={},'this source retains the precise cloud/account unresolved obligation')
    return dict(registrations={},failures=failures,proof=ref(path),
        profile_disposition=result['profile_disposition'],
        supported_local_complete=result.get('supported_local_complete'),
        unresolved_subscopes=result.get('unresolved_subscopes',[]))
