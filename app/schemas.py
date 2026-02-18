from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional, List
from datetime import datetime
import re

class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=30)
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)

    @validator('email')
    @classmethod
    def validate_email(cls, v):
        email_str = str(v).lower()
        disposable_domains = ['tempmail.com', 'throwaway.email', '10minutemail.com',
                             'guerrillamail.com', 'mailinator.com', 'trashmail.com']
        domain = email_str.split('@')[1] if '@' in email_str else ''
        if domain in disposable_domains:
            raise ValueError('Disposable email addresses are not allowed')
        if len(email_str) > 254:
            raise ValueError('Email address is too long')
        local_part = email_str.split('@')[0] if '@' in email_str else ''
        if len(local_part) > 64:
            raise ValueError('Email local part is too long')
        return v

    @validator('full_name')
    @classmethod
    def validate_full_name(cls, v):
        if v is not None:
            if not re.match(r"^[a-zA-Z\s\-'.]+$", v):
                raise ValueError('Full name can only contain letters, spaces, hyphens, apostrophes, and periods')
            if '  ' in v:
                raise ValueError('Full name cannot contain consecutive spaces')
            v = v.strip()
            if len(v) < 2:
                raise ValueError('Full name must be at least 2 characters long')
        return v

    @validator('username')
    @classmethod
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username can only contain letters, numbers, hyphens, and underscores')
        if v[0].isdigit():
            raise ValueError('Username cannot start with a number')
        if '--' in v or '__' in v:
            raise ValueError('Username cannot contain consecutive hyphens or underscores')
        reserved_usernames = ['admin', 'root', 'administrator', 'system', 'api', 'null', 'undefined']
        if v.lower() in reserved_usernames:
            raise ValueError('This username is reserved and cannot be used')
        return v

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)

    @validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if len(v) > 128:
            raise ValueError('Password must not exceed 128 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', v):
            raise ValueError('Password must contain at least one special character')
        common_passwords = ['password', '12345678', 'qwerty123', 'admin123', 'letmein1', 'welcome1']
        if v.lower() in common_passwords:
            raise ValueError('This password is too common. Please choose a stronger password')
        return v

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None

class User(UserBase):
    id: int
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    email: EmailStr
    token: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)

    @validator('new_password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if len(v) > 128:
            raise ValueError('Password must not exceed 128 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:\'",.<>?/\\|`~]', v):
            raise ValueError('Password must contain at least one special character')
        common_passwords = ['password', '12345678', 'qwerty123', 'admin123', 'letmein1', 'welcome1']
        if v.lower() in common_passwords:
            raise ValueError('This password is too common. Please choose a stronger password')
        return v

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_private: bool = False

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"

class TaskCreate(TaskBase):
    project_id: int
    assignee_id: Optional[int] = None

# TaskUpdate uses all-optional fields so partial updates don't cause 422
class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[int] = None

class Task(TaskBase):
    id: int
    project_id: int
    assignee_id: Optional[int]
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True

class CommentBase(BaseModel):
    content: str

class CommentCreate(CommentBase):
    task_id: int

class Comment(CommentBase):
    id: int
    task_id: int
    author_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class FileUpload(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_size: int
    mime_type: Optional[str]
    project_id: int
    uploader_id: int
    created_at: datetime

    class Config:
        from_attributes = True
