#!/usr/bin/env python3
"""Keep the pinned Binder singleton publication and reads under one lock."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/communication/ipc'
REVISION = 'b8d3e96cfcf382c8fae54502679ac8b3d827b428'
FILE = 'ipc/native/src/core/invoker/source/binder_connector.cpp'
HEADER = 'ipc/native/src/core/invoker/include/binder_connector.h'
OLD = '''BinderConnector *BinderConnector::GetInstance()
{
    if (instance_ == nullptr) {
        std::lock_guard<std::mutex> lockGuard(skeletonMutex);
        if (instance_ == nullptr) {
            auto temp = new (std::nothrow) BinderConnector(std::string(DRIVER_NAME));
            if (temp == nullptr) {
                ZLOGE(LABEL, "create BinderConnector object failed");
                return nullptr;
            }
            if (!temp->OpenDriver()) {
                delete temp;
                temp = nullptr;
            }
            instance_ = temp;
        }
    }

    return instance_;
}
'''
NEW = '''BinderConnector *BinderConnector::GetInstance()
{
    std::lock_guard<std::mutex> lockGuard(skeletonMutex);
    if (instance_ == nullptr) {
        auto temp = new (std::nothrow) BinderConnector(std::string(DRIVER_NAME));
        if (temp == nullptr) {
            ZLOGE(LABEL, "create BinderConnector object failed");
            return nullptr;
        }
        if (!temp->OpenDriver()) {
            delete temp;
            temp = nullptr;
        }
        instance_ = temp;
    }

    return instance_;
}
'''
OLD_TOKEN_QUERY = '''    int ret = ioctl(fd, ACCESS_TOKENID_GET_TOKENID, &selfTokenID_);
    if (ret != 0) {
        selfTokenID_ = 0;
    }
    (void)fclose(fp);
    return selfTokenID_;
'''
NEW_TOKEN_QUERY = '''    uint64_t token = 0;
    int ret = ioctl(fd, ACCESS_TOKENID_GET_TOKENID, &token);
    if (ret != 0) {
        token = 0;
    }
    (void)fclose(fp);
    return token;
'''
FILES = (
    (FILE, '4ae76cc56022f14f0e22c7902102b4165f5ed7ad5a914ba4f46feccbe1e62b41', '13c4569749bb2733f9583d1037b5ba64ba9b49d6d2f0e4ed3f7650d0c3fee3c4'),
    (HEADER, '3b3b3c20ddb2d958a70fb66c8b60242067ff3fbedad5d42f2995c4fa3afb7825', '76497e58ca4d8f0cc86acabc7c6c5eeb113355634cc1ce7a740e3f6560636198'),
)


def repaired_source(original, relative=FILE):
    if relative == HEADER:
        old = '    uint64_t selfTokenID_;\n'
        if original.count(old) != 1:
            raise ValueError('unknown Binder connector retained ABI member')
        return original.replace(old, '    [[maybe_unused]] uint64_t selfTokenID_;\n')
    if relative != FILE:
        raise ValueError('unknown Binder connector source')
    if original.count(OLD) != 1 or original.count(OLD_TOKEN_QUERY) != 1:
        raise ValueError('unknown pinned Binder connector source structure')
    return original.replace(OLD, NEW).replace(OLD_TOKEN_QUERY, NEW_TOKEN_QUERY)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('Binder connector singleton patch present: ' + str(validate(args.source_root, args.require_patched)))


if __name__ == '__main__':
    main()
