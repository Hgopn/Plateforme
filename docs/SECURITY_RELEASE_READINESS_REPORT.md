# InterArcade — Security + Release Readiness Sprint

État de travail : `interarcade-v2-release-readiness`, depuis le commit validé
`c786896f6d4f569617696d7604e8f537547c0324`. Aucun commit, push, merge ou
déploiement public n'est effectué dans ce sprint. Checkpoint local du parent :
`/tmp/interarcade-release-readiness-base.bundle`.

## Résumé et décision

Les limites de débit, l'isolation du renderer Electron, les en-têtes HTTP,
la journalisation du worker, le rôle PostgreSQL applicatif et le réseau Docker
ont été renforcés. Dark et ses trois niveaux ne sont pas modifiés. Le scanner
Gitleaks n'a trouvé aucun secret dans l'historique Git ; les valeurs de
`.env.integration` sont locales et ignorées par Git. L'audit Python du lockfile
de production ne signale aucune vulnérabilité connue. L'audit npm est passé de
18 packages signalés (dont un critique) à **zéro signalement actif** dans
`npm audit` au contrôle final du 23 octobre 2026. Huit signalements modérés
étaient encore présents au contrôle intermédiaire ; ils ont disparu après le
retrait de leur unique avis racine par GitHub, pas à cause d'une modification
supplémentaire du lockfile.

**État : prêt pour revue du code et pour préparer un environnement de test
privé. Pas encore autorisé pour un déploiement public ou une distribution
externe.** Il manque un domaine HTTPS opérationnel, des secrets de production
créés hors dépôt, un essai de restauration sur le VPS, un vrai essai TikTok
Live et une validation native des installateurs Windows/Mac.

## Secrets et historique

- Gitleaks v8.30.1, scan `git` de toutes les références et de l'historique,
  puis scan `dir` des fichiers suivis et nouveaux du working tree :
  **0 fuite détectée** sur les deux scans. Les rapports expurgés sont locaux dans `/tmp` et non
  versionné. `detect-secrets` sur le dépôt a relevé uniquement des exemples,
  des valeurs de tests, une chaîne vendue de Socket.IO et des marqueurs de
  cache ; vérification manuelle des emplacements, aucun secret réel suivi.
- `.env.integration` contient des secrets aléatoires de test local ; le fichier
  est ignoré, non présent dans l'historique, et n'est pas inclus dans l'image.
  `.env.production` n'existe pas ici. Aucune clé TikTok réelle, clé privée,
  certificat ou credential de production n'a été trouvé ou affiché.
- `.gitignore` et `.dockerignore` excluent les environnements, clés,
  certificats, dumps, bases locales, `.npmrc`, caches et artefacts desktop.
  Les fichiers `*.env.example` gardent seulement des valeurs fictives.
- Les secrets de production devront être générés indépendamment sur le VPS,
  avec permissions `0600`, et jamais copiés dans Git ou dans un artefact
  desktop. **Aucune rotation n'est déclenchée par cet audit**, faute de fuite
  détectée. Si une clé locale a été partagée hors du dépôt, son propriétaire
  doit la révoquer et la remplacer avant tout déploiement.

## Dépendances npm : examen des 18 signalements initiaux

Versions exactes issues du lockfile au checkpoint et du nouveau lockfile.
`electron` est le runtime distribué ; `electron-builder` et ses dépendances
sont utilisés pendant la construction, pas embarqués comme bibliothèque de
l'application. Les lignes « chaîne » sont des signalements propagés par
`npm audit` depuis une dépendance vulnérable, pas autant de failles distinctes.

