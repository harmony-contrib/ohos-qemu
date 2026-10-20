#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2021 Huawei Device Co., Ltd.
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

import os
import sys
import argparse


sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
from scripts.util.file_utils import read_json_file  # noqa: E402


def check_third_party_deps(args, dep_part: str, parts_deps_info: dict, _tips_info: dict, third_deps_allow_list: list):
    """check whether the three-party dependency is in the part declaration"""
    if args.part_name == dep_part:
        return
    part_deps_info = parts_deps_info.get(args.part_name)
    if not part_deps_info:
        _warning_info = f"{_tips_info} {args.part_name}."
    elif not part_deps_info.get('third_party') or \
        not dep_part in part_deps_info.get('third_party'):
        _warning_info = f"{_tips_info} {part_deps_info.get('build_config_file')}."
    else:
        _warning_info = ""

    if _warning_info != "":
        if args.target_path in third_deps_allow_list:
            print(f"[0/0] WARNING: {_warning_info}")
        else:
            raise Exception(_warning_info)

    return


def load_part_info(depfiles: list):
    """load part path info from parts_info"""
    # load parts path info file
    parts_path_file = 'build_configs/parts_info/parts_path_info.json'
    parts_path_info = read_json_file(parts_path_file)
    if parts_path_info is None:
        raise Exception("read pre_build parts_path_info failed.")
    depfiles.append(parts_path_file)

    # load path to parts info file
    path_parts_file = 'build_configs/parts_info/path_to_parts.json'
    path_parts_info = read_json_file(path_parts_file)
    if path_parts_info is None:
        raise Exception("read pre_build path to parts failed.")
    depfiles.append(path_parts_file)

    return parts_path_info, path_parts_info


def get_path_from_label(label: str):
    """get part path from target label, the format is //path:module"""
    return label.lstrip('//').split(':')[0]


def get_path_from_module_list(cur_part_name: str, depfiles: list) -> list:
    parts_module_lists = []
    parts_modules_file = "build_configs/parts_info/parts_modules_info.json"
    parts_modules_info = read_json_file(parts_modules_file)
    if parts_modules_info is None:
        raise Exception("read pre_build parts module info failed.")
    depfiles.append(parts_modules_file)

    for parts_module in parts_modules_info.get("parts"):
        if parts_module.get("part_name") == cur_part_name:
            parts_module_lists = parts_module["module_list"]
            break
    parts_path = [get_path_from_label(x) for x in parts_module_lists]

    return parts_path


def get_part_pattern(cur_part_name: str, parts_path_info: dict, path_parts_info: dict, depfiles: list,
                     component_path_file: str) -> list:
    """get all part path from part info"""
    part_pattern = []
    part_path = parts_path_info.get(cur_part_name)
    if part_path is None:
        return part_pattern

    path_to_part = path_parts_info.get(part_path, [])
    if len(path_to_part) == 1:
        part_pattern.append(part_path)
    else:
        part_pattern.extend(get_path_from_module_list(cur_part_name, depfiles))

    if not os.path.exists(component_path_file):
        return part_pattern

    component_path_info: dict[str, list[str]] = read_json_file(component_path_file)
    module_paths = component_path_info.get(part_path, [])
    part_pattern.extend(module_paths)

    return part_pattern


def get_dep_part(dep_path: str, third_part_info: dict) -> str:
    """gets the part by the longest path match"""
    for part_info in third_part_info:
        path = part_info[0]
        part = part_info[1][0]
        if dep_path.find(path) != -1:
            return part
    return ""


def check_part_deps(args, part_pattern: str, path_parts_info: dict, compile_standard_allow_info: dict, depfiles: list):
    deps_allow_list = compile_standard_allow_info.get("deps_added_external_part_module", [])
    third_deps_allow_list = compile_standard_allow_info.get("third_deps_bundle_not_add", [])
    parts_deps_file = 'build_configs/parts_info/parts_deps.json'
    parts_deps_info = read_json_file(parts_deps_file)
    if parts_deps_info is None:
        raise Exception("read pre_build parts_deps failed.")
    depfiles.append(parts_deps_file)

    parts_src_flag_file = "build_configs/parts_src_flag.json"
    parts_src_info = read_json_file(parts_src_flag_file)
    third_party_allow_list = os.path.join(args.source_root_dir, "out/products_ext/third_party_allow_list.json")
    if not os.path.exists(third_party_allow_list):
        third_party_allow_list = os.path.join(args.source_root_dir, "build/third_party_allow_list.json")
    third_party_allow_info = read_json_file(third_party_allow_list)

    # filter third_party part info, sort by longest path match
    third_party_info = [x for x in path_parts_info.items() if x[0].find('third_party') != -1]
    third_party_info.reverse()
    for dep in args.deps:
        dep_path = get_path_from_label(dep)
        if dep_path.find('third_party/rust/crates') != -1:
            continue
        if dep_path.find('third_party') != -1:
            dep_part = get_dep_part(dep_path, third_party_info)
            
            if dep_part not in parts_src_info and dep_part in third_party_allow_info:
                print(f"[0/0] WARNING: deps third_party '{dep_part}' not configured in part config json, "
                    f"target: '{args.target_path}', deps: '{dep}'")
            elif dep_part not in parts_src_info and dep_part not in third_party_allow_info:
                raise Exception(
                    f"deps third_party '{dep_part}' not configured in part config json, "
                    f"target: '{args.target_path}', deps: '{dep}'")
                        
            tips_info = "{} depend part {}, need set part deps {} info to".format(
                args.target_path, dep, dep_part)
            check_third_party_deps(args, dep_part, parts_deps_info, tips_info, third_deps_allow_list)
            continue

        match_flag = False
        for pattern in part_pattern:
            if dep_path.startswith(pattern):
                match_flag = True
                break
        if match_flag is False:
            message = "deps validation part_name: '{}', target: '{}', dep: '{}' failed!!!".format(
                args.part_name, args.target_path, dep)
            if args.target_path in deps_allow_list:
                print(f"[0/0] WARNING:{message}")
            else:
                raise Exception(message)


def check(args) -> list:
    depfiles = []
    # ignore test related parts
    part_allow_set = {'libc-test', 'libc-test-lib', 'libc-gtest-lib'}
    if args.part_name in part_allow_set:
        return depfiles

    compile_standard_allow_file = args.compile_standard_allow_file
    compile_standard_allow_info = read_json_file(compile_standard_allow_file)
    parts_path_info, path_parts_info = load_part_info(depfiles)
    component_path_file = os.path.join(args.source_root_dir, "out/products_ext/component_multipath_dict.json")

    part_pattern = get_part_pattern(args.part_name, parts_path_info, path_parts_info, depfiles, component_path_file)
    if not part_pattern:
        gn_allow_list = compile_standard_allow_info.get("gn_part_or_subsystem_error", [])
        message = "part_name: '{}' path is not exist, please check target: '{}'".format(
            args.part_name, args.target_path)
        if args.target_path in gn_allow_list:
            print(f"[0/0] {message}")
            return depfiles
        else:
            raise Exception(message)

    check_part_deps(args, part_pattern, path_parts_info, compile_standard_allow_info, depfiles)

    return depfiles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--deps', nargs='*', required=True)
    parser.add_argument('--part-name', required=True)
    parser.add_argument('--target-path', required=True)
    parser.add_argument('--source-root-dir', required=True)
    args = parser.parse_args()

    check(args)

    return 0


if __name__ == '__main__':
    sys.exit(main())
