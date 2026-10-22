# InterArcade V2 — productization et exploitation

## Parcours créateur

L'application installée ouvre directement le launcher. Le créateur s'inscrit ou
se connecte, choisit Dark, enregistre son `@pseudo` TikTok, puis utilise
**Tester sans live** ou **Lancer Dark**. Le jeu s'ouvre dans une fenêtre
broadcast indépendante. Le launcher garde les commandes de session et affiche
l'état du listener. Fermer le jeu, revenir à la bibliothèque, se déconnecter ou
terminer la session arrête la source associée. Le mode Test crée la même session
de jeu mais n'ouvre aucune connexion TikTok et identifie ses actions comme
simulées. Le jeu Dark validé et ses trois niveaux restent inchangés.

Le backend est un service hébergé. L'utilisateur final n'installe ni Python,
Docker ou base de données et n'utilise aucun terminal. Pour le développement,
le launcher peut viser l'API locale sur `http://127.0.0.1:15001`. Un paquet
distribué doit contenir l'origine HTTPS publique dans `desktop/server.json`.
L'application stocke ses cookies HTTP sécurisés dans le dossier de données
Electron `InterArcade`; aucun token de jeu ou secret administrateur n'est mis
dans un stockage local propre à l'application.

## Cycle d'une session

`POST /api/v1/creator/sessions` valide l'identité et le CSRF, puis verrouille
le créateur en base. Une même demande répétée rend la session existante et un
nouveau jeton de fenêtre ; un mode différent rend `session_already_active`.
Pour le Live, la licence Dark et le pseudo TikTok sont vérifiés dans cette
transaction. La source TikTok et la session sont créées ensemble et partagent
un identifiant de session immuable. Le worker séparé lit cette source, démarre
le connecteur et publie `connecting`, `connected`, `offline` ou `reconnecting`.
La supervision peut afficher `lost` quand le heartbeat du worker expire.

Le launcher interroge l'état toutes les quatre secondes et renouvelle un bail
de 120 secondes. Une session a aussi une durée maximale de huit heures, égale
à la durée du jeton du jeu. Après une fermeture brutale, le worker termine la session,
marque sa source `stopping` puis coupe le connecteur. Les callbacks tardifs ne
peuvent pas réactiver une source en arrêt. Un redémarrage rapide du launcher
retrouve la session active et permet de rouvrir la fenêtre. Le diagnostic
administrateur conserve les états détaillés ; les réponses du créateur ne
contiennent pas les erreurs brutes du connecteur.

## Développement et intégration

Le développement local utilise une API et une base locale ; SQLite reste
réservé aux tests. La pile d'intégration existante est lancée par
`./scripts/start.sh` et contrôlée par `./scripts/status.sh`. Le desktop local
utilise le port d'intégration loopback `15001` défini dans `desktop/server.json`.
Pour un test autonome du launcher Electron : `cd desktop`, `npm ci`, puis
`npm start` sur une machine avec Node 22 et l'API déjà lancée. Les commandes
de ce paragraphe sont réservées au développement, jamais au créateur.

L'environnement de test `.env.integration` et le fichier de production
`.env.production` sont distincts. Le domaine public ne doit jamais pointer
sur le Lenovo. `INTERARCADE_CREATOR_SESSION_LEASE_SECONDS` permet d'ajuster le
bail selon l'infrastructure. Garder une valeur supérieure à plusieurs cycles
de rafraîchissement du launcher.

## Installateur Windows

Le workflow manuel `.github/workflows/desktop-build.yml` utilise un runner
Windows et exige l'origine HTTPS approuvée dans `server_url`. Il configure le
backend, vérifie le process Electron, produit un NSIS et conserve l'artefact
non signé. Le NSIS installe InterArcade par utilisateur, crée des raccourcis
Bureau et menu Démarrer, offre la désinstallation et utilise la version de
`desktop/package.json`. Une icône de menu neutre est fournie, à remplacer
quand l'identité visuelle définitive sera validée.

Sur un runner Windows avec Node 22 :

```powershell
cd desktop
npm ci
$env:INTERARCADE_SERVER_URL="https://interarcade.example.com"
$env:INTERARCADE_BUILD_CHANNEL="production"
npm run configure:server
npm run check
npm run dist:win
```

