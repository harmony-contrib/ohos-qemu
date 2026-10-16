"""Host clock-protocol counterexamples only; never compile/run the C probe."""
import copy
import json
import unittest

import watchdog_clocks as clocks


class WatchdogClockTests(unittest.TestCase):
    def sample(self, before=100, boot=130, after=110, nonce='a'*32):
        return {'schema_version':1,'nonce':nonce,'monotonic_before_ns':before,
                'boottime_ns':boot,'monotonic_after_ns':after}

    def test_exact_json_text_bytes_and_optional_final_lf(self):
        sample=self.sample()
        for raw in (json.dumps(sample),json.dumps(sample)+'\n',(json.dumps(sample)+'\n').encode()):
            self.assertEqual(sample,clocks.parse(raw,'a'*32))

    def test_nonce_requires_exact_lowercase_hex_and_actual_challenge_binding(self):
        raw=json.dumps(self.sample())
        for nonce in ('A'*32,'a'*31,'a'*33,'g'*32,'a'*31+'\n',True,None):
            with self.subTest(nonce=nonce),self.assertRaises(ValueError):clocks.parse(raw,nonce)
        with self.assertRaises(ValueError):clocks.parse(raw,'b'*32)

    def test_extra_missing_schema_and_nonobject_rejected(self):
        sample=self.sample();values=[[],None,1,dict(sample,status='pass'),dict(sample,schema_version=True),dict(sample,schema_version=2)]
        for field in clocks.FIELDS:
            missing=copy.deepcopy(sample);del missing[field];values.append(missing)
        for value in values:
            with self.subTest(value=value),self.assertRaises(ValueError):clocks.parse(json.dumps(value),'a'*32)

    def test_duplicate_decoded_keys_nonfinite_and_float_rejected(self):
        raw=json.dumps(self.sample())
        duplicate=raw[:-1]+',"boottime_ns":131}'
        escaped_duplicate=raw[:-1]+',"\\u006eonce":"'+'a'*32+'"}'
        for text in (duplicate,escaped_duplicate,raw.replace('130','NaN'),raw.replace('130','Infinity'),
                     raw.replace('130','1e2'),raw.replace('130','130.0')):
            with self.subTest(text=text),self.assertRaises(ValueError):clocks.parse(text,'a'*32)

    def test_negative_bool_string_and_overflow_are_not_nanoseconds(self):
        for field in ('monotonic_before_ns','boottime_ns','monotonic_after_ns'):
            for number in (-1,True,'100',1.0,clocks.MAX_NS+1):
                sample=self.sample();sample[field]=number
                with self.subTest(field=field,number=number),self.assertRaises(ValueError):clocks.parse(json.dumps(sample),'a'*32)

    def test_multiple_lines_partial_trailing_log_prefix_and_oversize_rejected(self):
        raw=json.dumps(self.sample())
        for text in ('',raw[:-1],raw+'\n\n',raw+'\n'+raw,raw+' trailing',raw+'\r\n',' '+raw,
                     'log: '+raw,raw+'\x00','x'*1025,b'\xff'):
            with self.subTest(text=text),self.assertRaises(ValueError):clocks.parse(text,'a'*32)

    def test_monotonic_bracket_only_not_numeric_enclosure_of_boottime(self):
        self.assertEqual(10**12,clocks.parse(json.dumps(self.sample(100,10**12,110)),'a'*32)['boottime_ns'])
        with self.assertRaises(ValueError):clocks.parse(json.dumps(self.sample(110,130,100)),'a'*32)

    def test_elapsed_extrema_and_sum_of_bracket_uncertainties(self):
        actual=clocks.compare(self.sample(),self.sample(300,530,320,'b'*32))
        self.assertEqual(400,actual['boottime_elapsed_ns'])
        self.assertEqual({'minimum':190,'maximum':220},actual['monotonic_elapsed_ns'])
        self.assertEqual({'minimum':180,'maximum':210},actual['sleep_clock_difference_ns'])
        self.assertEqual(30,actual['uncertainty_ns'])
        self.assertEqual(('a'*32,'b'*32),(actual['before_nonce'],actual['after_nonce']))

    def test_zero_elapsed_difference_never_emits_sleep_state_or_pass_inference(self):
        actual=clocks.compare(self.sample(100,100,100),self.sample(200,200,200))
        self.assertEqual({'minimum':0,'maximum':0},actual['sleep_clock_difference_ns'])
        self.assertEqual(0,actual['uncertainty_ns'])
        self.assertEqual({'schema_version','before_nonce','after_nonce','boottime_elapsed_ns',
            'monotonic_elapsed_ns','sleep_clock_difference_ns','uncertainty_ns'},set(actual))

    def test_preemption_uncertainty_keeps_negative_edges_instead_of_clamping(self):
        actual=clocks.compare(self.sample(100,105,110),self.sample(300,305,310))
        self.assertEqual({'minimum':-10,'maximum':10},actual['sleep_clock_difference_ns'])
        self.assertEqual(20,actual['uncertainty_ns'])

    def test_reversed_or_overlapping_brackets_and_backwards_boot_rejected(self):
        before=self.sample()
        for after in (self.sample(0,200,10),self.sample(105,300,115),self.sample(300,129,310)):
            with self.subTest(after=after),self.assertRaises(ValueError):clocks.compare(before,after)

    def test_compare_revalidates_inputs_and_does_not_mutate_them(self):
        before=self.sample();after=self.sample(300,530,320);original=copy.deepcopy([before,after])
        clocks.compare(before,after);self.assertEqual(original,[before,after])
        before['boottime_ns']=True
        with self.assertRaises(ValueError):clocks.compare(before,after)

    def test_uint64_edges_and_touching_brackets_use_exact_integer_arithmetic(self):
        maximum=clocks.MAX_NS
        before=self.sample(0,0,0);after=self.sample(maximum,maximum,maximum)
        result=clocks.compare(before,after)
        self.assertEqual(maximum,result['boottime_elapsed_ns'])
        self.assertEqual({'minimum':0,'maximum':0},result['sleep_clock_difference_ns'])
        self.assertEqual(0,clocks.compare(before,before)['boottime_elapsed_ns'])

    def test_command_is_only_foreground_real_probe_without_fallback(self):
        script=clocks.capture_script('/data/local/tmp/clock-run/probe','a'*32)
        self.assertEqual('unset LD_LIBRARY_PATH LD_PRELOAD; test -f /data/local/tmp/clock-run/probe && '
            'test ! -L /data/local/tmp/clock-run/probe && test -x /data/local/tmp/clock-run/probe && '
            '/data/local/tmp/clock-run/probe '+'a'*32,script)
        for remote in ('relative','//path/probe','/path/../probe','/path//probe','/path/./probe','/path/probe;',
                       '/path/probe $(date)','/path/probe\n','/path/probe/',None):
            with self.subTest(remote=remote),self.assertRaises(ValueError):clocks.capture_script(remote,'a'*32)


if __name__=='__main__':unittest.main()
