// Additional types for Sprint 2

export type ToolStatus = 'online' | 'dev' | 'offline' | 'disabled';

export interface WorkspaceTool {
  tool_code: string;
  tool_name: string;
  category: string;
  status: ToolStatus;
  description: string;
  tags: string[];
  sort_order?: number;
  config?: Record<string, unknown>;
}
