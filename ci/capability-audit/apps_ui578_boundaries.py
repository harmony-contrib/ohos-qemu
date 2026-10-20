"""Actual account/default-display semantics; no resource or test entry point.

Root callbacks perform the original public-API/QMP mechanics. These functions
independently require raw caller results and actual frames, not callback pass
booleans. Missing account/default-mode capability remains a failed pending boundary.
"""
from apps_ui578_contract import decode, require, returned
from verify_screen_blink_results import verify_background_restored, verify_frames


def accounts(value):
    require(isinstance(value,dict) and set(value)=={'foreground','accounts'} and
        type(value['foreground']) is int and isinstance(value['accounts'],list),'actual account getter shape differs')
    out={}
    for item in value['accounts']:
        require(isinstance(item,dict) and type(item.get('localId')) is int and
            isinstance(item.get('localName'),str) and item['localId'] not in out,'actual account identity differs')
        out[item['localId']]=item['localName']
    return value['foreground'],out


def request(rows, op, action, number):
    actual=[r for r in rows if r['operation']==op and r['event']=='call.'+action]
    require(len(actual)==1 and decode(actual[0]['value'])==number,
            'actual public account API argument differs from nonce-owned ID')
    returned(rows,op,action)


def account(boundary,value,rows):
    require(isinstance(boundary,dict) and set(boundary)=={'kind','new_account_baseline','after_switch',
        'switch_observed','after_return','reacquired'} and boundary['kind']=='nonce-account-switch/v1',
        'actual account boundary input is absent; source plan cannot close full blink')
    actor=rows['account'];run=value['run']
    original,before=accounts(returned(actor,'acct.before','account-read'))
    require(original==100 and 'apps578-'+run not in before.values(),'fresh original account/nonce ownership differs')
    created=returned(actor,'acct.create','account-create')
    require(set(created)=={'original','id','name'} and created['original']==original and
        type(created['id']) is int and created['id'] not in before and created['id'] not in (0,100) and
        created['name']=='apps578-'+run,'actual newly-created account is not solely owned by this nonce')
    new_id=created['id']
    _,during=accounts(returned(actor,'acct.created','account-read'))
    require(during==before|{new_id:'apps578-'+run}, 'account creation changed an unrelated original account')
    request(actor,'acct.baseline-away','account-switch',new_id)
    away,_=accounts(returned(actor,'acct.baseline-read','account-read'))
    require(away==new_id,'baseline was not taken in the actual new foreground account')
    request(actor,'acct.baseline-back','account-switch',original)
    require(returned(rows['a'],'acct.active','start')==0,'real pulse was not active before the actual account switch')
    request(actor,'acct.away','account-switch',new_id)
    away,away_ids=accounts(returned(actor,'acct.away-read','account-read'))
    require(away==new_id and away_ids==during,'actual switch did not reach exactly the nonce-owned account')
    verify_background_restored(boundary['new_account_baseline'],boundary['after_switch'],boundary['switch_observed'])
    request(actor,'acct.back','account-switch',original)
    back,back_ids=accounts(returned(actor,'acct.back-read','account-read'))
    require(back==original and back_ids==during,'actual original account was not restored')
    require(boundary['after_return'] in value['pixels'] and boundary['reacquired'] in value['pixels'],
            'account framebuffer phases must use the original node-bound capture pipeline')
    verify_frames(boundary['after_return']['frames'],boundary['after_return']['rect'],'off')
    require(returned(rows['a'],'acct.reacquire','start')==0,'account switch left stale blink ownership')
    verify_frames(boundary['reacquired']['frames'],boundary['reacquired']['rect'],'continuous')
    require(returned(rows['a'],'acct.stop','stop')==0,'account test active pulse did not stop')
    request(actor,'acct.remove','account-remove',new_id)
    last,after=accounts(returned(actor,'acct.after','account-read'))
    require(last==original and after==before,'nonce account removal/original account inventory restoration failed')


