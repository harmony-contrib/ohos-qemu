# Calendar provider dependency

Remove the stale CalendarData prebuilt target and its dependencies. The real
provider is installed by the calendar_data source component, not by a second
HAP copied to the same installation directory. Do not interpret this dependency
change as successful provider behavior.
