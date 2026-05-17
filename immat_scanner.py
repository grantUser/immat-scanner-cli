#!/usr/bin/env python3
"""
Immat Scanner API Client
Reverse-engineered from com.prod.immatriculationscanner v2.3.0

Firebase project : immatriculation-scanner
API base         : https://api.scanimmat.fr/v1
"""

import json
import os
import re
import ssl
import string
import sys
import time
import random
import urllib.error
import urllib.parse
import urllib.request
import uuid

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Config ────────────────────────────────────────────────────
FIREBASE_API_KEY = 'AIzaSyA1Wo5yK98tU05mhWPw7daadnnxfiajZjc'
API_BASE = 'https://api.scanimmat.fr/v1'

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

_APP_HEADERS = {
    'User-Agent':     'okhttp/4.12.0',
    'Accept':         'application/json',
    'Content-Type':   'application/json',
    'x-app-platform': 'android',
    'x-app-version':  '2.3.0',
    'x-device-id':    str(uuid.uuid4()),
}

_TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'firebase_token.json')

APP_CHECK_TOKEN: str = ''   # override via --appcheck-token


# ── HTTP ──────────────────────────────────────────────────────
def _http(method: str, url: str, data=None, extra_headers=None):
    headers = {**_APP_HEADERS, **(extra_headers or {})}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_ctx, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}


def normalize_plate(plate: str) -> str:
    """'AB-351-PZ' -> 'AB351PZ'"""
    return re.sub(r'[\s\-]', '', plate).upper()


# ── Firebase Auth ─────────────────────────────────────────────
class FirebaseAuth:
    def __init__(self, email=None, password=None, id_token=None, refresh_token=None):
        self.email = email
        self.password = password
        self.id_token = id_token
        self.refresh_token = refresh_token
        self.expires_at = time.time() + 3590 if id_token else 0

    def _fb(self, endpoint, data):
        url = f'https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={FIREBASE_API_KEY}'
        return _http('POST', url, data)

    def _store(self, body):
        self.id_token = body['idToken']
        self.refresh_token = body.get('refreshToken', self.refresh_token)
        self.expires_at = time.time() + int(body.get('expiresIn', 3600)) - 30

    def signup(self, email=None, password=None):
        email = email or self.email or f'scan_{"".join(random.choices(string.ascii_lowercase+string.digits, k=8))}@gmail.com'
        password = password or self.password or 'Pass1234!'
        self.email, self.password = email, password
        _, body = self._fb('signUp', {'email': email, 'password': password, 'returnSecureToken': True})
        if 'idToken' not in body:
            raise Exception(f'signup failed: {body}')
        self._store(body)

    def signin(self):
        _, body = self._fb('signInWithPassword', {
            'email': self.email, 'password': self.password, 'returnSecureToken': True
        })
        if 'idToken' not in body:
            raise Exception(f'signin failed: {body}')
        self._store(body)

    def refresh(self):
        url = f'https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}'
        _, body = _http('POST', url, {'grant_type': 'refresh_token', 'refresh_token': self.refresh_token})
        if 'id_token' not in body:
            raise Exception(f'refresh failed: {body}')
        self.id_token = body['id_token']
        self.refresh_token = body.get('refresh_token', self.refresh_token)
        self.expires_at = time.time() + int(body.get('expires_in', 3600)) - 30

    def token(self) -> str:
        if not self.id_token:
            if self.email and self.password:
                self.signin()
            else:
                raise Exception('Aucun credentials — utilisez --email/--password ou --token')
        if time.time() > self.expires_at:
            if self.refresh_token:
                self.refresh()
            elif self.email and self.password:
                self.signin()
        return self.id_token

    def save(self, path=_TOKEN_FILE):
        with open(path, 'w') as f:
            json.dump({
                'email': self.email, 'password': self.password,
                'uid': '', 'id_token': self.id_token,
                'refresh_token': self.refresh_token,
            }, f, indent=2)

    @classmethod
    def load(cls, path=_TOKEN_FILE):
        with open(path) as f:
            d = json.load(f)
        obj = cls(email=d.get('email'), password=d.get('password'),
                  id_token=d.get('id_token'), refresh_token=d.get('refresh_token'))
        obj.expires_at = 0  # force refresh
        return obj


