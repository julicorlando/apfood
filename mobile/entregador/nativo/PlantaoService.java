package br.com.axionweb.apfood.entregador;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

import androidx.core.app.NotificationCompat;
import androidx.core.app.ServiceCompat;
import androidx.core.content.ContextCompat;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Plantão: enquanto o entregador está "Disponível", este serviço fica rodando com o
 * celular bloqueado ou o app fechado. A cada 5 s avisa o servidor que continua
 * disponível (com a posição) e, quando chega uma chamada, toca e mostra em tela cheia
 * com Aceitar / Recusar. Não depende do Firebase.
 */
public class PlantaoService extends Service {
    static final String CANAL = "plantao";
    static final int ID = 4242;
    static final String CHAVE_DISPONIVEL = "apfood_disponivel";
    static volatile boolean appVisivel = false;

    private ScheduledExecutorService relogio;
    private PowerManager.WakeLock acordado;
    private LocationManager lm;
    private LocationListener ouvinte;
    private volatile Location ultima;
    private String chamadaAtual;
    private int falhas = 0;

    static boolean disponivel(Context c) {
        SharedPreferences p = c.getSharedPreferences(Ofertas.PREFS, Context.MODE_PRIVATE);
        return "1".equals(p.getString(CHAVE_DISPONIVEL, "0")) && p.getString("apfood_entregador_token", null) != null;
    }

    static void iniciar(Context c) {
        if (!disponivel(c)) return;
        try {
            ContextCompat.startForegroundService(c, new Intent(c, PlantaoService.class));
        } catch (Exception e) {
            // Android não deixou iniciar agora (app em segundo plano): o app inicia na próxima vez
        }
    }

    static void parar(Context c) {
        c.stopService(new Intent(c, PlantaoService.class));
    }

    private static boolean temLocalizacao(Context c) {
        return ContextCompat.checkSelfPermission(c, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || ContextCompat.checkSelfPermission(c, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm.getNotificationChannel(CANAL) == null) {
                NotificationChannel ch = new NotificationChannel(CANAL, "Disponível para entregas", NotificationManager.IMPORTANCE_LOW);
                ch.setDescription("Fica visível enquanto você recebe chamadas com o celular bloqueado");
                ch.setShowBadge(false);
                nm.createNotificationChannel(ch);
            }
        }
        Ofertas.criarCanal(this);
        Intent abrir = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        Intent sair = new Intent(this, OfertaReceiver.class).putExtra("apfood_acao", "indisponivel");
        Notification n = new NotificationCompat.Builder(this, CANAL)
                .setSmallIcon(getApplicationInfo().icon)
                .setContentTitle("🛵 Você está disponível")
                .setContentText("As chamadas tocam mesmo com o celular bloqueado.")
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setCategory(NotificationCompat.CATEGORY_SERVICE)
                .setContentIntent(PendingIntent.getActivity(this, ID, abrir, Ofertas.flags()))
                .addAction(0, "Ficar indisponível", PendingIntent.getBroadcast(this, ID + 1, sair, Ofertas.flags()))
                .build();
        int tipo = 0;
        if (Build.VERSION.SDK_INT >= 29 && temLocalizacao(this)) tipo = ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
        else if (Build.VERSION.SDK_INT >= 34) tipo = ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE;
        try {
            ServiceCompat.startForeground(this, ID, n, tipo);
        } catch (Exception e) {
            stopSelf();
            return;
        }
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        acordado = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "apfood:plantao");
        acordado.setReferenceCounted(false);
        acordado.acquire(12 * 60 * 60 * 1000L);
        ligarGps();
        relogio = Executors.newSingleThreadScheduledExecutor();
        relogio.scheduleWithFixedDelay(this::tique, 0, 5, TimeUnit.SECONDS);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (relogio != null) relogio.shutdownNow();
        if (lm != null && ouvinte != null) {
            try { lm.removeUpdates(ouvinte); } catch (Exception e) { /* ok */ }
        }
        if (acordado != null && acordado.isHeld()) acordado.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void ligarGps() {
        if (!temLocalizacao(this)) return;
        lm = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        ouvinte = new LocationListener() {
            @Override public void onLocationChanged(Location l) { ultima = l; }
            @Override public void onStatusChanged(String p, int s, Bundle b) {}
            @Override public void onProviderEnabled(String p) {}
            @Override public void onProviderDisabled(String p) {}
        };
        for (String prov : new String[]{LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER}) {
            try {
                if (lm.isProviderEnabled(prov)) {
                    lm.requestLocationUpdates(prov, 15000, 20, ouvinte, Looper.getMainLooper());
                    Location l = lm.getLastKnownLocation(prov);
                    if (l != null && ultima == null) ultima = l;
                }
            } catch (SecurityException | IllegalArgumentException e) { /* sem esse provedor */ }
        }
    }

