package br.com.axionweb.apfood.entregador;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Botão "Recusar" da notificação: responde sem abrir o app. */
public class OfertaReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(final Context c, Intent i) {
        final String chamada = i.getStringExtra("apfood_chamada");
        final String acao = i.getStringExtra("apfood_acao");
        final PendingResult r = goAsync();
        new Thread(() -> {
            try {
                if ("indisponivel".equals(acao)) { Ofertas.ficarIndisponivel(c.getApplicationContext()); return; }
                Ofertas.responder(c.getApplicationContext(), chamada, acao == null ? "recusar" : acao);
            } finally {
                r.finish();
            }
        }).start();
    }
}
