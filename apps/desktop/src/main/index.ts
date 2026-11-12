import { join } from 'node:path';
import { app, BrowserWindow, Notification } from 'electron';
import { abrirBancoLocal } from './local-db';

/**
 * Processo principal do PDV.
 * Responsabilidades (Passo 3):
 *   • Banco local SQLite (cache do catálogo + fila de sincronização/outbox)
 *   • Worker de sync: envia outbox quando online, faz pull por cursor
 *   • Conexão Socket.IO com a API e alerta de novo pedido (som + notificação)
 *   • Impressão térmica ESC/POS (cozinha e cupom)
 * O renderer (React) só fala com o main via IPC seguro exposto no preload.
 */

let janela: BrowserWindow | null = null;

function criarJanela() {
  janela = new BrowserWindow({
    width: 1366,
    height: 768,
    minWidth: 1024,
    minHeight: 640,
    title: 'ApFood PDV',
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: true,
    },
  });

  if (process.env.ELECTRON_RENDERER_URL) {
    void janela.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    void janela.loadFile(join(__dirname, '../renderer/index.html'));
  }
}

export function alertarNovoPedido(numero: number | null) {
  new Notification({ title: 'Novo pedido online!', body: numero ? `Pedido #${numero}` : 'Pedido recebido' }).show();
  janela?.webContents.send('pedido:novo-alerta');
  janela?.flashFrame(true);
}

app.whenReady().then(() => {
  abrirBancoLocal(join(app.getPath('userData'), 'apfood-local.db'));
  criarJanela();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) criarJanela();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
