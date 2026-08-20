"""
WebApp de démonstration - Projet NoSQL TMDB (Cassandra + Redis)

Cette app Streamlit interroge directement les deux bases mises en place
dans les notebooks 02/03/04. Elle ne réécrit aucune logique métier : elle
réutilise exactement les mêmes requêtes que le rapport analytique, mais
dans une interface cliquable plutôt qu'un notebook.
"""

import os
import base64
import tempfile
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from cassandra.cluster import Cluster, ProtocolVersion
from cassandra.auth import PlainTextAuthProvider
import redis

# set_page_config() doit être la toute première commande Streamlit du script,
# avant même l'accès à st.secrets ci-dessous - sinon Streamlit lève une erreur.
st.set_page_config(page_title="TMDB - Cassandra & Redis", page_icon="🎬", layout="wide")

load_dotenv()

# Sur Streamlit Community Cloud, il n'y a pas de fichier .env : les secrets sont
# définis via l'interface web (onglet "Secrets") et exposés par st.secrets. On ne
# touche à st.secrets que si une variable clé manque déjà (donc jamais en local,
# où .env suffit) - ça évite le message "No secrets found" de Streamlit en local.
if "ASTRA_DB_APPLICATION_TOKEN" not in os.environ:
    try:
        for key, value in st.secrets.items():
            os.environ.setdefault(key, str(value))
    except Exception:
        pass


# ------------------------------------------------------------------
# Connexions (mises en cache par Streamlit : ne se reconnectent pas
# à chaque interaction de l'utilisateur, seulement au démarrage)
# ------------------------------------------------------------------

def get_bundle_path():
    """Retourne le chemin du secure connect bundle.

    En local, il vient du fichier pointé par ASTRA_DB_BUNDLE_PATH (.env).
    En déploiement, ce fichier n'est volontairement pas commité dans le repo
    (public) : on le reconstruit à la place depuis ASTRA_DB_BUNDLE_B64, une
    variable d'environnement contenant le zip encodé en base64.
    """
    bundle_path = os.environ.get("ASTRA_DB_BUNDLE_PATH")
    if bundle_path and os.path.exists(bundle_path):
        return bundle_path

    b64 = os.environ.get("ASTRA_DB_BUNDLE_B64")
    if not b64:
        raise RuntimeError(
            "Ni ASTRA_DB_BUNDLE_PATH (fichier local) ni ASTRA_DB_BUNDLE_B64 "
            "(variable d'env base64, utilisée en déploiement) ne sont disponibles."
        )

    tmp_path = os.path.join(tempfile.gettempdir(), "secure-connect-tmdb-platform.zip")
    with open(tmp_path, "wb") as f:
        f.write(base64.b64decode(b64))
    return tmp_path


@st.cache_resource
def get_cassandra_session():
    cloud_config = {
        "secure_connect_bundle": get_bundle_path(),
        "connect_timeout": 30,
    }
    auth_provider = PlainTextAuthProvider(
        username="token",
        password=os.environ["ASTRA_DB_APPLICATION_TOKEN"],
    )
    cluster = Cluster(cloud=cloud_config, auth_provider=auth_provider, protocol_version=ProtocolVersion.V4)
    session = cluster.connect()
    session.set_keyspace("tmdb_platform")
    return session


@st.cache_resource
def get_redis_client():
    return redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ["REDIS_PASSWORD"],
        username=os.environ.get("REDIS_USERNAME", "default"),
        decode_responses=True,
    )


try:
    session = get_cassandra_session()
    redis_client = get_redis_client()
    connexion_ok = True
except Exception as e:
    connexion_ok = False
    connexion_erreur = str(e)


# ------------------------------------------------------------------
# En-tête
# ------------------------------------------------------------------

st.title("🎬 Projet NoSQL & Big Data - TMDB")
st.caption("Benchmark Cassandra (colonnes larges) vs Redis (clé-valeur) sur le dataset TMDB 5000")

if not connexion_ok:
    st.error(
        "Impossible de se connecter aux bases. Vérifie que les variables "
        "d'environnement (ASTRA_DB_BUNDLE_PATH, ASTRA_DB_APPLICATION_TOKEN, "
        "REDIS_HOST, REDIS_PORT, REDIS_PASSWORD) sont bien définies."
    )
    st.code(connexion_erreur)
    st.stop()

st.success("Connectée à Cassandra (Astra DB) et Redis (Redis Cloud).")


# ------------------------------------------------------------------
# Navigation
# ------------------------------------------------------------------

