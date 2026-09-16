const labels: Record<string, string> = {
  queued: '排队中', running: '执行中', validating: '校验中', waiting: '等待任务结束', applying: '正在生效',
  succeeded: '已成功', failed: '失败', cancelled: '已取消', needs_recovery: '需要恢复核对', interrupted: '已中断，待核对',
  ready: '就绪', unhealthy: '异常', stopped: '已停止', creating: '创建中', missing: '容器缺失', absent: '容器不存在',
  idle: '空闲', busy: '忙碌', unknown: '未知', complete: '完成', prepare: '准备',
  'models.apply': '发布模型网关', 'agent.apply': '发布 Agent', 'agent.delete': '删除 Agent',
  'agent.archive': '归档 Agent', 'agent.delete-empty': '删除未发布 Agent',
  'sandbox.start': '启动沙箱', 'sandbox.stop': '停止沙箱', 'sandbox.restart': '重启沙箱',
  'sandbox.destroy': '销毁沙箱容器', destroyed: '已销毁 · 按需重建', on_demand: '按需创建',
};
export const operationLabel = (value: unknown) => labels[String(value)] || String(value || '未知');
export function localTime(value: unknown) {
  if (value == null || value === '') return '未记录';
  const date = new Date(typeof value === 'number' ? value * 1000 : String(value));
  return Number.isNaN(date.getTime()) ? '未记录' : date.toLocaleString('zh-CN', { hour12: false });
}
