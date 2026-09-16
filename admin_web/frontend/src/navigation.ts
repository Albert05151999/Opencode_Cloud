export const adminTabs = ['logs', 'load-tests', 'transfer', 'sandboxes', 'models', 'agents', 'mcp', 'skill', 'hook', 'jobs', 'connection'];
export function currentAdminTab() {
  const tab = new URLSearchParams(location.search).get('tab');
  return tab && adminTabs.includes(tab) ? tab : 'models';
}
export function navigateTo(path: string) {
  const event = new Event('app-before-navigate', { cancelable: true });
  if (!window.dispatchEvent(event)) return;
  history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}