# ── API Client ────────────────────────────────────────────────
class ImmatAPI:
    """
    Client pour api.scanimmat.fr/v1

    Endpoints documentés :
      GET  /vehicle/{plate}?origin=index|scanner   — lookup principal
      GET  /vehicle/services-health
      GET  /vehicle/scanner-config
      GET  /vehicle/check-update
      GET  /vehicle/garage-vehicle?plate={plate}
      POST /vehicle/report
      GET  /marketplace/ads
      GET  /app-users/profile
      GET  /app-users/profile/{uid}
      PATCH /app-users/user-type
      GET  /app-users/garage
      GET  /app-users/{uid}/garage
      POST /app-users/garage
      GET  /app-users/search-history
      DELETE /app-users/clear-history
      GET  /app-users/search-favorites
      DELETE /app-users/clear-favorite
      GET  /app-users/suggested-users
      GET  /app-users/{uid}/followers
      GET  /app-users/{uid}/following
      POST /app-users/follow
      POST /app-users/rate-vehicle
      GET  /app-users/insurance-providers
      POST /upload-image
    """

    def __init__(self, auth: FirebaseAuth):
        self.auth = auth

    def _auth_header(self):
        h = {}
        if APP_CHECK_TOKEN:
            h['x-firebase-appcheck'] = APP_CHECK_TOKEN
        try:
            h['Authorization'] = f'Bearer {self.auth.token()}'
        except Exception:
            pass
        return h

    def _get(self, path, params=None, public=False):
        url = API_BASE + path
        if params:
            url += '?' + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        return _http('GET', url, extra_headers={} if public else self._auth_header())

    def _post(self, path, data=None, public=False):
        return _http('POST', API_BASE + path, data=data,
                     extra_headers={} if public else self._auth_header())

    def _patch(self, path, data=None):
        return _http('PATCH', API_BASE + path, data=data, extra_headers=self._auth_header())

    def _delete(self, path, data=None):
        return _http('DELETE', API_BASE + path, data=data, extra_headers=self._auth_header())

    # ── Publics ───────────────────────────────────────────────
    def health(self):
        return self._get('/vehicle/services-health', public=True)

    def scanner_config(self):
        return self._get('/vehicle/scanner-config', public=True)

    def check_update(self, platform='android', version='2.3.0'):
        return _http('GET', API_BASE + '/vehicle/check-update',
                     extra_headers={'x-app-platform': platform, 'x-app-version': version})

    def marketplace_ads(self, page=1, limit=20, brand=None, model=None,
                        fuel=None, gearbox=None, department=None,
                        price_min=None, price_max=None,
                        year_min=None, year_max=None, mileage_max=None):
        return self._get('/marketplace/ads', params={
            'page': page, 'limit': limit, 'brand': brand, 'model': model,
            'fuel': fuel, 'gearbox': gearbox, 'department': department,
            'price_min': price_min, 'price_max': price_max,
            'year_min': year_min, 'year_max': year_max, 'mileage_max': mileage_max,
        }, public=True)

    def insurance_providers(self):
        return self._get('/app-users/insurance-providers', public=True)

    # ── Vehicle ───────────────────────────────────────────────
    def lookup(self, plate: str, origin: str = 'index'):
        """GET /vehicle/{plate}?origin=index|scanner"""
        p = normalize_plate(plate)
        return self._get(f'/vehicle/{p}', params={'origin': origin})

    def report(self, plate: str, errors: list, description: str = ''):
        return self._post('/vehicle/report', {
            'plate': normalize_plate(plate), 'errors': errors, 'description': description
        })

    def garage_vehicle(self, plate: str):
        return self._get('/vehicle/garage-vehicle', params={'plate': normalize_plate(plate)})

    # ── Profile ───────────────────────────────────────────────
    def my_profile(self):
        return self._get('/app-users/profile')

    def user_profile(self, uid: str):
        return self._get(f'/app-users/profile/{uid}')

    def set_user_type(self, user_type: str = 'particulier'):
        return self._patch('/app-users/user-type', {'user_type': user_type})

    # ── Garage ────────────────────────────────────────────────
    def my_garage(self, page=1, limit=20):
        return self._get('/app-users/garage', params={'page': page, 'limit': limit})

    def user_garage(self, uid: str, page=1, limit=20):
        return self._get(f'/app-users/{uid}/garage', params={'page': page, 'limit': limit})

    def add_to_garage(self, plate: str, nickname: str = '', is_main: bool = False):
        return self._post('/app-users/garage', {
            'plate': normalize_plate(plate), 'nickname': nickname, 'is_main_vehicle': is_main
        })

    # ── History / Favorites ───────────────────────────────────
    def search_history(self, page=1):
        return self._get('/app-users/search-history', params={'page': page})

    def clear_history(self):
        return self._delete('/app-users/clear-history')

    def search_favorites(self, page=1):
        return self._get('/app-users/search-favorites', params={'page': page})

    def clear_favorite(self, plate: str):
        return self._delete('/app-users/clear-favorite', {'plate': normalize_plate(plate)})

    # ── Social ────────────────────────────────────────────────
    def suggested_users(self, page=1):
        return self._get('/app-users/suggested-users', params={'page': page})

    def followers(self, uid: str, page=1):
        return self._get(f'/app-users/{uid}/followers', params={'page': page})

    def following(self, uid: str, page=1):
        return self._get(f'/app-users/{uid}/following', params={'page': page})

    def follow(self, uid: str):
        return self._post('/app-users/follow', {'uid': uid})

    def rate_vehicle(self, plate: str, rating: int, comment: str = ''):
        return self._post('/app-users/rate-vehicle', {
            'plate': normalize_plate(plate), 'rating': rating, 'comment': comment
        })

    def upload_image(self, plate: str, image_b64: str):
        return self._post('/upload-image', {'plate': normalize_plate(plate), 'image': image_b64})


