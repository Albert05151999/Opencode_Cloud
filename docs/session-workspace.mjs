// Install as an Agent Hook to give native tools a per-session default directory.
import {mkdir, realpath} from 'node:fs/promises';
import path from 'node:path';

export default async ({directory}) => {
  const root = await realpath(directory);
  return {
    'tool.execute.before': async (input, output) => {
      if (!['bash', 'read', 'write', 'edit', 'glob', 'grep'].includes(input.tool)) return;
      if (!/^ses_[A-Za-z0-9_-]+$/.test(input.sessionID || '')) {
        throw new Error('Missing or invalid platform session ID');
      }
      const sessions = path.join(root, 'sessions');
      const session = path.join(sessions, input.sessionID);
      // Check each directory before creating its children, including old sessions.
      for (const dir of [sessions, session, path.join(session, 'inputs'), path.join(session, 'outputs')]) {
        await mkdir(dir, {recursive: true});
        if (await realpath(dir) !== dir) throw new Error('Session directory must not be a symlink');
      }
      const key = input.tool === 'bash' ? 'workdir'
        : ['read', 'write', 'edit'].includes(input.tool) ? 'filePath' : 'path';
      const value = output.args[key];
      if (value === undefined && key === 'filePath') return;
      const resolved = !value || value === root ? session : path.resolve(session, value);
      // Catch mistyped IDs rather than silently writing to a different session.
      const relative = path.relative(sessions, resolved);
      if (relative && !relative.startsWith('..'+path.sep) && relative !== '..' && !path.isAbsolute(relative)
          && relative.split(path.sep)[0] !== input.sessionID) {
        throw new Error(`Wrong session path. Use exactly ${session}`);
      }
      output.args[key] = resolved;
    },
  };
};