page = st.sidebar.radio(
    "Section",
    [
        "Top 10 (Redis)",
        "Top par genre (Cassandra)",
        "Filmographie d'un réalisateur (Cassandra)",
        "Films d'un acteur (Cassandra)",
        "Nombre de films par année (Cassandra)",
        "CRUD - démonstration en direct",
    ],
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Rappel de conception** : Cassandra stocke le catalogue complet "
    "(source de vérité, requêtes filtrées sur une clé connue), Redis stocke "
    "un cache/classement dérivé pour les lectures les plus fréquentes."
)


# ------------------------------------------------------------------
# Page 1 : Top 10 (Redis)
# ------------------------------------------------------------------

if page == "Top 10 (Redis)":
    st.header("Top 10 des films les mieux notés")
    st.caption("Source : Redis, sorted set `leaderboard:top_rated` (ZREVRANGE)")

    top_n = st.slider("Nombre de films à afficher", 5, 30, 10)

    top = redis_client.zrevrange("leaderboard:top_rated", 0, top_n - 1, withscores=True)

    rows = []
    for movie_id, score in top:
        infos = redis_client.hgetall(f"movie:{movie_id}")
        rows.append({
            "Titre": infos.get("title", "?"),
            "Année": infos.get("release_year", "?"),
            "Réalisateur": infos.get("director", "?"),
            "Note pondérée": round(score, 2),
        })

    df_top = pd.DataFrame(rows)
    st.dataframe(df_top, use_container_width=True, hide_index=True)
    st.bar_chart(df_top.set_index("Titre")["Note pondérée"])


# ------------------------------------------------------------------
# Page 2 : Top par genre (Cassandra)
# ------------------------------------------------------------------

elif page == "Top par genre (Cassandra)":
    st.header("Top films par genre")
    st.caption(
        "Source : Cassandra, table `movies_by_genre` "
        "(partition = genre, clustering = weighted_rating DESC)"
    )

    genres_disponibles = [
        "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
        "Drama", "Family", "Fantasy", "History", "Horror", "Music",
        "Mystery", "Romance", "Science Fiction", "Thriller", "War", "Western",
    ]
    genre = st.selectbox("Choisir un genre", genres_disponibles, index=genres_disponibles.index("Drama"))
    limite = st.slider("Nombre de films", 3, 20, 10)

    rows = session.execute(
        "SELECT title, weighted_rating, vote_count FROM movies_by_genre WHERE genre = %s LIMIT %s",
        (genre, limite),
    )
    rows = list(rows)

    if not rows:
        st.warning(f"Aucun film trouvé pour le genre '{genre}'.")
    else:
        df_genre = pd.DataFrame([
            {"Titre": r.title, "Note pondérée": round(r.weighted_rating, 2), "Nb votes": r.vote_count}
            for r in rows
        ])
        st.dataframe(df_genre, use_container_width=True, hide_index=True)
        st.bar_chart(df_genre.set_index("Titre")["Note pondérée"])


# ------------------------------------------------------------------
# Page 3 : Filmographie d'un réalisateur (Cassandra)
# ------------------------------------------------------------------

