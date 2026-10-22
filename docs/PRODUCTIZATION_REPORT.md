# InterArcade V2 — rapport de productization (22 octobre 2026)

## État et périmètre

Le sprint a démarré sur `interarcade-v2-product-mvp`, qui contenait déjà des
modifications non commitées : site, launcher, desktop, actions Dark, mapping
TikTok et préparation VPS. Leur présence a été relevée avant les changements.
La branche locale `interarcade-v2-productization` a été créée à partir de ce
parent. `main` et `interarcade-v2-product-mvp` restent sur leurs références
initiales. Aucun commit, push, merge ou déploiement public n'a été fait.

Une archive du travail existant a été faite au début. Elle incluait alors
`.env.integration` et avait une permission trop large (`644`). Elle a été
remplacée par une archive filtrée, sans ce fichier, dans un répertoire `700`
avec permission `600`. Aucune lecture par un tiers n'a été constatée. Le contenu initial exact de
l'archive n'est donc plus disponible séparément ; tout le travail initial
reste présent dans le working tree. Ce point limite le rollback fichier par
fichier vers l'instant de départ. Le contrôle Git initial et le parent de
branche ont été conservés pour comparaison.
L'archive finale sécurisée est
`/tmp/interarcade-productization-checkpoint/worktree-final.tar.gz` ; son
empreinte SHA-256 est enregistrée dans le même répertoire.

## Livré

| Domaine | Résultat |
| --- | --- |
| Session | Lancement Test/Live sérialisé par créateur, réponse idempotente au double clic, conflit clair si autre mode actif, source Live créée dans la même transaction que la session. |
| Worker TikTok | États de connexion distincts, reprise après arrêt inattendu, source liée à un seul `session_id`, callbacks tardifs ignorés après arrêt. |
| Nettoyage | Bail renouvelé par le launcher, expiration après 120 secondes sans signal ou huit heures au total, arrêt de la source et de Dark ; reprise rapide de la session après redémarrage. |
| Launcher | Fenêtre Dark séparée, restauration de session, messages français sans erreur brute, connexion/absence de Live/reconnexion/listener perdu, fermeture automatique quand Dark est fermé, retour bibliothèque et fermeture de l'application. |
| Desktop | Dossier de données InterArcade, instance unique, gestion de page serveur indisponible, version et nom, fenêtre broadcast isolée, icône neutre. |
| Packaging | NSIS Windows avec raccourcis et désinstallation ; DMG/ZIP Mac ; garde HTTPS de paquet ; workflow natif Windows/macOS paramétré par backend public. |
| OVH/VPS | Compose API/PostgreSQL/Redis/worker/Caddy, contact ACME, domaine/IP/secrets à remplir, rotation des logs, précontrôle de configuration, migration additive, backup et script de restauration contrôlée. |

Le gameplay Dark, ses niveaux 1–3, les autres jeux et le design général n'ont
pas été retravaillés dans ce sprint. Aucun paiement, Twitch réel ou licence
factice n'a été ajouté. Les tarifs restent « Tarifs à venir ».

## Architecture

Electron charge le launcher depuis l'API HTTPS configurée. L'authentification
créateur utilise un cookie HTTP sécurisé et un jeton CSRF. L'API valide en
PostgreSQL le compte, le droit Dark et la session. Le worker séparé lit les
sources TikTok et envoie les événements normalisés à l'ingress interne. Le
jeu reçoit un jeton de session limité et reste non autoritaire. Redis est
prévu pour le fan-out Socket.IO de production. Les diagnostics internes ne
sont pas affichés comme interface produit.

## Fichiers du sprint

- Backend : `interarcade/app.py`, `interarcade/database.py`,
  `interarcade/config.py`, `interarcade/worker/service.py`,
  `interarcade/worker/tiktok.py`, `migrations/0002_creator_session_lease.sql`.
- Launcher et desktop : `static/launcher.js`, `desktop/main.js`,
  `desktop/preload.js`, `desktop/offline.{html,css,js}`,
  `desktop/{package.json,configure-server.js,verify-packaging.js}`,
  `desktop/build/{icon.svg,icon.png,render_icon.py}`,
  `.github/workflows/desktop-build.yml`.
