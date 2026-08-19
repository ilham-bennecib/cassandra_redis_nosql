import os
from dotenv import load_dotenv

load_dotenv()  # lit le fichier .env

print("--- Test de connexion Cassandra (Astra DB) ---")
try:
    from cassandra.cluster import Cluster, ProtocolVersion
    from cassandra.auth import PlainTextAuthProvider

    cloud_config = {"secure_connect_bundle": os.environ["ASTRA_DB_BUNDLE_PATH"]}
    auth_provider = PlainTextAuthProvider(
        username="token",
        password=os.environ["ASTRA_DB_APPLICATION_TOKEN"],
    )
    cluster = Cluster(
        cloud=cloud_config,
        auth_provider=auth_provider,
        protocol_version=ProtocolVersion.V4
    )
    session = cluster.connect()
    row = session.execute("SELECT release_version FROM system.local").one()
    print("OK - connectée à Cassandra, version :", row.release_version)
except Exception as e:
    print("ECHEC Cassandra :", type(e).__name__, "-", e)

print()
print("--- Test de connexion Redis ---")
try:
    import redis

    redis_client = redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ["REDIS_PORT"]),
        password=os.environ["REDIS_PASSWORD"],
        username=os.environ.get("REDIS_USERNAME", "default"),
        decode_responses=True,
    )
    print("OK - connectée à Redis :", redis_client.ping())
except Exception as e:
    print("ECHEC Redis :", type(e).__name__, "-", e)