def screen_inventory(inventory, default):
    require(isinstance(inventory,dict) and set(inventory)=={'defaultDisplay','screens'} and
        inventory['defaultDisplay']==default and isinstance(inventory['screens'],list) and
        1<=len(inventory['screens'])<=32,'actual bounded public screen inventory/default binding missing')
    ids=set()
    for item in inventory['screens']:
        require(isinstance(item,dict) and set(item)=={'id','sourceMode','activeModeIndex','modes'} and
            all(type(item[k]) is int for k in ('id','sourceMode','activeModeIndex')) and item['id'] not in ids and
            isinstance(item['modes'],list) and 1<=len(item['modes'])<=256, 'actual screen identity/mode inventory differs')
        ids.add(item['id']);mode_ids=set()
        for mode in item['modes']:
            require(isinstance(mode,dict) and set(mode)=={'id','width','height','refreshRate'} and
                all(type(x) is int for x in mode.values()) and mode['id']>=0 and mode['id'] not in mode_ids and
                mode['width']>=100 and mode['height']>=100 and mode['refreshRate']>0,
                'actual unique advertised screen mode required')
            mode_ids.add(mode['id'])
        require(item['activeModeIndex'] in mode_ids,'actual active mode is not advertised')
    matches=[s for s in inventory['screens'] if s['id']==default['id'] and s['sourceMode']==0]
    require(len(matches)==1,'exactly one actual main Screen/default Display binding required')
    main=matches[0]
    active=next(m for m in main['modes'] if m['id']==main['activeModeIndex'])
    require((active['width'],active['height'])==(default['width'],default['height']),
        'actual main screen active mode/default getter dimensions differ')
    alternatives=sorted((m for m in main['modes'] if
        (m['width'],m['height'])!=(default['width'],default['height'])), key=lambda m:m['id'])
    return main,active,alternatives


def display(boundary,value,rows,original_qmp_replay):
    require(isinstance(boundary,dict) and set(boundary)=={'kind','before','after','inventory','selected','mode_after',
        'restored_inventory','restored','active','quiet','resumed'} and boundary['kind']=='actual-default-display-change/v1',
        'actual default-display id/dimension change input absent; no virtual-display substitute')
    a=rows['a']
    before=returned(a,'display.before','display-read');after=returned(a,'display.after','display-read')
    require(isinstance(before,dict) and set(before)=={'id','width','height'} and isinstance(after,dict) and
        set(after)==set(before) and all(type(x) is int for x in (*before.values(),*after.values())) and
        min(before['width'],before['height'],after['width'],after['height'])>=100,
        'actual default display dimensions/identity missing')
    inventory=returned(a,'display.inventory','screen-read')
    main,original,alternatives=screen_inventory(inventory,before)
    selected=boundary['selected']
    require(boundary['inventory']==inventory and alternatives and selected==alternatives[0] and
        boundary['before']==before and boundary['after']==after and boundary['restored']==before and
        after['id']==before['id'] and (after['width'],after['height'])==(selected['width'],selected['height']),
        'only an actual advertised default main-screen dimension change covers product Tick cleanup')
    require(returned(a,'display.start','start')==0,'real default-display pulse missing')
    for operation,mode in (('display.mode.set',selected),('display.mode.restore',original)):
        returned(a,operation,'screen-mode')
        requests=[r for r in a if r['operation']==operation and r['event']=='request']
        require(len(requests)==1 and decode(requests[0]['value'])['numberArgument']==mode['id'],
            'actual screen API did not request the advertised selected/original mode')
    mode_after=returned(a,'display.mode.after','screen-read')
    observed,_,_=screen_inventory(mode_after,after)
    require(boundary['mode_after']==mode_after and observed['id']==main['id'] and
        observed['activeModeIndex']==selected['id'],'actual screen mode readback differs')
    restored=returned(a,'display.inventory.restored','screen-read')
    restored_screen,_,_=screen_inventory(restored,before)
    require(boundary['restored_inventory']==restored and restored_screen==main,'original actual screen mode not restored')
    changes=[r for r in a if r['event']=='display.changed' and decode(r['value']) in (before['id'],after['id'])]
    require(changes,'actual public default-display change callback missing')
    require(all(boundary[k] in value['pixels'] for k in ('active','quiet','resumed')),
            'display framebuffer phases must use the original node-bound capture pipeline')
    verify_frames(boundary['active']['frames'],boundary['active']['rect'],'continuous')
    verify_frames(boundary['quiet']['frames'],boundary['quiet']['rect'],'off')
    require(returned(a,'display.reacquire','start')==0,'display rebuild left stale owner/window state')
    verify_frames(boundary['resumed']['frames'],boundary['resumed']['rect'],'continuous')
    require(returned(a,'display.stop','stop')==0,'display test pulse did not stop')