    private void tique() {
        if (!disponivel(this)) { stopSelf(); return; }
        SharedPreferences p = getSharedPreferences(Ofertas.PREFS, Context.MODE_PRIVATE);
        String token = p.getString("apfood_entregador_token", null);
        String base = p.getString("apfood_base", "https://apfood.axionwebdigital.com.br");
        HttpURLConnection con = null;
        try {
            Location l = ultima;
            String corpo = l == null ? "{}" : String.format(Locale.US, "{\"latitude\":%.6f,\"longitude\":%.6f}", l.getLatitude(), l.getLongitude());
            con = (HttpURLConnection) new URL(base + "/api/entregador/plantao/").openConnection();
            con.setRequestMethod("POST");
            con.setConnectTimeout(8000);
            con.setReadTimeout(8000);
            con.setDoOutput(true);
            con.setRequestProperty("Authorization", "Entregador " + token);
            con.setRequestProperty("Content-Type", "application/json");
            con.setRequestProperty("Accept", "application/json");
            OutputStream o = con.getOutputStream();
            o.write(corpo.getBytes("UTF-8"));
            o.close();
            int codigo = con.getResponseCode();
            if (codigo == 401) { encerrar(p); return; }  // sessão expirou: entra de novo pelo app
            if (codigo != 200) return;
            falhas = 0;
            JSONObject r = new JSONObject(ler(con.getInputStream()));
            if (!r.optBoolean("online", false)) { encerrar(p); return; }  // ficou indisponível (pelo app ou pela loja)
            JSONObject oferta = r.optJSONObject("oferta");
            if (oferta == null) {
                if (chamadaAtual != null) {
                    ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).cancel(Ofertas.idDa(chamadaAtual));
                    chamadaAtual = null;
                }
                return;
            }
            String chamada = oferta.optString("chamada", null);
            if (chamada == null || chamada.equals(chamadaAtual)) return;
            chamadaAtual = chamada;
            if (appVisivel) return;  // com o app na tela, ele mesmo mostra a chamada
            long ganho = oferta.isNull("ganho_centavos") ? -1 : oferta.optLong("ganho_centavos", -1);
            String bairro = oferta.optString("bairro", "");
            String texto = "Para " + (bairro.isEmpty() || "null".equals(bairro) ? "o cliente" : bairro)
                    + (ganho > 0 ? String.format(Locale.forLanguageTag("pt-BR"), " · você recebe R$ %.2f", ganho / 100.0).replace('.', ',') : "")
                    + ". Aceite em " + oferta.optInt("segundos", 30) + " s.";
            Ofertas.mostrar(this, "🛵 Nova entrega — " + oferta.optString("loja", "ApFood"), texto, chamada, oferta.optInt("segundos", 30));
        } catch (Exception e) {
            falhas++;  // sem rede: tenta de novo no próximo tique
        } finally {
            if (con != null) con.disconnect();
        }
    }

    private void encerrar(SharedPreferences p) {
        p.edit().putString(CHAVE_DISPONIVEL, "0").apply();
        stopSelf();
    }

    private static String ler(InputStream in) throws java.io.IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) > 0) b.write(buf, 0, n);
        in.close();
        return b.toString("UTF-8");
    }
}
