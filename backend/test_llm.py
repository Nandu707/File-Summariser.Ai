import os
from dotenv import load_dotenv
load_dotenv()
from google import genai

key = os.getenv('GEMINI_API_KEY')
print('Gemini key exists?', bool(key))
client = genai.Client(api_key=key)

prompt = """You are a helpful and strict document question-answering assistant.
Your task is to answer the user's question accurately based on the provided document context excerpts below.

CRITICAL RULES:
1. Base your answer strictly on the provided context excerpts below.
2. If the user asks for a summary, overview, or explanation of the document, provide a clear, concise summary using the facts and points present in the excerpts.
3. Whenever citing facts, include the corresponding source page number in parentheses (e.g., "(Page 2)").
4. Keep your answer factual, direct, and concise.
5. Only if the provided context excerpts are completely unrelated to the question should you state:
   "I cannot find the answer in the provided document context."

--- PROVIDED CONTEXT (TOP 4 CHUNKS) ---
[Excerpt 1 | Page 1]:
Nanda Kumar - Resume (AWS Engineer). Full Stack Developer with Python, Angular, TypeScript. Worked at Femtosoft Technologies.
--- END OF CONTEXT ---

Question: What is this document?

Strict Context-Only Answer:"""

for m in ['gemini-2.5-flash', 'gemini-3.5-flash-lite']:
    try:
        res = client.models.generate_content(model=m, contents=prompt)
        print(f'{m} response: {res.text.strip()}')
        break
    except Exception as e:
        print(f'{m} failed: {e}')
