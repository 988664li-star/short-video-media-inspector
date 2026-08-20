export type ReplicaPlatform = "douyin" | "tiktok";
export type ReplicaRightsMode = "structure" | "licensed_v2v";

export interface ReplicaProjectInput {
  id?: string;
  name: string;
  product_name: string;
  platform: ReplicaPlatform;
  market: string;
  audience: string;
  landing_page: string;
  target_cpa: number | null;
  brand_facts: string;
  prohibited_claims: string;
  rights_mode: ReplicaRightsMode;
  rights_confirmed: boolean;
  aigc_label_required: boolean;
}

export interface ReplicaProject extends Required<Omit<ReplicaProjectInput, "id" | "target_cpa">> {
  id: string;
  target_cpa: number | null;
  created_at: number;
  updated_at: number;
}
