"""Audio-only opaque-hilog transport; all other parsing delegates to shared code.

No shared-module monkeypatching. The replacement text is only the exact legacy
collector display projection. Typed proof consumers cannot consume that view.
"""
import re


def require(value,message):
    if not value:raise ValueError(message)


class AudioHilogTransport:
    def __init__(self,value,hdc,target,*,checked,original,command_exit,failed):
        self.value,self.hdc,self.target=value,hdc,target
        self.checked,self.original,self.command_exit,self.failed=checked,original,command_exit,failed
        self.hilog={};self.opaque_keys=set();self.audit={}
        for segment in value['segments']:
            if 'native_log'not in segment:continue
            require(segment['expected']['action']=='start','only actual start-segment native logs are opaque')
            ref=segment['native_log'];matches=[r for r in value['observations']if r['raw']==ref]
            require(len(matches)==1,'opaque hilog requires one exact observation binding')
            o=matches[0];i=o['command']
            require(type(i)is int and 0<=i<len(value['commands'])and i not in self.hilog,'opaque command reused or invalid')
            row=value['commands'][i];label=segment['phase']+'-native-log'
            require(o['script']=='hilog -x'and o['name']==row['label']==label,'only exact original hilog observation is opaque')
            argv=row['argv'];require(type(argv)is list and len(argv)==5 and argv[:4]==[hdc,'-t',target,'shell'],'opaque hilog target/argv differs')
            markers=re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=',argv[4]);require(len(markers)==1,'one argv-bound hilog nonce required')
            expected='hilog -x; task_ui_rc=$?; printf "\\n'+markers[0]+'%s\\n" "$task_ui_rc"'
            require(argv[4]==expected,'opaque hilog command must match original exact argv')
            key=(ref['path'],ref['sha256']);require(key not in self.opaque_keys,'opaque observation reused')
            self.hilog[i]=(o,markers[0]);self.opaque_keys.add(key)

    def is_opaque(self,raw):
        return (raw['path'],raw['sha256'])in self.opaque_keys

    def _body(self,index):
        row=self.value['commands'][index];o,marker=self.hilog[index]
        raw=self.checked(row['raw']).read_bytes();require(len(raw)<=6*1024*1024,'bounded raw hilog required')
        # Surrogateescape is reversible: no original payload byte is discarded.
        text=raw.decode('utf-8',errors='surrogateescape').replace('\r\n','\n').replace('\r','\n')
        require(not self.failed(text),'original HDC transport error in opaque hilog')
        _,code=self.command_exit(text,marker);require(code==0,'real guest command success nonce required')
        # Exactly reproduce the already-recorded collector display view, never
        # interpret its replacements as JSON, sample, token or native proof.
        # Path.read_text uses universal newlines before the collector parses it.
        projected=raw.decode('utf-8',errors='replace').replace('\r\n','\n').replace('\r','\n')
        body,display_code=self.command_exit(projected,marker)
        require(display_code==code,'legacy projection changed the command exit record')
        normalized=body.rstrip('\n');actual=self.checked(o['raw']).read_text()
        require(actual==normalized,'normalized opaque observation differs from actual legacy collector projection')
        self.audit[index]=dict(command=index,raw=dict(row['raw']),raw_bytes=len(raw),normalized_observation=dict(o['raw']),
            normalization='original collector UTF8 replacement projection plus original CR/footer/trailing-newline handling',
            proof_body_semantics_used=False,raw_payload_preserved=True,guest_exit_code=code,
            surrogateescaped_payload_bytes=sum(0xdc80<=ord(c)<=0xdcff for c in text),
            scope='opaque informational hilog only; not first-frame/native/PCM/VDI proof')
        return normalized

    def verify_commands(self,rows,hdc,target):
        require(rows is self.value['commands']and(hdc,target)==(self.hdc,self.target),'original command/target collection required')
        for index,row in enumerate(rows):
            if index not in self.hilog:
                self.original.verify_commands([row],hdc,target);continue
            require(type(row.get('exit_code'))is int and row['exit_code']==0 and not row.get('timed_out'),'command failed/timed out')
            require(not row.get('layout_transition'),'exact hilog cannot claim a UITest layout transition')
            self._body(index)
            require(not re.search(r'\b(?:sqlite3|pm\s+grant|bm\s+grant|power-shell|system_powerdown)\b',row['argv'][4]),
                'collector cannot change SQL, grants or power policy')

    def exact_script(self,index,script):
        row=self.value['commands'][index]
        if index not in self.hilog:return self.original.exact_script(row,script)
        require(script=='hilog -x','opaque output cannot substitute another script')
        return self._body(index)

    def reject_typed_proof(self,raw):
        require(not self.is_opaque(raw),'opaque hilog display must not be used as structured proof')
