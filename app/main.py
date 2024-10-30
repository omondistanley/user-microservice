from fastapi import Depends, FastAPI, HTTPException
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from app.resources.user_resource import UserResource
from app.services.service_factory import ServiceFactory
from app.routers import users

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*']
)


app.include_router(users.router)


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}

@app.get("/users/{email}") #to get a specific user from db using the email
async def user(email):
    try:
        val = ServiceFactory.get_service("UserResource")
        user = val.get_by_email(email)
        if user is None:
            raise HTTPException(status_code=404, detail=str("User not found"))
        return user
    except Exception as e:
        raise HTTPException(status_code=500, detail=str("Internal Server Error"))

'''@app.post("/users/{email}")'''

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)