elif page == "Filmographie d'un réalisateur (Cassandra)":
    st.header("Filmographie d'un réalisateur")
    st.caption(
        "Source : Cassandra, table `movies_by_director` "
        "(partition = director, clustering = release_year DESC)"
    )

    realisateur = st.text_input("Nom du réalisateur", value="Steven Spielberg")

    if realisateur:
        rows = session.execute(
            "SELECT title, release_year, weighted_rating FROM movies_by_director WHERE director = %s",
            (realisateur,),
        )
        rows = list(rows)

        if not rows:
            st.warning(f"Aucun film trouvé pour '{realisateur}'. Vérifie l'orthographe exacte (sensible à la casse).")
        else:
            avg_row = session.execute(
                "SELECT AVG(weighted_rating) AS avg_rating FROM movies_by_director WHERE director = %s",
                (realisateur,),
            ).one()

            col1, col2 = st.columns(2)
            col1.metric("Films trouvés", len(rows))
            col2.metric("Note moyenne pondérée (AVG natif CQL)", f"{avg_row.avg_rating:.2f}")

            df_director = pd.DataFrame([
                {"Année": r.release_year, "Titre": r.title, "Note pondérée": round(r.weighted_rating, 2)}
                for r in rows
            ])
            st.dataframe(df_director, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------
# Page 4 : Films d'un acteur (Cassandra)
# ------------------------------------------------------------------

elif page == "Films d'un acteur (Cassandra)":
    st.header("Films dans lesquels a joué un acteur")
    st.caption(
        "Source : Cassandra, table `movies_by_actor` "
        "(partition = actor_name ; pas de clustering order pertinent ici, "
        "le tri par année est fait côté application)"
    )

    acteur = st.text_input("Nom de l'acteur / actrice", value="Samuel L. Jackson")

    if acteur:
        rows = session.execute(
            "SELECT title, release_year FROM movies_by_actor WHERE actor_name = %s",
            (acteur,),
        )
        rows = list(rows)

        if not rows:
            st.warning(f"Aucun film trouvé pour '{acteur}'.")
        else:
            rows_triees = sorted(rows, key=lambda r: r.release_year or 0, reverse=True)
            df_acteur = pd.DataFrame([
                {"Année": r.release_year, "Titre": r.title} for r in rows_triees
            ])
            st.metric("Films trouvés (dans le top 5 du casting)", len(rows))
            st.dataframe(df_acteur, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------
# Page 5 : Nombre de films par année (Cassandra)
# ------------------------------------------------------------------

elif page == "Nombre de films par année (Cassandra)":
    st.header("Nombre de films par année")
    st.caption(
        "Source : Cassandra, table `movies_by_year` (partition = release_year). "
        "Une requête par année est nécessaire (pas de GROUP BY en CQL)."
    )

    col1, col2 = st.columns(2)
    annee_debut = col1.number_input("Année de début", value=1990, min_value=1916, max_value=2016)
    annee_fin = col2.number_input("Année de fin", value=2016, min_value=1916, max_value=2016)

    if st.button("Lancer les requêtes"):
        annees = range(int(annee_debut), int(annee_fin) + 1)
        progress = st.progress(0.0)
        counts = {}
        for i, annee in enumerate(annees):
            result = session.execute(
                "SELECT COUNT(*) FROM movies_by_year WHERE release_year = %s", (annee,)
            ).one()
            counts[annee] = result.count
            progress.progress((i + 1) / len(annees))

        df_annees = pd.DataFrame({"Année": list(counts.keys()), "Nombre de films": list(counts.values())})
        st.line_chart(df_annees.set_index("Année"))
        st.caption(f"{len(annees)} requêtes Cassandra envoyées, une par partition (année).")


# ------------------------------------------------------------------
# Page 6 : CRUD - démonstration en direct
# ------------------------------------------------------------------

elif page == "CRUD - démonstration en direct":
    st.header("Démonstration CRUD en direct")
    st.caption(
        "Sur un film de test (movie_id fictif) pour ne jamais toucher aux "
        "vraies données pendant la démo."
    )

    TEST_MOVIE_ID = 999999

    col1, col2, col3, col4 = st.columns(4)

    if col1.button("1. Create"):
        insert_stmt = session.prepare("""
            INSERT INTO movies_by_id
            (movie_id, title, director, main_cast, genres, release_year, release_date,
             runtime, budget, revenue, popularity, vote_average, vote_count,
             weighted_rating, original_language, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)
        session.execute(insert_stmt, (
            TEST_MOVIE_ID, "Mon Film Test (démo webapp)", "Réalisateur Test",
            ["Acteur A", "Acteur B"], ["Comedy"], 2024, "2024-01-01", 100.0,
            1_000_000, 2_000_000, 5.0, 7.0, 42, 6.5, "fr", "Released",
        ))
        st.success("Film test créé dans Cassandra (movies_by_id).")

    if col2.button("2. Read"):
        rows = list(session.execute(
            "SELECT movie_id, title, vote_average FROM movies_by_id WHERE movie_id = %s",
            (TEST_MOVIE_ID,),
        ))
        if rows:
            st.json({"movie_id": rows[0].movie_id, "title": rows[0].title, "vote_average": rows[0].vote_average})
        else:
            st.warning("Aucun film test trouvé - clique d'abord sur Create.")

    if col3.button("3. Update"):
        session.execute(
            "UPDATE movies_by_id SET vote_average = %s WHERE movie_id = %s",
            (8.0, TEST_MOVIE_ID),
        )
        st.success("vote_average mis à jour à 8.0.")

    if col4.button("4. Delete"):
        session.execute("DELETE FROM movies_by_id WHERE movie_id = %s", (TEST_MOVIE_ID,))
        st.success("Film test supprimé.")

    st.markdown("---")
    st.caption(
        "Piège Cassandra : `UPDATE`/`DELETE` exigent la clé primaire complète "
        "(`movie_id` ici) - impossible de filtrer sur un autre champ comme en SQL."
    )
