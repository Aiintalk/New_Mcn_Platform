/**
 * exportXmind — 客户端生成 .xmind 文件（XMind 8/Zen 兼容格式）
 *
 * .xmind 文件本质是一个 ZIP，包含：
 * - content.json：核心数据（topic 树）
 * - metadata.json：创建者信息
 * - Thumbnails/（可选，缩略图）
 *
 * 参考：XMind 2022/Zen 的 content.json schema（rootTopic.children.attached 数组）
 *
 * 移植自旧架构服务端 `/api/mindmap/export`，改为纯前端实现（避免新增后端端点）。
 */
import JSZip from 'jszip';
import type { MindmapResult } from '../../../api/subtitle';

interface XmindTopic {
  id: string;
  title: string;
  children?: {
    attached: XmindTopic[];
  };
}

interface XmindSheet {
  id: string;
  title: string;
  rootTopic: XmindTopic;
}

let idCounter = 0;
function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}_${Date.now().toString(36)}_${idCounter}`;
}

function branchToTopics(title: string, childTexts: string[]): XmindTopic {
  const topic: XmindTopic = {
    id: nextId('branch'),
    title,
  };
  if (childTexts.length > 0) {
    topic.children = {
      attached: childTexts.map((text) => ({
        id: nextId('child'),
        title: text,
      })),
    };
  }
  return topic;
}

function buildContent(mindmap: MindmapResult): { sheets: XmindSheet[] } {
  const rootTopic: XmindTopic = {
    id: nextId('root'),
    title: mindmap.rootTitle,
    children: {
      attached: mindmap.branches.map((b) =>
        branchToTopics(b.title, b.children || []),
      ),
    },
  };

  // summary 放到根 topic 的 notes（XMind notes 字段）
  if (mindmap.summary) {
    // XMind 8 schema: rootTopic.notes.plain.content
    (rootTopic as unknown as { notes?: { plain?: { content: string } } }).notes = {
      plain: { content: mindmap.summary },
    };
  }

  return {
    sheets: [
      {
        id: nextId('sheet'),
        title: '思维导图',
        rootTopic,
      },
    ],
  };
}

/**
 * 把 MindmapResult 转换为 .xmind 文件 Blob。
 *
 * @param mindmap AI 生成的思维导图结果
 * @returns 可用于下载的 Blob（application/zip）
 */
export async function exportXmind(mindmap: MindmapResult): Promise<Blob> {
  const zip = new JSZip();
  const content = buildContent(mindmap);

  zip.file('content.json', JSON.stringify(content));
  zip.file(
    'metadata.json',
    JSON.stringify({
      creator: {
        name: 'mcn-platform',
        version: '1.0.0',
      },
    }),
  );

  return zip.generateAsync({
    type: 'blob',
    mimeType: 'application/zip',
    compression: 'DEFLATE',
  });
}

// 也导出 buildContent 供测试直接验证结构（不依赖 Blob.arrayBuffer）
export { buildContent };
