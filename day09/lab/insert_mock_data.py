import chromadb
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = chromadb.PersistentClient(path='./chroma_db')
col = client.get_or_create_collection('day09_docs')
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

docs = [
    {"fname": "SLA_policy.txt", "text": "SLA deadline for P1 tickets is 4 hours. P2 is 24 hours. For refund policies, check the finance document."},
    {"fname": "refund_policy.txt", "text": "Khách hàng yêu cầu hoàn tiền sau Flash Sale 8 ngày sẽ không được chấp nhận. Quy trình hoàn tiền thông thường là 14 ngày."},
]

for doc in docs:
    embedding = openai_client.embeddings.create(
        input=doc["text"], model="text-embedding-3-small"
    ).data[0].embedding
    col.upsert(
        ids=[doc["fname"]],
        embeddings=[embedding],
        documents=[doc["text"]],
        metadatas=[{'source': doc["fname"]}]
    )
print("Index ready with mock data for testing!")
