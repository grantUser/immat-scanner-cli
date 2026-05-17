# Immat Scanner CLI

Client Python pour l'API **Immat Scanner** (`api.scanimmat.fr`) — retourne toutes les données techniques d'un véhicule français à partir de sa plaque d'immatriculation.

Reverse-engineered depuis l'application Android `com.prod.immatriculationscanner` v2.3.0.

---

## Résultat

```
================================================================
  CITROËN C4 1.6 HDI
  2009, Génération 1, Phase 1
================================================================
  Plaque                           AB351PZ
  Energie                          Gazole
  Puissance                        109 CH
  Transmission                     Automatique
  Couple                           240 nm  (1750 rpm)
  0 à 100km/h                      13.2 sec
  Vitesse max                      180 km/h
  Puissance Fiscale                6 CV
  Couleur                          GRIS
  Carrosserie                      MONOSPACE COMPACT
  Critair                          3
  CO2 (g/km)                       142 g/km
  Prix neuf                        26 960 €
  Cylindrée                        1560 cc
  Code moteur                      9HZOU9H01
  Mise en circulation              00/06/2009
  VIN                              VF7UD9HZH9J101566
  Poids à vide                     1499 kg
  Volume du coffre                 500 L
  Pneus                            205/65 R15 94 H | 215/45 R18
  Huile moteur                     Viscosité 5W-30  Capacité 3.8 L
  Freins                           Avant Disques ventilés  Arrière Tambours
  Proprietaires                    25 connus sur la plateforme
================================================================
```

---

## Prérequis

- Python 3.8+
- Aucune dépendance externe (stdlib uniquement)
- Un compte sur l'application **Immat Scanner** (gratuit)

---

## Installation

```bash
git clone https://github.com/votre-user/immat-scanner-cli.git
cd immat-scanner-cli
```

Pas de `pip install` requis — le script n'utilise que la bibliothèque standard Python.

---

## Authentification

L'API requiert un compte Immat Scanner (Firebase). Deux façons de s'authentifier :

### Option A — Créer un compte automatiquement (recommandé)

```bash
py immat_scanner.py --signup
```

Un compte Firebase est créé automatiquement et les credentials sont sauvegardés dans `firebase_token.json`. Les prochaines recherches s'authentifient sans aucun argument.

### Option B — Utiliser votre compte Immat Scanner existant

```bash
py immat_scanner.py AB-351-PZ --email votre@gmail.com --password votremdp
```

Les credentials sont sauvegardés après la première connexion réussie.

> **Note :** `firebase_token.json` est dans `.gitignore` — ne le commitez jamais.

---

## Utilisation

### Recherche de plaque (usage principal)

```bash
# Format avec ou sans tirets
py immat_scanner.py AB-351-PZ
py immat_scanner.py AB351PZ

# JSON brut complet
py immat_scanner.py AB-351-PZ --json

# Spécifier l'origine (index = recherche manuelle, scanner = scan caméra)
py immat_scanner.py AB-351-PZ --origin scanner
```

### Profil et garage

```bash
py immat_scanner.py --profile
py immat_scanner.py --garage
py immat_scanner.py --history
py immat_scanner.py --favorites
py immat_scanner.py --user-garage <UID>
py immat_scanner.py --user-profile <UID>
```

### Marketplace

```bash
py immat_scanner.py --marketplace
py immat_scanner.py --marketplace --brand Peugeot
py immat_scanner.py --marketplace --brand BMW --department 75
```

### Santé de l'API

```bash
py immat_scanner.py --health
```

---

## Tous les arguments

