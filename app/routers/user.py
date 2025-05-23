from fastapi import APIRouter, Depends, HTTPException, status, Form
from typing import List
from app.models.user import User, UserCreate
from app.db.mongodb import get_database
from app.core.config import settings
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from bson import ObjectId
import logging
from pydantic import BaseModel, EmailStr
from app.core.security import get_password_hash
from app.services.auth import auth_service
from app.models.user import Token
from datetime import datetime, timedelta

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)

# Configure OAuth2 with the correct token URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_db():
    return get_database()

@router.post("/", response_model=User)
async def create_user(user: UserCreate, db=Depends(get_db)):
    # Check if user already exists
    if await db["users"].find_one({"email": user.email}):
        raise HTTPException(
            status_code=400,
            detail="User with this email already exists"
        )
    
    # Insert user
    user_dict = user.dict()
    
    # Hash password if it's not already hashed
    if "password" in user_dict and not user_dict.get("hashed_password"):
        user_dict["hashed_password"] = get_password_hash(user_dict.pop("password"))
    
    result = await db["users"].insert_one(user_dict)
    
    # Return created user
    created_user = await db["users"].find_one({"_id": result.inserted_id})
    created_user["id"] = str(created_user["_id"])
    
    # Don't return hashed_password
    if "hashed_password" in created_user:
        created_user.pop("hashed_password")
    
    return User(**created_user)

@router.get("/{id}", response_model=User)
async def get_user(id: str, db=Depends(get_db)):
    try:
        # Convert string ID to ObjectId for MongoDB lookup
        user = await db["users"].find_one({"_id": ObjectId(id)})
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
            
        # After fetching user from db, convert _id to string and remove _id
        if user:
            user["id"] = str(user["_id"])
            user.pop("_id", None)
            # Don't return hashed_password
            if "hashed_password" in user:
                user.pop("hashed_password")
            return User(**user)
    except Exception as e:
        logging.error(f"Error retrieving user: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail="User not found or invalid ID format"
        )

@router.get("/me", response_model=User)
async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode the JWT token
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        
        if user_id is None:
            raise credentials_exception
    except JWTError as e:
        logging.error(f"JWT error: {str(e)}")
        raise credentials_exception
        
    try:
        # Get user from database
        user = await db["users"].find_one({"_id": ObjectId(user_id)})
        
        if user is None:
            raise credentials_exception
            
        # After fetching user from db, convert _id to string and remove _id
        if user:
            user["id"] = str(user["_id"])
            user.pop("_id", None)
            # Don't return hashed_password
            if "hashed_password" in user:
                user.pop("hashed_password")
            return User(**user)
    except Exception as e:
        logging.error(f"Error retrieving current user: {str(e)}")
        raise credentials_exception

@router.post("/token", response_model=Token)
async def login_for_access_token(
    email: str = Form(...),
    password: str = Form(...)
):
    # Authenticate user by email
    token = await auth_service.login(email, password)
    return token

class SignupRequest(BaseModel):
    email: EmailStr
    username: str
    password: str

def create_access_token(email: str):
    expire = datetime.utcnow() + timedelta(minutes=60)
    to_encode = {"sub": email, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

# @router.post("/signup")
# async def signup(data: SignupRequest, db=Depends(get_db)):
#     ...
