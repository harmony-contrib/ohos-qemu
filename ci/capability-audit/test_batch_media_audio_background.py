"""Official SDK typecheck plus actual ETS helper resource state machine with controlled services."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).parent
SDK=Path(os.environ.get('BATCH_MEDIA_PUBLIC_SDK_ROOT','/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0'))

class Background(unittest.TestCase):
 def test_actual_ETS_helper_official_API26_types_and_failure_cleanup(self):
  source=(HERE/'batch_media_audio_event_probe.ets').read_text().split('@Entry')[0].replace("import nativeProbe from 'libbatchmediaaudioevent.so';\n",'')
  with tempfile.TemporaryDirectory(prefix='batch-media-background-') as temp:
   root=Path(temp);controller=root/'background-controller.ts';controller.write_text(source+'\nexport { AudioRecordingSession };\n')
   subprocess.run(['node',str(SDK/'ets/build-tools/ets-loader/node_modules/typescript/lib/tsc.js'),'--skipLibCheck','--strict','--target','ES2020','--module','commonjs','--moduleResolution','node','--lib','ES2020,DOM','--baseUrl',str(SDK/'ets/api'),'--outDir',str(root),str(controller)],check=True,timeout=30)
   subprocess.run(['node',str(HERE/'fixtures/batch_media/audio_events/background_lifecycle_harness.js'),str(root/'background-controller.js'),str(root)],check=True,timeout=10)

if __name__=='__main__':unittest.main(verbosity=2)
