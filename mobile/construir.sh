#!/usr/bin/env bash
# Gera o APK assinado de um dos apps (cliente | empresa).
# Uso: mobile/construir.sh cliente   → mobile/dist/ApFood-Cliente.apk
# Precisa de Node 20+, JDK 21, Android SDK (ANDROID_HOME) e ImageMagick.
# Assinatura: variáveis ANDROID_KEYSTORE_B64 / ANDROID_KEYSTORE_SENHA (secrets do
# GitHub) ou, na falta delas, a chave mobile/apfood.keystore do repositório.
set -euo pipefail

APP="$1"
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$RAIZ/mobile/$APP"
VERSAO="$(tr -d '[:space:]' < "$RAIZ/mobile/VERSAO")"
IFS=. read -r MA MI PA <<< "$VERSAO"
CODIGO=$((MA * 10000 + MI * 100 + PA))
NOME_APK="ApFood-$(echo "${APP:0:1}" | tr a-z A-Z)${APP:1}.apk"

cd "$DIR"
npm install --no-audit --no-fund
# Push (Firebase): só com o google-services.json (secret ANDROID_GOOGLE_SERVICES_B64) e só nos apps da equipe
PUSH=""
if [ -n "${ANDROID_GOOGLE_SERVICES_B64:-}" ] && [ "$APP" != "cliente" ]; then
  # empresa: plugin padrão; entregador: serviço nativo próprio (chamada com Aceitar/Recusar na tela bloqueada)
  if [ "$APP" = "empresa" ]; then npm install --no-audit --no-fund @capacitor/push-notifications@^7; fi
  PUSH=1
fi
rm -rf android
npx cap add android
if [ -n "$PUSH" ]; then
  echo "$ANDROID_GOOGLE_SERVICES_B64" | base64 -d > android/app/google-services.json
  echo "push: Firebase ligado neste APK"
fi
if [ "$APP" = "entregador" ]; then
  # código nativo: chamada por cima da tela bloqueada, Aceitar/Recusar na notificação
  PKG=android/app/src/main/java/br/com/axionweb/apfood/entregador
  mkdir -p "$PKG"
  cp "$DIR/nativo/MainActivity.java" "$DIR/nativo/Ofertas.java" "$DIR/nativo/OfertaReceiver.java" "$DIR/nativo/PlantaoService.java" "$PKG/"
  M=android/app/src/main/AndroidManifest.xml
  sed -i 's#<application#<uses-permission android:name="android.permission.USE_FULL_SCREEN_INTENT" />\n\n    <application#' "$M"
  sed -i 's#</application>#    <receiver android:name=".OfertaReceiver" android:exported="false" />\n    </application>#' "$M"
  # plantão: enquanto "Disponível", recebe as chamadas com o celular bloqueado ou o app fechado (sem Firebase)
  sed -i 's#<application#<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION" />\n    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_SPECIAL_USE" />\n    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />\n\n    <application#' "$M"
  sed -i 's#</application>#    <service android:name=".PlantaoService" android:exported="false" android:stopWithTask="false" android:foregroundServiceType="location|specialUse"><property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" android:value="Chamadas de entrega em tempo real enquanto o entregador está disponível" /></service>\n    </application>#' "$M"
  if [ -n "$PUSH" ]; then
    cp "$DIR/nativo/EntregaMessagingService.java" "$PKG/"
    sed -i 's#</application>#    <service android:name=".EntregaMessagingService" android:exported="false"><intent-filter><action android:name="com.google.firebase.MESSAGING_EVENT" /></intent-filter></service>\n    </application>#' "$M"
    sed -i '0,/^dependencies {/s//dependencies {\n    implementation "com.google.firebase:firebase-messaging:24.1.0"/' android/app/build.gradle
    sed -i 's#        // PUSH_TOKEN#        com.google.firebase.messaging.FirebaseMessaging.getInstance().getToken().addOnSuccessListener(t -> getSharedPreferences(Ofertas.PREFS, MODE_PRIVATE).edit().putString("apfood_push_token", t).apply());#' "$PKG/MainActivity.java"
  fi
fi
npx cap sync android

MANIFESTO=android/app/src/main/AndroidManifest.xml
if [ "$APP" = "cliente" ] || [ "$APP" = "entregador" ]; then
  # cliente: "Perto de mim"; entregador: chamadas pelo mais perto e rastreio da entrega
  sed -i 's#<application#<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />\n    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />\n\n    <application#' "$MANIFESTO"
fi
if [ "$APP" = "entregador" ]; then
  # alerta de chamada: notificação, vibração e tela acesa enquanto disponível
  sed -i 's#<application#<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n    <uses-permission android:name="android.permission.VIBRATE" />\n    <uses-permission android:name="android.permission.WAKE_LOCK" />\n\n    <application#' "$MANIFESTO"
fi

# versão
GRADLE=android/app/build.gradle
sed -i -E "s/versionCode [0-9]+/versionCode $CODIGO/; s/versionName \"[^\"]+\"/versionName \"$VERSAO\"/" "$GRADLE"

# ícone ApFood em todas as densidades (sem ícone adaptativo)
RES=android/app/src/main/res
rm -rf "$RES/mipmap-anydpi-v26"
ICONE="$RAIZ/backend/static/marca/icone-512.png"
for par in mdpi:48 hdpi:72 xhdpi:96 xxhdpi:144 xxxhdpi:192; do
  d="${par%%:*}"; t="${par##*:}"
  for n in ic_launcher ic_launcher_round ic_launcher_foreground; do
    convert "$ICONE" -resize "${t}x${t}" "$RES/mipmap-$d/$n.png"
  done
done

cd android
chmod +x gradlew
./gradlew --no-daemon assembleRelease

# assinatura
CHAVE="$RAIZ/mobile/apfood.keystore"; SENHA="apfood2026"
if [ -n "${ANDROID_KEYSTORE_B64:-}" ]; then
  CHAVE="$(mktemp)"; echo "$ANDROID_KEYSTORE_B64" | base64 -d > "$CHAVE"
  SENHA="$ANDROID_KEYSTORE_SENHA"
fi
BT="$(ls -d "$ANDROID_HOME"/build-tools/* | sort -V | tail -1)"
mkdir -p "$RAIZ/mobile/dist"
"$BT/zipalign" -f -p 4 app/build/outputs/apk/release/app-release-unsigned.apk /tmp/alinhado.apk
"$BT/apksigner" sign --ks "$CHAVE" --ks-pass "pass:$SENHA" --ks-key-alias apfood \
  --out "$RAIZ/mobile/dist/$NOME_APK" /tmp/alinhado.apk
"$BT/apksigner" verify "$RAIZ/mobile/dist/$NOME_APK"
echo "OK: mobile/dist/$NOME_APK ($VERSAO / $CODIGO)"
