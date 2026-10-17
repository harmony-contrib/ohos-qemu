import json
import os
import subprocess
import unittest

from guest_process_identity import (starttime_shell, uids_shell, identity_shell,
    producer_shell, producer_rows, producer_exit_code, cleanup_producer_shell)


REMOTE='/data/local/tmp/qemu-mic-'+'a'*32
MARKER='__PCM_CHILD_EXIT_'+'b'*32+'__='


def stat_line(comm='normal', start='12345'):
    return '123 ('+comm+') S '+' '.join(['0']*18+[start]+['0']*20)


class ProcessIdentityTests(unittest.TestCase):
    def shell(self, script, *, stat=None, uids='100 100 100 100', cat_rc='0', sed_rc='0', saved='12345', exe=None):
        # No actual process is signalled: every command which could signal or
        # inspect a guest is a fixture function, and kill only prints a receipt.
        mock='''
cat() {
 case "$1" in
 */producer.pid) printf '%s\\n' 123;;
 */producer.start) printf '%s\\n' "$TEST_SAVED";;
 /proc/123/stat) printf '%s\\n' "$TEST_STAT"; return "$TEST_CAT_RC";;
 *) return 2;; esac
}
sed() { printf '%s\\n' "$TEST_UIDS"; return "$TEST_SED_RC"; }
stat() { case "$*" in *'%u %a'*) printf '0 700\\n';; *) printf '0\\n';; esac; }
readlink() { printf '%s\\n' "$TEST_EXE"; }
pidof() { printf '123\\n'; }
kill() { printf 'MOCK_SIGNAL %s\\n' "$*"; task_fake_killed=yes; }
test() {
 case "$1:$2" in
 -d:/proc/123) command test "$task_fake_killed" != yes; return;;
 -d:/data/local/tmp/*|-e:/data/local/tmp/*|-f:/data/local/tmp/*) return 0;;
 esac
 command test "$@"
}
'''
        env=dict(os.environ,TEST_STAT=stat if stat is not None else stat_line(),TEST_UIDS=uids,
                 TEST_CAT_RC=cat_rc,TEST_SED_RC=sed_rc,TEST_SAVED=saved,TEST_EXE=exe or REMOTE+'/alsa_inject')
        return subprocess.run(['/bin/sh','-c',mock+'\n'+script],env=env,capture_output=True,text=True,timeout=3)

    def test_comm_last_delimiter_and_whitespace(self):
        for comm in ('hello world','a) b ) c','a (b) c','a\nb) c'):
            with self.subTest(comm=comm):
                p=self.shell(starttime_shell('123'),stat=stat_line(comm))
                self.assertEqual((p.returncode,p.stdout),(0,'12345\n'))

    def test_failed_or_malformed_stat_is_not_generation(self):
        for raw in ('','123 broken','999 (wrong) '+stat_line().split(') ')[1],stat_line(start='0'),stat_line(start=''),stat_line(start='1x')):
            with self.subTest(raw=raw):self.assertNotEqual(self.shell(starttime_shell('123'),stat=raw).returncode,0)
        self.assertNotEqual(self.shell(starttime_shell('123'),cat_rc='2').returncode,0)

    def test_uids_require_complete_single_successful_read(self):
        self.assertEqual(self.shell(uids_shell('123')).stdout,'100 100 100 100\n')
        for raw in ('','100 100','100 100 100 100\n100 100 100 100','100 bad 100 100'):
            self.assertNotEqual(self.shell(uids_shell('123'),uids=raw).returncode,0)
        self.assertNotEqual(self.shell(uids_shell('123'),sed_rc='2').returncode,0)

    def test_identity_never_hides_different_effective_uid(self):
        p=self.shell(identity_shell('org.example.test',all_uids=False))
        self.assertEqual((p.returncode,p.stdout),(0,'123 12345 100\n'))
        self.assertNotEqual(self.shell(identity_shell('org.example.test',all_uids=False),uids='100 0 100 100').returncode,0)

    def test_cleanup_only_signals_complete_matching_generation(self):
        p=self.shell(cleanup_producer_shell(REMOTE),uids='0 0 0 0')
        self.assertEqual((p.returncode,p.stdout),(0,'MOCK_SIGNAL -TERM 123\n'))
        for kwargs in ({'saved':''},{'saved':'0'},{'saved':'012345'},{'saved':'999'},
                       {'stat':''},{'cat_rc':'2'},{'sed_rc':'2'},{'uids':'0 100 0 0'},{'exe':'/different/exe'}):
            with self.subTest(kwargs=kwargs):
                p=self.shell(cleanup_producer_shell(REMOTE),**({'uids':'0 0 0 0'}|kwargs))
                self.assertNotEqual(p.returncode,0)
                self.assertNotIn('MOCK_SIGNAL',p.stdout)

    def test_untrusted_pid_and_remote_are_not_shell_code(self):
        for pid in ('0','-1','123; true','$(true)','$1'):
            with self.assertRaises(ValueError):starttime_shell(pid)
        with self.assertRaises(ValueError):cleanup_producer_shell('/tmp/arbitrary')

    def receipt(self):
        return dict(argv=['hdc','-t','target','shell',producer_shell(REMOTE,MARKER)],
                    host_exit_code=0,guest_exit_code=0,guest_exit_marker=MARKER)

    def test_producer_requires_actual_child_exit_not_hdc_success(self):
        body=json.dumps({'event':'feeding'})+'\n'+json.dumps({'event':'played'})+'\n'
        raw=body+'\n'+MARKER+'0\n'
        self.assertEqual(producer_rows(raw,self.receipt(),remote=REMOTE),[{'event':'feeding'},{'event':'played'}])
        self.assertEqual(producer_exit_code(raw,MARKER),0)
        for bad in (body,raw+'noise',raw.replace(MARKER+'0',MARKER+'7'),raw+raw,
                    'sh: awk: inaccessible or not found\n'+raw,
                    '{"event":"feeding","event":"played"}\n\n'+MARKER+'0\n'):
            with self.subTest(raw=bad):
                with self.assertRaises(ValueError):producer_rows(bad,self.receipt(),remote=REMOTE)
        receipt=self.receipt();receipt['argv'][-1]='true'
        with self.assertRaises(ValueError):producer_rows(raw,receipt,remote=REMOTE)


if __name__=='__main__':unittest.main()
