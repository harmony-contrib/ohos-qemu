#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2023 Huawei Device Co., Ltd.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import subprocess
import argparse
import os
import sys

from util import build_utils
from util import file_utils


def parse_args(args):
    parser = argparse.ArgumentParser()
    build_utils.add_depfile_option(parser)

    parser.add_argument('--keyPwd', help='')
    parser.add_argument('--sign-algo', help='')
    parser.add_argument('--keyalias', help='')
    parser.add_argument('--keystoreFile', help='')
    parser.add_argument('--keystorePwd', help='')
    parser.add_argument('--profileFile', help='')
    parser.add_argument('--hapsigner', help='')
    parser.add_argument('--unsigned-hap-path-list', help='')
    parser.add_argument('--compatible_version', help='compatible_version')
    parser.add_argument('--hap-out-dir', help='')
    parser.add_argument('--inFile', help='')
    parser.add_argument('--outFile', help='')
    parser.add_argument('--profileSigned', help='')
    parser.add_argument('--inForm', help='')
    parser.add_argument('--certificate-file', help='')
    parser.add_argument('--hap-name', help='')
    parser.add_argument('--hap-list', help='')
    options = parser.parse_args(args)
    return options


def sign_app(options, unsigned_hap_path: str, signed_hap_path: str):
    cmd = ['java', '-jar', options.hapsigner, 'sign-app']
    cmd.extend(['-mode', 'localsign'])
    cmd.extend(['-signAlg', options.sign_algo])
    cmd.extend(['-keyAlias', options.keyalias])
    cmd.extend(['-inFile', unsigned_hap_path])
    cmd.extend(['-outFile', signed_hap_path])
    cmd.extend(['-profileFile', options.profileFile])
    cmd.extend(['-keystoreFile', options.keystoreFile])
    cmd.extend(['-keystorePwd', options.keystorePwd])
    cmd.extend(['-keyPwd', options.keyPwd])
    cmd.extend(['-appCertFile', options.certificate_file])
    cmd.extend(['-profileSigned', (options.profileSigned or '1')])
    cmd.extend(['-inForm', (options.inForm or 'zip')])
    child = subprocess.Popen(cmd,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
    stdout, stderr = child.communicate()
    if child.returncode:
        print(stdout.decode(), stderr.decode())
        raise Exception("Failed to sign hap")


def main(args):
    options = parse_args(args)
    if not options.hap_out_dir:
        sign_app(options, options.inFile, options.outFile)
    else:
        if not os.path.exists(options.hap_out_dir):
            os.makedirs(options.hap_out_dir, exist_ok=True)
        unsigned_hap_path_list = file_utils.read_json_file(options.unsigned_hap_path_list)
        signed_hap_names = {}
        if os.path.isfile(options.hap_list):
            hap_list = file_utils.read_json_file(options.hap_list)
            signed_hap_names['do_filter'] = hap_list.get('do_filter')
            for unsigned_to_signed in hap_list.get('hap_list'):
                names = unsigned_to_signed.split(':')
                if len(names) == 2:
                    signed_hap_names[f'{names[0]}.hsp'] = f'{names[1]}.hsp'
                    signed_hap_names[f'{names[0]}.hap'] = f'{names[1]}.hap'
                else:
                    raise ValueError(f'Value hap_list {hap_list} not compliant with format')
        for unsigned_hap_path in unsigned_hap_path_list.get('unsigned_hap_path_list'):
            signed_hap_path = unsigned_hap_path.replace('unsigned', 'signed')
            output_hap_name = f'{options.hap_name}-{os.path.basename(signed_hap_path)}'
            unsigned_hap_name = f'{options.hap_name}-{os.path.basename(unsigned_hap_path)}'
            if len(unsigned_hap_path_list.get('unsigned_hap_path_list')) == 1 and options.hap_name:
                if unsigned_hap_path_list.get('unsigned_hap_path_list')[0].endswith('.hsp'):
                    output_hap_name = f'{options.hap_name}.hsp'
                    unsigned_hap_name = output_hap_name
                else:
                    output_hap_name = f'{options.hap_name}.hap'
                    unsigned_hap_name = output_hap_name
            if signed_hap_names.get('do_filter'):
                if signed_hap_names.get(unsigned_hap_name):
                    output_hap_name = signed_hap_names.get(unsigned_hap_name)
            output_hap = os.path.join(options.hap_out_dir, output_hap_name)
            sign_app(options, unsigned_hap_path, output_hap)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
