"""Extra Postgres types missing from SQLAlchemy."""

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import UserDefinedType


class Ltree(UserDefinedType[str]):
    """The ltree column type expressed through str.

    Postgres transmits ltree in text format and psycopg decodes unknown types to str, so it's
    bidirectional.
    """

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "LTREE"


# reflection otherwise degrades ltree columns to NullType
ischema_names["ltree"] = Ltree  # pyright: ignore[reportArgumentType] -- stub only lists builtin PG types
