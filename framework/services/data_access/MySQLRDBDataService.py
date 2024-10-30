from fastapi import HTTPException
from pymysql.err import IntegrityError
from typing import List, Dict
import pymysql
from sqlalchemy.dialects.mssql.information_schema import columns
from sympy.physics.vector.printing import params
from torch.utils.hipify.hipify_python import value

from .BaseDataService import DataDataService


class MySQLRDBDataService(DataDataService):
    """
    A generic data service for MySQL databases. The class implement common
    methods from BaseDataService and other methods for MySQL. More complex use cases
    can subclass, reuse methods and extend.
    """

    def __init__(self, context):
        super().__init__(context)

    def _get_connection(self):
        connection = pymysql.connect(
            host=self.context["host"],
            port=self.context["port"],
            user=self.context["user"],
            passwd=self.context["password"],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        return connection

    def get_data_object(self,
                        database_name: str,
                        collection_name: str,
                        key_field: str,
                        key_value: str):
        """
        See base class for comments.
        """

        connection = None
        result = None

        try:
            sql_statement = f"SELECT * FROM {database_name}.{collection_name} " + \
                        f"where {key_field}=%s"
            connection = self._get_connection()
            cursor = connection.cursor()
            cursor.execute(sql_statement, [key_value])
            result = cursor.fetchone()
        except Exception as e:
            if connection:
                connection.close()

        return result

    def get_data_objects(self, database_name: str, collection_name: str, limit: int = None, offset: int = None) -> List[Dict]:
        sql_statement = f"SELECT * FROM {database_name}.{collection_name}"
        params = []
        if limit is not None:
            sql_statement += " LIMIT %s "
            params.append(limit)
            if offset is not None:
                sql_statement += " OFFSET %s "
                params.append(offset)
            elif offset is not None:
                sql_statement += "LIMIT 2147483647 OFFSET %s "
                params.append(offset)
            self.cursor.execute(sql_statement, params)
            result = self.cursor.fetchall()
            return result

    def create_data_object(self, database, table, userdata):
        connection = None
        result = None
        cursor = None

        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            columns = ','.join(f"{key}" for key in userdata.keys())
            placeholders = ','.join(["%s"] * len(userdata.keys()))
            vals = tuple(userdata.values())

            sqlInsert = f"INSERT INTO {database}.{table} ({columns}) VALUES ({placeholders})"
            cursor.execute(sqlInsert, vals)

            lastuser = cursor.lastrowid
            userdata['id'] = lastuser
            result = userdata

        except IntegrityError as e:
            raise HTTPException(status_code=400,detail="Email has already been registered")
        except Exception as e:
            raise HTTPException(status_code=500,detail="Internal Server Error")

        return result










