"""HDC can report transport failure on stderr while returning exit code zero."""
import re


def failed(stdout, stderr=''):
    return re.search(r'\[Fail\]|Device not found or connected|^Connect server failed\s*$',
                     stdout + '\n' + stderr, re.M) is not None
