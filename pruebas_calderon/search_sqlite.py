from semantic_search_sqlite import FaissSemanticSearchSQLite

searcher = FaissSemanticSearchSQLite("pdf_metadata.db", "faiss.index")

filters = {
    "author": ["Juan", "Ana"],
    "year": "2022",
    "keywords": "deep learning"
}

filters = {
}

results = searcher.search(
    query="José",
    k=10,
    sections=["Abstract", "Title", "Authors"],
    filters={}
)
