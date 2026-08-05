import type { CreateKolRequest, UpdateKolRequest } from '../../types/kol';
import type { PersonaDetailsUpdate } from '../../types/kolWorkspace';

export const validPersonaUpdate: PersonaDetailsUpdate = { persona: '真实、克制' };

// @ts-expect-error 七字段更新每次必须且只能提交一个字段。
export const emptyPersonaUpdate: PersonaDetailsUpdate = {};

// @ts-expect-error 七字段更新不能在同一次请求提交多个字段。
export const multiplePersonaUpdate: PersonaDetailsUpdate = {
  persona: '真实、克制',
  content_plan: '围绕轻熟龄穿搭创作',
};

export const validCreateKol: CreateKolRequest = { name: '测试红人', platform: '抖音' };

export const createKolWithPersona: CreateKolRequest = {
  name: '测试红人',
  platform: '抖音',
  // @ts-expect-error 管理端创建契约不再接受人格档案。
  persona: '不应从管理端写入',
};

export const validUpdateKol: UpdateKolRequest = { owner: '运营甲', style_note: '口语自然' };

export const updateKolWithContentPlan: UpdateKolRequest = {
  owner: '运营甲',
  // @ts-expect-error 管理端更新契约不再接受内容规划。
  content_plan: '不应从管理端写入',
};
