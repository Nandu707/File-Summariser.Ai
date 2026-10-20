import os
from dotenv import load_dotenv
from app.services.vector_store import VectorStoreService
from app.services.llm_service import LLMService
from app.services.chat_history_service import ChatHistoryService
from app.services.firebase_service import FirebaseService

load_dotenv()

# Singleton service instances
vector_store = VectorStoreService()
llm_service = LLMService()
chat_history = ChatHistoryService()
firebase_service = FirebaseService()
