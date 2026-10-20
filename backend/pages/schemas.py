from typing import List, Optional
from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    doc_id: Optional[str] = Field(
        default="all",
        description="The unique ID of the indexed document or 'all' to search across all uploaded files"
    )
    question: str = Field(..., description="The user's question regarding the documents")

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
