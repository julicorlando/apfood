import { contextBridge, ipcRenderer } from 'electron';

/** API mínima e explícita exposta ao renderer (sem acesso direto ao Node). */
const api = {
  aoNovoPedido: (cb: () => void) => {
    const handler = () => cb();
    ipcRenderer.on('pedido:novo-alerta', handler);
    return () => ipcRenderer.removeListener('pedido:novo-alerta', handler);
  },
};

contextBridge.exposeInMainWorld('apfood', api);

export type ApFoodBridge = typeof api;
