export type KolStatus = 'signed' | 'pending_renewal' | 'terminated';

export interface Kol {
  id: number;
  name: string;
  platform: string;
  account_name: string;
  douyin_id?: string;
  sec_uid?: string;
  avatar_url?: string;
  followers_count: number;
  works_count: number;
  status: KolStatus;
  owner?: string;
  persona?: string;
  style_note?: string;
  created_at: string;
  updated_at?: string;
}

export interface FansGender {
  male: number;
  female: number;
}

export interface FansAge {
  range: string;
  ratio: number;
}

export interface FansRegion {
  region: string;
  ratio: number;
}

// tikhub_raw.fans_info.data 结构（实际返回格式）
// Gender / Age / Province → JSON 字符串，parse 后为 [{name: string, value: number}]
//   Gender.name: "female" | "male"，value: 0~1 浮点
//   Age.name: 年龄段字符串，value: 0~1 浮点
//   Province.name: 中文省份名，value: 0~1 浮点
// FirstTag → 字符串数组
export interface TikhubFansData {
  Gender?: string;
  Age?: string;
  Province?: string;
  FirstTag?: string[];
}

export interface TikhubRaw {
  fans_info?: {
    data?: TikhubFansData;
  };
  profile?: unknown;
}

export interface KolDetail extends Kol {
  signature?: string;
  tikhub_raw?: TikhubRaw;
  // 旧字段保留兼容
  fans_gender?: FansGender;
  fans_age?: FansAge[];
  fans_region?: FansRegion[];
}

export interface KolListParams {
  page?: number;
  page_size?: number;
  platform?: string;
  status?: string;
  keyword?: string;
}

export interface CreateKolRequest {
  name: string;
  platform: string;
  douyin_id?: string;
  sec_uid?: string;
  owner?: string;
}

export interface UpdateKolRequest {
  name?: string;
  platform?: string;
  douyin_id?: string;
  sec_uid?: string;
  owner?: string;
  status?: KolStatus;
  persona?: string;
  style_note?: string;
}
