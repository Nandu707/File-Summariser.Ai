from typing import List, Optional
from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    chat_id: Optional[str] = Field(
        default=None,
        description="The chat session ID"
    )
    doc_id: Optional[str] = Field(
        default="all",
        description="The unique ID of the indexed document or 'all' to search across all uploaded files"
    )
    question: str = Field(..., description="The user's question regarding the documents")

class CreateChatRequest(BaseModel):
    scope: Optional[str] = Field(default="all", description="'all' or 'file'")
    file_id: Optional[str] = Field(default=None, description="The file ID for single-file chats")
    file_name: Optional[str] = Field(default=None, description="The file name")
    title: Optional[str] = Field(default=None, description="Custom chat session title")

class RenameChatRequest(BaseModel):
    title: str = Field(..., description="The new title for the chat session")

class AskResponse(BaseModel):
    answer: str
    sources: List[int]
    source_documents: Optional[List[str]] = Field(
        default=None,
        description="List of document filenames cited in the answer"
    )
    source_details: Optional[List[dict]] = Field(
        default=None,
        description="Detailed list of cited sources with filename, doc_id, and page"
    )
    suggested_questions: Optional[List[str]] = Field(
        default=None,
        description="Sequential follow-up questions suggested by LLM relevant to the files and previous question"
    )

class SequentialQuestionsRequest(BaseModel):
    doc_id: Optional[str] = Field(default="all", description="The document ID or 'all'")
    question: str = Field(..., description="The previous user question")
    answer: Optional[str] = Field(default=None, description="The previous assistant answer (optional)")

class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    chunks: int
    suggested_questions: Optional[List[str]] = None

class SignupRequest(BaseModel):
    name: str = Field(..., description="User's full name")
    email: str = Field(..., description="User's email address")
    password: str = Field(..., min_length=8, description="User's password (min 8 chars)")

class LoginRequest(BaseModel):
    email: str = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: Optional[str] = None

class AuthResponse(BaseModel):
    token: str
    user: UserResponse
