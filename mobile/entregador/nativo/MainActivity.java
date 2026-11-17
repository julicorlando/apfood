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
    public void onResume() {
        super.onResume();
        // com o app na tela, o próprio app mantém o "Disponível" e mostra as chamadas
        PlantaoService.appVisivel = true;
        PlantaoService.parar(this);
        pedirParaNaoEconomizarBateria();
    }

    @Override
    public void onPause() {
        // tela bloqueada, outro app ou app fechado: o plantão segue recebendo as chamadas
        PlantaoService.appVisivel = false;
        PlantaoService.iniciar(this);
        super.onPause();
    }

    /** Uma vez: pede para o Android não "economizar bateria" no app (senão corta o plantão). */
    private void pedirParaNaoEconomizarBateria() {
        if (Build.VERSION.SDK_INT < 23 || !PlantaoService.disponivel(this)) return;
        android.content.SharedPreferences p = getSharedPreferences(Ofertas.PREFS, MODE_PRIVATE);
        android.os.PowerManager pm = (android.os.PowerManager) getSystemService(POWER_SERVICE);
        if (pm.isIgnoringBatteryOptimizations(getPackageName()) || p.getBoolean("apfood_bateria_pedida", false)) return;
        p.edit().putBoolean("apfood_bateria_pedida", true).apply();
        try {
            startActivity(new Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    android.net.Uri.parse("package:" + getPackageName())));
        } catch (Exception e) { /* aparelho sem essa tela */ }
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
