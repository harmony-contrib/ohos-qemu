ErrCode ReminderDataManager::CancelAllReminders(const std::string& bundleName,
    const int32_t userId, const int32_t callingUid, const bool isUninstallApp)
{
    NOTIFICATION_HITRACE(HITRACE_TAG_OHOS);
    CancelRemindersImplLocked(bundleName, userId, callingUid);
    if (isUninstallApp && bundleName.compare(ReminderCalendarShareTable::NAME) == 0) {
        ANSR_LOGI("%{public}s uninstall.", ReminderCalendarShareTable::NAME);
        ReminderDataShareHelper::GetInstance().ResetUid();
    }
    return ERR_OK;
}
