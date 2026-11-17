package br.com.axionweb.apfood.entregador;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;

import androidx.core.app.NotificationCompat;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** Chamada de entrega na tela bloqueada: notificação com Aceitar / Recusar e tela cheia. */
public final class Ofertas {
    static final String CANAL = "ofertas";
    static final String PREFS = "CapacitorStorage";

    private Ofertas() {}

    static int idDa(String chamada) {
        return chamada == null ? 7 : Math.abs(chamada.hashCode() % 1000000);
    }

    static void criarCanal(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm.getNotificationChannel(CANAL) != null) return;
        NotificationChannel ch = new NotificationChannel(CANAL, "Chamadas de entrega", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("Nova entrega para aceitar em 30 segundos");
        ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        ch.enableVibration(true);
        ch.setVibrationPattern(new long[]{0, 500, 250, 500, 250, 500});
        ch.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE),
                new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
        nm.createNotificationChannel(ch);
    }

    static int flags() {
        return PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0);
    }

    /** Mostra a chamada (também com o celular bloqueado). */
    static void mostrar(Context c, String titulo, String corpo, String chamada, int segundos) {
        criarCanal(c);
        int id = idDa(chamada);
        Intent abrir = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pAbrir = PendingIntent.getActivity(c, id, abrir, flags());
        NotificationCompat.Builder b = new NotificationCompat.Builder(c, CANAL)
                .setSmallIcon(c.getApplicationInfo().icon)
                .setContentTitle(titulo)
                .setContentText(corpo)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(corpo))
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setCategory(NotificationCompat.CATEGORY_CALL)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .setAutoCancel(true)
                .setOngoing(chamada != null)
                .setContentIntent(pAbrir)
                .setFullScreenIntent(pAbrir, true);
        if (segundos > 0) b.setTimeoutAfter(segundos * 1000L);
        if (chamada != null) {
            Intent aceitar = new Intent(c, MainActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    .putExtra("apfood_chamada", chamada).putExtra("apfood_acao", "aceitar");
            Intent recusar = new Intent(c, OfertaReceiver.class)
                    .putExtra("apfood_chamada", chamada).putExtra("apfood_acao", "recusar");
            b.addAction(0, "✅ Aceitar", PendingIntent.getActivity(c, id + 1, aceitar, flags()));
            b.addAction(0, "Recusar", PendingIntent.getBroadcast(c, id + 2, recusar, flags()));
        }
        ((NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE)).notify(id, b.build());
    }

    /** Responde a oferta direto no servidor (sem depender da tela do app). */
    static int responder(Context c, String chamada, String acao) {
        SharedPreferences p = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String token = p.getString("apfood_entregador_token", null);
        String base = p.getString("apfood_base", "https://apfood.axionwebdigital.com.br");
        if (token == null || chamada == null) return 0;
        HttpURLConnection con = null;
        try {
            URL url = new URL(base + "/api/entregador/ofertas/" + chamada + "/" + acao + "/");
            con = (HttpURLConnection) url.openConnection();
            con.setRequestMethod("POST");
            con.setConnectTimeout(10000);
            con.setReadTimeout(10000);
            con.setDoOutput(true);
            con.setRequestProperty("Authorization", "Entregador " + token);
            con.setRequestProperty("Content-Type", "application/json");
            con.setRequestProperty("Accept", "application/json");
            OutputStream o = con.getOutputStream();
            o.write("{}".getBytes("UTF-8"));
            o.close();
            return con.getResponseCode();
        } catch (Exception e) {
            return 0;
        } finally {
            if (con != null) con.disconnect();
            ((NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE)).cancel(idDa(chamada));
        }
    }
}
