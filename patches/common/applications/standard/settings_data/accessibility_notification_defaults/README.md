# Accessibility reminder preference defaults

Initialize the two real USER_SECURITY reminder preference rows to their
existing business default 1 on a fresh product. The public Settings API can
then save and restore the actual prior values after real notification actions.
No sentinel value is written as a fake deletion and no private DB is changed
by a test. Existing user choices are not migrated or overwritten.

The source default file also explicitly provides its empty user table. Wait
for the existing asynchronous default-table writes before reporting the store
ready and tolerate an absent optional table instead of dereferencing undefined.
This preserves all other defaults, permissions and storage routes.

Only actual new-image preference reads, real native notification production,
UI actions, independent config consumers, idle teardown and finally restoration
can accept this capability. This source transaction is not runtime evidence.
