/*
 * Copyright (c) 2022-2024 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License"),
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
/**
 * @file
 * @kit AbilityKit
 */
import { Caller } from '../@ohos.app.ability.UIAbility';
import OpenLinkOptions from '../@ohos.app.ability.OpenLinkOptions';
import AtomicServiceOptions from '../@ohos.app.ability.AtomicServiceOptions';
import { AsyncCallback } from '../@ohos.base';
import { ConnectOptions } from '../ability/connectOptions';
import ExtensionContext from './ExtensionContext';
import StartOptions from '../@ohos.app.ability.StartOptions';
import Want from '../@ohos.app.ability.Want';
/**
 * The ServiceExtensionContext module provides the context environment for the ServiceExtensionAbility. It inherits from
 * ExtensionContext.
 *
 * You can use the APIs of this module to start, terminate, connect, and disconnect an ability.
 *
 * > **NOTE**
 * >
 * > - The APIs of this module must be used on the main thread, but not in child threads such as Worker and TaskPool.
 *
 * @syscap SystemCapability.Ability.AbilityRuntime.Core
 * @systemapi
 * @stagemodelonly
 * @since 9
 */
declare class ServiceExtensionContext extends ExtensionContext {
    /**
     * Starts an ability. This API can be called only on the main thread. It uses an asynchronous callback to return the
     * result.
     *
     * @param { Want } want - Want information about the target ability, such as the ability name and bundle name.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is started, **err** is
     *     **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startAbility(want: Want, callback: AsyncCallback<void>): void;
    /**
     * Starts an ability. This API can be called only on the main thread. It uses an asynchronous callback to return the
     * result.
     *
     * @param { Want } want - Want information about the target ability.
     * @param { StartOptions } options - Parameters used for starting the ability.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is started, **err** is
     *     **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is
     *     forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startAbility(want: Want, options: StartOptions, callback: AsyncCallback<void>): void;
    /**
     * Starts an ability. This API can be called only on the main thread. It uses a promise to return the result
     * asynchronously.
     *
     * @param { Want } want - Want information about the target ability, such as the ability name and bundle name.
     * @param { StartOptions } [options] - Parameters used for starting the ability.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startAbility(want: Want, options?: StartOptions): Promise<void>;
    /**
     * Starts a UIAbility through App Linking. This API can be called only on the main thread. It uses a promise to return
     * the result asynchronously.
     *
     * A URL in the standard format is passed in to the **link** field to start the target UIAbility based on the implicit
     * Want matching rules. The target UIAbility must have the following filter characteristics to process links of App
     * Linking:
     *
     * - The **actions** field must contain **ohos.want.action.viewData**.
     * - The **entities** field must contain **entity.system.browsable**.
     * - The **uris** field must contain elements whose **scheme** is **https** and **domainVerify** is **true**.
     *
     * If an input parameter is invalid, for example, a mandatory parameter is not set or the URL set in **link** is not
     * in the standard format, an exception is thrown. If the parameter verification is successful but an error occurs
     * when starting the target UIAbility, the error information is returned through promise.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { string } link - URL to open, which must be in the standard format.
     * @param { OpenLinkOptions } [options] - Options of the URL.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Failed to start the invisible ability.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000013 - The application is controlled by EDM.
     * @throws { BusinessError } 16000019 - No matching ability is found.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000136 - The UIAbility is prohibited from launching itself via App Linking. [since 23]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 12
     */
    openLink(link: string, options?: OpenLinkOptions): Promise<void>;
    /**
     * Starts an ability with the caller information specified. The caller information is carried in **Want** and
     * identified at the system service layer. The ability can obtain the caller information from the **Want** parameter
     * in the **onCreate** lifecycle callback. When this API is used to start an ability, the caller information carried
     * in **Want** is not overwritten by the current application information. The system service layer can obtain the
     * initial caller information. This API can be called only on the main thread. It uses an asynchronous callback to
     * return the result.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } want - Want information about the target ability.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is started, **err** is
     *     **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000013 - The application is controlled by EDM.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 10
     */
    startAbilityAsCaller(want: Want, callback: AsyncCallback<void>): void;
    /**
     * Starts an ability with the caller information and start options specified. The caller information is carried in
     * **Want** and identified at the system service layer. The ability can obtain the caller information from the
     * **Want** parameter in the **onCreate** lifecycle callback. When this API is used to start an ability, the caller
     * information carried in **Want** is not overwritten by the current application information. The system service layer
     * can obtain the initial caller information. This API can be called only on the main thread. It uses an asynchronous
     * callback to return the result.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } want - Want information about the target ability.
     * @param { StartOptions } options - Parameters used for starting the ability.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is started, **err** is
     *     **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000013 - The application is controlled by EDM.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 10
     */
    startAbilityAsCaller(want: Want, options: StartOptions, callback: AsyncCallback<void>): void;
    /**
     * Starts an ability with the start options specified. The caller information is carried in **Want** and identified at
     * the system service layer. The ability can obtain the caller information from the **Want** parameter in the
     * **onCreate** lifecycle callback. When this API is used to start an ability, the caller information carried in
     * **Want** is not overwritten by the current application information. The system service layer can obtain the initial
     * caller information. This API can be called only on the main thread. It uses a promise to return the result
     * asynchronously.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } want - Want information about the target ability.
     * @param { StartOptions } options - Parameters used for starting the ability.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000013 - The application is controlled by EDM.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 10
     */
    startAbilityAsCaller(want: Want, options?: StartOptions): Promise<void>;
    /**
     * Starts an ability with the account ID specified. This API can be called only on the main thread. It uses an
     * asynchronous callback to return the result.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Want information about the target ability.
     * @param { number } accountId - ID of the target system account.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is started, **err** is
     *     **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000013 - The application is controlled by EDM.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startAbilityWithAccount(want: Want, accountId: number, callback: AsyncCallback<void>): void;
    /**
     * Starts an ability with the account ID and start options specified. This API can be called only on the main thread.
     * It uses an asynchronous callback to return the result.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Want information about the target ability.
     * @param { number } accountId - ID of the target system account.
     * @param { StartOptions } options - Parameters used for starting the ability.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is started, **err** is
     *     **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type. [since 9 - 9]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is
     *     forbidden. [since 9 - 9]
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startAbilityWithAccount(want: Want, accountId: number, options: StartOptions, callback: AsyncCallback<void>): void;
    /**
     * Starts an ability with the account ID specified. This API can be called only on the main thread. It uses a promise
     * to return the result asynchronously.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Want information about the target ability.
     * @param { number } accountId - ID of the target system account.
     * @param { StartOptions } [options] - Parameters used for starting the ability.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000013 - The application is controlled by EDM.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 12]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startAbilityWithAccount(want: Want, accountId: number, options?: StartOptions): Promise<void>;
    /**
     * Starts a ServiceExtensionAbility. This API uses an asynchronous callback to return the result.
     *
     * @param { Want } want - Want information about the target ability.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ServiceExtensionAbility is
     *     started, **err** is **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startServiceExtensionAbility(want: Want, callback: AsyncCallback<void>): void;
    /**
     * Starts a ServiceExtensionAbility. This API uses a promise to return the result asynchronously.
     *
     * @param { Want } want - Want information about the target ability.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startServiceExtensionAbility(want: Want): Promise<void>;
    /**
     * Starts a ServiceExtensionAbility with the account ID specified. This API uses an asynchronous callback to return
     * the result.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     * > > Permission verification is not required when **accountId** specifies the current user.
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Want information about the target ability.
     * @param { number } accountId - ID of the target system account.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ServiceExtensionAbility is
     *     started, **err** is **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startServiceExtensionAbilityWithAccount(want: Want, accountId: number, callback: AsyncCallback<void>): void;
    /**
     * Starts a ServiceExtensionAbility with the account ID specified. This API uses a promise to return the result
     * asynchronously.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     * > > Permission verification is not required when **accountId** specifies the current user.
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Want information about the target ability.
     * @param { number } accountId - ID of the target system account.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000019 - No matching ability is found. [since 12]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startServiceExtensionAbilityWithAccount(want: Want, accountId: number): Promise<void>;
    /**
     * Stops a ServiceExtensionAbility. This API uses an asynchronous callback to return the result.
     *
     * @param { Want } want - Want information about the target ability.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ServiceExtensionAbility is
     *     stopped, **err** is **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 10]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    stopServiceExtensionAbility(want: Want, callback: AsyncCallback<void>): void;
    /**
     * Stops a ServiceExtensionAbility. This API uses a promise to return the result asynchronously.
     *
     * @param { Want } want - Want information about the target ability.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 10]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    stopServiceExtensionAbility(want: Want): Promise<void>;
    /**
     * Stops a ServiceExtensionAbility with the specified account. This API uses an asynchronous callback to return the
     * result.
     *
     * > **NOTE**
     * >
     * > Permission verification is not required when **accountId** specifies the current user.
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Want information about the target ability.
     * @param { number } accountId - ID of the target system account.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ServiceExtensionAbility is
     *     stopped, **err** is **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    stopServiceExtensionAbilityWithAccount(want: Want, accountId: number, callback: AsyncCallback<void>): void;
    /**
     * Stops a ServiceExtensionAbility with the specified account. This API uses a promise to return the result
     * asynchronously.
     *
     * > **NOTE**
     * >
     * > Permission verification is not required when **accountId** specifies the current user.
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Want information about the target ability.
     * @param { number } accountId - ID of the target system account.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    stopServiceExtensionAbilityWithAccount(want: Want, accountId: number): Promise<void>;
    /**
     * Terminates this ability. This API can be called only on the main thread. It uses an asynchronous callback to return
     * the result.
     *
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is terminated, **err**
     *     is **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist. [since 9 - 9]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 9 - 9]
     * @throws { BusinessError } 16000005 - The specified process does not have the permission. [since 9 - 9]
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    terminateSelf(callback: AsyncCallback<void>): void;
    /**
     * Terminates this ability. This API can be called only on the main thread. It uses a promise to return the result
     * asynchronously.
     *
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 16000001 - The specified ability does not exist. [since 9 - 9]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 9 - 9]
     * @throws { BusinessError } 16000005 - The specified process does not have the permission. [since 9 - 9]
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    terminateSelf(): Promise<void>;

    /**
     * Stops this SERVICE instance only if expectedStartId is still its current request.
     * The same-image native ServiceExtensionContext and AMS implement this method.
     * A stale request returns false; native permission/token/IPC failures reject.
     * @param { number } expectedStartId - Positive delivered onRequest startId.
     * @returns { Promise<boolean> } Whether the current SERVICE request was stopped.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 26.0.0 dynamic
     */
    terminateSelfIfStartId(expectedStartId: number): Promise<boolean>;
    /**
     * Connects this ability to a ServiceExtensionAbility. This API can be called only on the main thread.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } want - Want information about the target ability, such as the ability name and bundle name.
     * @param { ConnectOptions } options - Callback used to return the information indicating that the connection is
     *     successful, interrupted, or failed.
     * @returns { number } A number, based on which the connection will be interrupted.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000002 - Incorrect ability type. [since 10]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed. [since 10]
     * @throws { BusinessError } 16000008 - The crowdtesting application expires. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI. [since 10]
     * @throws { BusinessError } 16000055 - Installation-free timed out. [since 10]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    connectServiceExtensionAbility(want: Want, options: ConnectOptions): number;
    /**
     * Connects this ability to a ServiceExtensionAbility of a given account. This API can be called only on the main
     * thread.
     *
     * This API can be properly called on phones and tablets. If it is called on other devices, error code 16000006 is
     * returned.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     * > > Permission verification is not required when **accountId** specifies the current user.
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Want information about the target ability.
     * @param { number } accountId - ID of the target system account.
     * @param { ConnectOptions } options - Remote object instance.
     * @returns { number } Result code of the connection.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000002 - Incorrect ability type. [since 10]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 10]
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed. [since 10]
     * @throws { BusinessError } 16000008 - The crowdtesting application expires. [since 10]
     * @throws { BusinessError } 16000012 - The application is controlled. [since 10]
     * @throws { BusinessError } 16000013 - The application is controlled by EDM. [since 10]
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI. [since 10]
     * @throws { BusinessError } 16000055 - Installation-free timed out. [since 10]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    connectServiceExtensionAbilityWithAccount(want: Want, accountId: number, options: ConnectOptions): number;
    /**
     * Disconnects this ability from a ServiceExtensionAbility and after the successful disconnection, sets the remote
     * object returned upon the connection to void. This API can be called only on the main thread. It uses an
     * asynchronous callback to return the result.
     *
     * @param { number } connection - Number returned after **connectServiceExtensionAbility** is called.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is disconnected,
     *     **err** is **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    disconnectServiceExtensionAbility(connection: number, callback: AsyncCallback<void>): void;
    /**
     * Disconnects this ability from a ServiceExtensionAbility and after the successful disconnection, sets the remote
     * object returned upon the connection to void. This API can be called only on the main thread. It uses a promise to
     * return the result asynchronously.
     *
     * @param { number } connection - Number returned after **connectServiceExtensionAbility** is called.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    disconnectServiceExtensionAbility(connection: number): Promise<void>;
    /**
     * Starts an ability in the foreground or background and obtains the caller object for communicating with the ability.
     * This API can be called only on the main thread. It uses a promise to return the result asynchronously.
     *
     * This API cannot be used to start the UIAbility with the launch type set to
     * [specified](docroot://application-models/uiability-launch-type.md#specified).
     *
     * Observe the following when using this API:
     *
     * - If an application running in the background needs to call this API to start an ability, it must have the
     * ohos.permission.START_ABILITIES_FROM_BACKGROUND permission.
     * - If **exported** of the target ability is **false** in cross-application scenarios, the caller must have the
     * ohos.permission.START_INVISIBLE_ABILITY permission.
     * - The rules for using this API in the same-device and cross-device scenarios are different. For details, see
     * [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @permission ohos.permission.ABILITY_BACKGROUND_COMMUNICATION
     * @param { Want } want - Information about the ability to start, including **abilityName**, **moduleName**,
     *     **bundleName**, **deviceId**, and **parameters** (optional). If **parameters** is left blank or null, the
     *     ability is started in the background.
     * @returns { Promise<Caller> } Promise used to return the caller object to communicate with.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission. [since 9 - 9]
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released. [since 9 - 9]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startAbilityByCall(want: Want): Promise<Caller>;
    /**
     * Starts an ability with the account ID specified and obtains the caller object for communicating with the ability.
     * This API can be called only on the main thread. It uses a promise to return the result asynchronously.
     *
     * This API cannot be used to start the UIAbility with the launch type set to
     * [specified](docroot://application-models/uiability-launch-type.md#specified).
     *
     * Observe the following when using this API:
     *
     * - If an application needs to call this API to start an ability that belongs to another user, it must have the
     * ohos.permission.ABILITY_BACKGROUND_COMMUNICATION and ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS permissions.
     * - If an application running in the background needs to call this API to start an ability, it must have the
     * ohos.permission.START_ABILITIES_FROM_BACKGROUND permission.
     * - If **exported** of the target ability is **false** in cross-application scenarios, the caller must have the
     * ohos.permission.START_INVISIBLE_ABILITY permission.
     * - The rules for using this API in the same-device and cross-device scenarios are different. For details, see
     * [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @permission ohos.permission.ABILITY_BACKGROUND_COMMUNICATION and ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } want - Information about the ability to start, including **abilityName**, **moduleName**,
     *     **bundleName**, **deviceId** (optional), and **parameters** (optional). If **deviceId** is left blank or null,
     *     the local ability is started. If **parameters** is left blank or null, the ability is started in the
     *     background.
     * @param { number } accountId - ID of the target system account. The value **-1** indicates the current user.
     * @returns { Promise<Caller> } Promise used to return the caller object to communicate with.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000013 - The application is controlled by EDM.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 10
     */
    startAbilityByCallWithAccount(want: Want, accountId: number): Promise<Caller>;
    /**
     * Starts an ability. If the ability has multiple instances, the latest instance is started. This API can be called
     * only on the main thread. It uses an asynchronous callback to return the result.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } want - Want information about the target ability.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is started, **err** is
     *     **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 10]
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api. [since 14]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startRecentAbility(want: Want, callback: AsyncCallback<void>): void;
    /**
     * Starts an ability. If the ability has multiple instances, the latest instance is started. This API can be called
     * only on the main thread. It uses an asynchronous callback to return the result.
     *
     * You can use this API to carry start options.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } want - Want information about the target ability.
     * @param { StartOptions } options - Parameters used for starting the ability.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the ability is started, **err** is
     *     **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type. [since 9 - 9]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is
     *     forbidden. [since 9 - 9]
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 10]
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api. [since 14]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startRecentAbility(want: Want, options: StartOptions, callback: AsyncCallback<void>): void;
    /**
     * Starts an ability. If the ability has multiple instances, the latest instance is started. This API uses a promise
     * to return the result asynchronously. It can be called only on the main thread.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } want - Want information about the target ability.
     * @param { StartOptions } [options] - Parameters used for starting the ability.
     * @returns { Promise<void> } The promise returned by the function.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000010 - The call with the continuation and prepare continuation flag is forbidden.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16000053 - The ability is not on the top of the UI.
     * @throws { BusinessError } 16000055 - Installation-free timed out.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 10]
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api. [since 14]
     * @throws { BusinessError } 16000071 - App clone is not supported. [since 14]
     * @throws { BusinessError } 16000072 - App clone or multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000073 - The app clone index is invalid. [since 14]
     * @throws { BusinessError } 16000076 - The app instance key is invalid. [since 14]
     * @throws { BusinessError } 16000077 - The number of app instances reaches the limit. [since 14]
     * @throws { BusinessError } 16000078 - The multi-instance is not supported. [since 14]
     * @throws { BusinessError } 16000079 - The APP_INSTANCE_KEY cannot be specified. [since 14]
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported. [since 14]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 9
     */
    startRecentAbility(want: Want, options?: StartOptions): Promise<void>;
    /**
     * Requests the specified focused application to start the UIExtensionAbility of the corresponding type. The focused
     * application is specified by **bundleName** in **want.parameters**. If **bundleName** is left unspecified, or if the
     * specified application does not gain focus, the UIExtensionAbility is directly started on the system UI. The
     * UIExtensionAbility to start is determined by the combination of the **bundleName**, **abilityName**, and
     * **moduleName** fields in **Want**, and its type is determined by the **ability.want.params.uiExtensionType** field
     * in **want.parameters**. This API can be called only on the main thread. It uses an asynchronous callback to return
     * the result.
     *
     * Before starting the UIExtensionAbility, ensure that the focused application has finished page initialization.
     * Otherwise, the UIExtensionAbility fails to start. The application can determine the time to start the
     * UIExtensionAbility by listening for the page loading status.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } pickerWant - Want information used to start the UIExtensionAbility.
     * @param { AsyncCallback<void> } callback - Callback used to return the result. If the UIExtensionAbility is started,
     *     **err** is **undefined**; otherwise, **err** is an error object.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 11 - 11]
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist. [since 11 - 11]
     * @throws { BusinessError } 16000002 - Incorrect ability type. [since 11 - 11]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 11 - 11]
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released. [since 11 - 11]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 11
     */
    requestModalUIExtension(pickerWant: Want, callback: AsyncCallback<void>): void;
    /**
     * Requests the specified focused application to start the UIExtensionAbility of the corresponding type. The focused
     * application is specified by **bundleName** in **want.parameters**. If **bundleName** is left unspecified, or if the
     * specified application does not gain focus, the UIExtensionAbility is directly started on the system UI. The
     * UIExtensionAbility to start is determined by the combination of the **bundleName**, **abilityName**, and
     * **moduleName** fields in **Want**, and its type is determined by the **ability.want.params.uiExtensionType** field
     * in **want.parameters**. This API can be called only on the main thread. It uses a promise to return the result
     * asynchronously.
     *
     * Before starting the UIExtensionAbility, ensure that the focused application has finished page initialization.
     * Otherwise, the UIExtensionAbility fails to start. The application can determine the time to start the
     * UIExtensionAbility by listening for the page loading status.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } pickerWant - Want information used to start the UIExtensionAbility.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface. [since 11 - 11]
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16000001 - The specified ability does not exist. [since 11 - 11]
     * @throws { BusinessError } 16000002 - Incorrect ability type. [since 11 - 11]
     * @throws { BusinessError } 16000004 - Cannot start an invisible component. [since 11 - 11]
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released. [since 11 - 11]
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 11
     */
    requestModalUIExtension(pickerWant: Want): Promise<void>;
    /**
     * Requests the specified focused application to start the UIExtensionAbility of the corresponding type for the
     * specified user. The focused application is specified by **bundleName** in **want.parameters**. If **bundleName**
     * is left unspecified, or if the specified application does not gain focus, the UIExtensionAbility is directly
     * started on the system UI. The UIExtensionAbility to start is determined by the combination of the **bundleName**,
     * **abilityName**, and **moduleName** fields in **Want**, and its type is determined by the
     * **ability.want.params.uiExtensionType** field in **want.parameters**. This API can be called only on the main thread.
     * It uses a promise to return the result asynchronously.
     *
     * Before starting the UIExtensionAbility, ensure that the focused application has finished page initialization.
     * Otherwise, the UIExtensionAbility fails to start. The application can determine the time to start the
     * UIExtensionAbility by listening for the page loading status.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @permission ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS
     * @param { Want } pickerWant - Want information used to start the UIExtensionAbility.
     * @param { number } accountId - The account to request.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 16000050 - Internal error. Possible causes: 1.Connect to system service failed;
     *     2.Send restart message to system service failed; 3.System service failed to communicate with dependency module.
     *     4.The logical screen corresponding to the specified accountId is not in the foreground.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 26.0.0
     */
    requestModalUIExtensionWithAccount(pickerWant: Want, accountId: number): Promise<void>;
    /**
     * Starts an atomic service and pre-opens the window, with the loading box skipped. This API uses a promise to return
     * the result.
     *
     * If parameter verification is successful but the atomic service fails to start, you need to implement an exception
     * mechanism to capture the error.
     *
     * @permission ohos.permission.PRE_START_ATOMIC_SERVICE
     * @param { string } bundleName - Bundle name of the atomic service.
     * @param { string } moduleName - Module name of the atomic service.
     * @param { string } abilityName - Ability name of the atomic service.
     * @param { string } startTime - Start time to open the atomic service, in milliseconds.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 16300007 - The target free-installation task does not exist.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 12
     */
    preStartMission(bundleName: string, moduleName: string, abilityName: string, startTime: string): Promise<void>;
    /**
     * Starts a new
     * [UIServiceExtensionAbility]{@link ./../@ohos.app.ability.UIServiceExtensionAbility:UIServiceExtensionAbility}. This
     * API uses a promise to return the result asynchronously.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Want } want - Indicates the want info to start.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - The application is not system-app, can not use system-api.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1. Mandatory parameters are left unspecified;
     *     2. Incorrect parameter types; 3. Parameter verification failed.
     * @throws { BusinessError } 801 - Capability not supported.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000013 - The application is controlled by EDM.
     * @throws { BusinessError } 16000019 - No matching ability is found.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 14
     */
    startUIServiceExtensionAbility(want: Want): Promise<void>;
    /**
     * Starts an atomic service based on an application ID. This API uses a promise to return the result asynchronously.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { string } appId - Unique ID of the application, which is allocated by the cloud.
     * @param { AtomicServiceOptions } [options] - Parameter carried in the request for starting the atomic service in
     *     jump-out mode.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 401 - Parameter error. Possible causes: 1.Mandatory parameters are left unspecified.
     *     2.Incorrect parameter types.
     * @throws { BusinessError } 16000002 - Incorrect ability type.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000012 - The application is controlled.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 18
     */
    openAtomicService(appId: string, options?: AtomicServiceOptions): Promise<void>;
    /**
     * Starts multiple UIAbility components simultaneously. This API uses a promise to return the result asynchronously.
     *
     * You can pass the Want information of multiple UIAbility instances, which can point to one or more applications. If
     * all the UIAbility instances can be started successfully, the system displays these UIAbility instances in multiple
     * windows simultaneously. Depending on the window handling, different devices may have varying display effects (
     * including window shape, quantity, and layout).
     *
     * This API can be properly called on phones and tablets. If it is called on other devices, error code 801 is
     * returned.
     *
     * > **NOTE**
     * >
     * > For details about the startup rules for the components in the stage model, see
     * > [Component Startup Rules (Stage Model)](docroot://application-models/component-startup-rules.md).
     *
     * @param { Array<Want> } wantList - List of launch parameters for multiple UIAbility components to be started
     *     simultaneously. A maximum of four Want objects can be passed. The **Want** parameter does not support implicit
     *     launch, cross-user launch, distributed launch, instant installation, or on-demand loading. By default, the main
     *     application is launched unless specified otherwise.
     * @returns { Promise<void> } Promise that returns no value.
     * @throws { BusinessError } 201 - The application does not have permission to call the interface.
     * @throws { BusinessError } 202 - Not system application.
     * @throws { BusinessError } 801 - Capability not supported.
     * @throws { BusinessError } 16000001 - The specified ability does not exist.
     * @throws { BusinessError } 16000004 - Cannot start an invisible component.
     * @throws { BusinessError } 16000005 - The specified process does not have the permission.
     * @throws { BusinessError } 16000006 - Cross-user operations are not allowed.
     * @throws { BusinessError } 16000008 - The crowdtesting application expires.
     * @throws { BusinessError } 16000009 - An ability cannot be started or stopped in Wukong mode.
     * @throws { BusinessError } 16000011 - The context does not exist.
     * @throws { BusinessError } 16000050 - Internal error.
     * @throws { BusinessError } 16200001 - The caller has been released.
     * @throws { BusinessError } 16000073 - The app clone index is invalid.
     * @throws { BusinessError } 16000076 - The app instance key is invalid.
     * @throws { BusinessError } 16000080 - Creating a new instance is not supported.
     * @throws { BusinessError } 16000120 - A maximum of four UIAbility instances can be started simultaneously.
     *     The current parameter exceeds the maximum number or is less than 1.
     * @throws { BusinessError } 16000121 - The target component type is not a UIAbility.
     * @throws { BusinessError } 16000122 - The target component is blocked by the system module and
     *     does not support startup.
     * @throws { BusinessError } 16000123 - Implicit startup is not supported.
     * @throws { BusinessError } 16000124 - Starting a remote UIAbility is not supported.
     * @throws { BusinessError } 16000125 - Starting a plugin UIAbility is not supported.
     * @throws { BusinessError } 16000126 - Starting DLP files is not supported.
     * @syscap SystemCapability.Ability.AbilityRuntime.Core
     * @systemapi
     * @stagemodelonly
     * @since 20
     */
    startUIAbilities(wantList: Array<Want>): Promise<void>;
}
export default ServiceExtensionContext;
