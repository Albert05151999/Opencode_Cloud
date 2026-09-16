import { remote } from './api';

export async function waitForPublish(id: string, label = "发布") {
  for (let attempt = 0; attempt < 300; attempt++) {
    const job = await remote(`/cloud/admin/jobs/${id}`);
    if (job.status === 'succeeded') {
      if (job.kind === 'models.apply' || job.kind === 'agent.apply') {
        const catalog = await remote('/cloud/admin/catalog?compact=true');
        const active = job.kind === 'models.apply' ? catalog.gateway_active : catalog.agents[job.target]?.active;
        if (!active || (job.result?.version && active < job.result.version))
          throw Error('任务已结束，但尚未确认生效版本。请刷新发布记录。');
      }
      return job;
    }
    if (['failed', 'cancelled', 'needs_recovery', 'interrupted'].includes(job.status))
      throw Error(`${label}失败：${job.error || job.status}`);
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw Error(`${label}仍在处理中，请在发布记录查看结果；当前尚未确认成功。`);
}