Remplacer le domaine avant exécution. `verify-packaging.js` refuse un backend
HTTP local pour un paquet distribuable. Le nom légal de l'éditeur et le sujet
du certificat Windows doivent être renseignés avant une release signée.
Fournir un certificat de signature de code via les secrets du runner, selon
[la documentation electron-builder](https://www.electron.build/docs/features/code-signing/).
L'installateur n'a pas été exécuté sur Windows dans ce sprint.

## Bundle Mac

Le même workflow utilise un runner macOS pour produire un DMG et un ZIP
contenant l'app. La fenêtre broadcast est créée par le même process Electron.
Une compilation locale suit la configuration ci-dessus avec `npm run dist:mac`
sur un Mac avec Node 22. Le workflow d'aperçu désactive le hardened runtime
pour l'artefact non signé. Pour distribuer hors App Store, fournir un
certificat Developer ID Application (`CSC_LINK`, `CSC_KEY_PASSWORD`), conserver
le hardened runtime, puis fournir les identifiants de notarisation Apple
(`APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER` ou l'alternative Apple
ID). Vérifier ensuite signature, notarisation, ouverture et fenêtre broadcast
sur le matériel cible. Référence :
[signature et notarisation electron-builder](https://www.electron.build/docs/notarization/).

## Préparation OVH / VPS

Prévoir un VPS Linux, un domaine contrôlé et ses enregistrements DNS A/AAAA
vers l'IP publique du VPS. Ouvrir uniquement 80/443 au public ; garder SSH
réservé à l'administration et ne publier ni 5432 ni 6379. Caddy obtient et
renouvelle le certificat HTTPS. La composition comprend API/Socket.IO,
PostgreSQL, Redis pour le fan-out, worker TikTok et Caddy. Les services ont un
redémarrage automatique, des healthchecks et des logs JSON bornés par taille
et nombre de fichiers. L'API et le worker partagent l'URL PostgreSQL et le
jeton interne d'événements.

1. Sur le VPS, obtenir une version Git approuvée du projet. Copier
   `deploy/production.env.example` vers `.env.production`, régler les
   permissions à `600` et renseigner le vrai domaine, l'IP publique, l'email
   ACME pour les certificats Caddy, les secrets aléatoires indépendants, le
   mot de passe PostgreSQL et l'origine HTTPS. Ne jamais
   commiter ce fichier. Définir le DNS avant le démarrage de Caddy.
2. Exécuter `python3 scripts/production_preflight.py .env.production` puis
   `docker compose --env-file .env.production -f deploy/docker-compose.production.yml config`.
   Le contrôle valide la forme des secrets et du domaine ; il ne prouve pas la
   résolution DNS ni la validité du certificat.
3. Avant chaque mise à jour, exécuter `bash scripts/backup_production.sh` et
   conserver le dump PostgreSQL hors VPS. Le code applique les migrations
   additives à l'ouverture sous verrou PostgreSQL. Les fichiers
   `migrations/0001_creator_mvp.sql` et `0002_creator_session_lease.sql`
   documentent ces changements.
4. Après autorisation de déploiement, exécuter
   `docker compose --env-file .env.production -f deploy/docker-compose.production.yml up -d --build`.
   Contrôler `https://DOMAINE/health/live` puis `/health/ready`, les logs
   structurés `docker compose logs --tail=100 api worker proxy`, et les
   diagnostics avec le token observateur. Tester inscription, login, Test,
   licence, session et arrêt avant d'ouvrir les téléchargements.
5. Pour restaurer après validation humaine, arrêter l'accès public, choisir
   un dump vérifié et exécuter
   `bash scripts/restore_production.sh --confirm-restore /chemin/backup.dump`.
   Cette opération remplace les données de la base. Pour revenir à la version
   précédente du code, redéployer son tag ou image après le backup ; les
   migrations de ce sprint sont additives. Vérifier à nouveau readiness,
   sessions et droits.

Ni le VPS ni un certificat public ne sont configurés ici. Le déploiement et
les secrets restent à fournir et à autoriser. Le compte TikTok réel et les
droits de connexion du worker nécessitent un essai contrôlé avec un compte
test approuvé. Aucun paiement n'est intégré : le site affiche toujours
« Tarifs à venir ». Avant un testeur externe, valider un installateur signé
sur Windows, le Mac sur machine réelle, le domaine HTTPS, une sauvegarde
restaurable, la délivrance de licences et un test Live TikTok complet.
