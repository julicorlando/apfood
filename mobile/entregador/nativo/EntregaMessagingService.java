package br.com.axionweb.apfood.entregador;

import android.content.Context;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import java.util.Map;

/** Push do Firebase: chega com o app fechado e o celular bloqueado. */
public class EntregaMessagingService extends FirebaseMessagingService {
    @Override
    public void onNewToken(String token) {
        getSharedPreferences(Ofertas.PREFS, Context.MODE_PRIVATE).edit().putString("apfood_push_token", token).apply();
    }

    @Override
    public void onMessageReceived(RemoteMessage m) {
        Map<String, String> d = m.getData();
        String titulo = d.get("titulo");
        String corpo = d.get("corpo");
        if (titulo == null && m.getNotification() != null) {
            titulo = m.getNotification().getTitle();
            corpo = m.getNotification().getBody();
        }
        if (titulo == null) return;
        int segundos = 0;
        try { segundos = Integer.parseInt(d.containsKey("segundos") ? d.get("segundos") : "0"); } catch (NumberFormatException e) { segundos = 0; }
        Ofertas.mostrar(this, titulo, corpo == null ? "" : corpo, "oferta".equals(d.get("tipo")) ? d.get("chamada") : null, segundos);
    }
}
