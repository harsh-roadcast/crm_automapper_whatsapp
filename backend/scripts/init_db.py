import asyncio

import backend.app.models  # noqa: F401
from backend.app.core.database import Base, engine


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def main() -> None:
    asyncio.run(init_database())
    print("Database tables are ready.")


if __name__ == "__main__":
    main()