from fastapi import FastAPI, HTTPException, Body, status
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any
from bson import ObjectId

# Create FastAPI app
app = FastAPI()

# MongoDB setup
MONGODB_URL = "mongodb://localhost:27017"

# ObjectId handling
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
        
    @classmethod
    def validate(cls, v, info):  # Add the info parameter to match Pydantic v2 expectations
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)
        
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema, _):
        field_schema.update(type="string")
        return field_schema

# User models - combined for simplicity
class UserModel(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    name: str
    age: int
    
    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v):
        if not v or v.strip() == "":
            raise ValueError("Name cannot be empty")
        return v
    
    model_config = {
        "validate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str}
    }

# Database setup
@app.on_event("startup")
async def startup_db_client():
    app.mongodb = AsyncIOMotorClient(MONGODB_URL)["userdb"]

@app.on_event("shutdown")
async def shutdown_db_client():
    app.mongodb.client.close()

@app.get("/")
async def root():
    return {"success": True}

# CRUD operations
@app.post("/users/", response_model=UserModel, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserModel = Body(...)):
    user_dict = {k: v for k, v in user.model_dump(by_alias=True).items() if k != "_id" or v is not None}
    new_user = await app.mongodb["users"].insert_one(user_dict)
    return await app.mongodb["users"].find_one({"_id": new_user.inserted_id})

@app.get("/users/", response_model=List[UserModel])
async def list_users():
    return await app.mongodb["users"].find().to_list(1000)

@app.get("/users/{id}", response_model=UserModel)
async def get_user(id: str):
    if user := await app.mongodb["users"].find_one({"_id": ObjectId(id)}):
        return user
    raise HTTPException(status_code=404, detail=f"User with ID {id} not found")

@app.put("/users/{id}", response_model=UserModel)
async def update_user(id: str, user: UserModel = Body(...)):
    update_data = {k: v for k, v in user.model_dump(exclude_unset=True).items() if k != "id" and v is not None}
    
    if update_data:
        await app.mongodb["users"].update_one({"_id": ObjectId(id)}, {"$set": update_data})
    
    if user := await app.mongodb["users"].find_one({"_id": ObjectId(id)}):
        return user
    raise HTTPException(status_code=404, detail=f"User with ID {id} not found")

@app.delete("/users/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(id: str):
    if (await app.mongodb["users"].delete_one({"_id": ObjectId(id)})).deleted_count:
        return
    raise HTTPException(status_code=404, detail=f"User with ID {id} not found")