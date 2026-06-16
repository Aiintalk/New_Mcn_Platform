/**
 * 前端规范守卫 — 红线 #3: API 调用必须走 request.ts
 *
 * 扫描 src/api/*.ts（排除 request.ts 自身），检查是否有裸 fetch() 调用。
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
import { readFileSync, readdirSync } from 'fs'
import { join, resolve } from 'path'

const API_DIR = resolve(process.cwd(), 'src', 'api')

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

function findFetchViolations(): FetchViolation[] {
  const violations: FetchViolation[] = []

  let files: string[]
  try {
    files = readdirSync(API_DIR)
      .filter((f) => f.endsWith('.ts') && f !== 'request.ts')
  } catch {
    return [{ file: '(api-dir)', line: 0, context: `无法读取目录 ${API_DIR}` }]
  }

  for (const file of files) {
    const content = readFileSync(join(API_DIR, file), 'utf-8')
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
          file,
          line: i + 1,
          context: trimmed.substring(0, 80),
        })
      }
    }
  }

  return violations
}

describe('红线 #3: API 调用必须走 request.ts', () => {
  it('src/api/*.ts 中不应有未经例外的裸 fetch() 调用', () => {
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
