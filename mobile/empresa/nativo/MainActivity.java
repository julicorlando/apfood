package br.com.axionweb.apfood.empresa;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(ImpressaoPlugin.class);  // impressora térmica do celular (Bluetooth / rede) e do Android
        super.onCreate(savedInstanceState);
    }
}
