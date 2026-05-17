# Analyse de Sécurité — Immat Scanner v2.3.0

Reverse-engineering de `com.prod.immatriculationscanner` v2.3.0  
API cible : `https://api.scanimmat.fr/v1`  
Date d'analyse : Mai 2026

---

## Sommaire

| ID | Titre | Sévérité |
|---|---|---|
| [S-01](#s-01--idor--accès-au-garage-privé-de-nimporte-quel-utilisateur) | IDOR — Garage privé accessible sans autorisation | 🔴 Critique |
| [S-02](#s-02--firebase-api-key-exposée--inscription-ouverte) | Firebase API Key exposée + inscription ouverte | 🔴 Critique |
| [S-03](#s-03--contournement-complet-de-firebase-app-check) | Contournement complet de Firebase App Check | 🟠 Élevé |
| [S-04](#s-04--oracle-de-validation-de-plaque-sans-quota) | Oracle de validation plaque SIV sans quota | 🟠 Élevé |
| [S-05](#s-05--aucun-rate-limiting-sur-la-création-de-comptes) | Aucun rate limiting sur la création de comptes | 🟠 Élevé |
| [S-06](#s-06--données-sensibles-exposées-sans-consentement) | VIN / CNIT / historique propriétaires sans consentement | 🟡 Moyen |
| [S-07](#s-07--absence-de-certificate-pinning) | Absence de certificate pinning | 🟡 Moyen |
| [S-08](#s-08--refresh-token-firebase-sans-expiration-côté-serveur) | Refresh token Firebase sans expiration côté serveur | 🟡 Moyen |
| [S-09](#s-09--énumération-duids-et-de-profils-utilisateurs) | Énumération d'UIDs et de profils utilisateurs | 🟢 Faible |
| [S-10](#s-10--corrélation-plaqueidentité-via-similar-owners) | Corrélation plaque → identité via `similar-owners` | 🟢 Faible |

---

## S-01 — IDOR : Accès au garage privé de n'importe quel utilisateur

**Sévérité :** 🔴 Critique  
**Type :** Insecure Direct Object Reference (IDOR)  
**OWASP :** A01:2021 – Broken Access Control

### Description

L'endpoint suivant retourne le garage complet d'un utilisateur (véhicules, plaques, modèles, années) en utilisant uniquement son UID Firebase comme paramètre :

```
GET /v1/app-users/{uid}/garage
Authorization: Bearer <n'importe quel token valide>
```

Le serveur ne vérifie pas que l'utilisateur authentifié est bien le propriétaire du garage demandé. N'importe quel compte valide peut accéder aux données privées de n'importe quel autre utilisateur.

### Reproduction

```python
# Étape 1 : récupérer des UIDs via suggested-users
GET /v1/app-users/suggested-users?page=1
# → retourne une liste d'utilisateurs avec leurs UIDs

# Étape 2 : accéder au garage privé de chaque UID
GET /v1/app-users/SCeYIc2CQVguuAWz7vJsglQBDrU2/garage
# → retourne les véhicules privés de cet utilisateur
```

### Données exposées

- Plaques d'immatriculation
- Marque, modèle, année, version
- Statut "véhicule principal"
- Surnom donné au véhicule par le propriétaire
- Statut de vérification du garage

### Impact

Un attaquant peut automatiser l'énumération de tous les UIDs via `/suggested-users` (paginé) puis scraper l'intégralité des garages de tous les utilisateurs enregistrés sur la plateforme, corrélant ainsi des identités réelles à des plaques de véhicules.

### Correction recommandée

Vérifier côté serveur que `uid` dans le chemin correspond à l'UID du token JWT présenté, sauf si la relation de suivi (follow) est établie et que le garage est marqué public.

---

## S-02 — Firebase API Key exposée + inscription ouverte

**Sévérité :** 🔴 Critique  
**Type :** Sensitive Data Exposure + Missing Authentication Control  
**OWASP :** A02:2021 – Cryptographic Failures / A07:2021 – Identification and Authentication Failures

### Description

La clé API Firebase est hardcodée en clair dans le binaire de l'application :

```
AIzaSyA1Wo5yK98tU05mhWPw7daadnnxfiajZjc
```

Elle est extractible depuis le fichier `resources.arsc` (ressources Android binaires) sans avoir à décompiler le bytecode. Cette clé permet d'utiliser directement l'API Firebase Identity Toolkit pour :

- Créer un nombre illimité de comptes
- S'authentifier avec email/password
- Rafraîchir des tokens
- Accéder à l'ensemble des endpoints authentifiés de l'API

### Reproduction

```bash
# Créer un compte sans passer par l'app
curl -X POST \
  "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=AIzaSyA1Wo5yK98tU05mhWPw7daadnnxfiajZjc" \
  -H "Content-Type: application/json" \
  -d '{"email":"attaque@exemple.com","password":"Pass1234!","returnSecureToken":true}'

# → retourne un idToken valide immédiatement utilisable
```

### Impact

- Création de comptes robots en masse pour contourner les quotas
- Utilisation de l'API sans passer par l'application officielle
- Abus potentiel du quota Firebase du projet (coûts)
- Tentatives de brute-force sur des emails enregistrés

### Correction recommandée

Les clés Firebase sont par nature publiques (elles doivent l'être pour fonctionner côté client). La vraie protection doit être assurée par **Firebase App Check** correctement configuré et **strictement imposé** côté serveur, avec des règles Firebase Security Rules adaptées. Voir aussi S-03.

---

## S-03 — Contournement complet de Firebase App Check

**Sévérité :** 🟠 Élevé  
**Type :** Security Control Bypass  
**OWASP :** A04:2021 – Insecure Design

### Description

Firebase App Check avec Play Integrity est censé garantir que les requêtes proviennent exclusivement de l'application officielle sur un vrai appareil Android. Cependant, le serveur accepte **indifféremment** :

- Un token `x-firebase-appcheck` valide (Play Integrity)
- **OU** un header `Authorization: Bearer <firebase_id_token>`

Ces deux mécanismes sont traités comme équivalents. Obtenir un Bearer token (via S-02) suffit à bypasser complètement App Check.

### Reproduction

```python
# Sans App Check, juste avec un Bearer token créé via S-02
headers = {
    "Authorization": "Bearer eyJhbGci...",   # token Firebase créé librement
    "User-Agent": "okhttp/4.12.0",
    "x-app-platform": "android",
    "x-app-version": "2.3.0",
}
response = requests.get("https://api.scanimmat.fr/v1/vehicle/AB351PZ?origin=index",
                        headers=headers)
# → HTTP 200, données complètes
```

### Impact

La protection Play Integrity est rendue inefficace. N'importe quel script peut accéder à l'API en créant simplement un compte Firebase, annulant l'investissement en sécurité d'App Check.

### Correction recommandée

- Rendre `x-firebase-appcheck` **obligatoire** sur tous les endpoints sensibles, indépendamment de la présence d'un Bearer token
- Ne pas traiter les deux mécanismes comme interchangeables
- Configurer Firebase App Check en mode **enforcement** strict (pas seulement monitoring)

---

## S-04 — Oracle de validation de plaque SIV sans quota

**Sévérité :** 🟠 Élevé  
**Type :** Business Logic Bypass  
**OWASP :** A04:2021 – Insecure Design

### Description

L'endpoint d'ajout au garage effectue une validation de la plaque contre la base SIV (Système d'Immatriculation des Véhicules) nationale et retourne une confirmation ou une erreur détaillée. Contrairement à l'endpoint principal de lookup, **il n'est pas soumis au quota journalier**.

```
POST /v1/app-users/garage
{"plate": "AB351PZ"}
```

- Si la plaque existe dans le SIV → `200 OK` avec données partielles du véhicule
- Si la plaque est invalide → `400 Bad Request` avec message explicite

### Impact

Cet endpoint peut être utilisé comme oracle pour :
- Valider l'existence de plaques en masse (scraping du SIV via l'API)
- Identifier des plaques actives sans déclencher le quota journalier
- Constituer une base de données de correspondances plaque/véhicule

### Correction recommandée

- Appliquer le même quota journalier sur le POST garage que sur le lookup
- Rate-limiter cet endpoint par compte et par IP
- Ne pas retourner de données véhicule dans la réponse d'ajout au garage

---

## S-05 — Aucun rate limiting sur la création de comptes

**Sévérité :** 🟠 Élevé  
**Type :** Missing Rate Limiting  
**OWASP :** A07:2021 – Identification and Authentication Failures

### Description

La création de comptes via Firebase Identity Toolkit n'est soumise à aucune limitation observable : ni CAPTCHA, ni vérification de device, ni délai entre créations. Des dizaines de comptes peuvent être créés par seconde depuis la même adresse IP.

### Reproduction

```python
import random, string, time

for i in range(50):
    email = f"bot_{random.randbytes(4).hex()}@gmail.com"
    # → création instantanée, token valide immédiatement
    # Temps total pour 50 comptes : ~8 secondes
```

### Impact

Combiné avec S-04, un attaquant peut contourner indéfiniment le quota journalier en créant de nouveaux comptes à la demande. Le quota par compte devient une protection sans effet.

### Correction recommandée

- Activer le rate limiting Firebase sur les inscriptions (disponible dans Firebase Console)
- Imposer une vérification email **avant** tout accès aux endpoints quotas
- Implémenter un délai minimum entre créations depuis la même IP

---

## S-06 — Données sensibles exposées sans consentement

**Sévérité :** 🟡 Moyen  
**Type :** Sensitive Data Exposure / RGPD  
**OWASP :** A02:2021 – Cryptographic Failures

### Description

Pour n'importe quelle plaque française, l'API retourne des données techniques complètes issues du SIV sans que le propriétaire du véhicule n'ait consenti à cette exposition :

```json
{
  "VIN": "VF7UD9HZH9J101566",
  "CNIT": "MCT7316VL406",
  "TVV": "UD9HZH/P",
  "mise_en_circulation": "00/06/2009",
  "proprietaires_recenses": 25
}
```

Ces données incluent notamment :
- **VIN** (Vehicle Identification Number) — identifiant unique et permanent du véhicule
- **CNIT** — numéro de certificat national d'identification du type
- **Nombre de propriétaires recensés** sur la plateforme

### Impact potentiel RGPD

Une plaque d'immatriculation est une donnée à caractère personnel en France (délibération CNIL). La corrélation plaque → VIN → identité propriétaire constitue un traitement de données personnelles soumis au RGPD. L'absence de mécanisme de opt-out pour les propriétaires de véhicules est problématique.

### Correction recommandée

- Permettre aux propriétaires de véhicules de demander le masquage de leur plaque
- Ne pas exposer le VIN complet sans authentification forte
- Revoir la politique de conformité RGPD

---

## S-07 — Absence de certificate pinning

**Sévérité :** 🟡 Moyen  
**Type :** Improper Certificate Validation  
**OWASP :** A02:2021 – Cryptographic Failures

### Description

L'application utilise `okhttp/4.12.0` sans avoir configuré de certificate pinning. Aucun `network_security_config.xml` n'est présent dans l'APK. Le comportement par défaut d'Android (vérification standard de la chaîne de confiance) s'applique.

Sur un appareil rooté avec Magisk + module de proxy système (ex: Magisk Trust User Certs), la totalité du trafic HTTPS est interceptable en clair, incluant les tokens d'authentification et les données véhicule.

### Reproduction (appareil rooté)

```
1. Installer mitmproxy CA dans le store système via Magisk
2. Configurer le proxy système
3. Tout le trafic app → api.scanimmat.fr est visible en clair
```

### Impact

- Capture de tokens Firebase (Bearer + App Check) pour rejeu
- Exposition des données de toutes les requêtes effectuées
- Possibilité de modifier les réponses en temps réel (MITM actif)

### Correction recommandée

```xml
<!-- res/xml/network_security_config.xml -->
<network-security-config>
    <domain-config>
        <domain includeSubdomains="true">api.scanimmat.fr</domain>
        <pin-set>
            <pin digest="SHA-256">VOTRE_HASH_CERTIFICAT=</pin>
        </pin-set>
    </domain-config>
</network-security-config>
```

---

## S-08 — Refresh token Firebase sans expiration côté serveur

**Sévérité :** 🟡 Moyen  
**Type :** Insufficient Session Expiration  
**OWASP :** A07:2021 – Identification and Authentication Failures

### Description

Les refresh tokens Firebase délivrés par le projet n'ont pas d'expiration imposée côté serveur de l'application. Un refresh token compromis (via S-07 par exemple) reste utilisable indéfiniment pour générer de nouveaux ID tokens valides, même si le mot de passe du compte est changé ultérieurement.

```python
# Un refresh token capturé reste valide des semaines/mois après
POST https://securetoken.googleapis.com/v1/token?key=AIzaSy...
{"grant_type": "refresh_token", "refresh_token": "<token_vole>"}
# → nouvel id_token valide
```

### Correction recommandée

- Implémenter une liste de révocation de tokens côté API
- Invalider les refresh tokens lors d'un changement de mot de passe
- Réduire la durée de vie des sessions actives

---

## S-09 — Énumération d'UIDs et de profils utilisateurs

**Sévérité :** 🟢 Faible  
**Type :** Information Disclosure  
**OWASP :** A01:2021 – Broken Access Control

### Description

Deux endpoints permettent d'énumérer les utilisateurs de la plateforme et d'accéder à leurs profils détaillés :

```
GET /v1/app-users/suggested-users?page=1    # liste paginée d'utilisateurs
GET /v1/app-users/profile/{uid}             # profil complet d'un utilisateur
```

Les profils exposent : username, XP, nombre de recherches totales, nombre de véhicules, followers/following, avatar.

### Impact

Permet de construire une liste exhaustive de tous les utilisateurs avec leurs UIDs (nécessaire pour S-01), et d'établir un graphe social de la plateforme.

### Correction recommandée

- Paginer et rate-limiter agressivement `suggested-users`
- Restreindre `profile/{uid}` aux utilisateurs mutuellement suivis ou avoir un paramètre de confidentialité

---

## S-10 — Corrélation plaque → identité via `similar-owners`

**Sévérité :** 🟢 Faible  
**Type :** Privacy Violation  
**OWASP :** A01:2021 – Broken Access Control

### Description

L'endpoint `similar-owners` associe explicitement une plaque d'immatriculation à des profils d'utilisateurs publics (avec photo, username, UID) ayant possédé le même modèle de véhicule :

```
GET /v1/app-users/similar-owners?uid=...&plate=AB351PZ
```

La réponse liste des utilisateurs ayant enregistré ce modèle dans leur garage, avec leurs avatars et usernames publics.

### Impact

Permet de relier une plaque (donnée personnelle) à des identités numériques publiques, facilitant la dé-anonymisation de propriétaires de véhicules.

### Correction recommandée

- Ne retourner que des statistiques agrégées (ex: "23 propriétaires") sans exposer les identités individuelles
- Ou limiter cet endpoint aux utilisateurs ayant explicitement rendu leur garage public

---

## Matrice de risque globale

```
Sévérité    Impact      Exploitabilité  ID
─────────────────────────────────────────────
Critique    Très élevé  Triviale        S-01, S-02
Élevé       Élevé       Facile          S-03, S-04, S-05
Moyen       Moyen       Modérée         S-06, S-07, S-08
Faible      Faible      Difficile       S-09, S-10
```

## Divulgation responsable

Cette analyse a été réalisée dans un cadre de recherche en sécurité (reverse engineering légal d'une application publique). Les vulnérabilités identifiées n'ont pas été exploitées à des fins malveillantes. Il est recommandé de contacter l'équipe Immat Scanner pour divulgation responsable avant toute publication.
