package br.com.axionweb.apfood.entregador;

import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.view.WindowManager;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // a chamada aparece por cima da tela bloqueada e acende a tela
        if (Build.VERSION.SDK_INT >= 27) {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
        } else {
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON);
        }
        Ofertas.criarCanal(this);
        tratar(getIntent());
        // PUSH_TOKEN
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        tratar(intent);
    }

    /** "Aceitar" tocado na notificação: confirma no servidor; o app mostra a entrega em seguida. */
    private void tratar(Intent i) {
        if (i == null) return;
        final String chamada = i.getStringExtra("apfood_chamada");
        final String acao = i.getStringExtra("apfood_acao");
        if (chamada == null || acao == null) return;
        i.removeExtra("apfood_acao");
        final android.content.Context c = getApplicationContext();
        new Thread(() -> Ofertas.responder(c, chamada, acao)).start();
    }
}
