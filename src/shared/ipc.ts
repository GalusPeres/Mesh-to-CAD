// IPC channel names between the main process and the preload bridge.

export const IPC = {
  kernelRequest: 'kernel:request',
  kernelCancel: 'kernel:cancel',
  kernelRestart: 'kernel:restart',
  kernelStatus: 'kernel:status',
  kernelGetStatus: 'kernel:getStatus',
  kernelEvent: 'kernel:event',
  filesRun: 'files:run',
  filesDropped: 'files:dropped',
  filesOpenRecent: 'files:openRecent',
  filesReveal: 'files:reveal',
  recentList: 'recent:list',
  recoveryList: 'recovery:list',
  recoveryResolve: 'recovery:resolve',
  settingsGet: 'settings:get',
  settingsSet: 'settings:set',
  windowSetTitleBarColors: 'window:setTitleBarColors',
  windowBeforeClose: 'window:beforeClose',
  windowConfirmClose: 'window:confirmClose',
  windowSetTitle: 'window:setTitle',
  appInfo: 'app:info',
  appLog: 'app:log',
  appOpenHelp: 'app:openHelp',
} as const;

export type IpcChannel = (typeof IPC)[keyof typeof IPC];
