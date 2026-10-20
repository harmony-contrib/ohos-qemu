"""Strict capture through the original held sink QMP; no recorder/process/socket.

Grammar follows batch_media_audio_haptic_runtime's actual QEMU capture protocol.
The caller supplies no backend/path/command; only finite phase names are accepted.
"""
import hashlib
from pathlib import Path
import re
import shlex
import time
import wave

PHASES = ('baseline', 'playing', 'paused', 'resumed', 'disconnected', 'reentry')


def require(ok, text):
    if not ok:
        raise ValueError(text)


def reference(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'actual regular capture file required')
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def listing_body(text):
    require(type(text) is str, 'actual textual HMP reply required')
    return text.removeprefix("warning: 'info capture' is deprecated since v10.2, to be removed\r\n")


def mutation_empty(text, name):
    require(name in ('wavcapture', 'stopcapture'), 'finite capture mutation')
    return type(text) is str and text in ('', "warning: '" + name + "' is deprecated since v10.2, to be removed\r\n")


class HeldCapture:
    """Only original IO owns the QMP transport and guest resources."""
    def __init__(self, io, run):
        require(re.fullmatch('[a-f0-9]{32}', run), 'actual fresh paired nonce')
        self.io = io;self.run = run;self.owned = False;self.phase = None;self.path = None
        self.records = [];self.completed = {}
        self.output = Path(io.output) / ('apps_paired579_capture_' + run)
        self.output.mkdir(exist_ok=False)
        env = io.test_environment if hasattr(io, 'test_environment') else io.guest.report['test_environment']
        require(env['boot_id'] == io.boot_id and env['udid'].lower() == io.udid.lower(), 'actual sink boot/UDID envelope differs')
        argv = shlex.split(env['qemu_command'])
        audio = [argv[n+1] for n, value in enumerate(argv[:-1]) if value == '-audiodev']
        ids = [re.search(r'(?:^|,)id=([A-Za-z0-9_-]+)(?:,|$)', row) for row in audio]
        require(len(ids)==1 and ids[0] is not None, 'one actual sink QEMU audio backend required')
        self.backend = ids[0][1]
        require(any(value.startswith('es1370,') and 'audiodev='+self.backend in value.split(',') for value in argv),
                'actual sink ES1370 must use the independently observed backend')
        self.actual_environment = env
        help_reply = self.hmp('help wavcapture')
        require(re.search(r'wavcapture\s+path audiodev', help_reply), 'actual monitor capture syntax differs')
        require(listing_body(self.hmp('info capture')) == '', 'foreign/unknown sink capture exists')
        io.register_cleanup(self.cleanup)

    def hmp(self, command):
        started = time.monotonic_ns()
        row = self.io.qmp('human-monitor-command', {'command-line':command})
        self.records.append({'host_start_ns':started,'host_end_ns':time.monotonic_ns(),'actual':row})
        require(row['boot_id']==self.io.boot_id and row['completed'] and type(row['reply']) is str,
                'actual held sink QMP reply required')
        return row['reply']

    def owned_listing(self):
        text = self.hmp('info capture')
        require(re.fullmatch(r'\[0\]: Capturing audio\(48000,16,2\) to '+re.escape(str(self.path))+r': [0-9]+ bytes\r?\n',listing_body(text)),
                'actual index/path/format must be exclusively this nonce capture')

    def start(self, phase):
        require(phase in PHASES and phase not in self.completed and not self.owned, 'finite fresh capture phase')
        require(listing_body(self.hmp('info capture'))=='', 'capture ownership changed')
        path = self.output / (phase+'.wav')
        require(not path.exists() and re.fullmatch(r'/[A-Za-z0-9_./-]+',str(path)), 'fresh monitor-safe capture path')
        self.phase = phase;self.path = path;self.started = time.monotonic_ns();self.mark = len(self.records)
        # Intent precedes mutation: an ambiguous reply still requires own-path
        # inspection during original-Owner cleanup; never stop a foreign index.
        self.owned = True
        require(mutation_empty(self.hmp('wavcapture '+str(path)+' '+self.backend+' 48000 16 2'),'wavcapture'), 'actual sink capture failed')
        self.owned_listing()
        return {'boot_id':self.io.boot_id,'phase':phase,'host_begin_ns':self.started,'qmp':self.records[self.mark:]}

    def stop(self):
        require(self.owned and self.path is not None, 'no actual owned sink capture')
        self.owned_listing()
        require(mutation_empty(self.hmp('stopcapture 0'),'stopcapture'), 'actual sink capture stop failed')
        ended = time.monotonic_ns()
        require(listing_body(self.hmp('info capture'))=='', 'actual sink capture remains active')
        self.owned = False
        wav = reference(self.path)
        with wave.open(str(self.path),'rb') as stream:
            require((stream.getframerate(),stream.getsampwidth(),stream.getnchannels(),stream.getcomptype())==(48000,2,2,'NONE'),
                    'actual sink WAV format differs')
            require(stream.getnframes()>0, 'actual sink capture has no samples')
            frames = stream.getnframes()
        result = {'boot_id':self.io.boot_id,'udid':self.io.udid,'archive_sha256':self.io.archive_sha256,
            'run_id':self.run,'phase':self.phase,'wav':wav,'frames':frames,'backend':self.backend,
            'host_begin_ns':self.started,'host_end_ns':ended,'qmp':self.records[self.mark:]}
        self.completed[self.phase] = result
        return result

    def cleanup(self):
        if self.owned:
            return {'actual_capture_stop':self.stop(),'failures':[]}
        return {'boot_id':self.io.boot_id,'owned_capture_active':False,'completed':dict(self.completed),'qmp':list(self.records),'failures':[]}