# ── Display ───────────────────────────────────────────────────
def _items_flat(body: dict) -> dict:
    """Aplatit les categories de la réponse vehicle en un dict label->value."""
    flat = {}
    v = body.get('vehicle', {})
    h = v.get('header', {})
    flat['Plaque']   = h.get('plate', '')
    flat['Modele']   = f"{h.get('model', '')} {h.get('modelVersion', '')}".strip()
    flat['Tags']     = ', '.join(h.get('tags', []))

    for item in v.get('featuredItems', []):
        flat[item['label']] = item.get('value', '')

    for cat in v.get('categories', []):
        for item in cat.get('items', []):
            label = item.get('label', '')
            if not label or item.get('type') in ('communityButton', 'similarOwners'):
                continue
            val = item.get('value', '')
            if isinstance(val, list):
                # tires, fullTank, etc.
                if all(isinstance(x, str) for x in val):
                    val = ' | '.join(val)
                elif all(isinstance(x, dict) for x in val):
                    val = '  '.join(f"{x.get('name','')} {x.get('value','')} {x.get('cost','')}".strip() for x in val)
            elif isinstance(val, bool):
                val = 'Oui' if val else 'Non'
            elif isinstance(val, (int, float)) and item.get('unit'):
                val = f"{val} {item['unit']}"
            caption = item.get('caption', '')
            unit    = item.get('unit', '')
            if caption:
                val = f"{val}  ({caption})"
            elif unit and not str(val).endswith(unit):
                val = f"{val} {unit}"
            flat[label] = val

        # colonnes (boîte, freins, huile…)
        for item in cat.get('items', []):
            if item.get('type') == 'columns':
                cols = '  '.join(f"{c['label']} {c['value']}" for c in item.get('columns', []) if c.get('value'))
                if cols:
                    flat[item['label']] = cols

    # Communauté
    for cat in v.get('categories', []):
        for item in cat.get('items', []):
            if item.get('type') == 'similarOwners':
                flat['Proprietaires'] = f"{item.get('totalCount', 0)} connus sur la plateforme"

    return flat


def display_vehicle(body: dict):
    W = 64
    flat = _items_flat(body)

    print()
    print('=' * W)
    title = flat.get('Modele', flat.get('Plaque', 'VEHICULE'))
    print(f'  {title.upper()}')
    tags = flat.get('Tags', '')
    if tags:
        print(f'  {tags}')
    print('=' * W)

    PRIORITY = [
        'Plaque', 'Energie', 'Puissance', 'Transmission', 'Couple',
        '0 a 100km/h', '0 à 100km/h', 'Vitesse max',
        'Puissance Fiscale', 'Nombre de portes', 'Places assises',
        'Nb de vitesses', 'Roues motrices', 'Couleur', 'Carrosserie',
        'Critair', 'CO2 (g/km)', 'Prix neuf',
        'Cylindree', 'Cylindrée', 'Code moteur', 'Architecture',
        'Mise en circulation', 'VIN', 'CNIT', 'Norme euro',
        'Longueur (A)', 'Largeur (B)', 'Hauteur (C)',
        'Poids a vide', 'Poids à vide', 'Volume du coffre',
        'Mixte', 'Capacite reservoir', 'Capacité réservoir',
        'Pneus', 'Huile moteur', 'Freins', 'Boite de vitesses',
        'Proprietaires',
    ]

    printed = set()
    for label in PRIORITY:
        if label in flat and flat[label]:
            val = str(flat[label])[:W - 36]
            print(f'  {label:<32} {val}')
            printed.add(label)

    # reste non affiché
    for label, val in flat.items():
        if label not in printed and label not in ('Modele', 'Tags') and val:
            val_s = str(val)[:W - 36]
            print(f'  {label:<32} {val_s}')

    print('=' * W)


