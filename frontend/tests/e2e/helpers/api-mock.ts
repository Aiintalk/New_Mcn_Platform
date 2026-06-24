import type { Page, Route } from '@playwright/test';

/**
 * E2E 测试用外部 API mock 工具。
 *
 * 真实调用 yunwu/tikhub/oss/asr 会让测试慢且依赖外部凭证，
 * 通过 page.route() 拦截这些请求，返回固定 mock 响应。
 *
 * 原则：mock 在网络层（请求未发出），不打应用代码。
 */

/** 阿里云 OSS 上传 mock：返回一个公网 URL。 */
export async function mockOssUpload(page: Page) {
  await page.route('**/api/tools/seeding-writer/products/parse-document', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        code: 'OK',
        message: 'success',
        data: {
          _rawText: 'MOCK 产品文档解析内容',
          product_name: 'MOCK 精华液',
          selling_points: ['保湿', '提亮'],
          source_format: 'txt',
        },
      }),
    });
  });
}

/** 卖点流式（SSE）mock：返回 3 个卖点。 */
export async function mockSellingPointsStream(page: Page) {
  await page.route('**/api/tools/seeding-writer/products/extract-selling-points', async (route) => {
    const sseBody = [
      'data: {"delta":"MOCK 卖点1"}\n\n',
      'data: {"delta":"MOCK 卖点2"}\n\n',
      'data: {"delta":"MOCK 卖点3"}\n\n',
      'data: [DONE]\n\n',
    ].join('');
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: sseBody,
    });
  });
}

/** 抖音视频解析 mock：返回视频 URL + 音频 URL。 */
export async function mockFetchVideo(page: Page) {
  await page.route('**/api/tools/seeding-writer/fetch-video', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        code: 'OK',
        message: 'success',
        data: {
          video_url: 'https://mock.example.com/video.mp4',
          audio_url: 'https://mock.example.com/audio.mp3',
          title: 'MOCK 抖音视频',
          author: 'MOCK 达人',
        },
      }),
    });
  });
}

/** ASR submit mock：返回 task_id。 */
export async function mockAsrSubmit(page: Page) {
  await page.route('**/api/tools/seeding-writer/transcribe/submit', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        code: 'OK',
        message: 'success',
        data: { task_id: 'mock-asr-task-001', status: 'RUNNING' },
      }),
    });
  });
}

/** ASR poll mock：第 1 次 RUNNING，第 2 次 SUCCESS 返回文本。 */
export async function mockAsrPoll(page: Page) {
  let callCount = 0;
  await page.route('**/api/tools/seeding-writer/transcribe/poll', async (route) => {
    callCount++;
    const statusText = callCount === 1 ? 'RUNNING' : 'SUCCESS';
    const data: Record<string, unknown> = { task_id: 'mock-asr-task-001', status: statusText };
    if (statusText === 'SUCCESS') {
      data.transcript = 'MOCK 转写文本：这是抖音视频的口播内容。';
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, code: 'OK', message: 'success', data }),
    });
  });
}

/** 结构拆解流式（SSE）mock。 */
export async function mockAnalyzeStructureStream(page: Page) {
  await page.route('**/api/tools/seeding-writer/analyze-structure', async (route) => {
    const sseBody = [
      'data: {"delta":"MOCK 钩子"}\n\n',
      'data: {"delta":"MOCK 痛点"}\n\n',
      'data: {"delta":"MOCK 卖点"}\n\n',
      'data: [DONE]\n\n',
    ].join('');
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: sseBody,
    });
  });
}

/** AI 推荐 + 写作/迭代流式 mock。 */
export async function mockChatStream(page: Page) {
  await page.route('**/api/tools/seeding-writer/chat', async (route) => {
    const sseBody = [
      'data: {"delta":"MOCK "}\n\n',
      'data: {"delta":"种草 "}\n\n',
      'data: {"delta":"文案 "}\n\n',
      'data: {"delta":"内容"}\n\n',
      'data: [DONE]\n\n',
    ].join('');
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: sseBody,
    });
  });
}

/** 一键安装所有 mock（推荐每个测试用例 setup 时调用）。 */
export async function installAllMocks(page: Page) {
  await Promise.all([
    mockOssUpload(page),
    mockSellingPointsStream(page),
    mockFetchVideo(page),
    mockAsrSubmit(page),
    mockAsrPoll(page),
    mockAnalyzeStructureStream(page),
    mockChatStream(page),
  ]);
}

/** 默认通过的非外部 API（GET kols/products/references/outputs 等）— 不 mock。 */
export async function passthroughApi(page: Page) {
  // 占位：默认 page 不拦截 GET 请求，让它们打到后端
  return page;
}

/** 类型小工具：从 Route 取请求体 JSON。 */
export async function readRouteBody(route: Route): Promise<unknown> {
  const request = route.request();
  const body = request.postData();
  if (!body) return null;
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}