- Exploitation : `deploy/{Caddyfile,docker-compose.production.yml,production.env.example}`,
  `.env.example`, `scripts/{production_preflight.py,restore_production.sh,
  test.sh,autocheck.sh}`, `.gitignore`, `pyproject.toml`.
- Vérification et documentation : `tests/{test_creator_product.py,
  test_live_hub.py,test_launcher_client.js}`, `docs/{PRODUCTIZATION.md,
  PRODUCT_MVP.md,LOCAL_DEVELOPMENT.md,ANOMALIES.md}` et ce rapport.

Les autres fichiers déjà modifiés au départ appartiennent au MVP en cours et
ont été conservés. Leur présence dans `git status` ne signifie pas qu'ils ont
été refaits pendant ce sprint.

## Vérification

- Suite Python : 66 tests `unittest` et `pytest` verts, avec création Test, gate licence,
  Live simulé, double lancement, états de source, nettoyage, reprise et
  séparation des comptes.
- Tests JS : 13 tests Dark et 5 tests launcher verts ; syntaxe des jeux,
  du launcher et d'Electron vérifiée.
- `scripts/test.sh`, `scripts/test_e2e.sh`, `scripts/test_resilience.sh` et
  `scripts/autocheck.sh` passent sur la pile locale d'intégration.
- Ruff, Bandit, `git diff --check`, précontrôle d'environnement et validation
  de la configuration Compose passent.
- L'E2E vérifie le parcours Dark/Marble, l'isolation d'événements, le refus
  après fermeture et la reprise après redémarrage. La résilience vérifie la
  détection des pannes worker/PostgreSQL et le maintien du nombre de licences.

Le premier passage d'intégration a révélé une requête de bail incompatible
avec le marqueur `%` de psycopg. Elle a été corrigée et testée sur PostgreSQL.
Les anciennes erreurs restent dans les diagnostics de la base d'intégration ;
le moniteur peut donc conserver une sévérité `warning` historique alors que
`/health/ready` et le worker sont sains. Aucune donnée de diagnostic n'a été
effacée.

## Exécution et limites

Les procédures exactes de développement local, packaging Windows/Mac et
déploiement OVH figurent dans [PRODUCTIZATION.md](PRODUCTIZATION.md). Pour un
créateur, le parcours est sans terminal **une fois** le backend public et un
installateur distribuable fournis. Le mode Test est fonctionnel sans TikTok.
Le Live automatique est câblé jusqu'au worker et testé avec connecteur simulé ;
aucune session avec un compte TikTok réel approuvé n'a été lancée.

Le build Windows tenté sur Linux a téléchargé Electron et préparé
`win-unpacked`, puis s'est arrêté car Wine n'est pas installé. Aucun `.exe`
installable n'a été produit ni validé ici. Le workflow Windows natif est prêt
pour un déclenchement manuel après commit/push autorisé. La voie Mac est
configurée mais ni DMG, ni signature, ni notarisation n'ont été vérifiés sur
un Mac. Aucun domaine, certificat, secret OVH ou serveur public n'a été
configuré ; aucune sauvegarde/restauration de production n'a été exécutée.

## Avant un testeur externe

1. Fournir domaine, IP VPS, email ACME et secrets de production ; autoriser le
   déploiement, vérifier HTTPS, sauvegarde et restauration sur un environnement
   isolé.
2. Définir l'identité légale de l'éditeur et les certificats de signature,
   construire l'installateur sur Windows, installer/désinstaller et vérifier
   la fenêtre broadcast ; faire de même sur Mac et notariser la release Mac.
3. Fournir un compte TikTok de test et les credentials approuvés pour un essai
   réel offline/online, reconnexion, événements et fin de session.
4. Définir l'attribution réelle des licences et la procédure d'assistance ;
   aucun paiement ni droit automatique n'est simulé.
5. Revoir les 18 alertes `npm audit` observées à l'installation des outils
   desktop (principalement dépendances de build) et planifier une mise à jour
   Electron/electron-builder validée avant diffusion large.

Le sprint n'est pas une release publique. La validation humaine du rapport,
du domaine, des certificats et du compte de test précède toute publication.
