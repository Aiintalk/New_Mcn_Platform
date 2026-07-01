/**
 * OutputHistoryDrawer — 可复用的产出历史抽屉
 *
 * 用于 operator 工具页内嵌「历史记录」抽屉，按 tool_code 过滤全局 outputs。
 * 支持：分页拉取、删除（软删，调全局 DELETE /outputs/:id）、自定义渲染。
 *
 * 使用方：
 *   <OutputHistoryDrawer
 *     toolCode="values-writer"
 *     toolName="价值观仿写"
 *     open={open}
 *     onClose={onClose}
 *   />
 */
import { useEffect, useState, useCallback } from 'react';
import { Drawer, List, Button, Tag, App, Spin, Empty, Typography } from 'antd';
import { getOutputs, deleteOutput } from '../api/outputs';
import type { Output } from '../types/output';

const { Paragraph, Text } = Typography;

export interface OutputHistoryDrawerProps {
  /** 工具 code，用于过滤全局 outputs（如 "values-writer"） */
  toolCode: string;
  /** 工具展示名（用于抽屉标题、空态文案） */
  toolName: string;
  open: boolean;
  onClose: () => void;
  /** 自定义单项渲染；不传则默认显示标题 + content 预览 */
  renderItem?: (output: Output) => React.ReactNode;
}

const PAGE_SIZE = 10;

export default function OutputHistoryDrawer({
  toolCode,
  toolName,
  open,
  onClose,
  renderItem,
}: OutputHistoryDrawerProps) {
  const { message, modal } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<Output[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const fetchPage = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const result = await getOutputs({ tool_code: toolCode, page: p, page_size: PAGE_SIZE });
      setItems(result.items ?? []);
      setTotal(result.pagination?.total ?? 0);
      setPage(p);
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '加载历史失败');
    } finally {
      setLoading(false);
    }
  }, [toolCode, message]);

  useEffect(() => {
    if (open) {
      fetchPage(1);
    }
  }, [open, fetchPage]);

  async function handleDelete(id: number) {
    modal.confirm({
      title: '确认删除？',
      content: '删除后不可恢复。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteOutput(id);
          message.success('已删除');
          // 重新拉当前页（若删的是最后一项会自动回到合适合页）
          await fetchPage(page);
        } catch (err: unknown) {
          message.error(err instanceof Error ? err.message : '删除失败');
        }
      },
    });
  }

  return (
    <Drawer
      title={`${toolName} · 历史记录`}
      open={open}
      onClose={onClose}
      width={560}
      destroyOnClose
    >
      <Spin spinning={loading}>
        {items.length === 0 && !loading ? (
          <Empty description={`暂无${toolName}历史`} />
        ) : (
          <List
            dataSource={items}
            pagination={{
              current: page,
              total,
              pageSize: PAGE_SIZE,
              onChange: (p) => fetchPage(p),
              showTotal: (t) => `共 ${t} 条`,
              size: 'small',
            }}
            renderItem={(item) => (
              <List.Item
                key={item.id}
                actions={[
                  <Button
                    key="delete"
                    type="link"
                    danger
                    size="small"
                    onClick={() => handleDelete(item.id)}
                  >
                    删除
                  </Button>,
                ]}
              >
                {renderItem ? (
                  renderItem(item)
                ) : (
                  <div style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <Text strong>{item.title || `#${item.id}`}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {new Date(item.created_at).toLocaleString('zh-CN')}
                      </Text>
                    </div>
                    {item.word_count != null && (
                      <Tag style={{ marginBottom: 6 }}>{item.word_count} 字</Tag>
                    )}
                    <Paragraph
                      type="secondary"
                      ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                      style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
                    >
                      {item.content ?? ''}
                    </Paragraph>
                  </div>
                )}
              </List.Item>
            )}
          />
        )}
      </Spin>
    </Drawer>
  );
}
