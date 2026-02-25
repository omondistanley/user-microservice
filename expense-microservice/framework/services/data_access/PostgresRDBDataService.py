from fastapi import HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict

from .BaseDataService import DataDataService


class PostgresRDBDataService(DataDataService):
    """
    Generic PostgreSQL data service. database_name = schema, collection_name = table.
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
        try:
            sql_statement = (
                f'SELECT * FROM "{database_name}"."{collection_name}" '
                f'WHERE "{key_field}"=%s'
            )
            connection = self._get_connection()
            cursor = connection.cursor()
            cursor.execute(sql_statement, [key_value])
            result = cursor.fetchone()
            if result is not None:
                result = dict(result)
        except Exception:
            raise
        finally:
            if connection:
                connection.close()
        return result

    def get_data_objects(self, database_name: str, collection_name: str,
                         limit: int = None, offset: int = None) -> List[Dict]:
        connection = None
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
            return []
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=500, detail="Internal Server Error")
        finally:
            if connection:
                connection.close()
