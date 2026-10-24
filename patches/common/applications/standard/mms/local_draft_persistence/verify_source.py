#!/usr/bin/env python3
"""Require one complete pinned MMS local-text-draft source state."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'applications/standard/mms'
REVISION = '26df98e3738f4219aa45efe6a3e7f6b1be55c051'
FILES = (('entry/src/main/ets/pages/conversation/CreateNewConversation.ets', '97260d924faa4fcb202f6ec66df45f0da77c84f2e45dc077b97235544cd6bdb6', '128f661daeecbbc367e5ee453f0eed187cc6552b8594638df4fa753658ad3b22'), ('entry/src/main/ets/pages/conversation/CreateNewConversationViewModle.ets', '1dcad1224c34074000c3b76fcf906b2a06a2d37338e00b0dbd50c661464a4c18', '53445bf5faa88c2eb55edab99c4946fdcdc22ac048a8fcef65757c847a823f9a'), ('entry/src/main/ets/service/ConversationListService.ets', '7bb37ad2d705ded59226bb46df9a4f802c2d7bc430dec992ab9ead54a0cc874b', '32dd94a34774a93126f92d829254c2eacd0670457c5d60b3b58463659d8c0acb'), ('entry/src/main/ets/utils/DraftUtils.ets', '88e7a1c9097ae3030e12657329f606366e358001d8753c32f3ba056a6db1ec43', '615976263cb4cf94b139ebdb0e0e5b7bdf1096a86c88e6e084123ff04c07e11a'))


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    validate(args.source_root, require_patched=args.require_final)
