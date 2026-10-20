void HiPlayerImpl::ApplyAudioSourceProvenance505()
{
    Qap505::Observe([&] {
        auto provenance = std::atomic_load(&audioSourceProvenance505_);
        if (!provenance || !audioSink_ || !demuxer_) { return; }
        auto completeMeta = demuxer_->GetGlobalMetaInfo();
        if (!completeMeta) { return; }
        // Both relays replace globalMeta_: reconstruct the complete existing map.
        completeMeta->SetData(Tag::APP_PID, appPid_);
        completeMeta->SetData(Tag::APP_UID, appUid_);
        if (audioRenderInfo_) {
            for (MapIt iter = audioRenderInfo_->begin(); iter != audioRenderInfo_->end(); iter++) {
                completeMeta->SetData(iter->first, iter->second);
            }
        }
        if (audioInterruptMode_) {
            for (MapIt iter = audioInterruptMode_->begin(); iter != audioInterruptMode_->end(); iter++) {
                completeMeta->SetData(iter->first, iter->second);
            }
        }
        completeMeta->SetData(Qap505::KEY, *provenance);
        audioSink_->SetParameter(completeMeta);
        Qap505::EmitForwarded(*provenance, EmitProvenance505);
    });
}
