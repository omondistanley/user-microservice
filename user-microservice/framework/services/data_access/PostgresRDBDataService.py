from fastapi import HTTPException
import psycopg2
from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor
from typing import Any, List, Dict

from .BaseDataService import DataDataService


class PostgresRDBDataService(DataDataService):
    """
    A generic data service for PostgreSQL databases. Implements common
    methods from BaseDataService. database_name is used as schema name,
    collection_name as table name (e.g. users_db.user).
    """

    def __init__(self, context):
        super().__init__(context)

    def _get_connection(self):
        connection = psycopg2.connect(
            host=self.context["host"],
            port=self.context["port"],
            user=self.context["user"],
            password=self.context["password"],
            dbname=self.context["dbname"],
            cursor_factory=RealDictCursor,
        )
        connection.autocommit = True
        return connection

    def get_data_object(self,
                        database_name: str,
                        collection_name: str,
                        key_field: str,
                        key_value: str):
        connection = None
        result = None
        try:
            sql_statement = (
                f'SELECT * FROM "{database_name}"."{collection_name}" '
                f"WHERE {key_field}=%s"
            )
            connection = self._get_connection()
            cursor = connection.cursor()
            cursor.execute(sql_statement, [key_value])
            result = cursor.fetchone()
            if result is not None:
                result = dict(result)
        except Exception as e:
            raise
        finally:
            if connection:
                connection.close()
        return result

    def get_data_objects(self, database_name: str, collection_name: str, limit: int = None, offset: int = None) -> List[Dict]:
        connection = None
        result = None
        try:
            sql_statement = f'SELECT * FROM "{database_name}"."{collection_name}"'
            params = []
            if limit is not None:
                sql_statement += " LIMIT %s "
                params.append(limit)
                if offset is not None:
                    sql_statement += " OFFSET %s "
                    params.append(offset)
            connection = self._get_connection()
            cursor = connection.cursor()
            cursor.execute(sql_statement, params)
            result = cursor.fetchall()
            if result is not None:
                return [dict(row) for row in result]
            else:
                raise HTTPException(status_code=404, detail="No users found")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail="Internal Server Error")
        finally:
            if connection:
                connection.close()

    def create_data_object(self, database, table, userdata):
        connection = None
        result = None
        cursor = None
        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            columns = ",".join(f'"{k}"' for k in userdata.keys())
            placeholders = ",".join(["%s"] * len(userdata.keys()))
            vals = tuple(userdata.values())

            sql_insert = (
                f'INSERT INTO "{database}"."{table}" ({columns}) '
                f"VALUES ({placeholders}) RETURNING id"
            )
            cursor.execute(sql_insert, vals)
            row = cursor.fetchone()
            new_id = row["id"] if row else None
            userdata["id"] = new_id
            result = userdata
        except IntegrityError as e:
            raise HTTPException(status_code=400, detail="Email has already been registered")
        except Exception as e:
            # Surface DB error so missing columns etc. are visible (e.g. in dev)
            raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")
        finally:
            if connection:
                connection.close()
        return result

    def get_data_object_where(self, database_name: str, collection_name: str, where: Dict[str, Any]):
        """Fetch one row matching all key=value pairs in where. Returns dict or None."""
        if not where:
            return None
        connection = None
        try:
            keys = list(where.keys())
            conditions = " AND ".join(f'"{k}"=%s' for k in keys)
            sql = f'SELECT * FROM "{database_name}"."{collection_name}" WHERE {conditions}'
            connection = self._get_connection()
            cursor = connection.cursor()
            cursor.execute(sql, [where[k] for k in keys])
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            if connection:
                connection.close()

    def update_data_object(self, database: str, table: str, id_value: int, updates: Dict[str, Any]):
        """Update row by id. updates is dict of column -> value."""
        if not updates:
            return
        connection = None
        try:
            cols = list(updates.keys())
            set_clause = ", ".join(f'"{k}"=%s' for k in cols)
            vals = [updates[k] for k in cols]
            vals.append(id_value)
            sql = f'UPDATE "{database}"."{table}" SET {set_clause} WHERE id=%s'
            connection = self._get_connection()
            cursor = connection.cursor()
            cursor.execute(sql, vals)
        finally:
            if connection:
                connection.close()
