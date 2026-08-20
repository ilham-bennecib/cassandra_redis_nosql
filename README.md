# Projet NoSQL & Big Data - TMDB (Cassandra + Redis)

Projet réalisé en solo dans le cadre du TP NoSQL & Big Data (IPSSI). Dataset et
choix de bases de données (Cassandra + Redis) validés par le formateur.

## Contexte et choix techniques

- **Dataset** : [TMDB 5000 Movies](https://www.kaggle.com/datasets/tmdb/tmdb-movie-metadata)
  (Kaggle) - `tmdb_5000_movies.csv` + `tmdb_5000_credits.csv`, 4803 films.
- **Bases de données** :
  - **Cassandra** (via [Astra DB](https://astra.datastax.com), le service managé
    DataStax) : source de vérité, catalogue complet des films, modélisé en
    *query-first design* (une table par question-métier, quitte à dupliquer).
  - **Redis** (via [Redis Cloud](https://redis.com/try-free)) : cache par film et
    classements (leaderboards) pour les lectures les plus fréquentes, construits
    à partir des données Cassandra.

Le détail de la conception (tables Cassandra, clés de partition/clustering,
questions-métier) est expliqué dans le notebook `02_modelisation_ingestion.ipynb`.

## Structure du dépôt

```
.
├── notebooks/
│   ├── 01_exploration_nettoyage.ipynb    # Exploration + nettoyage des données
│   ├── 02_modelisation_ingestion.ipynb   # Modélisation Cassandra + ingestion + CRUD
│   ├── 03_rapport_analytique.ipynb       # Questions-métier, requêtes, visualisations
│   └── 04_administration.ipynb           # Dump/restauration, perf, sécurité
├── app.py                # WebApp Streamlit (démo locale)
├── test_connexion.py     # Script de vérification rapide des connexions Cassandra/Redis
├── requirements.txt      # Dépendances Python (notebooks + app)
├── .env.example          # Modèle de fichier .env à copier et remplir
├── tmdb_5000_movies.csv / tmdb_5000_credits.csv   # Dataset source
└── secure-connect-tmdb-platform.zip                # Bundle Astra (à ta charge, non fourni)
```

## Prérequis

- Python 3.11
- Une base Astra DB (tier gratuit) et son secure connect bundle (fichier `.zip`
  téléchargeable depuis la console Astra, section "Connect")
- Une base Redis Cloud (tier gratuit)

## Installation

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Copie `.env.example` vers `.env` et remplis tes propres valeurs (token Astra,
host/port/mot de passe Redis). Place aussi ton secure connect bundle Astra à la
racine du projet (nom par défaut attendu : `secure-connect-tmdb-platform.zip`,
modifiable via `ASTRA_DB_BUNDLE_PATH` dans `.env`).

Vérifie que tout est bien connecté :
```powershell
python test_connexion.py
```
Tu dois voir `OK - connectée à Cassandra` et `OK - connectée à Redis`.

## Lancer les notebooks

Les notebooks se lancent **dans l'ordre**, chacun pouvant être exécuté
indépendamment une fois que le précédent a fait son travail (les données sont
dans Cassandra/Redis, pas juste en mémoire) :

```powershell
jupyter notebook
```
Puis ouvrir dans l'ordre : `01_exploration_nettoyage.ipynb` →
`02_modelisation_ingestion.ipynb` → `03_rapport_analytique.ipynb` →
`04_administration.ipynb`.

Le notebook `02` crée les tables et insère les ~4800 films - à ne lancer qu'une
fois (les insertions suivantes sont sans risque, `CREATE TABLE IF NOT EXISTS`
et les mêmes `movie_id` réécrivent les mêmes lignes).

## Lancer la WebApp (démonstration locale)

```powershell
streamlit run app.py
```
Ouvre ensuite `http://localhost:8501` dans le navigateur. L'app propose 6
pages (top 10 Redis, top par genre, filmographie d'un réalisateur, films d'un
acteur, nombre de films par année, démo CRUD en direct), toutes branchées sur
les mêmes tables Cassandra/Redis que les notebooks.

**Note sur le déploiement** : un déploiement en ligne (Heroku, puis Streamlit
Community Cloud) a été tenté puis abandonné (contraintes de compte/temps sans
rapport avec le code lui-même) - décision actée avec le formateur de présenter
la WebApp en local uniquement. Le code reste prêt à déployer : `app.py` gère
déjà la reconstruction du secure connect bundle depuis une variable
d'environnement encodée en base64 (`ASTRA_DB_BUNDLE_B64`) pour les plateformes
qui ne permettent pas d'uploader ce fichier directement.

## Scripts d'administration

Dump, restauration, import de fichiers volumineux, optimisations de
performance et sécurisation sont couverts et testés dans
`notebooks/04_administration.ipynb` (avec un vrai cycle
supprimer → vérifier → restaurer → revérifier, pas une simulation).

## Auteure

Ilham Bennecib - IPSSI
