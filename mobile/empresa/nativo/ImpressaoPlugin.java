package br.com.axionweb.apfood.empresa;

import android.Manifest;
import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothSocket;
import android.content.Context;
import android.os.Build;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.util.Base64;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.UUID;

/**
 * Impressão no app ApFood Empresa (o WebView do Android não tem a janela de impressão do navegador):
 *   imprimirBluetooth → térmica Bluetooth pareada (ESC/POS pelo perfil serial SPP)
 *   imprimirRede      → térmica de rede/Wi-Fi (ESC/POS na porta RAW 9100)
 *   imprimirSistema   → serviço de impressão do Android (Wi-Fi, Mopria, RawBT…), a partir de HTML
 */
@CapacitorPlugin(name = "Impressao", permissions = {
        @Permission(strings = {Manifest.permission.BLUETOOTH_CONNECT}, alias = "bluetooth")})
public class ImpressaoPlugin extends Plugin {
    private static final UUID SPP = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
    private WebView paginaImpressao;  // mantém viva até o Android gerar o documento

    private boolean precisaPermissao() {
        return Build.VERSION.SDK_INT >= 31 && getPermissionState("bluetooth") != PermissionState.GRANTED;
    }

    private BluetoothAdapter adaptador() {
        BluetoothManager bm = (BluetoothManager) getContext().getSystemService(Context.BLUETOOTH_SERVICE);
        return bm == null ? null : bm.getAdapter();
    }

    @PluginMethod
    public void listarBluetooth(PluginCall call) {
        if (precisaPermissao()) { requestPermissionForAlias("bluetooth", call, "depoisDaPermissaoListar"); return; }
        listar(call);
    }

    @PermissionCallback
    private void depoisDaPermissaoListar(PluginCall call) {
        if (precisaPermissao()) call.reject("Permita o acesso a dispositivos próximos (Bluetooth) para o ApFood Empresa.");
        else listar(call);
    }

    @SuppressLint("MissingPermission")
    private void listar(PluginCall call) {
        BluetoothAdapter a = adaptador();
        if (a == null) { call.reject("Este celular não tem Bluetooth."); return; }
        if (!a.isEnabled()) { call.reject("Ligue o Bluetooth do celular."); return; }
        JSArray lista = new JSArray();
        for (BluetoothDevice d : a.getBondedDevices()) {
            JSObject o = new JSObject();
            o.put("nome", d.getName() == null ? d.getAddress() : d.getName());
            o.put("endereco", d.getAddress());
            lista.put(o);
        }
        JSObject r = new JSObject();
        r.put("dispositivos", lista);
        call.resolve(r);
    }

    @PluginMethod
    public void imprimirBluetooth(PluginCall call) {
        if (precisaPermissao()) { requestPermissionForAlias("bluetooth", call, "depoisDaPermissaoImprimir"); return; }
        enviarBluetooth(call);
    }

    @PermissionCallback
    private void depoisDaPermissaoImprimir(PluginCall call) {
        if (precisaPermissao()) call.reject("Permita o acesso a dispositivos próximos (Bluetooth) para o ApFood Empresa.");
        else enviarBluetooth(call);
    }

    @SuppressLint("MissingPermission")
    private void enviarBluetooth(PluginCall call) {
        String endereco = call.getString("endereco");
        byte[] dados = Base64.decode(call.getString("base64", ""), Base64.DEFAULT);
        BluetoothAdapter a = adaptador();
        if (a == null || !a.isEnabled()) { call.reject("Ligue o Bluetooth do celular."); return; }
        if (endereco == null || endereco.isEmpty()) { call.reject("Escolha a impressora Bluetooth."); return; }
        new Thread(() -> {
            BluetoothSocket s = null;
            try {
                BluetoothDevice d = a.getRemoteDevice(endereco);
                try { a.cancelDiscovery(); } catch (Exception ignorado) { /* ok */ }
                try {
                    s = d.createRfcommSocketToServiceRecord(SPP);
                    s.connect();
                } catch (Exception primeira) {  // algumas térmicas só aceitam a conexão "insegura"
                    if (s != null) try { s.close(); } catch (Exception ignorado) { /* ok */ }
                    s = d.createInsecureRfcommSocketToServiceRecord(SPP);
                    s.connect();
                }
                OutputStream out = s.getOutputStream();
                for (int i = 0; i < dados.length; i += 512) {  // em pedaços: as térmicas baratas têm buffer pequeno
                    out.write(dados, i, Math.min(512, dados.length - i));
                    out.flush();
                    Thread.sleep(20);
                }
                Thread.sleep(400);
                call.resolve();
            } catch (Exception e) {
                call.reject("Não consegui imprimir na impressora Bluetooth (ligada e perto do celular?): " + e.getMessage());
            } finally {
                if (s != null) try { s.close(); } catch (Exception ignorado) { /* ok */ }
            }
        }).start();
    }

    @PluginMethod
    public void imprimirRede(PluginCall call) {
        String host = call.getString("host");
        int porta = call.getInt("porta", 9100);
        byte[] dados = Base64.decode(call.getString("base64", ""), Base64.DEFAULT);
        if (host == null || host.isEmpty()) { call.reject("Digite o IP da impressora."); return; }
        new Thread(() -> {
            try (Socket s = new Socket()) {
                s.connect(new InetSocketAddress(host, porta), 5000);
                s.setSoTimeout(5000);
                OutputStream out = s.getOutputStream();
                out.write(dados);
                out.flush();
                Thread.sleep(200);
                call.resolve();
            } catch (Exception e) {
                call.reject("Não consegui imprimir em " + host + ":" + porta + " (mesmo Wi-Fi da impressora?): " + e.getMessage());
            }
        }).start();
    }

    @PluginMethod
    public void imprimirSistema(PluginCall call) {
        String html = call.getString("html", "");
        String titulo = call.getString("titulo", "ApFood");
        getActivity().runOnUiThread(() -> {
            try {
                WebView w = new WebView(getActivity());
                paginaImpressao = w;
                w.setWebViewClient(new WebViewClient() {
                    @Override
                    public void onPageFinished(WebView view, String url) {
                        PrintManager pm = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);
                        pm.print(titulo, view.createPrintDocumentAdapter(titulo), new PrintAttributes.Builder().build());
                        call.resolve();
                    }
                });
                w.loadDataWithBaseURL("https://apfood.axionwebdigital.com.br/", html, "text/html", "UTF-8", null);
            } catch (Exception e) {
                call.reject("Não consegui abrir a impressão do Android: " + e.getMessage());
            }
        });
    }
}
