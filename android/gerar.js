// Gera o projeto Android (Trusted Web Activity) em android/projeto/, a partir de
// public/manifest.webmanifest e android/app.json. Usado pelo workflow "Gerar app Android".
// Uso: node android/gerar.js [versionCode]   (VERSAO=1.0.1 troca o nome da versão)
const fs = require("fs");
const path = require("path");
const { TwaManifest, TwaGenerator, ConsoleLog } = require("@bubblewrap/core");

(async () => {
  const raiz = path.resolve(__dirname, "..");
  const app = JSON.parse(fs.readFileSync(path.join(__dirname, "app.json"), "utf8"));
  const web = JSON.parse(fs.readFileSync(path.join(raiz, "public", "manifest.webmanifest"), "utf8"));
  const site = new URL(app.site);

  // base a partir do manifesto do site; por cima, o que é específico do app
  const base = TwaManifest.fromWebManifestJson(new URL("manifest.webmanifest", site), web).toJson();
  const twa = new TwaManifest({
    ...base,
    packageId: app.packageId,
    host: site.host,
    name: app.name,
    launcherName: app.launcherName,
    startUrl: site.pathname,
    fullScopeUrl: site.href,
    appVersion: process.env.VERSAO || app.appVersion,
    appVersionCode: Number(process.argv[2] || 1),
    enableNotifications: true,
    minSdkVersion: 24,   // a Proteção Automática do Google Play exige 24 ou mais (Android 7.0)
    fallbackType: "customtabs",
    splashScreenFadeOutDuration: 300,
    themeColor: app.themeColor || base.themeColor,   // barra de status da cor do painel
    navigationColor: app.navigationColor,
    navigationColorDark: app.navigationColorDark,
    themeColorDark: app.themeColorDark,
    signingKey: { path: "chave.keystore", alias: app.keyAlias },
    generatorApp: "monitor-rios",
    // só para testes locais: buscar o manifesto em outro endereço
    ...(process.env.MANIFESTO_URL ? { webManifestUrl: process.env.MANIFESTO_URL } : {}),
  });

  const destino = path.join(__dirname, "projeto");
  fs.rmSync(destino, { recursive: true, force: true });
  fs.mkdirSync(destino, { recursive: true });
  const log = new ConsoleLog("gerar");
  const erro = twa.validate?.();
  if (erro) throw new Error(erro);
  await new TwaGenerator().createTwaProject(destino, twa, log);
  fs.writeFileSync(path.join(destino, "twa-manifest.json"), JSON.stringify(twa.toJson(), null, 2));
  console.log(`Projeto gerado em ${destino} (versão ${twa.appVersionName}, código ${twa.appVersionCode})`);
})().catch(e => { console.error(e); process.exit(1); });