| Package | Avant → après | Avis ou origine | Portée et action |
| --- | --- | --- | --- |
| `electron` | 33.4.11 → 45.0.0 | Plusieurs avis Electron, dont `GHSA-532v-xpq5-8h95` | Runtime desktop ; mise à jour majeure, risque de régression des fenêtres et du preload ; validation native encore requise. |
| `electron-builder` | 25.1.8 → 26.15.3 | Chaîne `app-builder-lib` / `tar` | Build seulement ; signalements actifs éliminés. |
| `app-builder-lib` | 25.1.8 → 26.15.3 | `GHSA-7g7r-gx96-252g` et chaîne | Build ; l'avis AppImage est corrigé, AppImage non utilisé. |
| `builder-util` | 25.1.7 → 26.15.3 | Chaîne build | Build ; signalement élevé éliminé. |
| `builder-util-runtime` | 9.2.10 → 9.7.0 | `GHSA-p2f4-r6v6-j797` | Build/runtime du builder ; corrigé. |
| `cacache` | 16.1.3 → retiré | Chaîne build | Build ; retiré du lockfile. |
| `dmg-builder` | 25.1.8 → 26.15.3 | Chaîne build | Build Mac ; signalements actifs éliminés. |
| `@electron/get` | 2.0.3 → 5.1.0 | Chaîne `global-agent` | Téléchargement du binaire ; le builder conserve une copie transitive, sans avis actif au contrôle final. |
| `@electron/rebuild` | 3.6.1 → 4.2.1 | Chaîne build | Build ; signalement élevé éliminé. |
| `electron-builder-squirrel-windows` | 25.1.8 → 26.15.3 | Chaîne build | Build Windows ; la cible distribuée reste NSIS. |
| `electron-publish` | 25.1.7 → 26.15.3 | Chaîne build | Publication désactivée ; signalement élevé éliminé. |
| `extract-zip` | 2.0.1 → retiré | `GHSA-jmr9-qjv8-65gv`, `GHSA-7pqw-9j4j-h8q3` | Extraction au build ; retiré. |
| `global-agent` | 3.0.0 → 3.0.0 | Chaîne `roarr` | Outil de build, pas le renderer ; avis racine retiré. |
| `make-fetch-happen` | 10.2.1 → retiré | Chaîne build | Build ; retiré. |
| `node-gyp` | 9.4.1 → 12.4.0 | Chaîne build | Build ; signalement élevé éliminé. |
| `roarr` | 2.15.4 → 2.15.4 | Chaîne `sprintf-js` | Logs du builder ; avis racine retiré. |
| `sprintf-js` | 1.1.3 → 1.1.3 | `GHSA-hp3w-g68c-fv3c` / CVE-2026-97058 | Ancien avis modéré retiré le 22 octobre 2026 ; format de log du builder, aucun format contrôlé par un créateur identifié. |
| `tar` | 6.2.1 → 7.5.22 | `GHSA-23hp-3jrh-7fpw` / CVE-2026-59873, plus autres avis | **Critique initial**, build seulement ; version corrigée, alerte éliminée. |

