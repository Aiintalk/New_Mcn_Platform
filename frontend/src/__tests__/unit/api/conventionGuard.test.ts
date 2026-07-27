/**
 * 前端规范守卫 — 红线 #3: API 调用必须走 request.ts
 *
 * 扫描范围：src 下所有 api 子目录里的 .ts 文件（含 src/api 与 src/evaluation/api 等）。
 * 检查：是否存在裸 fetch() 调用（未走 request.ts 的 get/post/put/del）。
 *
 * 例外场景（允许直接使用 fetch）:
 *   - FormData 上传（代码中出现 FormData）
 *   - Blob/文件下载（代码中出现 .blob()）
 *   - SSE 流式（代码中出现 getReader 或 Promise<Response>）
 *
 * 新增 fetch() 调用时，必须满足以上例外之一，否则应改用 request.ts 的 get/post/put/del。
 * 例外函数也必须手动解包 .data（见 CLAUDE.md §12 #3）。
 */
import { describe, it } from 'vitest'
import { readFileSync, readdirSync, statSync, existsSync } from 'fs'
import { join, resolve, relative } from 'path'

const ROOT_DIR = resolve(process.cwd(), 'src')

// fetch() 附近出现以下任一模式时视为合法例外
const EXCEPTION_INDICATORS = [
  'FormData',           // 文件上传
  '.blob()',            // Blob 下载
  'getReader',          // SSE 流式（reader 模式）
  'Promise<Response>',  // SSE 流式（返回原始 Response）
]

// 扫描窗口：fetch() 前 5 行 + 后 15 行
const LOOK_BACK = 5
const LOOK_FORWARD = 15

interface FetchViolation {
  file: string
  line: number
  context: string
}

/** 递归收集所有 src 下 api 子目录里的 .ts 文件（排除 request.ts 自身） */
function collectApiFiles(): string[] {
  const result: string[] = []

  function walk(dir: string) {
    if (!existsSync(dir)) return
    let entries: string[]
    try {
      entries = readdirSync(dir)
    } catch {
      return
    }
    for (const name of entries) {
      const abs = join(dir, name)
      let st
      try {
        st = statSync(abs)
      } catch {
        continue
      }
      if (st.isDirectory()) {
        walk(abs)
      } else if (st.isFile() && name.endsWith('.ts') && name !== 'request.ts') {
        // 只接受路径段包含 /api/ 的文件
        const normalized = abs.replace(/\\/g, '/')
        // 排除测试文件（自身守卫扫描不应触发自己）
        if (normalized.includes('/api/') && !normalized.includes('.test.') && !normalized.includes('/__tests__/')) {
          result.push(abs)
        }
      }
    }
  }

  walk(ROOT_DIR)
  return Array.from(new Set(result))
}

function findFetchViolations(): FetchViolation[] {
  const violations: FetchViolation[] = []
  const files = collectApiFiles()

  if (files.length === 0) {
    return [{ file: '(api-dir)', line: 0, context: `未扫描到任何 .ts 文件（${ROOT_DIR}）` }]
  }

  for (const abs of files) {
    const rel = relative(process.cwd(), abs)
    const content = readFileSync(abs, 'utf-8')
    const lines = content.split('\n')

    for (let i = 0; i < lines.length; i++) {
      // 跳过注释行和 import 行
      const trimmed = lines[i].trim()
      if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('import ')) {
        continue
      }
      if (!lines[i].includes('fetch(')) continue

      // 扫描 fetch() 前 LOOK_BACK 行 + 后 LOOK_FORWARD 行
      const start = Math.max(0, i - LOOK_BACK)
      const end = Math.min(lines.length, i + LOOK_FORWARD + 1)
      const window = lines.slice(start, end).join('\n')

      const hasException = EXCEPTION_INDICATORS.some((p) => window.includes(p))
      if (!hasException) {
        violations.push({
          file: rel,
          line: i + 1,
          context: trimmed.substring(0, 80),
        })
      }
    }
  }

  return violations
}

describe('红线 #3: API 调用必须走 request.ts', () => {
  it('src/api/*.ts 与 src/**/api/*.ts 中不应有未经例外的裸 fetch() 调用', () => {
    const violations = findFetchViolations()

    if (violations.length > 0) {
      const report = violations
        .map((v) => `  - ${v.file}:${v.line}  ${v.context}`)
        .join('\n')

      throw new Error(
        `发现 ${violations.length} 处裸 fetch() 调用。\n` +
          `JSON 调用必须走 request.ts 的 get/post/put/del。\n` +
          `例外（保留原生 fetch + 手动解包 .data）: ` +
          `FormData 上传、Blob 下载、SSE 流式。\n` +
          `(见 CLAUDE.md §12 #3)\n\n${report}`,
      )
    }
  })
})
