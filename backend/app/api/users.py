from typing import Any
from uuid import UUID

from edgedb import AsyncIOConnection
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic.networks import EmailStr

from app import auth, crud, db, schemas
from app.config import settings
from app.utils import send_new_account_email

router = APIRouter()


@router.get("/", response_model=schemas.PaginatedUsers)
async def read_users(
    con: AsyncIOConnection = Depends(db.get_con),
    filtering: schemas.UserFilterParams = Depends(),
    commons: schemas.CommonQueryParams = Depends(),
    current_user: schemas.User = Depends(auth.get_current_active_superuser),
) -> Any:
    """
    Retrieve users.
    """
    paginated_users = await crud.user.get_multi(
        con,
        filtering=filtering.dict_exclude_unset(),
        ordering=commons.ordering,
        offset=commons.offset,
        limit=commons.limit,
    )
    return paginated_users


@router.post("/", response_model=schemas.User, status_code=201)
async def create_user(
    *,
    con: AsyncIOConnection = Depends(db.get_con),
    user_in: schemas.UserCreate,
    current_user: schemas.User = Depends(auth.get_current_active_superuser),
) -> Any:
    """
    Create new user.
    """
    user = await crud.user.get_by_email(con, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    user = await crud.user.create(con, obj_in=user_in)
    if settings.EMAILS_ENABLED and user_in.email:
        send_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
    return user


@router.put("/me", response_model=schemas.User)
async def update_user_me(
    *,
    con: AsyncIOConnection = Depends(db.get_con),
    password: str = Body(None),
    full_name: str = Body(None),
    email: EmailStr = Body(None),
    current_user: schemas.User = Depends(auth.get_current_active_user),
) -> Any:
    """
    Update own user.
    """
    current_user_data = jsonable_encoder(current_user)
    user_in = schemas.UserUpdate(**current_user_data)
    if password is not None:
        user_in.password = password
    if full_name is not None:
        user_in.full_name = full_name
    if email is not None:
        user_in.email = email
    user = await crud.user.update(con, id=current_user.id, obj_in=user_in)
    return user


@router.get("/me", response_model=schemas.User)
async def read_user_me(
    con: AsyncIOConnection = Depends(db.get_con),
    current_user: schemas.User = Depends(auth.get_current_active_user),
) -> Any:
    """
    Get current user.
    """
    return current_user


@router.post("/open", response_model=schemas.User, status_code=201)
async def create_user_open(
    *,
    con: AsyncIOConnection = Depends(db.get_con),
    password: str = Body(...),
    email: EmailStr = Body(...),
    full_name: str = Body(None),
) -> Any:
    """
    Create new user without the need to be logged in.
    """
    if not settings.USERS_OPEN_REGISTRATION:
        raise HTTPException(
            status_code=403,
            detail="Open user registration is forbidden on this server",
        )
    user = await crud.user.get_by_email(con, email=email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system",
        )
    user_in = schemas.UserCreate(password=password, email=email, full_name=full_name)
    user = await crud.user.create(con, obj_in=user_in)
    return user


@router.get("/{user_id}", response_model=schemas.User)
async def read_user(
    *,
    con: AsyncIOConnection = Depends(db.get_con),
    user_id: UUID,
    current_user: schemas.User = Depends(auth.get_current_active_user),
) -> Any:
    """
    Get user by id.
    """
    user = await crud.user.get(con, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=400, detail="The user doesn't have enough privileges"
        )
    return user


@router.put("/{user_id}", response_model=schemas.User)
async def update_user(
    *,
    con: AsyncIOConnection = Depends(db.get_con),
    user_id: UUID,
    user_in: schemas.UserUpdate,
    current_user: schemas.User = Depends(auth.get_current_active_user),
) -> Any:
    """
    Update a user.
    """
    user = await crud.user.get(con, id=user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this username does not exist in the system",
        )
    user = await crud.user.update(con, id=user_id, obj_in=user_in)
    return user


@router.delete("/{user_id}", response_model=schemas.User)
async def delete_user(
    *,
    con: AsyncIOConnection = Depends(db.get_con),
    user_id: UUID,
    current_user: schemas.User = Depends(auth.get_current_active_user),
) -> Any:
    """
    Delete a user.
    """
    user = await crud.user.get(con, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not current_user.is_superuser and (user.id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    user = await crud.user.remove(con, id=user_id)
    return user
