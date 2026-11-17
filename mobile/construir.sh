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
rm -rf android
npx cap add android
npx cap sync android

MANIFESTO=android/app/src/main/AndroidManifest.xml
if [ "$APP" = "cliente" ]; then
  # "Perto de mim" usa a localização do aparelho
  sed -i 's#<application#<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />\n    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />\n\n    <application#' "$MANIFESTO"
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
