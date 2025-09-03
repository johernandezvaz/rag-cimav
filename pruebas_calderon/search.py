from semantic_search import FaissSemanticSearch

searcher = FaissSemanticSearch("faiss.index", "chunks_with_metadata.json")

query = "Who is the first author?"
sections = ["First_Author"]

query = "What is the main objective of the IGWT framework?"
#query = "Why is explainability important in short-text NLP tasks?"
#query = "What challenges are associated with explainability in tweet classification?"
#query = "Name of the paper?"
query = " A Pre-Hoc Approach could be based in what ?"
sections = ["Title", "Abstract", "Introduction", "First_Author", "State_of_the_Art", "Methods"]


results = searcher.search(query, sections=sections)

print(f"Buscar: '{query}' en '{sections}'")

for r in results:
    print(f"\n[{r['section']}] {r['subsection']}")
    print(r["text"])
    print("Score:", r["score"])
