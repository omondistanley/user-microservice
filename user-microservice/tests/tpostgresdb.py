from framework.services.data_access.PostgresRDBDataService import PostgresRDBDataService
import json


def get_db_service():
    context = dict(
        user="postgres",
        password="postgres",
        host="localhost",
        port=5432,
        dbname="users_db",
    )
    data_service = PostgresRDBDataService(context=context)
    return data_service


def t1():
    data_service = get_db_service()
    result = data_service.get_data_object(
        "users_db",
        "user",
        key_field="email",
        key_value="test@example.com",
    )
    print("t1 result = \n", json.dumps(result, indent=4, default=str))


if __name__ == "__main__":
    t1()