| Argument | Description |
|---|---|
| `plate` | Plaque à rechercher (ex: `AB-351-PZ` ou `AB351PZ`) |
| `--email` | Email du compte Firebase |
| `--password` | Mot de passe |
| `--token` | ID Token Firebase direct (depuis HTTP Toolkit) |
| `--appcheck-token` | Token x-firebase-appcheck (vrai appareil Android) |
| `--signup` | Créer un nouveau compte Firebase automatiquement |
| `--origin` | `index` (défaut) ou `scanner` |
| `--json` | Afficher le JSON brut complet |
| `--profile` | Mon profil utilisateur |
| `--garage` | Mon garage |
| `--history` | Historique de recherches |
| `--favorites` | Véhicules favoris |
| `--health` | État des services API |
| `--marketplace` | Annonces LeBonCoin agrégées |
| `--brand` | Filtre marque (marketplace) |
| `--department` | Filtre département (marketplace) |
| `--user-garage UID` | Garage public d'un utilisateur |
| `--user-profile UID` | Profil public d'un utilisateur |

---

## Données retournées

| Catégorie | Champs |
|---|---|
| **Identité** | Plaque, Marque, Modèle, Version, Tags (génération, phase) |
| **Motorisation** | Énergie, Puissance (DIN + fiscale), Couple, Cylindrée, Code moteur, Architecture, Turbo |
| **Performances** | 0-100 km/h, Vitesse max |
| **Transmission** | Boîte, Nombre de vitesses, Roues motrices |
| **Carrosserie** | Type, Nombre de portes, Places, Couleur, Dimensions (L/l/h), Empattement |
| **Écologie** | Crit'Air, CO₂ (g/km), Norme Euro, Dépollution |
| **Consommation** | Mixte / Urbain / Extra-urbain, Capacité réservoir, Prix du plein |
| **Carte Grise** | VIN, CNIT, TVV, Mise en circulation, Numéro de série |
| **Mécanique** | Freins, Pneus, Huile moteur, Batterie, Direction, Roue de secours |
| **Communauté** | Nombre de propriétaires recensés sur la plateforme |

---

## Architecture API

```
Base URL : https://api.scanimmat.fr/v1
Auth     : Firebase JWT (Bearer token)
App      : com.prod.immatriculationscanner
```

### Endpoints principaux

```
GET  /vehicle/{plate}?origin=index          Lookup plaque (endpoint principal)
GET  /vehicle/services-health               Santé des services
GET  /vehicle/scanner-config                Config scanner caméra
GET  /marketplace/ads                       Annonces LeBonCoin
GET  /app-users/profile                     Mon profil
GET  /app-users/garage                      Mon garage
GET  /app-users/{uid}/garage                Garage public d'un user
GET  /app-users/search-history              Historique
GET  /app-users/suggested-users             Utilisateurs suggérés
POST /app-users/garage                      Ajouter au garage (valide via SIV)
PATCH /app-users/user-type                  Définir particulier/professionnel
POST /vehicle/report                        Signaler une erreur
GET  /app-users/insurance-providers         Liste des assurances (117)
```

### Firebase

```
API Key  : AIzaSyA1Wo5yK98tU05mhWPw7daadnnxfiajZjc
Project  : immatriculation-scanner
App ID   : 1:258352946399:android:3f09920525ead974
Auth     : https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword
Refresh  : https://securetoken.googleapis.com/v1/token
```

### Headers requis par l'API

```
User-Agent:     okhttp/4.12.0
x-app-platform: android
x-app-version:  2.3.0
x-device-id:    <uuid v4>
Authorization:  Bearer <firebase_id_token>
```

---

## Quota

L'API applique un **quota journalier** par compte (reset à minuit, heure CET). En cas de dépassement, la réponse est `HTTP 403` avec le message `Quota journalier dépassé`.

---

## Sécurité — Firebase App Check

L'API supporte aussi l'authentification sans compte via **Firebase App Check** (Play Integrity), mais ce token ne peut être généré que par un vrai appareil Android non-rooté exécutant l'application officielle. Il n'est pas possible de le générer programmatiquement.

Si vous avez capturé un token valide via [HTTP Toolkit](https://httptoolkit.com) sur votre téléphone :

```bash
py immat_scanner.py AB-351-PZ --appcheck-token "eyJ..."
```

---

## Licence

Ce projet est publié à des fins éducatives et de recherche. L'utilisation de l'API `api.scanimmat.fr` est soumise aux conditions d'utilisation d'Immat Scanner.
