# Publicar o Monitor dos Rios na Play Store

O app da Play Store é o próprio site, aberto em tela cheia (um *Trusted Web Activity*, o mesmo
formato usado por apps como o do Twitter Lite). Por isso:

- **Mudanças no painel, nos dados ou nas bacias chegam ao app sozinhas**, assim que o site é
  publicado. Não precisa mandar versão nova para a loja.
- Só é preciso gerar um app novo para mudar nome, ícone, cores ou o endereço do site.

## O que já está pronto neste repositório

| Item | Onde |
|---|---|
| Manifesto do app (nome, ícones, cores, atalhos por rio) | `public/manifest.webmanifest` (os atalhos são atualizados por `scripts/montar_site.py`) |
| Funciona sem internet (última leitura guardada) | `public/sw.js`, agora também na página inicial |
| Política de privacidade | `public/privacidade.html` → https://dimasdecampos.github.io/monitora-rio/privacidade.html |
| Textos da loja | `playstore/ficha-da-loja.md` |
| Ícone, imagem de destaque e capturas de tela | `playstore/imagens/` |
| Arquivos de verificação do domínio | `playstore/dominio/` |
| Gerador do app Android | `android/` (configuração em `app.json`) e `.github/workflows/app-android.yml` |

**Identificador do app (não dá para mudar depois de publicado):**
`com.monitora_rios`

---

## Passo 1 — Publicar o site com estas mudanças

Faça o commit e o push deste repositório. Confira que estes endereços abrem:

- https://dimasdecampos.github.io/monitora-rio/manifest.webmanifest
- https://dimasdecampos.github.io/monitora-rio/privacidade.html

## Passo 2 — Conta de desenvolvedor no Google Play

1. Acesse https://play.google.com/console e crie uma conta **pessoal**.
2. Pague a taxa única de **US$ 25** e faça a verificação de identidade (documento com foto).
   A aprovação pode levar alguns dias.

> ⚠️ **Teste fechado obrigatório.** Contas pessoais novas precisam fazer um **teste fechado
> com pelo menos 12 pessoas, por 14 dias seguidos**, antes de poder publicar para todo mundo.
> Vá juntando desde já os e-mails (contas Google) de amigos, comerciantes, pessoas da Defesa
> Civil etc. Cada um precisa aceitar o convite e manter o app instalado durante os 14 dias.

## Passo 3 — Gerar o app pelo GitHub

O workflow **Gerar app Android** (`.github/workflows/app-android.yml`) monta o app a partir de
`public/manifest.webmanifest` e `android/app.json`, compila e assina. Não precisa instalar nada.

**Chave do app (já criada):** fica em `C:\Users\dimas\Documents\monitora-rio-chave-android\`,
fora do repositório. O arquivo `LEIA-ME - chave do app.txt` tem a senha e a impressão digital.

> 🔐 **Guarde essa pasta em dois lugares seguros** (por exemplo, um pendrive e o Google Drive
> pessoal). **Nunca coloque no GitHub** (o `.gitignore` já bloqueia `*.keystore`). Sem ela, não dá
> para atualizar o app.

**Segredos no GitHub** (*Settings → Secrets and variables → Actions*, uma vez só):

| Segredo | Conteúdo |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | o arquivo `chave.keystore` em base64. No PowerShell: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("$HOME\Documents\monitora-rio-chave-android\chave.keystore"))` |
| `ANDROID_KEYSTORE_SENHA` | a senha do `LEIA-ME - chave do app.txt` |

**Gerar:** *Actions → Gerar app Android → Run workflow* (pode informar o nome da versão, por
exemplo `1.0.1`). Em cerca de 5 minutos aparecem em **Artifacts**, no fim da página da rodada:

- `monitor-dos-rios-<versão>-<n>.apk`: para instalar direto no celular;
- `monitor-dos-rios-<versão>-<n>.aab`: para enviar à Play Console.

O código da versão é o número da rodada, então cada geração é maior que a anterior, como a Play
Store exige.

