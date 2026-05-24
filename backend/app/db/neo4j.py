from app.config import settings


class Neo4jManager:
    def __init__(self) -> None:
        from neo4j import AsyncGraphDatabase
        self.driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    async def verify_connectivity(self) -> bool:
        await self.driver.verify_connectivity()
        return True

    async def close(self) -> None:
        await self.driver.close()

    def session(self):
        return self.driver.session()


_instance = None


def get_neo4j_manager():
    global _instance
    if _instance is None:
        _instance = Neo4jManager()
    return _instance
