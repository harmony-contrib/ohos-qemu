/*
 * Copyright (c) 2025 Huawei Device Co., Ltd.
 * Licensed under the Apache License, Version 2.0 (the "License");
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

#ifndef __IMEDIA_API_H__
#define __IMEDIA_API_H__

#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef USE_IMEDIA_INNER_API

// Redefinition of 8-bit data types
typedef unsigned char IMEDIA_UINT8;
typedef signed char IMEDIA_INT8;
typedef char IMEDIA_CHAR;  // Redefinition for 8-bit data type, compatible with uniDSP header files

// 16-bit
typedef unsigned short IMEDIA_UINT16;
typedef signed short IMEDIA_INT16;

// 32-bit
typedef unsigned int IMEDIA_UINT32;
typedef signed int IMEDIA_INT32;
typedef unsigned int IMEDIA_BOOL;  // Redefinition for 32-bit data type, compatible with uniDSP header files

#ifndef IMEDIA_VOID
#define IMEDIA_VOID void
#endif

// Algorithm processing frame length: 480 samples
#define IMEDIA_SWS_FRAME_LEN (480)

// Error code definitions
#define IMEDIA_SWS_EOK (0)  // Normal

#define IMEDIA_SWS_EQ_BANDS (12)  // Maximum number of frequency bands for PEQ module
#define IMEDIA_SWS_VERLEN (64)    // Length of version information and release date strings for algorithm library

#define COEFFICIENT 10
#define OFFSET 100
#define EQ_BANDS 10
#define CHANNEL 2
#define ONE_BYTE_OFFSET 8
#define LBA_OFFSET 14

// Memory size structure
typedef struct tagSTRU_IMEDIA_SWS_MEM_SIZE {
    IMEDIA_INT32 iStrSize;      // Channel size
    IMEDIA_INT32 iScracthSize;  // Scratch buffer size
    IMEDIA_INT32 iReserve[4];   // Reserved area
} iMedia_SWS_MEM_SIZE;

// Data structure
typedef struct tagSTRU_IMEDIA_SWS_DATA {
    IMEDIA_INT32 *piDataIn;       // Input data address
    IMEDIA_INT32 *piDataOut;      // Output data address
    IMEDIA_INT32 iSize;           // Input data length
    IMEDIA_INT32 iEnable_SWS;     // SWS enable flag
    IMEDIA_INT32 iData_Format16;  // 1:16bit 0:24bit 2:32bit
    IMEDIA_INT32 iMasterVolume;   // Master key volume gain
    IMEDIA_INT32 iData_Channel;   // Number of input audio channels
    IMEDIA_INT32 iData_Reserve;   // 8-byte alignment padding
} iMedia_SWS_DATA;

// Version structure
typedef struct tagSTRU_IMEDIA_SWS_VERSION {
    IMEDIA_INT8 ucCgtVersion[IMEDIA_SWS_VERLEN];   // Compiler version number
    IMEDIA_INT8 ucReleaseVer[IMEDIA_SWS_VERLEN];   // Algorithm library version number
    IMEDIA_INT8 ucReleaseTime[IMEDIA_SWS_VERLEN];  // Release date
} iMedia_SWS_STRU_VERSION, *iMedia_SWS_PST_VERSION;
#endif

// Sound field configuration parameters
typedef enum tagEnum_IMEDIA_Surround_PARA {
    IMEDIA_SWS_SOUROUND_BROAD = 0,          // Broad
    IMEDIA_SWS_SOUROUND_FRONT = 1,          // Front
    IMEDIA_SWS_SOUROUND_DEFAULT = 2,        // Listening
    IMEDIA_SWS_SOUROUND_GRAND = 3           // Grand
} iMedia_Surround_PARA;

typedef struct tagSTRU_IMEDIA_Support_SPECS {
    bool isSupport;
    bool isRealTime;
    uint32_t frameLen;
    uint32_t inSampleRate;
    uint32_t inChannels;
    uint32_t inFormat;
    uint32_t outSampleRate;
    uint32_t outChannels;
    uint32_t outFormat;
} iMedia_Support_SPECS;

// Sound field algorithm configurations
#define AUDIO_SURROUND_ENABLE_SWS           (1)    // SWS enabled by default
#define AUDIO_SURROUND_MASTER_VOLUME        (15)   // Default volume gain: 15
#define AUDIO_SURROUND_PCM_16_BIT           (1)    // Supported bit depth for sound field algorithm: 16bits
#define AUDIO_SURROUND_PCM_48K_FRAME_LEN    (480)  // Processing frame length (samples per frame): 480
#define AUDIO_SURROUND_PCM_CHANNEL_NUM      (2)    // Supported channels: stereo (2)

extern IMEDIA_INT32 iMedia_Surround_GetSize(iMedia_SWS_MEM_SIZE *pMemSize);

extern IMEDIA_INT32 iMedia_Surround_Init(IMEDIA_VOID *pHandle, IMEDIA_VOID *pScratchBuf, IMEDIA_INT32 iScratchBufLen,
    const iMedia_Surround_PARA surroundType);

extern IMEDIA_INT32 iMedia_Surround_Apply(
    IMEDIA_VOID *pHandle, IMEDIA_VOID *pScratchBuf, IMEDIA_INT32 iScratchBufLen, iMedia_SWS_DATA *pData);

extern IMEDIA_INT32 iMedia_Surround_SetParams(IMEDIA_VOID *pHandle, IMEDIA_VOID *pScratchBuf,
    IMEDIA_INT32 iScratchBufLen, const iMedia_Surround_PARA surroundType);

extern IMEDIA_INT32 iMedia_Surround_GetParams(IMEDIA_VOID *pHandle, iMedia_Surround_PARA *pSurroundType);

typedef struct tagSTRU_IMEDIA_Eq_PARA {
    IMEDIA_INT16 sFrameLen;  // Frame length (samples), e.g., 480;
    IMEDIA_INT16 sEQLRBands;
    IMEDIA_INT16 sEQLRType[IMEDIA_SWS_EQ_BANDS];
    IMEDIA_INT16 sEQLRGain[IMEDIA_SWS_EQ_BANDS];
} iMedia_Eq_PARA;

extern IMEDIA_INT32 iMedia_Eq_GetSize(iMedia_SWS_MEM_SIZE *pMemSize);

extern IMEDIA_INT32 iMedia_Eq_Init(
    IMEDIA_VOID *pHandle, IMEDIA_VOID *pScratchBuf, IMEDIA_INT32 iScratchBufLen, const iMedia_Eq_PARA *pParams);

extern IMEDIA_INT32 iMedia_Eq_Apply(
    IMEDIA_VOID *pHandle, IMEDIA_VOID *pScratchBuf, IMEDIA_INT32 iScratchBufLen, iMedia_SWS_DATA *pData);

extern IMEDIA_INT32 iMedia_Eq_SetParams(
    IMEDIA_VOID *pHandle, IMEDIA_VOID *pScratchBuf, IMEDIA_INT32 iScratchBufLen, const iMedia_Eq_PARA *pParams);

extern IMEDIA_INT32 iMedia_Eq_GetParams(IMEDIA_VOID *pHandle, iMedia_Eq_PARA *pParams);

extern IMEDIA_INT32 iMedia_Eq_GetVersion(iMedia_SWS_PST_VERSION *ppVersion);

// Environmental sound configuration parameters
typedef enum tagEnum_IMEDIA_Env_PARA {
    IMEDIA_SWS_ENV_UNKNOW = -1,
    IMEDIA_SWS_ENV_BROADCAST = 0,
    IMEDIA_SWS_ENV_TELEPHONE_RECEIVER = 1,
    IMEDIA_SWS_ENV_UNDER_WATER = 2,
    IMEDIA_SWS_ENV_PHONOGRAPH = 3,
    IMEDIA_SWS_ENV_TYPE_NUM
} iMedia_Env_PARA;

#ifdef __cplusplus
}
#endif

#endif