def display_garage(vehicles: list, title='Garage'):
    print(f'\n[{title}]  {len(vehicles)} vehicule(s)')
    for v in vehicles:
        plate = v.get('plate', '?')
        model = v.get('model', '?')
        ver   = v.get('modelVersion', '') or ''
        year  = v.get('year', '?')
        fuel  = v.get('fuel', '') or ''
        print(f'  {plate:10}  {model} {ver}  ({year})  {fuel}')


# ── CLI ───────────────────────────────────────────────────────
def main():
    import argparse

    ap = argparse.ArgumentParser(
        description='Immat Scanner — recherche de vehicule par plaque FR',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
exemples :
  py immat_scanner.py AB-351-PZ
  py immat_scanner.py AB-123-CD --email moi@gmail.com --password monmdp
  py immat_scanner.py AB-123-CD --appcheck-token "eyJ..."
  py immat_scanner.py --health
  py immat_scanner.py --marketplace --brand Peugeot --department 75
  py immat_scanner.py --profile

credentials par defaut : firebase_token.json (genere au premier --signup)
        """)

    ap.add_argument('plate',              nargs='?',        help='Plaque (ex: AB-351-PZ ou AB351PZ)')
    ap.add_argument('--email',                              help='Email Firebase')
    ap.add_argument('--password',                           help='Mot de passe Firebase')
    ap.add_argument('--token',                              help='ID Token Firebase direct')
    ap.add_argument('--appcheck-token',                     help='x-firebase-appcheck (depuis HTTP Toolkit sur vrai appareil)')
    ap.add_argument('--device-id',                          help='x-device-id personnalise (UUID)')
    ap.add_argument('--signup',           action='store_true', help='Creer un nouveau compte Firebase')
    ap.add_argument('--origin',           default='index',  help='index|scanner (defaut: index)')
    ap.add_argument('--json',             action='store_true', help='Afficher le JSON brut complet')
    ap.add_argument('--profile',          action='store_true', help='Mon profil')
    ap.add_argument('--garage',           action='store_true', help='Mon garage')
    ap.add_argument('--history',          action='store_true', help='Historique de recherche')
    ap.add_argument('--favorites',        action='store_true', help='Vehicules favoris')
    ap.add_argument('--health',           action='store_true', help='Etat des services API')
    ap.add_argument('--marketplace',      action='store_true', help='Annonces marketplace')
    ap.add_argument('--brand',                              help='Filtre marque (marketplace)')
    ap.add_argument('--model-filter',     dest='mfilter',   help='Filtre modele (marketplace)')
    ap.add_argument('--department',                         help='Filtre departement (marketplace)')
    ap.add_argument('--user-garage',      metavar='UID',    help='Garage public d\'un utilisateur')
    ap.add_argument('--user-profile',     metavar='UID',    help='Profil public d\'un utilisateur')
    args = ap.parse_args()

    global APP_CHECK_TOKEN
    if args.appcheck_token:
        APP_CHECK_TOKEN = args.appcheck_token
    if args.device_id:
        _APP_HEADERS['x-device-id'] = args.device_id

    # ── Auth ──────────────────────────────────────────────────
    if args.token:
        auth = FirebaseAuth(id_token=args.token)
        print('[+] Token fourni directement.')
    elif args.email and args.password:
        auth = FirebaseAuth(email=args.email, password=args.password)
        print(f'[+] Connexion ({args.email})...')
        auth.signin()
        auth.save()
        print('[+] Connecte. Credentials sauvegardes.')
    elif args.signup:
        auth = FirebaseAuth()
        print('[+] Creation d\'un compte Firebase...')
        auth.signup()
        ImmatAPI(auth).set_user_type('particulier')
        auth.save()
        print(f'[+] Compte cree : {auth.email}')
        print(f'    Mot de passe : {auth.password}')
        print(f'    Sauvegarde dans firebase_token.json')
    elif os.path.exists(_TOKEN_FILE):
        auth = FirebaseAuth.load(_TOKEN_FILE)
        print(f'[+] Credentials charges ({auth.email})')
    else:
        print('[!] Aucun credentials. Utilisez --email/--password ou --signup.')
        print('    Ex: py immat_scanner.py --signup')
        sys.exit(1)

    api = ImmatAPI(auth)

    # ── Actions ───────────────────────────────────────────────
    if args.health:
        _, body = api.health()
        print('[Services API]')
        for svc in body.get('data', []):
            ok = 'OK' if svc.get('is_healthy') else 'KO'
            print(f'  [{ok}] {svc["service_key"]}')
        return

    if args.marketplace:
        _, body = api.marketplace_ads(page=1, limit=10, brand=args.brand,
                                      model=args.mfilter, department=args.department)
        total = body.get('totalCount', 0)
        print(f'[Marketplace]  {total} annonces')
        for ad in body.get('data', []):
            price = ad.get('price_cents', 0) // 100
            print(f'  {ad.get("brand",""):12} {ad.get("model",""):20} '
                  f'{ad.get("reg_year",""):4}  {price:>6} EUR  '
                  f'{ad.get("mileage_km","?"):>6} km  {ad.get("fuel_label",""):<12} '
                  f'{ad.get("garage_name","")[:25]}')
        return

    if args.profile:
        _, body = api.my_profile()
        d = body.get('data', body)
        print('[Mon profil]')
        for k in ['username', 'xp', 'total_classic_searches', 'total_scanner_searches',
                  'streak_count', 'verified_garage_count', 'followers_count',
                  'following_count', 'user_type', 'plate_public']:
            if k in d:
                print(f'  {k:<30} {d[k]}')
        return

    if args.user_profile:
        _, body = api.user_profile(args.user_profile)
        d = body.get('data', body)
        print(f'[Profil {args.user_profile}]')
        for k, v in d.items():
            if k not in ('avatarConfig', 'social_links'):
                print(f'  {k:<30} {v}')
        return

    if args.garage:
        _, body = api.my_garage()
        display_garage(body.get('data', []), 'Mon Garage')
        return

    if args.user_garage:
        _, body = api.user_garage(args.user_garage)
        display_garage(body.get('data', []), f'Garage de {args.user_garage}')
        return

    if args.history:
        _, body = api.search_history()
        d = body.get('data', [])
        print(f'[Historique]  {len(d)} entrees')
        for h in d:
            print(f'  {h.get("plate","?"):10}  {h.get("searched_at","")}')
        return

    if args.favorites:
        _, body = api.search_favorites()
        d = body.get('data', [])
        print(f'[Favoris]  {len(d)} vehicules')
        for fav in d:
            print(f'  {fav.get("plate","?"):10}  {fav.get("brand","")}: {fav.get("model","")}')
        return

    if not args.plate:
        ap.print_help()
        sys.exit(0)

    # ── Lookup plaque ─────────────────────────────────────────
    raw   = args.plate
    plate = normalize_plate(raw)
    print(f'\n[+] Recherche : {raw} -> {plate}')

    status, body = api.lookup(plate, origin=args.origin)
    print(f'[+] HTTP {status}')

    if status == 200:
        if args.json:
            print(json.dumps(body, indent=2, ensure_ascii=False))
        else:
            display_vehicle(body)
            print('\nJSON complet avec --json')
        sys.exit(0)

    msg = body.get('message', json.dumps(body, ensure_ascii=False)[:200])

    if status == 403 and ('email' in msg.lower() or 'verifi' in msg.lower()):
        print(f'[!] Email non verifie (403) : {msg}')
        print('    Verifiez votre boite mail et cliquez sur le lien de confirmation Firebase.')

    elif status == 403:
        print(f'[!] Quota journalier depasse (403) : {msg}')
        print('    Reset a minuit (heure CET).')
        if APP_CHECK_TOKEN:
            print('    Conseil : le token App Check a peut-etre expire (TTL ~1h).')

    elif status == 401:
        print(f'[!] Non autorise (401) : {msg}')
        print('    -> py immat_scanner.py --signup   (creer un compte)')
        print('    -> py immat_scanner.py PLAQUE --email vous@gmail.com --password mdp')

    elif status == 404:
        print('[!] Plaque introuvable dans la base Immat Scanner.')

    else:
        print(f'[!] Erreur {status} : {msg}')

    sys.exit(1)


if __name__ == '__main__':
    main()
