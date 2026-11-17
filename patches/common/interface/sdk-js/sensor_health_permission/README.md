# Sensor heart-rate permission contract

The API 26 deprecated `SensorType.SENSOR_TYPE_ID_HEART_RATE` overloads still
refer to `HEALTH_DATA` or `HEART_RATE` permission names that do not exist in
the pinned AccessToken definitions. The actual Sensor service, Native C header,
and current `SensorId.HEART_RATE` overloads all require the registered
`ohos.permission.READ_HEALTH_DATA` user-grant permission. Correct only these
three declaration comments. Do not add alias grants or bypass Sensor checks.
