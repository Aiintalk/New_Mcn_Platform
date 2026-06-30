// src/api/kolWorkspaceConfig.ts
import { get, put } from './request';
import type { KolWorkspaceConfig, WorkspaceTabCode, ToolCode, ToolPromptFields } from '../types/kolWorkspaceConfig';

export const getKolWorkspaceConfig = (kolId: number) =>
  get<KolWorkspaceConfig>(`/api/admin/kols/${kolId}/workspace-config`);

export const updateKolWorkspaceConfig = (
  kolId: number,
  data: {
    enabled_tabs: WorkspaceTabCode[];
    prompt_overrides: { [K in ToolCode]?: Partial<ToolPromptFields[K]> };
  }
) => put<KolWorkspaceConfig>(`/api/admin/kols/${kolId}/workspace-config`, data);