## Passo 4 — Verificação do domínio (tira a barra de endereço do app)

Sem isso, o app abre com uma barra de endereço do Chrome no topo. O Android só confia no app
se o arquivo `https://dimasdecampos.github.io/.well-known/assetlinks.json` existir. Como o site
fica em `/monitora-rio/`, esse arquivo precisa de um repositório próprio:

1. Crie no GitHub um repositório **público** chamado exatamente `dimasdecampos.github.io`.
2. Envie para ele o conteúdo da pasta `playstore/dominio/`, que tem `.nojekyll`, `index.html`
   (redireciona para o monitor) e `.well-known/assetlinks.json`. Ele já vem com a impressão
   digital da sua chave, o que basta para o APK instalado direto.
3. Depois do primeiro envio à Play Console, acrescente a impressão da chave do Play:
   Play Console → seu app → **Testar e lançar → Configuração → Integridade do app → Assinatura
   de apps** → "Impressão digital do certificado SHA-256". Ela entra como segundo item da lista
   `sha256_cert_fingerprints`, entre aspas e separada por vírgula.
4. Confira se https://dimasdecampos.github.io/.well-known/assetlinks.json abre.

O link principal continua funcionando: `/monitora-rio/` é servido pelo repositório do monitor,
e a raiz `dimasdecampos.github.io` só redireciona para ele.

## Passo 5 — Criar o app na Play Console

1. **Criar app**: nome `Monitor dos Rios`, idioma Português (Brasil), App, Gratuito. Aceite
   as declarações.
2. **Presença na loja → Página principal da loja**: copie os textos e as imagens de
   `ficha-da-loja.md` e `imagens/`.
3. **Conteúdo do app** (menu "Política"). Respostas sugeridas:

   | Seção | Resposta |
   |---|---|
   | Política de privacidade | `https://dimasdecampos.github.io/monitora-rio/privacidade.html` |
   | Anúncios | Não contém anúncios |
   | Acesso ao app | Todas as funções estão disponíveis sem restrições (não tem login) |
   | Classificação do conteúdo | Categoria "Referência, notícias ou educacional". Responda "não" a violência, sexo, drogas, jogos de azar e interação entre usuários. Deve sair **Livre** |
   | Público-alvo | 18 anos ou mais (evita as regras de apps infantis; o app não é para crianças) |
   | Segurança dos dados | Coleta: **"IDs do dispositivo ou outros IDs"** (endereço de notificação, só se a pessoa ligar os avisos). Finalidade: **funcionalidade do app**. Não compartilhado, criptografado em trânsito, a pessoa pode pedir exclusão (botão "desligar"). Opcional. Nada mais é coletado |
   | App de notícias | Não |
   | App do governo | Não. A descrição já diz que é independente e cita as fontes |
   | Saúde / finanças / ID de publicidade | Não / Não / Não usa |

4. **Testar e lançar → Teste fechado**: crie uma faixa, envie o `.aab`, adicione a lista com os
   e-mails dos 12+ testadores e mande o link do convite para eles.
5. Depois do primeiro envio, pegue a impressão da chave do Play e complete o passo 4.
6. Passados os 14 dias com 12+ testadores, peça o **acesso à produção** (o Google faz algumas
   perguntas sobre o teste) e publique a versão de produção.

## Testar no seu celular antes

O `.apk` gerado no passo 3 instala direto (ative "instalar apps desconhecidos" para o
gerenciador de arquivos). Enquanto o passo 4 não estiver feito, ele abre com a barra de
endereço no topo. Isso é normal.

## Atualizar o app no futuro

- **Painel, dados, bacias novas**: só publique o site. O app atualiza sozinho.
- **Nome, ícone, cores**: mude `public/manifest.webmanifest` ou `android/app.json`, publique o
  site, rode de novo o workflow **Gerar app Android** e envie o novo `.aab` na Play Console.
- **Notificações com o app fechado (Web Push)**: já implementadas; a política de privacidade e a
  resposta de "Segurança dos dados" acima já consideram o endereço de notificação guardado.
