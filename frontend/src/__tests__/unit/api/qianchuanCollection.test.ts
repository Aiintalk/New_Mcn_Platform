/**
 * qianchuanCollection.test.ts
 * 千川爆文合集 API 模块守卫测试（对齐 conventionGuard.test.ts 规范）
 *
 * 验证：
 * 1. JSON 接口（getPersonas/createPersona/deletePersona/getScripts/createScript/deleteScript）
 *    全部走 request.ts 的 get/post/del，不直接调用 fetch()
 * 2. parseFile 为 FormData 例外，允许直接 fetch，且有明确的例外注释标注
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const FILE_PATH = resolve(process.cwd(), 'src', 'api', 'qianchuanCollection.ts');

function readFile(): string {
  return readFileSync(FILE_PATH, 'utf-8');
}

describe('qianchuanCollection API 规范守卫', () => {
  it('getPersonas 使用 request.ts get', () => {
    const content = readFile();
    expect(content).toMatch(/get<[^>]+>\(.*\/personas/);
  });

  it('createPersona 使用 request.ts post', () => {
    const content = readFile();
    expect(content).toMatch(/post<[^>]+>\(.*\/personas/);
  });

  it('deletePersona 使用 request.ts del', () => {
    const content = readFile();
    expect(content).toMatch(/del<[^>]+>\(.*\/personas/);
  });

  it('getScripts 使用 request.ts get', () => {
    const content = readFile();
    expect(content).toMatch(/get<[^>]+>\(.*\/scripts/);
  });

  it('createScript 使用 request.ts post', () => {
    const content = readFile();
    expect(content).toMatch(/post<[^>]+>\(.*\/scripts/);
  });

  it('deleteScript 使用 request.ts del', () => {
    const content = readFile();
    expect(content).toMatch(/del<[^>]+>\(.*\/scripts\//);
  });

  it('parseFile 为 FormData 例外，有明确注释', () => {
    const content = readFile();
    // 必须有 FormData 例外说明
    expect(content).toMatch(/FormData/);
    // 必须有文件解析相关的 fetch 调用
    expect(content).toMatch(/fetch\(.*parse-file/);
  });

  it('parseFile 文件末有 fetch 而非 get/post（FormData 例外合规）', () => {
    const content = readFile();
    // parseFile 函数内使用了原生 fetch
    const parseFnMatch = content.match(/async function parseFile[\s\S]+?^}/m);
    expect(parseFnMatch).not.toBeNull();
    expect(parseFnMatch?.[0]).toMatch(/fetch\(/);
  });
});
