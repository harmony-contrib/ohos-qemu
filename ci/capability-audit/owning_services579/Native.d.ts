export interface NativeCallback { rc: number; level: number; kind: string; ns: string; identity_hex: string; }
export interface NativeResult { action: string; argument: string; data: string; rc: number; value: number;
 uid: number; pid: number; account: number; begin_ns: string; end_ns: string; token: string;
 napi_status: number; output_eof: boolean; output_errno: number; callbacks: NativeCallback[]; }
export const execute: (action: string, argument: string, account: number, output: string) => Promise<NativeResult>;
