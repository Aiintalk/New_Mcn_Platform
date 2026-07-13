// Types for 直播脚本仿写工具（livestream-writer）

export interface Persona {
  id: number;
  name: string;
  soul: string;
  contentPlan: string;
}

export interface LivestreamWriterConfig {
  generate_prompt: string;
  iterate_prompt: string;
  model_id: string;
}

export interface ParseFileResponse {
  text: string;
  filename: string;
}

export interface ChatRequest {
  messages: Array<{ role: 'user' | 'assistant'; content: string }>;
  systemPrompt: string;
  model?: string;
  workspace_mode?: boolean;
  kol_id?: number;
  reference_script?: string;
  reference_confirmed?: boolean;
  sp_order?: SpOrder;
  createJob?: boolean;
  jobContext?: {
    productName: string;
    personaName: string;
    spOrder: string;
    refLength: number;
  };
}

export type SpOrder = '背书→机制→种草' | '机制→背书→种草' | '种草→背书→机制';

export type Step = 1 | 2 | 3 | 4;

export interface StepState {
  // Step 1
  selectedPersona: Persona | null;
  // Step 2
  sellingPoints: string;
  productName: string;
  spOrder: SpOrder;
  // Step 3
  refScript: string;
  refScriptLocked: boolean;
  // Step 4
  chatMessages: Array<{ role: 'user' | 'assistant'; content: string }>;
  isStreaming: boolean;
  currentStep: Step;
}
