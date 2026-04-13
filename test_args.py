def rerank(query, candidates, top_n=3):
    return top_n

try:
    rerank("a", [], top_k=5)
except Exception as e:
    print(e)
