"""Run the actual product recipe verification CLI against authentic source states."""
from pathlib import Path
import os,subprocess,tempfile,unittest
import test_batch_media_audio_haptic_lifecycle as lifecycle
import test_batch_media_audio_haptic_fixes as public_errors
import test_batch_media_capturer_frame_assembly as frames
ROOT=Path(__file__).resolve().parents[2]
RECIPE=ROOT/'scripts/build_standard_qemu_in_docker.sh'
class ProductVerifierCLI(unittest.TestCase):
 def files(self,root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
 def check(self,component,variable,log,populate):
  lines=RECIPE.read_text().splitlines();matches=[i for i,line in enumerate(lines) if 'logs/'+log+'.log' in line]
  self.assertEqual(len(matches),1);i=matches[0];fragment='\n'.join(lines[i-1:i+1]);self.assertIn('--require-patched',fragment)
  with tempfile.TemporaryDirectory(prefix='recipe-verifier-') as temporary:
   root=Path(temporary).resolve();cache=root/'cache';(cache/'logs').mkdir(parents=True);populate(root)
   environment=dict(os.environ,OHOS_ROOT=str(root),CACHE_ROOT=str(cache),PYTHONDONTWRITEBYTECODE='1',**{variable:str(component/'apply.sh')})
   def verify():return subprocess.run(['bash','-euo','pipefail','-c',fragment],env=environment,capture_output=True,text=True,timeout=30)
   before=self.files(root);bad=verify();self.assertNotEqual(bad.returncode,0,bad.stdout+bad.stderr)
   # tee owns its explicit log. The verifier may not mutate any source state.
   source_before={p:v for p,v in before.items() if not p.startswith('cache/')}
   self.assertEqual(source_before,{p:v for p,v in self.files(root).items() if not p.startswith('cache/')})
   applied=subprocess.run(['bash',str(component/'apply.sh'),'--source-root',str(root)],env=environment,capture_output=True,text=True,timeout=30)
   self.assertEqual(applied.returncode,0,applied.stdout+applied.stderr);after=self.files(root)
   good=verify();self.assertEqual(good.returncode,0,good.stdout+good.stderr)
   self.assertEqual({p:v for p,v in after.items() if not p.startswith('cache/')},
                    {p:v for p,v in self.files(root).items() if not p.startswith('cache/')})
 def test_lifecycle_product_verifier_rejects_preimage_then_reads_complete_postimage(self):
  self.check(lifecycle.COMPONENT,'AUDIO_HAPTIC_LIFECYCLE_COMPONENT_SCRIPT','verify_audio_haptic_lifecycle_component',lambda root:lifecycle.populate(root,'incarnation_e'))
 def test_public_errors_product_verifier_rejects_preimage_then_reads_complete_postimage(self):
  def populate(root):
   for name,data in public_errors.originals().items():
    target=root/'foundation/multimedia/player_framework'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
  self.check(public_errors.COMP,'AUDIO_HAPTIC_PUBLIC_ERRORS_COMPONENT_SCRIPT','verify_audio_haptic_public_errors_component',populate)
 def test_frame_assembly_product_verifier_rejects_preimage_then_reads_complete_postimage(self):
  self.check(frames.COMP,'CAPTURER_FRAME_ASSEMBLY_COMPONENT_SCRIPT','verify_capturer_frame_assembly_component',frames.populate)
if __name__=='__main__':unittest.main()
