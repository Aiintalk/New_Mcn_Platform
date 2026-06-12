// Types for TikTok 脚本仿写工具

export interface Persona {
  name: string;
  soul: string;
  contentPlan: string;
}

export interface GetPersonasResponse {
  personas: Persona[];
}

export interface ChatRequest {
  messages: Array<{ role: 'user' | 'assistant'; content: string }>;
  systemPrompt: string;
  model?: string;
  createJob?: boolean;
  jobContext?: {
    tiktokUrl: string;
    likesCount: string;
    selectedPersonaName: string;
  };
}

export interface ExportWordRequest {
  personaName: string;
  topic: string;
  content: string;
  taskJobId?: number;
}

export type Step = 1 | 2 | 3 | 4 | 5;

export interface StepState {
  tiktokUrl: string;
  transcript: string;
  likesCount: string;
  selectedPersona: Persona | null;
  hookEvaluation: string;
  hookVerdict: 'PASS' | 'FAIL' | null;
  lockedOpening: string;
  structureAnalysis: string;
  aiBody: string;
  finalBody: string;
  rewriteMode: 'ai' | 'user';
  userIdeas: string;
  chatMessages: Array<{ role: 'user' | 'assistant'; content: string }>;
  isStreaming: boolean;
  currentStep: Step;
}
