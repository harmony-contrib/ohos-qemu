#!/usr/bin/env python3
"""Compile both complete GL sampling TUs with real three-product commands."""
import argparse
import json
from pathlib import Path
from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT = ROOT / 'patches/common/foundation/graphic/graphic_2d/color_picker_gl_sampling'
PREFIX = 'foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/'
UNITS = {
    'picker': ('feature/color_picker/rs_color_picker_utils.cpp',
               'feature/color_picker/render_service_base_src/rs_color_picker_utils.o'),
    'scale': ('drawable/rs_property_drawable_utils.cpp',
              'drawable/render_service_base_src/rs_property_drawable_utils.o'),
}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    parser.add_argument('--unit', choices=UNITS, required=True)
    args = parser.parse_args()
    source, target = UNITS[args.unit]
    report = run(args, component=COMPONENT, source_file=Path(PREFIX + source),
                 target='obj/' + PREFIX + target, caller=__file__)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], objects_count=report['objects_count'],
                         first_artifact_behavior_gate_passed=False)))