Au contrôle intermédiaire, `npm audit` signalait huit entrées modérées :
`sprintf-js`, `roarr`, `global-agent`, une copie de `@electron/get`,
`app-builder-lib`, `dmg-builder`, `electron-builder-squirrel-windows` et
`electron-builder`. Elles remontaient toutes à `GHSA-hp3w-g68c-fv3c`.
[GitHub a retiré cet avis le 22 octobre 2026](https://github.com/advisories/GHSA-hp3w-g68c-fv3c),
car la gestion de l'exception relève de l'application appelante. Les audits
npm répétés le 23 octobre, sous npm 9 et npm 10/Node 22, signalent **zéro
vulnérabilité active**. Les deux commandes `npm audit` et `npm audit
--audit-level=high` passent. Aucun `npm audit fix --force` n'a été utilisé.
Le risque de
régression de la mise à jour majeure Electron est contrôlé par les tests JS,
la vérification Node 22 et, encore à faire, les essais natifs Windows/Mac.

Références : [avis `tar`](https://github.com/advisories/GHSA-23hp-3jrh-7fpw),
[avis `app-builder-lib`](https://github.com/electron-userland/electron-builder/security/advisories/GHSA-7g7r-gx96-252g),
[avis `sprintf-js`](https://github.com/advisories/GHSA-hp3w-g68c-fv3c),
[sécurité Electron](https://www.electronjs.org/docs/latest/tutorial/security/).

## Dépendances Python et supply chain

`pip-audit` trouvait 30 entrées d'avis, réparties sur 12 packages épinglés.
Les doublons d'identifiant proviennent de plusieurs sources de l'index.

| Package | Avant → après | Avis | Usage |
| --- | --- | --- | --- |
| `anyio` | 4.10.0 → 4.14.2 | PYSEC-2026-4024, -4025 | Runtime HTTP/TikTok |
| `h2` | 4.3.0 → 4.4.1 | PYSEC-2026-3628 | Runtime HTTP/2 |
| `hpack` | 4.1.0 → 4.2.0 | PYSEC-2026-4053 | Runtime HTTP/2 |
| `certifi` | 2025.8.3 → 2026.10.19 | PYSEC-2026-4320 | Runtime TLS |
| `idna` | 3.10 → 3.15 | PYSEC-2026-215 | Runtime noms de domaine |
| `protobuf` | 6.32.0 → 6.33.5 | PYSEC-2026-1805 | Runtime TikTok |
| `Flask` | 3.0.3 → 3.1.3 | PYSEC-2026-2151 | API runtime |
| `Flask-Cors` | 4.0.1 → 6.0.0 | PYSEC-2024-71, PYSEC-2026-1383/1384/1385 | API runtime |
| `python-socketio` | 5.14.1 → 5.16.2 | PYSEC-2026-3042 | Live Hub runtime |
| `requests` | 2.32.3 → 2.33.0 | PYSEC-2026-1872, -2275 | Runtime HTTP |
| `python-dotenv` | 1.0.1 → 1.2.2 | PYSEC-2026-2270 | Configuration runtime |
| `pytest` | 8.3.5 → 9.0.3 | PYSEC-2026-1845 | Développement seulement |

`Flask-SocketIO` a aussi été porté de 5.3.6 à 5.7.0 pour rester compatible
avec Flask corrigé ; le premier test a révélé l'incompatibilité, puis la suite
est redevenue verte. `requirements.lock` verrouille les 66 paquets de test ;
`requirements.production.lock` verrouille 55 paquets runtime. L'image de
production n'installe plus pytest, Ruff ou Bandit. Les deux lockfiles passent
`pip-audit` sans avis connu. Les 285 paquets npm du lockfile proviennent tous
du registre npm, sans URL Git/file inattendue. Le script d'installation de
`electron-winstaller` sélectionne son binaire 7z ; Electron 45 télécharge son
binaire officiel au premier lancement selon sa nouvelle méthode. Les versions
des dépendances directes sont exactes.

## Electron, frontend et API

- Les deux fenêtres gardent `nodeIntegration: false`, `contextIsolation: true`,
  `sandbox: true` et `webSecurity: true`. Le preload expose seulement la
  relance et l'avis de fermeture broadcast. L'IPC vérifie l'émetteur ; les
  permissions du navigateur sont refusées, les webviews bloquées, les
  redirections et ouvertures de fenêtres limitées aux chemins autorisés et
  à l'origine configurée. L'URL serveur refuse credentials, chemin et requête.
  Aucun secret serveur n'est transmis au renderer ou à `server.json`.
- Le frontend créateur écrit les valeurs de compte en `textContent`. La démo
  locale n'insère en HTML que des définitions de jeux constantes ; ses styles
  dynamiques ont été déplacés vers CSS. La page d'attente utilise une feuille
  externe. CSP interdit les scripts inline, les objets et les frames externes.
  Dark peut être intégré uniquement par une page de même origine pour la démo.
- L'API limite les corps à 64 Kio, applique `nosniff`, `Referrer-Policy`,
  `Permissions-Policy`, CSP, protection clickjacking et `Cache-Control:
  no-store` sur les routes créateur. Les cookies sont `HttpOnly`, `SameSite=Strict`
  et `Secure` en production. Caddy assure HTTPS et la redirection HTTP→HTTPS.
  HSTS reste à `max-age=0` pendant validation ; le passer à un an seulement
  après contrôle du domaine et du certificat.
- Les mots de passe utilisent PBKDF2-HMAC-SHA256 avec sel aléatoire et 600 000
  itérations. Les erreurs de login restent génériques ; un compte inconnu
  entraîne le même travail de hachage. Les tokens sont aléatoires ou signés,
  expirent et les cookies de login sont révocables. Les POST créateur exigent
  un token CSRF ; les inscriptions/login contrôlent aussi l'origine. Le
  compteur de tentatives est atomique en base et partagé entre processus :
  10 logins par email, 30 par IP, 5 inscriptions par email et 10 par IP sur
  15 minutes, réponse 429 avec `Retry-After`. Caddy remplace lui-même
  l'en-tête IP client ; l'API ne le fait confiance qu'en configuration proxy.
- Les routes administrateur exigent le jeton admin ; l'ingress worker exige
  le jeton interne. Les sessions et sources restent vérifiées par tenant,
  statut et liaison de source avant d'accepter un événement. Les logs du
  worker et les erreurs persistées ne gardent plus le texte brut d'exception,
  seulement son type. Les noms d'événement et identifiants de session non
  sensibles restent traçables. Aucune simulation n'est activée en production.
- Le jeton de jeu éphémère passe dans le fragment URL de la fenêtre Dark : il
  n'entre pas dans les journaux HTTP ni le Referer, mais reste accessible au
  renderer et peut apparaître dans l'historique local jusqu'à fermeture de la
  session. Le retirer immédiatement casserait le rechargement autonome de la
  fenêtre ; un mécanisme de reprise sans fragment est à concevoir avant une
  distribution large. Aucun jeton interne durable n'y est présent.

## Docker, PostgreSQL, Redis et OVH

Seuls Caddy 80/443 sont publiés. `frontend` relie proxy/API ; `backend`
interne relie API, worker, PostgreSQL et Redis ; `egress` donne au worker la
sortie nécessaire vers TikTok. PostgreSQL et Redis n'ont aucun port hôte.
Redis conserve uniquement le fan-out éphémère et n'est pas exposé ; une
authentification deviendrait obligatoire si cette isolation change.

L'API et le worker tournent avec l'utilisateur non root UID 10001 de l'image.
Un rôle PostgreSQL `interarcade_admin` crée le volume neuf ; le rôle API
`interarcade` possède la base et le schéma, mais n'est pas superutilisateur.
Les deux mots de passe sont distincts et le secret administrateur DB n'est
plus injecté dans l'API/worker. L'initialisation a été vérifiée sur un volume
jetable : `interarcade` non superutilisateur, droit `CREATE` confirmé ; le
volume de test a été supprimé. Cela s'applique à un **volume neuf** ; une base
existante exige une migration de rôles préparée séparément avant bascule.
Les services ont redémarrage automatique, healthchecks et logs JSON bornés.
Le dump PostgreSQL est créé avec umask 077 et vérifié par `pg_restore --list` ;
une restauration réelle sur le VPS reste à tester. `docker compose config
--quiet` valide sans imprimer les secrets interpolés.

### Checklist OVH/VPS avant ouverture publique

1. **VPS** — créer un VPS Linux maintenu, stockage chiffré si proposé, accès console de secours.
2. **DNS** — pointer A/AAAA du domaine approuvé sur l'IP du VPS ; vérifier la propagation.
3. **Firewall** — ouvrir 80/443 ; limiter SSH aux administrateurs ; fermer 5432/6379.
4. **Utilisateur système** — créer un opérateur sans login root direct, SSH par clé, accès Docker limité.
5. **Docker** — installer versions maintenues de Docker Engine/Compose ; activer les mises à jour de sécurité hôte.
6. **Secrets** — créer `.env.production` depuis l'exemple en `0600`, secrets distincts et aléatoires, hors Git ; conserver une copie dans un coffre.
7. **PostgreSQL** — démarrer sur volume neuf, vérifier le rôle API non superutilisateur et la santé ; préparer une migration séparée si données antérieures.
8. **Redis** — confirmer absence de port publié et réseau `backend` uniquement ; persistance désactivée car fan-out éphémère.
9. **API** — construire l'image depuis un commit approuvé, vérifier UID 10001 et `/health/live`.
10. **Worker** — vérifier même base et même token interne que l'API, heartbeat et sortie TikTok.
11. **Caddy** — charger le domaine exact, proxy vers API seulement, valider la configuration.
12. **HTTPS** — contrôler certificat, redirection HTTP→HTTPS et cookies Secure ; après validation, régler HSTS à 31536000.
13. **Migrations** — sauvegarder avant toute version, exécuter les migrations additives et contrôler comptes/licences/sessions.
14. **Sauvegarde** — exécuter `bash scripts/backup_production.sh`, transférer le dump chiffré hors VPS, fixer rétention et accès.
15. **Restauration** — restaurer sur un environnement isolé, contrôler comptes/licences et le temps de reprise ; opération de production uniquement après validation humaine.
16. **Healthchecks** — vérifier `/health/live`, `/health/ready`, PostgreSQL, Redis et heartbeat worker ; alerter sur les échecs.
17. **Monitoring** — collecter logs JSON bornés, métriques espace disque/CPU, erreurs 5xx, expirations TLS et sessions orphelines.
18. **Rollback** — conserver image/commit précédent et dump vérifié, arrêter l'accès public si nécessaire, restaurer seulement après décision humaine.

Préflight : `python3 scripts/production_preflight.py .env.production`, puis
`docker compose --env-file .env.production -f deploy/docker-compose.production.yml config --quiet`.
Ces commandes ne déploient rien. Le démarrage `up -d --build` exige une
autorisation explicite. Ne jamais afficher `docker compose config` sans
`--quiet` avec de vrais secrets.

## Windows, Mac et GitHub Actions

Le workflow manuel utilise trois jobs séparés par matrice : Windows 2022 x64
pour NSIS, macOS 15 Apple Silicon et macOS 15 Intel pour DMG/ZIP. Il utilise Node 22, `npm
ci`, un seuil d'audit bloquant élevé/critique, des actions épinglées sur SHA,
`contents: read`, checkout sans credentials persistants, timeout et artefacts
à rétention de sept jours. `CSC_IDENTITY_AUTO_DISCOVERY=false` produit des
aperçus **non signés**. Le serveur est injecté comme origine HTTPS publique
validée, jamais comme clé. Le build Mac désactive le hardened runtime
uniquement pour cet aperçu non signé.

La configuration NSIS conserve installation/désinstallation, raccourcis,
version, dossier de données utilisateur et icône neutre. Le bundle Mac et sa
fenêtre broadcast utilisent le même process. Le workflow passe `actionlint`.
**Aucun installateur Windows ni bundle Mac distribuable de ce sprint n'a été
produit** : cette branche reste locale à la demande de l'utilisateur, donc
GitHub Actions ne peut pas construire ce code. Une tentative NSIS croisée sous
Linux a extrait l'application Windows, puis échoué à `spawn wine ENOENT`
pendant la création de l'installateur ; les deux fichiers NSIS partiels ont
été supprimés. L'hôte Linux n'a pas les bibliothèques graphiques nécessaires
pour lancer Electron. Le contrôle syntaxique Node 22 et l'installation npm
ont réussi ; l'essai du binaire Linux a échoué sur des bibliothèques système
manquantes. Après revue et push autorisé, déclencher
manuellement le workflow sur cette branche avec un backend HTTPS de test
approuvé, puis installer et désinstaller sur les deux OS.
L'`app.asar` extrait pendant la tentative Windows a été inspecté : il ne
contient que les sept fichiers desktop explicitement autorisés, sans `.env`,
clé serveur ou module Node embarqué dans le renderer.

Une distribution Windows signée demande le nom légal de l'éditeur et un
certificat de signature. Mac demande Apple Developer ID Application,
hardened runtime, signature et notarisation Apple, puis un essai sur Mac réel.
Les identifiants de signature/notarisation doivent rester dans les secrets du
runner, jamais dans le dépôt ni le package.

## Tests et risques résiduels

Contrôles locaux du 23 octobre 2026 : `scripts/test.sh` passe 73 tests
`unittest`, le parcours d'intégration et 18 tests JS Dark/launcher ; le test
Electron de contrat de sécurité passe. `scripts/autocheck.sh` passe 73 tests
`pytest` et 12 sous-tests, Ruff, Bandit, la syntaxe JS et `git diff --check`.
`npm audit` sous Node 22 retourne 0 vulnérabilité ; `pip-audit` retourne 0
sur chacun des deux lockfiles. Gitleaks retourne 0 fuite dans l'historique
et dans l'état final du working tree. `actionlint`, `docker compose config
--quiet` et la validation Caddy passent. Le monitor reste en avertissement
pour des erreurs historiques persistées et des lignes d'erreur de tests ;
API, base et worker sont sains. Le parcours E2E passe, y compris le contrôle
après redémarrage de l'API et du worker. Le test de résilience passe les cinq
contrôles : redémarrage API, redémarrage worker, panne worker, panne base et
intégrité des données.

**Critique :** aucun problème critique connu au contrôle final. Les scans
ne prouvent pas l'absence de défaut inconnu ; les relancer avant chaque
livraison.

| Niveau | Point restant | Action avant sortie |
| --- | --- | --- |
| Élevé | Aucun backend HTTPS public, ni essai de restauration sur le VPS ; aucun test TikTok réel approuvé. | Valider infrastructure privée, restauration et Live réel avant ouverture. |
| Élevé | Installateurs Windows/Mac de cette branche non construits, non signés, non testés sur OS natifs. | Après push approuvé, construire les artefacts unsigned, tester parcours complet, puis signer avant distribution large. |
| Moyen | Les clés de licence héritées sont stockées en clair dans PostgreSQL et ses dumps. | Limiter strictement accès DB/backups ; planifier une migration de hachage avec validation humaine avant de charger des licences client réelles. |
| Moyen | Le jeton de jeu reste dans le fragment local pour permettre le rechargement Dark. | Concevoir une reprise de fenêtre qui n'exige plus le fragment avant diffusion large. |
| Faible | `sprintf-js` reste dans le builder ; son ancien avis a été retiré et npm audit est vert. | Garder le builder hors runtime et surveiller une éventuelle nouvelle analyse. |
| Moyen | Caddy/DB/worker préparés localement ; charge, restauration et firewall du VPS non vérifiés. | Répéter les contrôles sur l'hôte cible avant exposition. |
| Moyen | Les images Docker ont des tags de version, sans empreintes digest immuables. | Geler les digests approuvés pour la première livraison et prévoir leur mise à jour de sécurité. |
| Faible | `TikTokLive` utilise encore des API `websockets` dépréciées dans les tests. | Suivre une version compatible du SDK et revalider le Live. |

Il n'y a ni paiement réel, ni nouvelle licence créée dans ce sprint. Toute
création de secret, modification d'entitlement client, migration destructive,
publication de package ou déploiement public requiert validation humaine.
