# InterArcade — Vision produit

## Positionnement

InterArcade est une application payante pour les créateurs qui animent des
lives TikTok. C’est un logiciel/launcher de mini-jeux interactifs : il permet
de choisir un jeu, de connecter un compte TikTok Live, puis de transformer les
interactions du public en actions visibles dans le jeu.

InterArcade n’est ni un dashboard IA, ni un simple site de jeux. Le site
présente et vend le produit ; l’application installée est l’espace de travail
du créateur pendant ses lives.

## Cible client

- créateurs TikTok Live réguliers ou en croissance ;
- streamers qui veulent augmenter la participation du public ;
- agences ou collectifs qui animent plusieurs comptes ;
- créateurs qui recherchent une expérience prête à lancer, sans développer
  eux-mêmes un jeu ou une intégration TikTok.

La priorité est une expérience fiable, compréhensible et rapide à lancer en
direct. Les fonctions internes d’observabilité ne doivent pas devenir le
produit visible par le créateur.

## Proposition de valeur

InterArcade donne au créateur une bibliothèque de jeux conçus pour les lives,
une connexion TikTok contrôlée et une session exploitable en quelques clics.
Les likes, cadeaux, commentaires, follows et partages deviennent des actions
de jeu selon les règles de chaque titre. Le créateur peut ainsi proposer une
animation interactive récurrente et mesurer ce qui s’est passé pendant son
live.

## Parcours utilisateur

1. Le site public présente InterArcade, les jeux, les offres et le
   téléchargement de l’application.
2. L’utilisateur installe l’application et se connecte avec son compte.
3. Son abonnement ou sa licence détermine les jeux accessibles.
4. Il arrive sur sa bibliothèque de mini-jeux.
5. Il choisit un jeu et connecte ou sélectionne son compte TikTok.
6. InterArcade détecte l’état du live et propose de lancer une session.
7. Les interactions TikTok déclenchent les événements du jeu autorisés par ce
   titre.
8. Le créateur arrête la session ; les résultats et statistiques sont
   conservés dans l’historique selon son offre.

## Rôle du site web

Le site est la vitrine et le point d’acquisition : présentation du produit,
aperçu des jeux, tarifs, FAQ, téléchargement, connexion au compte et gestion
commerciale future. Il ne doit pas être confondu avec l’interface de contrôle
utilisée pendant le live.

## Rôle de l’application

L’application est le launcher desktop ou client distribué InterArcade. Elle
gère la connexion utilisateur, l’état de licence, la bibliothèque, la
connexion TikTok, le lancement des jeux, les sessions et l’historique. Elle
doit rester utilisable même quand les détails techniques du backend sont
invisibles.

## Authentification

L’utilisateur s’authentifie auprès du service InterArcade. Les tokens de
session sont courts, liés à un utilisateur/tenant et séparés des tokens
internes worker/API. Les jeux ne reçoivent jamais de secret d’administration.
Une future authentification TikTok doit privilégier le mécanisme officiel
approprié et ne jamais demander au créateur de déposer un secret dans Git.

## Abonnements et licences

L’abonnement commercial est traduit en licence et droits d’accès : jeux
disponibles, nombre de comptes ou de sessions, fonctions d’historique et
éventuelles limites d’usage. Le serveur reste l’autorité sur ces droits ; le
client ne doit pas pouvoir s’auto-accorder un jeu en modifiant son interface.
Le paiement réel, la facturation et les offres ne sont pas encore implémentés
dans le prototype.

## Bibliothèque de jeux

La bibliothèque affiche les jeux autorisés par la licence avec une fiche
courte : promesse, interactions TikTok supportées, état de disponibilité et
boutons `Tester`/`Lancer avec TikTok`. Les jeux restent des modules séparés,
avec un contrat d’événement versionné commun.

## Connexion TikTok et session live

Le créateur sélectionne un compte TikTok, puis InterArcade vérifie l’état du
live avant de lancer une session. Le worker TikTok reçoit les événements,
l’API valide le tenant/session et les droits, puis le jeu reçoit uniquement
les événements autorisés. Une session possède un état explicite : préparation,
active, arrêt demandé, terminée ou en erreur. La reconnexion et la reprise ne
doivent pas perdre ou dupliquer les événements identifiants.

## Statistiques et historique

À la fin d’une session, InterArcade peut conserver la durée, le jeu, le
compte TikTok, les types/volumes d’interactions, les participants et les
résultats utiles au jeu. L’historique visible au créateur doit rester lisible
et orienté décision ; les logs techniques et erreurs détaillées restent des
outils internes.

## Mises à jour

Les mises à jour doivent préserver les licences, les sessions et les jeux
installés. Le launcher pourra vérifier une version disponible, télécharger
une release signée et permettre un retour contrôlé en cas d’échec. Aucun
mécanisme de mise à jour automatique public n’est encore activé.

## Fonctions utilisateur vs outils internes

| Utilisateur créateur | Interne/admin/agent |
| --- | --- |
| Compte, licence, bibliothèque, jeu, TikTok, session, statistiques | Healthchecks, diagnostics, logs structurés, migrations |
| Tester et lancer un jeu | Gestion des tenants, workers, listeners et erreurs |
| Historique et préférences | Outils de test, autocheck, résilience et déploiement |

Les routes d’administration, tokens internes, diagnostics complets et outils
de simulation ne doivent pas être présentés comme des fonctions commerciales
par défaut. La démo locale peut les exposer explicitement sous un mode isolé,
mais ce mode doit rester désactivé dans une configuration distribuée.
