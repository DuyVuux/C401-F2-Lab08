import re

content = "2, 0, 1"
indices = [int(x) for x in re.findall(r'\d+', content)]
print("Indices:", indices)

candidates = [
    {"id": "doc1"},  # 0
    {"id": "doc2"},  # 1
    {"id": "doc3"},  # 2
]

reranked = []
for rank, idx in enumerate(indices):
    if 0 <= idx < len(candidates):
        chunk = candidates[idx]
        score = 1.0 / (rank + 1)
        chunk["score"] = score
        reranked.append(chunk)

print("Reranked:", reranked)
