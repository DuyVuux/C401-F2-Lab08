from day08.lab.src.retrieval.rag_answer import rag_answer
if __name__ == "__main__":
    res = rag_answer("Test ERR-403 permission", retrieval_mode="master")
    print(res["answer"])
