from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import pymysql
from pydantic import BaseModel


#check for the user existense - throw error
#create a new user and add the user to the db
#return user with the user id and stuff
#implement error checks in all these cases

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"])

try:
    db_connection = pymysql.connect(
    host="localhost",
    user="root",
    password="dbuserdbuser",
    db="users_db"
    )
    print("Database connection established")

    db_cursor = db_connection.cursor()

    @app.get("/")
    async def root():
        print("Root route")
        return {"message": "Base"}


    @app.get("/select_all")
    async def select():
        db_cursor.execute("SELECT * FROM users")
        print(db_cursor.fetchall())
        return db_cursor.fetchall()

    @app.get("/select_one")
    async def select_one():
        try:
            db_cursor.execute("SELECT email FROM users")
            return db_cursor.fetchone()
        except Exception as e:
            print("user not found")


except pymysql.Error as e:
    print("Internal server error")



