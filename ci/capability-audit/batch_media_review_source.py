#!/usr/bin/env python3
"""Bounded read-only review of fixed multimedia projects, no out/artifact inference."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PROJECTS = {
    'foundation/multimedia/av_codec': 'e5c525670d1f6622d441c9e5bf975ea0579ea177',
    'foundation/multimedia/media_library': '564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380',
    'foundation/multimedia/media_foundation': 'a9d40eb0bfcb61626ea6780527d2235cbd9bc5dc',
    'foundation/multimedia/audio_framework': '6932fa64335b8272ca4a59de7808ab0d6c9eae7a',
    'foundation/multimedia/player_framework': '3d3b1231db27561e8978652d7ae867c12f488d9a',
    'drivers/peripheral/audio': '69094b77aa2200160207b1b06b3c0b586ae2157c',
    'device/qemu': 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b',
    'interface/sdk-js': '43e34facc58b9c0f15c58571554ddd7eaa004455',
}
SNAPSHOTS = {
    ('foundation/multimedia/media_library','services/media_analysis_data_manager/include/dao/table/location_column.h'):
        ['GEO_KNOWLEDGE_TABLE =', 'KNOWLEDG_INDEX =', 'LOCATION_CITY_NAME_INDEX ='],
    ('foundation/multimedia/media_library','frameworks/innerkitsimpl/medialibrary_data_extension/src/medialibrary_rdb_utils.cpp'):
        ['vector<string> GetPhotoAndKnowledgeConnection()', 'int GetNewKnowledgeDataCount('],
    ('interface/sdk-js','api/@ohos.file.photoAccessHelper.d.ts'):
        ['class KnowledgeContent','static getRelatedEntity','static getSearchSuggestion','topicField:','recommendationCount?:'],
    ('foundation/multimedia/media_foundation','src/capi/native_audio_vivid.cpp'):
        ['dlopen("libAudioVividMetaBuilder.z.so"','dlsym(ptr, "CreateAudioVividMetaBuilder"','dlsym(ptr, "DestroyAudioVividMetaBuilder"'],
    ('foundation/multimedia/media_foundation','src/buffer/avbuffer/avmemory.cpp'):
        ['int32_t AVMemory::GetOffset()', 'uint8_t *AVMemory::GetAddr()'],
    ('device/qemu','common/virt_full/hardware/display/src/display_gralloc/display_buffer_vdi_impl.cpp'):
        ['int32_t DisplayBufferVdiImpl::GetImageLayout('],
    ('device/qemu','common/virt_full/hardware/display/src/display_gralloc/display_gralloc_gbm.cpp'):
        ['bufferHandle->stride =', 'bufferHandle->size ='],
    ('drivers/peripheral/audio','supportlibs/alsa_adapter/src/alsa_snd_capture.c'):
        ['snd_pcm_open(', 'snd_pcm_readi('],
    ('foundation/multimedia/av_codec','services/media_engine/filters/audio_capture_filter.cpp'):
        ['AudioCaptureFilter::DoStart', 'AudioCaptureFilter::DoPrepare'],
    ('foundation/multimedia/av_codec','services/media_engine/filters/video_capture_filter.cpp'):
        ['VideoCaptureFilter::GetInputSurface', 'VideoCaptureFilter::DoPrepare'],
    ('foundation/multimedia/player_framework','frameworks/native/audio_haptic/audio_haptic_player_impl.cpp'):
        ['AudioHapticPlayerImpl::Start', 'audioPlayer_->Start', 'soundPlayer_->Start'],
    ('foundation/multimedia/av_codec','services/engine/codec/video/avcencoder/avc_encoder.cpp'):
        ['int32_t AvcEncoder::GetSurfaceBufferUvOffset(', 'int32_t AvcEncoder::GetInputFrameFromAVBuffer('],
    ('foundation/multimedia/av_codec','services/engine/codec/video/avcencoder/avc_encoder_util.cpp'):
        ['case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCBCR_P010:',
         'case GraphicPixelFormat::GRAPHIC_PIXEL_FMT_YCRCB_P010:'],
}


def review(root):
    result={'read_only':True,'uses_out':False,'package_or_runtime_evidence':False,'projects':{},'snapshots':{}}
    for project,expected in PROJECTS.items():
        actual=subprocess.check_output(['git','-C',str(root/project),'rev-parse','HEAD'],text=True).strip()
        if actual!=expected:raise ValueError('fixed project changed: '+project)
        result['projects'][project]=actual
    for (project,name),needles in SNAPSHOTS.items():
        data=subprocess.check_output(['git','-C',str(root/project),'show','HEAD:./'+name])
        lines=data.decode().splitlines()
        result['snapshots'][project+'/'+name]={'sha256':hashlib.sha256(data).hexdigest(),'matches':[
            {'needle':needle,'line':i+1,'excerpt':lines[max(0,i-1):i+7]}
            for i,line in enumerate(lines) for needle in needles if needle in line]}
    tokens=['KnowledgeContent','getRelatedEntity','getSearchSuggestion']
    files=[];hits=[]
    library=root/'foundation/multimedia/media_library'
    for path in sorted(library.rglob('*')):
        if not path.is_file() or path.suffix not in ('.h','.cpp','.c','.ts','.ets','.json','.gn'):continue
        files.append(str(path.relative_to(library)))
        data=path.read_text(errors='replace')
        found=[token for token in tokens if token in data]
        if found:hits.append({'path':str(path.relative_to(library)),'tokens':found})
    result['knowledge_contract_implementation_search']={'root':'foundation/multimedia/media_library',
        'tokens':tokens,'searched_files':len(files),'hits':hits,
        'file_list_sha256':hashlib.sha256('\n'.join(files).encode()).hexdigest(),
        'scope':'current prepared fixed project files only; no claim about external vendor algorithms'}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(review(args.source_root),ensure_ascii=False,indent=2))
